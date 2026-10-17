"""Synthetic national order of battle at a representative national scale.

Every formation, platform and site here is fictional (AGENTS.md): designations are invented, sites are fictional
placements near public reference cities, and quantities are only of the right order of magnitude for a
mid-sized Nordic defence force. Platform *classes* are public, generic types (a delta-canard fighter, a tracked
IFV, a stealth corvette) so the picture reads realistically without asserting anything about real units.

The structure is a tree: service → formation (brigade, air wing, flotilla) → unit (battalion, squadron) →
sub-unit (company, flight) → platform. The client aggregates by echelon from this tree, so zooming out shows a
brigade where zooming in shows its companies and finally each vehicle on its road.

Movement is declared with `motion.MotionSpec`: ground platforms follow routes on the real road network
(`geonet`), police and ambulances roam real city streets, ships follow water routes, aircraft fly sorties that
start in their shelter, taxi, take off along the runway, fly a mission pattern and land again.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
import threading
from dataclasses import dataclass, field
from pathlib import Path as FsPath

from . import geo, sitegen
from .motion import MotionSpec, Path, densify, racetrack

ROUTE_CACHE = FsPath(__file__).resolve().parents[1] / "data" / "world_routes.json.gz"
ROUTE_CACHE_VERSION = 3

# Public reference points (city centres, coastal and sea waypoints), [lng, lat].
P: dict[str, tuple[float, float]] = {
    "stockholm": (18.07, 59.33), "uppsala": (17.64, 59.86), "enkoping": (17.08, 59.64), "norrtalje": (18.70, 59.76),
    "nykoping": (17.01, 58.75), "norrkoping": (16.19, 58.59), "linkoping": (15.62, 58.41), "vasteras": (16.55, 59.61),
    "orebro": (15.21, 59.27), "karlstad": (13.50, 59.38), "goteborg": (11.97, 57.71), "halmstad": (12.86, 56.67),
    "malmo": (13.00, 55.61), "helsingborg": (12.69, 56.05), "kristianstad": (14.16, 56.03), "karlskrona": (15.59, 56.16),
    "kalmar": (16.36, 56.66), "visby": (18.29, 57.64), "vaxjo": (14.81, 56.88), "jonkoping": (14.16, 57.78),
    "skovde": (13.85, 58.39), "gavle": (17.14, 60.67), "falun": (15.63, 60.61), "sundsvall": (17.31, 62.39),
    "ostersund": (14.64, 63.18), "umea": (20.26, 63.83), "skelleftea": (21.00, 64.75), "lulea": (22.15, 65.58),
    "boden": (21.69, 65.82), "kiruna": (20.22, 67.86), "haparanda": (24.14, 65.84), "ornskoldsvik": (18.72, 63.29),
    "harnosand": (17.94, 62.63), "arvidsjaur": (19.17, 65.59), "gallivare": (20.65, 67.13), "mora": (14.54, 61.00),
    "trollhattan": (12.29, 58.28), "uddevalla": (11.94, 58.35), "ystad": (13.82, 55.43), "oskarshamn": (16.44, 57.27),
    "vastervik": (16.63, 57.76), "soderhamn": (17.06, 61.30), "hudiksvall": (17.10, 61.73), "nynashamn": (17.95, 58.90),
    "ludvika": (15.19, 60.15), "eskilstuna": (16.51, 59.37), "motala": (15.04, 58.54), "borlange": (15.43, 60.49),
    "lidkoping": (13.16, 58.50), "kalix": (23.16, 65.85), "trelleborg": (13.16, 55.37), "simrishamn": (14.35, 55.56),
    "hemse": (18.37, 57.24), "slite": (18.80, 57.71), "nybro": (15.91, 56.74), "solleftea": (17.27, 63.17),
    # sea waypoints (open water)
    "sea_stockholm_e": (19.40, 59.30), "sea_gotland_e": (19.60, 57.60), "sea_gotland_s": (18.30, 56.80), "sea_gotland_ne": (19.40, 58.25),
    "sea_oland_s": (16.60, 55.95), "sea_oland_e": (17.30, 56.80), "sea_bornholm_n": (14.90, 55.60), "sea_hano": (14.60, 55.75), "sea_oresund": (12.70, 55.80),
    "sea_kattegat": (11.50, 57.30), "sea_kattegat_n": (11.20, 57.85), "sea_bothnia_s": (18.80, 61.60), "sea_bothnia_m": (19.90, 62.90),
    "sea_bothnia_n": (21.80, 64.60), "sea_bothnia_bay": (23.00, 65.30), "sea_landsort": (18.00, 58.60), "sea_aland": (19.30, 60.10),
}

COUNTY_OF = {
    "stockholm": "01", "norrtalje": "01", "nynashamn": "01", "uppsala": "03", "enkoping": "03", "nykoping": "04", "eskilstuna": "04",
    "norrkoping": "05", "linkoping": "05", "motala": "05", "jonkoping": "06", "vaxjo": "07", "kalmar": "08", "oskarshamn": "08",
    "vastervik": "08", "nybro": "08", "visby": "09", "hemse": "09", "slite": "09", "karlskrona": "10", "malmo": "12", "helsingborg": "12",
    "kristianstad": "12", "ystad": "12", "trelleborg": "12", "simrishamn": "12", "halmstad": "13", "goteborg": "14", "skovde": "14",
    "trollhattan": "14", "uddevalla": "14", "lidkoping": "14", "karlstad": "17", "orebro": "18", "vasteras": "19", "falun": "20",
    "mora": "20", "ludvika": "20", "borlange": "20", "gavle": "21", "soderhamn": "21", "hudiksvall": "21", "sundsvall": "22",
    "harnosand": "22", "ornskoldsvik": "22", "solleftea": "22", "ostersund": "23", "umea": "24", "skelleftea": "24", "lulea": "25",
    "boden": "25", "kiruna": "25", "haparanda": "25", "arvidsjaur": "25", "gallivare": "25", "kalix": "25",
}
COUNTY_SEATS = [("01", "Stockholm", "stockholm"), ("03", "Uppsala", "uppsala"), ("04", "Södermanland", "nykoping"), ("05", "Östergötland", "linkoping"),
                ("06", "Jönköping", "jonkoping"), ("07", "Kronoberg", "vaxjo"), ("08", "Kalmar", "kalmar"), ("09", "Gotland", "visby"),
                ("10", "Blekinge", "karlskrona"), ("12", "Skåne", "malmo"), ("13", "Halland", "halmstad"), ("14", "Västra Götaland", "goteborg"),
                ("17", "Värmland", "karlstad"), ("18", "Örebro", "orebro"), ("19", "Västmanland", "vasteras"), ("20", "Dalarna", "falun"),
                ("21", "Gävleborg", "gavle"), ("22", "Västernorrland", "harnosand"), ("23", "Jämtland", "ostersund"), ("24", "Västerbotten", "umea"),
                ("25", "Norrbotten", "lulea")]


# ---- tree node --------------------------------------------------------------------------------------------------
@dataclass
class Node:
    id: str
    label: str
    kind: str  # formation | fixed_wing | helicopter | multirotor | ground_vehicle | vessel | personnel | facility | infrastructure | unknown
    domain: str  # air | land | sea | site | infra | unknown
    layer: str
    sidc: str
    affiliation: str = "own"
    parent: str | None = None
    echelon: str | None = None  # team squad section platoon company battalion regiment brigade division service
    short: str = ""
    platform: str | None = None  # public class name, e.g. "Delta-canard fighter"
    model: str | None = None  # 3D model key (frontend/src/scene/three/models.ts)
    site: str | None = None
    region: str | None = None
    capabilities: list[str] = field(default_factory=list)
    motion: MotionSpec | None = None
    crew: int = 0
    range_km: float | None = None  # sensor / weapon / tasking reach used by analysis surfaces
    priority: int = 1
    tags: list[str] = field(default_factory=list)


@dataclass
class SiteDef:
    id: str
    label: str
    kind: str  # airbase navbase garrison depot hospital radar comms power port bridge telecom hq roadbase adsite police ems
    near: str
    offset_km: tuple[float, float]
    axis: float
    unit: str
    capabilities: list[str]
    affiliation: str = "own"
    sidc: str = ""
    layer: str = "sites.land"


SITES: list[SiteDef] = [
    SiteDef("hq-joint", "Joint Operations HQ", "hq", "enkoping", (6, 3), 30, "Joint Staff", ["command", "comms_hub"], sidc="SFGPUH----H-", layer="sites.land"),
    SiteDef("airbase-norr", "Airbase Norr", "airbase", "lulea", (-9, 4), 140, "Air Wing North", ["fighter", "fuel", "maintenance"], sidc="SFGPIBA---H-", layer="sites.air"),
    SiteDef("airbase-syd", "Airbase Syd", "airbase", "kristianstad", (9, -3), 10, "Air Wing South", ["fighter", "fuel", "maintenance"], sidc="SFGPIBA---H-", layer="sites.air"),
    SiteDef("airbase-vast", "Airbase Väst", "airbase", "lidkoping", (6, 3), 50, "Air Wing West", ["fighter", "fuel", "maintenance"], sidc="SFGPIBA---H-", layer="sites.air"),
    SiteDef("airbase-mitt", "Airbase Mitt", "airbase", "uppsala", (-5, 6), 10, "Air Wing Centre", ["transport", "aew", "fuel"], sidc="SFGPIBA---H-", layer="sites.air"),
    SiteDef("airbase-ost", "Heliport Öst", "airbase", "linkoping", (-4, 4), 110, "Helicopter Wing", ["helicopter", "maintenance", "fuel"], sidc="SFGPIBA---H-", layer="sites.air"),
    SiteDef("garrison-norr", "Garrison Norr", "garrison", "boden", (-4, 2), 90, "Brigade North", ["armour", "logistics", "medical"], sidc="SFGPIB----H-"),
    SiteDef("garrison-fjall", "Garrison Fjäll", "garrison", "arvidsjaur", (2, 1), 70, "Brigade North", ["rangers", "winter"], sidc="SFGPIB----H-"),
    SiteDef("garrison-mitt", "Garrison Mitt", "garrison", "enkoping", (-8, -4), 20, "Brigade Centre", ["mech_infantry", "logistics"], sidc="SFGPIB----H-"),
    SiteDef("garrison-syd", "Garrison Syd", "garrison", "kristianstad", (-6, 5), 160, "Brigade South", ["armour", "mech_infantry"], sidc="SFGPIB----H-"),
    SiteDef("garrison-vast", "Garrison Väst", "garrison", "skovde", (3, -2), 0, "Brigade West", ["armour", "training"], sidc="SFGPIB----H-"),
    SiteDef("garrison-gotland", "Garrison Gotland", "garrison", "visby", (4, -6), 30, "Battlegroup Gotland", ["mech_infantry", "air_defence"], sidc="SFGPIB----H-"),
    SiteDef("navbase-syd", "Naval Base Syd", "navbase", "karlskrona", (3, -2.5), 160, "Naval Flotilla South", ["corvette", "mine_warfare", "submarine", "fuel"], sidc="SFGPIBN-----", layer="sites.sea"),
    SiteDef("navbase-ost", "Naval Base Öst", "navbase", "nynashamn", (2.5, -1.5), 120, "Naval Flotilla East", ["patrol_boat", "amphibious", "fuel"], sidc="SFGPIBN-----", layer="sites.sea"),
    SiteDef("navbase-vast", "Naval Station Väst", "navbase", "goteborg", (-9, -4), 260, "Naval Station West", ["patrol_boat", "coast_guard"], sidc="SFGPIBN-----", layer="sites.sea"),
    SiteDef("depot-mitt", "Central Depot Mitt", "depot", "orebro", (6, 4), 0, "Logistics Regiment", ["ammunition", "spares", "fuel"], sidc="SFGPIRP-----", layer="sites.logistics"),
    SiteDef("depot-norr", "Depot Norr", "depot", "ostersund", (3, -3), 0, "Logistics Regiment", ["fuel", "spares", "winter"], sidc="SFGPIRP-----", layer="sites.logistics"),
    SiteDef("depot-syd", "Depot Syd", "depot", "vaxjo", (-5, 2), 0, "Logistics Regiment", ["ammunition", "fuel"], sidc="SFGPIRP-----", layer="sites.logistics"),
    SiteDef("depot-bothnia", "Depot Bothnia", "depot", "umea", (5, 2), 0, "Logistics Regiment", ["fuel", "spares"], sidc="SFGPIRP-----", layer="sites.logistics"),
    SiteDef("hospital-mitt", "Field Hospital Mitt", "hospital", "vasteras", (4, 2), 0, "Medical Battalion", ["medical"], sidc="SFGPIXH-----", layer="sites.medical"),
    SiteDef("hospital-norr", "Field Hospital Norr", "hospital", "boden", (3, -2), 0, "Medical Battalion", ["medical"], sidc="SFGPIXH-----", layer="sites.medical"),
    SiteDef("radar-gotland", "Sensor Site Gotland", "radar", "visby", (12, 8), 0, "Air Surveillance", ["radar", "air_picture"], sidc="SFGPIR------", layer="infra.sensors"),
    SiteDef("radar-norr", "Sensor Site Norr", "radar", "kiruna", (6, -4), 0, "Air Surveillance", ["radar", "air_picture"], sidc="SFGPIR------", layer="infra.sensors"),
    SiteDef("radar-syd", "Sensor Site Syd", "radar", "ystad", (8, 3), 0, "Sea Surveillance", ["radar", "sea_picture"], sidc="SFGPIR------", layer="infra.sensors"),
    SiteDef("radar-vast", "Sensor Site Väst", "radar", "uddevalla", (-9, 2), 0, "Sea Surveillance", ["radar", "sea_picture"], sidc="SFGPIR------", layer="infra.sensors"),
    SiteDef("radar-ost", "Sensor Site Öst", "radar", "norrtalje", (8, -6), 0, "Air Surveillance", ["radar", "air_picture", "sea_picture"], sidc="SFGPIR------", layer="infra.sensors"),
    SiteDef("radar-bothnia", "Sensor Site Bothnia", "radar", "harnosand", (6, 3), 0, "Air Surveillance", ["radar", "air_picture"], sidc="SFGPIR------", layer="infra.sensors"),
    SiteDef("comms-mitt", "Comms Node Mitt", "comms", "eskilstuna", (2, 6), 0, "Signals Regiment", ["comms_hub"], sidc="SFGPIUT-----", layer="infra.comms"),
    SiteDef("comms-norr", "Comms Node Norr", "comms", "sundsvall", (-3, 5), 0, "Signals Regiment", ["comms_hub"], sidc="SFGPIUT-----", layer="infra.comms"),
    SiteDef("comms-syd", "Comms Node Syd", "comms", "jonkoping", (5, -5), 0, "Signals Regiment", ["comms_hub"], sidc="SFGPIUT-----", layer="infra.comms"),
    SiteDef("comms-fjall", "Comms Node Fjäll", "comms", "gallivare", (-4, 3), 0, "Signals Regiment", ["comms_hub"], sidc="SFGPIUT-----", layer="infra.comms"),
    SiteDef("power-mitt", "Grid Node Mälardalen", "power", "vasteras", (-7, -3), 0, "Grid operator (public)", ["power"], "civil", "SNGPIUE-----", "infra.power"),
    SiteDef("power-syd", "Grid Node Skåne", "power", "helsingborg", (10, 4), 0, "Grid operator (public)", ["power"], "civil", "SNGPIUE-----", "infra.power"),
    SiteDef("power-norr", "Grid Node Norrland", "power", "skelleftea", (-8, -2), 0, "Grid operator (public)", ["power"], "civil", "SNGPIUE-----", "infra.power"),
    SiteDef("power-vast", "Grid Node Väst", "power", "trollhattan", (4, 3), 0, "Grid operator (public)", ["power"], "civil", "SNGPIUE-----", "infra.power"),
    SiteDef("port-goteborg", "Port Göteborg (civil)", "port", "goteborg", (-4, -3), 0, "Port authority (public)", ["port", "fuel"], "civil", "SNGPIBN-----", "infra.transport"),
    SiteDef("port-trelleborg", "Port Trelleborg (civil)", "port", "trelleborg", (0, 0), 0, "Port authority (public)", ["port"], "civil", "SNGPIBN-----", "infra.transport"),
    SiteDef("port-lulea", "Port Luleå (civil)", "port", "lulea", (3, -3), 0, "Port authority (public)", ["port", "fuel"], "civil", "SNGPIBN-----", "infra.transport"),
    SiteDef("bridge-oresund", "Öresund crossing (civil)", "bridge", "malmo", (-6, 0), 0, "Transport authority (public)", ["transport"], "civil", "SNGPIT------", "infra.transport"),
    SiteDef("bridge-hoga", "Höga Kusten crossing (civil)", "bridge", "harnosand", (4, 8), 0, "Transport authority (public)", ["transport"], "civil", "SNGPIT------", "infra.transport"),
    SiteDef("telecom-stockholm", "Telecom core Stockholm (civil)", "telecom", "stockholm", (-3, 5), 0, "Telecom operator (public)", ["telecom"], "civil", "SNGPIUT-----", "infra.telecom"),
    SiteDef("telecom-goteborg", "Telecom core Göteborg (civil)", "telecom", "goteborg", (5, 4), 0, "Telecom operator (public)", ["telecom"], "civil", "SNGPIUT-----", "infra.telecom"),
]

# Undersea cables and pipelines: approximate, publicly reported corridors drawn for illustration (not survey data).
CABLES: list[dict] = [
    {"id": "cable-gotland-lt", "label": "Gotland–Lithuania data cable (approx.)", "kind": "data", "coords": [[18.85, 57.43], [19.6, 57.0], [20.4, 56.5], [21.07, 56.05]]},
    {"id": "cable-gotland-mainland", "label": "Gotland–mainland power link (approx.)", "kind": "power", "coords": [[16.66, 57.75], [17.3, 57.68], [17.9, 57.63], [18.25, 57.60]]},
    {"id": "cable-nordbalt", "label": "Sweden–Lithuania power link (approx.)", "kind": "power", "coords": [[16.2, 56.55], [17.2, 56.25], [18.8, 55.95], [20.2, 55.75], [21.1, 55.7]]},
    {"id": "cable-fi-de", "label": "Finland–Germany data cable (approx.)", "kind": "data", "coords": [[24.9, 60.15], [22.6, 59.6], [20.6, 58.6], [19.75, 57.6], [18.9, 56.6], [16.6, 55.3], [13.1, 54.4]]},
    {"id": "pipe-fi-ee", "label": "Finland–Estonia gas pipeline (approx.)", "kind": "gas", "coords": [[24.0, 60.1], [24.05, 59.75], [24.1, 59.35]]},
]

AREAS_STATIC = [
    {"id": "area-gotland", "label": "Gotland defence sector", "kind": "operational_area", "ring": [[17.9, 56.8], [19.6, 56.8], [19.6, 58.1], [17.9, 58.1], [17.9, 56.8]], "requires": ["garrison-gotland", "radar-gotland", "fm-coy-g-ad"], "priority": 1},
    {"id": "area-oresund", "label": "Öresund approaches", "kind": "operational_area", "ring": [[12.2, 55.3], [13.4, 55.3], [13.4, 56.5], [12.2, 56.5], [12.2, 55.3]], "requires": ["navbase-syd", "radar-syd", "airbase-syd"], "priority": 2},
    {"id": "area-bothnia", "label": "Bothnia northern approaches", "kind": "operational_area", "ring": [[21.0, 64.3], [24.5, 64.3], [24.5, 66.2], [21.0, 66.2], [21.0, 64.3]], "requires": ["airbase-norr", "garrison-norr", "port-lulea"], "priority": 2},
    {"id": "area-malardalen", "label": "Mälardalen command region", "kind": "operational_area", "ring": [[16.0, 59.0], [18.9, 59.0], [18.9, 60.1], [16.0, 60.1], [16.0, 59.0]], "requires": ["hq-joint", "comms-mitt", "power-mitt", "telecom-stockholm"], "priority": 1},
    {"id": "area-vast", "label": "West coast approaches", "kind": "operational_area", "ring": [[11.0, 57.0], [12.6, 57.0], [12.6, 58.6], [11.0, 58.6], [11.0, 57.0]], "requires": ["navbase-vast", "port-goteborg", "radar-vast"], "priority": 3},
    {"id": "zone-exercise-skovde", "label": "Exercise area Väst (restricted)", "kind": "restricted_zone", "ring": [[13.6, 58.3], [14.2, 58.3], [14.2, 58.6], [13.6, 58.6], [13.6, 58.3]], "requires": [], "priority": 4},
]


def pt(ref: str | tuple[float, float], east_km: float = 0, north_km: float = 0) -> tuple[float, float]:
    base = P[ref] if isinstance(ref, str) else ref
    p = geo.destination(base, 90, east_km * 1000) if east_km else base
    return geo.destination(p, 0, north_km * 1000) if north_km else p


# ---- route cache ------------------------------------------------------------------------------------------------
class RouteCache:
    """Road/sea/street routes are expensive to compute; results persist in a committed gzip file keyed by request."""

    def __init__(self, path: FsPath = ROUTE_CACHE) -> None:
        self.path = path
        self.data: dict[str, list[list[float]]] = {}
        self.dirty = False
        self.lock = threading.Lock()
        if path.exists():
            try:
                blob = json.loads(gzip.decompress(path.read_bytes()))
                if blob.get("version") == ROUTE_CACHE_VERSION:
                    self.data = blob["routes"]
            except Exception:  # corrupt cache: rebuild
                self.data = {}

    @staticmethod
    def key(*parts) -> str:
        return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def get(self, key: str, compute) -> list[tuple[float, float]]:
        with self.lock:
            hit = self.data.get(key)
        if hit is not None:
            return [(p[0], p[1]) for p in hit]
        coords = compute()
        with self.lock:
            self.data[key] = [[round(p[0], 6), round(p[1], 6)] for p in coords]
            self.dirty = True
        return coords

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps({"version": ROUTE_CACHE_VERSION, "routes": self.data}, separators=(",", ":")).encode()
        self.path.write_bytes(gzip.compress(blob, 9))
        self.dirty = False


def _geonet():
    try:
        from . import geonet  # noqa: PLC0415  (optional until the network data is built)
        return geonet
    except Exception:
        return None


def on_gotland(p: tuple[float, float]) -> bool:
    return 18.0 <= p[0] <= 19.4 and 56.85 <= p[1] <= 58.0


def road_net(p: tuple[float, float]):
    """Gotland has no fixed link: anything on the island routes on the island's own graph."""
    gn = _geonet()
    if not gn:
        return None
    if on_gotland(p):
        try:
            return gn.city("gotland")
        except KeyError:
            return None
    return gn.national()


