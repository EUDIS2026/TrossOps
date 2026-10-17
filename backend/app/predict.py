"""Trajectory prediction and intercept geometry. Dead reckoning with declared uncertainty growth —
predicted positions are labelled `predicted` and never replace observed samples.

Every hypothesis respects the ground it moves over:
- air tracks fly straight lines and arcs;
- surface tracks stay in navigable water (`geonet.sea()` mask): a step that would cross land is deflected by the
  smallest turn that keeps the hull wet (coast following), or the track holds when no turn up to 90° works;
  goal-seeking toward a coastal site follows a sea route (`geonet.sea().route`);
- ground tracks follow the national road graph (`geonet.national()`): at each junction the branch closest to the
  current heading is taken; goal-seeking follows the fastest road route.
Each path's `basedOn` says which constraint shaped it. No learned model is involved.
"""
from __future__ import annotations

import math
from collections import OrderedDict

from . import geo
from .models import PredictedPath, SceneEntity

UNCERTAINTY_GROWTH = 0.08  # metres of 1-sigma cross-track error per metre travelled (synthetic sensor model)
ROAD_UNCERTAINTY_GROWTH = 0.03  # on a road the track cannot drift sideways; the corridor only widens for along-track/branch error
DEFLECT_STEPS = (10, 20, 30, 45, 60, 75, 90)  # degrees tried either side when the next step would leave the water
ROAD_SNAP_M = 2_000.0  # a ground track further than this from any road is predicted cross-country (unconstrained)
MAX_BRANCH_TURN = 100.0  # at a junction, branches more than this off the current heading are not a continuation


# ---- terrain ------------------------------------------------------------------------------------
def _sea():
    try:
        from . import geonet  # noqa: PLC0415  (heavy data, loaded on first use)
        return geonet.sea()
    except (OSError, ValueError, ImportError):
        return None


def _roads():
    try:
        from . import geonet  # noqa: PLC0415
        return geonet.national()
    except (OSError, ValueError, ImportError):
        return None


def water_check(entity: SceneEntity):
    """`ok(p)` for a surface track whose current position is on the sea mask, else None (unconstrained)."""
    if entity.domain != "sea" or not entity.position:
        return None
    sea = _sea()
    if sea is None:
        return None
    start = (entity.position.longitudeDeg, entity.position.latitudeDeg)
    if not sea.is_water(start):
        return None  # in a harbour cell finer than the mask, or outside it: do not invent a constraint
    return sea.is_water


def _step(p, h, dist, ok):
    """Next point from p on heading h, deflected toward the original heading's nearest wet bearing. (point, heading, deflection)."""
    q = geo.destination(p, h, dist)
    if ok is None or (ok(q) and ok(geo.interpolate(p, q, 0.5))):
        return q, h, 0.0
    for d in DEFLECT_STEPS:
        for sgn in (1, -1):
            h2 = (h + sgn * d) % 360
            q2 = geo.destination(p, h2, dist)
            if ok(q2) and ok(geo.interpolate(p, q2, 0.5)):
                return q2, h2, sgn * d
    return None, h, 0.0


def _walk(start, h0, v, horizon_s, step_s, t0, ok, steer=None):
    """Time-stepped walk. `steer(p, h, t)` returns the wanted heading (default: hold). Returns (points, notes)."""
    pts = [[start[0], start[1], t0]]
    p, h = start, h0
    deflected, held_at = 0, None
    t = step_s
    while t <= horizon_s + 1e-9:
        want = steer(p, h, t) if steer else h
        q, h_new, dev = _step(p, want, v * step_s, ok)
        if q is None:
            held_at = held_at if held_at is not None else t
            q = p  # no wet way forward: the vessel has to stop or turn back; hold position as the conservative estimate
        else:
            if dev:
                deflected += 1
            h = h_new
        p = q
        pts.append([round(p[0], 6), round(p[1], 6), t0 + t])
        t += step_s
    notes = []
    if ok is not None:
        notes.append("kept in navigable water (sea mask, ~280 m)" + (f"; deflected along the coast on {deflected} of {len(pts) - 1} steps" if deflected else ""))
        if held_at is not None:
            notes.append(f"no navigable continuation after {held_at / 60:.0f} min: held at the last wet position")
    return pts, notes


