import json
import math

from app import geo, motion
from tests.motion_cases import FIXTURE, SPECS, TIMES, generate, spec


def test_fixture_matches_python_model():
    """The committed fixture is what the TypeScript twin is checked against; the Python model must still produce it."""
    want = json.loads(FIXTURE.read_text())
    got = generate()
    for name in SPECS:
        for a, b in zip(want["cases"][name], got["cases"][name]):
            for x, y in zip(a, b):
                assert (x == y) if isinstance(x, str) or x is None or y is None else math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-9)


def test_speed_is_respected_within_a_segment():
    m = spec("loop")
    a, b = motion.state_at(m, 300.0), motion.state_at(m, 301.0)
    assert abs(geo.haversine_m((a.lng, a.lat), (b.lng, b.lat)) - a.speed) < 3


def test_waiting_holding_and_once_done():
    m = spec("loop")
    assert motion.state_at(m, 0).phase == "waiting"
    once = spec("once_offset")
    assert motion.state_at(once, 99999).phase == "done" and motion.state_at(once, 99999).speed == 0


def test_trim_keeps_column_inside_sub_path():
    m = spec("pingpong_trim")
    p = m.path
    for t in TIMES:
        s = motion.state_at(m, t)
        assert 150.0 - 1e-6 <= s.distance <= p.length - 300.0 + 1e-6


def test_aircraft_attitude_is_plausible():
    m = spec("loop")
    climbs = [motion.state_at(m, t).pitch for t in range(100, 400, 5)]
    assert max(climbs) > 1 and all(abs(motion.state_at(m, t).bank) <= 65 for t in range(100, 600, 7))
