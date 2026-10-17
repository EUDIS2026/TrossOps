"""Scenario injection: operator-triggered synthetic events that every rule reacts to like any other input.

Each preset is deterministic in (preset, atS, revision) so a persisted injection replays identically. Presets add
inputs (reports, sensor detections, directives) and, where the event is physical, spawn sensor-held tracks with a
declared motion. All injected content is synthetic and labelled `simulated`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from . import geo
from .models import GeoPosition, InputReport
from .motion import MotionSpec, Path, densify
from .orbat import CABLES, Node

PRESETS = {
    "drone_swarm": "Drone swarm over Airbase Norr",
    "cable_cut": "Undersea cable damage east of Gotland",
    "air_raid": "Inbound air raid from the south-east",
    "gnss_jamming": "GNSS jamming in the southern Baltic",
    "power_outage": "Regional power outage in Mälardalen",
    "disinformation": "Disinformation wave about Göteborg port",
}


@dataclass
class Injection:
    inputs: list[InputReport]
    tracks: list[Node]
    message: str


def _input(rev: int, k: int, epoch: datetime, at_s: float, speed: float, channel: str, level: str, author: str, severity: str, title: str, text: str,
           pos: tuple[float, float] | None = None, radius: float | None = None, refs: tuple[str, ...] = (), tags: tuple[str, ...] = ()) -> InputReport:
    ts = (epoch + timedelta(seconds=at_s / speed)).isoformat()
    return InputReport(id=f"in-j{rev}-{k}", channel=channel, authorLevel=level, author=author, receivedAt=ts, effectiveAt=ts, severity=severity,  # type: ignore[arg-type]
                       title=title, text=text, position=GeoPosition(longitudeDeg=pos[0], latitudeDeg=pos[1]) if pos else None, radiusM=radius,
                       entityRefs=list(refs), tags=list(tags) + ["injected"], sourceKind="simulated")


def _track(tid: str, label: str, domain: str, sidc: str, pts: list[tuple[float, float]], speeds: list[float] | float, start: float, alt: float | None, tags: list[str], model: str,
           mode: str = "once") -> Node:
    path = Path([(p[0], p[1], alt) for p in pts], speeds if isinstance(speeds, list) else [speeds])
    return Node(tid, label, "unknown", domain, "track.unknown", sidc, "unknown", None, None, label.split(" ")[-1], None, model, None, None, [],
                MotionSpec("path", path=path, start_s=start, mode=mode, airborne=domain == "air"), tags=tags + ["injected"])


def build(preset: str, at_s: float, rev: int, epoch: datetime, speed: float, sites: dict[str, tuple[float, float]]) -> Injection:
    if preset not in PRESETS:
        raise KeyError(preset)
    I = lambda k, *a, **kw: _input(rev, k, epoch, at_s, speed, *a, **kw)  # noqa: E731
    tracks: list[Node] = []
    inputs: list[InputReport] = []
    if preset == "drone_swarm":
        base = sites["airbase-norr"]
        for k in range(6):
            ring = [geo.destination(base, b + k * 60, 1800 + (k % 3) * 700) for b in range(0, 1081, 30)]
            tracks.append(_track(f"inj{rev}-uas-{k + 1}", f"Unknown UAS J{rev}-{k + 1}", "air", "SUAPMFQ-----", ring, 16.0 + k, at_s + k * 20, 140.0, ["small_uas", "low_level"], "uav"))
        inputs.append(I(1, "sensor_detection", "sensor", "Airbase Norr short-range radar", "critical", "Six small UAS over Airbase Norr",
                        "Six small UAS orbiting Airbase Norr at 140 m, 1.8–3.2 km from the dispersal areas. Coordinated spacing; no flight plans.", None, 5_000,
                        ("airbase-norr",) + tuple(t.id for t in tracks), ("drone", "small_uas")))
        inputs.append(I(2, "field_report", "soldier", "Guard post 2, Airbase Norr", "warning", "Drone lights over dispersal A",
                        "At least four drones with navigation lights over dispersal A, heading changes every few minutes.", None, 3_000, ("airbase-norr",), ("drone", "perimeter")))
        msg = "Six small UAS now orbit Airbase Norr; R16 proposes counter-UAS options."
    elif preset == "cable_cut":
        cable = CABLES[1]
        mid = tuple(cable["coords"][2])
        loiter = [(mid[0] + 0.02, mid[1] + 0.01), (mid[0] - 0.02, mid[1] - 0.005), (mid[0] + 0.015, mid[1] - 0.012), (mid[0] - 0.01, mid[1] + 0.01)] * 3
        tracks.append(_track(f"inj{rev}-ves-1", f"Bulk carrier OCEAN DAWN (AIS) J{rev}", "sea", "SSSPXMC-----", [(mid[0] + 0.3, mid[1] - 0.2)] + loiter, [5.0] + [0.9] * (len(loiter) - 1),
                             at_s - 1200, None, ["ais_declared:cargo", "ais_gaps", "loiter_over_cable"], "cargo_ship"))
        inputs.append(I(1, "infrastructure_status", "operator", "Grid operator (public)", "critical", "Gotland–mainland power link tripped",
                        "Protection tripped on the Gotland–mainland link; fault location estimated mid-strait. Gotland on local generation; repair vessel needed.",
                        mid, 30_000, (), ("power", "cable", "outage")))
        inputs.append(I(2, "sensor_detection", "sensor", "Sea surveillance (AIS + radar fusion)", "warning", "Vessel over the cable at the fault location",
                        "Bulk carrier OCEAN DAWN has loitered over the cable corridor at under 2 kn for 40 minutes with two AIS gaps.", mid, 4_000, (tracks[0].id,), ("sea", "ais", "cable")))
        msg = "Cable fault reported; a loitering bulk carrier sits over the corridor (R17, deception)."
    elif preset == "air_raid":
        targets = [sites["airbase-syd"], sites["navbase-syd"], sites["radar-syd"], sites["garrison-syd"]]
        for k, tgt in enumerate(targets):
            start = (21.8 + 0.3 * k, 55.2 + 0.15 * k)
            mid = geo.interpolate(start, tgt, 0.55)
            mid = geo.destination(mid, 0, 15_000 * (k - 1.5))
            tracks.append(_track(f"inj{rev}-air-{k + 1}", f"Unknown air track R{rev}-{k + 1}", "air", "SUAPMF------", densify([start, mid, tgt], 8000), 245.0, at_s + k * 15, 300.0,
                                 ["low_level", "fast"], "fighter"))
        inputs.append(I(1, "sensor_detection", "sensor", "Air surveillance (fused)", "critical", "Four fast low-level tracks inbound from the south-east",
                        "Four tracks at 245 m/s and 300 m over the southern Baltic, no IFF, heading for the Skåne–Blekinge coast. Time to coast about 12 minutes.",
                        (21.9, 55.4), 60_000, tuple(t.id for t in tracks), ("air", "unknown_track", "inbound")))
        inputs.append(I(2, "command_directive", "regional", "Joint Operations Commander", "critical", "Scramble QRA; air defence weapons free in the south",
                        "Scramble QRA from Airbase Syd. Southern AD units to weapons free for unidentified tracks failing to respond.", None, None, ("airbase-syd",), ("priority", "air_defence")))
        msg = "Four fast unknown tracks inbound; R01 predicts targets and proposes intercepts."
    elif preset == "gnss_jamming":
        inputs.append(I(1, "sensor_detection", "sensor", "ADS-B integrity monitoring", "warning", "GNSS interference over the southern Baltic",
                        "Aircraft and ships report position jumps and loss of GNSS integrity across a 150 km area south of Öland. Pattern consistent with jamming.",
                        (17.2, 55.6), 150_000, (), ("gnss", "ew")))
        inputs.append(I(2, "allied_liaison", "allied", "Allied maritime liaison officer", "advisory", "Partner reports spoofed positions",
                        "Two merchant ships report AIS positions inland on Bornholm; partner navy confirms GNSS spoofing in the area.", (15.4, 55.2), 80_000, (), ("gnss", "spoofing")))
        msg = "GNSS interference reported; R18 flags affected air and sea units."
    elif preset == "power_outage":
        inputs.append(I(1, "infrastructure_status", "operator", "Grid operator (public)", "critical", "Grid Node Mälardalen tripped",
                        "Transmission node Mälardalen tripped after a transformer fault. 60 % load shed in Västmanland and Uppsala; restoration estimate 6 h.",
                        None, 90_000, ("power-mitt", "hq-joint", "comms-mitt", "airbase-mitt", "hospital-mitt"), ("power", "outage")))
        msg = "Grid Node Mälardalen down; dependent HQ, comms, airbase and hospital lose readiness (R05)."
    else:  # disinformation
        port = sites["port-goteborg"]
        inputs.append(I(1, "public_news", "media", "Social media (new accounts)", "critical", "Claims of explosions at Göteborg port",
                        "Hundreds of new accounts share an identical video claiming explosions and burning ships at Göteborg port. The video's buildings do not match the port.",
                        port, 10_000, ("port-goteborg",), ("hostile_claim", "social_media", "amplified", "uncorroborated")))
        inputs.append(I(2, "public_news", "media", "Regional newspaper (open source)", "advisory", "Newspaper asks police about port reports",
                        "Regional newspaper reports that police have no information about any incident at the port.", port, 10_000, (), ("media",)))
        msg = "Disinformation wave injected; the deception layer scores it against coverage and sources."
    return Injection(inputs, tracks, msg)
