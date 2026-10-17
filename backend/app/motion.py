"""Motion model v2: every synthetic platform moves along a declared polyline with per-segment speeds.

The same model is implemented in `frontend/src/core/motion.ts`; the client evaluates it at display rate so
thousands of synthetic platforms move smoothly without streaming. `backend/tests/test_motion.py` pins sample
values that `frontend/src/core/__tests__/motion.test.ts` checks against, so the two never drift.

Definitions (all distances in metres, times in scenario seconds, angles in degrees):
- A path is a list of vertices [lng, lat, altM | None]; altM None means "on the ground" (clamped to terrain by the
  renderer, 0 m AGL for rules). Segment i runs from vertex i to i+1 at speeds[i] m/s (constant within a segment).
- cycle time = sum(segment times) + holdS. The platform waits `holdS` at the final vertex before repeating (loop),
  reversing (pingpong: forward, hold, backward, hold) or stopping (once).
- `offsetS` shifts the platform's phase forward in time.
- `trim` = [startM, endM] restricts the platform to the sub-path [startM, length − endM]. A convoy shares one route:
  the lead trims the start by (n−1)·spacing, the tail trims the end by the same, so the column keeps its spacing,
  halts as a column at both ends, and every vehicle uses the same shared geometry.
- Attitude is derived from the path itself over a window w = clamp(2 s × speed, 6 m, 600 m):
  heading = bearing(p(d−w) → p(d+w)); pitch = atan2(alt(d+w) − alt(d−w), 2w) for airborne segments;
  bank = atan(v · turnRate / g) for aircraft (clamped to ±65°), 0 otherwise.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from . import geo

G = 9.81
AIR_KINDS = {"fixed_wing", "helicopter", "multirotor"}


@dataclass
class Path:
    pts: list[tuple[float, float, float | None]]
    speeds: list[float]
    cum_d: list[float] = field(default_factory=list)  # cumulative distance at each vertex
    cum_t: list[float] = field(default_factory=list)  # cumulative time at each vertex
    seg_len: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.pts) < 1:
            raise ValueError("empty path")
        if len(self.speeds) == 1 and len(self.pts) > 2:
            self.speeds = self.speeds * (len(self.pts) - 1)
        if len(self.pts) > 1 and len(self.speeds) != len(self.pts) - 1:
            raise ValueError("speeds must have one entry per segment")
        d = t = 0.0
        self.cum_d, self.cum_t, self.seg_len = [0.0], [0.0], []
        for i in range(len(self.pts) - 1):
            seg = geo.haversine_m(self.pts[i][:2], self.pts[i + 1][:2])
            if self.pts[i][2] is not None and self.pts[i + 1][2] is not None:
                seg = math.hypot(seg, self.pts[i + 1][2] - self.pts[i][2])  # type: ignore[operator]
            self.seg_len.append(seg)
            d += seg
            t += seg / max(self.speeds[i], 0.01)
            self.cum_d.append(d)
            self.cum_t.append(t)

    @property
    def length(self) -> float:
        return self.cum_d[-1]

    @property
    def duration(self) -> float:
        return self.cum_t[-1]

    def at_distance(self, d: float) -> tuple[float, float, float | None, int]:
        """Point at distance d (clamped), plus the segment index."""
        if len(self.pts) == 1 or d <= 0:
            p = self.pts[0]
            return p[0], p[1], p[2], 0
        if d >= self.length:
            p = self.pts[-1]
            return p[0], p[1], p[2], len(self.pts) - 2
        i = bisect.bisect_right(self.cum_d, d) - 1
        i = min(max(i, 0), len(self.pts) - 2)
        f = (d - self.cum_d[i]) / (self.seg_len[i] or 1)
        a, b = self.pts[i], self.pts[i + 1]
        alt = None if a[2] is None or b[2] is None else a[2] + (b[2] - a[2]) * f
        if a[2] is None and b[2] is not None:
            alt = b[2] * f  # lifting off the ground
        if a[2] is not None and b[2] is None:
            alt = a[2] * (1 - f)  # touching down
        return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, alt, i

    def time_at_distance(self, d: float) -> float:
        if len(self.pts) == 1 or d <= 0:
            return 0.0
        if d >= self.length:
            return self.duration
        i = bisect.bisect_right(self.cum_d, d) - 1
        i = min(max(i, 0), len(self.pts) - 2)
        return self.cum_t[i] + (d - self.cum_d[i]) / max(self.speeds[i], 0.01)

    def distance_at_time(self, t: float) -> tuple[float, float]:
        """(distance, speed) after t seconds of travel along the path."""
        if len(self.pts) == 1 or t <= 0:
            return 0.0, (self.speeds[0] if self.speeds else 0.0)
        if t >= self.duration:
            return self.length, 0.0
        i = bisect.bisect_right(self.cum_t, t) - 1
        i = min(max(i, 0), len(self.pts) - 2)
        return self.cum_d[i] + (t - self.cum_t[i]) * self.speeds[i], self.speeds[i]


@dataclass
class MotionSpec:
    """A platform's declared movement. kind 'static' uses `pos`/`heading`; kind 'path' uses `path`."""
    kind: str  # 'static' | 'path'
    pos: tuple[float, float, float | None] | None = None
    heading: float = 0.0
    path: Path | None = None
    start_s: float = 0.0
    offset_s: float = 0.0
    hold_s: float = 0.0
    mode: str = "loop"  # loop | pingpong | once
    airborne: bool = False  # aircraft: derive pitch and bank
    route_id: str | None = None  # shared path in the route catalogue (client fetches it once)
    fuel_start: float | None = None  # % at the start of each cycle (refuelled at the end vertex)
    fuel_burn_per_km: float = 0.0
    trim: tuple[float, float] = (0.0, 0.0)

    def to_api(self) -> dict:
        if self.kind == "static" or self.path is None:
            p = self.pos or (0.0, 0.0, None)
            return {"kind": "static", "pos": [round(p[0], 6), round(p[1], 6), p[2]], "heading": round(self.heading, 1)}
        out = {"kind": "path", "startS": self.start_s, "offsetS": round(self.offset_s, 2), "holdS": self.hold_s, "mode": self.mode,
               "airborne": self.airborne, "fuelStart": self.fuel_start, "fuelBurnPerKm": self.fuel_burn_per_km}
        if self.trim != (0.0, 0.0):
            out["trim"] = [round(self.trim[0], 1), round(self.trim[1], 1)]
        if self.route_id:
            out["routeId"] = self.route_id
        else:
            out.update(encode_path(self.path))
        return out


