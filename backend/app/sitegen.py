"""Procedural, deterministic site layouts for the synthetic national world.

Sites are fictional placements (see AGENTS.md: no real military locations). Each layout is generated in a local
metric frame — u along the site axis (runway heading, pier direction), v to the right of it — then projected to
lng/lat. Every feature carries the sub-layer it belongs to so an operator who zooms into a base can see the
infrastructure, the aircraft, the logistics or the defence picture separately:

  infra      runways, taxiways, aprons, shelters, hangars, buildings, piers, markings, lights, navaids
  aircraft   parking/shelter positions (the platforms themselves are entities)
  logistics  fuel farms (with fill level), ammunition storage, motor pools, supply routes
  defence    perimeter, guard posts, air-defence positions
  personnel  barracks and accommodation

Spots are named parking positions (shelter, apron stand, berth, motor-pool slot) with a heading; the order of
battle assigns platforms to them. Local routes (taxi routes, base roads) let ground traffic inside a base move on
the base's own surfaces; at an airbase aircraft taxi on a taxiway graph (shortest path along the painted lines).
"""
from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field

from . import geo
from .motion import arc

LngLat = tuple[float, float]
SUMMARY_CLASSES = {"fuel_tank"}  # features an entity detail carries (Inspector: fuel farm fill)


@dataclass
class Spot:
    id: str
    lng: float
    lat: float
    heading: float
    kind: str  # shelter | qra | apron | berth | motorpool | helipad | pad
    front: LngLat | None = None  # taxi point in front of the spot (where the platform joins the base surface)
    node: str | None = None  # taxiway-graph node at `front` (airbases)


@dataclass
class SiteLayout:
    site_id: str
    kind: str
    center: LngLat
    axis: float
    features: list[dict] = field(default_factory=list)
    spots: dict[str, list[Spot]] = field(default_factory=dict)
    routes: dict[str, list[LngLat]] = field(default_factory=dict)
    runway: dict | None = None
    footprint: list[LngLat] = field(default_factory=list)
    taxi: TaxiNet | None = None  # airbases: taxiway graph for aircraft ground routes (not part of the API payload)

    def to_api(self, summary: bool = False) -> dict:
        """The full layout (`/api/sites/{id}/layout`), or with `summary` the slim copy embedded in an entity detail:
        spots, runway and footprint, but only the features the inspector reads (fuel tanks with their fill)."""
        feats = [f for f in self.features if f["properties"]["cls"] in SUMMARY_CLASSES] if summary else self.features
        return {"siteId": self.site_id, "kind": self.kind, "center": list(self.center), "axis": self.axis,
                "features": {"type": "FeatureCollection", "features": feats},
                "spots": {k: [{"id": s.id, "lng": round(s.lng, 6), "lat": round(s.lat, 6), "heading": round(s.heading, 1), "kind": s.kind} for s in v] for k, v in self.spots.items()},
                "runway": self.runway, "footprint": [[round(p[0], 6), round(p[1], 6)] for p in self.footprint]}


class Frame:
    """Local metric frame: u along `axis` (bearing), v to its right."""

    def __init__(self, center: LngLat, axis: float) -> None:
        self.c, self.axis = center, axis

    def p(self, u: float, v: float) -> LngLat:
        q = geo.destination(self.c, self.axis, u) if u else self.c
        return geo.destination(q, self.axis + 90, v) if v else q

    def rect(self, u: float, v: float, length: float, width: float, rot: float = 0.0) -> list[list[float]]:
        """Rectangle centred at (u, v), `length` along the axis rotated by `rot` degrees."""
        r = math.radians(rot)
        cu, su = math.cos(r), math.sin(r)
        pts = []
        for du, dv in ((-length / 2, -width / 2), (length / 2, -width / 2), (length / 2, width / 2), (-length / 2, width / 2), (-length / 2, -width / 2)):
            pts.append(_r(self.p(u + du * cu - dv * su, v + du * su + dv * cu)))
        return pts

    def circle(self, u: float, v: float, radius: float, steps: int = 20) -> list[list[float]]:
        c = self.p(u, v)
        ring = [_r(geo.destination(c, 360 * k / steps, radius)) for k in range(steps)]
        ring.append(ring[0])
        return ring

    def line(self, pts: list[tuple[float, float]]) -> list[list[float]]:
        return [_r(self.p(u, v)) for u, v in pts]

    def heading(self, rot: float) -> float:
        return (self.axis + rot) % 360


def _r(p: LngLat) -> list[float]:
    return [round(p[0], 7), round(p[1], 7)]


def _poly(layout: SiteLayout, ring: list[list[float]], layer: str, cls: str, name: str = "", height: float = 0.0, **props) -> None:
    layout.features.append({"type": "Feature", "properties": {"siteId": layout.site_id, "layer": layer, "cls": cls, "name": name, "height": height, **props},
                            "geometry": {"type": "Polygon", "coordinates": [ring]}})


def _line(layout: SiteLayout, coords: list[list[float]], layer: str, cls: str, name: str = "", **props) -> None:
    layout.features.append({"type": "Feature", "properties": {"siteId": layout.site_id, "layer": layer, "cls": cls, "name": name, **props},
                            "geometry": {"type": "LineString", "coordinates": coords}})


def _point(layout: SiteLayout, p: LngLat, layer: str, cls: str, name: str = "", **props) -> None:
    layout.features.append({"type": "Feature", "properties": {"siteId": layout.site_id, "layer": layer, "cls": cls, "name": name, **props},
                            "geometry": {"type": "Point", "coordinates": _r(p)}})


# ---- airbase ------------------------------------------------------------------------------------------------
# Local frame: u along the runway (threshold of the primary direction at u = -L/2), v to its right. Airside sits
# on the +v side (parallel taxiway, aprons, maintenance, dispersal loops), the QRA compound, navaids, helipads, the
# reserve road strip and the weapons storage area on the -v side, the landside cantonment by the main gate at -u.
AIRBASE_LAYOUT = 3  # bump when the airbase footprint or built surfaces change: the airbases are then re-placed
RUNWAY_M = 2400.0
RUNWAY_W = 45.0
TAXI_V = 200.0   # parallel taxiway A centreline
TAXI_W = 23.0
HOLD_V = 75.0    # runway-holding position on every connector
HUB_U, HUB_V, HUB_R = 950.0, 780.0, 215.0  # dispersal loops: centre (±u, v) and loop centreline radius
APRON_LANE_V = 268.0
EXIT_U = (150.0, 604.0)  # rapid-exit taxiways B1, B2 leave the runway here (landing direction: +u)


