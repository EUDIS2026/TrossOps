"""Trajectory planning: route alternatives for one platform to a destination, on the network its domain uses.

- Land: the national road graph (`geonet.national()`), fastest and threat-avoiding variants.
- Sea: the water grid (`geonet.sea()`).
- Air: great circle with a climb / cruise / descent profile; the avoiding variant detours around threat circles.

Every option states distance, time, fuel needed against fuel available, exposure (metres inside threat areas,
weather warnings crossed) and the assumptions it rests on. Committing an option replaces the platform's declared
motion with the planned path from "now" (`Engine.commit_plan`), so the platform visibly executes it.
"""
from __future__ import annotations

import math

from . import geo
from .models import SceneEntity

CRUISE = {"fixed_wing": 230.0, "helicopter": 65.0, "multirotor": 15.0, "vessel": 9.0, "ground_vehicle": 15.0, "personnel": 1.4}
ROAD_CAP = {"mbt": 13.0, "ifv": 14.0, "bv": 11.0, "spg_wheeled": 18.0, "apc_wheeled": 19.0, "police_car": 22.0, "ambulance": 20.0, "car": 22.0}
BURN_PER_KM = {"fixed_wing": 0.055, "helicopter": 0.25, "vessel": 0.02, "ground_vehicle": 0.12, "personnel": 0.0, "multirotor": 0.5}


def _threat_zones(predictions: list, restricted: list[dict]) -> list[dict]:
    zones = []
    for p in predictions:
        if p.uncertaintyRing and p.hypothesis == "constant velocity":
            zones.append({"id": f"threat:{p.entityId}", "label": f"Predicted path of {p.entityId}", "ring": [(q[0], q[1]) for q in p.uncertaintyRing]})
    for a in restricted:
        zones.append({"id": a["id"], "label": a["label"], "ring": [(q[0], q[1]) for q in a["ring"]]})
    return zones


