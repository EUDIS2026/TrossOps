"""Nothing that stands or drives on the ground is on water, and sites are not built on roads.

The world places sites and ground units from declared seeds (town + offset), then moves every one of them through
the land mask (`geonet.land()`: OSM sea, lakes, rivers) and the rasterised road networks. These tests pin the result,
so a new placement that skips that step fails here instead of showing up as a tank in a lake.
"""
import pytest

from app import geo, geonet
from app.sitegen import placement_samples
from app.world import SyntheticWorld

STOCKHOLM_WATER = (18.06, 59.322)  # Riddarfjärden


@pytest.fixture(scope="module")
def world():
    return SyntheticWorld()


@pytest.fixture(scope="module")
def land():
    return geonet.land()


@pytest.fixture(scope="module")
def roads(land):
    cells = set(land.road_cells(geonet.national()))
    for name in geonet.cities():
        cells |= land.road_cells(geonet.city(name))
    return cells


def test_land_mask_knows_lakes_and_towns(land):
    for lake in [(13.5, 58.9), (14.55, 58.3), (14.8, 60.85), (19.5, 68.3), (15.9, 59.25)]:  # Vänern Vättern Siljan Torneträsk Hjälmaren
        assert land.is_water(lake), lake
    for town in [(18.071, 59.325), (17.64, 59.86), (20.22, 67.855), (11.97, 57.705)]:  # Gamla stan Uppsala Kiruna Göteborg
        assert land.is_dry(town), town
    assert land.is_water((19.5, 57.0))  # open Baltic (sea-mask fallback)
    assert "lake" in land.header["water"]["classes"]


def test_sites_stand_on_dry_ground_clear_of_roads(world, land, roads):
    for sid, lay in world.layouts.items():
        dry, wet, sea, core = placement_samples(lay)
        assert not [q for q in dry if land.is_water(q)], f"{sid} footprint on water"
        assert not [q for q in dry if land.cell(q) in roads], f"{sid} fenced over a national road"
        bad = [q for q in core if land.on_any_road(q) or land.cell(q) in roads]
        assert len(bad) <= 0.01 * len(core), f"{sid}: {len(bad)} of {len(core)} built-surface samples on a road"
        assert all(land.is_water(q) for q in wet), f"{sid} berths or pads not in the water"
        assert all(land.sea.is_water(q) for q in sea), f"{sid} channel not in navigable sea"


def test_parked_ground_units_are_on_dry_land(world, land):
    wet = [e.base.id for e in world.entities.values()
           if e.base.domain == "land" and e.motion and e.motion.kind == "static" and land.is_water(e.motion.pos[:2])]
    assert wet == []


def test_ground_paths_cross_water_only_on_roads(world, land, roads):
    """Bridges are fine (a road crosses the water there); a straight leg over a lake or the sea is not."""
    seen, bad = set(), []
    for e in world.entities.values():
        m = e.motion
        if e.base.domain != "land" or not m or m.kind != "path" or m.path is None or id(m.path) in seen:
            continue
        seen.add(id(m.path))
        pts = m.path.pts
        for a, b in zip(pts, pts[1:]):
            n = max(1, int(geo.haversine_m(a[:2], b[:2]) / 50))
            for k in range(n):
                q = (a[0] + (b[0] - a[0]) * (k + 0.5) / n, a[1] + (b[1] - a[1]) * (k + 0.5) / n)
                c = land.cell(q)
                # a bridge: the road raster passes through this cell or an adjacent one (bridge ends clip corners)
                if land.is_water(q) and not any(c + dr * land.w + dc in roads for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                    bad.append((e.base.id, round(q[0], 4), round(q[1], 4)))
                    break
            else:
                continue
            break
    assert bad == []


def test_router_never_drives_a_leg_across_water(land):
    city = geonet.city("stockholm")
    node = city.node(city.nearest_node(STOCKHOLM_WATER)[0])
    r = city.route(STOCKHOLM_WATER, (18.03, 59.34))
    assert r is not None and r.coords[0] == node  # starts at the street node (here a bridge), not in Riddarfjärden
    loop = city.random_loop(seed=3, start=STOCKHOLM_WATER, length_m=6000)
    assert loop.coords[0] == loop.coords[-1] == node
    none = geonet.national().route((18.07, 59.33), (17.64, 59.86), access="none")
    n0 = geonet.national().nearest_node((18.07, 59.33))[0]
    assert none.coords[0] == geonet.national().node(n0)


def _deep_dry(land, q):
    """Dry land with no water in the surrounding cells (tolerates ~110 m coastline quantisation)."""
    c = land.cell(q)
    if c < 0 or land.sea.is_water(q):
        return False
    return not any((land.water[(c + dr * land.w + dc) >> 3] >> ((c + dr * land.w + dc) & 7)) & 1 for dr in (-1, 0, 1) for dc in (-1, 0, 1))


def test_ships_stay_in_the_water(world, land):
    parked = [e.base.id for e in world.entities.values()
              if e.base.domain == "sea" and e.motion and e.motion.kind == "static" and land.is_dry(e.motion.pos[:2])]
    assert parked == []
    seen, over_land = set(), []
    for e in world.entities.values():
        m = e.motion
        if e.base.domain != "sea" or not m or m.kind != "path" or m.path is None or id(m.path) in seen:
            continue
        seen.add(id(m.path))
        for a, b in zip(m.path.pts, m.path.pts[1:]):
            n = max(1, int(geo.haversine_m(a[:2], b[:2]) / 100))
            if any(_deep_dry(land, (a[0] + (b[0] - a[0]) * (k + 0.5) / n, a[1] + (b[1] - a[1]) * (k + 0.5) / n)) for k in range(n)):
                over_land.append(e.base.id)
                break
    assert over_land == []
