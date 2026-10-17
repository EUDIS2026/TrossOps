from collections import Counter

from app import geo
from app.world import SyntheticWorld


def test_world_is_deterministic_and_national_scale():
    a, b = SyntheticWorld(), SyntheticWorld()
    assert list(a.entities) == list(b.entities) and list(a.formations) == list(b.formations)
    assert len(a.entities) > 900 and len(a.formations) > 200
    s1, s2 = a.state_at(a.entities["aw-s-03"], 1234.5), b.state_at(b.entities["aw-s-03"], 1234.5)
    assert (s1.lng, s1.lat, s1.alt) == (s2.lng, s2.lat, s2.alt)


def test_every_platform_has_a_formation_and_symbol():
    w = SyntheticWorld()
    for e in w.entities.values():
        assert e.base.sidc and len(e.base.sidc) >= 10, e.base.id
        if e.base.kind not in ("facility", "infrastructure", "unknown"):
            assert e.base.parentId in w.formations, e.base.id
    kinds = Counter(e.base.kind for e in w.entities.values())
    assert kinds["fixed_wing"] >= 70 and kinds["ground_vehicle"] >= 500 and kinds["vessel"] >= 30 and kinds["helicopter"] >= 20


def test_fighters_take_off_from_their_runway():
    w = SyntheticWorld()
    ent = next(e for e in w.entities.values() if e.motion and e.motion.kind == "path" and e.base.modelKey == "fighter")
    m = ent.motion
    start = w.state_at(ent, m.start_s - m.offset_s - 1)
    assert start.alt is None and start.phase == "waiting"
    airborne = [w.state_at(ent, m.start_s + t) for t in range(0, 3000, 30)]
    assert any(s.alt and s.alt > 5000 for s in airborne)


def test_convoy_keeps_spacing():
    w = SyntheticWorld()
    a, b = w.entities["coy-n1a-01"], w.entities["coy-n1a-02"]
    t = a.motion.start_s + 900
    sa, sb = w.state_at(a, t), w.state_at(b, t)
    assert 40 < geo.haversine_m((sa.lng, sa.lat), (sb.lng, sb.lat)) < 200


def test_unknown_tracks_are_observed_and_routes_hidden():
    w = SyntheticWorld()
    unk = [e for e in w.entities.values() if e.base.affiliation == "unknown"]
    assert unk and all(e.base.sourceKind == "observed" for e in unk)
    cat = {c["id"]: c for c in w.catalog()["entities"]}
    assert all("motion" not in cat[e.base.id] for e in unk)


def test_altitude_datum_is_honest():
    w = SyntheticWorld()
    fighter = next(e for e in w.entities.values() if e.motion and e.motion.kind == "path" and e.base.modelKey == "fighter")
    t = next(t for t in range(int(fighter.motion.start_s), 99999, 60) if (w.state_at(fighter, t).alt or 0) > 3000)
    cruising = w.entity_at(fighter, t, "2026-01-01T00:00:00+00:00", 1)
    assert cruising.position.altitudeDatum == "MSL"
    land = w.entity_at(w.entities["coy-n1a-01"], 0, "2026-01-01T00:00:00+00:00", 1)
    assert land.position.altitudeM is None and land.position.altitudeDatum == "UNKNOWN"
