"""Procedural, deterministic site layouts for the synthetic national world.

Sites are fictional placements (see AGENTS.md: no real military locations). Each layout is generated in a local
metric frame — u along the site axis (runway heading, pier direction), v to the right of it — then projected to
lng/lat. Every feature carries the sub-layer it belongs to so an operator who zooms into a base can see the
infrastructure, the aircraft, the logistics or the defence picture separately:

  infra      runways, taxiways, aprons, shelters, hangars, buildings, piers, fences
  aircraft   parking/shelter positions (the platforms themselves are entities)
  logistics  fuel farms (with fill level), ammunition storage, motor pools, supply routes
  defence    perimeter, guard posts, air-defence positions
  personnel  barracks and accommodation

Spots are named parking positions (shelter, apron stand, berth, motor-pool slot) with a heading; the order of
battle assigns platforms to them. Local routes (taxi routes, base roads) let ground traffic inside a base move on
the base's own surfaces.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import geo
from .motion import arc

LngLat = tuple[float, float]


@dataclass
class Spot:
    id: str
    lng: float
    lat: float
    heading: float
    kind: str  # shelter | qra | apron | berth | motorpool | helipad | pad
    front: LngLat | None = None  # taxi point in front of the spot (where the platform joins the base surface)


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

    def to_api(self) -> dict:
        return {"siteId": self.site_id, "kind": self.kind, "center": list(self.center), "axis": self.axis,
                "features": {"type": "FeatureCollection", "features": self.features},
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
RUNWAY_M = 2400.0
TAXI_V = 200.0


def airbase(site_id: str, center: LngLat, axis: float, seed: int, shelters_per_hub: int = 12, fuel_fill: list[float] | None = None) -> SiteLayout:
    rng = random.Random(seed)
    f = Frame(center, axis)
    L = RUNWAY_M
    lay = SiteLayout(site_id, "airbase", center, axis)
    # Ground pad: the base footprint (drawn under everything so a synthetic base reads as one installation).
    fence = [(-L / 2 - 600, -1450), (L / 2 + 700, -1450), (L / 2 + 700, 1250), (-L / 2 - 600, 1250)]
    lay.footprint = [f.p(u, v) for u, v in fence] + [f.p(*fence[0])]
    _poly(lay, [_r(p) for p in lay.footprint], "infra", "footprint", "Base area")
    _line(lay, [_r(p) for p in lay.footprint], "defence", "fence", "Perimeter fence")
    # Runway, markings, taxiways, connectors, apron
    _poly(lay, f.rect(0, 0, L, 45), "infra", "runway", f"Runway {round(axis / 10) % 36 or 36:02d}/{round((axis + 180) / 10) % 36 or 36:02d}")
    _line(lay, f.line([(-L / 2 + 60, 0), (L / 2 - 60, 0)]), "infra", "runway_centerline")
    for end in (-1, 1):
        for k in range(-3, 4):
            _poly(lay, f.rect(end * (L / 2 - 30), k * 5.5, 30, 1.8), "infra", "runway_marking")
    _point(lay, f.p(-L / 2 + 120, 0), "infra", "runway_label", f"{round(axis / 10) % 36 or 36:02d}", rotation=axis)
    _point(lay, f.p(L / 2 - 120, 0), "infra", "runway_label", f"{round((axis + 180) / 10) % 36 or 36:02d}", rotation=(axis + 180) % 360)
    _poly(lay, f.rect(0, TAXI_V, L - 160, 23), "infra", "taxiway", "Parallel taxiway")
    for u in (-L / 2 + 80, -L / 4, 0, L / 4, L / 2 - 80):
        _poly(lay, f.rect(u, TAXI_V / 2, TAXI_V - 20, 23, 90), "infra", "taxiway", "Connector")
    _poly(lay, f.rect(-300, 330, 420, 160), "infra", "apron", "Main apron")
    # Buildings
    for i, u in enumerate((-660, -470, -280)):
        _poly(lay, f.rect(u, 470, 62, 56), "infra", "hangar", f"Hangar {i + 1}", 18, model="hangar")
    _poly(lay, f.rect(-40, 440, 12, 12), "infra", "tower", "Control tower", 32, model="tower")
    _poly(lay, f.rect(160, 470, 52, 26), "infra", "building", "Base operations", 11)
    _poly(lay, f.rect(-120, -320, 14, 14), "defence", "radar", "Approach radar", 6, model="radar_rotating")
    # Fuel farm (logistics) with per-tank fill
    fills = fuel_fill or [round(rng.uniform(45, 95)) for _ in range(6)]
    _poly(lay, f.rect(560, 560, 150, 100), "logistics", "bund", "Fuel farm")
    for k in range(6):
        u, v = 510 + (k % 3) * 50, 535 + (k // 3) * 50
        _poly(lay, f.circle(u, v, 11), "logistics", "fuel_tank", f"Fuel tank {k + 1}", 13, fill=fills[k], model="fuel_tank")
    # Ammunition storage across the runway, dispersed
    for k in range(8):
        u, v = 700 + (k % 4) * 95, -1000 - (k // 4) * 110
        _poly(lay, f.rect(u, v, 22, 14, 90), "logistics", "ammo_bunker", f"Ammunition bunker {k + 1}", 5, model="bunker")
    _line(lay, f.line([(L / 2 - 80, TAXI_V), (L / 2 + 250, 0), (L / 2 + 250, -900), (1000, -1000), (700, -1000)]), "logistics", "base_road", "Ammunition road")
    # Barracks (personnel)
    for k in range(6):
        _poly(lay, f.rect(-980 + (k % 3) * 120, 700 + (k // 3) * 90, 70, 22), "personnel", "barracks", f"Barracks {k + 1}", 12, model="barracks")
    # Base roads: gate → apron → fuel farm; fuel bowser route
    gate = (-L / 2 - 600, 650)
    _line(lay, f.line([gate, (-1000, 620), (-500, 600), (0, 560), (480, 600)]), "logistics", "base_road", "Main base road")
    lay.routes["bowser"] = [f.p(480, 600), f.p(0, 560), f.p(-300, 420), f.p(-300, 250), f.p(0, TAXI_V), f.p(L / 4, TAXI_V)]
    _point(lay, f.p(*gate), "defence", "gate", "Main gate")
    # Dispersal hubs with hardened shelters on ring roads
    lay.spots["shelter"], lay.spots["qra"], lay.spots["apron"] = [], [], []
    for h, hu in enumerate((900.0, -900.0)):
        hv = 780.0
        hub = f.p(hu, hv)
        ring = arc(hub, 215, 0, 360, 10)
        _line(lay, [_r(p) for p in ring], "infra", "taxiway_line", f"Dispersal loop {'AB'[h]}")
        _poly(lay, [_r(p) for p in arc(hub, 228, 0, 360, 10)], "infra", "dispersal", f"Dispersal {'AB'[h]}")
        lane = [f.p(hu, TAXI_V), f.p(hu, hv - 215)]
        _line(lay, [_r(p) for p in lane], "infra", "taxiway_line", "Taxi lane")
        _poly(lay, f.rect(hu, (TAXI_V + hv - 215) / 2, hv - 215 - TAXI_V, 18, 90), "infra", "taxiway", "Taxi lane")
        for k in range(shelters_per_hub):
            ang = (axis + 200 + k * (300 / max(1, shelters_per_hub - 1))) % 360  # leave the gap toward the taxi lane
            front = geo.destination(hub, ang, 215)
            centre = geo.destination(hub, ang, 262)
            facing = (ang + 180) % 360  # open front faces the ring road
            ring_s = _shelter_ring(centre, facing)
            _poly(lay, ring_s, "infra", "shelter", f"Shelter {'AB'[h]}{k + 1}", 8, model="shelter", heading=facing)
            mouth = geo.destination(centre, facing, 21)  # parked nose-out on the shelter apron, ready to taxi
            lay.spots["shelter"].append(Spot(f"{site_id}:S{'AB'[h]}{k + 1}", mouth[0], mouth[1], facing, "shelter", front))
        lay.routes[f"hub{h}"] = [p for p in ring]
        lay.routes[f"lane{h}"] = lane
    # QRA shelters by the runway threshold
    for k in range(2):
        c = f.p(-L / 2 + 160 + k * 70, -150)
        facing = f.heading(0)
        _poly(lay, _shelter_ring(c, facing), "infra", "shelter", f"QRA shelter {k + 1}", 8, model="shelter", heading=facing, qra=True)
        mouth = geo.destination(c, facing, 21)
        lay.spots["qra"].append(Spot(f"{site_id}:Q{k + 1}", mouth[0], mouth[1], facing, "qra", f.p(-L / 2 + 160 + k * 70, -60)))
    _poly(lay, f.rect(-L / 2 + 195, -95, 160, 40), "infra", "taxiway", "QRA pad")
    for k in range(8):
        p = f.p(-470 + k * 50, 330)
        lay.spots["apron"].append(Spot(f"{site_id}:A{k + 1}", p[0], p[1], f.heading(90), "apron", f.p(-470 + k * 50, 260)))
    lay.runway = {"start": _r(f.p(-L / 2, 0)), "end": _r(f.p(L / 2, 0)), "heading": axis, "lengthM": L}
    return lay


def _shelter_ring(centre: LngLat, facing: float) -> list[list[float]]:
    g = Frame(centre, facing)
    return g.rect(0, 0, 30, 22)


def taxi_out(lay: SiteLayout, spot: Spot) -> list[LngLat]:
    """Ground route from a spot to the take-off threshold (ends on the runway centreline, facing the axis)."""
    f = Frame(lay.center, lay.axis)
    L = RUNWAY_M
    pts: list[LngLat] = [(spot.lng, spot.lat)]
    if spot.front:
        pts.append(spot.front)
    if spot.kind == "shelter":
        hub_idx = 0 if spot.id.split(":S")[1][0] == "A" else 1
        hu = 900.0 if hub_idx == 0 else -900.0
        ring = lay.routes[f"hub{hub_idx}"]
        exit_pt = f.p(hu, 780 - 215)
        pts += _ring_walk(ring, spot.front or (spot.lng, spot.lat), exit_pt)
        pts += [f.p(hu, TAXI_V)]
        pts += [f.p(-L / 2 + 80, TAXI_V), f.p(-L / 2 + 80, 30), f.p(-L / 2 + 70, 0)]
    elif spot.kind == "qra":
        pts += [f.p(-L / 2 + 120, -40), f.p(-L / 2 + 70, 0)]
    else:
        pts += [f.p(-L / 2 + 80, TAXI_V), f.p(-L / 2 + 80, 30), f.p(-L / 2 + 70, 0)]
    return _dedupe(pts)


def taxi_in(lay: SiteLayout, spot: Spot) -> list[LngLat]:
    """Ground route from the runway roll-out exit back to the spot."""
    f = Frame(lay.center, lay.axis)
    L = RUNWAY_M
    pts: list[LngLat] = [f.p(L / 2 - 80, 0), f.p(L / 2 - 80, TAXI_V)]
    if spot.kind == "shelter":
        hub_idx = 0 if spot.id.split(":S")[1][0] == "A" else 1
        hu = 900.0 if hub_idx == 0 else -900.0
        ring = lay.routes[f"hub{hub_idx}"]
        entry = f.p(hu, 780 - 215)
        pts += [f.p(hu, TAXI_V), entry]
        pts += _ring_walk(ring, entry, spot.front or (spot.lng, spot.lat))[1:]
    elif spot.kind == "qra":
        pts += [f.p(-L / 2 + 160, TAXI_V), f.p(-L / 2 + 120, -40)]
    else:
        pts += [f.p(-200, TAXI_V), f.p(-200, 260)]
    if spot.front:
        pts.append(spot.front)
    pts.append((spot.lng, spot.lat))
    return _dedupe(pts)


def _ring_walk(ring: list[LngLat], a: LngLat, b: LngLat) -> list[LngLat]:
    """Shortest walk along a closed ring polyline from the vertex nearest a to the vertex nearest b."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    ia = min(range(len(pts)), key=lambda i: geo.haversine_m(pts[i], a))
    ib = min(range(len(pts)), key=lambda i: geo.haversine_m(pts[i], b))
    n = len(pts)
    fwd = [pts[(ia + k) % n] for k in range((ib - ia) % n + 1)]
    back = [pts[(ia - k) % n] for k in range((ia - ib) % n + 1)]
    return fwd if len(fwd) <= len(back) else back


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


