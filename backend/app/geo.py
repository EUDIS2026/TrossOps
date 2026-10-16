"""Geodesic helpers on a WGS84 sphere approximation. Units are stated on every function.
Coordinates are always [longitude, latitude] in degrees (EPSG:4326)."""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8

LngLat = tuple[float, float]


def haversine_m(a: LngLat, b: LngLat) -> float:
    """Great-circle distance in metres."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def bearing_deg(a: LngLat, b: LngLat) -> float:
    """Initial true bearing in degrees [0, 360) from a to b."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination(a: LngLat, bearing: float, distance_m: float) -> LngLat:
    """Point reached from a after distance_m metres along a true bearing in degrees."""
    lat1, lon1, brg = math.radians(a[1]), math.radians(a[0]), math.radians(bearing)
    d = distance_m / EARTH_RADIUS_M
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return (((math.degrees(lon2) + 540) % 360) - 180, math.degrees(lat2))


def interpolate(a: LngLat, b: LngLat, f: float) -> LngLat:
    """Point at fraction f in [0, 1] along the great circle from a to b."""
    if f <= 0:
        return a
    if f >= 1:
        return b
    d = haversine_m(a, b)
    if d < 1e-6:
        return a
    return destination(a, bearing_deg(a, b), d * f)


def wrap_heading_delta(from_deg: float, to_deg: float) -> float:
    """Signed shortest rotation from one heading to another, in (-180, 180]."""
    delta = (to_deg - from_deg + 180) % 360 - 180
    return 180.0 if delta == -180 else delta


def point_in_ring(point: LngLat, ring: list[LngLat]) -> bool:
    """Ray-casting containment test on a lng/lat ring (adequate for operational areas)."""
    x, y = point
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def circle_ring(center: LngLat, radius_m: float, steps: int = 48) -> list[LngLat]:
    """Geodesic circle as a closed ring (first point repeated)."""
    ring = [destination(center, 360 * i / steps, radius_m) for i in range(steps)]
    ring.append(ring[0])
    return ring


def grid_key(point: LngLat, cell_deg: float) -> tuple[int, int]:
    """Equirectangular cell key with cell_deg degree edges (attention aggregation grid)."""
    return (math.floor(point[0] / cell_deg), math.floor(point[1] / cell_deg))


def grid_center(key: tuple[int, int], cell_deg: float) -> LngLat:
    return ((key[0] + 0.5) * cell_deg, (key[1] + 0.5) * cell_deg)


def grid_ring(key: tuple[int, int], cell_deg: float) -> list[LngLat]:
    x, y = key
    return [
        (x * cell_deg, y * cell_deg),
        ((x + 1) * cell_deg, y * cell_deg),
        ((x + 1) * cell_deg, (y + 1) * cell_deg),
        (x * cell_deg, (y + 1) * cell_deg),
        (x * cell_deg, y * cell_deg),
    ]
