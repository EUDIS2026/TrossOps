"""Road and sea routing over the committed geonet artefacts (backend/data/geo)."""
import json
import math
from pathlib import Path

import pytest

from app import geonet
from app.geonet import haversine_m

SWEDEN_BBOX = (10.5, 55.0, 24.5, 69.5)
COUNTIES = Path(__file__).resolve().parents[2] / "frontend" / "public" / "data" / "sweden_counties.geojson"

STOCKHOLM = (18.07, 59.33)
UPPSALA = (17.64, 59.86)
MALMO = (13.00, 55.60)
GOTEBORG = (11.97, 57.71)
KIRUNA = (20.22, 67.86)
KARLSKRONA = (15.59, 56.16)
VISBY = (18.29, 57.64)


def _in_ring(p, ring):
    x, y = p
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        (xi, yi), (xj, yj) = ring[i], ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _county_polygons():
    doc = json.loads(COUNTIES.read_text(encoding="utf-8"))
    polys = []
    for f in doc["features"]:
        g = f["geometry"]
        for poly in g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]:
            polys.append([[tuple(c) for c in ring] for ring in poly])
    return polys


def _on_land(p, polys, margin_m=1500.0):
    """p and four points margin_m around it all lie inside one (coarse, SCB) land polygon:
    i.e. clearly on land, not merely in a strait the simplified coastline bleeds into."""
    dy = margin_m / 111_195.0
    dx = dy / math.cos(math.radians(p[1]))
    probe = [p, (p[0] + dx, p[1]), (p[0] - dx, p[1]), (p[0], p[1] + dy), (p[0], p[1] - dy)]
    for poly in polys:
        if all(_in_ring(q, poly[0]) and not any(_in_ring(q, hole) for hole in poly[1:]) for q in probe):
            return True
    return False


def _samples(coords, step_m=500.0):
    """(point, distance from start) every step_m along the polyline (linear in lng/lat)."""
    out = [(coords[0], 0.0)]
    run = 0.0
    nxt = step_m
    for a, b in zip(coords, coords[1:]):
        d = haversine_m(a, b)
        while d > 0 and nxt <= run + d:
            f = (nxt - run) / d
            out.append(((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), nxt))
            nxt += step_m
        run += d
    out.append((coords[-1], run))
    return out, run


def _assert_polyline(route, max_gap_m=3000.0):
    for a, b in zip(route.coords, route.coords[1:]):
        assert haversine_m(a, b) <= max_gap_m


# --- roads -------------------------------------------------------------------------------

def test_stockholm_uppsala_road_route():
    r = geonet.national().route(STOCKHOLM, UPPSALA)
    assert r is not None
    assert 60_000 <= r.length_m <= 95_000
    assert 0.5 * 3600 <= r.duration_s <= 1.6 * 3600  # 60-95 km at convoy speeds
    assert sum(r.classes_m.values()) == pytest.approx(r.length_m, rel=0.01)
    assert r.coords[0] == STOCKHOLM and r.coords[-1] == UPPSALA
    lo_x, lo_y, hi_x, hi_y = SWEDEN_BBOX
    assert all(lo_x <= x <= hi_x and lo_y <= y <= hi_y for x, y in r.coords)
    _assert_polyline(r)
    # the polyline length matches the reported length (shape geometry is complete)
    assert sum(haversine_m(a, b) for a, b in zip(r.coords, r.coords[1:])) == pytest.approx(r.length_m, rel=0.01)


def test_long_routes_exist():
    n = geonet.national()
    r1 = n.route(MALMO, GOTEBORG)
    assert r1 is not None and 230_000 <= r1.length_m <= 340_000
    r2 = n.route(MALMO, KIRUNA)
    assert r2 is not None
    assert 1_500_000 <= r2.length_m <= 2_100_000
    assert r2.classes_m.get("motorway", 0) + r2.classes_m.get("trunk", 0) > 0.5 * r2.length_m
    _assert_polyline(r2)


