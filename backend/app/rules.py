"""Deterministic rule engine. Every input channel and every world state element passes through these rules;
the outputs (attention, alerts, interventions, predictions, derived statuses) carry the rule id and the input ids
they were derived from, so any pixel on the map can be traced back. No learned model is involved."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import geo, predict
from .attention import Contribution
from .inputs import SEVERITY_RANK
from .models import Alert, GeoPosition, Intervention, InterventionOption, OutcomeBand, PredictedPath, SceneEntity, InputReport

ROAD_DISPATCH_MPS = 20.0  # a detachment leaving a site by road, synthetic planning figure
SEVERITY_WEIGHT = {"info": 0.15, "advisory": 0.4, "warning": 0.8, "critical": 1.4}


@dataclass
class Context:
    t: float
    now_iso: str
    revision: int
    entities: dict[str, SceneEntity]
    inputs: list[InputReport]
    areas: list[dict]
    committed: dict[str, dict]  # interventionId -> {optionId, committedAtS}
    acknowledged: set[str]
    cables: list[dict] = field(default_factory=list)
    sites: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass
class Effects:
    attention: list[Contribution] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    interventions: list[Intervention] = field(default_factory=list)
    predictions: list[PredictedPath] = field(default_factory=list)
    entity_status: dict[str, dict] = field(default_factory=dict)  # id -> {condition?, readinessDelta?, notes[]}
    area_status: dict[str, dict] = field(default_factory=dict)
    priorities: dict[str, float] = field(default_factory=dict)  # areaId -> multiplier
    traces: list[dict] = field(default_factory=list)
    stale_ids: set[str] = field(default_factory=set)
    deception: dict[str, dict] = field(default_factory=dict)  # subject id -> assessment (deception.py)
    fusion: dict[str, dict] = field(default_factory=dict)  # subject id -> source fusion (fusion.py)


Rule = Callable[[Context, Effects], None]
RULES: list[tuple[str, str, Rule]] = []


def rule(rule_id: str, title: str):
    def wrap(fn: Rule):
        RULES.append((rule_id, title, fn))
        return fn
    return wrap


# ---- helpers -----------------------------------------------------------------------------------
def pos(e: SceneEntity) -> tuple[float, float] | None:
    return (e.position.longitudeDeg, e.position.latitudeDeg) if e.position else None


CRUISE_MPS = {"fixed_wing": 230.0, "helicopter": 65.0, "multirotor": 15.0, "vessel": 10.0, "ground_vehicle": 16.0, "personnel": 1.4,
              "facility": ROAD_DISPATCH_MPS, "infrastructure": ROAD_DISPATCH_MPS}
MODEL_CRUISE_MPS = {"transport": 150.0, "aew": 190.0, "sigint": 200.0, "uav": 45.0, "police_car": 20.0, "ambulance": 18.0, "cb90": 18.0, "mbt": 13.0, "ifv": 14.0}


def speed_of(e: SceneEntity) -> float:
    """Planning speed: the platform class cruise speed (straight-line tasking estimate)."""
    if e.track:
        return e.track.speedMps
    return MODEL_CRUISE_MPS.get(e.modelKey or "", CRUISE_MPS.get(e.kind, 10.0))


def weather_penalty(ctx: Context, at: tuple[float, float] | None) -> float:
    """0..0.45 penalty for air/small-craft operations from active weather advisories covering the point."""
    if at is None:
        return 0.0
    pen = 0.0
    for i in ctx.inputs:
        if i.channel == "weather_advisory" and i.position and i.radiusM:
            if geo.haversine_m(at, (i.position.longitudeDeg, i.position.latitudeDeg)) <= i.radiusM:
                pen = max(pen, 0.15 + 0.1 * SEVERITY_RANK[i.severity])
    return min(0.45, pen)


MAX_TASKING_KM = {"fixed_wing": 600, "helicopter": 250, "multirotor": 12, "vessel": 250, "ground_vehicle": 300, "personnel": 15, "facility": 300, "infrastructure": 0, "unknown": 0, "formation": 0}


def candidates(ctx: Context, caps: list[str], target: tuple[float, float], domains: list[str] | None = None, limit: int = 3, exclude: set[str] = frozenset()) -> list[tuple[SceneEntity, float]]:
    out = []
    for e in ctx.entities.values():
        if e.affiliation not in ("own", "allied", "civil") or e.id in exclude or e.condition == "unavailable":
            continue
        if domains and e.domain not in domains:
            continue
        if e.position and geo.haversine_m((e.position.longitudeDeg, e.position.latitudeDeg), target) > MAX_TASKING_KM.get(e.kind, 0) * 1000:
            continue
        if caps and not any(c in e.capabilities for c in caps):
            continue
        p = pos(e)
        if not p:
            continue
        out.append((e, geo.haversine_m(p, target)))
    out.sort(key=lambda x: x[1])
    return out[:limit]


def make_option(ctx: Context, idx: int, e: SceneEntity, dist_m: float, target: tuple[float, float], title: str, steps: list[str], rule_ids: list[str],
                deadline_min: float | None, base_success: float, risk: str, cost: dict[str, float]) -> InterventionOption:
    spd = speed_of(e)
    eta_min = dist_m / spd / 60 if spd > 0 else None
    r = e.readiness.score if e.readiness else 0.6
    wp = weather_penalty(ctx, target) if e.domain == "air" or e.modelKey in ("patrol_boat",) else weather_penalty(ctx, target) * 0.3
    late = 0.0 if not deadline_min or eta_min is None else max(0.0, (eta_min - deadline_min) / max(deadline_min, 1)) * 0.5
    success = round(max(0.05, min(0.97, base_success + 0.35 * (r - 0.6) - wp - late)), 2)
    eta = eta_min or 0
    outcomes = [
        OutcomeBand(label="best", probability=round(success * 0.45, 2), timeToEffectMin=round(eta * 0.9, 1), description="Effect achieved early; no further resources needed."),
        OutcomeBand(label="expected", probability=round(success * 0.55, 2), timeToEffectMin=round(eta * 1.15, 1), description="Effect achieved on schedule with planned resources."),
        OutcomeBand(label="worst", probability=round(1 - success, 2), timeToEffectMin=round(eta * 1.6, 1), description="Effect delayed or not achieved; fallback option required."),
    ]
    return InterventionOption(id=f"opt-{idx}", title=f"{title}: {e.label}", rationale=f"{e.label} ({e.kind.replace('_', ' ')}, readiness {r:.2f}) is {dist_m / 1000:.0f} km away at {spd:.0f} m/s; weather penalty {wp:.2f}.",
                              steps=steps, assignedEntityIds=[e.id], etaMin=round(eta_min, 1) if eta_min is not None else None, successLikelihood=success,
                              riskLevel=risk, resourceCost=cost, outcomes=outcomes, ruleIds=rule_ids, distanceKm=round(dist_m / 1000, 1))  # type: ignore[arg-type]


def intervention(ctx: Context, fx: Effects, iv_id: str, alert: Alert, objective: str, target: tuple[float, float] | None, options: list[InterventionOption]) -> None:
    if not options:
        return
    ranked = sorted(options, key=lambda o: (-o.successLikelihood, o.etaMin or 0))
    committed = ctx.committed.get(iv_id)
    iv = Intervention(id=iv_id, alertId=alert.id, title=alert.title, objective=objective, position=list(target) if target else None, options=options,
                      recommendedOptionId=ranked[0].id)
    if committed:
        opt = next((o for o in options if o.id == committed["optionId"]), None)
        iv.committedOptionId = committed["optionId"]
        iv.committedAt = committed["committedAt"]
        eta_s = (opt.etaMin or 1) * 60 if opt else 600
        progress = min(1.0, (ctx.t - committed["committedAtS"]) / max(eta_s, 1))
        iv.progress = round(progress, 3)
        iv.status = "completed" if progress >= 1 else "in_progress"
    alert.recommendedInterventionId = iv_id
    fx.interventions.append(iv)


def alert(fx: Effects, ctx: Context, alert_id: str, severity: str, title: str, detail: str, rule_id: str, inputs: list[str], entities: list[str], layers: list[str], at: tuple[float, float] | None) -> Alert:
    a = Alert(id=alert_id, severity=severity, title=title, detail=detail, createdAt=ctx.now_iso, ruleId=rule_id, inputIds=inputs, entityIds=entities, layerIds=layers,  # type: ignore[arg-type]
              position=list(at) if at else None, acknowledged=alert_id in ctx.acknowledged)
    fx.alerts.append(a)
    return a


def inputs_for(ctx: Context, entity_id: str | None = None, channel: str | None = None, tag: str | None = None) -> list[InputReport]:
    return [i for i in ctx.inputs if (entity_id is None or entity_id in i.entityRefs) and (channel is None or i.channel == channel) and (tag is None or tag in i.tags)]


def layer_for(e: SceneEntity) -> str:
    return e.layer or {"air": "air.fighter", "land": "land.manoeuvre", "sea": "sea.combat", "site": "sites.land", "infra": "infra.comms", "unknown": "track.unknown"}[e.domain]


# ---- rules -------------------------------------------------------------------------------------
@rule("R01", "Unknown track approach and intercept planning")
def r01(ctx: Context, fx: Effects) -> None:
    own_targets = [e for e in ctx.entities.values() if e.affiliation == "own" and e.kind in ("facility", "infrastructure")]
    for e in ctx.entities.values():
        if e.affiliation != "unknown" or "small_uas" in e.tags:
            continue
        path = predict.dead_reckon(e, horizon_s=1800, step_s=60, t0=ctx.t)
        p = pos(e)
        if not p:
            continue
        downgraded = any("downgrade" in i.tags for i in inputs_for(ctx, e.id, "intel_report"))
        detections = inputs_for(ctx, e.id, "sensor_detection")
        threatened: list[tuple[SceneEntity, float, float]] = []
        if path:
            for tgt in own_targets:
                tp = pos(tgt)
                if not tp:
                    continue
                d, dt = predict.closest_approach(path, tp)
                if d < 60_000:
                    threatened.append((tgt, d, dt))
            threatened.sort(key=lambda x: x[1])
            path.threatenedEntityIds = [t[0].id for t in threatened[:5]]
            path.etaS = threatened[0][2] if threatened else None
            fx.predictions.append(path)
            fx.predictions.extend(predict.alternatives(e, path, [(t, pos(t)) for t in own_targets if pos(t)], ctx.t))
        sev = "advisory" if downgraded else ("critical" if threatened and threatened[0][1] < 25_000 else "warning")
        weight = SEVERITY_WEIGHT[sev] * (1.6 if e.domain == "air" else 1.2)
        fx.attention.append(Contribution(p[0], p[1], 45_000 if e.domain == "air" else 25_000, weight, f"Unknown track {e.label}", e.id, "R01"))
        if path:
            for k, (lng, lat, _t) in enumerate(path.points[1::6]):
                fx.attention.append(Contribution(lng, lat, 20_000, weight * 0.5 / (k + 1), f"Predicted path {e.label}", e.id, "R01"))
        for tgt, d, dt in threatened[:2]:
            tp = pos(tgt)
            fx.attention.append(Contribution(tp[0], tp[1], 15_000, weight * 0.8, f"{tgt.label} on predicted path of {e.label}", tgt.id, "R01"))
        detail = (f"{e.label} at {e.kinematics.speedMps:.0f} m/s heading {e.kinematics.headingDeg:.0f}°. " if e.kinematics else "") + \
                 (f"Closest approach {threatened[0][1] / 1000:.0f} km to {threatened[0][0].label} in {threatened[0][2] / 60:.0f} min. " if threatened else "No own asset on the 30 min predicted path. ") + \
                 ("J2 assesses the track as civil transport; posture unchanged." if downgraded else "Identity unresolved.")
        a = alert(fx, ctx, f"al-R01-{e.id}", sev, f"{e.label}: {'monitor' if downgraded else 'identify and shadow'}", detail, "R01",
                  [i.id for i in detections] + [i.id for i in inputs_for(ctx, e.id, "intel_report")], [e.id] + [t[0].id for t in threatened[:3]], ["track.unknown", "picture.predictions"], p)
        fx.traces.append({"rule": "R01", "subject": e.id, "severity": sev, "threatened": [t[0].id for t in threatened[:3]], "downgraded": downgraded})
        if downgraded:
            continue
        caps = ["air_patrol", "isr"] if e.domain == "air" else ["patrol", "surface", "sea_picture", "isr"]
        domains = ["air"] if e.domain == "air" else ["sea", "air"]
        opts = []
        for idx, (c, dist) in enumerate(candidates(ctx, caps, p, domains, limit=4), 1):
            steps = [f"Vector {c.label} toward predicted track of {e.label}", "Establish visual or electronic identification", "Report identity to joint picture", "Shadow until track leaves sector or is identified"]
            o = make_option(ctx, idx, c, dist, p, "Identify with", steps, ["R01"], deadline_min=(threatened[0][2] / 60 if threatened else 30), base_success=0.78 if c.domain == "air" else 0.62,
                            risk="medium" if sev == "critical" else "low", cost={"flightHours": round(dist / 1000 / 400, 2) if c.domain == "air" else 0, "crewHours": round(dist / speed_of(c) / 3600 * 2, 1)})
            if path:
                it = predict.intercept_time_s(pos(c), speed_of(c), path)  # type: ignore[arg-type]
                if it:
                    o.etaMin = round(it[0] / 60, 1)
                    o.rationale += f" Earliest intercept point {it[1][0]:.2f}, {it[1][1]:.2f} after {it[0] / 60:.0f} min."
            opts.append(o)
        intervention(ctx, fx, f"iv-R01-{e.id}", a, f"Identify {e.label} before it reaches own assets", p, opts)


@rule("R02", "Readiness and fuel thresholds")
def r02(ctx: Context, fx: Effects) -> None:
    for e in ctx.entities.values():
        if e.affiliation != "own" or not e.readiness or e.kind == "unknown":
            continue
        r = e.readiness
        if e.kind == "formation":
            continue
        low_fuel = r.fuelPct is not None and r.fuelPct < (12 if e.domain == "air" else 25)
        low_score = r.score < 0.45
        if not (low_fuel or low_score):
            continue
        p = pos(e)
        sev = "warning" if (r.fuelPct is not None and r.fuelPct < (8 if e.domain == "air" else 15)) or r.score < 0.3 else "advisory"
        if p:
            fx.attention.append(Contribution(p[0], p[1], 12_000, SEVERITY_WEIGHT[sev] * 0.6, f"Low readiness {e.label}", e.id, "R02"))
        a = alert(fx, ctx, f"al-R02-{e.id}", sev, f"{e.label}: readiness {r.score:.2f}" + (f", fuel {r.fuelPct:.0f} %" if low_fuel else ""),
                  "Below the sustainment threshold (fuel < 25 %, aircraft < 12 %, or readiness < 0.45). Resupply, recovery or rotation recommended.", "R02",
                  [i.id for i in inputs_for(ctx, e.id, tag="fuel")], [e.id], [layer_for(e)], p)
        if p and low_fuel and e.domain != "air":
            opts = [make_option(ctx, i, c, d, p, "Resupply from", [f"Dispatch fuel from {c.label}", f"Rendezvous with {e.label}", "Confirm fuel state ≥ 70 %"], ["R02"], 240, 0.85, "low", {"fuelM3": 6, "crewHours": 8})
                    for i, (c, d) in enumerate(candidates(ctx, ["fuel", "supply"], p, ["land", "sea", "site"], limit=3, exclude={e.id}), 1)]
            intervention(ctx, fx, f"iv-R02-{e.id}", a, f"Restore fuel autonomy of {e.label}", p, opts)


@rule("R03", "Reported faults and maintenance")
def r03(ctx: Context, fx: Effects) -> None:
    for i in ctx.inputs:
        if "fault" not in i.tags or i.channel not in ("maintenance_log", "field_report", "unit_sitrep"):
            continue
        for eid in i.entityRefs:
            e = ctx.entities.get(eid)
            if not e or e.kind in ("facility", "infrastructure"):
                continue
            st = fx.entity_status.setdefault(eid, {"notes": []})
            st["condition"] = "degraded" if e.condition == "normal" else e.condition
            st["notes"].append(f"{i.channel}: {i.title}")
            p = pos(e)
            if p:
                fx.attention.append(Contribution(p[0], p[1], 10_000, 0.5, f"Fault reported on {e.label}", e.id, "R03"))
            a = alert(fx, ctx, f"al-R03-{eid}", "warning", f"{e.label}: fault reported", i.text, "R03", [i.id], [eid], [layer_for(e)], p)
            if p:
                opts = [make_option(ctx, k, c, d, p, "Recover with", [f"Dispatch {c.label} to {e.label}", "Assess and repair in place or recover to workshop", "Return unit to normal condition"], ["R03"], 180, 0.8, "low", {"crewHours": 12, "spares": 1})
                        for k, (c, d) in enumerate(candidates(ctx, ["maintenance", "spares"], p, ["land", "site"], limit=3, exclude={eid}), 1)]
                intervention(ctx, fx, f"iv-R03-{eid}", a, f"Return {e.label} to full mobility", p, opts)


@rule("R04", "Communications degradation")
def r04(ctx: Context, fx: Effects) -> None:
    for e in ctx.entities.values():
        reports = [i for i in ctx.inputs if e.id in i.entityRefs and ("comms" in i.tags or "cyber" in i.tags)]
        lost = e.readiness is not None and e.readiness.commsStatus in ("degraded", "lost")
        if not reports and not lost:
            continue
        p = pos(e)
        sev = "critical" if (e.readiness and e.readiness.commsStatus == "lost") else "warning"
        if "comms_hub" in e.capabilities:
            fx.entity_status.setdefault(e.id, {"notes": []})["condition"] = "degraded"
        if p:
            fx.attention.append(Contribution(p[0], p[1], 30_000 if "comms_hub" in e.capabilities else 8_000, SEVERITY_WEIGHT[sev], f"Communications degraded at {e.label}", e.id, "R04"))
        a = alert(fx, ctx, f"al-R04-{e.id}", sev, f"{e.label}: communications degraded", "; ".join(i.title for i in reports) or "Comms status reported degraded.", "R04",
                  [i.id for i in reports], [e.id], [layer_for(e)], p)
        if p and "comms_hub" in e.capabilities:
            opts = [make_option(ctx, k, c, d, p, "Restore with", [f"Reposition {c.label} as relay for {e.label}", "Re-establish priority circuits", "Verify end-to-end connectivity"], ["R04"], 120, 0.75, "medium", {"crewHours": 10})
                    for k, (c, d) in enumerate(candidates(ctx, ["comms_hub"], p, ["land", "site"], limit=3, exclude={e.id}), 1)]
            intervention(ctx, fx, f"iv-R04-{e.id}", a, f"Restore communications capacity at {e.label}", p, opts)


@rule("R05", "Infrastructure outages and dependent sites")
def r05(ctx: Context, fx: Effects) -> None:
    for i in ctx.inputs:
        if i.channel != "infrastructure_status" or SEVERITY_RANK[i.severity] < 1:
            continue
        node = next((ctx.entities[r] for r in i.entityRefs if r in ctx.entities and ctx.entities[r].kind == "infrastructure"), None)
        if not node:
            continue
        p = pos(node)
        fx.entity_status.setdefault(node.id, {"notes": []})["condition"] = "degraded"
        dependents = [ctx.entities[r] for r in i.entityRefs if r in ctx.entities and r != node.id]
        if p:
            fx.attention.append(Contribution(p[0], p[1], i.radiusM or 40_000, SEVERITY_WEIGHT[i.severity] * 1.2, f"{i.title}", node.id, "R05"))
        for dep in dependents:
            st = fx.entity_status.setdefault(dep.id, {"notes": []})
            st["readinessDelta"] = st.get("readinessDelta", 0) - 0.15
            st["notes"].append(f"Depends on {node.label}: {i.title}")
        a = alert(fx, ctx, f"al-R05-{node.id}", i.severity, i.title, i.text + (f" Dependent sites: {', '.join(d.label for d in dependents)}." if dependents else ""), "R05",
                  [i.id], [node.id] + [d.id for d in dependents], list(dict.fromkeys([layer_for(node)] + [layer_for(d) for d in dependents])), p)
        if p and "power" in i.tags:
            opts = [make_option(ctx, k, c, d, p, "Bridge outage with", [f"Deploy {c.label} with generator sets to dependent sites", "Prioritise medical, comms and command circuits", "Stand down when grid restores"], ["R05"], 180, 0.7, "medium", {"crewHours": 24, "generators": 2})
                    for k, (c, d) in enumerate(candidates(ctx, ["engineering", "logistics", "supply"], p, ["land", "site"], limit=3), 1)]
            intervention(ctx, fx, f"iv-R05-{node.id}", a, f"Keep dependent sites functional during {node.label} outage", p, opts)


@rule("R06", "Civil emergency support")
def r06(ctx: Context, fx: Effects) -> None:
    for i in ctx.inputs:
        if i.channel != "civil_emergency" or not i.position:
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        fx.attention.append(Contribution(p[0], p[1], i.radiusM or 5_000, SEVERITY_WEIGHT[i.severity] * 1.3, i.title, i.id, "R06"))
        a = alert(fx, ctx, f"al-R06-{i.id}", i.severity, i.title, i.text, "R06", [i.id], [], ["picture.reports"], p)
        opts = []
        k = 1
        for c, d in candidates(ctx, ["medevac", "sar"], p, ["air"], limit=2):
            opts.append(make_option(ctx, k, c, d, p, "Medevac with", [f"Launch {c.label} to incident", "Triage with regional ambulance command", "Transport critical casualties to nearest hospital"], ["R06"], 45, 0.8, "medium", {"flightHours": round(d / 1000 / 200, 2), "crewHours": 6}))
            k += 1
        for c, d in candidates(ctx, ["medical"], p, ["land", "site"], limit=2):
            opts.append(make_option(ctx, k, c, d, p, "Medical team from", [f"Dispatch medical team from {c.label}", "Support triage and evacuation", "Hand over to civil healthcare"], ["R06"], 90, 0.7, "low", {"crewHours": 10}))
            k += 1
        intervention(ctx, fx, f"iv-R06-{i.id}", a, "Support civil rescue with military medical capacity", p, opts)


@rule("R07", "Weather advisories")
def r07(ctx: Context, fx: Effects) -> None:
    for i in ctx.inputs:
        if i.channel != "weather_advisory" or not i.position:
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        fx.attention.append(Contribution(p[0], p[1], i.radiusM or 50_000, SEVERITY_WEIGHT[i.severity] * 0.5, i.title, i.id, "R07"))
        affected = [e.id for e in ctx.entities.values() if e.domain in ("air", "sea") and pos(e) and geo.haversine_m(pos(e), p) <= (i.radiusM or 50_000)]  # type: ignore[arg-type]
        for eid in affected:
            st = fx.entity_status.setdefault(eid, {"notes": []})
            st["readinessDelta"] = st.get("readinessDelta", 0) - 0.1
            st["notes"].append(f"Weather: {i.title}")
        alert(fx, ctx, f"al-R07-{i.id}", "advisory", i.title, i.text + f" {len(affected)} air/sea units inside the advisory area.", "R07", [i.id], affected[:40], ["env.warnings"], p)


@rule("R08", "Intelligence assessments raise area priority")
def r08(ctx: Context, fx: Effects) -> None:
    for i in ctx.inputs:
        if i.channel != "intel_report" or SEVERITY_RANK[i.severity] < 1:
            continue
        for ref in i.entityRefs:
            if ref.startswith("area-"):
                fx.priorities[ref] = fx.priorities.get(ref, 1.0) * 1.3
        if i.position:
            fx.attention.append(Contribution(i.position.longitudeDeg, i.position.latitudeDeg, i.radiusM or 80_000, SEVERITY_WEIGHT[i.severity] * 0.9, i.title, i.id, "R08"))
        alert(fx, ctx, f"al-R08-{i.id}", i.severity, i.title, i.text, "R08", [i.id], [r for r in i.entityRefs if r in ctx.entities], ["picture.areas", "track.unknown"],
              (i.position.longitudeDeg, i.position.latitudeDeg) if i.position else None)


@rule("R10", "Operational area coverage")
def r10(ctx: Context, fx: Effects) -> None:
    for area in ctx.areas:
        if area["kind"] != "operational_area":
            continue
        req = [ctx.entities[r] for r in area["requires"] if r in ctx.entities]
        blockers = []
        for e in req:
            cond = fx.entity_status.get(e.id, {}).get("condition", e.condition)
            if cond != "normal":
                blockers.append(f"{e.label} is {cond}")
            elif e.readiness and e.readiness.score < 0.5:
                blockers.append(f"{e.label} readiness {e.readiness.score:.2f}")
        mult = fx.priorities.get(area["id"], 1.0)
        status = "covered" if not blockers else ("degraded" if len(blockers) < len(req) else "uncovered")
        fx.area_status[area["id"]] = {"status": status, "blockers": blockers, "priority": round(area["priority"] / mult, 2), "requires": area["requires"]}
        if blockers:
            ring = area["ring"]
            cx = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
            cy = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
            fx.attention.append(Contribution(cx, cy, 70_000, 0.7 * mult * len(blockers), f"{area['label']} {status}", area["id"], "R10"))
            alert(fx, ctx, f"al-R10-{area['id']}", "warning" if status == "degraded" else "critical", f"{area['label']}: {status}", "; ".join(blockers), "R10", [], [e.id for e in req], ["picture.areas"], (cx, cy))


@rule("R11", "Directives set priorities")
def r11(ctx: Context, fx: Effects) -> None:
    for i in ctx.inputs:
        if i.channel not in ("command_directive", "head_of_state_directive"):
            continue
        mult = 1.5 if i.channel == "command_directive" else 2.0
        for ref in i.entityRefs:
            if ref.startswith("area-"):
                fx.priorities[ref] = fx.priorities.get(ref, 1.0) * mult
            e = ctx.entities.get(ref)
            if e and pos(e):
                p = pos(e)
                fx.attention.append(Contribution(p[0], p[1], 25_000, 0.9 * mult / 1.5, f"Directive: {i.title}", e.id, "R11"))
        alert(fx, ctx, f"al-R11-{i.id}", i.severity, i.title, i.text, "R11", [i.id], [r for r in i.entityRefs if r in ctx.entities], ["picture.areas"], None)


@rule("R12", "Stale reporting")
def r12(ctx: Context, fx: Effects) -> None:
    for e in ctx.entities.values():
        if e.affiliation != "own" or e.kind in ("facility", "infrastructure"):
            continue
        if e.readiness and e.readiness.commsStatus == "lost":
            fx.stale_ids.add(e.id)


@rule("R13", "Mid-intervention monitoring")
def r13(ctx: Context, fx: Effects) -> None:
    for iv in fx.interventions:
        if iv.status not in ("in_progress", "completed") or not iv.committedOptionId:
            continue
        opt = next((o for o in iv.options if o.id == iv.committedOptionId), None)
        if not opt:
            continue
        issues = []
        for eid in opt.assignedEntityIds:
            e = ctx.entities.get(eid)
            if not e:
                continue
            cond = fx.entity_status.get(eid, {}).get("condition", e.condition)
            if cond != "normal":
                issues.append(f"{e.label} is {cond}")
            if e.readiness and e.readiness.fuelPct is not None and e.readiness.fuelPct < 25:
                issues.append(f"{e.label} fuel {e.readiness.fuelPct:.0f} %")
        if iv.position and weather_penalty(ctx, tuple(iv.position)) >= 0.25:  # type: ignore[arg-type]
            issues.append("weather advisory now covers the objective")
        if iv.status == "completed":
            iv.monitorAlerts.append(f"Completed: {opt.title}")
            continue
        if issues:
            a = alert(fx, ctx, f"al-R13-{iv.id}", "warning", f"Re-plan {iv.title}", "; ".join(issues) + ". Alternative options remain ranked in the intervention.", "R13", [], opt.assignedEntityIds, ["picture.interventions"],
                      tuple(iv.position) if iv.position else None)  # type: ignore[arg-type]
            iv.monitorAlerts.append(a.id)
        else:
            iv.monitorAlerts.append(f"On track: {opt.title} {iv.progress * 100:.0f} %")


@rule("R14", "Open-source reporting near own activity")
def r14(ctx: Context, fx: Effects) -> None:
    for i in ctx.inputs:
        if i.channel != "public_news" or not i.position:
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        fx.attention.append(Contribution(p[0], p[1], i.radiusM or 20_000, 0.25, i.title, i.id, "R14"))
        alert(fx, ctx, f"al-R14-{i.id}", "info", i.title, i.text + " Operational security review recommended.", "R14", [i.id], [r for r in i.entityRefs if r in ctx.entities], ["picture.reports"], p)


@rule("R15", "Allied offers become intervention options")
def r15(ctx: Context, fx: Effects) -> None:
    offers = [i for i in ctx.inputs if i.channel == "allied_liaison" and "offer" in i.tags]
    if not offers:
        return
    for iv in fx.interventions:
        if iv.id.startswith("iv-R01-unk-sea") or iv.id.startswith("iv-R01-unk-air"):
            for o in offers:
                iv.options.append(InterventionOption(id=f"opt-allied-{o.id}", title=f"Request allied maritime patrol ({o.author})", rationale=o.text, steps=["Submit tasking request via liaison", "Share track data", "Receive identification report"],
                                                     assignedEntityIds=[], etaMin=90, successLikelihood=0.66, riskLevel="low", resourceCost={"liaisonHours": 2}, ruleIds=["R15", "R01"],
                                                     outcomes=[OutcomeBand(label="best", probability=0.3, timeToEffectMin=70, description="Allied sortie identifies the track."),
                                                               OutcomeBand(label="expected", probability=0.36, timeToEffectMin=100, description="Identification during the sortie window."),
                                                               OutcomeBand(label="worst", probability=0.34, timeToEffectMin=180, description="Sortie not tasked in time.")]))


@rule("R16", "Small UAS activity near protected sites")
def r16(ctx: Context, fx: Effects) -> None:
    """Sensor-held small UAS tracks and drone reports within 6 km of an own site raise a counter-UAS response."""
    sites = [e for e in ctx.entities.values() if e.kind in ("facility", "infrastructure") and e.affiliation in ("own", "civil")]
    groups: dict[str, list[tuple[str, float]]] = {}
    for e in ctx.entities.values():
        if e.affiliation != "unknown" or "small_uas" not in e.tags or not pos(e):
            continue
        near = min(((s, geo.haversine_m(pos(e), pos(s))) for s in sites if pos(s)), key=lambda x: x[1], default=None)  # type: ignore[arg-type]
        if near and near[1] < 6000:
            groups.setdefault(near[0].id, []).append((e.id, near[1]))
    reports: dict[str, list[InputReport]] = {}
    for i in ctx.inputs:
        if "drone" in i.tags or "small_uas" in i.tags:
            for ref in i.entityRefs:
                if ref in ctx.entities and ctx.entities[ref].kind in ("facility", "infrastructure"):
                    reports.setdefault(ref, []).append(i)
    for sid in set(groups) | set(reports):
        site = ctx.entities[sid]
        p = pos(site)
        tracks = groups.get(sid, [])
        reps = reports.get(sid, [])
        sev = "critical" if len(tracks) >= 2 else "warning"
        if p:
            fx.attention.append(Contribution(p[0], p[1], 8_000, SEVERITY_WEIGHT[sev] * 1.4, f"Small UAS activity at {site.label}", sid, "R16"))
        detail = (f"{len(tracks)} small UAS track(s) held within {max((d for _, d in tracks), default=0) / 1000:.1f} km of {site.label}. " if tracks else "") +                  (f"{len(reps)} report(s): " + "; ".join(r.title for r in reps[-3:]) + ". " if reps else "") +                  "Pattern consistent with reconnaissance of the site (persistent orbit, low level)."
        a = alert(fx, ctx, f"al-R16-{sid}", sev, f"{site.label}: small UAS activity", detail, "R16", [r.id for r in reps], [sid] + [t for t, _ in tracks],
                  ["track.unknown", "sites.air" if "fighter" in site.capabilities or "transport" in site.capabilities else "sites.land"], p)
        fx.traces.append({"rule": "R16", "subject": sid, "tracks": [t for t, _ in tracks], "reports": [r.id for r in reps]})
        if not p:
            continue
        opts = []
        k = 1
        for c, d in candidates(ctx, ["air_defence"], p, ["land"], limit=2):
            opts.append(make_option(ctx, k, c, d, p, "Counter-UAS with", [f"Cue {c.label} sensors on the UAS tracks", "Positive identification before engagement", "Engage per rules of engagement or jam"], ["R16"], 20, 0.72, "medium", {"crewHours": 4}))
            k += 1
        for c, d in candidates(ctx, ["guard", "law_enforcement"], p, ["land"], limit=2):
            opts.append(make_option(ctx, k, c, d, p, "Ground search with", [f"Dispatch {c.label} to likely launch points", "Search and secure operator", "Report to the joint picture"], ["R16"], 40, 0.55, "low", {"crewHours": 6}))
            k += 1
        intervention(ctx, fx, f"iv-R16-{sid}", a, f"Deny UAS reconnaissance of {site.label}", p, opts)


@rule("R18", "GNSS interference")
def r18(ctx: Context, fx: Effects) -> None:
    """Reports of GNSS jamming or spoofing degrade navigation for every air and sea platform inside the area."""
    for i in ctx.inputs:
        if not ({"gnss", "spoofing"} & set(i.tags)) or not i.position:
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        r = i.radiusM or 100_000
        affected = [e for e in ctx.entities.values() if e.domain in ("air", "sea") and e.affiliation in ("own", "civil") and pos(e) and geo.haversine_m(pos(e), p) <= r]  # type: ignore[arg-type]
        for e in affected:
            st = fx.entity_status.setdefault(e.id, {"notes": []})
            st["readinessDelta"] = st.get("readinessDelta", 0) - 0.08
            st["notes"].append(f"GNSS degraded: {i.title}")
        fx.attention.append(Contribution(p[0], p[1], r, SEVERITY_WEIGHT[i.severity] * 0.9, i.title, i.id, "R18"))
        alert(fx, ctx, f"al-R18-{i.id}", i.severity, i.title, i.text + f" {len(affected)} own or civil air/sea platforms inside the area; inertial or terrestrial navigation advised.",
              "R18", [i.id], [e.id for e in affected][:40], ["analysis.gnss", "air.fighter", "sea.combat"], p)


AIS_DARK_WINDOW = (900.0, 1500.0, 1800.0)  # scripted: the suspect tanker stops transmitting 900–1500 s into every 30 min


@rule("R17", "Maritime anomaly over undersea infrastructure")
def r17(ctx: Context, fx: Effects) -> None:
    """Slow loitering within 3 km of an undersea cable or pipeline, plus AIS gaps, indicate a sabotage risk."""
    for e in ctx.entities.values():
        if e.domain != "sea" or e.affiliation not in ("unknown", "hostile_suspected") or not pos(e):
            continue
        p = pos(e)
        near = None
        for c in ctx.cables:
            d = _dist_to_line(p, c["coords"])  # type: ignore[arg-type]
            if d < 3000 and (near is None or d < near[1]):
                near = (c, d)
        dark = "ais_gaps" in e.tags and AIS_DARK_WINDOW[0] <= ctx.t % AIS_DARK_WINDOW[2] < AIS_DARK_WINDOW[1]
        if dark:
            fx.entity_status.setdefault(e.id, {"notes": []}).setdefault("flags", []).append("dark")
        slow = e.kinematics is not None and (e.kinematics.speedMps or 0) < 1.6
        if not near or not (slow or dark):
            continue  # transiting across a corridor at speed is normal traffic
        cable, d = near
        sev = "critical" if (dark or "ais_gaps" in e.tags) and slow else "warning"
        fx.attention.append(Contribution(p[0], p[1], 15_000, SEVERITY_WEIGHT[sev] * 1.3, f"{e.label} loitering over {cable['label']}", e.id, "R17"))
        detail = f"{e.label} at {(e.kinematics.speedMps or 0) * 1.944:.1f} kn, {d:.0f} m from {cable['label']}. " +                  ("AIS transmissions currently absent (dark period). " if dark else ("Intermittent AIS gaps recorded. " if "ais_gaps" in e.tags else "")) +                  "Slow, course-changing movement over the corridor is consistent with anchor dragging or survey activity."
        a = alert(fx, ctx, f"al-R17-{e.id}", sev, f"{e.label}: loitering over undersea infrastructure", detail, "R17",
                  [i.id for i in inputs_for(ctx, e.id)], [e.id], ["track.unknown", "infra.cables"], p)
        fx.traces.append({"rule": "R17", "subject": e.id, "cable": cable["id"], "distanceM": round(d), "dark": dark, "slow": slow})
        opts = []
        for k, (c, dist) in enumerate(candidates(ctx, ["patrol", "surface", "sar"], p, ["sea", "air"], limit=3), 1):
            opts.append(make_option(ctx, k, c, dist, p, "Shadow and hail with", [f"Vector {c.label} to {e.label}", "Hail on VHF 16 and request intentions", "Document anchor position and seabed contact", "Coordinate with coast guard for boarding"],
                                    ["R17"], 90, 0.7 if c.domain == "sea" else 0.6, "medium", {"crewHours": round(dist / speed_of(c) / 3600 * 2, 1)}))
        intervention(ctx, fx, f"iv-R17-{e.id}", a, f"Protect {cable['label']} and establish intent of {e.label}", p, opts)


def _dist_to_line(p: tuple[float, float], coords: list[list[float]]) -> float:
    """Approximate distance in metres from p to a polyline (local equirectangular projection)."""
    import math as _m
    kx = 111_320 * _m.cos(_m.radians(p[1]))
    best = float("inf")
    for a, b in zip(coords, coords[1:]):
        ax, ay = (a[0] - p[0]) * kx, (a[1] - p[1]) * 110_540
        bx, by = (b[0] - p[0]) * kx, (b[1] - p[1]) * 110_540
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1e-9
        f = max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
        best = min(best, _m.hypot(ax + f * dx, ay + f * dy))
    return best


def evaluate(ctx: Context) -> Effects:
    fx = Effects()
    for rule_id, _title, fn in RULES:
        fn(ctx, fx)
    # Dedupe alerts by id (a rule may fire once per input per entity) keeping the highest severity.
    seen: dict[str, Alert] = {}
    for a in fx.alerts:
        if a.id not in seen or SEVERITY_RANK[a.severity] > SEVERITY_RANK[seen[a.id].severity]:
            seen[a.id] = a
    fx.alerts = sorted(seen.values(), key=lambda a: (-SEVERITY_RANK[a.severity], a.id))
    from . import deception, fusion  # noqa: PLC0415  (assessment layers run after every rule has fired)
    fx.fusion = fusion.assess(ctx, fx)
    fx.deception = deception.assess(ctx, fx)
    return fx


def rule_catalogue() -> list[dict]:
    return [{"id": rid, "title": title} for rid, title, _ in RULES]