def road_route(cache: RouteCache, a: tuple[float, float], b: tuple[float, float]) -> list[tuple[float, float]]:
    def compute():
        net = road_net(a)
        r = net.route(a, b) if net and on_gotland(a) == on_gotland(b) else None
        return r.coords if r else densify([a, b], 2000)
    return cache.get(RouteCache.key("road", a, b), compute)


def street_loop(cache: RouteCache, city: str, seed: int, start: tuple[float, float], length_m: float) -> list[tuple[float, float]]:
    def compute():
        gn = _geonet()
        try:
            return gn.city(city).random_loop(seed, start, length_m).coords if gn else _fallback_loop(start, length_m, seed)
        except KeyError:
            return _fallback_loop(start, length_m, seed)
    return cache.get(RouteCache.key("loop", city, seed, start, length_m), compute)


def sea_route(cache: RouteCache, a: tuple[float, float], b: tuple[float, float]) -> list[tuple[float, float]]:
    def compute():
        gn = _geonet()
        r = gn.sea().route(a, b) if gn else None
        return r.coords if r else densify([a, b], 3000)
    return cache.get(RouteCache.key("sea", a, b), compute)


def _fallback_loop(start: tuple[float, float], length_m: float, seed: int) -> list[tuple[float, float]]:
    r = length_m / (2 * math.pi)
    rng = random.Random(seed)
    c = geo.destination(start, rng.uniform(0, 360), r)
    ring = [geo.destination(c, b, r) for b in range(0, 361, 15)]
    return ring


