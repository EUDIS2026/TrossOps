from app.world import SyntheticWorld
from app import geo


def test_world_is_deterministic():
    a, b = SyntheticWorld(), SyntheticWorld()
    assert [e.base.id for e in a.entities.values()] == [e.base.id for e in b.entities.values()]
    assert a.state_at(a.entities["fw-01"], 1234.5) == b.state_at(b.entities["fw-01"], 1234.5)
    assert a.entities["gv-02"].readiness == b.entities["gv-02"].readiness


def test_motion_is_continuous_and_respects_speed():
    w = SyntheticWorld()
    e = w.entities["fw-01"]
    p0, _, _, v = w.state_at(e, 100)
    p1, _, _, _ = w.state_at(e, 110)
    assert abs(geo.haversine_m(p0, p1) - v * 10) < 2  # 210 m/s × 10 s


def test_unit_waits_before_start_and_holds_at_end():
    w = SyntheticWorld()
    e = w.entities["ves-02"]  # start 1800 s, non-looping
    assert w.state_at(e, 10)[3] == 0.0
    far = e.total_length / e.spec.speed_mps + 1800 + 100
    pos, _, _, speed = w.state_at(e, far)
    assert speed == 0.0 and pos == e.waypoints[-1]


def test_all_kinds_present_and_unknown_tracks_observed():
    w = SyntheticWorld()
    kinds = {e.base.kind for e in w.entities.values()}
    assert {"fixed_wing", "helicopter", "multirotor", "ground_vehicle", "vessel", "personnel", "facility", "infrastructure", "unknown"} <= kinds
    unk = [e for e in w.entities.values() if e.base.kind == "unknown"]
    assert unk and all(e.base.sourceKind == "observed" and e.base.affiliation == "unknown" for e in unk)


def test_altitude_datum_is_honest():
    w = SyntheticWorld()
    air = w.entity_at(w.entities["fw-01"], 0, "2026-01-01T00:00:00+00:00", 1)
    land = w.entity_at(w.entities["gv-01"], 0, "2026-01-01T00:00:00+00:00", 1)
    assert air.position.altitudeDatum == "MSL" and air.position.altitudeM == 6500
    assert land.position.altitudeM is None and land.position.altitudeDatum == "UNKNOWN"