def _inside(p: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    return geo.point_in_ring(p, ring)


def _exposure(coords: list[tuple[float, float]], zones: list[dict]) -> tuple[float, list[str]]:
    metres, hit = 0.0, []
    for a, b in zip(coords, coords[1:]):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        for z in zones:
            if _inside(mid, z["ring"]):
                metres += geo.haversine_m(a, b)
                if z["label"] not in hit:
                    hit.append(z["label"])
                break
    return metres, hit


def _length(coords: list[tuple[float, float]]) -> float:
    return sum(geo.haversine_m(a, b) for a, b in zip(coords, coords[1:]))


def _option(oid: str, label: str, e: SceneEntity, coords: list[tuple[float, float]], alts: list[float | None], speeds: list[float], zones: list[dict],
            warnings: list[dict], based_on: list[str]) -> dict:
    dist = _length(coords)
    dur = sum(geo.haversine_m(a, b) / max(s, 0.1) for a, b, s in zip(coords, coords[1:], speeds))
    burn = BURN_PER_KM.get(e.kind, 0.1) * dist / 1000
    fuel = e.readiness.fuelPct if e.readiness and e.readiness.fuelPct is not None else None
    exp_m, exp_zones = _exposure(coords, zones)
    weather_hits = []
    for w in warnings:
        c, r = w["center"], w["radiusM"]
        if any(geo.haversine_m(p, c) < r for p in coords[:: max(1, len(coords) // 60)]):
            weather_hits.append(w["title"])
    notes = []
    if fuel is not None and fuel - burn < 15:
        notes.append(f"Fuel insufficient: needs {burn:.0f} %, has {fuel:.0f} % (reserve 15 %)")
    if exp_m > 0:
        notes.append(f"{exp_m / 1000:.1f} km inside: {', '.join(exp_zones)}")
    if weather_hits:
        notes.append("Crosses weather warning: " + ", ".join(weather_hits[:2]))
    risk = min(1.0, exp_m / 20_000 + 0.15 * len(weather_hits) + (0.4 if fuel is not None and fuel - burn < 15 else 0))
    return {"id": oid, "label": label, "path": [[round(c[0], 6), round(c[1], 6), None if a is None else round(a, 1)] for c, a in zip(coords, alts)],
            "speeds": [round(s, 2) for s in speeds], "distanceKm": round(dist / 1000, 1), "etaMin": round(dur / 60, 1), "fuelUsePct": round(burn, 1),
            "fuelAfterPct": None if fuel is None else round(fuel - burn, 1), "exposureKm": round(exp_m / 1000, 1), "exposure": exp_zones, "risk": round(risk, 2),
            "feasible": not (fuel is not None and fuel - burn < 5), "notes": notes, "basedOn": based_on, "airborne": e.domain == "air"}


def plan(e: SceneEntity, to: tuple[float, float], predictions: list, restricted: list[dict], warnings: list[dict]) -> dict:
    if not e.position:
        raise ValueError("entity has no position")
    start = (e.position.longitudeDeg, e.position.latitudeDeg)
    zones = _threat_zones(predictions, restricted)
    options: list[dict] = []
    if e.domain == "land" and e.kind != "personnel":
        from . import geonet  # noqa: PLC0415
        cap = ROAD_CAP.get(e.modelKey or "", 16.0)
        net = geonet.national()
        fast = net.route(start, to, max_speed_mps=cap)
        if not fast:
            raise ValueError("no road route")
        speeds = _road_speeds(fast.coords, fast.duration_s, cap)
        options.append(_option("fastest", "Fastest by road", e, fast.coords, [None] * len(fast.coords), speeds, zones, warnings,
                               [f"national road graph (OSM via OpenFreeMap), {len(fast.coords)} vertices", f"convoy speed capped at {cap * 3.6:.0f} km/h for {e.platform or e.kind}",
                                f"class speeds: {', '.join(f'{k} {v / 1000:.0f} km' for k, v in sorted(fast.classes_m.items(), key=lambda kv: -kv[1])[:3])}"]))
        avoid_rings = [z["ring"] for z in zones]
        if avoid_rings:
            safe = net.route(start, to, avoid=avoid_rings, max_speed_mps=cap)
            if safe and _length(safe.coords) > _length(fast.coords) * 1.01:
                options.append(_option("avoid", "Avoid threat areas", e, safe.coords, [None] * len(safe.coords), _road_speeds(safe.coords, safe.duration_s, cap), zones, warnings,
                                       ["same road graph with prohibitive cost inside predicted threat corridors and restricted zones"]))
    elif e.domain == "sea":
        from . import geonet  # noqa: PLC0415
        r = geonet.sea().route(start, to)
        if not r:
            raise ValueError("no sea route")
        v = CRUISE["vessel"]
        alt = -40.0 if e.modelKey == "submarine" else None
        options.append(_option("sea", "Shortest navigable route", e, r.coords, [alt] * len(r.coords), [v] * (len(r.coords) - 1), zones, warnings,
                               ["water grid A* with coastline clearance, smoothed", f"transit speed {v * 1.944:.0f} kn"]))
    elif e.domain == "air":
        v = CRUISE.get(e.kind, 200.0)
        cruise = 7000.0 if e.kind == "fixed_wing" else 300.0
        direct = _air_profile(start, to, cruise, v, e.position.altitudeM)
        options.append(_option("direct", "Direct", e, direct[0], direct[1], direct[2], zones, warnings,
                               [f"great circle at {cruise:.0f} m, {v:.0f} m/s", "climb and descent at 3°"]))
        detour = _air_detour(start, to, zones)
        if detour:
            prof = _air_profile_multi(detour, cruise, v, e.position.altitudeM)
            options.append(_option("avoid", "Route around threat areas", e, prof[0], prof[1], prof[2], zones, warnings,
                                   ["great-circle legs offset 25 km clear of predicted threat corridors"]))
    else:
        raise ValueError(f"no planner for {e.kind}")
    for o in options:
        o["score"] = round(o["etaMin"] * (1 + 2 * o["risk"]), 1)
    rec = min(options, key=lambda o: (not o["feasible"], o["score"]))["id"]
    return {"entityId": e.id, "from": [start[0], start[1]], "to": [to[0], to[1]], "options": options, "recommended": rec,
            "method": "score = ETA × (1 + 2 × risk); risk = threat exposure / 20 km + 0.15 per weather warning + 0.4 if fuel reserve is breached"}


def _road_speeds(coords: list[tuple[float, float]], duration_s: float, cap: float) -> list[float]:
    total = _length(coords)
    avg = min(cap, total / max(duration_s, 1))
    return [avg] * max(1, len(coords) - 1)


def _air_profile(a, b, cruise, v, alt0):
    d = geo.haversine_m(a, b)
    climb = min(d * 0.3, cruise / math.tan(math.radians(3)))
    n = max(4, int(d // 20_000))
    coords, alts = [], []
    for k in range(n + 1):
        f = k / n
        p = geo.interpolate(a, b, f)
        s = d * f
        alt = min(cruise, (alt0 or 0) + s * math.tan(math.radians(3)), (d - s) * math.tan(math.radians(3)) + 50)
        coords.append(p)
        alts.append(max(alt, 30.0))
    _ = climb
    return coords, alts, [v] * n


def _air_detour(a, b, zones) -> list[tuple[float, float]] | None:
    blocked = [z for z in zones if any(_inside(geo.interpolate(a, b, f / 20), z["ring"]) for f in range(21))]
    if not blocked:
        return None
    pts = [a]
    for z in blocked:
        ring = z["ring"]
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        radius = max(geo.haversine_m((cx, cy), p) for p in ring) + 25_000
        side = 90 if geo.wrap_heading_delta(geo.bearing_deg(a, b), geo.bearing_deg(a, (cx, cy))) < 0 else -90
        pts.append(geo.destination((cx, cy), geo.bearing_deg(a, b) + side, radius))
    pts.append(b)
    return pts


def _air_profile_multi(wps, cruise, v, alt0):
    coords, alts, speeds = [], [], []
    total = sum(geo.haversine_m(x, y) for x, y in zip(wps, wps[1:]))
    done = 0.0
    for i, (x, y) in enumerate(zip(wps, wps[1:])):
        leg = geo.haversine_m(x, y)
        n = max(2, int(leg // 20_000))
        for k in range(0 if i == 0 else 1, n + 1):
            p = geo.interpolate(x, y, k / n)
            s = done + leg * k / n
            alt = min(cruise, (alt0 or 0) + s * math.tan(math.radians(3)), (total - s) * math.tan(math.radians(3)) + 50)
            coords.append(p)
            alts.append(max(alt, 30.0))
        done += leg
    return coords, alts, [v] * (len(coords) - 1)