class TaxiNet:
    """Taxiway graph of an airbase: named nodes on the painted centrelines, edges along them. Aircraft ground
    routes are shortest paths on it, so they follow the lines; runway edges cost extra (back-taxiing on the runway
    is the last resort)."""

    RUNWAY_COST = 6.0

    def __init__(self, f: Frame) -> None:
        self.f = f
        self.uv: dict[str, tuple[float, float]] = {}
        self.adj: dict[str, dict[str, float]] = {}

    def node(self, name: str, u: float, v: float) -> str:
        self.uv[name] = (u, v)
        self.adj.setdefault(name, {})
        return name

    def link(self, *names: str, cost: float = 1.0) -> None:
        for a, b in zip(names, names[1:]):
            self.adj[a][b] = self.adj[b][a] = math.dist(self.uv[a], self.uv[b]) * cost

    def at(self, name: str) -> LngLat:
        return self.f.p(*self.uv[name])

    def route(self, a: str, b: str) -> list[str]:
        dist, prev, heap, done = {a: 0.0}, {}, [(0.0, a)], set()
        while heap:
            d, n = heapq.heappop(heap)
            if n in done:
                continue
            done.add(n)
            if n == b:
                break
            for m, w in sorted(self.adj[n].items()):
                if d + w < dist.get(m, math.inf):
                    dist[m], prev[m] = d + w, n
                    heapq.heappush(heap, (d + w, m))
        if b not in done:
            raise ValueError(f"no taxi route {a} -> {b}")
        out = [b]
        while out[-1] != a:
            out.append(prev[out[-1]])
        return out[::-1]

    def length(self, names: list[str]) -> float:
        return sum(self.adj[a][b] for a, b in zip(names, names[1:]))


def _designator(bearing: float) -> str:
    return f"{round((bearing % 360) / 10) % 36 or 36:02d}"


def _strip(lay: SiteLayout, f: Frame, pts: list[tuple[float, float]], width: float, layer: str, cls: str, name: str = "", **props) -> None:
    """A paved strip along a local polyline: one rectangle per leg plus round fillets at the joints."""
    for (u0, v0), (u1, v1) in zip(pts, pts[1:]):
        _poly(lay, f.rect((u0 + u1) / 2, (v0 + v1) / 2, math.hypot(u1 - u0, v1 - v0), width, math.degrees(math.atan2(v1 - v0, u1 - u0))), layer, cls, name, **props)
    for u, v in pts[1:-1]:
        _poly(lay, f.circle(u, v, width / 2, 12), layer, cls, name, **props)


def _along(pts: list[tuple[float, float]], step: float, skip_first: bool = False) -> list[tuple[float, float]]:
    """Points every `step` metres along a local polyline (for edge and centreline lights)."""
    out: list[tuple[float, float]] = []
    carry = 0.0 if not skip_first else step
    for (u0, v0), (u1, v1) in zip(pts, pts[1:]):
        ln = math.hypot(u1 - u0, v1 - v0)
        s = carry
        while s <= ln + 1e-6:
            out.append((u0 + (u1 - u0) * s / ln, v0 + (v1 - v0) * s / ln))
            s += step
        carry = s - ln
    return out


def _across(p: tuple[float, float], q: tuple[float, float], half: float) -> list[tuple[float, float]]:
    """A segment through p, perpendicular to p→q, `half` metres to each side (hold bars, stop bars)."""
    a = math.atan2(q[1] - p[1], q[0] - p[0])
    nu, nv = -math.sin(a), math.cos(a)
    return [(p[0] - nu * half, p[1] - nv * half), (p[0] + nu * half, p[1] + nv * half)]