def placement_samples(lay: SiteLayout, spacing_m: float = 50.0) -> tuple[list[LngLat], list[LngLat], list[LngLat]]:
    """(dry, wet, sea): points that must be dry, road-free ground (the whole footprint: fence line and interior on a
    `spacing_m` grid), points that must be water (a naval base's berths and boat pads, fine ~110 m mask) and points
    that must be navigable sea (its channel out, routing mask) for this layout to make sense."""
    if lay.kind == "navbase":
        f = Frame(lay.center, lay.axis)
        # land side up to 60 m short of the quay (the coastline cell quantisation is ~110 m)
        dry = [f.p(u, v) for u in range(-650, -59, int(spacing_m)) for v in range(-520, 521, int(spacing_m))]
        wet = [(s.lng, s.lat) for kind in ("berth", "pad") for s in lay.spots.get(kind, [])] + [f.p(240, 0), f.p(300, 0)]
        return dry, wet, [f.p(600, 0), f.p(1500, 0)]
    ring = lay.footprint
    dry: list[LngLat] = []
    for a, b in zip(ring, ring[1:]):
        n = max(1, int(geo.haversine_m(a, b) / spacing_m))
        dry += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    lo_x, hi_x = min(p[0] for p in ring), max(p[0] for p in ring)
    lo_y, hi_y = min(p[1] for p in ring), max(p[1] for p in ring)
    dy = spacing_m / 111_195.0
    dx = dy / math.cos(math.radians((lo_y + hi_y) / 2))
    y = lo_y + dy / 2
    while y < hi_y:
        x = lo_x + dx / 2
        while x < hi_x:
            if _in_ring((x, y), ring):
                dry.append((x, y))
            x += dx
        y += dy
    return dry, [], []


def ad_battery_positions(center: LngLat, axis: float, n: int, radius_m: float, seed: int) -> list[tuple[LngLat, float]]:
    """Dispersed launcher positions around a battery centre, each facing outward."""
    rng = random.Random(seed)
    out = []
    for k in range(n):
        b = (axis + k * 360 / n + rng.uniform(-12, 12)) % 360
        out.append((geo.destination(center, b, radius_m * rng.uniform(0.8, 1.15)), b))
    return out
