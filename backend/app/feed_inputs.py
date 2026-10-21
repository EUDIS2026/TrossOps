"""Real public feeds as rule-engine inputs (sourceKind `public` / `observed`).

Only cached feed payloads are read here — an evaluation never waits on the network. The browser's live layers keep
the caches warm; on a cold instance the engine simply sees no real inputs yet. Translations are deliberately narrow:
- SMHI impact-based warnings (yellow and above) → `weather_advisory` (feeds R07: air/sea readiness penalties).
- Police events mentioning drones, sabotage, explosions or shooting → `police_event` (R16 and the deception layer).
- ADS-B emergency squawks (7500/7600/7700) and clusters of degraded GNSS integrity → `sensor_detection`.
- Pattern indicators on real traffic (rule R19): AIS vessels slow over an undersea cable corridor for >= 20 min, and
  ADS-B aircraft flying orbit/racetrack patterns (the signature of ISR flights). These are neutral indicators derived
  from public broadcasts, never assessments of the named vessel or aircraft.
- Trafikverket road situations (accidents, obstructions, restrictions) in force now or within 6 h → `road_situation`
  (rule R21: obstructions on a moving column's route, accidents near own sites).
- NASA FIRMS VIIRS thermal anomalies from the last 24 h, clustered per heat source → `thermal_anomaly` (rule R22 and
  the deception layer's corroboration of explosion and fire claims).
The engine keeps a road situation or thermal anomaly only when it concerns the picture (`relevance.relevant`): near an own site,
an own road march, or (thermal) a reported explosion or fire.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone

from . import feeds, geo
from .envfile import public_mode
from .orbat import CABLES
from .models import GeoPosition, InputReport

SEVERITY = {"yellow": "advisory", "orange": "warning", "red": "critical"}
# Keys emitted by feeds/polisen.py `keywords()` (English ids; the Swedish words are matched there). Fires ("brand") are
# left out on purpose: ordinary building fires are frequent and would bury the operational picture.
POLICE_KEYWORDS = {"drone", "sabotage", "explosion", "shooting", "bomb-threat", "suspicious-object"}


def _when(s) -> datetime | None:
    """Aware datetime from an ISO string with 'Z' or an offset (naive = UTC); None when missing or unparsable."""
    if not isinstance(s, str) or not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


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
        valid_to = _when(w.get("validTo"))
        if valid_to is not None and valid_to < now:
            continue  # expired warning (validTo null = until further notice); future ones stay as forecasts (R07 shows, does not penalise)
        (lng, lat), r = c
        out.append(InputReport(id=f"in-x-smhi-{w['id']}", channel="weather_advisory", authorLevel="civil_authority", author="SMHI (real warning)", receivedAt=w.get("published") or iso,
                               effectiveAt=w.get("validFrom") or iso, severity=sev, title=f"{(w.get('level') or '').title()} warning: {w.get('event') or w.get('headline')} — {w.get('areaName')}",  # type: ignore[arg-type]
                               text=(w.get("description") or w.get("headline") or "")[:600], position=GeoPosition(longitudeDeg=lng, latitudeDeg=lat), radiusM=r,
                               region=None, tags=["weather", "smhi", "real"], sourceKind="public"))
    cutoff = now - timedelta(hours=6)
    for ev in _cached(feeds.POLISEN).get("items", []) or []:
        kws = set(ev.get("keywords") or [])
        when = _when(ev.get("datetime"))
        # Compare instants, not strings: police times carry +01:00/+02:00 offsets, the cutoff is UTC.
        if not kws & POLICE_KEYWORDS or ev.get("lng") is None or when is None or when < cutoff:
            continue
        tags = ["police", "real"] + sorted(kws)
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
    out.extend(_memo("tv", feeds.TRAFIKVERKET, now, road_situations))
    out.extend(_memo("firms", feeds.FIRMS, now, thermal_anomalies))
    _ = t
    return out


_MEMO: dict[str, tuple[tuple, list[InputReport]]] = {}


def _memo(key: str, feed, now: datetime, fn) -> list[InputReport]:
    """Large feeds (hundreds of road situations or fire pixels) are translated once per feed payload and minute, not
    on every 2 s evaluation. The reports are shared between evaluations; the engine only (re)sets `acknowledged` on them."""
    data = _cached(feed)
    items = data.get("items") or []
    sig = (hash(tuple((it.get("id"), it.get("lng"), it.get("lat"), it.get("start"), it.get("end"), it.get("acquired")) for it in items if isinstance(it, dict))),
           len(items), int(now.timestamp() // 60))
    hit = _MEMO.get(key)
    if hit is None or hit[0] != sig:
        hit = (sig, fn(now))
        _MEMO[key] = hit
    return list(hit[1])


# ---- Trafikverket road situations -> `road_situation` -----------------------------------------------------------------
ROAD_KIND = {"Olycka": "accident", "Hinder": "obstruction", "Restriktion": "restriction", "Viktig trafikinformation": "traffic_info"}
ROAD_KIND_EN = {"accident": "Accident", "obstruction": "Obstruction", "restriction": "Restriction", "traffic_info": "Traffic information"}
ROAD_BASE_SEVERITY = {"accident": "advisory", "obstruction": "advisory", "restriction": "info", "traffic_info": "info"}
ROAD_LOOKAHEAD = timedelta(hours=6)  # a situation starting later than this is not yet relevant to a march
ACCIDENT_STALE = timedelta(hours=12)  # an accident with no end time older than this is a stale record, not a live blockage


def road_situations(now: datetime) -> list[InputReport]:
    """Trafikverket deviations with a position, in force now or within ROAD_LOOKAHEAD, not ended. Severity: accidents and
    obstructions advisory, restrictions and traffic information info; Trafikverket's own impact grade 4-5 ('stor' /
    'mycket stor påverkan') raises one step. The end time travels as a `valid_to:` tag so rules can tell whether the
    situation will still be there when a column arrives."""
    out = []
    for it in _cached(feeds.TRAFIKVERKET).get("items", []) or []:
        try:
            r = _road_item(it, now)
        except Exception:  # noqa: BLE001  one malformed deviation must not drop the rest (or the other feeds' inputs)
            r = None
        if r is not None:
            out.append(r)
    return out


def _road_item(it: dict, now: datetime) -> InputReport | None:
    iso = now.isoformat()
    kind = ROAD_KIND.get(it.get("type") or "")
    if not kind or it.get("lng") is None or it.get("lat") is None or not it.get("id"):
        return None
    start, end = _when(it.get("start")), _when(it.get("end"))
    start, end = (start.astimezone(timezone.utc) if start else None), (end.astimezone(timezone.utc) if end else None)
    if end is not None and end < now:
        return None
    if start is not None and start > now + ROAD_LOOKAHEAD:
        return None
    if kind == "accident" and end is None and start is not None and start < now - ACCIDENT_STALE:
        return None
    sev = ROAD_BASE_SEVERITY[kind]
    code = it.get("severityCode")
    if isinstance(code, (int, float)) and code >= 4:
        sev = {"info": "advisory", "advisory": "warning"}.get(sev, sev)
    road = it.get("roadNumber")
    road_s = f"road {road}" if road and not str(road).lower().startswith(("väg", "road", "e")) else (str(road) if road else "")
    where = ", ".join(x for x in (road_s, it.get("location") or "") if x) or "unnamed road"
    valid = f"In force from {(start or now).strftime('%Y-%m-%d %H:%M')} UTC" + (f" until {end.strftime('%Y-%m-%d %H:%M')} UTC" if end else " until further notice")
    impact = f" Trafikverket impact: {it.get('severity')}." if it.get("severity") else ""
    tags = ["road", "trafikverket", "real", kind] + ([f"valid_to:{end.isoformat()}"] if end else []) + ([f"road:{road}"] if road else [])
    return InputReport(id=f"in-x-tv-{it['id']}", channel="road_situation", authorLevel="civil_authority", author="Trafikverket (real road situation)",
                       receivedAt=iso, effectiveAt=(start or now).isoformat(), severity=sev, title=f"{ROAD_KIND_EN[kind]}: {where}"[:160],  # type: ignore[arg-type]
                       text=f"{(it.get('message') or '').strip()[:400]} {valid}.{impact}".strip(), position=GeoPosition(longitudeDeg=it["lng"], latitudeDeg=it["lat"]),
                       radiusM=500, tags=tags, sourceKind="public")


# ---- NASA FIRMS -> `thermal_anomaly` -----------------------------------------------------------------------------------
FIRMS_MAX_AGE = timedelta(hours=24)
FIRMS_CLUSTER_M = 1_500  # VIIRS 375 m pixels: one heat source shows as several pixels and on several satellites' passes
FIRMS_CONFIDENCE = {"h": "high", "n": "nominal", "l": "low"}
FIRMS_CAVEAT = ("VIIRS detects heat, not fire: gas flares, steelworks, power plants, controlled burns and sun glint also "
                "register. Verify before acting.")


def thermal_anomalies(now: datetime) -> list[InputReport]:
    """VIIRS detections from the last 24 h, nominal or high confidence (low-confidence pixels are mostly glint and edge
    noise), clustered within 1.5 km into one input per heat source. The input id is the earliest detection in the
    cluster, so it stays stable as later passes add detections. A source seen on both day and night passes is
    persistent heat - as consistent with industry or a flare as with a fire - and the text says so."""
    dets = []
    for d in _cached(feeds.FIRMS).get("items", []) or []:
        if not isinstance(d, dict) or not isinstance(d.get("lng"), (int, float)) or not isinstance(d.get("lat"), (int, float)):
            continue
        when = _when(d.get("acquired"))
        conf = str(d.get("confidence") or "").lower()[:1]
        if d.get("lng") is None or d.get("lat") is None or when is None or when < now - FIRMS_MAX_AGE or conf == "l":
            continue
        dets.append((when, str(d.get("id")), d))
    dets.sort(key=lambda x: (x[0], x[1]))
    clusters: list[list[tuple[datetime, str, dict]]] = []
    cells: dict[tuple[int, int], list[int]] = {}  # 0.05° x 0.02° cells (>= 2 km at Swedish latitudes): only neighbours are compared
    for det in dets:
        p = (det[2]["lng"], det[2]["lat"])
        cx, cy = math.floor(p[0] / 0.05), math.floor(p[1] / 0.02)
        near = [k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in cells.get((cx + dx, cy + dy), ())]
        home = next((k for k in sorted(near) if geo.haversine_m(p, (clusters[k][0][2]["lng"], clusters[k][0][2]["lat"])) <= FIRMS_CLUSTER_M), None)
        if home is None:
            cells.setdefault((cx, cy), []).append(len(clusters))
            clusters.append([det])
        else:
            clusters[home].append(det)
    out = []
    for c in clusters:
        first, last = c[0], c[-1]
        frp = max((x[2].get("frpMw") or 0.0) for x in c)
        lng = sum(x[2]["lng"] for x in c) / len(c)
        lat = sum(x[2]["lat"] for x in c) / len(c)
        dn = {str(x[2].get("daynight") or "").upper() for x in c}
        sats = sorted({str(x[2].get("satellite") or x[2].get("source") or "VIIRS") for x in c})
        conf = "high" if any(str(x[2].get("confidence") or "").lower().startswith("h") for x in c) else "nominal"
        persistent = {"D", "N"} <= dn
        text = (f"{len(c)} VIIRS detection(s) ({', '.join(sats)}) within {FIRMS_CLUSTER_M / 1000:.1f} km, first {first[0].strftime('%H:%M')} UTC, "
                f"latest {last[0].strftime('%H:%M')} UTC; peak fire radiative power {frp:.1f} MW, {conf} confidence. "
                + ("Seen on both day and night passes: persistent heat, consistent with industry or a gas flare as much as a fire. " if persistent else "")
                + FIRMS_CAVEAT)
        out.append(InputReport(id=f"in-x-firms-{first[1]}", channel="thermal_anomaly", authorLevel="sensor", author="NASA FIRMS VIIRS (real)",
                               receivedAt=now.isoformat(), effectiveAt=last[0].isoformat(), severity="advisory" if frp >= 10 else "info",
                               title=f"Thermal anomaly, {frp:.0f} MW FRP ({len(c)} detection{'s' if len(c) > 1 else ''})",
                               text=text, position=GeoPosition(longitudeDeg=lng, latitudeDeg=lat), radiusM=FIRMS_CLUSTER_M,
                               tags=["thermal", "firms", "real", f"frp:{frp:.1f}", f"first:{first[0].isoformat()}"] + (["persistent"] if persistent else []),
                               sourceKind="observed"))
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
            # public demo: a real vessel is never named next to a cable (a screenshot would read as an accusation)
            anon = public_mode()
            name = "A vessel" if anon else (v.get("name") or f"MMSI {v['id']}")
            status = v.get("navStatusLabel") or "status not reported"
            vid = hashlib.sha1(str(v["id"]).encode()).hexdigest()[:10] if anon else v["id"]
            out.append(InputReport(id=f"in-x-ais-{vid}-{c['id']}", channel="sensor_detection", authorLevel="sensor", author="AIS pattern indicator (Digitraffic, real)",
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
