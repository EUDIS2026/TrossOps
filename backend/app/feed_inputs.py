"""Real public feeds as rule-engine inputs (sourceKind `public` / `observed`).

Only cached feed payloads are read here — an evaluation never waits on the network. The browser's live layers keep
the caches warm; on a cold instance the engine simply sees no real inputs yet. Translations are deliberately narrow:
- SMHI impact-based warnings (yellow and above) → `weather_advisory` (feeds R07: air/sea readiness penalties).
- Police events mentioning drones, sabotage, explosions or shooting → `police_event` (R16 and the deception layer).
- ADS-B emergency squawks (7500/7600/7700) and clusters of degraded GNSS integrity → `sensor_detection`.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from . import feeds, geo
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
    _ = math, t
    return out
