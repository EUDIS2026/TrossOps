"""Input channels: a scripted, deterministic live timeline of synthetic reports plus rule-based text parsing
for operator-submitted reports. Fourteen channels span a soldier's field report to a head-of-state directive."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import Channel, GeoPosition, InputIn, InputReport, Severity
from .orbat import P, SITES

CHANNEL_META: dict[str, dict] = {
    "field_report": {"label": "Field report", "level": "soldier", "weight": 0.6},
    "unit_sitrep": {"label": "Unit SITREP", "level": "company", "weight": 0.8},
    "logistics_report": {"label": "Logistics report", "level": "battalion", "weight": 0.7},
    "maintenance_log": {"label": "Maintenance log", "level": "operator", "weight": 0.6},
    "sensor_detection": {"label": "Sensor detection", "level": "sensor", "weight": 1.0},
    "intel_report": {"label": "Intelligence report", "level": "joint", "weight": 0.9},
    "civil_emergency": {"label": "Civil emergency (112)", "level": "civil_authority", "weight": 0.8},
    "weather_advisory": {"label": "Weather advisory (SMHI)", "level": "civil_authority", "weight": 0.5},
    "infrastructure_status": {"label": "Infrastructure status", "level": "operator", "weight": 0.9},
    "public_news": {"label": "Public news", "level": "media", "weight": 0.3},
    "cyber_alert": {"label": "Cyber alert (CERT)", "level": "joint", "weight": 0.8},
    "command_directive": {"label": "Command directive", "level": "regional", "weight": 1.0},
    "allied_liaison": {"label": "Allied liaison", "level": "allied", "weight": 0.7},
    "head_of_state_directive": {"label": "Head-of-state directive", "level": "head_of_state", "weight": 1.0},
    "police_event": {"label": "Police event (public)", "level": "civil_authority", "weight": 0.6},
    "crisis_info": {"label": "Crisis information (public)", "level": "civil_authority", "weight": 0.7},
}

SEVERITY_RANK: dict[str, int] = {"info": 0, "advisory": 1, "warning": 2, "critical": 3}


@dataclass
class Scripted:
    at_s: float
    channel: Channel
    author_level: str
    author: str
    severity: Severity
    title: str
    text: str
    position: tuple[float, float] | None = None
    radius_m: float | None = None
    entity_refs: tuple[str, ...] = ()
    region: str | None = None
    tags: tuple[str, ...] = ()


def _site(id_: str) -> tuple[float, float] | None:
    for s in SITES:
        if s.id == id_:
            return None  # resolved by world at runtime
    return None


SCRIPT: list[Scripted] = [
    Scripted(15, "sensor_detection", "sensor", "Sensor Site Gotland", "warning", "Unknown air track A1 detected",
             "Radar fusion: unidentified air track 9000 m MSL, 190 m/s, heading 293, no transponder, inbound toward Gotland sector from the south-east.",
             (21.9, 57.2), 20_000, ("unk-air-01", "radar-gotland", "area-gotland"), "09", ("air", "unknown_track", "inbound")),
    Scripted(40, "field_report", "soldier", "Pvt. L. Ekström, patrol 3", "advisory", "Small drone observed over Comms Node Mitt",
             "Observed one small quadcopter circling the perimeter fence at approx 80 m AGL for four minutes before leaving north-east. No markings.",
             None, 800, ("comms-mitt",), "04", ("drone", "perimeter", "isr_suspected")),
    Scripted(70, "maintenance_log", "operator", "Workshop Norr", "warning", "Hydraulic fault on tank N1T-03",
             "Tank company N1T reports hydraulic pressure loss on vehicle 03 during the road march toward Haparanda. Vehicle mobile at reduced speed, turret traverse limited.",
             None, None, ("coy-n1t-03",), "25", ("fault", "hydraulics", "mobility_reduced")),
    Scripted(100, "infrastructure_status", "operator", "Grid operator (public)", "warning", "Grid Node Skåne partial outage",
             "Transmission disturbance at Grid Node Skåne: 40 % load shed in the southern region. Restoration estimate 3 h. Backup generation at dependent sites requested.",
             None, 60_000, ("power-syd", "garrison-syd", "airbase-syd"), "12", ("power", "outage")),
    Scripted(130, "civil_emergency", "civil_authority", "SOS Alarm Västernorrland", "critical", "Bus collision E4 south of Sundsvall",
             "Multiple-vehicle collision on E4 at Njurunda. 12 injured, 3 critical. Regional ambulances committed; request military medevac helicopter and medical team support.",
             (17.30, 62.25), 3_000, (), "22", ("civil", "casualties", "medevac")),
    Scripted(160, "weather_advisory", "civil_authority", "SMHI (public)", "advisory", "Wind warning class 2, Gotland sea area",
             "Gale force winds 20-24 m/s expected from 18:00. Sea state 6. Helicopter and small-craft operations degraded in the Gotland sea area.",
             (19.0, 57.4), 120_000, ("hs-1-02", "fl-e-pat1", "area-gotland"), "09", ("weather", "wind", "air_ops_degraded")),
    Scripted(190, "intel_report", "joint", "J2 Joint Intelligence", "warning", "Elevated maritime activity south-east Baltic",
             "Assessment: pattern of unidentified surface contacts near the Gotland sea lanes over 48 h. Likelihood of ISR activity against sensor sites: medium-high.",
             (19.5, 57.0), 150_000, ("area-gotland", "radar-gotland", "unk-sea-01"), "09", ("isr", "maritime", "pattern")),
    Scripted(220, "cyber_alert", "joint", "CERT-FM", "warning", "Anomalous traffic at Comms Node Syd",
             "Outbound beaconing detected from a management VLAN at Comms Node Syd. Containment in progress; node capacity reduced to 60 %.",
             None, None, ("comms-syd",), "06", ("cyber", "comms", "containment")),
    Scripted(250, "unit_sitrep", "company", "Battlegroup Gotland S3", "advisory", "Gotland readiness 0.6, fuel constraint",
             "Fuel stock at Garrison Gotland 38 %. Mech company G1 holding positions. Request resupply via support ship or ferry slot before 06:00.",
             None, None, ("garrison-gotland", "coy-g1-03", "fl-s-sup1"), "09", ("fuel", "resupply")),
    Scripted(280, "public_news", "media", "Regional newspaper (open source)", "info", "Convoy movements reported on E4",
             "Local media reports military convoy movements on E4 between Umeå and Luleå. Social media photos show fuel trucks.",
             (20.6, 64.3), 40_000, ("sup-n-01",), "24", ("opsec", "media")),
    Scripted(310, "command_directive", "regional", "Joint Operations Commander", "warning", "Priority: Gotland sector",
             "Directive 14: Gotland sector is the priority effort until further notice. Gotland AD company to reposition; airborne surveillance east of Gotland continuous.",
             None, None, ("area-gotland", "coy-g-ad-l1", "aew-01"), "09", ("priority", "gotland")),
    Scripted(340, "allied_liaison", "allied", "Allied maritime liaison officer", "info", "Allied maritime patrol aircraft available",
             "Partner nation offers one maritime patrol sortie over the southern Baltic from 20:00 for six hours, subject to tasking request.",
             (17.0, 56.5), 200_000, ("area-gotland",), None, ("allied", "mpa", "offer")),
    Scripted(370, "logistics_report", "battalion", "Logistics Regiment S4", "warning", "Depot Syd fuel 30 %",
             "Depot Syd diesel stock down to 30 % after convoy issue. Resupply from Depot Mitt scheduled; ETA 5 h. Southern brigade fuel autonomy 36 h.",
             None, None, ("depot-syd", "garrison-syd", "sup-s-01"), "07", ("fuel", "depot")),
    Scripted(400, "head_of_state_directive", "head_of_state", "Government Offices", "critical", "Raise national readiness; protect civil functions",
             "Government decision: heightened readiness nationally. Civil functions (power, telecom, transport) protection takes precedence over exercise activity. Report hourly.",
             None, None, ("power-mitt", "power-syd", "telecom-stockholm", "bridge-oresund"), None, ("national", "readiness", "civil_protection")),
    Scripted(430, "sensor_detection", "sensor", "Sensor Site Syd", "warning", "Unknown sea track S2 in Öresund approaches",
             "Surface contact 7 kn without AIS tracking north through Öresund approaches; course consistent with transit toward Kattegat.",
             (12.4, 55.95), 8_000, ("unk-sea-02", "area-oresund", "radar-syd"), "12", ("sea", "unknown_track")),
    Scripted(460, "field_report", "soldier", "Sgt. A. Nilsson, Garrison Syd", "warning", "Generator failure during outage",
             "Backup generator 2 at Garrison Syd failed to start under the grid outage. Running on generator 1 only; comms and medical on priority circuit.",
             None, None, ("garrison-syd", "power-syd"), "12", ("power", "generator", "fault")),
    Scripted(490, "unit_sitrep", "battalion", "Brigade North S3", "info", "Routine SITREP Brigade North",
             "All units on schedule. N1T-03 moving at reduced speed pending recovery team. Weather clear, -2 °C.",
             None, None, ("garrison-norr", "coy-n1t-03", "mnt-n-01"), "25", ("routine",)),
    Scripted(520, "infrastructure_status", "operator", "Telecom operator (public)", "advisory", "Telecom core Stockholm capacity reduced",
             "Fibre cut north of Stockholm; mobile data capacity in the northern suburbs reduced ~25 %. Repair crew on site, ETA 4 h.",
             None, 25_000, ("telecom-stockholm",), "01", ("telecom", "degraded")),
    Scripted(550, "intel_report", "joint", "J2 Joint Intelligence", "info", "Unknown air track A1 assessed as transport",
             "Track A1 behaviour consistent with civil transport without transponder; monitoring continues, no change in posture recommended.",
             None, None, ("unk-air-01",), "09", ("assessment", "downgrade")),
    Scripted(640, "public_news", "media", "Social media (unverified accounts)", "warning", "Claims of landing craft off Ystad",
             "Dozens of new accounts post near-identical messages and a blurry video claiming hostile landing craft approaching the beach east of Ystad.",
             (13.95, 55.40), 15_000, (), "12", ("hostile_claim", "landing", "social_media", "amplified")),
    Scripted(700, "public_news", "media", "Social media (open source)", "advisory", "Armoured column filmed near Haparanda",
             "Video shared publicly shows a column of tracked vehicles on the E4 west of Haparanda. Posters speculate about a foreign incursion.",
             (23.85, 65.86), 20_000, (), "25", ("column", "social_media", "opsec")),
    Scripted(880, "sensor_detection", "sensor", "Sea surveillance (AIS + radar fusion)", "warning", "Tanker NORDIC STAR slowing over cable corridor",
             "AIS-declared tanker NORDIC STAR reduced to 2 kn with repeated course changes east of Gotland, inside the Gotland–Lithuania cable corridor. Draught inconsistent with a laden tanker.",
             (19.62, 57.0), 6_000, ("unk-sea-03", "area-gotland"), "09", ("sea", "ais", "cable")),
    Scripted(920, "sensor_detection", "sensor", "Sensor Site Syd", "advisory", "Track A3: radar-only contact",
             "New air track A3 south-east of Öland at 4000 m, 150 m/s. No IFF, no ESM intercept. Speed and heading constant to sensor precision since first detection.",
             (19.5, 56.3), 20_000, ("unk-air-03", "radar-syd"), "08", ("air", "unknown_track", "no_emitter")),
    Scripted(1000, "allied_liaison", "allied", "Allied maritime liaison officer", "warning", "Partner flags NORDIC STAR",
             "Partner nation reports NORDIC STAR changed name and flag twice in 18 months; ownership opaque; earlier AIS spoofing observed in the Gulf of Finland.",
             None, None, ("unk-sea-03",), None, ("flag_of_convenience", "maritime")),
    Scripted(1240, "sensor_detection", "sensor", "Airbase Syd short-range radar", "critical", "Small UAS over Airbase Syd",
             "Three small UAS tracks orbiting Airbase Syd at 150 m, 2.5–3.5 km from the shelter area. No flight plans; control links not identified.",
             None, 4_000, ("unk-uas-01", "unk-uas-02", "unk-uas-03", "airbase-syd"), "12", ("drone", "small_uas", "night")),
    Scripted(1300, "field_report", "soldier", "Guard Sgt. M. Holm, Airbase Syd", "warning", "Drone lights over shelter area",
             "Guard post 4 observes two blinking lights moving slowly over dispersal B, then heading north-east. Sound consistent with small multirotor.",
             None, 3_000, ("airbase-syd",), "12", ("drone", "perimeter")),
    Scripted(1560, "sensor_detection", "sensor", "Sea surveillance (AIS + radar fusion)", "critical", "NORDIC STAR AIS lost over cable",
             "AIS from NORDIC STAR stopped for the second time while the radar still holds a slow contact inside the cable corridor.",
             (19.6, 57.0), 5_000, ("unk-sea-03",), "09", ("sea", "ais_gap", "cable")),
]

ROUTINE_ENTITIES = ["coy-s1a-01", "sup-c-01", "fl-s-cor1", "aw-s-03", "hs-1-01", "hg-12-1a", "depot-mitt", "garrison-vast", "uav-02", "coy-w1t-01", "fl-w-pat1", "comms-norr"]


def scripted_reports(epoch: datetime, now_s: float) -> list[InputReport]:
    """All scripted reports effective at or before scenario second now_s, plus routine SITREPs every 90 s."""
    out: list[InputReport] = []
    for i, s in enumerate(SCRIPT):
        if s.at_s > now_s:
            continue
        ts = (epoch + timedelta(seconds=s.at_s)).isoformat()
        out.append(InputReport(
            id=f"in-{i + 1:03d}", channel=s.channel, authorLevel=s.author_level, author=s.author, receivedAt=ts, effectiveAt=ts,  # type: ignore[arg-type]
            severity=s.severity, title=s.title, text=s.text,
            position=GeoPosition(longitudeDeg=s.position[0], latitudeDeg=s.position[1]) if s.position else None,
            radiusM=s.radius_m, entityRefs=list(s.entity_refs), region=s.region, tags=list(s.tags), sourceKind="simulated",
        ))
    k = 0
    t = 600.0
    while t <= now_s:
        ent = ROUTINE_ENTITIES[k % len(ROUTINE_ENTITIES)]
        ts = (epoch + timedelta(seconds=t)).isoformat()
        out.append(InputReport(id=f"in-r{k + 1:03d}", channel="unit_sitrep", authorLevel="company", author=f"{ent} reporting", receivedAt=ts, effectiveAt=ts,
                               severity="info", title=f"Routine report {ent}", text="Position, fuel and personnel state reported on schedule. No change.",
                               entityRefs=[ent], tags=["routine"], sourceKind="simulated"))
        k += 1
        t += 90
    return out


# ---- rule-based text parsing for operator-submitted reports --------------------------------
SEVERITY_WORDS: list[tuple[str, Severity]] = [
    (r"\b(casualt|killed|explosion|attack|critical|mayday|collision|fire\b)", "critical"),
    (r"\b(fault|outage|unknown|unidentified|lost|failure|degraded|warning|injur)", "warning"),
    (r"\b(request|observed|delay|reduced|advisory|minor)", "advisory"),
]
TAG_WORDS: dict[str, str] = {
    "fuel": "fuel", "diesel": "fuel", "ammunition": "ammunition", "ammo": "ammunition", "hydraul": "fault", "fault": "fault", "engine": "fault",
    "drone": "drone", "uav": "drone", "radar": "sensor", "comms": "comms", "radio": "comms", "power": "power", "grid": "power", "telecom": "telecom",
    "medevac": "medevac", "injur": "casualties", "casualt": "casualties", "wind": "weather", "storm": "weather", "snow": "weather", "ice": "weather",
    "cyber": "cyber", "malware": "cyber", "unknown": "unknown_track", "unidentified": "unknown_track", "priority": "priority", "bridge": "transport",
}


def parse_input(body: InputIn, entity_ids: set[str], received_at: datetime) -> InputReport:
    """Deterministic extraction: severity from keywords (unless given), entity ids and place names from the text."""
    text = f"{body.title} {body.text}"
    low = text.lower()
    severity: Severity = body.severity or "info"
    if body.severity is None:
        for pattern, sev in SEVERITY_WORDS:
            if re.search(pattern, low):
                severity = sev
                break
    refs = list(dict.fromkeys(body.entityRefs + [eid for eid in entity_ids if re.search(rf"\b{re.escape(eid)}\b", low)]))
    tags = list(dict.fromkeys(body.tags + [tag for word, tag in TAG_WORDS.items() if word in low]))
    position = body.position
    if position is None:
        for name, (lng, lat) in P.items():
            if not name.startswith("sea_") and name in low:
                position = GeoPosition(longitudeDeg=lng, latitudeDeg=lat)
                tags.append(f"place:{name}")
                break
    ts = received_at.astimezone(timezone.utc).isoformat()
    return InputReport(id="", channel=body.channel, authorLevel=body.authorLevel, author=body.author, receivedAt=ts, effectiveAt=ts,
                       severity=severity, title=body.title, text=body.text, position=position, radiusM=body.radiusM or (5_000 if position else None),
                       entityRefs=refs, region=body.region, tags=tags, sourceKind="observed")