def test_speed_cap_and_avoid():
    n = geonet.national()
    fast = n.route(STOCKHOLM, UPPSALA)
    slow = n.route(STOCKHOLM, UPPSALA, max_speed_mps=10.0)
    assert slow.duration_s >= fast.length_m / 10.0 * 0.95
    assert slow.duration_s > fast.duration_s
    # block a box around the middle of the fastest route: the detour must leave it
    mid = fast.coords[len(fast.coords) // 2]
    box = [(mid[0] - 0.05, mid[1] - 0.03), (mid[0] + 0.05, mid[1] - 0.03),
           (mid[0] + 0.05, mid[1] + 0.03), (mid[0] - 0.05, mid[1] + 0.03)]
    det = n.route(STOCKHOLM, UPPSALA, avoid=[box])
    assert det is not None
    inside = [p for p in det.coords if box[0][0] < p[0] < box[1][0] and box[0][1] < p[1] < box[2][1]]
    assert not inside
    assert det.length_m < 200_000


def test_nearest_node_and_bounds():
    n = geonet.national()
    i, d = n.nearest_node(STOCKHOLM)
    assert 0 <= i and d < 2_000
    x0, y0, x1, y1 = n.bounds()
    assert x0 < 12 and x1 > 23 and y0 < 56 and y1 > 68


def test_city_graphs():
    names = geonet.cities()
    assert {"stockholm", "goteborg", "malmo", "kiruna", "visby", "karlskrona", "gotland"} <= set(names)
    assert len(names) == 21
    with pytest.raises(KeyError):
        geonet.city("atlantis")
    s = geonet.city("stockholm")
    x0, y0, x1, y1 = s.bounds()
    assert x0 < 18.07 < x1 and y0 < 59.33 < y1
    r = s.route((18.03, 59.34), (18.10, 59.31))
    assert r is not None and 4_000 < r.length_m < 15_000


def test_random_loop_closed_and_deterministic():
    s = geonet.city("stockholm")
    a = s.random_loop(seed=1, start=STOCKHOLM, length_m=8000)
    b = s.random_loop(seed=1, start=STOCKHOLM, length_m=8000)
    c = s.random_loop(seed=2, start=STOCKHOLM, length_m=8000)
    assert a.coords == b.coords and a.length_m == b.length_m
    assert a.coords != c.coords
    assert haversine_m(a.coords[0], a.coords[-1]) < 1.0
    assert 6_000 <= a.length_m <= 14_000
    _assert_polyline(a, 1_100)


def test_nodes_within():
    s = geonet.city("stockholm")
    pts = s.nodes_within(STOCKHOLM, 500)
    assert len(pts) > 20
    dists = [haversine_m(STOCKHOLM, p) for p in pts]
    assert all(d <= 500 for d in dists) and dists == sorted(dists)
    assert pts == s.nodes_within(STOCKHOLM, 500)
    big = geonet.national().nodes_within(STOCKHOLM, 3_000, classes={"motorway", "trunk"})
    assert big and all(haversine_m(STOCKHOLM, p) <= 3_000 for p in big)
    assert len(big) < len(geonet.national().nodes_within(STOCKHOLM, 3_000))


def _nodes_within_bruteforce(net, center, radius_m, classes=None):
    """Reference: every vertex of every edge (the pre-optimisation algorithm, without the cell pre-filter)."""
    want = None if classes is None else {i for i, c in enumerate(net.classes) if c in classes}
    found = {}
    for i in range(len(net.ea)):
        if want is not None and net.ecls[i] not in want:
            continue
        for p in net.edge_coords(i):
            d = haversine_m(center, p)
            if d <= radius_m:
                found[p] = d
    return [p for p, _d in sorted(found.items(), key=lambda kv: (kv[1], kv[0]))]


@pytest.mark.parametrize("name,center,radius,classes", [
    ("national", (14.62, 57.78), 1_500, {"secondary", "tertiary"}),  # an in_field() style query
    ("national", (20.66, 67.13), 6_000, {"secondary", "tertiary"}),  # sparse north: long edges only
    ("national", STOCKHOLM, 4_000, None),
    ("gotland", VISBY, 1_800, {"secondary", "tertiary", "minor"}),
])
def test_nodes_within_matches_bruteforce(name, center, radius, classes):
    net = geonet.national() if name == "national" else geonet.city(name)
    got = net.nodes_within(center, radius, classes)
    assert got == _nodes_within_bruteforce(net, center, radius, classes)


# --- sea ---------------------------------------------------------------------------------

def test_is_water():
    sea = geonet.sea()
    assert sea.is_water((19.5, 58.0))  # open Baltic
    assert not sea.is_water((15.0, 60.0))  # inland Sweden
    assert not sea.is_water((14.5, 58.9))  # lake Vattern is not sea
    assert sea.is_water((11.5, 57.5))  # Kattegat


def _islands(polys):
    """County polygon parts that contain Oland (Borgholm) or Gotland (Visby)."""
    marks = [(16.656, 56.879), (18.45, 57.45)]
    return [p for p in polys if any(_in_ring(m, p[0]) for m in marks)]


def test_sea_route_karlskrona_visby():
    sea = geonet.sea()
    r = sea.route(KARLSKRONA, VISBY)
    assert r is not None and r.snapped
    assert r.coords[0] == KARLSKRONA and r.coords[-1] == VISBY
    assert 150_000 < r.length_m < 320_000
    samples, total = _samples(r.coords)
    islands = _islands(_county_polygons())
    assert len(islands) == 2
    for p, d in samples:
        if 3_000 <= d <= total - 3_000:
            assert sea.is_water(p), p
        if 10_000 <= d <= total - 10_000:
            assert not _on_land(p, islands), p


def test_sea_route_goteborg_stockholm_goes_around_the_south():
    sea = geonet.sea()
    r = sea.route(GOTEBORG, (18.6, 59.2))
    assert r is not None
    assert min(y for _x, y in r.coords) < 55.6
    samples, total = _samples(r.coords)
    polys = _county_polygons()
    for p, d in samples:
        if 3_000 <= d <= total - 3_000:
            assert sea.is_water(p), p
        if 15_000 <= d <= total - 15_000:
            assert not _on_land(p, polys), p
    assert 750_000 < r.length_m < 1_300_000
    assert r.classes_m == {"sea": r.length_m}


def test_sea_route_unreachable_inland():
    assert geonet.sea().route((15.0, 62.0), (19.5, 58.0)) is None


def test_gotland_region_graph():
    g = geonet.city("gotland")
    x0, y0, x1, y1 = g.bounds()
    assert x0 < 18.2 and x1 > 19.2 and y0 < 57.0 and y1 > 57.9  # whole island incl. Faro
    slite = (18.80, 57.71)
    r = g.route(VISBY, slite)
    assert r is not None
    assert 30_000 <= r.length_m <= 55_000
    assert "ferry" not in r.classes_m
    _assert_polyline(r, 1_100)
    # stays on Gotland: inside the island's bbox, mostly inside the (coarse) county polygon,
    # and never out over open water (water all around a sample point)
    assert all(18.05 <= x <= 19.35 and 56.88 <= y <= 57.98 for x, y in r.coords)
    gotland = [p for p in _county_polygons() if _in_ring((18.45, 57.45), p[0])]
    assert len(gotland) == 1
    inside = sum(_in_ring(p, gotland[0][0]) for p in r.coords)
    assert inside >= 0.8 * len(r.coords)
    sea = geonet.sea()
    for p, _d in _samples(r.coords)[0]:
        dy = 1000 / 111_195.0
        dx = dy / math.cos(math.radians(p[1]))
        around = [p, (p[0] + dx, p[1]), (p[0] - dx, p[1]), (p[0], p[1] + dy), (p[0], p[1] - dy)]
        assert not all(sea.is_water(q) for q in around), p
    # Faro is reached over the Farosund ferry
    faro = g.route(VISBY, (19.17, 57.93))
    assert faro is not None and faro.classes_m.get("ferry", 0) > 500