def _road_polyline(net, start, h0, length_m):
    """Greedy road continuation from the nearest node: at each junction take the branch closest to the current heading."""
    n, snap = net.nearest_node(start)
    if snap > ROAD_SNAP_M:
        return None, snap
    coords = [start, net.node(n)]
    came_from = None
    h = h0  # joining the road: branch choice follows the track's own heading, not the access leg's bearing
    run = geo.haversine_m(start, net.node(n))
    visited = {n}
    while run < length_m:
        best = None
        for nb, ei in net.adj[n]:
            if came_from is not None and nb == came_from:
                continue
            pts = net.edge_coords(ei)
            if len(pts) < 2:
                continue
            b = geo.bearing_deg(pts[0], pts[1] if geo.haversine_m(pts[0], pts[1]) > 5 else pts[-1])
            dev = abs(geo.wrap_heading_delta(h, b))
            if dev <= MAX_BRANCH_TURN and (best is None or dev < best[0]):
                best = (dev, nb, pts)
        if best is None:
            break
        _dev, nb, pts = best
        for a, b in zip(pts, pts[1:]):
            coords.append(b)
            run += geo.haversine_m(a, b)
        if len(pts) >= 2:
            h = geo.bearing_deg(pts[-2], pts[-1])
        came_from, n = n, nb
        if n in visited:
            break
        visited.add(n)
    return coords, snap


def _resample(coords, v, horizon_s, step_s, t0):
    """Points every step_s along a polyline at speed v (holding at the end if the polyline is shorter)."""
    cum = [0.0]
    for a, b in zip(coords, coords[1:]):
        cum.append(cum[-1] + geo.haversine_m(a, b))
    out = [[coords[0][0], coords[0][1], t0]]
    k = 0
    t = step_s
    while t <= horizon_s + 1e-9:
        s = min(v * t, cum[-1])
        while k < len(cum) - 2 and cum[k + 1] < s:
            k += 1
        seg = cum[k + 1] - cum[k] if k + 1 < len(cum) else 0
        f = (s - cum[k]) / seg if seg > 0 else 0.0
        p = geo.interpolate(coords[k], coords[min(k + 1, len(coords) - 1)], f)
        out.append([round(p[0], 6), round(p[1], 6), t0 + t])
        t += step_s
    return out, cum[-1]


