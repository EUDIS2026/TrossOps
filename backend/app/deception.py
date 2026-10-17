"""Deception assessment: deterministic indicator scoring for decoys, false identities, feints and disinformation.

Each subject (unknown track or report) starts from a prior log-odds and every indicator that fires adds a declared
weight (positive = more likely deceptive, negative = less). probability = σ(prior + Σ wᵢ). The output lists every
indicator with its weight and the evidence it used, plus the collection that would most change the assessment.
No learned model: an analyst can recompute any number by hand.

Summing log-odds is only right for *independent* evidence. Indicators that read the same observation (for example
"slow over a cable" and "behaviour contradicts declared tanker", both driven by low speed) share an evidence `group`:
the strongest counts in full and every further one in the group at DEPENDENCE_DISCOUNT of its weight. Each indicator
carries `rawWeight` (declared) and `weight` (what was added), so Σ weight + prior = logOdds exactly.

Bands: < 0.25 unlikely · 0.25–0.5 possible · 0.5–0.75 likely · ≥ 0.75 very likely.
"""
from __future__ import annotations

import math
from datetime import timedelta

from . import geo

PRIOR_TRACK = -1.6  # ≈ 17 %
PRIOR_REPORT = -2.2  # ≈ 10 %
DEPENDENCE_DISCOUNT = 0.35  # weight kept by a second indicator reading the same evidence
CORROBORATION_WINDOW = timedelta(hours=2)  # a detection only corroborates a claim made within this time of it
LOITER_MPS = 1.6


def band(p: float) -> str:
    return "very likely" if p >= 0.75 else "likely" if p >= 0.5 else "possible" if p >= 0.25 else "unlikely"


def _ind(iid: str, label: str, weight: float, evidence: str, group: str | None = None) -> dict:
    return {"id": iid, "label": label, "weight": weight, "rawWeight": weight, "evidence": evidence, "group": group or iid}


def combine(indicators: list[dict]) -> list[dict]:
    """Apply the dependence discount within each evidence group (strongest first, then declaration order)."""
    by_group: dict[str, list[dict]] = {}
    for i in indicators:
        by_group.setdefault(i["group"], []).append(i)
    for members in by_group.values():
        ranked = sorted(members, key=lambda i: -abs(i["rawWeight"]))
        for k, i in enumerate(ranked):
            i["weight"] = round(i["rawWeight"] * (1.0 if k == 0 else DEPENDENCE_DISCOUNT), 3)
            if k:
                i["evidence"] = f"{i['evidence']} (shares evidence with {ranked[0]['id']}: ×{DEPENDENCE_DISCOUNT})"
    return indicators


def _result(subject: str, kind: str, hypothesis: str, prior: float, indicators: list[dict], collect: list[str]) -> dict:
    combine(indicators)
    logit = prior + sum(i["weight"] for i in indicators)
    p = 1 / (1 + math.exp(-logit))
    return {"subject": subject, "kind": kind, "hypothesis": hypothesis, "prior": round(1 / (1 + math.exp(-prior)), 2), "logOdds": round(logit, 2),
            "probability": round(p, 2), "band": band(p), "indicators": indicators, "wouldChange": collect,
            "method": f"σ(prior log-odds + Σ indicator weights); indicators sharing evidence count ×{DEPENDENCE_DISCOUNT} after the strongest; "
                      "weights are declared constants in deception.py"}


def _parse(s):
    from .rules import parse_iso  # noqa: PLC0415  (rules imports this module lazily; avoid an import cycle)
    return parse_iso(s)


def _within_window(a, b) -> bool:
    ta, tb = _parse(a), _parse(b)
    return ta is None or tb is None or abs(ta - tb) <= CORROBORATION_WINDOW


def _covered(ctx, p) -> dict | None:
    """The sensor coverage model area containing p, if any."""
    for a in ctx.areas:
        if a.get("kind") == "coverage_model" and geo.point_in_ring(p, [tuple(q) for q in a["ring"]]):
            return a
    return None


def _weather_over(ctx, p):
    from .rules import weather_cover  # noqa: PLC0415
    return weather_cover(ctx, p)[1]


