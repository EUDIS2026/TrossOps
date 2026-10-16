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
                         horizonS=horizon_s, points=points, uncertaintyRing=ring)


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