def _corridor(points: list[list[float]], base: float, growth: float) -> list[list[float]]:
    """Uncertainty ring that follows the (possibly curved) path: ±σ(d) perpendicular to the local direction, with
    σ(d) = base + growth × distance travelled, and a cap of σ ahead of the end."""
    pp = [(p[0], p[1]) for p in points]
    if len(pp) < 2:
        return []
    dist = [0.0]
    for a, b in zip(pp, pp[1:]):
        dist.append(dist[-1] + geo.haversine_m(a, b))
    idx = sorted(set(list(range(0, len(pp), max(1, len(pp) // 10))) + [len(pp) - 1]))
    left, right = [], []
    for k in idx:
        a, b = pp[max(0, k - 1)], pp[min(len(pp) - 1, k + 1)]
        brg = geo.bearing_deg(a, b) if geo.haversine_m(a, b) > 1 else (geo.bearing_deg(pp[0], pp[-1]) if geo.haversine_m(pp[0], pp[-1]) > 1 else 0.0)
        s = base + growth * dist[k]
        left.append(geo.destination(pp[k], brg - 90, s))
        right.append(geo.destination(pp[k], brg + 90, s))
    end_brg = geo.bearing_deg(pp[idx[-2]], pp[-1]) if len(idx) > 1 and geo.haversine_m(pp[idx[-2]], pp[-1]) > 1 else 0.0
    cap = [geo.destination(pp[-1], end_brg, base + growth * dist[-1])]
    ring = [[round(p[0], 6), round(p[1], 6)] for p in left + cap + list(reversed(right))]
    ring.append(ring[0])
    return ring


# ---- constant velocity ----------------------------------------------------------------------------
def dead_reckon(entity: SceneEntity, horizon_s: float, step_s: float = 60.0, t0: float = 0.0) -> PredictedPath | None:
    """Extrapolation of the last observed heading and speed, constrained by terrain (see module doc). Returns None for
    stationary entities."""
    if not entity.position or not entity.kinematics or not entity.kinematics.speedMps or entity.kinematics.headingDeg is None:
        return None
    start = (entity.position.longitudeDeg, entity.position.latitudeDeg)
    speed, heading = entity.kinematics.speedMps, entity.kinematics.headingDeg
    base = entity.position.horizontalAccuracyM or 200.0
    based = [f"last observed heading {heading:.0f}° and speed {speed:.0f} m/s", f"position accuracy ±{base:.0f} m"]
    growth = UNCERTAINTY_GROWTH
    method = f"dead_reckoning(heading={heading:.0f}, speed={speed:.0f} m/s, sigma0={base:.0f} m, growth={UNCERTAINTY_GROWTH})"
    points = None
    if entity.domain == "land":
        net = _roads()
        if net is not None:
            coords, snap = _road_polyline(net, start, heading, speed * horizon_s)
            if coords is not None and len(coords) > 2:
                points, _length = _resample(coords, speed, horizon_s, step_s, t0)
                growth = ROAD_UNCERTAINTY_GROWTH
                method = f"road_following(speed={speed:.0f} m/s, branch=closest to heading, sigma0={base:.0f} m, growth={growth})"
                based.append(f"follows the national road graph from the nearest road ({snap:.0f} m away), taking the branch closest to the current heading at each junction")
            else:
                based.append(f"no road within {ROAD_SNAP_M / 1000:.0f} km: cross-country straight line")
    if points is None:
        ok = water_check(entity)
        points, notes = _walk(start, heading, speed, horizon_s, step_s, t0, ok)
        based.extend(notes)
        if ok is not None:
            method = f"dead_reckoning_sea(heading={heading:.0f}, speed={speed:.0f} m/s, sigma0={base:.0f} m, growth={UNCERTAINTY_GROWTH}, coast-following)"
    based.append(f"cross-track error grows {growth * 100:.0f} % of distance travelled")
    return PredictedPath(entityId=entity.id, method=method, horizonS=horizon_s, points=points, uncertaintyRing=_corridor(points, base, growth),
                         hypothesis="constant velocity", basedOn=based)


def closest_approach(path: PredictedPath, target: tuple[float, float]) -> tuple[float, float]:
    """(minimum distance in metres, time offset in seconds) between the predicted path and a fixed target."""
    best = (float("inf"), 0.0)
    for lng, lat, t in path.points:
        d = geo.haversine_m((lng, lat), target)
        if d < best[0]:
            best = (d, t - path.points[0][2])
    return best


def intercept_time_s(interceptor: tuple[float, float], interceptor_speed: float, path: PredictedPath) -> tuple[float, list[float]] | None:
    """Earliest point on the predicted path the interceptor can reach before the track does (first feasible sample)."""
    if interceptor_speed <= 0:
        return None
    t0 = path.points[0][2]
    for lng, lat, t in path.points:
        travel = geo.haversine_m(interceptor, (lng, lat)) / interceptor_speed
        if travel <= (t - t0) + 1e-6:
            return (max(travel, t - t0), [lng, lat, t])
    return None


# ---- competing hypotheses --------------------------------------------------------------------------
MAX_TURN_DPS = {"air": 3.0, "sea": 0.6, "land": 2.0}  # sustained turn rates (deg/s) assumed for goal-seeking and turning hypotheses
STANDARD_TURN_DPS = {"air": 1.2, "sea": 0.25, "land": 0.5}  # turn rate assumed when the track history shows no turn
_ROUTE_CACHE: OrderedDict = OrderedDict()


def _cached_route(kind: str, start, target_id: str, target, fn):
    key = (kind, round(start[0], 2), round(start[1], 2), target_id)
    if key in _ROUTE_CACHE:
        _ROUTE_CACHE.move_to_end(key)
        return _ROUTE_CACHE[key]
    try:
        r = fn()
    except Exception:  # noqa: BLE001  routing is an enhancement; the hypothesis falls back to the open-water/straight walk
        r = None
    _ROUTE_CACHE[key] = r
    if len(_ROUTE_CACHE) > 256:
        _ROUTE_CACHE.popitem(last=False)
    return r


def observed_turn_rate(entity: SceneEntity, history: dict | None) -> float | None:
    """Signed turn rate (deg/s, + = right) between the history sample and now; None without history."""
    if not history or not entity.kinematics or entity.kinematics.headingDeg is None or history.get("headingDeg") is None or not history.get("dtS"):
        return None
    return geo.wrap_heading_delta(history["headingDeg"], entity.kinematics.headingDeg) / history["dtS"]


def alternatives(entity: SceneEntity, cv: PredictedPath, targets: list[tuple[SceneEntity, tuple[float, float]]], t0: float,
                 horizon_s: float = 1800, step_s: float = 60, history: dict | None = None) -> list[PredictedPath]:
    """Competing hypotheses next to constant velocity: goal-seeking toward the most exposed own site ahead, and
    continuation of the turn observed in the track history. Probabilities are normalised with the constant-velocity
    path (updated in place). Surface tracks stay in water, ground tracks on roads (see module doc)."""
    if not entity.position or not entity.kinematics or not entity.kinematics.speedMps:
        return []
    start = (entity.position.longitudeDeg, entity.position.latitudeDeg)
    v, h0 = entity.kinematics.speedMps, entity.kinematics.headingDeg or 0.0
    turn = MAX_TURN_DPS.get(entity.domain, 2.0)
    ok = water_check(entity)
    out: list[PredictedPath] = []
    # Goal-seeking: the own site that needs the least heading change, weighted by distance, within reach.
    best = None
    for tgt, tp in targets:
        d = geo.haversine_m(start, tp)
        if d > v * horizon_s or d < 2000:
            continue
        dh = abs(geo.wrap_heading_delta(h0, geo.bearing_deg(start, tp)))
        if dh > 100:
            continue
        score = (1 - dh / 100) * (1 - d / (v * horizon_s)) * (1.5 if tgt.visualPriority >= 3 else 1.0)
        if best is None or score > best[0]:
            best = (score, tgt, tp, dh)
    w_goal = 0.0
    if best:
        _, tgt, tp, dh = best
        pts, eta, how = None, None, []
        if ok is not None:
            sea = _sea()
            route = _cached_route("sea", start, tgt.id, tp, lambda: sea.route(start, tp)) if sea is not None else None
            if route is not None:
                coords = [c for c in route.coords if ok(c)] or [start]
                coords = [start] + coords
                pts, length = _resample(coords, v, horizon_s, step_s, t0)
                eta = length / v
                how = [f"sea route to the water nearest {tgt.label} ({length / 1000:.0f} km)"]
        elif entity.domain == "land" and _roads() is not None:
            net = _roads()
            route = _cached_route("road", start, tgt.id, tp, lambda: net.route(start, tp))
            if route is not None:
                pts, length = _resample(list(route.coords), v, horizon_s, step_s, t0)
                eta = length / v
                how = [f"fastest road route to {tgt.label} ({length / 1000:.0f} km)"]
        if pts is None:
            def steer(p, h, _t):
                want = geo.bearing_deg(p, tp)
                delta = geo.wrap_heading_delta(h, want)
                return (h + max(-turn * step_s, min(turn * step_s, delta))) % 360
            if geo.haversine_m(start, tp) > 0:
                pts, notes = _walk(start, h0, v, horizon_s, step_s, t0, ok, steer)
                # stop at the target rather than orbiting it
                for k, q in enumerate(pts):
                    if geo.haversine_m((q[0], q[1]), tp) <= v * step_s:
                        pts = pts[:k + 1] + [[q[0], q[1], r[2]] for r in pts[k + 1:]]
                        break
                eta = geo.haversine_m(start, tp) / v
                how = [f"turns toward {tgt.label} at up to {turn}°/s"] + notes
        if pts is not None:
            w_goal = 0.25 + 0.35 * (1 - dh / 100)
            out.append(PredictedPath(entityId=entity.id, method=f"goal_seeking(target={tgt.id}, max_turn={turn}°/s)", horizonS=horizon_s, points=pts,
                                     threatenedEntityIds=[tgt.id], etaS=round(eta or 0, 0), hypothesis=f"heading for {tgt.label}", probability=w_goal,
                                     basedOn=[f"{tgt.label} is {dh:.0f}° off the current heading", f"reachable in {(eta or 0) / 60:.0f} min at {v:.0f} m/s",
                                              "site value: " + ("high" if tgt.visualPriority >= 3 else "medium")] + how))
    # Turning: continue the turn rate observed in the track history, decaying in the second half of the horizon.
    rate_obs = observed_turn_rate(entity, history)
    std = STANDARD_TURN_DPS.get(entity.domain, 1.0)
    if rate_obs is not None and abs(rate_obs) >= 0.05 * std:
        rate = max(-turn, min(turn, rate_obs))
        why = f"observed turn {rate_obs:+.2f}°/s over the last {history['dtS']:.0f} s of the track history (+ = right)"  # type: ignore[index]
        w_turn = min(0.5, 0.1 + 0.4 * abs(rate) / std)
    else:
        rate = std
        why = ("no turn in the last " + f"{history['dtS']:.0f} s of the track history" if history else "no track history available") + \
              f"; standard rate {std}°/s to the right assumed"
        w_turn = 0.1
    if entity.domain == "land" and _roads() is not None and cv.method.startswith("road_following"):
        # On a road network a "turn" is a different branch: take the junction choice furthest from straight ahead on the turn side.
        net = _roads()
        coords, _snap = _road_polyline(net, start, (h0 + math.copysign(60, rate)) % 360, v * horizon_s)
        if coords is not None and len(coords) > 2:
            pts, _len = _resample(coords, v, horizon_s, step_s, t0)
            why += "; on roads: the branch nearest 60° to the turn side at each junction"
        else:
            pts = cv.points
    else:
        def steer_turn(p, h, t):
            return (h + rate * step_s * (0.6 if t > horizon_s / 2 else 1.0)) % 360
        pts, notes = _walk(start, h0, v, horizon_s, step_s, t0, ok, steer_turn)
        if notes:
            why += "; " + "; ".join(notes)
    out.append(PredictedPath(entityId=entity.id, method=f"constant_turn(rate={rate:+.2f}°/s decaying)", horizonS=horizon_s, points=pts, hypothesis="continues turning (orbit/patrol)",
                             probability=w_turn, basedOn=[why, "rate decays to 60 % after half the horizon"]))
    w_cv = max(0.2, 1.0 - w_goal - w_turn)
    total = w_cv + w_goal + w_turn
    cv.probability = round(w_cv / total, 2)
    cv.basedOn = list(cv.basedOn) + [f"weight {w_cv:.2f} before normalisation (1 − goal − turn weights, at least 0.2)"]
    for alt in out:
        alt.probability = round(alt.probability / total, 2)
    return out
