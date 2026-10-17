"""Deterministic rule engine. Every input channel and every world state element passes through these rules;
the outputs (attention, alerts, interventions, predictions, derived statuses) carry the rule id and the input ids
they were derived from, so any pixel on the map can be traced back. No learned model is involved."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
    # Sensor track history for unknown tracks: id -> {"dtS", "lng", "lat", "headingDeg", "speedMps"} observed dtS seconds ago.
    history: dict[str, dict] = field(default_factory=dict)


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
    priority_basis: dict[str, dict[str, tuple[float, str, str]]] = field(default_factory=dict)  # areaId -> source key -> (mult, inputId, title)


Rule = Callable[[Context, Effects], None]
RULES: list[tuple[str, str, Rule]] = []
# Rules that read other rules' output run after all the rest (and after interventions settle), in catalogue order:
# R10 needs every priority multiplier (R08 intelligence and R11 directives) and every derived condition; R13 needs every
# intervention, whichever rule raised it.
POST_RULES = {"R10", "R13"}


def rule(rule_id: str, title: str):
    def wrap(fn: Rule):
        RULES.append((rule_id, title, fn))
        return fn
    return wrap


def parse_iso(s: str | None) -> datetime | None:
    """Timezone-aware datetime from an ISO string (with 'Z' or an offset); None when unparsable."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def is_active(ctx: Context, i: InputReport) -> bool:
    """True when the report is in force at scenario time (effectiveAt not in the future, e.g. a forecast warning)."""
    eff, now = parse_iso(i.effectiveAt), parse_iso(ctx.now_iso)
    return eff is None or now is None or eff <= now + timedelta(seconds=1)


def penalise(fx: Effects, eid: str, cause: str, delta: float, note: str) -> None:
    """Readiness penalty that does not stack within one cause: two overlapping weather warnings or two reports of the
    same outage cost the same as one (the worst counts). Different causes add up."""
    st = fx.entity_status.setdefault(eid, {"notes": []})
    pens = st.setdefault("penalties", {})
    pens[cause] = min(pens.get(cause, 0.0), delta)
    st["readinessDelta"] = round(sum(pens.values()), 3)
    if note not in st["notes"]:
        st["notes"].append(note)


def raise_priority(fx: Effects, area_id: str, mult: float, source: str, i: InputReport) -> None:
    """Area priority multiplier: the strongest input per source kind counts, kinds multiply. A re-issued directive or a
    second intelligence report on the same area does not compound."""
    basis = fx.priority_basis.setdefault(area_id, {})
    if source not in basis or mult > basis[source][0]:
        basis[source] = (mult, i.id, i.title)
    total = 1.0
    for m, _iid, _title in basis.values():
        total *= m
    fx.priorities[area_id] = round(total, 3)


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


def weather_cover(ctx: Context, at: tuple[float, float] | None) -> tuple[float, InputReport | None]:
    """(0..0.45 penalty, the advisory responsible) for air/small-craft operations at a point. Only advisories in force
    count: a warning valid from later today is a forecast, not a penalty now."""
    if at is None:
        return 0.0, None
    pen, worst = 0.0, None
    for i in ctx.inputs:
        if i.channel == "weather_advisory" and i.position and i.radiusM and is_active(ctx, i):
            if geo.haversine_m(at, (i.position.longitudeDeg, i.position.latitudeDeg)) <= i.radiusM:
                p = 0.15 + 0.1 * SEVERITY_RANK[i.severity]
                if p > pen:
                    pen, worst = p, i
    return min(0.45, pen), worst


def weather_penalty(ctx: Context, at: tuple[float, float] | None) -> float:
    """0..0.45 penalty for air/small-craft operations from active weather advisories covering the point."""
    return weather_cover(ctx, at)[0]


MAX_TASKING_KM = {"fixed_wing": 600, "helicopter": 250, "multirotor": 12, "vessel": 250, "ground_vehicle": 300, "personnel": 15, "facility": 300, "infrastructure": 0, "unknown": 0, "formation": 0}
TASKING_FUEL_FLOOR = {"air": 15.0}  # below this fuel % a platform is not offered for new tasking (default 10 %)


def taskable(e: SceneEntity) -> bool:
    """A unit that cannot receive orders (comms lost) or would run dry on the way is not a real option."""
    r = e.readiness
    if r is None:
        return True
    if r.commsStatus == "lost":
        return False
    return r.fuelPct is None or r.fuelPct >= TASKING_FUEL_FLOOR.get(e.domain, 10.0)


