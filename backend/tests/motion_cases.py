"""Shared motion cases: the Python model generates `fixtures/motion_cases.json`; the TypeScript twin must reproduce it.
Regenerate with `python -m tests.motion_cases` after an intentional change to the motion model (then rerun both suites)."""
from __future__ import annotations

import json
from pathlib import Path

from app import motion

FIXTURE = Path(__file__).parent / "fixtures" / "motion_cases.json"

PATH = [(18.0, 59.0, None), (18.01, 59.0, None), (18.02, 59.005, 50.0), (18.05, 59.02, 900.0), (18.08, 59.0, 900.0), (18.06, 58.98, 300.0), (18.0, 58.99, None)]
SPEEDS = [8.0, 40.0, 90.0, 200.0, 180.0, 70.0]
SPECS = {
    "loop": dict(kind="path", start_s=100.0, hold_s=60.0, mode="loop", airborne=True, fuel_start=100.0, fuel_burn_per_km=0.5),
    "pingpong_trim": dict(kind="path", start_s=0.0, hold_s=30.0, mode="pingpong", trim=(150.0, 300.0)),
    "once_offset": dict(kind="path", start_s=50.0, offset_s=20.0, mode="once"),
}
TIMES = [0.0, 99.0, 100.0, 130.5, 160.0, 205.0, 260.0, 333.3, 400.0, 512.0, 640.0, 777.7, 900.0, 1200.0, 2400.5]


def spec(name: str) -> motion.MotionSpec:
    return motion.MotionSpec(path=motion.Path(PATH, SPEEDS), **SPECS[name])  # type: ignore[arg-type]


def generate() -> dict:
    out = {"path": PATH, "speeds": SPEEDS, "specs": {k: {kk: (list(vv) if isinstance(vv, tuple) else vv) for kk, vv in v.items()} for k, v in SPECS.items()}, "times": TIMES, "cases": {}}
    for name in SPECS:
        m = spec(name)
        rows = []
        for t in TIMES:
            s = motion.state_at(m, t)
            rows.append([s.lng, s.lat, s.alt, s.heading, s.pitch, s.bank, s.speed, s.phase, s.fuel])
        out["cases"][name] = rows
    return out


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(generate(), indent=1))
    print(f"wrote {FIXTURE}")
