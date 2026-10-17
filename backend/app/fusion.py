"""Source fusion: why the picture believes what it shows about each subject.

For every entity or track that any input refers to (and every unknown track), this builds a ledger of the
contributing sources with an Admiralty grading (NATO AJP-2: source reliability A–F, information credibility 1–6),
how many *independent* channels corroborate it, a combined confidence, and — for unknown tracks — identity
hypotheses with the indicators behind each. Deterministic and explainable: every number names its inputs.

Confidence of one source = reliability weight × credibility weight; combined confidence over independent channels
= 1 − Π(1 − cᵢ), taking the best source per channel (repeats from one channel are not independent corroboration).
"""
from __future__ import annotations

from .inputs import CHANNEL_META

# Default Admiralty grading per channel (reliability of the source type, credibility of a typical report).
GRADING: dict[str, tuple[str, int]] = {
    "sensor_detection": ("B", 2), "intel_report": ("B", 3), "field_report": ("C", 3), "unit_sitrep": ("B", 2), "logistics_report": ("B", 2),
    "maintenance_log": ("A", 2), "civil_emergency": ("A", 2), "weather_advisory": ("A", 1), "infrastructure_status": ("B", 2), "public_news": ("E", 4),
    "cyber_alert": ("B", 2), "command_directive": ("A", 1), "allied_liaison": ("B", 2), "head_of_state_directive": ("A", 1),
    "police_event": ("B", 3), "crisis_info": ("A", 2), "adsb": ("A", 2), "ais": ("C", 3),
}
RELIABILITY = {"A": 0.95, "B": 0.8, "C": 0.6, "D": 0.4, "E": 0.25, "F": 0.5}
CREDIBILITY = {1: 0.95, 2: 0.8, 3: 0.6, 4: 0.4, 5: 0.2, 6: 0.5}
RELIABILITY_LABEL = {"A": "completely reliable", "B": "usually reliable", "C": "fairly reliable", "D": "not usually reliable", "E": "unreliable", "F": "cannot be judged"}
CREDIBILITY_LABEL = {1: "confirmed", 2: "probably true", 3: "possibly true", 4: "doubtful", 5: "improbable", 6: "cannot be judged"}


def grade(channel: str, tags: list[str]) -> tuple[str, int]:
    rel, cred = GRADING.get(channel, ("F", 6))
    if "downgrade" in tags or "assessment" in tags:
        cred = min(cred, 2)
    if "uncorroborated" in tags or "social_media" in tags:
        rel, cred = "E", 5
    return rel, cred


def assess(ctx, fx) -> dict[str, dict]:
    subjects: dict[str, list] = {}
    for i in ctx.inputs:
        for ref in i.entityRefs:
            subjects.setdefault(ref, []).append(i)
    for e in ctx.entities.values():
        if e.affiliation == "unknown":
            subjects.setdefault(e.id, [])
    out: dict[str, dict] = {}
    for sid, reports in subjects.items():
        e = ctx.entities.get(sid)
        sources = []
        best_by_channel: dict[str, float] = {}
        for r in reports[-25:]:
            rel, cred = grade(r.channel, r.tags)
            conf = round(RELIABILITY[rel] * CREDIBILITY[cred], 2)
            best_by_channel[r.channel] = max(best_by_channel.get(r.channel, 0.0), conf)
            sources.append({"inputId": r.id, "channel": r.channel, "channelLabel": CHANNEL_META.get(r.channel, {}).get("label", r.channel), "author": r.author,
                            "at": r.effectiveAt, "grading": f"{rel}{cred}", "reliability": RELIABILITY_LABEL[rel], "credibility": CREDIBILITY_LABEL[cred],
                            "confidence": conf, "title": r.title, "sourceKind": r.sourceKind})
        if e is not None and e.affiliation == "unknown":
            # The track itself is held by the sensor network; that is a source even without a written report.
            best_by_channel.setdefault("sensor_track", 0.64)
            sources.insert(0, {"inputId": None, "channel": "sensor_track", "channelLabel": "Sensor track (fused radar picture)", "author": "Air/sea surveillance",
                               "at": ctx.now_iso, "grading": "B2", "reliability": RELIABILITY_LABEL["B"], "credibility": CREDIBILITY_LABEL[2], "confidence": 0.64,
                               "title": "Track held", "sourceKind": "observed"})
        combined = 1.0
        for c in best_by_channel.values():
            combined *= (1 - c)
        item = {"subject": sid, "sources": sources, "channels": sorted(best_by_channel), "corroboration": len(best_by_channel),
                "confidence": round(1 - combined, 2), "method": "1 − Π(1 − best confidence per independent channel); Admiralty grading per channel"}
        if e is not None and e.affiliation == "unknown":
            item["identity"] = _identity(e, reports, fx)
        out[sid] = item
    return out


def _identity(e, reports, fx) -> list[dict]:
    """Identity hypotheses for an unknown track (scores normalised to 1), each with the indicators behind it."""
    tags = set(e.tags)
    text = " ".join((r.title + " " + r.text).lower() for r in reports)
    hyp: dict[str, tuple[float, list[str]]] = {}

    def add(name: str, w: float, why: str) -> None:
        cur = hyp.get(name, (0.0, []))
        hyp[name] = (cur[0] + w, cur[1] + [why])

    if e.domain == "air":
        add("Civil aircraft without transponder", 1.0, "prior: most unidentified air tracks are civil")
        add("Military reconnaissance aircraft", 0.8, "prior: activity pattern near the sensor network")
        if "transport" in text or "downgrade" in text:
            add("Civil aircraft without transponder", 2.0, "J2 assessment: behaviour consistent with civil transport")
        if "inbound" in text or "no transponder" in text:
            add("Military reconnaissance aircraft", 0.7, "sensor report: inbound, no transponder")
        if "no_emitter" in tags or "constant_kinematics" in tags:
            add("Decoy / drone emulator", 1.6, "no emissions and machine-perfect speed and heading")
        if "small_uas" in tags:
            hyp.clear()
            add("Small UAS (reconnaissance)", 2.0, "low, slow orbit around a protected site")
            add("Hobby drone", 0.6, "prior: recreational drones are common near towns")
    else:
        add("Merchant vessel with AIS off", 1.0, "prior: most unidentified surface contacts are merchants")
        add("State-directed vessel (ISR or sabotage)", 0.6, "prior: elevated maritime activity assessment")
        if "ais_declared:tanker" in tags:
            add("Merchant vessel with AIS off", 0.4, "declares itself a tanker on AIS")
        if "loiter_over_cable" in tags or any(t.get("rule") == "R17" and t.get("subject") == e.id for t in fx.traces):
            add("State-directed vessel (ISR or sabotage)", 1.8, "slow loiter over an undersea cable corridor")
        if "ais_gaps" in tags:
            add("State-directed vessel (ISR or sabotage)", 0.9, "repeated AIS dark periods")
        if "flag_of_convenience" in tags:
            add("State-directed vessel (ISR or sabotage)", 0.5, "flag of convenience reported by liaison")
    total = sum(v[0] for v in hyp.values()) or 1.0
    return sorted(({"hypothesis": k, "probability": round(v[0] / total, 2), "indicators": v[1]} for k, v in hyp.items()), key=lambda h: -h["probability"])