def assess(ctx, fx) -> dict[str, dict]:
    out: dict[str, dict] = {}
    sensor_reports = [i for i in ctx.inputs if i.channel == "sensor_detection"]
    uas_near_site: dict[str, list[str]] = {}
    for t in fx.traces:
        if t.get("rule") == "R16":
            for tid in t.get("tracks", []):
                uas_near_site[tid] = t.get("tracks", [])
    for e in ctx.entities.values():
        if e.affiliation != "unknown":
            continue
        tags = set(e.tags)
        ind: list[dict] = []
        refs = [i for i in ctx.inputs if e.id in i.entityRefs]
        if e.domain == "air" and "small_uas" not in tags:
            hyp = "Decoy or emulated track"
            if "constant_kinematics" in tags:
                ind.append(_ind("D1", "Machine-perfect kinematics", 1.3, "speed and heading constant to sensor precision over the whole track"))
            if "no_emitter" in tags:
                ind.append(_ind("D2", "No emissions detected", 0.9, "radar-only track; no ESM intercept, no transponder"))
            sensors = {i.author for i in refs if i.channel == "sensor_detection"}
            second = [i for i in refs if i.channel in ("intel_report", "allied_liaison")]
            if not second and len(sensors) <= 1:
                ind.append(_ind("D3", "Single-sensor custody", 0.4, f"held only by {next(iter(sensors)) if sensors else 'the radar network'}; no second sensor, intelligence or allied source"))
            down = next((i for i in refs if "downgrade" in i.tags), None)
            if down is not None:
                ind.append(_ind("N1", "Assessed civil by J2", -1.6, f"{down.id}: {down.title}"))
            pred = next((p for p in fx.predictions if p.entityId == e.id and p.hypothesis == "constant velocity"), None)
            if pred and not pred.threatenedEntityIds:
                ind.append(_ind("D4", "Probing geometry", 0.5, "constant-velocity path stays > 60 km from every own site (sensor-edge probing)"))
            out[e.id] = _result(e.id, "track", hyp, PRIOR_TRACK, ind, ["EO/IR identification by an interceptor", "ESM intercept of the track", "second-radar correlation"])
        elif e.domain == "sea":
            hyp = "False AIS identity / covert activity"
            speed = (e.kinematics.speedMps or 0) if e.kinematics else 0.0
            slow = e.kinematics is not None and speed < LOITER_MPS
            declared = next((t.split(":", 1)[1] for t in tags if t.startswith("ais_declared:")), None)
            if declared in ("tanker", "cargo", "container", "bulk") and (slow or "loiter_over_cable" in tags):
                what = f"{speed * 1.944:.1f} kn" if slow else "repeated loiter (reported)"
                ind.append(_ind("D5", "Behaviour contradicts declared identity", 1.4, f"AIS declares a {declared} on passage, observed {what}, not on a trade route", "slow_over_cable"))
            if "ais_gaps" in tags:
                gap_reps = [i.id for i in refs if "ais_gap" in i.tags or "ais_gaps" in i.tags]
                dark_now = "dark" in (fx.entity_status.get(e.id, {}).get("flags") or [])
                ind.append(_ind("D6", "AIS dark periods", 1.2, "repeated AIS transmission gaps" + (" (dark now)" if dark_now else "") + (f"; reported in {', '.join(gap_reps)}" if gap_reps else "")))
            r17 = next((t for t in fx.traces if t.get("rule") == "R17" and t.get("subject") == e.id), None)
            if r17 is not None:
                ind.append(_ind("D7", "Loiter over undersea infrastructure", 1.1, f"R17 fired: {r17['distanceM']} m from {r17['cable']}" + (" at low speed" if r17.get("slow") else ""), "slow_over_cable"))
            if "flag_of_convenience" in tags:
                src = next((i.id for i in refs if "flag_of_convenience" in i.tags), None)
                ind.append(_ind("D8", "Flag of convenience", 0.4, "registry and ownership opaque" + (f" ({src})" if src else " (liaison report)")))
            wx = _weather_over(ctx, (e.position.longitudeDeg, e.position.latitudeDeg)) if e.position else None
            if slow and wx is not None:
                ind.append(_ind("N5", "Weather explains low speed", -0.6, f"{wx.title} ({wx.id}) in force here; heavy weather slows merchants (does not explain AIS gaps)"))
            if not ind and e.kinematics and speed > 3:
                ind.append(_ind("N2", "Transit behaviour", -0.6, f"steady {speed * 1.944:.0f} kn consistent with a merchant on passage"))
            out[e.id] = _result(e.id, "track", hyp, PRIOR_TRACK, ind, ["visual identification (patrol ship or helicopter)", "AIS history from a second provider", "port-state and ownership check"])
        elif "small_uas" in tags:
            mates = [t for t in uas_near_site.get(e.id, []) if t != e.id]
            if mates:
                ind.append(_ind("D9", "Coordinated orbit pattern", 0.3, f"{len(mates) + 1} small UAS tracks orbit the same site ({', '.join(mates[:3])} with this one)"))
            out[e.id] = _result(e.id, "track", "Diversion (feint) drawing attention from elsewhere", PRIOR_TRACK, ind, ["check for simultaneous activity at other sites", "RF direction finding of control links"])
    # Reports: disinformation and single-source claims
    for i in ctx.inputs:
        if i.channel not in ("public_news", "field_report", "police_event") or not i.position:
            continue
        if i.channel == "police_event" and "drone" not in i.tags:
            continue
        p = (i.position.longitudeDeg, i.position.latitudeDeg)
        radius = max(i.radiusM or 10_000, 10_000)
        ind = []

        def near(s, extra=0.0) -> bool:
            return bool(s.position) and s.id != i.id and _within_window(s.effectiveAt, i.effectiveAt) and \
                geo.haversine_m(p, (s.position.longitudeDeg, s.position.latitudeDeg)) < radius + extra

        corroborating = [s for s in sensor_reports if near(s, s.radiusM or 0)]
        official = [s for s in ctx.inputs if s.channel in ("civil_emergency", "police_event", "infrastructure_status", "crisis_info") and s.channel != i.channel and near(s, s.radiusM or 0)]
        own_near = [e for e in ctx.entities.values() if e.affiliation == "own" and e.position and e.kind not in ("facility", "infrastructure")
                    and geo.haversine_m(p, (e.position.longitudeDeg, e.position.latitudeDeg)) < radius]
        hostile_claim = any(t in i.tags for t in ("hostile_claim", "landing", "column"))
        cover = _covered(ctx, p)
        if i.channel == "public_news" and not corroborating:
            ind.append(_ind("D10", "No sensor corroboration", 1.0, f"no sensor detection within {radius / 1000:.0f} km and {CORROBORATION_WINDOW.total_seconds() / 3600:.0f} h", "no_sensor"))
        if hostile_claim and own_near:
            ind.append(_ind("D11", "Explained by own activity", 0.6, f"{len(own_near)} own platforms within {radius / 1000:.0f} km (likely misidentified own movement, also an OPSEC finding)"))
        elif hostile_claim and not own_near and not corroborating and cover is not None:
            ind.append(_ind("D12", "Claim contradicted by coverage", 1.1, f"inside {cover['label']} with nothing detected", "no_sensor"))
        if "social_media" in i.tags or "uncorroborated" in i.tags:
            ind.append(_ind("D13", "Low-reliability source", 0.7, "Admiralty E5: unverified social media origin"))
        if "amplified" in i.tags:
            ind.append(_ind("D14", "Coordinated amplification", 0.8, "identical wording across many new accounts within minutes"))
        if corroborating:
            ind.append(_ind("N3", "Sensor corroboration", -1.5, ", ".join(s.id for s in corroborating[:3])))
        if official:
            ind.append(_ind("N4", "Official channel corroboration", -1.2, ", ".join(f"{s.channel.replace('_', ' ')} {s.id}" for s in official[:3])))
        if not ind:
            continue
        out[i.id] = _result(i.id, "report", "Disinformation or misidentification", PRIOR_REPORT, ind, ["task ISR to the reported location", "contact the original author", "cross-check own unit positions"])
    return out
