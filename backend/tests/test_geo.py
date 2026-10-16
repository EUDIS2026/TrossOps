import math

from app import geo


def test_haversine_known_distance():
    # Stockholm → Göteborg ≈ 398 km great-circle
    d = geo.haversine_m((18.07, 59.33), (11.97, 57.71))
    assert 390_000 < d < 405_000


def test_destination_roundtrip():
    start = (17.0, 60.0)
    end = geo.destination(start, 45, 50_000)
    assert abs(geo.haversine_m(start, end) - 50_000) < 5
    assert abs(geo.bearing_deg(start, end) - 45) < 0.5


def test_interpolate_endpoints_and_midpoint():
    a, b = (10.0, 55.0), (20.0, 65.0)
    assert geo.interpolate(a, b, 0) == a and geo.interpolate(a, b, 1) == b
    mid = geo.interpolate(a, b, 0.5)
    assert abs(geo.haversine_m(a, mid) - geo.haversine_m(mid, b)) < 10


def test_heading_wrap():
    assert geo.wrap_heading_delta(350, 10) == 20
    assert geo.wrap_heading_delta(10, 350) == -20
    assert geo.wrap_heading_delta(0, 180) == 180


def test_point_in_ring_and_grid():
    ring = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    assert geo.point_in_ring((0.5, 0.5), ring) and not geo.point_in_ring((1.5, 0.5), ring)
    key = geo.grid_key((17.26, 59.31), 0.5)
    assert key == (34, 118)
    assert geo.grid_center(key, 0.5) == (17.25, 59.25)
    assert math.isclose(geo.haversine_m(geo.circle_ring((17, 59), 1000)[0], (17, 59)), 1000, rel_tol=1e-3)
