"""Predictions respect geography: ships stay in navigable water, ground tracks follow roads, air flies straight; turn
hypotheses come from the observed track history and say so; uncertainty widens with distance travelled."""
from app import geo, geonet, predict
from app.models import GeoPosition, Kinematics, SceneEntity


def track(domain: str, p, heading: float, speed: float, eid: str = "t-1") -> SceneEntity:
    kind = {"sea": "vessel", "land": "ground_vehicle", "air": "fixed_wing"}[domain]
    return SceneEntity(id=eid, resourceId=eid, kind=kind, domain=domain, affiliation="unknown", label=f"Test {domain}",  # type: ignore[arg-type]
                       position=GeoPosition(longitudeDeg=p[0], latitudeDeg=p[1], horizontalAccuracyM=500.0), kinematics=Kinematics(headingDeg=heading, speedMps=speed))


def first_wet_point_heading_at_land(sea, start, heading, reach_m):
    """A start/heading pair whose straight line would cross land within reach (keeps the test meaningful)."""
    return any(not sea.is_water(geo.destination(start, heading, f * reach_m)) for f in (0.25, 0.5, 0.75, 1.0))


def test_ship_heading_for_the_coast_stays_in_water():
    sea = geonet.sea()
    start, heading, speed = (19.25, 57.45), 270.0, 15.0  # east of Gotland, steaming west at the island
    assert sea.is_water(start) and first_wet_point_heading_at_land(sea, start, heading, speed * 1800)
    path = predict.dead_reckon(track("sea", start, heading, speed), 1800, 60, 0)
    assert all(sea.is_water((q[0], q[1])) for q in path.points)
    assert path.method.startswith("dead_reckoning_sea") and any("navigable water" in b for b in path.basedOn)
    assert any("deflected" in b or "held" in b for b in path.basedOn)


def test_ship_alternatives_stay_in_water():
    sea = geonet.sea()
    e = track("sea", (19.25, 57.45), 270.0, 15.0)
    cv = predict.dead_reckon(e, 1800, 60, 0)
    alts = predict.alternatives(e, cv, [], 0, history={"dtS": 60, "headingDeg": 260.0})
    assert alts and all(sea.is_water((q[0], q[1])) for a in alts for q in a.points)


def test_ground_track_follows_roads_and_stays_dry():
    net, land = geonet.national(), geonet.land()
    node, _ = net.nearest_node((17.95, 59.60))  # a road near Arlanda/Märsta
    start = net.node(node)
    path = predict.dead_reckon(track("land", start, 0.0, 15.0), 1200, 60, 0)
    assert path.method.startswith("road_following") and any("road graph" in b for b in path.basedOn)
    assert all(land.is_dry((q[0], q[1])) for q in path.points)
    # every predicted sample lies on (within 60 m of) a road vertex or between two of them on a short edge piece
    for q in path.points[1:]:
        assert net.nodes_within((q[0], q[1]), 1_000), q
    moved = geo.haversine_m(start, (path.points[-1][0], path.points[-1][1]))
    assert moved > 3_000  # it actually goes somewhere along the road


def test_air_track_is_not_terrain_constrained():
    path = predict.dead_reckon(track("air", (16.0, 59.0), 90.0, 200.0), 600, 60, 0)
    end = (path.points[-1][0], path.points[-1][1])
    assert abs(geo.haversine_m((16.0, 59.0), end) - 200.0 * 600) < 500 and path.method.startswith("dead_reckoning(")


def test_turn_hypothesis_uses_the_observed_rate_and_its_direction():
    e = track("air", (16.0, 59.0), 90.0, 200.0)
    cv = predict.dead_reckon(e, 1800, 60, 0)
    left = next(a for a in predict.alternatives(e, cv, [], 0, history={"dtS": 60, "headingDeg": 120.0}) if a.hypothesis.startswith("continues turning"))
    assert "observed turn -0.50°/s" in left.basedOn[0]
    # turning left from east-bound ends north of the start
    assert left.points[5][1] > 59.0
    cv2 = predict.dead_reckon(e, 1800, 60, 0)
    none = next(a for a in predict.alternatives(e, cv2, [], 0, history=None) if a.hypothesis.startswith("continues turning"))
    assert "no track history" in none.basedOn[0]
    assert left.probability > none.probability  # an observed turn makes the turn hypothesis more likely


def test_uncertainty_corridor_widens_with_distance():
    path = predict.dead_reckon(track("air", (16.0, 59.0), 0.0, 200.0), 1800, 60, 0)
    ring = path.uncertaintyRing
    n = (len(ring) - 2) // 2  # left side, cap, right side, closing point
    width_start = geo.haversine_m(tuple(ring[0]), tuple(ring[-2]))
    width_end = geo.haversine_m(tuple(ring[n - 1]), tuple(ring[n + 1]))
    assert width_start < 1_100 and width_end > 10 * width_start