def candidates(ctx: Context, caps: list[str], target: tuple[float, float], domains: list[str] | None = None, limit: int = 3, exclude: set[str] = frozenset()) -> list[tuple[SceneEntity, float]]:
    out = []
    for e in ctx.entities.values():
        if e.affiliation not in ("own", "allied", "civil") or e.id in exclude or e.condition == "unavailable" or not taskable(e):
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
                deadline_min: float | None, base_success: float, risk: str, cost: dict[str, float], eta_override_min: float | None = None,
                eta_basis: str | None = None) -> InterventionOption:
    """One tasking option. `eta_override_min` (e.g. an intercept time on a moving track) replaces the straight-line
    transit time *before* success and outcome bands are computed, so all three agree."""
    spd = speed_of(e)
    eta_min = eta_override_min if eta_override_min is not None else (dist_m / spd / 60 if spd > 0 else None)
    r = e.readiness.score if e.readiness else 0.6
    wp_full, wx = weather_cover(ctx, target)
    exposed = e.domain == "air" or e.modelKey in ("patrol_boat",)
    wp = wp_full if exposed else wp_full * 0.3
    late = 0.0 if not deadline_min or eta_min is None else max(0.0, (eta_min - deadline_min) / max(deadline_min, 1)) * 0.5
    success = round(max(0.05, min(0.97, base_success + 0.35 * (r - 0.6) - wp - late)), 2)
    eta = eta_min or 0
    outcomes = [
        OutcomeBand(label="best", probability=round(success * 0.45, 2), timeToEffectMin=round(eta * 0.9, 1), description="Effect achieved early; no further resources needed."),
        OutcomeBand(label="expected", probability=round(success * 0.55, 2), timeToEffectMin=round(eta * 1.15, 1), description="Effect achieved on schedule with planned resources."),
        OutcomeBand(label="worst", probability=round(1 - success, 2), timeToEffectMin=round(eta * 1.6, 1), description="Effect delayed or not achieved; fallback option required."),
    ]
    why = [f"{e.label} ({e.kind.replace('_', ' ')}, readiness {r:.2f}) is {dist_m / 1000:.0f} km away (straight line) at {spd:.0f} m/s"]
    if eta_basis:
        why.append(eta_basis)
    why.append(f"success = {base_success:.2f} base + 0.35 × (readiness − 0.6) = {0.35 * (r - 0.6):+.2f}")
    if wx is not None and wp > 0:
        why.append(f"− weather {wp:.2f} ({wx.title}, {wx.id}{'' if exposed else '; ×0.3 for a weather-tolerant platform'})")
    else:
        why.append("no weather advisory in force over the objective")
    if late > 0:
        why.append(f"− late {late:.2f} (ETA {eta:.0f} min against a {deadline_min:.0f} min deadline)")
    return InterventionOption(id=f"opt-{e.id}", title=f"{title}: {e.label}", rationale="; ".join(why) + f" → {success:.2f}.",
                              steps=steps, assignedEntityIds=[e.id], etaMin=round(eta_min, 1) if eta_min is not None else None, successLikelihood=success,
                              riskLevel=risk, resourceCost=cost, outcomes=outcomes, ruleIds=rule_ids, distanceKm=round(dist_m / 1000, 1))  # type: ignore[arg-type]


def intervention(ctx: Context, fx: Effects, iv_id: str, alert: Alert, objective: str, target: tuple[float, float] | None, options: list[InterventionOption]) -> None:
    """Register an intervention. Option ids name the assigned unit (stable while candidates re-rank as units move, so a
    committed option keeps pointing at the unit the operator chose). Recommendation and committed progress are
    settled once every rule has run (`settle_interventions`), so options added later (allied offers) count too."""
    if not options:
        return
    seen: dict[str, int] = {}
    for o in options:
        n = seen.get(o.id, 0)
        seen[o.id] = n + 1
        if n:
            o.id = f"{o.id}-{n + 1}"
    iv = Intervention(id=iv_id, alertId=alert.id, title=alert.title, objective=objective, position=list(target) if target else None, options=options,
                      recommendedOptionId=options[0].id)
    alert.recommendedInterventionId = iv_id
    fx.interventions.append(iv)


