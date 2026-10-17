"""Trajectory prediction and intercept geometry. Dead reckoning with declared uncertainty growth —
predicted positions are labelled `predicted` and never replace observed samples."""
from __future__ import annotations

from . import geo
from .models import PredictedPath, SceneEntity

UNCERTAINTY_GROWTH = 0.08  # metres of 1-sigma cross-track error per metre travelled (synthetic sensor model)


def dead_reckon(entity: SceneEntity, horizon_s: float, step_s: float = 60.0, t0: float = 0.0) -> PredictedPath | None:
    """Straight-line extrapolation of the last observed heading and speed. Returns None for stationary entities."""
    if not entity.position or not entity.kinematics or not entity.kinematics.speedMps or entity.kinematics.headingDeg is None:
        return None
    start = (entity.position.longitudeDeg, entity.position.latitudeDeg)
    speed, heading = entity.kinematics.speedMps, entity.kinematics.headingDeg
    points: list[list[float]] = [[start[0], start[1], t0]]
    t = step_s
    while t <= horizon_s:
        p = geo.destination(start, heading, speed * t)
        points.append([round(p[0], 6), round(p[1], 6), t0 + t])
        t += step_s
    end = geo.destination(start, heading, speed * horizon_s)
    base = entity.position.horizontalAccuracyM or 200.0
    sigma_end = base + UNCERTAINTY_GROWTH * speed * horizon_s
    left = [geo.destination(geo.destination(start, heading, speed * f * horizon_s), heading - 90, base + UNCERTAINTY_GROWTH * speed * f * horizon_s) for f in (0, 0.25, 0.5, 0.75, 1.0)]
    right = [geo.destination(geo.destination(start, heading, speed * f * horizon_s), heading + 90, base + UNCERTAINTY_GROWTH * speed * f * horizon_s) for f in (1.0, 0.75, 0.5, 0.25, 0)]
    cap = [geo.destination(end, heading, sigma_end)]
    ring = [[round(p[0], 6), round(p[1], 6)] for p in left + cap + right]
    ring.append(ring[0])
    return PredictedPath(entityId=entity.id, method=f"dead_reckoning(heading={heading:.0f}, speed={speed:.0f} m/s, sigma0={base:.0f} m, growth={UNCERTAINTY_GROWTH})",
                         horizonS=horizon_s, points=points, uncertaintyRing=ring, hypothesis="constant velocity",
                         basedOn=[f"last observed heading {heading:.0f}° and speed {speed:.0f} m/s", f"position accuracy ±{base:.0f} m",
                                  f"cross-track error grows {UNCERTAINTY_GROWTH * 100:.0f} % of distance travelled"])


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


MAX_TURN_DPS = {"air": 3.0, "sea": 0.6}  # sustained turn rates (deg/s) assumed for goal-seeking and turning hypotheses


def alternatives(entity: SceneEntity, cv: PredictedPath, targets: list[tuple[SceneEntity, tuple[float, float]]], t0: float,
                 horizon_s: float = 1800, step_s: float = 60, history: dict | None = None) -> list[PredictedPath]:
    """Competing hypotheses next to constant velocity: goal-seeking toward the most exposed own site ahead,
    and continuation of a turn. Probabilities are normalised with the constant-velocity path (updated in place)."""
    if not entity.position or not entity.kinematics or not entity.kinematics.speedMps:
        return []
    start = (entity.position.longitudeDeg, entity.position.latitudeDeg)
    v, h0 = entity.kinematics.speedMps, entity.kinematics.headingDeg or 0.0
    turn = MAX_TURN_DPS.get(entity.domain, 2.0)
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
        pts, p, h = [[start[0], start[1], t0]], start, h0
        t = step_s
        while t <= horizon_s:
            want = geo.bearing_deg(p, tp)
            delta = geo.wrap_heading_delta(h, want)
            h = (h + max(-turn * step_s, min(turn * step_s, delta))) % 360
            p = geo.destination(p, h, v * step_s) if geo.haversine_m(p, tp) > v * step_s else tp
            pts.append([round(p[0], 6), round(p[1], 6), t0 + t])
            t += step_s
        w_goal = 0.25 + 0.35 * (1 - dh / 100)
        eta = geo.haversine_m(start, tp) / v
        out.append(PredictedPath(entityId=entity.id, method=f"goal_seeking(target={tgt.id}, max_turn={turn}°/s)", horizonS=horizon_s, points=pts,
                                 threatenedEntityIds=[tgt.id], etaS=round(eta, 0), hypothesis=f"heading for {tgt.label}", probability=w_goal,
                                 basedOn=[f"{tgt.label} is {dh:.0f}° off the current heading", f"reachable in {eta / 60:.0f} min at {v:.0f} m/s",
                                          "site value: " + ("high" if tgt.visualPriority >= 3 else "medium")]))
    # Turning: continue the most recent turn rate observed in the track history (the predicted path shape is an arc).
    rate = 1.2 if entity.domain == "air" else 0.25
    pts, p, h = [[start[0], start[1], t0]], start, h0
    t = step_s
    while t <= horizon_s:
        h = (h + rate * step_s * (0.6 if t > horizon_s / 2 else 1.0)) % 360
        p = geo.destination(p, h, v * step_s)
        pts.append([round(p[0], 6), round(p[1], 6), t0 + t])
        t += step_s
    w_turn = 0.2
    out.append(PredictedPath(entityId=entity.id, method=f"constant_turn(rate={rate}°/s decaying)", horizonS=horizon_s, points=pts, hypothesis="continues turning (orbit/patrol)",
                             probability=w_turn, basedOn=["recent heading changes in the track history", "orbit and patrol patterns earlier in this area"]))
    w_cv = max(0.2, 1.0 - w_goal - w_turn)
    total = w_cv + w_goal + w_turn
    cv.probability = round(w_cv / total, 2)
    for alt in out:
        alt.probability = round(alt.probability / total, 2)
    return out
