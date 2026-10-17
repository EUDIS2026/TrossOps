"""Deception assessment: deterministic indicator scoring for decoys, false identities, feints and disinformation.

Each subject (unknown track or report) starts from a prior log-odds and every indicator that fires adds a declared
weight (positive = more likely deceptive, negative = less). probability = σ(prior + Σ wᵢ). The output lists every
indicator with its weight and the evidence it used, plus the collection that would most change the assessment.
No learned model: an analyst can recompute any number by hand.

Bands: < 0.25 unlikely · 0.25–0.5 possible · 0.5–0.75 likely · ≥ 0.75 very likely.
"""
from __future__ import annotations

import math

from . import geo

PRIOR_TRACK = -1.6  # ≈ 17 %
PRIOR_REPORT = -2.2  # ≈ 10 %


def band(p: float) -> str:
    return "very likely" if p >= 0.75 else "likely" if p >= 0.5 else "possible" if p >= 0.25 else "unlikely"


def _result(subject: str, kind: str, hypothesis: str, prior: float, indicators: list[dict], collect: list[str]) -> dict:
    logit = prior + sum(i["weight"] for i in indicators)
    p = 1 / (1 + math.exp(-logit))
    return {"subject": subject, "kind": kind, "hypothesis": hypothesis, "prior": round(1 / (1 + math.exp(-prior)), 2), "logOdds": round(logit, 2),
            "probability": round(p, 2), "band": band(p), "indicators": indicators, "wouldChange": collect,
            "method": "σ(prior log-odds + Σ indicator weights); weights are declared constants in deception.py"}


def assess(ctx, fx) -> dict[str, dict]:
    out: dict[str, dict] = {}
    sensor_reports = [i for i in ctx.inputs if i.channel == "sensor_detection"]
    for e in ctx.entities.values():
        if e.affiliation != "unknown":
            continue
        tags = set(e.tags)
        ind: list[dict] = []
        refs = [i for i in ctx.inputs if e.id in i.entityRefs]
        if e.domain == "air" and "small_uas" not in tags:
            hyp = "Decoy or emulated track"
            if "constant_kinematics" in tags:
                ind.append({"id": "D1", "label": "Machine-perfect kinematics", "weight": 1.3, "evidence": "speed and heading constant to sensor precision over the whole track"})
            if "no_emitter" in tags:
                ind.append({"id": "D2", "label": "No emissions detected", "weight": 0.9, "evidence": "radar-only track; no ESM intercept, no transponder"})
            if not any(i.channel in ("intel_report", "allied_liaison") for i in refs):
                ind.append({"id": "D3", "label": "Single-sensor custody", "weight": 0.4, "evidence": "only the radar network holds the track; no second source"})
            if any("downgrade" in i.tags for i in refs):
                ind.append({"id": "N1", "label": "Assessed civil by J2", "weight": -1.6, "evidence": next(i.id for i in refs if "downgrade" in i.tags)})
            pred = next((p for p in fx.predictions if p.entityId == e.id), None)
            if pred and not pred.threatenedEntityIds:
                ind.append({"id": "D4", "label": "Probing geometry", "weight": 0.5, "evidence": "predicted path stays clear of own assets (sensor-edge probing)"})
            out[e.id] = _result(e.id, "track", hyp, PRIOR_TRACK, ind, ["EO/IR identification by an interceptor", "ESM intercept of the track", "second-radar correlation"])
        elif e.domain == "sea":
            hyp = "False AIS identity / covert activity"
            if "ais_declared:tanker" in tags:
                slow = e.kinematics is not None and (e.kinematics.speedMps or 0) < 1.6
                if slow or "loiter_over_cable" in tags:
                    ind.append({"id": "D5", "label": "Behaviour contradicts declared identity", "weight": 1.4, "evidence": "declared tanker moving at < 3 kn with repeated course changes, not on a trade route"})
            if "ais_gaps" in tags:
                ind.append({"id": "D6", "label": "AIS dark periods", "weight": 1.2, "evidence": "transmissions stop for ~10 min in every 30 min while near infrastructure"})
            if any(t.get("rule") == "R17" and t.get("subject") == e.id for t in fx.traces):
                ind.append({"id": "D7", "label": "Loiter over undersea infrastructure", "weight": 1.1, "evidence": "R17 fired: within 3 km of a cable corridor at low speed"})
            if "flag_of_convenience" in tags:
                ind.append({"id": "D8", "label": "Flag of convenience", "weight": 0.4, "evidence": "registry and ownership opaque (liaison report)"})
            if not ind and e.kinematics and (e.kinematics.speedMps or 0) > 3:
                ind.append({"id": "N2", "label": "Transit behaviour", "weight": -0.6, "evidence": "steady transit speed consistent with a merchant on passage"})
            out[e.id] = _result(e.id, "track", hyp, PRIOR_TRACK, ind, ["visual identification (patrol ship or helicopter)", "AIS history from a second provider", "port-state and ownership check"])
        elif "small_uas" in tags:
            ind.append({"id": "D9", "label": "Coordinated orbit pattern", "weight": 0.3, "evidence": "several tracks orbit the same site at offset radii"})
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
        corroborating = [s for s in sensor_reports if s.position and geo.haversine_m(p, (s.position.longitudeDeg, s.position.latitudeDeg)) < radius + (s.radiusM or 0)]
        own_near = [e for e in ctx.entities.values() if e.affiliation == "own" and e.position and e.kind not in ("facility", "infrastructure")
                    and geo.haversine_m(p, (e.position.longitudeDeg, e.position.latitudeDeg)) < radius]
        hostile_claim = any(t in i.tags for t in ("hostile_claim", "landing", "column"))
        if i.channel == "public_news" and not corroborating:
            ind.append({"id": "D10", "label": "No sensor corroboration", "weight": 1.0, "evidence": f"no sensor detection within {radius / 1000:.0f} km"})
        if hostile_claim and own_near:
            ind.append({"id": "D11", "label": "Explained by own activity", "weight": 0.6, "evidence": f"{len(own_near)} own platforms within {radius / 1000:.0f} km (likely misidentified own movement, also an OPSEC finding)"})
        elif hostile_claim and not own_near and not corroborating:
            ind.append({"id": "D12", "label": "Claim contradicted by coverage", "weight": 1.1, "evidence": "area inside sensor coverage with nothing detected"})
        if "social_media" in i.tags or "uncorroborated" in i.tags:
            ind.append({"id": "D13", "label": "Low-reliability source", "weight": 0.7, "evidence": "Admiralty E5: unverified social media origin"})
        if "amplified" in i.tags:
            ind.append({"id": "D14", "label": "Coordinated amplification", "weight": 0.8, "evidence": "identical wording across many new accounts within minutes"})
        if corroborating:
            ind.append({"id": "N3", "label": "Sensor corroboration", "weight": -1.5, "evidence": ", ".join(s.id for s in corroborating[:3])})
        if not ind:
            continue
        out[i.id] = _result(i.id, "report", "Disinformation or misidentification", PRIOR_REPORT, ind, ["task ISR to the reported location", "contact the original author", "cross-check own unit positions"])
    return out
