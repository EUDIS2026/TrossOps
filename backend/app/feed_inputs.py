"""Real public feeds as rule-engine inputs (sourceKind `public` / `observed`).

Only cached feed payloads are read here — an evaluation never waits on the network. The browser's live layers keep
the caches warm; on a cold instance the engine simply sees no real inputs yet. Translations are deliberately narrow:
- SMHI impact-based warnings (yellow and above) → `weather_advisory` (feeds R07: air/sea readiness penalties).
- Police events mentioning drones, sabotage, explosions or shooting → `police_event` (R16 and the deception layer).
- ADS-B emergency squawks (7500/7600/7700) and clusters of degraded GNSS integrity → `sensor_detection`.
- Pattern indicators on real traffic (rule R19): AIS vessels slow over an undersea cable corridor for >= 20 min, and
  ADS-B aircraft flying orbit/racetrack patterns (the signature of ISR flights). These are neutral indicators derived
  from public broadcasts, never assessments of the named vessel or aircraft.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from . import feeds, geo
from .orbat import CABLES
from .models import GeoPosition, InputReport

SEVERITY = {"yellow": "advisory", "orange": "warning", "red": "critical"}
POLICE_KEYWORDS = {"drone", "drönare", "sabotage", "explosion", "skottlossning", "sprängning"}


def _cached(feed) -> dict:
    return getattr(feed, "_data", None) or {}


def _ring_center(geom: dict | None) -> tuple[tuple[float, float], float] | None:
    if not geom:
        return None
    coords: list = []
    t = geom.get("type")
    if t == "Polygon":
        coords = geom["coordinates"][0]
    elif t == "MultiPolygon":
        coords = [p for poly in geom["coordinates"] for p in poly[0]]
    elif t == "LineString":
        coords = geom["coordinates"]
    if not coords:
        return None
    cx = sum(p[0] for p in coords) / len(coords)
    cy = sum(p[1] for p in coords) / len(coords)
    r = max(geo.haversine_m((cx, cy), (p[0], p[1])) for p in coords)
    return (cx, cy), max(r, 10_000)


def inputs_for_engine(t: float) -> list[InputReport]:
    now = datetime.now(timezone.utc)
    iso = now.isoformat()
    out: list[InputReport] = []
    for w in _cached(feeds.SMHI_WARNINGS).get("items", []) or []:
        sev = SEVERITY.get(w.get("level") or "")
        c = _ring_center(w.get("geometry"))
        if not sev or not c:
            continue
        (lng, lat), r = c
        out.append(InputReport(id=f"in-x-smhi-{w['id']}", channel="weather_advisory", authorLevel="civil_authority", author="SMHI (real warning)", receivedAt=w.get("published") or iso,
                               effectiveAt=w.get("validFrom") or iso, severity=sev, title=f"{(w.get('level') or '').title()} warning: {w.get('event') or w.get('headline')} — {w.get('areaName')}",  # type: ignore[arg-type]
                               text=(w.get("description") or w.get("headline") or "")[:600], position=GeoPosition(longitudeDeg=lng, latitudeDeg=lat), radiusM=r,
                               region=None, tags=["weather", "smhi", "real"], sourceKind="public"))
    cutoff = (now - timedelta(hours=6)).isoformat()
    for ev in _cached(feeds.POLISEN).get("items", []) or []:
        kws = set(ev.get("keywords") or [])
        if not kws & POLICE_KEYWORDS or ev.get("lng") is None or (ev.get("datetime") or "") < cutoff:
            continue
        tags = ["police", "real"] + (["drone"] if kws & {"drone", "drönare"} else []) + sorted(kws)
        out.append(InputReport(id=f"in-x-pol-{ev['id']}", channel="police_event", authorLevel="civil_authority", author="Polisen (real event)", receivedAt=ev.get("datetime") or iso,
                               effectiveAt=ev.get("datetime") or iso, severity="advisory", title=ev.get("name") or "Police event", text=ev.get("summary") or "",
                               position=GeoPosition(longitudeDeg=ev["lng"], latitudeDeg=ev["lat"]), radiusM=25_000 if ev.get("precision") == "municipality" else 60_000,
                               tags=tags, sourceKind="public"))
    adsb = _cached(feeds.ADSB)
    for ac in adsb.get("items", []) or []:
        if ac.get("squawk") in ("7500", "7600", "7700") or ac.get("emergency"):
            what = {"7500": "unlawful interference", "7600": "radio failure", "7700": "general emergency"}.get(ac.get("squawk"), ac.get("emergency") or "emergency")
            out.append(InputReport(id=f"in-x-sq-{ac['id']}", channel="sensor_detection", authorLevel="sensor", author="ADS-B (adsb.lol, real)", receivedAt=iso, effectiveAt=iso,
                                   severity="critical" if ac.get("squawk") == "7500" else "warning", title=f"{ac.get('callsign') or ac['id']} squawks {ac.get('squawk')} ({what})",
                                   text=f"Real ADS-B: {ac.get('type') or 'aircraft'} {ac.get('registration') or ''} at {ac.get('altM') or 0:.0f} m.", position=GeoPosition(longitudeDeg=ac["lng"], latitudeDeg=ac["lat"]),
                                   radiusM=20_000, tags=["air", "squawk", "real"], sourceKind="observed"))
    try:
        samples = feeds.ADSB.gnss()
    except Exception:
        samples = []
    bad = [s for s in samples if s.get("degraded")]
    used: set[int] = set()
    for i, s in enumerate(bad):
        if i in used:
            continue
        group = [j for j, o in enumerate(bad) if geo.haversine_m((s["lng"], s["lat"]), (o["lng"], o["lat"])) < 150_000]
        if len(group) < 3:
            continue
        used.update(group)
        lng = sum(bad[j]["lng"] for j in group) / len(group)
        lat = sum(bad[j]["lat"] for j in group) / len(group)
        near = [o for o in samples if geo.haversine_m((lng, lat), (o["lng"], o["lat"])) < 150_000]
        share = len(group) / max(1, len(near))
        out.append(InputReport(id=f"in-x-gnss-{round(lng, 1)}-{round(lat, 1)}", channel="sensor_detection", authorLevel="sensor", author="ADS-B integrity (adsb.lol, real)",
                               receivedAt=iso, effectiveAt=iso, severity="warning" if share > 0.4 else "advisory",
                               title=f"GNSS interference indicated ({len(group)} of {len(near)} aircraft degraded)",
                               text="Aircraft report reduced navigation integrity (NIC < 7 or NACp < 8) in this area. Consistent with GNSS jamming or spoofing.",
                               position=GeoPosition(longitudeDeg=lng, latitudeDeg=lat), radiusM=150_000, tags=["gnss", "ew", "real"], sourceKind="observed"))
    out.extend(_ais_cable_loiter(iso))
    out.extend(_adsb_orbits(iso))
    _ = t
    return out


def _dist_to_line_m(p: tuple[float, float], coords: list[list[float]]) -> float:
    kx = 111_320 * math.cos(math.radians(p[1]))
    best = float("inf")
    for a, b in zip(coords, coords[1:]):
        ax, ay, bx, by = (a[0] - p[0]) * kx, (a[1] - p[1]) * 110_540, (b[0] - p[0]) * kx, (b[1] - p[1]) * 110_540
        dx, dy = bx - ax, by - ay
        f = max(0.0, min(1.0, -(ax * dx + ay * dy) / ((dx * dx + dy * dy) or 1e-9)))
        best = min(best, math.hypot(ax + f * dx, ay + f * dy))
    return best


def _ais_cable_loiter(iso: str) -> list[InputReport]:
    """Real AIS: slow (< 2 kn) within 2 km of a cable corridor, away from its landing points, for at least 20 minutes."""
    out = []
    for v in _cached(feeds.AIS).get("items", []) or []:
        p = (v.get("lng"), v.get("lat"))
        if p[0] is None or (v.get("speedMps") or 0) > 1.0:
            continue
        for c in CABLES:
            ends = (tuple(c["coords"][0]), tuple(c["coords"][-1]))
            if min(geo.haversine_m(p, e) for e in ends) < 8_000 or _dist_to_line_m(p, c["coords"]) > 2_000:  # type: ignore[arg-type]
                continue
            hist = feeds.AIS.history(v["id"])
            run = [h for h in hist if (h.get("speedMps") or 0) <= 1.0 and _dist_to_line_m((h["lng"], h["lat"]), c["coords"]) <= 2_000]
            minutes = (run[-1]["timestampMs"] - run[0]["timestampMs"]) / 60_000 if len(run) >= 2 else 0
            if minutes < 20:
                continue
            name = v.get("name") or f"MMSI {v['id']}"
            status = v.get("navStatusLabel") or "status not reported"
            out.append(InputReport(id=f"in-x-ais-{v['id']}-{c['id']}", channel="sensor_detection", authorLevel="sensor", author="AIS pattern indicator (Digitraffic, real)",
                                   receivedAt=iso, effectiveAt=iso, severity="advisory", title=f"{name} slow over {c['label']} for {minutes:.0f} min",
                                   text=f"Public AIS: {v.get('shipTypeLabel') or 'vessel'} at {(v.get('speedMps') or 0) * 1.944:.1f} kn, {status}, within 2 km of the corridor. "
                                        "A pattern indicator from public broadcasts, not an assessment of the vessel.",
                                   position=GeoPosition(longitudeDeg=p[0], latitudeDeg=p[1]), radiusM=5_000, tags=["ais", "cable", "loiter", "real"], sourceKind="observed"))
            break
    return out


def _adsb_orbits(iso: str) -> list[InputReport]:
    """Real ADS-B: >= 330 degrees of accumulated turn within a compact area over >= 8 min (orbits, racetracks)."""
    out = []
    for ac in _cached(feeds.ADSB).get("items", []) or []:
        if ac.get("onGround"):
            continue
        tr = feeds.ADSB.trail(ac["id"])
        if len(tr) < 12 or tr[-1]["t"] - tr[0]["t"] < 480:
            continue
        turn, prev = 0.0, None
        for a, b in zip(tr, tr[1:]):
            if geo.haversine_m((a["lng"], a["lat"]), (b["lng"], b["lat"])) < 200:
                continue
            brg = geo.bearing_deg((a["lng"], a["lat"]), (b["lng"], b["lat"]))
            if prev is not None:
                turn += abs(geo.wrap_heading_delta(prev, brg))
            prev = brg
        cx = sum(x["lng"] for x in tr) / len(tr)
        cy = sum(x["lat"] for x in tr) / len(tr)
        spread = max(geo.haversine_m((cx, cy), (x["lng"], x["lat"])) for x in tr)
        if turn < 330 or spread > 80_000:
            continue
        mil = bool(ac.get("military"))
        who = ac.get("callsign") or ac["id"].upper()
        out.append(InputReport(id=f"in-x-orb-{ac['id']}", channel="sensor_detection", authorLevel="sensor", author="ADS-B pattern indicator (adsb.lol, real)",
                               receivedAt=iso, effectiveAt=iso, severity="advisory" if mil else "info",
                               title=f"{who} flying an orbit pattern ({ac.get('type') or 'aircraft'}{', military-flagged' if mil else ''})",
                               text=f"Public ADS-B: {turn:.0f} degrees of turn within {spread / 1000:.0f} km over {(tr[-1]['t'] - tr[0]['t']) / 60:.0f} min at {ac.get('altM') or 0:.0f} m. "
                                    "Orbits are typical of surveillance, training, survey or holding; a pattern indicator, not an assessment.",
                               position=GeoPosition(longitudeDeg=cx, latitudeDeg=cy), radiusM=max(spread, 10_000), tags=["air", "orbit", "real"] + (["military"] if mil else []),
                               sourceKind="observed"))
    return out