def chain(*legs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for leg in legs:
        for p in leg:
            if not out or geo.haversine_m(out[-1], p) > 0.5:
                out.append(p)
    return out


# ---- builders ---------------------------------------------------------------------------------------------------
class Orbat:
    def __init__(self, seed: int = 20261016, cache: RouteCache | None = None) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.cache = cache or RouteCache()
        self.nodes: dict[str, Node] = {}
        self.sites: dict[str, tuple[float, float]] = {}
        self.layouts: dict[str, sitegen.SiteLayout] = {}
        self.routes: dict[str, Path] = {}
        self.used_spots: set[str] = set()
        self._build()
        self.cache.save()

    # -- helpers
    def add(self, n: Node) -> Node:
        if n.id in self.nodes:
            raise ValueError(f"duplicate id {n.id}")
        self.nodes[n.id] = n
        return n

    def formation(self, id_: str, label: str, short: str, sidc: str, echelon: str, parent: str | None, layer: str, domain: str, affiliation: str = "own", region: str | None = None, caps: list[str] | None = None) -> Node:
        return self.add(Node(id_, label, "formation", domain, layer, sidc, affiliation, parent, echelon, short, region=region, capabilities=caps or []))

    def spot(self, site: str, *kinds: str) -> sitegen.Spot:
        for kind in kinds:
            for s in self.layouts[site].spots.get(kind, []):
                if s.id not in self.used_spots:
                    self.used_spots.add(s.id)
                    return s
        raise RuntimeError(f"no free {'/'.join(kinds)} spot at {site}")

    def region_of(self, p: tuple[float, float]) -> str | None:
        best = min(COUNTY_OF, key=lambda k: geo.haversine_m(P[k], p))
        return COUNTY_OF[best]

    def shared_route(self, rid: str, coords: list[tuple[float, float]], speed: float, alts: list[float | None] | None = None) -> Path:
        if rid not in self.routes:
            pts = [(c[0], c[1], alts[i] if alts else None) for i, c in enumerate(coords)]
            self.routes[rid] = Path(pts, [speed] * max(1, len(pts) - 1))
        return self.routes[rid]

    # -- build
    def _build(self) -> None:
        self._sites()
        self.formation("fm-sweden", "National forces", "SE", "SFGPU-------", "service", None, "forces", "land")
        self._air_force()
        self._army()
        self._navy()
        self._home_guard()
        self._civil()
        self._unknowns()

    def _sites(self) -> None:
        for s in SITES:
            c = pt(s.near, *s.offset_km)
            self.sites[s.id] = c
            seed = int(hashlib.md5(s.id.encode()).hexdigest()[:8], 16)
            if s.kind == "airbase":
                lay = sitegen.airbase(s.id, c, s.axis, seed, shelters_per_hub=12 if s.id != "airbase-ost" else 6)
            elif s.kind == "navbase":
                lay = sitegen.navbase(s.id, c, s.axis, seed, piers=4 if s.id == "navbase-syd" else 3)
            elif s.kind == "garrison":
                lay = sitegen.garrison(s.id, c, s.axis, seed)
            elif s.kind == "depot":
                lay = sitegen.depot(s.id, c, s.axis, seed)
            elif s.kind == "radar":
                lay = sitegen.radar(s.id, c, s.axis)
            else:
                lay = sitegen.generic(s.id, s.kind, c, s.axis, 160 if s.affiliation == "civil" else 220)
            self.layouts[s.id] = lay
            kind = "facility" if s.kind in ("airbase", "navbase", "garrison", "depot", "hospital", "hq") else "infrastructure"
            self.add(Node(s.id, s.label, kind, "site" if kind == "facility" else "infra", s.layer, s.sidc or "SFGPI-------", s.affiliation, None, None,
                          s.label.split(" (")[0], None, None, s.id, COUNTY_OF.get(s.near), s.capabilities, MotionSpec("static", pos=(c[0], c[1], None)),
                          crew=400 if kind == "facility" else 12, range_km=180 if s.kind == "radar" else None, priority=3 if kind == "facility" else 2, tags=[s.kind, s.unit]))

    # -- air -------------------------------------------------------------------------------------------------------
    def _sortie(self, base: str, spot: sitegen.Spot, mission: list[tuple[float, float]], cruise_alt: float, cruise_mps: float, laps: int = 1,
                climb_alt: float = 600.0) -> Path:
        """Shelter → taxi → take-off roll → climb → mission pattern × laps → approach → landing → taxi back."""
        lay = self.layouts[base]
        rw = lay.runway
        assert rw
        axis = rw["heading"]
        start = tuple(rw["start"])
        out_taxi = sitegen.taxi_out(lay, spot)
        verts: list[tuple[float, float, float | None]] = []
        speeds: list[float] = []

        def add(p, alt, v):
            if verts and geo.haversine_m(verts[-1][:2], p) < 0.5 and verts[-1][2] == alt:
                return
            if verts:
                speeds.append(v)
            verts.append((p[0], p[1], alt))

        for p in out_taxi:
            add(p, None, 8.0)
        roll = [geo.destination(start, axis, d) for d in (100, 300, 650, 1150, 1550)]
        for p, v in zip(roll, (8.0, 25.0, 50.0, 72.0, 82.0)):
            add(p, None, v)
        lift = geo.destination(start, axis, 1700)
        add(lift, 30.0, 88.0)
        climb1 = geo.destination(start, axis, 6000)
        add(climb1, climb_alt, 120.0)
        # turn toward the mission entry, climbing to cruise
        entry = mission[0]
        mid = geo.interpolate(climb1, entry, 0.25)
        add(mid, cruise_alt * 0.7, cruise_mps * 0.8)
        for _ in range(laps):
            for p in mission:
                add(p, cruise_alt, cruise_mps)
        # recovery: from the mission back to a 15 km final on the runway axis
        faf = geo.destination(start, axis + 180, 15000)
        iaf = geo.destination(start, axis + 180, 30000)
        add(geo.interpolate(mission[-1], iaf, 0.6), cruise_alt * 0.6, cruise_mps * 0.9)
        add(iaf, 1200.0, 140.0)
        add(faf, 600.0, 85.0)
        add(geo.destination(start, axis, 300), 15.0, 75.0)
        add(geo.destination(start, axis, 360), None, 70.0)
        add(geo.destination(start, axis, 1100), None, 45.0)
        add(geo.destination(start, axis, 1900), None, 20.0)
        for p in sitegen.taxi_in(lay, spot):
            add(p, None, 8.0)
        return Path(verts, speeds)

    def _circuit(self, base: str, spot: sitegen.Spot) -> Path:
        """Continuous training circuits: taxi out, three touch-and-go circuits at 450 m, full-stop landing, taxi in."""
        lay = self.layouts[base]
        rw = lay.runway
        assert rw
        axis = rw["heading"]
        start = tuple(rw["start"])
        side = axis + 90
        up = geo.destination(start, axis, 6500)
        cross1 = geo.destination(up, side, 3500)
        down0 = geo.destination(cross1, axis + 180, 6500 + 4500)
        base_leg = geo.destination(down0, side + 180, 3500)
        circuit = [up, cross1, down0, base_leg]
        mission = []
        for _ in range(3):
            mission += circuit
        return self._sortie(base, spot, mission, 450.0, 110.0, laps=1, climb_alt=300.0)

    def _air_force(self) -> None:
        self.formation("fm-air", "Air Force", "AF", "SFAPM-------", "service", "fm-sweden", "air", "air")
        wings = [
            ("aw-n", "Air Wing North", "AW N", "airbase-norr", [("sq-n1", "1st Fighter Squadron", 12), ("sq-n2", "2nd Fighter Squadron", 12)],
             [racetrack(pt("sea_bothnia_bay"), 60, 70_000, 14_000), racetrack(pt("kalix", 0, 60), 150, 60_000, 12_000)]),
            ("aw-s", "Air Wing South", "AW S", "airbase-syd", [("sq-s1", "3rd Fighter Squadron", 12), ("sq-s2", "4th Fighter Squadron", 12)],
             [racetrack(pt("sea_gotland_s"), 30, 80_000, 15_000), racetrack(pt("sea_bornholm_n"), 80, 60_000, 12_000)]),
            ("aw-w", "Air Wing West", "AW W", "airbase-vast", [("sq-w1", "5th Fighter Squadron", 12), ("sq-w2", "6th Fighter Squadron", 12)],
             [racetrack(pt("sea_kattegat"), 20, 70_000, 13_000), racetrack(pt("sea_aland"), 160, 70_000, 14_000)]),
        ]
        for wid, wlabel, wshort, base, sqs, caps in wings:
            self.formation(f"fm-{wid}", wlabel, wshort, "SFAPMFF---H-", "regiment", "fm-air", "air.fighter", "air", region=self.region_of(self.sites[base]))
            tail = 0
            for si, (sqid, sqlabel, n) in enumerate(sqs):
                self.formation(f"fm-{sqid}", sqlabel, sqlabel.split(" ")[0], "SFAPMFF---F-", "battalion", f"fm-{wid}", "air.fighter", "air")
                for fl in range(n // 4):
                    fid = f"fm-{sqid}-f{fl + 1}"
                    self.formation(fid, f"{sqlabel.split(' ')[0]} flight {'ABC'[fl]}", f"{'ABC'[fl]}", "SFAPMFF---D-", "platoon", f"fm-{sqid}", "air.fighter", "air")
                    for k in range(4):
                        tail += 1
                        acid = f"{wid}-{tail:02d}"
                        qra = si == 0 and fl == 0 and k < 2
                        spot = self.spot(base, "qra" if qra else "shelter")
                        pair = (tail - 1) // 2
                        node = Node(acid, f"{wshort} {tail:02d}", "fixed_wing", "air", "air.fighter", "SFAPMFF-----", "own", fid, None, f"{tail:02d}",
                                    "Delta-canard multirole fighter", "fighter", base, self.region_of(self.sites[base]),
                                    ["air_patrol", "intercept", "isr"] + (["qra"] if qra else []), crew=1, range_km=600)
                        if qra:
                            node.motion = MotionSpec("static", pos=(spot.lng, spot.lat, None), heading=spot.heading, fuel_start=100)
                            node.tags.append("QRA 15 min")
                        elif pair in (1, 2, 4):
                            cap = caps[pair % len(caps)]
                            path = self._sortie(base, spot, cap, 7000 + 500 * (pair % 3), 220.0, laps=2)
                            node.motion = MotionSpec("path", path=path, start_s=300 + pair * 1700, offset_s=10.0 if tail % 2 == 0 else 0.0, hold_s=2400,
                                                     mode="loop", airborne=True, fuel_start=100, fuel_burn_per_km=0.055)
                        elif pair == 6:
                            node.motion = MotionSpec("path", path=self._circuit(base, spot), start_s=120 + k * 45, hold_s=420, mode="loop", airborne=True,
                                                     fuel_start=100, fuel_burn_per_km=0.08)
                        else:
                            node.motion = MotionSpec("static", pos=(spot.lng, spot.lat, None), heading=spot.heading, fuel_start=round(self.rng.uniform(60, 100)))
                        self.add(node)
        # Air Wing Centre: transport, AEW, SIGINT
        self.formation("fm-aw-c", "Air Wing Centre", "AW C", "SFAPMFC---H-", "regiment", "fm-air", "air.transport", "air", region="03")
        self.formation("fm-sq-tr", "Transport Squadron", "Tpt Sqn", "SFAPMFC---F-", "battalion", "fm-aw-c", "air.transport", "air")
        self.formation("fm-sq-aew", "Airborne Surveillance Squadron", "ASC Sqn", "SFAPMFRW--F-", "battalion", "fm-aw-c", "air.transport", "air")
        routes_tr = [["airbase-norr", "airbase-syd"], ["airbase-syd", "garrison-gotland"], ["airbase-vast", "airbase-norr"]]
        for k in range(5):
            spot = self.spot("airbase-mitt", "shelter" if k < 3 else "apron", "shelter")
            node = Node(f"tr-{k + 1:02d}", f"Transport {k + 1:02d}", "fixed_wing", "air", "air.transport", "SFAPMFC-----", "own", "fm-sq-tr", None, f"T{k + 1}",
                        "Four-engine tactical airlifter", "transport", "airbase-mitt", "03", ["transport", "medevac"], crew=5, range_km=3000)
            if k < 3:
                mission = [self.sites[s] for s in routes_tr[k]]
                node.motion = MotionSpec("path", path=self._sortie("airbase-mitt", spot, mission, 5500, 150.0), start_s=600 + k * 2900, hold_s=3600,
                                         mode="loop", airborne=True, fuel_start=100, fuel_burn_per_km=0.03)
            else:
                node.motion = MotionSpec("static", pos=(spot.lng, spot.lat, None), heading=spot.heading, fuel_start=90)
            self.add(node)
        for k, (model, plat, label, alt) in enumerate([("aew", "Business-jet airborne early warning", "AEW 01", 9500), ("aew", "Business-jet airborne early warning", "AEW 02", 9500),
                                                       ("sigint", "Twin-jet signals intelligence", "SIGINT 01", 10500)]):
            spot = self.spot("airbase-mitt", "shelter")
            orbit = racetrack(pt("sea_gotland_ne", -30, -20), 30, 160_000, 25_000) if k != 2 else racetrack(pt("sea_gotland_e", 20, -60), 10, 120_000, 22_000)
            node = Node(f"aew-{k + 1:02d}", label, "fixed_wing", "air", "air.transport", "SFAPMFRW----" if model == "aew" else "SFAPMFRX----", "own", "fm-sq-aew", None,
                        label, plat, model, "airbase-mitt", "03", ["isr", "air_picture"] + (["sigint"] if k == 2 else []), crew=6, range_km=450 if model == "aew" else 300)
            if k != 1:
                node.motion = MotionSpec("path", path=self._sortie("airbase-mitt", spot, orbit, alt, 190.0, laps=3), start_s=200 + k * 3000, hold_s=5400,
                                         mode="loop", airborne=True, fuel_start=100, fuel_burn_per_km=0.02)
            else:
                node.motion = MotionSpec("static", pos=(spot.lng, spot.lat, None), heading=spot.heading, fuel_start=100)
            self.add(node)
        # Helicopter wing: medium (NH90 class), utility (UH-60 class), light (A109 class)
        self.formation("fm-hw", "Helicopter Wing", "HW", "SFAPMH----H-", "regiment", "fm-air", "air.rotary", "air", region="05")
        hel = [("hs-1", "Helicopter Squadron Öst", "airbase-ost", [("heli_medium", 4), ("heli_utility", 6), ("heli_light", 4)]),
               ("hs-2", "Helicopter Squadron Norr", "airbase-norr", [("heli_medium", 3), ("heli_utility", 3)]),
               ("hs-3", "Helicopter Squadron Syd", "airbase-syd", [("heli_light", 3), ("heli_medium", 2)])]
        missions = {
            "hs-1": [[pt("norrkoping"), pt("nykoping"), self.sites["hospital-mitt"]], [pt("visby"), self.sites["radar-gotland"], pt("hemse")], [pt("vastervik"), pt("oskarshamn")]],
            "hs-2": [[self.sites["garrison-norr"], pt("arvidsjaur"), self.sites["garrison-fjall"]], [pt("sea_bothnia_bay"), pt("haparanda")]],
            "hs-3": [[self.sites["navbase-syd"], pt("sea_hano"), pt("sea_bornholm_n")], [pt("simrishamn"), pt("ystad")]],
        }
        for hid, hlabel, base, mix in hel:
            self.formation(f"fm-{hid}", hlabel, hlabel.split(" ")[-1], "SFAPMH----F-", "battalion", "fm-hw", "air.rotary", "air")
            n = 0
            for model, count in mix:
                for _ in range(count):
                    n += 1
                    spot = self.spot(base, "apron", "shelter")
                    sidc = {"heli_medium": "SFAPMHU-----", "heli_utility": "SFAPMHU-----", "heli_light": "SFAPMHH-----"}[model]
                    plat = {"heli_medium": "Medium transport helicopter", "heli_utility": "Utility helicopter", "heli_light": "Light helicopter"}[model]
                    node = Node(f"{hid}-{n:02d}", f"{hlabel.split(' ')[-1]} {n:02d}", "helicopter", "air", "air.rotary", sidc, "own", f"fm-{hid}", None, f"H{n}",
                                plat, model, base, self.region_of(self.sites[base]), ["medevac", "sar", "transport"] + (["asw"] if model == "heli_medium" and hid == "hs-3" else []),
                                crew=4, range_km=250)
                    ms = missions[hid]
                    if n <= len(ms):
                        legs = ms[n - 1]
                        path = self._heli_sortie(base, spot, legs)
                        node.motion = MotionSpec("path", path=path, start_s=150 + n * 900, hold_s=1800, mode="loop", airborne=True, fuel_start=100, fuel_burn_per_km=0.25)
                    else:
                        node.motion = MotionSpec("static", pos=(spot.lng, spot.lat, None), heading=spot.heading, fuel_start=round(self.rng.uniform(70, 100)))
                    self.add(node)
        # UAV detachment
        self.formation("fm-uav", "UAV Squadron", "UAV", "SFAPMFQ---F-", "battalion", "fm-air", "air.uav", "air")
        for k, (gar, orbit_c) in enumerate([("garrison-norr", pt("haparanda", -15, 5)), ("garrison-gotland", pt("hemse", 15, 0)), ("garrison-syd", pt("simrishamn", 5, -12)),
                                            ("garrison-mitt", pt("norrtalje", 15, 0))]):
            c = self.sites[gar]
            loop = [geo.destination(orbit_c, b, 6000) for b in range(0, 361, 20)]
            path_pts = [(c[0], c[1], None), (c[0], c[1], 300.0)] + [(p[0], p[1], 1500.0) for p in loop] * 3 + [(c[0], c[1], 300.0), (c[0], c[1], None)]
            speeds = [5.0] + [45.0] * (len(path_pts) - 3) + [5.0]
            self.add(Node(f"uav-{k + 1:02d}", f"UAV {k + 1:02d}", "fixed_wing", "air", "air.uav", "SFAPMFQ-----", "own", "fm-uav", None, f"U{k + 1}",
                          "Tactical UAV", "uav", gar, self.region_of(c), ["isr"], crew=0, range_km=150,
                          motion=MotionSpec("path", path=Path(path_pts, speeds), start_s=60 + k * 700, hold_s=1200, mode="loop", airborne=True, fuel_start=100, fuel_burn_per_km=0.05)))

    def _heli_sortie(self, base: str, spot: sitegen.Spot, legs: list[tuple[float, float]]) -> Path:
        s = (spot.lng, spot.lat)
        verts: list[tuple[float, float, float | None]] = [(s[0], s[1], None), (s[0], s[1], 60.0)]
        speeds = [3.0]
        prev = s
        for p in legs + [s]:
            verts.append((p[0], p[1], 300.0 if p != s else 60.0))
            speeds.append(65.0 if geo.haversine_m(prev, p) > 2000 else 20.0)
            prev = p
        verts.append((s[0], s[1], None))
        speeds.append(3.0)
        return Path(verts, speeds)

    # -- army ------------------------------------------------------------------------------------------------------
    VEH = {
        "mbt": ("Main battle tank", "SFGPEVATH---", "land.manoeuvre", 4, ["armour"]),
        "ifv": ("Tracked infantry fighting vehicle", "SFGPEVAI----", "land.manoeuvre", 3, ["mech_infantry"]),
        "apc_wheeled": ("8×8 armoured personnel carrier", "SFGPEVAA----", "land.manoeuvre", 3, ["mech_infantry"]),
        "bv": ("Articulated all-terrain carrier", "SFGPEVUS----", "land.manoeuvre", 2, ["rangers", "winter"]),
        "spg_wheeled": ("Wheeled 155 mm self-propelled howitzer", "SFGPEWHH----", "land.fires", 4, ["fires"]),
        "ad_launcher": ("Air-defence missile launcher", "SFGPEWMS----", "land.ad", 3, ["air_defence"]),
        "radar_vehicle": ("Air-defence radar", "SFGPESR-----", "land.ad", 3, ["air_defence", "radar"]),
        "command_post": ("Command post vehicle", "SFGPUH------", "land.support", 4, ["command"]),
        "engineer": ("Engineer vehicle", "SFGPEVE-----", "land.support", 3, ["engineering", "bridging"]),
        "truck": ("Logistics truck", "SFGPEVUL----", "land.logistics", 2, ["supply"]),
        "fuel_truck": ("Fuel tanker truck", "SFGPEVUT----", "land.logistics", 2, ["fuel", "supply"]),
        "recovery": ("Recovery vehicle", "SFGPEVAAR---", "land.logistics", 3, ["maintenance"]),
        "ambulance": ("Armoured ambulance", "SFGPEVUA----", "land.logistics", 3, ["medical"]),
    }

    def vehicle(self, vid: str, label: str, model: str, parent: str, region: str | None, motion: MotionSpec, extra_caps: list[str] | None = None) -> Node:
        plat, sidc, layer, crew, caps = self.VEH[model]
        rng = random.Random(vid)
        if motion.fuel_start is None:
            motion.fuel_start = round(rng.uniform(55, 100))
            motion.fuel_burn_per_km = 0.18 if model in ("mbt", "ifv", "spg_wheeled") else 0.09
        return self.add(Node(vid, label, "ground_vehicle", "land", layer, sidc, "own", parent, None, label.split(" ")[-1], plat, model, None, region,
                             caps + (extra_caps or []), motion, crew, range_km=300))

    def _company(self, cid: str, label: str, short: str, sidc: str, parent: str, layer: str, region: str | None, mix: list[tuple[str, int]],
                 placement, caps: list[str] | None = None) -> list[str]:
        """Create a company of vehicles. `placement(index, total) -> MotionSpec` decides where each vehicle is."""
        self.formation(cid, label, short, sidc, "company", parent, layer, "land", region=region, caps=caps)
        total = sum(c for _, c in mix)
        ids, i = [], 0
        for model, count in mix:
            for _ in range(count):
                vid = f"{cid[3:]}-{i + 1:02d}"
                self.vehicle(vid, f"{short} {i + 1:02d}", model, cid, region, placement(i, total))
                ids.append(vid)
                i += 1
        return ids

    def at_garrison(self, site: str):
        def place(i: int, total: int) -> MotionSpec:
            s = self.spot(site, "motorpool")
            return MotionSpec("static", pos=(s.lng, s.lat, None), heading=s.heading)
        return place

    def in_field(self, center: tuple[float, float], facing: float, radius_m: float, seed: int):
        """Dispersed field positions next to real roads around `center`, vehicles facing the threat axis."""
        rng = random.Random(seed)
        nodes: list[tuple[float, float]] = []
        net = road_net(center)
        if net is not None:
            cand = list(net.nodes_within(center, radius_m, {"secondary", "tertiary", "minor"} if on_gotland(center) else {"secondary", "tertiary"}))
            rng.shuffle(cand)
            nodes = cand[:64]

        def place(i: int, total: int) -> MotionSpec:
            if nodes:
                base = nodes[i % len(nodes)]
                p = geo.destination(base, rng.uniform(0, 360), rng.uniform(25, 60))
            else:
                p = geo.destination(center, rng.uniform(0, 360), rng.uniform(0.2, 1.0) * radius_m)
            return MotionSpec("static", pos=(p[0], p[1], None), heading=(facing + rng.uniform(-25, 25)) % 360)
        return place

    def on_road(self, rid: str, a: tuple[float, float], b: tuple[float, float], speed: float, start_s: float, hold_s: float, spacing_m: float = 70.0):
        coords = road_route(self.cache, a, b)
        path = self.shared_route(rid, coords, speed)

        def place(i: int, total: int) -> MotionSpec:
            return MotionSpec("path", path=path, route_id=rid, start_s=start_s, hold_s=hold_s, mode="pingpong",
                              trim=((total - 1 - i) * spacing_m, i * spacing_m))
        return place

    def _army(self) -> None:
        self.formation("fm-army", "Army", "Army", "SFGPU-------", "service", "fm-sweden", "land", "land")
        fields = {
            "n": (pt("haparanda", -18, 4), 90.0), "c": (pt("norrtalje", 4, 6), 80.0), "s": (pt("ystad", -6, 6), 180.0),
            "s2": (pt("karlskrona", -10, 6), 150.0), "w": (pt("uddevalla", 8, -4), 260.0), "g": (pt("visby", 14, -8), 100.0), "g2": (pt("slite", -4, -2), 70.0),
        }
        brigades = [
            ("n", "Brigade North", "N Bde", "garrison-norr", "25"),
            ("c", "Brigade Centre", "C Bde", "garrison-mitt", "03"),
            ("s", "Brigade South", "S Bde", "garrison-syd", "12"),
            ("w", "Brigade West", "W Bde", "garrison-vast", "14"),
        ]
        for b, blabel, bshort, gar, region in brigades:
            bid = f"fm-bde-{b}"
            self.formation(bid, blabel, bshort, "SFGPUCIZ---H", "brigade", "fm-army", "land.manoeuvre", "land", region=region)
            self._company(f"fm-hq-{b}", f"{bshort} HQ Company", "HQ", "SFGPUH-----E", bid, "land.support", region, [("command_post", 3), ("radar_vehicle", 1)], self.at_garrison(gar))
            bns = 2 if b in ("c", "s") else 1
            for bn in range(1, bns + 1):
                bnid = f"fm-bn-{b}{bn}"
                self.formation(bnid, f"{bnid[6:].upper()} Mechanised Battalion", f"{b.upper()}{bn} Mech", "SFGPUCIZ---F", "battalion", bid, "land.manoeuvre", "land", region=region)
                moving = (b, bn) in (("n", 1), ("s", 1), ("w", 1))
                deployed = (b, bn) in (("c", 1), ("s", 2))
                for ci, (letter, mix, sidc) in enumerate([("a", [("ifv", 10)], "SFGPUCIZ---E"), ("b", [("ifv", 10)], "SFGPUCIZ---E"),
                                                          ("c", [("ifv", 9), ("apc_wheeled", 1)], "SFGPUCIZ---E"), ("t", [("mbt", 10)], "SFGPUCA----E")]):
                    cid = f"fm-coy-{b}{bn}{letter}"
                    clabel = f"{b.upper()}{bn} {'Tank' if letter == 't' else 'Mech'} Company {letter.upper()}"
                    if moving:
                        dest = fields[b][0]
                        place = self.on_road(f"r-{b}{bn}", self.sites[gar], dest, 14.0 if letter != "t" else 13.0, 200 + ci * 240 + bn * 60, 3600, 75.0)
                    elif deployed:
                        # each company holds its own position inside the battalion area (~1.5 km dispersal)
                        key = "c" if b == "c" else "s2"
                        cpos = geo.destination(fields[key][0], fields[key][1] - 60 + ci * 40, 3500)
                        place = self.in_field(cpos, fields[key][1], 1500, int(hashlib.md5(f"{b}{bn}{letter}".encode()).hexdigest()[:4], 16))
                    else:
                        place = self.at_garrison(gar)
                    self._company(cid, clabel, f"{b.upper()}{bn}{letter.upper()}", sidc, bnid, "land.manoeuvre", region, mix, place)
            # fires, air defence, engineers, logistics
            art = f"fm-bn-{b}-art"
            self.formation(art, f"{bshort} Artillery Battalion", f"{bshort} Arty", "SFGPUCFHE--F", "battalion", bid, "land.fires", "land", region=region)
            art_place = self.on_road(f"r-{b}-art", self.sites[gar], fields[b][0], 15.0, 1500, 5400, 90.0) if b == "s" else self.at_garrison(gar)
            for bt in range(2):
                self._company(f"fm-bty-{b}{bt + 1}", f"{bshort} Battery {bt + 1}", f"Bty {bt + 1}", "SFGPUCFHE--E", art, "land.fires", region, [("spg_wheeled", 6), ("truck", 2)], art_place)
            ad = f"fm-bn-{b}-ad"
            self.formation(ad, f"{bshort} Air Defence Battalion", f"{bshort} AD", "SFGPUCD----F", "battalion", bid, "land.ad", "land", region=region)
            ad_c = geo.destination(self.sites[gar], 45, 4000)
            self._ad_unit(f"fm-adc-{b}", f"{bshort} AD Company", ad, region, ad_c, 4, 1, "Short-range air-defence launcher", 15)
            self._company(f"fm-eng-{b}", f"{bshort} Engineer Company", "Eng", "SFGPUCE----E", bid, "land.support", region, [("engineer", 8)], self.at_garrison(gar))
            log = f"fm-bn-{b}-log"
            self.formation(log, f"{bshort} Logistics Battalion", f"{bshort} Log", "SFGPUSS----F", "battalion", bid, "land.logistics", "land", region=region)
            depot = {"n": "depot-bothnia", "c": "depot-mitt", "s": "depot-syd", "w": "depot-mitt"}[b]
            dest = fields[{"c": "c", "s": "s2"}.get(b, b)][0]
            shuttle = self.on_road(f"r-{b}-log", self.sites[depot], dest, 19.0, 400, 1800, 60.0)
            self._company(f"fm-sup-{b}", f"{bshort} Supply Company", "Sup", "SFGPUSS----E", log, "land.logistics", region, [("truck", 8), ("fuel_truck", 4)], shuttle)
            self._company(f"fm-mnt-{b}", f"{bshort} Maintenance Company", "Mnt", "SFGPUSX----E", log, "land.logistics", region, [("recovery", 4), ("truck", 2)], self.at_garrison(gar))
            self._company(f"fm-med-{b}", f"{bshort} Medical Company", "Med", "SFGPUSM----E", log, "land.logistics", region, [("ambulance", 6)], self.at_garrison(gar))
        # Ranger battalion (north, winter)
        self.formation("fm-bn-rgr", "Ranger Battalion", "Rgr Bn", "SFGPUCIS---F", "battalion", "fm-bde-n", "land.manoeuvre", "land", region="25")
        for ci, letter in enumerate("abc"):
            place = self.in_field(pt("gallivare", 30, -20), 30, 6000, 900 + ci) if letter == "a" else self.at_garrison("garrison-fjall")
            self._company(f"fm-coy-r{letter}", f"Ranger Company {letter.upper()}", f"R{letter.upper()}", "SFGPUCIS---E", "fm-bn-rgr", "land.manoeuvre", "25", [("bv", 8)], place)
        # Battlegroup Gotland
        self.formation("fm-bg-g", "Battlegroup Gotland", "BG G", "SFGPUCIZ---G", "regiment", "fm-army", "land.manoeuvre", "land", region="09")
        self._company("fm-coy-g1", "Gotland Mech Company", "G1", "SFGPUCIZ---E", "fm-bg-g", "land.manoeuvre", "09", [("ifv", 10)], self.in_field(fields["g"][0], fields["g"][1], 1800, 77))
        self._company("fm-coy-g2", "Gotland Tank Company", "G2", "SFGPUCA----E", "fm-bg-g", "land.manoeuvre", "09", [("mbt", 10)],
                      self.on_road("r-g2", self.sites["garrison-gotland"], fields["g2"][0], 12.0, 500, 2400, 80.0))
        self._ad_unit("fm-coy-g-ad", "Gotland AD Company", "fm-bg-g", "09", pt("visby", 8, -12), 4, 1, "Medium-range air-defence launcher", 40)
        # Long-range air defence batteries protecting the capital, Gotland and Skåne
        self.formation("fm-ad", "Air Defence Regiment", "AD Regt", "SFGPUCD----G", "regiment", "fm-army", "land.ad", "land")
        for k, (lbl, c, rng_km) in enumerate([("AD Battery Capital", pt("stockholm", -12, 10), 100), ("AD Battery Skåne", pt("malmo", 12, 8), 100), ("AD Battery Bothnia", pt("lulea", -20, 0), 40)]):
            self._ad_unit(f"fm-adb-{k + 1}", lbl, "fm-ad", self.region_of(c), c, 4, 1, "Long-range air-defence launcher" if rng_km > 50 else "Medium-range air-defence launcher", rng_km)

    def _ad_unit(self, cid: str, label: str, parent: str, region: str | None, center: tuple[float, float], launchers: int, radars: int, plat: str, range_km: float) -> None:
        self.formation(cid, label, label.split(" ")[-1] if "Battery" not in label else label.replace("AD Battery ", "Bty "), "SFGPUCD----E", "company", parent, "land.ad", "land", region=region, caps=["air_defence"])
        for i, (p, b) in enumerate(sitegen.ad_battery_positions(center, 0, launchers, 1800 if range_km > 50 else 900, hash(cid) & 0xFFFF)):
            n = self.vehicle(f"{cid[3:]}-l{i + 1}", f"{label} L{i + 1}", "ad_launcher", cid, region, MotionSpec("static", pos=(p[0], p[1], None), heading=b))
            n.platform = plat
            n.range_km = range_km
        for i in range(radars):
            n = self.vehicle(f"{cid[3:]}-r{i + 1}", f"{label} radar", "radar_vehicle", cid, region, MotionSpec("static", pos=(center[0], center[1], None), heading=0))
            n.range_km = range_km * 1.6

    # -- navy ------------------------------------------------------------------------------------------------------
    def _navy(self) -> None:
        self.formation("fm-navy", "Navy", "Navy", "SFSPC-------", "service", "fm-sweden", "sea", "sea")
        fleet = [
            ("fl-s", "Naval Flotilla South", "4 Flot", "navbase-syd", [
                ("corvette", "Corvette", 4, "SFSPCLFF----", "sea.combat", [("sea_hano", "sea_bornholm_n", "sea_oland_s"), ("sea_oland_s", "sea_oland_e", "sea_gotland_s")]),
                ("patrol_ship", "Patrol ship", 2, "SFSPCPSB----", "sea.combat", [("sea_oland_e", "sea_gotland_s", "sea_gotland_e")]),
                ("mcm", "Mine countermeasures vessel", 4, "SFSPCMMS----", "sea.combat", [("sea_hano", "sea_oland_s")]),
                ("submarine", "Submarine", 3, "SFUPSN------", "sea.sub", [("sea_oland_s", "sea_gotland_s", "sea_bornholm_n")]),
                ("support_ship", "Support ship", 1, "SFSPNR------", "sea.support", []),
            ]),
            ("fl-e", "Naval Flotilla East", "3 Flot", "navbase-ost", [
                ("corvette", "Corvette", 2, "SFSPCLFF----", "sea.combat", [("sea_landsort", "sea_gotland_ne", "sea_stockholm_e")]),
                ("mcm", "Mine countermeasures vessel", 2, "SFSPCMMS----", "sea.combat", [("sea_landsort", "sea_stockholm_e")]),
                ("patrol_ship", "Patrol ship", 2, "SFSPCPSB----", "sea.combat", [("sea_aland", "sea_stockholm_e")]),
            ]),
            ("fl-w", "Naval Station West", "NS W", "navbase-vast", [
                ("patrol_ship", "Patrol ship", 2, "SFSPCPSB----", "sea.combat", [("sea_kattegat", "sea_kattegat_n")]),
            ]),
        ]
        for fid, flabel, fshort, base, groups in fleet:
            self.formation(f"fm-{fid}", flabel, fshort, "SFSPCLFF--G-", "regiment", "fm-navy", "sea.combat", "sea", region=self.region_of(self.sites[base]))
            n = 0
            for model, plat, count, sidc, layer, patrols in groups:
                gid = f"fm-{fid}-{model}"
                self.formation(gid, f"{flabel} {plat.lower()}s", plat, sidc, "battalion", f"fm-{fid}", layer, "sea")
                for k in range(count):
                    n += 1
                    berth = self.spot(base, "berth")
                    vid = f"{fid}-{model[:3]}{k + 1}"
                    node = Node(vid, f"{plat} {fshort}-{k + 1}", "vessel", "sea", layer, sidc, "own", gid, None, f"{k + 1}", plat, model, base,
                                self.region_of(self.sites[base]), {"corvette": ["asw", "surface", "sea_picture", "air_defence"], "patrol_ship": ["patrol", "sea_picture"],
                                                                  "mcm": ["mine_warfare"], "submarine": ["asw", "isr"], "support_ship": ["supply", "fuel"]}[model],
                                crew={"corvette": 43, "patrol_ship": 30, "mcm": 25, "submarine": 27, "support_ship": 50}[model], range_km=250)
                    if k < len(patrols):
                        wps = [self.sites[base]] + [P[w] for w in patrols[k]] + [self.sites[base]]
                        coords = chain(*[sea_route(self.cache, wps[i], wps[i + 1]) for i in range(len(wps) - 1)])
                        coords = chain([(berth.lng, berth.lat)], coords, [(berth.lng, berth.lat)])
                        alt = -40.0 if model == "submarine" else None
                        pts = [(c[0], c[1], alt) for c in coords]
                        spd = {"corvette": 9.0, "patrol_ship": 8.0, "mcm": 5.0, "submarine": 4.0}[model]
                        sp = [3.0] + [spd] * (len(pts) - 3) + [3.0] if len(pts) > 3 else [spd] * (len(pts) - 1)
                        node.motion = MotionSpec("path", path=Path(pts, sp), start_s=100 + n * 400, hold_s=3600 * 2, mode="loop", fuel_start=100, fuel_burn_per_km=0.02)
                        if model == "submarine":
                            node.tags.append("submerged at sea")
                    else:
                        node.motion = MotionSpec("static", pos=(berth.lng, berth.lat, None), heading=berth.heading, fuel_start=round(self.rng.uniform(60, 100)))
                    self.add(node)
        # Amphibious battalion with fast assault craft
        self.formation("fm-amph", "Amphibious Battalion", "Amph Bn", "SFGPUCIZ---F", "battalion", "fm-navy", "sea.amphib", "sea", region="01")
        for ci, (base, count) in enumerate([("navbase-ost", 8), ("navbase-vast", 6)]):
            cid = f"fm-amph-{ci + 1}"
            self.formation(cid, f"Amphibious Company {ci + 1}", f"Amph {ci + 1}", "SFSPCALC---E", "company", "fm-amph", "sea.amphib", "sea")
            lay = self.layouts[base]
            for k in range(count):
                pad = self.spot(base, "pad")
                vid = f"amph{ci + 1}-{k + 1:02d}"
                node = Node(vid, f"Assault craft {ci + 1}-{k + 1:02d}", "vessel", "sea", "sea.amphib", "SFSPCALC----", "own", cid, None, f"{k + 1}",
                            "Fast assault craft", "cb90", base, self.region_of(self.sites[base]), ["amphibious", "patrol"], crew=3, range_km=80)
                if k < 2:
                    ch = lay.routes["channel"]
                    out = chain([(pad.lng, pad.lat)], ch, sea_route(self.cache, ch[-1], geo.destination(ch[-1], lay.axis + 40, 12000)))
                    loop = out + list(reversed(out))[1:]
                    node.motion = MotionSpec("path", path=Path([(c[0], c[1], None) for c in loop], [14.0]), start_s=300 + k * 30, hold_s=1500, mode="loop")
                else:
                    node.motion = MotionSpec("static", pos=(pad.lng, pad.lat, None), heading=pad.heading)
                self.add(node)

    # -- home guard -------------------------------------------------------------------------------------------------
    def _home_guard(self) -> None:
        self.formation("fm-hg", "Home Guard", "HG", "SFGPUCI----I", "division", "fm-army", "land.homeguard", "land")
        protect = {s.id: self.sites[s.id] for s in SITES if s.kind in ("power", "port", "bridge", "telecom", "comms", "radar", "depot")}
        for code, county, seat in COUNTY_SEATS:
            bid = f"fm-hg-{code}"
            self.formation(bid, f"Home Guard Battalion {county}", f"HG {county}", "SFGPUCI----F", "battalion", "fm-hg", "land.homeguard", "land", region=code)
            near = sorted(protect.items(), key=lambda kv: geo.haversine_m(kv[1], P[seat]))[:2]
            for ci in range(3):
                cid = f"fm-hg-{code}-{ci + 1}"
                self.formation(cid, f"HG {county} Company {ci + 1}", f"{ci + 1}", "SFGPUCI----E", "company", bid, "land.homeguard", "land", region=code)
                if ci < len(near) and geo.haversine_m(near[ci][1], P[seat]) < 120_000:
                    c = geo.destination(near[ci][1], 200 + ci * 60, 450)
                    task = f"Protect {near[ci][0]}"
                else:
                    c = pt(seat, (ci - 1) * 4, 2)
                    task = "Area security"
                for t in range(2):
                    p = geo.destination(c, t * 140, 120)
                    self.add(Node(f"hg-{code}-{ci + 1}{'ab'[t]}", f"HG {county} {ci + 1}{'AB'[t]}", "personnel", "land", "land.homeguard", "SFGPUCI----D", "own", cid,
                                  None, f"{ci + 1}{'AB'[t]}", "Home Guard platoon", "personnel", None, code, ["guard", "area_security"],
                                  MotionSpec("static", pos=(p[0], p[1], None), heading=t * 140), crew=30, range_km=20, tags=[task]))
                if ci == 0:
                    route = street_loop(self.cache, seat, hash(code) & 0xFFFF, P[seat], 9000) if seat in _known_cities() else None
                    if route:
                        path = self.shared_route(f"r-hg-{code}", route, 11.0)
                        self.add(Node(f"hg-{code}-v1", f"HG {county} patrol vehicle", "ground_vehicle", "land", "land.homeguard", "SFGPEVU-----", "own", cid, None,
                                      "Pat", "Patrol vehicle", "car", None, code, ["area_security"], MotionSpec("path", path=path, route_id=f"r-hg-{code}", start_s=50, mode="loop"), crew=4))

    # -- civil blue-light fleets ------------------------------------------------------------------------------------
    POLICE = {"stockholm": 24, "goteborg": 14, "malmo": 12, "uppsala": 6, "linkoping": 4, "orebro": 4, "vasteras": 4, "helsingborg": 4, "norrkoping": 4,
              "jonkoping": 4, "umea": 3, "lulea": 3, "sundsvall": 3, "gavle": 3, "kalmar": 2, "karlskrona": 2, "ostersund": 2, "visby": 2, "kiruna": 2, "boden": 1}
    EMS = {"stockholm": 8, "goteborg": 5, "malmo": 4, "uppsala": 2, "linkoping": 2, "orebro": 2, "umea": 2, "lulea": 2, "sundsvall": 1, "visby": 1}

    def _civil(self) -> None:
        self.formation("fm-police", "Police Authority", "Police", "SNGPUULC---I", "division", None, "civil.police", "land", affiliation="civil")
        self.formation("fm-ems", "Ambulance services", "EMS", "SNGPUSM----I", "division", None, "civil.ems", "land", affiliation="civil")
        for city, n in self.POLICE.items():
            region = COUNTY_OF.get(city)
            rid = f"fm-pol-{city}"
            self.formation(rid, f"Police {city.title()}", city.title(), "SNGPUULC---E", "company", "fm-police", "civil.police", "land", "civil", region)
            for k in range(n):
                seed = int(hashlib.md5(f"pol{city}{k}".encode()).hexdigest()[:6], 16)
                rng = random.Random(seed)
                start = geo.destination(P[city], rng.uniform(0, 360), rng.uniform(0, 2500 if n > 6 else 1200))
                coords = street_loop(self.cache, city, seed, start, rng.uniform(6000, 14000))
                speed = rng.uniform(8.0, 12.5)
                path = Path([(c[0], c[1], None) for c in coords], [speed])
                self.add(Node(f"pol-{city}-{k + 1:02d}", f"Patrol car {city.title()} {k + 1:02d}", "ground_vehicle", "land", "civil.police", "SNGPUULC----", "civil",
                              rid, None, f"{k + 1:02d}", "Police patrol car", "police_car", None, region, ["law_enforcement"],
                              MotionSpec("path", path=path, start_s=rng.uniform(0, 200), offset_s=rng.uniform(0, path.duration), mode="loop"), crew=2, range_km=40))
        for city, n in self.EMS.items():
            region = COUNTY_OF.get(city)
            rid = f"fm-ems-{city}"
            self.formation(rid, f"Ambulances {city.title()}", city.title(), "SNGPUSM----E", "company", "fm-ems", "civil.ems", "land", "civil", region)
            for k in range(n):
                seed = int(hashlib.md5(f"ems{city}{k}".encode()).hexdigest()[:6], 16)
                rng = random.Random(seed)
                start = geo.destination(P[city], rng.uniform(0, 360), rng.uniform(0, 1500))
                coords = street_loop(self.cache, city, seed, start, rng.uniform(5000, 9000))
                path = Path([(c[0], c[1], None) for c in coords], [rng.uniform(9.0, 14.0)])
                self.add(Node(f"ems-{city}-{k + 1:02d}", f"Ambulance {city.title()} {k + 1:02d}", "ground_vehicle", "land", "civil.ems", "SNGPEVUA----", "civil",
                              rid, None, f"{k + 1:02d}", "Ambulance", "ambulance", None, region, ["medical"],
                              MotionSpec("path", path=path, start_s=rng.uniform(0, 300), offset_s=rng.uniform(0, path.duration), hold_s=rng.uniform(120, 600), mode="loop"), crew=2, range_km=60))
        # Coast guard (civil authority, synthetic positions)
        self.formation("fm-cg", "Coast Guard", "CG", "SNSPXL----I-", "division", None, "civil.coastguard", "sea", affiliation="civil")
        cg = [("cg-1", "port-lulea", ["sea_bothnia_bay", "sea_bothnia_n"]), ("cg-2", "navbase-vast", ["sea_kattegat_n", "sea_kattegat"]), ("cg-3", "port-trelleborg", ["sea_oresund", "sea_bornholm_n"]),
              ("cg-4", "navbase-ost", ["sea_landsort", "sea_gotland_ne"]), ("cg-5", "navbase-syd", ["sea_oland_s", "sea_oland_e"]), ("cg-6", "port-goteborg", []), ("cg-7", "port-lulea", [])]
        for k, (vid, base, wps_names) in enumerate(cg):
            c = self.sites[base]
            node = Node(vid, f"Coast guard vessel {k + 1}", "vessel", "sea", "civil.coastguard", "SNSPXL------", "civil", "fm-cg", None, f"KBV{k + 1}",
                        "Coast guard patrol vessel", "coast_guard", base, self.region_of(c), ["patrol", "sar", "law_enforcement"], crew=12, range_km=200)
            if wps_names:
                wps = [c] + [P[w] for w in wps_names] + [c]
                coords = chain(*[sea_route(self.cache, wps[i], wps[i + 1]) for i in range(len(wps) - 1)])
                node.motion = MotionSpec("path", path=Path([(x[0], x[1], None) for x in coords], [7.5]), start_s=k * 300, hold_s=2400, mode="loop")
            else:
                node.motion = MotionSpec("static", pos=(c[0], c[1], None), heading=0)
            self.add(node)

    # -- the uncertain part of the picture: unknown and suspect tracks ------------------------------------------------
    def _unknowns(self) -> None:
        def track(id_, label, kind, domain, layer, sidc, pts, speed, start, alt=None, mode="once", hold=0.0, tags=None, model="unknown_air"):
            path = Path([(p[0], p[1], alt) for p in pts], speed if isinstance(speed, list) else [speed])
            return self.add(Node(id_, label, kind, domain, layer, sidc, "unknown", None, None, label.split(" ")[-1], None, model, None, None, [],
                                 MotionSpec("path", path=path, start_s=start, mode=mode, hold_s=hold, airborne=domain == "air"), tags=tags or []))

        track("unk-air-01", "Unknown air track A1", "unknown", "air", "track.unknown", "SUAPMF------",
              [(21.90, 57.20), (20.10, 57.60), (19.30, 58.00), (19.60, 58.60), (20.60, 58.40), (21.40, 57.70), (20.80, 57.00), (19.90, 56.80), (19.40, 57.30)], 190, 0, 9000)
        track("unk-air-02", "Unknown air track A2", "unknown", "air", "track.unknown", "SUAPMF------",
              [(24.80, 65.90), (23.60, 65.60), (22.70, 65.75), (23.20, 65.20), (24.30, 65.00), (24.60, 65.60)], 150, 400, 6000)
        # A track with suspiciously perfect kinematics and no emissions: a decoy candidate.
        track("unk-air-03", "Unknown air track A3", "unknown", "air", "track.unknown", "SUAPMF------",
              densify([(20.6, 56.2), (18.2, 56.5), (17.2, 56.75)], 5000), 150.0, 900, 4000, tags=["no_emitter", "constant_kinematics"])
        track("unk-sea-01", "Unknown sea track S1", "unknown", "sea", "track.unknown", "SUSP--------",
              [(20.30, 56.60), (19.40, 57.10), (19.00, 57.55), (19.20, 58.10), (19.90, 58.30)], 9, 0, model="unknown_sea")
        track("unk-sea-02", "Unknown sea track S2", "unknown", "sea", "track.unknown", "SUSP--------",
              [(12.40, 55.95), (12.75, 56.30), (12.30, 56.60), (11.90, 57.00), (11.60, 57.50)], 7, 600, model="unknown_sea")
        # A tanker declaring itself on AIS, loitering slowly over the Gotland–Lithuania cable with AIS dark periods.
        cable = CABLES[0]["coords"]
        loiter = [tuple(cable[1]), (19.62, 56.97), (19.55, 57.02), (19.66, 57.04), (19.58, 56.99), (19.64, 57.03), (19.57, 57.0), tuple(cable[1])]
        tanker_pts = [(19.70, 56.93)] + loiter * 3 + [(20.2, 57.8), (21.0, 58.9)]
        tanker_speeds = [6.0] + [1.0] * (len(loiter) * 3 - 1) + [6.0, 6.0]
        track("unk-sea-03", "Tanker NORDIC STAR (AIS)", "unknown", "sea", "track.unknown", "SSSPXMO-----",
              tanker_pts, tanker_speeds, 0, model="tanker",
              tags=["ais_declared:tanker", "ais_gaps", "loiter_over_cable", "flag_of_convenience"])
        # Small UAS circling Airbase Syd at low level at night.
        base = self.sites["airbase-syd"]
        for k in range(3):
            ring = [geo.destination(base, b + k * 40, 2600 + k * 500) for b in range(0, 721, 30)]
            track(f"unk-uas-0{k + 1}", f"Unknown UAS U{k + 1}", "unknown", "air", "track.unknown", "SUAPMFQ-----", ring, 18.0, 1200 + k * 90, 150.0,
                  tags=["small_uas", "low_level"], model="uav")


def _known_cities() -> set[str]:
    gn = _geonet()
    try:
        return set(gn.cities()) if gn else set()
    except Exception:
        return set()