def airbase(site_id: str, center: LngLat, axis: float, seed: int, shelters_per_hub: int = 12, fuel_fill: list[float] | None = None,
            helipads: int = 0) -> SiteLayout:
    rng = random.Random(seed)
    f = Frame(center, axis)
    L, W = RUNWAY_M, RUNWAY_W
    lay = SiteLayout(site_id, "airbase", center, axis)
    net = lay.taxi = TaxiNet(f)
    d1, d2 = _designator(axis), _designator(axis + 180)

    lights: list[tuple[float, float, str]] = []
    openings: list[tuple[tuple[float, float], tuple[float, float], float]] = []  # strips crossing a runway/taxiway edge

    def light(u: float, v: float, kind: str) -> None:
        lights.append((u, v, kind))

    def opening(pts: list[tuple[float, float]], width: float) -> None:
        openings.extend((a, b, width / 2) for a, b in zip(pts, pts[1:]))

    def sign(u: float, v: float, text: str) -> None:
        _point(lay, f.p(u, v), "infra", "taxi_sign", text)

    # Ground pad: the base footprint (drawn under everything so a synthetic base reads as one installation).
    fence = [(-L / 2 - 600, -1450), (L / 2 + 700, -1450), (L / 2 + 700, 1250), (-L / 2 - 600, 1250)]
    lay.footprint = [f.p(u, v) for u, v in fence] + [f.p(*fence[0])]
    _poly(lay, [_r(p) for p in lay.footprint], "infra", "footprint", "Base area")
    _line(lay, [_r(p) for p in lay.footprint], "defence", "fence", "Perimeter fence")
    patrol = [(-L / 2 - 575, -1425), (L / 2 + 675, -1425), (L / 2 + 675, 1225), (-L / 2 - 575, 1225), (-L / 2 - 575, -1425)]
    _line(lay, f.line(patrol), "defence", "patrol_road", "Perimeter patrol road")
    lay.routes["perimeter"] = [f.p(u, v) for u, v in patrol]

    # ---- runway: shoulders, blast pads, markings, arresting gear, lights ----
    _poly(lay, f.rect(0, 0, L, W + 15), "infra", "runway_shoulder")
    _poly(lay, f.rect(0, 0, L, W), "infra", "runway", f"Runway {d1}/{d2}")
    _line(lay, f.line([(-L / 2 + 110, 0), (L / 2 - 110, 0)]), "infra", "runway_centerline")
    for side in (-1, 1):
        _line(lay, f.line([(-L / 2, side * (W / 2 - 1)), (L / 2, side * (W / 2 - 1))]), "infra", "runway_edge")
        for u, _v in _along([(-L / 2, 0), (L / 2, 0)], 60):
            light(u, side * (W / 2 + 2), "edge")
    for end, des, rot in ((-1, d1, axis), (1, d2, (axis + 180) % 360)):
        ut, d = end * L / 2, -end

        def at(s: float, ut: float = ut, d: float = d) -> float:  # s metres from this threshold into the runway
            return ut + d * s
        _poly(lay, f.rect(at(-75), 0, 150, W), "infra", "blast_pad", f"Blast pad {des}")
        for k in range(4):
            s0 = -(30 + 32 * k)
            _line(lay, f.line([(at(s0 - 22), -19), (at(s0), 0), (at(s0 - 22), 19)]), "infra", "chevron")
        for side in (-1, 1):
            for i in range(6):  # threshold piano keys
                _poly(lay, f.rect(at(21), side * (2.4 + i * 3.24), 30, 1.8), "infra", "runway_marking")
            _poly(lay, f.rect(at(425), side * 13.5, 50, 9), "infra", "runway_marking")  # aiming point
            for s, n in ((150, 3), (300, 3), (600, 2), (750, 2), (900, 1)):  # touchdown zone
                for j in range(n):
                    _poly(lay, f.rect(at(s + 11), side * (10.5 + j * 4.5), 22.5, 3), "infra", "runway_marking")
        _point(lay, f.p(at(80), 0), "infra", "runway_label", des, rotation=rot)
        _line(lay, f.line([(at(450), -W / 2 - 4), (at(450), W / 2 + 4)]), "infra", "arrestor", f"Arresting gear {des}")
        for k in range(16):
            light(at(0), -22.5 + k * 3, "threshold")
            light(at(-3), -22.5 + k * 3, "end")
        for i in range(4):  # PAPI on the left of the landing aircraft
            light(at(300), end * (32 + i * 9), "papi_red" if i < 2 else "papi_white")
        if end == -1:  # precision approach lighting on the primary (ILS) direction: barrettes and a 300 m crossbar
            for k in range(1, 19):
                for dv in (-2, -1, 0, 1, 2):
                    light(at(-30 * k), dv, "approach")
            for k in range(-10, 11):
                light(at(-300), k * 1.5, "approach")
        else:
            for k in range(1, 11):
                light(at(-30 * k), 0, "approach")

    # ---- parallel taxiway A, connectors, rapid exits, holding positions ----
    a_nodes = sorted({-1160.0, -1060.0, -HUB_U, -560.0, -80.0, 40.0, 420.0, EXIT_U[0] + 346, 600.0, 780.0, HUB_U, 1160.0})
    for u in a_nodes:
        net.node(f"A@{u:g}", u, TAXI_V)
    net.link(*[f"A@{u:g}" for u in a_nodes])
    _strip(lay, f, [(-1160, TAXI_V), (1160, TAXI_V)], TAXI_W + 15, "infra", "taxiway_shoulder")
    _strip(lay, f, [(-1160, TAXI_V), (1160, TAXI_V)], TAXI_W, "infra", "taxiway", "Taxiway A")
    _line(lay, f.line([(-1160, TAXI_V), (1160, TAXI_V)]), "infra", "taxiway_line", "Taxiway A")
    for side in (-1, 1):
        for u, v in _along([(-1160, TAXI_V + side * 13.5), (1160, TAXI_V + side * 13.5)], 60):
            light(u, v, "taxi_edge")
    for u in (-700, 300, 1060):
        sign(u, TAXI_V + 22, "A")
    rwy = []
    for name, u, eor in (("A1", -1160.0, True), ("A2", -560.0, False), ("A3", 40.0, False), ("A4", 1160.0, True)):
        net.node(f"hold-{name}", u, HOLD_V)
        rwy.append((u, net.node(f"rwy-{name}", u, 0)))
        if eor:  # arm/de-arm (end-of-runway) pad on the connector: last checks, weapons armed, pins pulled
            net.node(f"eor-{name}", u, 135)
            net.link(f"A@{u:g}", f"eor-{name}", f"hold-{name}", f"rwy-{name}")
            _poly(lay, f.rect(u, 135, 70, 80), "infra", "arming_pad", f"Arm/de-arm pad {name}")
        else:
            net.link(f"A@{u:g}", f"hold-{name}", f"rwy-{name}")
        pts = [(u, TAXI_V), (u, 0)]
        opening(pts, TAXI_W)
        _strip(lay, f, pts, TAXI_W + 15, "infra", "taxiway_shoulder")
        _strip(lay, f, pts, TAXI_W, "infra", "taxiway", f"Taxiway {name}")
        _line(lay, f.line(pts), "infra", "taxiway_line", f"Taxiway {name}")
        _hold(lay, f, (u, HOLD_V), (u, 0), light)
        for q in _along([(u, TAXI_V - 15), (u, W / 2)], 15):
            light(q[0], q[1], "taxi_center")
        sign(u + 22, HOLD_V + (10 if eor else 25), name)
    for name, x in (("B1", EXIT_U[0]), ("B2", EXIT_U[1])):
        pts = [(x, 0.0), (x + 110, 40.0), (x + 346, TAXI_V)]
        opening(pts, TAXI_W)
        rwy.append((x, net.node(f"rwy-{name}", x, 0)))
        net.node(f"{name}-mid", x + 110, 40)
        net.link(f"rwy-{name}", f"{name}-mid", f"A@{x + 346:g}")
        _strip(lay, f, pts, TAXI_W + 15, "infra", "taxiway_shoulder")
        _strip(lay, f, pts, TAXI_W, "infra", "taxiway", f"Rapid exit {name}")
        _line(lay, f.line(pts), "infra", "taxiway_line", f"Rapid exit {name}")
        t = (HOLD_V - 40) / (TAXI_V - 40)
        hp = (x + 110 + 236 * t, HOLD_V)
        _hold(lay, f, hp, pts[1], light)
        for q in _along(pts, 15, skip_first=True):
            light(q[0], q[1], "taxi_center")
        sign(x + 190, 70, name)
    rwy.sort()
    net.link(*[n for _u, n in rwy], cost=TaxiNet.RUNWAY_COST)

    # ---- main apron: marked stands, taxilane, hydrant fuel pits ----
    _poly(lay, f.rect(-320, 330, 520, 200), "infra", "apron", "Main apron")
    net.node("tl-W", -560, APRON_LANE_V)
    net.node("tl-E", -80, APRON_LANE_V)
    net.link("A@-560", "tl-W")
    net.link("A@-80", "tl-E")
    for u in (-560, -80):
        opening([(u, TAXI_V), (u, 240)], TAXI_W)
        _strip(lay, f, [(u, TAXI_V), (u, 240)], TAXI_W, "infra", "taxiway", "Apron link")
    _line(lay, f.line([(-560, TAXI_V), (-560, APRON_LANE_V), (-80, APRON_LANE_V), (-80, TAXI_V)]), "infra", "taxiway_line", "Apron taxilane")
    lay.spots["shelter"], lay.spots["qra"], lay.spots["apron"] = [], [], []
    lane = ["tl-W"]
    for k in range(8):
        u = -530 + k * 60
        lane.append(net.node(f"AP{k + 1}", u, APRON_LANE_V))
        p = f.p(u, 345)
        lay.spots["apron"].append(Spot(f"{site_id}:A{k + 1}", p[0], p[1], f.heading(90), "apron", net.at(f"AP{k + 1}"), f"AP{k + 1}"))
        _line(lay, f.line([(u, APRON_LANE_V), (u, 362)]), "infra", "stand_line", f"Stand {k + 1}")
        _line(lay, f.line([(u - 5, 362), (u + 5, 362)]), "infra", "stand_line")
        _point(lay, f.p(u, 398), "infra", "stand_label", str(k + 1), rotation=f.heading(90))
        _point(lay, f.p(u + 14, 330), "logistics", "hydrant", f"Hydrant pit {k + 1}")
    net.link(*lane, "tl-E")

    # ---- maintenance, operations and rescue ----
    for i, u in enumerate((-500, -320, -140)):  # doors face the apron
        _poly(lay, f.rect(u, 480, 50, 66, -90), "infra", "hangar", f"Maintenance hangar {i + 1}", 18, model="hangar")
    _poly(lay, f.rect(-760, 330, 60, 40), "infra", "building", "Avionics & engine workshop", 11, model="warehouse")
    _poly(lay, f.rect(-20, 450, 12, 12), "infra", "tower", "Control tower", 32, model="tower")
    _poly(lay, f.rect(130, 470, 52, 26), "infra", "building", "Base operations", 11)
    _poly(lay, f.rect(60, 250, 70, 40), "infra", "apron", "Rescue apron")
    _poly(lay, f.rect(60, 300, 50, 28), "infra", "building", "Fire & rescue station", 9)
    # de-icing pad by the take-off end, engine run-up pad with blast wall, hush house, compass swing base
    net.node("deice", -1060, 300)
    net.link("A@-1060", "deice")
    for u, v_end in ((-1060, 235), (420, 270), (600, 308), (780, 290)):
        opening([(u, TAXI_V), (u, v_end)], TAXI_W)
    _strip(lay, f, [(-1060, TAXI_V), (-1060, 235)], TAXI_W, "infra", "taxiway")
    _poly(lay, f.rect(-1060, 300, 120, 130), "infra", "deice_pad", "De-icing pad")
    _poly(lay, f.rect(-1140, 400, 20, 10), "infra", "building", "De-icing fluid store", 4)
    _strip(lay, f, [(420, TAXI_V), (420, 270)], TAXI_W, "infra", "taxiway")
    _poly(lay, f.rect(420, 300, 90, 70), "infra", "runup_pad", "Engine run-up pad")
    _poly(lay, f.rect(470, 300, 4, 60), "infra", "blast_wall", "Blast deflector", 6)
    _strip(lay, f, [(600, TAXI_V), (600, 308)], TAXI_W, "infra", "taxiway")
    _poly(lay, f.rect(600, 330, 44, 24, 90), "infra", "building", "Hush house (engine test)", 12, model="hush_house")
    _strip(lay, f, [(780, TAXI_V), (780, 290)], TAXI_W, "infra", "taxiway")
    _poly(lay, f.circle(780, 320, 32, 28), "infra", "compass_pad", "Compass swing base")
    for k in range(8):
        a = math.radians(k * 45)
        _line(lay, f.line([(780 + 9 * math.cos(a), 320 + 9 * math.sin(a)), (780 + 29 * math.cos(a), 320 + 29 * math.sin(a))]), "infra", "compass_line")
    for u in (420, 600, 780):
        _line(lay, f.line([(u, TAXI_V), (u, 290)]), "infra", "taxiway_line")

    # ---- fuel: farm with per-tank fill, truck fill stand, hydrant line to the apron ----
    fills = fuel_fill or [round(rng.uniform(45, 95)) for _ in range(6)]
    _poly(lay, f.rect(560, 560, 150, 100), "logistics", "bund", "Fuel farm")
    for k in range(6):
        u, v = 510 + (k % 3) * 50, 535 + (k // 3) * 50
        _poly(lay, f.circle(u, v, 11), "logistics", "fuel_tank", f"Fuel tank {k + 1}", 13, fill=fills[k], model="fuel_tank")
    _poly(lay, f.rect(440, 590, 22, 12), "logistics", "fuel_point", "Truck fill stand", 4)
    _line(lay, f.line([(485, 560), (485, 440), (-580, 440)]), "logistics", "fuel_line", "Hydrant fuel line")

    # ---- dispersal loops with hardened shelters on short spurs between earth revetments ----
    for h, hu in enumerate((HUB_U, -HUB_U)):
        tag = "AB"[h]
        hub = f.p(hu, HUB_V)
        step = 300 / max(1, shelters_per_hub - 1)
        angles = [(300 + k * step) % 360 for k in range(shelters_per_hub)]  # gap of 60° around the lane (270°)
        ring_angles = sorted({round(a, 3) for a in list(range(0, 360, 10)) + angles + [270]})
        ring_names = [net.node(f"H{tag}@{a:g}", hu + HUB_R * math.cos(math.radians(a)), HUB_V + HUB_R * math.sin(math.radians(a))) for a in ring_angles]
        net.link(*ring_names, ring_names[0])
        net.link(f"A@{hu:g}", f"H{tag}@270")
        outer = [_r(p) for p in arc(hub, HUB_R + 11, 0, 360, 5)]
        inner = [_r(p) for p in arc(hub, HUB_R - 11, 360, -360, 5)]
        lay.features.append({"type": "Feature", "properties": {"siteId": site_id, "layer": "infra", "cls": "taxiway", "name": f"Dispersal loop {tag}", "height": 0.0},
                             "geometry": {"type": "Polygon", "coordinates": [outer, inner]}})
        _line(lay, [_r(p) for p in arc(hub, HUB_R, 0, 360, 5)], "infra", "taxiway_line", f"Dispersal loop {tag}")
        opening([(hu, TAXI_V), (hu, HUB_V - HUB_R)], 18)
        _strip(lay, f, [(hu, TAXI_V), (hu, HUB_V - HUB_R)], 18, "infra", "taxiway", f"Taxi lane {tag}")
        _line(lay, f.line([(hu, TAXI_V), (hu, HUB_V - HUB_R)]), "infra", "taxiway_line", f"Taxi lane {tag}")
        sign(hu + 18, TAXI_V + 60, f"D{tag}")
        _poly(lay, f.rect(hu, HUB_V, 40, 20), "infra", "building", f"Squadron operations {tag}", 8)
        _poly(lay, f.rect(hu, HUB_V - 45, 30, 18), "infra", "apron", f"Squadron vehicle park {tag}")
        for k, a in enumerate(angles):
            ra = math.radians(a)
            cu, cv = math.cos(ra), math.sin(ra)
            nu, nv = -cv, cu
            centre = f.p(hu + 275 * cu, HUB_V + 275 * cv)
            facing = (axis + a + 180) % 360  # open front faces the loop
            _poly(lay, f.rect(hu + 244 * cu, HUB_V + 244 * cv, 36, 26, a), "infra", "apron", f"Shelter pad {tag}{k + 1}")
            _poly(lay, _shelter_ring(centre, facing), "infra", "shelter", f"Shelter {tag}{k + 1}", 8, model="shelter", heading=facing)
            for s in (-1, 1):
                _poly(lay, f.rect(hu + 272 * cu + s * 19 * nu, HUB_V + 272 * cv + s * 19 * nv, 38, 6, a), "infra", "revetment", "Earth revetment", 5)
            _line(lay, [_r(net.at(f"H{tag}@{round(a, 3):g}")), _r(geo.destination(centre, facing, 21))], "infra", "taxiway_line")
            mouth = geo.destination(centre, facing, 21)  # parked nose-out on the shelter pad, ready to taxi
            node = f"H{tag}@{round(a, 3):g}"
            lay.spots["shelter"].append(Spot(f"{site_id}:S{tag}{k + 1}", mouth[0], mouth[1], facing, "shelter", net.at(node), node))
        lay.routes[f"hub{h}"] = [net.at(n) for n in ring_names] + [net.at(ring_names[0])]

    # ---- QRA compound: two alert shelters with their own taxiway straight onto the runway ----
    net.node("Q-W", -1150, -110)
    net.node("Q-hold", -1158, -HOLD_V)
    net.link("rwy-A1", "Q-hold", "Q-W")
    q_lane = ["Q-W"]
    for k, u in enumerate((-1090.0, -1030.0)):
        c = f.p(u, -195)
        facing = f.heading(90)
        q_lane.append(net.node(f"Q{k + 1}", u, -110))
        _poly(lay, _shelter_ring(c, facing), "infra", "shelter", f"QRA shelter {k + 1}", 8, model="shelter", heading=facing, qra=True)
        _poly(lay, f.rect(u, -150, 64, 26, 90), "infra", "apron", f"QRA pad {k + 1}")
        mouth = geo.destination(c, facing, 21)
        lay.spots["qra"].append(Spot(f"{site_id}:Q{k + 1}", mouth[0], mouth[1], facing, "qra", net.at(f"Q{k + 1}"), f"Q{k + 1}"))
    net.link(*q_lane)
    opening([(-1150, -110), (-1160, -60), (-1160, -W / 2)], 22)
    _strip(lay, f, [(-1000, -110), (-1150, -110), (-1160, -60), (-1160, -W / 2)], 22, "infra", "taxiway", "Taxiway Q")
    _line(lay, f.line([(-1000, -110), (-1150, -110), (-1158, -HOLD_V), (-1160, 0)]), "infra", "taxiway_line", "Taxiway Q")
    _hold(lay, f, (-1158, -HOLD_V), (-1160, 0), light)
    sign(-1142, -94, "Q")
    _poly(lay, f.rect(-1000, -195, 20, 28), "infra", "building", "QRA alert crew building", 6)
    _line(lay, f.line([(-1130, -90), (-1130, -96)]), "defence", "inner_fence", "QRA compound fence")
    _line(lay, f.line([(-1130, -124), (-1130, -235), (-985, -235), (-985, -90)]), "defence", "inner_fence", "QRA compound fence")
    _point(lay, f.p(-1130, -110), "defence", "gate", "QRA compound gate")

    # ---- navaids, weather, approach radar ----
    _poly(lay, f.rect(L / 2 + 220, 0, 4, 36, 180), "infra", "navaid", f"ILS {d1} localizer", 4, model="ils_array")
    _poly(lay, f.rect(-L / 2 + 300, -150, 3, 3), "infra", "navaid", f"ILS {d1} glideslope", 14, model="mast")
    _poly(lay, f.rect(-L / 2 + 300, -162, 6, 4), "infra", "building", "Glideslope equipment", 3)
    _poly(lay, f.rect(560, -300, 3, 3), "infra", "navaid", "TACAN", 14, model="mast")
    _poly(lay, f.rect(560, -315, 8, 5), "infra", "building", "TACAN equipment", 3)
    _poly(lay, f.rect(420, -220, 3, 3), "infra", "navaid", "Weather station", 10, model="mast")
    _poly(lay, f.rect(-120, -320, 14, 14), "defence", "radar", "Approach radar", 6, model="radar_rotating")

    # ---- helipads (heliports) ----
    if helipads:
        lay.spots["helipad"] = []
        _strip(lay, f, [(-720, -245), (-190, -245)], 16, "infra", "taxiway", "Helicopter taxi route H")
        opening([(-450, -245), (-450, -W / 2)], 16)
        _strip(lay, f, [(-450, -245), (-450, -W / 2)], 16, "infra", "taxiway", "Helicopter taxi route H")
        sign(-435, -110, "H")
        for k in range(helipads):
            u = -700 + k * 70
            _poly(lay, f.circle(u, -280, 14, 24), "infra", "helipad", f"Helipad {k + 1}")
            _point(lay, f.p(u, -280), "infra", "helipad_label", "H", rotation=f.heading(-90))
            p = f.p(u, -280)
            lay.spots["helipad"].append(Spot(f"{site_id}:H{k + 1}", p[0], p[1], f.heading(-90), "helipad"))

    # ---- reserve road strip: a straight, widened base road usable as a runway when the main one is cut ----
    _poly(lay, f.rect(-300, -750, 1200, 25), "infra", "runway", "Reserve strip (road base)")
    _line(lay, f.line([(-870, -750), (270, -750)]), "infra", "runway_centerline")
    for ue in (-900, 300):
        for i in range(4):
            _poly(lay, f.rect(ue + (12 if ue < 0 else -12), -750 + (i - 1.5) * 4.5, 20, 1.8), "infra", "runway_marking")
    opening([(200, -W / 2), (200, -737)], 18)
    _strip(lay, f, [(200, -W / 2), (200, -737)], 18, "infra", "taxiway", "Taxiway R")
    _line(lay, f.line([(200, 0), (200, -750)]), "infra", "taxiway_line", "Taxiway R")
    _hold(lay, f, (200, -HOLD_V), (200, 0), light)
    sign(215, -100, "R")

    # ---- weapons storage area: dispersed earth-covered bunkers inside their own fence ----
    for k in range(8):
        u, v = 700 + (k % 4) * 95, -1000 - (k // 4) * 110
        _poly(lay, f.rect(u, v, 22, 14, 90), "logistics", "ammo_bunker", f"Ammunition bunker {k + 1}", 5, model="bunker")
    _poly(lay, f.rect(1035, -1055, 30, 50), "logistics", "warehouse", "Weapons assembly", 8)
    _line(lay, f.line([(1080, -990), (1080, -940), (640, -940), (640, -1210), (1080, -1210), (1080, -1010)]), "defence", "inner_fence", "Weapons storage area fence")
    _point(lay, f.p(1080, -1000), "defence", "gate", "Weapons storage area gate")
    _line(lay, f.line(_across((1190, 230), (1160, TAXI_V), 4)), "infra", "hold_line", "Road–taxiway crossing (vehicle stop)")
    _line(lay, f.line([(1060, -1000), (L / 2 + 450, -1000), (L / 2 + 450, 260), (1220, 260), (1160, TAXI_V)]), "logistics", "base_road", "Munitions road")
    _line(lay, f.line([(L / 2 + 450, -1000), (L / 2 + 700, -1000)]), "logistics", "base_road", "Logistics gate road")
    _point(lay, f.p(L / 2 + 700, -1000), "defence", "gate", "Logistics gate")

    # ---- landside cantonment by the main gate (personnel) ----
    gate = (-L / 2 - 600, 650)
    _point(lay, f.p(*gate), "defence", "gate", "Main gate")
    _poly(lay, f.rect(-1748, 690, 24, 14), "defence", "guardhouse", "Guardhouse", 5)
    _poly(lay, f.rect(-1730, 580, 50, 40), "personnel", "parking", "Visitor parking")
    _poly(lay, f.rect(-1650, 740, 60, 28), "infra", "building", "Wing headquarters", 14)
    _poly(lay, f.rect(-1440, 740, 40, 24), "personnel", "building", "Medical centre", 8)
    for k in range(6):
        _poly(lay, f.rect(-1680 + (k % 3) * 120, 880 + (k // 3) * 80, 70, 22), "personnel", "barracks", f"Barracks {k + 1}", 12, model="barracks")
    _poly(lay, f.rect(-1340, 900, 50, 40), "personnel", "building", "Mess hall", 8)
    _poly(lay, f.rect(-1340, 1000, 40, 30), "personnel", "building", "Gym", 9)
    _poly(lay, f.rect(-1560, 1110, 160, 90), "personnel", "sports_field", "Sports field")
    _poly(lay, f.rect(-1440, 560, 90, 50), "personnel", "parking", "Personnel parking")
    _line(lay, f.line([(-1600, 650), (-1600, 1040), (-1300, 1040), (-1300, 650)]), "personnel", "base_road", "Cantonment loop")

    # ---- base roads: gate → cantonment → maintenance area → fuel farm; bowser route to the flight line ----
    _line(lay, f.line([gate, (-1290, 650), (-1290, 430), (-780, 430), (-720, 530), (-180, 530), (20, 560), (480, 600)]), "logistics", "base_road", "Main base road")
    _line(lay, f.line([(20, 560), (60, 314)]), "logistics", "base_road", "Rescue road")
    for vv in (430 - 12, 430 + 12):
        _line(lay, f.line([(-959, vv), (-941, vv)]), "infra", "hold_line", "Road–taxiway crossing")
    for uu in (-950 - 16, -950 + 16):
        _line(lay, f.line([(uu, 426), (uu, 434)]), "infra", "hold_line", "Road–taxiway crossing (vehicle stop)")
    lay.routes["bowser"] = [f.p(480, 600), f.p(20, 560), f.p(-180, 530), f.p(-200, 440), f.p(-200, 300), f.p(-80, TAXI_V), f.p(EXIT_U[0] + 346, TAXI_V)]

    # ---- defence: guard towers on the fence, air-defence emplacements ----
    for k, (u, v) in enumerate([(-1780, -1430), (L / 2 + 680, -1430), (L / 2 + 680, 1230), (-1780, 1230), (0, -1430), (300, 1230)]):
        _poly(lay, f.rect(u, v, 5, 5), "defence", "guard_tower", f"Guard tower {k + 1}", 12, model="guard_tower")
    for k, (u, v) in enumerate([(-1650, -1300), (1750, -1300), (1750, 1150), (-1100, 1180)]):
        _poly(lay, f.circle(u, v, 22, 20), "defence", "ad_position", f"Air-defence emplacement {k + 1}", 2)

    for u, v, kind in lights:
        if kind in ("edge", "taxi_edge") and any(_seg_dist((u, v), a, b) < hw + 2 for a, b, hw in openings):
            continue
        _point(lay, f.p(u, v), "infra", "light", light=kind)

    lay.runway = {"start": _r(f.p(-L / 2, 0)), "end": _r(f.p(L / 2, 0)), "heading": axis, "lengthM": L}
    return lay


def _seg_dist(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance in the local frame from p to the segment a-b."""
    du, dv = b[0] - a[0], b[1] - a[1]
    ln2 = du * du + dv * dv
    t = 0.0 if ln2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * du + (p[1] - a[1]) * dv) / ln2))
    return math.hypot(p[0] - a[0] - t * du, p[1] - a[1] - t * dv)


def _hold(lay: SiteLayout, f: Frame, p: tuple[float, float], toward_runway: tuple[float, float], light) -> None:
    """Runway-holding position: two solid bars on the taxiway side, two dashed on the runway side, red stop bar."""
    a = math.atan2(toward_runway[1] - p[1], toward_runway[0] - p[0])
    du, dv = math.cos(a), math.sin(a)
    for off, cls in ((-1.2, "hold_line"), (-0.4, "hold_line"), (0.6, "hold_line_dash"), (1.4, "hold_line_dash")):
        q = (p[0] + du * off, p[1] + dv * off)
        _line(lay, f.line(_across(q, toward_runway, 11.5)), "infra", cls)
    for k in range(-4, 5):
        q = _across((p[0] - du * 2.5, p[1] - dv * 2.5), toward_runway, k * 2.5)[1]
        light(q[0], q[1], "stopbar")


def _shelter_ring(centre: LngLat, facing: float) -> list[list[float]]:
    g = Frame(centre, facing)
    return g.rect(0, 0, 30, 22)


def taxi_out(lay: SiteLayout, spot: Spot) -> list[LngLat]:
    """Ground route from a spot along the taxiway graph (through the arm/de-arm pad) to line-up on the runway
    centreline, facing the axis, just past the threshold."""
    f = Frame(lay.center, lay.axis)
    pts: list[LngLat] = [(spot.lng, spot.lat)]
    if spot.front:
        pts.append(spot.front)
    if lay.taxi is not None and spot.node:
        pts += [lay.taxi.at(n) for n in lay.taxi.route(spot.node, "rwy-A1")]
    pts.append(f.p(-RUNWAY_M / 2 + 70, 0))
    return _dedupe(pts)


def taxi_in(lay: SiteLayout, spot: Spot) -> list[LngLat]:
    """Ground route from the runway exit (the rapid exit nearer the spot) back to the spot. The first point is on
    the runway centreline, where the landing roll hands over to taxiing."""
    f = Frame(lay.center, lay.axis)
    pts: list[LngLat] = []
    if lay.taxi is not None and spot.node:
        net = lay.taxi
        best = min((net.route(e, spot.node) for e in ("rwy-B1", "rwy-B2")), key=net.length)
        pts += [net.at(n) for n in best]
    else:
        pts.append(f.p(EXIT_U[0], 0))
    if spot.front:
        pts.append(spot.front)
    pts.append((spot.lng, spot.lat))
    return _dedupe(pts)


def _dedupe(pts: list[LngLat]) -> list[LngLat]:
    out = [pts[0]]
    for p in pts[1:]:
        if geo.haversine_m(out[-1], p) > 1.0:
            out.append(p)
    return out


# ---- naval base ---------------------------------------------------------------------------------------------
def navbase(site_id: str, center: LngLat, seaward: float, seed: int, piers: int = 3, fuel_fill: list[float] | None = None) -> SiteLayout:
    """`center` sits on the shoreline; `seaward` is the bearing from land to open water."""
    rng = random.Random(seed)
    f = Frame(center, seaward)
    lay = SiteLayout(site_id, "navbase", center, seaward)
    lay.footprint = [f.p(-650, -520), f.p(40, -520), f.p(40, 520), f.p(-650, 520), f.p(-650, -520)]
    _poly(lay, [_r(p) for p in lay.footprint], "infra", "footprint", "Base area")
    _line(lay, [_r(p) for p in lay.footprint[:-1]] + [_r(lay.footprint[0])], "defence", "fence", "Perimeter fence")
    _poly(lay, f.rect(-10, 0, 40, 1000), "infra", "quay", "Quay")
    lay.spots["berth"] = []
    for k in range(piers):
        v = (k - (piers - 1) / 2) * 190
        _poly(lay, f.rect(120, v, 240, 16), "infra", "pier", f"Pier {k + 1}")
        for side in (-1, 1):
            for j in range(2):
                p = f.p(70 + j * 110, v + side * 28)
                lay.spots["berth"].append(Spot(f"{site_id}:B{k + 1}{'LR'[side > 0]}{j + 1}", p[0], p[1], f.heading(0), "berth", f.p(260 + j * 40, v + side * 28)))
    _poly(lay, f.rect(115, 430, 130, 70), "infra", "pontoon", "Boat basin")  # u 50..180: off the quay, in the water
    lay.spots["pad"] = []
    for j in range(8):
        p = f.p(70 + (j % 4) * 30, 405 + (j // 4) * 40)
        lay.spots["pad"].append(Spot(f"{site_id}:P{j + 1}", p[0], p[1], f.heading(0), "pad", f.p(200, 430)))
    for k, (u, v, ln, w, h, cls, nm) in enumerate([(-200, -300, 90, 40, 14, "building", "Workshop"), (-200, -180, 70, 30, 12, "building", "Naval staff"),
                                                   (-380, -330, 60, 24, 12, "barracks", "Barracks 1"), (-380, -230, 60, 24, 12, "barracks", "Barracks 2"),
                                                   (-250, 250, 80, 50, 10, "warehouse", "Stores")]):
        _poly(lay, f.rect(u, v, ln, w), "personnel" if cls == "barracks" else "infra", cls, nm, h, model="barracks" if cls == "barracks" else "warehouse")
    fills = fuel_fill or [round(rng.uniform(50, 95)) for _ in range(4)]
    _poly(lay, f.rect(-430, 260, 120, 90), "logistics", "bund", "Fuel depot")
    for k in range(4):
        _poly(lay, f.circle(-460 + (k % 2) * 55, 235 + (k // 2) * 50, 12), "logistics", "fuel_tank", f"Fuel tank {k + 1}", 12, fill=fills[k], model="fuel_tank")
    _line(lay, f.line([(-650, 0), (-420, 0), (-120, 0), (-60, 300)]), "logistics", "base_road", "Base road")
    lay.routes["channel"] = [f.p(300, 0), f.p(1500, 0), f.p(4000, 0)]
    return lay


# ---- garrison, depot, radar, AD battery, generic ---------------------------------------------------------------
def garrison(site_id: str, center: LngLat, axis: float, seed: int, slots: int = 160) -> SiteLayout:
    f = Frame(center, axis)
    lay = SiteLayout(site_id, "garrison", center, axis)
    lay.footprint = [f.p(-520, -380), f.p(520, -380), f.p(520, 380), f.p(-520, 380), f.p(-520, -380)]
    _poly(lay, [_r(p) for p in lay.footprint], "infra", "footprint", "Garrison area")
    _line(lay, [_r(p) for p in lay.footprint], "defence", "fence", "Perimeter fence")
    _poly(lay, f.rect(120, -60, 560, 330), "logistics", "motorpool", "Motor pool")
    lay.spots["motorpool"] = []
    cols = 40
    for k in range(slots):
        r, c = divmod(k, cols)
        u, v = -140 + c * 13.5, -200 + r * 26
        p = f.p(u, v)
        lay.spots["motorpool"].append(Spot(f"{site_id}:M{k + 1}", p[0], p[1], f.heading(90 if r % 2 else -90), "motorpool", f.p(u, v + (12 if r % 2 else -12))))
    for k in range(6):
        _poly(lay, f.rect(-430 + (k % 3) * 95, 150 + (k // 3) * 90, 70, 24), "personnel", "barracks", f"Barracks {k + 1}", 12, model="barracks")
    _poly(lay, f.rect(-380, -180, 90, 50), "infra", "building", "Workshops", 12, model="warehouse")
    _poly(lay, f.rect(-380, -60, 60, 30), "infra", "building", "Headquarters", 14)
    _poly(lay, f.rect(-200, 280, 70, 40), "logistics", "fuel_point", "Fuel point", 4)
    _point(lay, f.p(-520, 0), "defence", "gate", "Main gate")
    _line(lay, f.line([(-520, 0), (-140, 0), (400, 0)]), "logistics", "base_road", "Base road")
    lay.routes["exit"] = [f.p(-140, 0), f.p(-520, 0), f.p(-800, 0)]
    return lay


def depot(site_id: str, center: LngLat, axis: float, seed: int, fuel_fill: list[float] | None = None) -> SiteLayout:
    rng = random.Random(seed)
    f = Frame(center, axis)
    lay = SiteLayout(site_id, "depot", center, axis)
    lay.footprint = [f.p(-450, -300), f.p(450, -300), f.p(450, 300), f.p(-450, 300), f.p(-450, -300)]
    _poly(lay, [_r(p) for p in lay.footprint], "infra", "footprint", "Depot area")
    _line(lay, [_r(p) for p in lay.footprint], "defence", "fence", "Perimeter fence")
    for k in range(8):
        _poly(lay, f.rect(-300 + (k % 4) * 110, -150 + (k // 4) * 110, 80, 40), "logistics", "warehouse", f"Warehouse {k + 1}", 11, model="warehouse")
    fills = fuel_fill or [round(rng.uniform(40, 95)) for _ in range(6)]
    for k in range(6):
        _poly(lay, f.circle(220 + (k % 3) * 55, 120 + (k // 3) * 55, 14), "logistics", "fuel_tank", f"Fuel tank {k + 1}", 14, fill=fills[k], model="fuel_tank")
    for k in range(6):
        _poly(lay, f.rect(250 + (k % 3) * 60, -200 - (k // 3) * 45, 22, 14), "logistics", "ammo_bunker", f"Ammunition bunker {k + 1}", 5, model="bunker")
    lay.spots["motorpool"] = []
    for k in range(30):
        r, c = divmod(k, 10)
        p = f.p(-380 + c * 14, 200 + r * 24)
        lay.spots["motorpool"].append(Spot(f"{site_id}:M{k + 1}", p[0], p[1], f.heading(90), "motorpool", f.p(-380 + c * 14, 188 + r * 24)))
    lay.routes["exit"] = [f.p(-300, 0), f.p(-450, 0), f.p(-700, 0)]
    return lay


def radar(site_id: str, center: LngLat, axis: float) -> SiteLayout:
    f = Frame(center, axis)
    lay = SiteLayout(site_id, "radar", center, axis)
    lay.footprint = [f.p(-120, -90), f.p(120, -90), f.p(120, 90), f.p(-120, 90), f.p(-120, -90)]
    _poly(lay, [_r(p) for p in lay.footprint], "infra", "footprint", "Sensor site")
    _line(lay, [_r(p) for p in lay.footprint], "defence", "fence", "Perimeter fence")
    _poly(lay, f.circle(0, 0, 9), "infra", "radar", "Surveillance radar", 22, model="radar_dome")
    _poly(lay, f.rect(-60, 40, 30, 14), "infra", "building", "Equipment shelter", 5)
    return lay


def generic(site_id: str, kind: str, center: LngLat, axis: float, size: float = 220.0) -> SiteLayout:
    f = Frame(center, axis)
    lay = SiteLayout(site_id, kind, center, axis)
    lay.footprint = [f.p(-size, -size * 0.7), f.p(size, -size * 0.7), f.p(size, size * 0.7), f.p(-size, size * 0.7), f.p(-size, -size * 0.7)]
    _poly(lay, [_r(p) for p in lay.footprint], "infra", "footprint", "Site area")
    _line(lay, [_r(p) for p in lay.footprint], "defence", "fence", "Perimeter fence")
    _poly(lay, f.rect(0, 0, size * 0.5, size * 0.3), "infra", "building", "Main building", 14)
    return lay


def _in_ring(p: LngLat, ring: list[LngLat]) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        (xi, yi), (xj, yj) = ring[i], ring[j]
        if (yi > p[1]) != (yj > p[1]) and p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


CORE_CLASSES = {"runway", "taxiway", "apron", "dispersal", "shelter", "hangar", "tower", "building", "radar", "bund",
                "fuel_tank", "ammo_bunker", "barracks", "motorpool", "fuel_point", "warehouse", "blast_pad", "arming_pad",
                "deice_pad", "runup_pad", "helipad", "revetment", "navaid", "ad_position"}


def _sample_ring(ring: list, spacing_m: float) -> list[LngLat]:
    """Ring outline every `spacing_m` plus the interior on a `spacing_m` grid (at least the centroid)."""
    ring = [(p[0], p[1]) for p in ring]
    out: list[LngLat] = []
    for a, b in zip(ring, ring[1:]):
        n = max(1, int(geo.haversine_m(a, b) / spacing_m))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    lo_x, hi_x = min(p[0] for p in ring), max(p[0] for p in ring)
    lo_y, hi_y = min(p[1] for p in ring), max(p[1] for p in ring)
    dy = spacing_m / 111_195.0
    dx = dy / math.cos(math.radians((lo_y + hi_y) / 2))
    y = lo_y + dy / 2
    while y < hi_y:
        x = lo_x + dx / 2
        while x < hi_x:
            if _in_ring((x, y), ring):
                out.append((x, y))
            x += dx
        y += dy
    m = len(ring) - 1 if len(ring) > 1 and ring[0] == ring[-1] else len(ring)
    out.append((sum(p[0] for p in ring[:m]) / m, sum(p[1] for p in ring[:m]) / m))
    return out


def placement_samples(lay: SiteLayout, spacing_m: float = 50.0) -> tuple[list[LngLat], list[LngLat], list[LngLat], list[LngLat]]:
    """(dry, wet, sea, core) for this layout to make sense on the ground:
    dry  - the whole footprint (fence line and interior on a `spacing_m` grid): dry land, clear of the national road
           graph (a fenced base can still enclose a small road that was closed for it);
    wet  - a naval base's berths and boat pads: water (fine ~110 m mask);
    sea  - its channel out: navigable sea (routing mask);
    core - built surfaces (runway, taxiways, aprons, shelters, buildings, tanks …) every ~35 m: clear of every road,
           minor roads included."""
    core = [q for f in lay.features if f["geometry"]["type"] == "Polygon" and f["properties"]["cls"] in CORE_CLASSES
            for q in _sample_ring(f["geometry"]["coordinates"][0], 35.0)]
    if lay.kind == "navbase":
        f = Frame(lay.center, lay.axis)
        # land side up to 60 m short of the quay (the coastline cell quantisation is ~110 m)
        dry = [f.p(u, v) for u in range(-650, -59, int(spacing_m)) for v in range(-520, 521, int(spacing_m))]
        wet = [(s.lng, s.lat) for kind in ("berth", "pad") for s in lay.spots.get(kind, [])] + [f.p(240, 0), f.p(300, 0)]
        return dry, wet, [f.p(600, 0), f.p(1500, 0)], core
    return _sample_ring(lay.footprint, spacing_m), [], [], core


def ad_battery_positions(center: LngLat, axis: float, n: int, radius_m: float, seed: int) -> list[tuple[LngLat, float]]:
    """Dispersed launcher positions around a battery centre, each facing outward."""
    rng = random.Random(seed)
    out = []
    for k in range(n):
        b = (axis + k * 360 / n + rng.uniform(-12, 12)) % 360
        out.append((geo.destination(center, b, radius_m * rng.uniform(0.8, 1.15)), b))
    return out