def settle_interventions(ctx: Context, fx: Effects) -> None:
    """De-duplicate interventions raised more than once (several reports on one subject: the newest wins), rank the
    options, and derive committed status and progress from the committed option's ETA."""
    latest: dict[str, Intervention] = {}
    for iv in fx.interventions:
        latest[iv.id] = iv
    fx.interventions = list(latest.values())
    for iv in fx.interventions:
        ranked = sorted(iv.options, key=lambda o: (-o.successLikelihood, o.etaMin or 0, o.id))
        iv.recommendedOptionId = ranked[0].id
        committed = ctx.committed.get(iv.id)
        if not committed:
            continue
        opt = next((o for o in iv.options if o.id == committed["optionId"]), None)
        legacy = re.fullmatch(r"opt-(\d+)", committed["optionId"])
        if opt is None and legacy and 0 < int(legacy.group(1)) <= len(iv.options):
            opt = iv.options[int(legacy.group(1)) - 1]  # commits recorded before option ids named the unit
        iv.committedOptionId = opt.id if opt else committed["optionId"]
        iv.committedAt = committed["committedAt"]
        eta_s = (opt.etaMin or 1) * 60 if opt else 600
        progress = min(1.0, (ctx.t - committed["committedAtS"]) / max(eta_s, 1))
        iv.progress = round(progress, 3)
        iv.status = "completed" if progress >= 1 else "in_progress"


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
THREAT_RADIUS_M = 60_000  # an own site within this distance of a predicted path is "threatened"
CRITICAL_APPROACH_M = 25_000  # closest approach below this makes R01 critical


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
        referencing = inputs_for(ctx, e.id)
        threatened: list[tuple[SceneEntity, float, float]] = []
        if path:
            for tgt in own_targets:
                tp = pos(tgt)
                if not tp:
                    continue
                d, dt = predict.closest_approach(path, tp)
                if d < THREAT_RADIUS_M:
                    threatened.append((tgt, d, dt))
            threatened.sort(key=lambda x: x[1])
            path.threatenedEntityIds = [t[0].id for t in threatened[:5]]
            path.etaS = threatened[0][2] if threatened else None
            fx.predictions.append(path)
            fx.predictions.extend(predict.alternatives(e, path, [(t, pos(t)) for t in own_targets if pos(t)], ctx.t, history=ctx.history.get(e.id)))
        sev = "advisory" if downgraded else ("critical" if threatened and threatened[0][1] < CRITICAL_APPROACH_M else "warning")
        weight = SEVERITY_WEIGHT[sev] * (1.6 if e.domain == "air" else 1.2)
        fx.attention.append(Contribution(p[0], p[1], 45_000 if e.domain == "air" else 25_000, weight, f"Unknown track {e.label}", e.id, "R01"))
        if path:
            for k, (lng, lat, _t) in enumerate(path.points[1::6]):
                fx.attention.append(Contribution(lng, lat, 20_000, weight * 0.5 / (k + 1), f"Predicted path {e.label}", e.id, "R01"))
        for tgt, d, dt in threatened[:2]:
            tp = pos(tgt)
            fx.attention.append(Contribution(tp[0], tp[1], 15_000, weight * 0.8, f"{tgt.label} on predicted path of {e.label}", tgt.id, "R01"))
        kin = (f"{e.label} at {e.kinematics.speedMps:.0f} m/s heading {e.kinematics.headingDeg:.0f}°. " if e.kinematics else "")
        if threatened:
            tgt0, d0, dt0 = threatened[0]
            approach = f"Constant-velocity path passes {d0 / 1000:.0f} km from {tgt0.label} in {dt0 / 60:.0f} min"
            approach += (f" (< {CRITICAL_APPROACH_M / 1000:.0f} km: critical). " if d0 < CRITICAL_APPROACH_M else f" (inside {THREAT_RADIUS_M / 1000:.0f} km, outside {CRITICAL_APPROACH_M / 1000:.0f} km: warning). ")
            if len(threatened) > 1:
                approach += f"{len(threatened) - 1} more own site(s) within {THREAT_RADIUS_M / 1000:.0f} km of the path. "
        else:
            approach = f"No own site within {THREAT_RADIUS_M / 1000:.0f} km of the 30 min constant-velocity path. "
        down = next((i for i in referencing if i.channel == "intel_report" and "downgrade" in i.tags), None)
        detail = kin + approach + (f"J2 assesses the track as civil ({down.id}: {down.title}); posture unchanged, monitoring only." if down else "Identity unresolved.")
        a = alert(fx, ctx, f"al-R01-{e.id}", sev, f"{e.label}: {'monitor' if downgraded else 'identify and shadow'}", detail, "R01",
                  [i.id for i in referencing], [e.id] + [t[0].id for t in threatened[:3]], ["track.unknown", "picture.predictions"], p)
        fx.traces.append({"rule": "R01", "subject": e.id, "severity": sev, "threatened": [t[0].id for t in threatened[:3]], "downgraded": downgraded,
                          "closestApproachM": round(threatened[0][1]) if threatened else None, "thresholdsM": [CRITICAL_APPROACH_M, THREAT_RADIUS_M]})
        if downgraded:
            continue
        if e.domain == "air":
            caps, domains = ["air_patrol", "isr"], ["air"]
        elif e.domain == "land":
            caps, domains = ["patrol", "law_enforcement", "guard", "isr"], ["land", "air"]
        else:
            caps, domains = ["patrol", "surface", "sea_picture", "isr"], ["sea", "air"]
        opts = []
        for idx, (c, dist) in enumerate(candidates(ctx, caps, p, domains, limit=4), 1):
            steps = [f"Vector {c.label} toward predicted track of {e.label}", "Establish visual or electronic identification", "Report identity to joint picture", "Shadow until track leaves sector or is identified"]
            it = predict.intercept_time_s(pos(c), speed_of(c), path) if path else None  # type: ignore[arg-type]
            basis = (f"earliest intercept on the predicted path at {it[1][0]:.2f}, {it[1][1]:.2f} after {it[0] / 60:.0f} min" if it else
                     ("no intercept inside the 30 min prediction: ETA is the transit to the track's current position" if path else None))
            o = make_option(ctx, idx, c, dist, p, "Identify with", steps, ["R01"], deadline_min=(threatened[0][2] / 60 if threatened else 30), base_success=0.78 if c.domain == "air" else 0.62,
                            risk="medium" if sev == "critical" else "low", cost={"flightHours": round(dist / 1000 / 400, 2) if c.domain == "air" else 0, "crewHours": round(dist / speed_of(c) / 3600 * 2, 1)},
                            eta_override_min=it[0] / 60 if it else None, eta_basis=basis)
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
        air = e.domain == "air"
        fuel_adv, fuel_warn = (12, 8) if air else (25, 15)
        low_fuel = r.fuelPct is not None and r.fuelPct < fuel_adv
        low_score = r.score < 0.45
        if not (low_fuel or low_score):
            continue
        p = pos(e)
        sev = "warning" if (r.fuelPct is not None and r.fuelPct < fuel_warn) or r.score < 0.3 else "advisory"
        if p:
            fx.attention.append(Contribution(p[0], p[1], 12_000, SEVERITY_WEIGHT[sev] * 0.6, f"Low readiness {e.label}", e.id, "R02"))
        fired = []
        if low_fuel:
            fired.append(f"fuel {r.fuelPct:.0f} % < {fuel_adv} %" + (f" (< {fuel_warn} %: warning)" if r.fuelPct < fuel_warn else "") + (" aircraft threshold" if air else ""))
        if low_score:
            fired.append(f"readiness {r.score:.2f} < 0.45" + (" (< 0.30: warning)" if r.score < 0.3 else ""))
        drivers = [n for n in (r.faults or [])][:2] + ([f"comms {r.commsStatus}"] if r.commsStatus in ("degraded", "lost") else [])
        a = alert(fx, ctx, f"al-R02-{e.id}", sev, f"{e.label}: readiness {r.score:.2f}" + (f", fuel {r.fuelPct:.0f} %" if low_fuel else ""),
                  "Below the sustainment threshold: " + "; ".join(fired) + "." + (f" Contributing: {', '.join(drivers)}." if drivers else "") +
                  (" Resupply recommended." if low_fuel and not air else " Recovery to base recommended." if low_fuel else " Recovery or rotation recommended."), "R02",
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
        status = e.readiness.commsStatus if e.readiness else None
        lost = status in ("degraded", "lost")
        if not reports and not lost:
            continue
        p = pos(e)
        # Severity: the worse of the reported comms state (lost → critical, degraded → warning) and the reports' own severity (≥ warning).
        sev = "critical" if status == "lost" else "warning"
        for i in reports:
            if SEVERITY_RANK[i.severity] > SEVERITY_RANK[sev]:
                sev = i.severity
        if "comms_hub" in e.capabilities:
            fx.entity_status.setdefault(e.id, {"notes": []})["condition"] = "degraded"
        word = "lost" if status == "lost" else "degraded"
        if p:
            fx.attention.append(Contribution(p[0], p[1], 30_000 if "comms_hub" in e.capabilities else 8_000, SEVERITY_WEIGHT[sev], f"Communications {word} at {e.label}", e.id, "R04"))
        detail = (f"Comms status {status}. " if lost else "") + "; ".join(f"{i.title} ({i.id})" for i in reports[-3:]) + ("." if reports else "")
        if "comms_hub" in e.capabilities:
            detail += " Node is a comms hub: dependent circuits run degraded."
        a = alert(fx, ctx, f"al-R04-{e.id}", sev, f"{e.label}: communications {word}", detail.strip(), "R04",
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
            penalise(fx, dep.id, f"outage:{node.id}", -0.15, f"Depends on {node.label}: {i.title}")
        wx = weather_cover(ctx, p)[1] if p else None
        cause = f" {wx.title} ({wx.id}) is in force over the node: weather is a plausible cause." if wx else ""
        a = alert(fx, ctx, f"al-R05-{node.id}", i.severity, i.title, i.text + (f" Dependent sites (−0.15 readiness each, once per outage): {', '.join(d.label for d in dependents)}." if dependents else "") + cause, "R05",
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
        if not is_active(ctx, i):
            # A forecast warning: show it, but readiness and tasking penalties apply only once it is in force.
            alert(fx, ctx, f"al-R07-{i.id}", "info", i.title, i.text + f" Valid from {i.effectiveAt}; no readiness penalty until then.", "R07", [i.id], [], ["env.warnings"], p)
            continue
        fx.attention.append(Contribution(p[0], p[1], i.radiusM or 50_000, SEVERITY_WEIGHT[i.severity] * 0.5, i.title, i.id, "R07"))
        affected = [e.id for e in ctx.entities.values() if e.domain in ("air", "sea") and e.affiliation in ("own", "allied", "civil") and pos(e)
                    and geo.haversine_m(pos(e), p) <= (i.radiusM or 50_000)]  # type: ignore[arg-type]
        for eid in affected:
            penalise(fx, eid, "weather", -0.1, f"Weather: {i.title}")
        alert(fx, ctx, f"al-R07-{i.id}", "advisory", i.title, i.text + f" {len(affected)} own/allied/civil air and sea units inside the advisory area: −0.1 readiness "
              "(overlapping advisories do not stack).", "R07", [i.id], affected[:40], ["env.warnings"], p)


@rule("R08", "Intelligence assessments raise area priority")
def r08(ctx: Context, fx: Effects) -> None:
    for i in ctx.inputs:
        if i.channel != "intel_report" or SEVERITY_RANK[i.severity] < 1:
            continue
        for ref in i.entityRefs:
            if ref.startswith("area-"):
                raise_priority(fx, ref, 1.3, "intel_report", i)
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
        basis = [f"×{m:g} {src.replace('_', ' ')} ({iid}: {title})" for src, (m, iid, title) in sorted(fx.priority_basis.get(area["id"], {}).items())]
        fx.area_status[area["id"]] = {"status": status, "blockers": blockers, "priority": round(area["priority"] / mult, 2), "requires": area["requires"],
                                      "priorityBasis": basis}
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
                raise_priority(fx, ref, mult, i.channel, i)
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
    """An allied offer becomes an option on unknown-track interventions it can actually serve: a maritime patrol (mpa)
    offer only for surface tracks, and only for tracks inside the offer's declared area."""
    offers = [i for i in ctx.inputs if i.channel == "allied_liaison" and "offer" in i.tags]
    if not offers:
        return
    for iv in fx.interventions:
        if not iv.id.startswith("iv-R01-"):
            continue
        track = ctx.entities.get(iv.id[len("iv-R01-"):])
        if track is None:
            continue
        for o in offers:
            if "mpa" in o.tags and track.domain != "sea":
                continue  # a maritime patrol aircraft does not identify a fast air track
            where = ""
            if o.position and o.radiusM and pos(track):
                d = geo.haversine_m(pos(track), (o.position.longitudeDeg, o.position.latitudeDeg))  # type: ignore[arg-type]
                if d > o.radiusM:
                    continue
                where = f" Track is {d / 1000:.0f} km from the centre of the offered area (radius {o.radiusM / 1000:.0f} km)."
            iv.options.append(InterventionOption(id=f"opt-allied-{o.id}", title=f"Request allied {'maritime patrol' if 'mpa' in o.tags else 'support'} ({o.author})", rationale=o.text + where,
                                                 steps=["Submit tasking request via liaison", "Share track data", "Receive identification report"],
                                                 assignedEntityIds=[], etaMin=90, successLikelihood=0.66, riskLevel="low", resourceCost={"liaisonHours": 2}, ruleIds=["R15", "R01"],
                                                 outcomes=[OutcomeBand(label="best", probability=0.3, timeToEffectMin=70, description="Allied sortie identifies the track."),
                                                           OutcomeBand(label="expected", probability=0.36, timeToEffectMin=100, description="Identification during the sortie window."),
                                                           OutcomeBand(label="worst", probability=0.34, timeToEffectMin=180, description="Sortie not tasked in time.")]))


UAS_SITE_RADIUS_M = 6000  # a small UAS track this close to a site is activity *at* that site
UAS_REPORT_ASSOC_M = 25_000  # positioned drone reports without a site reference attach to the nearest own site within this


@rule("R16", "Small UAS activity near protected sites")
def r16(ctx: Context, fx: Effects) -> None:
    """Sensor-held small UAS tracks within 6 km of an own or civil site, plus drone reports about the site (by reference, or
    by position for police and public reports), raise a counter-UAS response. Severity rises with independent corroboration:
    >= 2 tracks, or tracks confirmed by a second channel -> critical; tracks or >= 2 channels -> warning; one report -> advisory."""
    sites = [e for e in ctx.entities.values() if e.kind in ("facility", "infrastructure") and e.affiliation in ("own", "civil")]
    groups: dict[str, list[tuple[str, float]]] = {}
    for e in ctx.entities.values():
        if e.affiliation != "unknown" or "small_uas" not in e.tags or not pos(e):
            continue
        near = min(((s, geo.haversine_m(pos(e), pos(s))) for s in sites if pos(s)), key=lambda x: x[1], default=None)  # type: ignore[arg-type]
        if near and near[1] < UAS_SITE_RADIUS_M:
            groups.setdefault(near[0].id, []).append((e.id, near[1]))
    reports: dict[str, list[InputReport]] = {}
    for i in ctx.inputs:
        if "drone" not in i.tags and "small_uas" not in i.tags:
            continue
        refs = [r for r in i.entityRefs if r in ctx.entities and ctx.entities[r].kind in ("facility", "infrastructure")]
        if not refs and i.position:
            ip = (i.position.longitudeDeg, i.position.latitudeDeg)
            near = min(((s, geo.haversine_m(ip, pos(s))) for s in sites if pos(s) and s.affiliation == "own"), key=lambda x: x[1], default=None)  # type: ignore[arg-type]
            if near and near[1] <= min(max(i.radiusM or 5_000, 5_000), UAS_REPORT_ASSOC_M):
                refs = [near[0].id]
        for ref in refs:
            reports.setdefault(ref, []).append(i)
    for sid in sorted(set(groups) | set(reports)):
        site = ctx.entities[sid]
        p = pos(site)
        tracks = sorted(groups.get(sid, []), key=lambda x: x[1])
        reps = reports.get(sid, [])
        # Independent channels: the sensor network (its tracks and its own detection reports count once), then each other channel.
        channels = sorted({"sensor" if r.channel == "sensor_detection" else r.channel for r in reps} | ({"sensor"} if tracks else set()))
        if len(tracks) >= 2 or (tracks and len(channels) >= 2):
            sev = "critical"
        elif tracks or len(channels) >= 2 or any(SEVERITY_RANK[r.severity] >= 2 for r in reps):
            sev = "warning"
        else:
            sev = "advisory"
        if p:
            fx.attention.append(Contribution(p[0], p[1], 8_000, SEVERITY_WEIGHT[sev] * 1.4, f"Small UAS activity at {site.label}", sid, "R16"))
        detail = (f"{len(tracks)} small UAS track(s) held {tracks[0][1] / 1000:.1f}-{tracks[-1][1] / 1000:.1f} km from {site.label} (inside {UAS_SITE_RADIUS_M / 1000:.0f} km). " if tracks else
                  f"No small UAS track held by sensors near {site.label}. ")
        if reps:
            detail += f"{len(reps)} report(s): " + "; ".join(f"{r.title} ({r.id})" for r in reps[-3:]) + ". "
        detail += f"Independent channels: {', '.join(c.replace('_', ' ') for c in channels)} ({len(channels)}). "
        if tracks and any("low_level" in ctx.entities[t].tags for t, _ in tracks):
            detail += "Persistent low-level orbit is consistent with reconnaissance of the site."
        a = alert(fx, ctx, f"al-R16-{sid}", sev, f"{site.label}: small UAS activity", detail.strip(), "R16", [r.id for r in reps], [sid] + [t for t, _ in tracks],
                  ["track.unknown", "sites.air" if "fighter" in site.capabilities or "transport" in site.capabilities else "sites.land"], p)
        fx.traces.append({"rule": "R16", "subject": sid, "tracks": [t for t, _ in tracks], "reports": [r.id for r in reps], "channels": channels, "severity": sev})
        if not p or sev == "advisory":
            continue  # a single uncorroborated report is shown, not answered with a counter-UAS tasking
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
    """Reports of GNSS jamming or spoofing degrade navigation for every own or civil air and sea platform inside the area.
    Overlapping reports of the same interference (a sensor report and a liaison report) cost the penalty once."""
    for i in ctx.inputs:
        if not ({"gnss", "spoofing"} & set(i.tags)) or not i.position:
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        r = i.radiusM or 100_000
        affected = [e for e in ctx.entities.values() if e.domain in ("air", "sea") and e.affiliation in ("own", "civil") and pos(e) and geo.haversine_m(pos(e), p) <= r]  # type: ignore[arg-type]
        for e in affected:
            penalise(fx, e.id, "gnss", -0.08, f"GNSS degraded: {i.title}")
        fx.attention.append(Contribution(p[0], p[1], r, SEVERITY_WEIGHT[i.severity] * 0.9, i.title, i.id, "R18"))
        alert(fx, ctx, f"al-R18-{i.id}", i.severity, i.title, i.text + f" {len(affected)} own or civil air/sea platforms within {r / 1000:.0f} km: −0.08 readiness "
              "(not stacked across overlapping reports); inertial or terrestrial navigation advised.",
              "R18", [i.id], [e.id for e in affected][:40], ["analysis.gnss", "air.fighter", "sea.combat"], p)


@rule("R19", "Pattern indicators on real public traffic")
def r19(ctx: Context, fx: Effects) -> None:
    """Real AIS loitering over cable corridors and real ADS-B orbit patterns become alerts with observation options.
    The wording stays neutral: these are indicators from public broadcasts, not assessments of the named traffic."""
    for i in ctx.inputs:
        if "real" not in i.tags or not i.position or not ({"cable", "orbit"} & set(i.tags)):
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        sea = "cable" in i.tags
        fx.attention.append(Contribution(p[0], p[1], 20_000 if sea else 40_000, SEVERITY_WEIGHT[i.severity] * (1.1 if sea else 0.8), i.title, i.id, "R19"))
        a = alert(fx, ctx, f"al-R19-{i.id}", i.severity, i.title, i.text, "R19", [i.id], [], ["live.sea", "infra.cables"] if sea else ["live.air", "live.air_mil"], p)
        if sea:
            opts = [make_option(ctx, k, c, d, p, "Observe with", [f"Task {c.label} to observe the vessel", "Hail on VHF 16; request intentions", "Document position against the corridor"],
                                ["R19"], 120, 0.7, "low", {"crewHours": round(d / speed_of(c) / 3600 * 2, 1)})
                    for k, (c, d) in enumerate(candidates(ctx, ["patrol", "sar", "surface"], p, ["sea", "air"], limit=2), 1)]
            intervention(ctx, fx, f"iv-R19-{i.id}", a, "Establish what the vessel is doing over the corridor", p, opts)


@rule("R20", "Emergency squawks on real air traffic")
def r20(ctx: Context, fx: Effects) -> None:
    """A real ADS-B emergency squawk (7500 unlawful interference, 7600 radio failure, 7700 general emergency) is an alert at
    the report's severity. A civil emergency (112) report within 50 km corroborates it; 7700 and 7500 get search-and-rescue
    options. Public broadcast data: the alert describes the squawk, not the aircraft's intent."""
    for i in ctx.inputs:
        if "squawk" not in i.tags or not i.position:
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        near_112 = [c for c in ctx.inputs if c.channel == "civil_emergency" and c.position
                    and geo.haversine_m(p, (c.position.longitudeDeg, c.position.latitudeDeg)) <= 50_000]
        fx.attention.append(Contribution(p[0], p[1], 40_000, SEVERITY_WEIGHT[i.severity], i.title, i.id, "R20"))
        detail = i.text + (f" Corroborated by civil emergency report(s): {', '.join(f'{c.title} ({c.id})' for c in near_112[:2])}." if near_112 else
                           " No civil emergency report within 50 km yet.")
        a = alert(fx, ctx, f"al-R20-{i.id}", i.severity, i.title, detail, "R20", [i.id] + [c.id for c in near_112[:3]], [], ["live.air"], p)
        if "7600" in i.title:
            continue  # radio failure: an air-traffic matter, no military tasking proposed
        opts = [make_option(ctx, k, c, d, p, "Stand by with", [f"Bring {c.label} to readiness for search and rescue", "Coordinate with the JRCC and air traffic control",
                                                                "Launch on request"], ["R20"], 60, 0.75, "low", {"flightHours": round(d / 1000 / 200, 2), "crewHours": 6})
                for k, (c, d) in enumerate(candidates(ctx, ["sar", "medevac"], p, ["air"], limit=2), 1)]
        intervention(ctx, fx, f"iv-R20-{i.id}", a, "Be ready to support search and rescue for the aircraft in distress", p, opts)


AIS_DARK_WINDOW = (900.0, 1500.0, 1800.0)  # scripted: the suspect tanker stops transmitting 900–1500 s into every 30 min
CABLE_LOITER_M = 3000  # within this of a cable or pipeline
LOITER_MPS = 1.6  # ~3 kn: below this a merchant is not on passage


@rule("R17", "Maritime anomaly over undersea infrastructure")
def r17(ctx: Context, fx: Effects) -> None:
    """Slow loitering within 3 km of an undersea cable or pipeline, plus AIS gaps, indicate a sabotage risk. An active
    weather advisory over the vessel is a benign explanation for slow speed (not for AIS gaps) and lowers the severity."""
    for e in ctx.entities.values():
        if e.domain != "sea" or e.affiliation not in ("unknown", "hostile_suspected") or not pos(e):
            continue
        p = pos(e)
        near = None
        for c in ctx.cables:
            d = _dist_to_line(p, c["coords"])  # type: ignore[arg-type]
            if d < CABLE_LOITER_M and (near is None or d < near[1]):
                near = (c, d)
        dark = "ais_gaps" in e.tags and AIS_DARK_WINDOW[0] <= ctx.t % AIS_DARK_WINDOW[2] < AIS_DARK_WINDOW[1]
        if dark:
            fx.entity_status.setdefault(e.id, {"notes": []}).setdefault("flags", []).append("dark")
        speed = (e.kinematics.speedMps or 0) if e.kinematics else 0.0
        slow = e.kinematics is not None and speed < LOITER_MPS
        if not near or not (slow or dark):
            continue  # transiting across a corridor at speed is normal traffic
        cable, d = near
        gaps = dark or "ais_gaps" in e.tags
        wx = weather_cover(ctx, p)[1]
        if gaps and slow:
            sev = "critical"
        elif slow and wx is not None and not gaps:
            sev = "advisory"
        else:
            sev = "warning"
        fx.attention.append(Contribution(p[0], p[1], 15_000, SEVERITY_WEIGHT[sev] * 1.3, f"{e.label} loitering over {cable['label']}", e.id, "R17"))
        fired = []
        if slow:
            fired.append(f"speed {speed * 1.944:.1f} kn < {LOITER_MPS * 1.944:.0f} kn")
        fired.append(f"{d:.0f} m from {cable['label']} (< {CABLE_LOITER_M / 1000:.0f} km)")
        if dark:
            fired.append("AIS transmissions currently absent (dark period)")
        elif "ais_gaps" in e.tags:
            fired.append("intermittent AIS gaps recorded")
        detail = f"{e.label}: " + "; ".join(fired) + ". "
        detail += ("Slow movement over the corridor with AIS gaps is consistent with anchor dragging or survey activity." if slow and gaps else
                   "Slow movement over the corridor is consistent with anchor dragging or survey activity." if slow else
                   "AIS dark over the corridor; speed not anomalous.")
        if wx is not None and slow:
            detail += f" {wx.title} ({wx.id}) is in force here: heavy weather can also explain the low speed{'' if not gaps else ', not the AIS gaps'}."
        a = alert(fx, ctx, f"al-R17-{e.id}", sev, f"{e.label}: loitering over undersea infrastructure", detail, "R17",
                  [i.id for i in inputs_for(ctx, e.id)] + ([wx.id] if wx is not None and slow else []), [e.id], ["track.unknown", "infra.cables"], p)
        fx.traces.append({"rule": "R17", "subject": e.id, "cable": cable["id"], "distanceM": round(d), "dark": dark, "slow": slow, "weather": wx.id if wx is not None else None})
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


def merge_alerts(alerts: list[Alert]) -> list[Alert]:
    """One alert per id. A rule fires once per input, so the same subject can raise its alert several times (two fault
    reports on one vehicle, two reports of one outage). The highest severity wins (the newest on a tie); input, entity and
    layer references are united so no source drops out of the trace, and the detail notes what else was reported."""
    merged: dict[str, Alert] = {}
    extra: dict[str, list[str]] = {}
    for a in alerts:
        cur = merged.get(a.id)
        if cur is None:
            merged[a.id] = a
            continue
        keep, other = (a, cur) if SEVERITY_RANK[a.severity] >= SEVERITY_RANK[cur.severity] else (cur, a)
        keep.inputIds = list(dict.fromkeys(cur.inputIds + a.inputIds))
        keep.entityIds = list(dict.fromkeys(cur.entityIds + a.entityIds))
        keep.layerIds = list(dict.fromkeys(cur.layerIds + a.layerIds))
        keep.recommendedInterventionId = keep.recommendedInterventionId or other.recommendedInterventionId
        notes = extra.setdefault(a.id, [])
        if other.detail != keep.detail and other.detail not in notes:
            notes.append(other.detail)
        merged[a.id] = keep
    for aid, notes in extra.items():
        a = merged[aid]
        if notes:
            more = " | ".join(n if len(n) <= 160 else n[:157] + "..." for n in notes[-2:])
            a.detail = f"{a.detail} Also reported ({len(notes)}): {more}"
    return sorted(merged.values(), key=lambda a: (-SEVERITY_RANK[a.severity], a.id))


ACK_ATTENTION_FACTOR = 0.5  # an acknowledged alert keeps half its attention weight: seen, not resolved


def discount_acknowledged(ctx: Context, fx: Effects) -> None:
    """Attention that belongs to an acknowledged alert (same rule, same subject) is halved, so unseen problems rank first."""
    if not ctx.acknowledged:
        return
    for c in fx.attention:
        if f"al-{c.rule_id}-{c.contributor}" in ctx.acknowledged:
            c.weight = round(c.weight * ACK_ATTENTION_FACTOR, 4)
            c.reason = f"{c.reason} (acknowledged)"


def evaluate(ctx: Context) -> Effects:
    fx = Effects()
    post = []
    for rule_id, _title, fn in RULES:
        if rule_id in POST_RULES:
            post.append(fn)
            continue
        fn(ctx, fx)
    settle_interventions(ctx, fx)
    for fn in post:  # mid-intervention monitoring sees every intervention, whichever rule raised it
        fn(ctx, fx)
    fx.alerts = merge_alerts(fx.alerts)
    discount_acknowledged(ctx, fx)
    from . import deception, fusion  # noqa: PLC0415  (assessment layers run after every rule has fired)
    fx.fusion = fusion.assess(ctx, fx)
    fx.deception = deception.assess(ctx, fx)
    return fx


def rule_catalogue() -> list[dict]:
    return [{"id": rid, "title": title} for rid, title, _ in RULES]