def encode_path(path: Path) -> dict:
    return {"path": [[round(p[0], 6), round(p[1], 6), None if p[2] is None else round(p[2], 1)] for p in path.pts],
            "speeds": [round(s, 2) for s in path.speeds]}


@dataclass
class State:
    lng: float
    lat: float
    alt: float | None
    heading: float
    pitch: float
    bank: float
    speed: float
    distance: float  # metres along the path in the current pass
    phase: str  # 'static' | 'waiting' | 'moving' | 'holding' | 'returning' | 'done'
    fuel: float | None


def _phase_distance(m: MotionSpec, t: float) -> tuple[float, float, int, str, float]:
    """(distance along path, speed, direction ±1, phase name, distance travelled this cycle)."""
    p = m.path
    assert p is not None
    d0 = min(max(m.trim[0], 0.0), p.length)
    d1 = max(min(p.length - m.trim[1], p.length), d0)
    t0, t1 = p.time_at_distance(d0), p.time_at_distance(d1)
    run = t1 - t0

    def fwd(tt: float) -> tuple[float, float]:
        if tt >= run:
            return d1, 0.0
        d, v = p.distance_at_time(t0 + max(tt, 0.0))
        return min(max(d, d0), d1), v

    tau = t - m.start_s + m.offset_s
    if tau < 0:
        return d0, 0.0, 1, "waiting", 0.0
    if m.mode == "once":
        d, v = fwd(tau)
        return d, v, 1, ("moving" if tau < run else "done"), d - d0
    if m.mode == "pingpong":
        cycle = 2 * (run + m.hold_s)
        ph = tau % cycle if cycle > 0 else 0
        if ph < run:
            d, v = fwd(ph)
            return d, v, 1, "moving", d - d0
        if ph < run + m.hold_s:
            return d1, 0.0, 1, "holding", d1 - d0
        ph2 = ph - run - m.hold_s
        if ph2 < run:
            # Backwards: travel time measured from the end, so per-segment speeds are honoured in reverse.
            d, v = fwd(run - ph2)
            return d, v, -1, "returning", (d1 - d0) + (d1 - d)
        return d0, 0.0, -1, "holding", 2 * (d1 - d0)
    cycle = run + m.hold_s
    ph = tau % cycle if cycle > 0 else 0
    if ph < run:
        d, v = fwd(ph)
        return d, v, 1, "moving", d - d0
    return d1, 0.0, 1, "holding", d1 - d0


