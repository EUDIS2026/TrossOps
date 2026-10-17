"""Where things are in the synthetic world makes operational sense.

test_ground.py pins the physics (nothing on water, no sites on roads, ships at sea). These tests pin the judgement on
top of it: units in the field deploy beside roads they can reach, outside towns and not on top of each other; the
Home Guard guards objects in its own county from outside their fences; fighter orbits stay clear of neighbouring
territory.
"""
from collections import defaultdict

import pytest

from app import geo, geonet, orbat
from app.sitegen import _in_ring
from app.world import SyntheticWorld


@pytest.fixture(scope="module")
def world():
    return SyntheticWorld()


def _free_statics(world):
    """Static land units not parked inside a site."""
    rings = [lay.footprint for lay in world.layouts.values()]
    out = []
    for e in world.entities.values():
        m = e.motion
        if e.base.domain == "land" and m and m.kind == "static":
            p = m.pos[:2]
            if not any(_in_ring(p, r) for r in rings):
                out.append((e, p))
    return out


def _road_m(p):
    nets = [orbat.road_net(p)] + [geonet.city(n) for n in geonet.cities() if n != "gotland" and orbat._within(p, geonet.city(n).bounds(), 0)]
    best = float("inf")
    for net in nets:
        if net is not None:
            got = net.nodes_within(p, 3000)
            if got:
                best = min(best, geo.haversine_m(p, got[0]))
    return best


def test_field_units_deploy_beside_roads_outside_towns(world):
    by_unit = defaultdict(list)
    for e, p in _free_statics(world):
        if e.base.layer in ("land.manoeuvre", "land.ad", "land.fires"):
            by_unit[e.base.parentId].append((e.base.id, p))
    assert len(by_unit) >= 15
    far, in_town = [], []
    for unit, members in by_unit.items():
        for vid, p in members:
            if e_is_launcher(vid):
                continue  # dispersed launchers stand up to ~2 km from the fire-control radar
            if _road_m(p) > 400:
                far.append((vid, round(_road_m(p))))
            if orbat.urban(p):
                in_town.append((vid, orbat.urban(p)))
    assert far == []
    assert in_town == []


def e_is_launcher(vid: str) -> bool:
    return vid.rsplit("-", 1)[-1].startswith("l")


def test_nothing_parked_on_top_of_each_other(world):
    pts = _free_statics(world)
    stacked = []
    for i, (a, pa) in enumerate(pts):
        for b, pb in pts[i + 1:]:
            if abs(pa[1] - pb[1]) < 0.001 and geo.haversine_m(pa, pb) < 15:
                stacked.append((a.base.id, b.base.id))
    assert stacked == []


def test_home_guard_guards_its_own_county_from_outside_the_fence(world):
    guards = defaultdict(set)
    for e, p in _free_statics(world):
        if e.base.layer != "land.homeguard" or not e.base.tags or not e.base.tags[0].startswith("Protect "):
            continue
        sid = e.base.tags[0][len("Protect "):]
        site = next(s for s in orbat.SITES if s.id == sid)
        assert orbat.COUNTY_OF[site.near] == e.base.region, (e.base.id, sid)
        lay = world.layouts[sid]
        reach = max(geo.haversine_m(lay.center, q) for q in lay.footprint)
        assert geo.haversine_m(lay.center, p) <= reach + 1000, (e.base.id, sid)
        guards[sid].add(e.base.parentId)
    assert len(guards) >= 15
    assert {sid: cs for sid, cs in guards.items() if len(cs) > 1} == {}


# Neighbouring territory a Swedish fighter orbit must stay out of (coarse boxes / circles, generous margins).
ALAND = (19.45, 59.75, 21.2, 60.55)  # demilitarised Åland islands and their waters
FINLAND_NORTH = [(24.2, 65.6, 30.0, 66.3), (23.75, 66.3, 30.0, 70.0)]  # east of the Torne (Haparanda is at 24.14)
NORWAY_WEST = (4.0, 59.0, 11.6, 71.0)  # west of the Bohuslän / Värmland border (coarse: north of 59.0, west of 11.6)
BORNHOLM = ((14.92, 55.13), 45_000)  # island plus its 12 nm territorial sea


def _in_box(p, b):
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def test_combat_air_patrols_stay_clear_of_neighbours(world):
    bad = []
    for e in world.entities.values():
        m = e.motion
        if e.base.domain != "air" or e.base.affiliation != "own" or not m or m.kind != "path":
            continue
        for q in m.path.pts:
            if q[2] is None:
                continue
            p = q[:2]
            if any(_in_box(p, b) for b in (ALAND, *FINLAND_NORTH, NORWAY_WEST)) or geo.haversine_m(p, BORNHOLM[0]) < BORNHOLM[1]:
                bad.append((e.base.id, round(p[0], 2), round(p[1], 2)))
                break
    assert bad == []


def test_ground_routes_are_real_journeys(world):
    short = []
    for rid, path in world.routes.items():
        pts = [q[:2] for q in path.pts]
        length = sum(geo.haversine_m(a, b) for a, b in zip(pts, pts[1:]))
        if length < 500:
            short.append((rid, round(length)))
    assert short == []


def _reaches_road(land, roads, p, max_cells):
    """Breadth-first walk over dry cells from p: does it reach a road cell within max_cells (~110 m each)?"""
    c0 = land.cell(p)
    r0, q0 = divmod(c0, land.w)
    seen, frontier = {c0}, [c0]
    while frontier:
        nxt = []
        for c in frontier:
            if c in roads:
                return True
            r, q = divmod(c, land.w)
            for rr, qq in ((r + 1, q), (r - 1, q), (r, q + 1), (r, q - 1)):
                n = rr * land.w + qq
                if abs(rr - r0) > max_cells or abs(qq - q0) > max_cells or n in seen:
                    continue
                seen.add(n)
                if land.is_dry((land.lng0 + (qq + 0.5) * land.dlng, land.lat1 - (rr + 0.5) * land.dlat)):
                    nxt.append(n)
        frontier = nxt
    return False


def test_sites_and_field_units_are_not_cut_off_on_islands(world):
    """Everything on the ground can be reached over dry land from a road (no port or platoon on a roadless islet)."""
    land = geonet.land()
    roads = set(land.road_cells(geonet.national()))
    for name in geonet.cities():
        roads |= land.road_cells(geonet.city(name))
    cut_off = [sid for sid, c in world.sites.items() if not _reaches_road(land, roads, c, 45)]
    cut_off += [e.base.id for e, p in _free_statics(world) if not _reaches_road(land, roads, p, 45)]
    assert cut_off == []