def state_at(m: MotionSpec, t: float) -> State:
    if m.kind == "static" or m.path is None:
        lng, lat, alt = m.pos or (0.0, 0.0, None)
        return State(lng, lat, alt, m.heading, 0.0, 0.0, 0.0, 0.0, "static", m.fuel_start)
    p = m.path
    d, v, direction, phase, travelled = _phase_distance(m, t)
    lng, lat, alt, _ = p.at_distance(d)
    w = min(max(2.0 * max(v, 3.0), 6.0), 600.0)
    a = p.at_distance(d - w * direction)
    b = p.at_distance(d + w * direction)
    if geo.haversine_m(a[:2], b[:2]) < 0.5:  # degenerate (single vertex or end of path): use the last segment
        i = min(max(bisect.bisect_right(p.cum_d, d) - 1, 0), len(p.pts) - 2) if len(p.pts) > 1 else 0
        a, b = (p.pts[i], p.pts[i + 1]) if len(p.pts) > 1 else (p.pts[0], p.pts[0])
        if direction < 0:
            a, b = b, a
    heading = geo.bearing_deg(a[:2], b[:2]) if geo.haversine_m(a[:2], b[:2]) > 0.01 else 0.0
    pitch = bank = 0.0
    if m.airborne and alt is not None and v > 0:
        if a[2] is not None and b[2] is not None:
            pitch = math.degrees(math.atan2(b[2] - a[2], 2 * w))
        h1 = geo.bearing_deg(a[:2], (lng, lat)) if geo.haversine_m(a[:2], (lng, lat)) > 0.01 else heading
        h2 = geo.bearing_deg((lng, lat), b[:2]) if geo.haversine_m((lng, lat), b[:2]) > 0.01 else heading
        rate = math.radians(geo.wrap_heading_delta(h1, h2)) / max(w / v, 0.05)
        bank = max(-65.0, min(65.0, math.degrees(math.atan(v * rate / G))))
    fuel = None
    if m.fuel_start is not None:
        fuel = max(0.0, m.fuel_start - m.fuel_burn_per_km * travelled / 1000) if phase != "holding" or m.mode == "pingpong" else m.fuel_start
    return State(lng, lat, alt, heading, pitch, bank, v, d, phase, fuel)


def sample(m: MotionSpec, t_from: float, t_to: float, step_s: float) -> list[list[float | None]]:
    out: list[list[float | None]] = []
    t = max(0.0, t_from)
    while t <= t_to + 1e-9:
        s = state_at(m, t)
        out.append([round(s.lng, 6), round(s.lat, 6), None if s.alt is None else round(s.alt, 1), round(t, 1)])
        t += step_s
    return out


# ---- path construction helpers ------------------------------------------------------------------------------
def densify(coords: list[tuple[float, float]], max_step_m: float) -> list[tuple[float, float]]:
    out = [coords[0]]
    for a, b in zip(coords, coords[1:]):
        d = geo.haversine_m(a, b)
        n = int(d // max_step_m)
        for k in range(1, n + 1):
            f = k / (n + 1)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        out.append(b)
    return out


def arc(center: tuple[float, float], radius_m: float, start_deg: float, sweep_deg: float, step_deg: float = 10.0) -> list[tuple[float, float]]:
    """Points on a circle (bearing angles, clockwise positive) — used for racetracks and turns."""
    n = max(1, int(abs(sweep_deg) / step_deg))
    return [geo.destination(center, start_deg + sweep_deg * k / n, radius_m) for k in range(n + 1)]


def racetrack(center: tuple[float, float], axis_deg: float, length_m: float, radius_m: float) -> list[tuple[float, float]]:
    """Closed racetrack (combat air patrol orbit), clockwise, starting at the inbound leg's start."""
    half = length_m / 2
    c1 = geo.destination(center, axis_deg, half)
    c2 = geo.destination(center, axis_deg + 180, half)
    pts = arc(c1, radius_m, axis_deg - 90, 180) + arc(c2, radius_m, axis_deg + 90, 180)
    pts.append(pts[0])
    return pts
