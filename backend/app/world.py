"""Synthetic national world: fictional Swedish forces, sites, infrastructure and tracks.

Everything is generated deterministically from a seed so replay, tests and the browser agree.
No real military installation, unit identity, route or capability is represented. Coordinates are
plausible Swedish geography (public cities, coasts, roads) with fictional sites placed near them.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import geo
from .models import Condition, EntityKind, GeoPosition, Kinematics, Readiness, SceneEntity, Track

SCENARIO_ID = "sweden-synthetic"
MODEL_VERSION = "1.0.0"

# Public reference points (city centres / coastal waypoints), [lng, lat].
P = {
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
    # sea waypoints (Baltic, Bothnia, Kattegat, Öresund)
    "sea_stockholm_e": (19.40, 59.30), "sea_gotland_e": (19.60, 57.60), "sea_gotland_s": (18.30, 56.80),
    "sea_oland_s": (16.60, 56.00), "sea_bornholm_n": (14.90, 55.60), "sea_oresund": (12.70, 55.80),
    "sea_kattegat": (11.50, 57.30), "sea_bothnia_s": (18.80, 61.60), "sea_bothnia_m": (19.90, 62.90),
    "sea_bothnia_n": (21.80, 64.60), "sea_bothnia_bay": (23.00, 65.30), "sea_landsort": (18.00, 58.60),
}

COUNTY_OF = {  # nearest-city → SCB county code (for region grouping)
    "stockholm": "01", "norrtalje": "01", "nynashamn": "01", "uppsala": "03", "enkoping": "03", "nykoping": "04",
    "eskilstuna": "04", "norrkoping": "05", "linkoping": "05", "motala": "05", "jonkoping": "06", "vaxjo": "07",
    "kalmar": "08", "oskarshamn": "08", "vastervik": "08", "visby": "09", "karlskrona": "10", "malmo": "12",
    "helsingborg": "12", "kristianstad": "12", "ystad": "12", "halmstad": "13", "goteborg": "14", "skovde": "14",
    "trollhattan": "14", "uddevalla": "14", "karlstad": "17", "orebro": "18", "vasteras": "19", "falun": "20",
    "mora": "20", "ludvika": "20", "borlange": "20", "gavle": "21", "soderhamn": "21", "hudiksvall": "21",
    "sundsvall": "22", "harnosand": "22", "ornskoldsvik": "22", "ostersund": "23", "umea": "24", "skelleftea": "24",
    "lulea": "25", "boden": "25", "kiruna": "25", "haparanda": "25", "arvidsjaur": "25", "gallivare": "25",
}


@dataclass
class SiteSpec:
    id: str
    label: str
    kind: EntityKind
    near: str
    offset_km: tuple[float, float]  # east, north km from the reference point (fictional placement)
    capabilities: list[str]
    unit: str
    model_key: str
    affiliation: str = "own"


@dataclass
class MobileSpec:
    id: str
    label: str
    kind: EntityKind
    unit: str
    model_key: str
    route: list[str | tuple[float, float]]
    speed_mps: float
    altitude_m: float | None
    capabilities: list[str]
    start_s: float = 0
    loop: bool = True
    hold_s: float = 0
    affiliation: str = "own"
    home: str | None = None


def _pt(ref: str | tuple[float, float], east_km: float = 0, north_km: float = 0) -> tuple[float, float]:
    base = P[ref] if isinstance(ref, str) else ref
    p = geo.destination(base, 90, east_km * 1000)
    return geo.destination(p, 0, north_km * 1000)


SITES: list[SiteSpec] = [
    SiteSpec("hq-joint", "Joint Operations HQ (synthetic)", "facility", "enkoping", (6, 3), ["command", "comms_hub"], "Joint Staff", "hq"),
    SiteSpec("garrison-norr", "Garrison Norr", "facility", "boden", (-4, 2), ["armour", "logistics", "medical"], "Brigade North", "garrison"),
    SiteSpec("garrison-mitt", "Garrison Mitt", "facility", "kungsangen" if False else "enkoping", (-8, -4), ["mech_infantry", "logistics"], "Brigade Centre", "garrison"),
    SiteSpec("garrison-syd", "Garrison Syd", "facility", "kristianstad", (-6, 5), ["armour", "mech_infantry"], "Brigade South", "garrison"),
    SiteSpec("garrison-vast", "Garrison Väst", "facility", "skovde", (3, -2), ["armour", "training"], "Brigade West", "garrison"),
    SiteSpec("garrison-gotland", "Garrison Gotland", "facility", "visby", (4, -6), ["mech_infantry", "air_defence"], "Battlegroup Gotland", "garrison"),
    SiteSpec("garrison-fjall", "Garrison Fjäll", "facility", "arvidsjaur", (2, 1), ["rangers", "winter"], "Ranger Battalion", "garrison"),
    SiteSpec("airfield-norr", "Airfield Norr", "facility", "lulea", (-9, 4), ["fighter", "transport", "fuel"], "Air Wing North", "airfield"),
    SiteSpec("airfield-mitt", "Airfield Mitt", "facility", "uppsala", (-5, 6), ["transport", "helicopter", "fuel"], "Air Wing Centre", "airfield"),
    SiteSpec("airfield-syd", "Airfield Syd", "facility", "kristianstad", (9, -3), ["fighter", "fuel"], "Air Wing South", "airfield"),
    SiteSpec("airfield-ost", "Airfield Öst", "facility", "linkoping", (-4, 4), ["helicopter", "maintenance"], "Helicopter Wing", "airfield"),
    SiteSpec("navbase-syd", "Naval Base Syd", "facility", "karlskrona", (3, -2), ["corvette", "mine_warfare", "fuel"], "Naval Flotilla South", "navbase"),
    SiteSpec("navbase-ost", "Naval Base Öst", "facility", "nynashamn", (4, -3), ["patrol_boat", "amphibious"], "Naval Flotilla East", "navbase"),
    SiteSpec("navbase-vast", "Naval Station Väst", "facility", "goteborg", (-6, -4), ["patrol_boat", "coast_guard"], "Naval Station West", "navbase"),
    SiteSpec("depot-mitt", "Central Depot Mitt", "facility", "orebro", (6, 4), ["ammunition", "spares", "fuel"], "Logistics Regiment", "depot"),
    SiteSpec("depot-norr", "Depot Norr", "facility", "ostersund", (3, -3), ["fuel", "spares", "winter"], "Logistics Regiment", "depot"),
    SiteSpec("depot-syd", "Depot Syd", "facility", "vaxjo", (-5, 2), ["ammunition", "fuel"], "Logistics Regiment", "depot"),
    SiteSpec("depot-bothnia", "Depot Bothnia", "facility", "umea", (5, 2), ["fuel", "spares"], "Logistics Regiment", "depot"),
    SiteSpec("hospital-mitt", "Field Hospital Mitt", "facility", "vasteras", (4, 2), ["medical"], "Medical Battalion", "hospital"),
    SiteSpec("hospital-norr", "Field Hospital Norr", "facility", "boden", (3, -2), ["medical"], "Medical Battalion", "hospital"),
    SiteSpec("radar-gotland", "Sensor Site Gotland", "infrastructure", "visby", (12, 8), ["radar", "air_picture"], "Air Surveillance", "radar"),
    SiteSpec("radar-norr", "Sensor Site Norr", "infrastructure", "kiruna", (6, -4), ["radar", "air_picture"], "Air Surveillance", "radar"),
    SiteSpec("radar-syd", "Sensor Site Syd", "infrastructure", "ystad", (8, 3), ["radar", "sea_picture"], "Sea Surveillance", "radar"),
    SiteSpec("radar-vast", "Sensor Site Väst", "infrastructure", "uddevalla", (-9, 2), ["radar", "sea_picture"], "Sea Surveillance", "radar"),
    SiteSpec("comms-mitt", "Comms Node Mitt", "infrastructure", "eskilstuna", (2, 6), ["comms_hub"], "Signals Regiment", "comms"),
    SiteSpec("comms-norr", "Comms Node Norr", "infrastructure", "sundsvall", (-3, 5), ["comms_hub"], "Signals Regiment", "comms"),
    SiteSpec("comms-syd", "Comms Node Syd", "infrastructure", "jonkoping", (5, -5), ["comms_hub"], "Signals Regiment", "comms"),
    SiteSpec("comms-fjall", "Comms Node Fjäll", "infrastructure", "gallivare", (-4, 3), ["comms_hub"], "Signals Regiment", "comms"),
    SiteSpec("power-mitt", "Grid Node Mälardalen", "infrastructure", "vasteras", (-7, -3), ["power"], "Grid operator (public)", "power", "civil"),
    SiteSpec("power-syd", "Grid Node Skåne", "infrastructure", "helsingborg", (10, 4), ["power"], "Grid operator (public)", "power", "civil"),
    SiteSpec("power-norr", "Grid Node Norrland", "infrastructure", "skelleftea", (-8, -2), ["power"], "Grid operator (public)", "power", "civil"),
    SiteSpec("power-vast", "Grid Node Väst", "infrastructure", "trollhattan", (4, 3), ["power"], "Grid operator (public)", "power", "civil"),
    SiteSpec("port-goteborg", "Port Göteborg (civil)", "infrastructure", "goteborg", (-4, -3), ["port", "fuel"], "Port authority (public)", "port", "civil"),
    SiteSpec("port-trelleborg", "Port Trelleborg (civil)", "infrastructure", "ystad", (-14, -1), ["port"], "Port authority (public)", "port", "civil"),
    SiteSpec("port-lulea", "Port Luleå (civil)", "infrastructure", "lulea", (3, -3), ["port", "fuel"], "Port authority (public)", "port", "civil"),
    SiteSpec("bridge-oresund", "Öresund crossing (civil)", "infrastructure", "malmo", (-6, 0), ["transport"], "Transport authority (public)", "bridge", "civil"),
    SiteSpec("bridge-hoga", "Höga Kusten crossing (civil)", "infrastructure", "harnosand", (4, 8), ["transport"], "Transport authority (public)", "bridge", "civil"),
    SiteSpec("telecom-stockholm", "Telecom core Stockholm (civil)", "infrastructure", "stockholm", (-3, 5), ["telecom"], "Telecom operator (public)", "telecom", "civil"),
    SiteSpec("telecom-goteborg", "Telecom core Göteborg (civil)", "infrastructure", "goteborg", (5, 4), ["telecom"], "Telecom operator (public)", "telecom", "civil"),
]


def _mobile_specs() -> list[MobileSpec]:
    specs: list[MobileSpec] = []
    # Fixed wing patrols (altitudes MSL)
    specs += [
        MobileSpec("fw-01", "Patrol Baltic 01", "fixed_wing", "Air Wing South", "fighter", ["airfield-syd", "sea_bornholm_n", "sea_oland_s", "sea_gotland_s", "sea_gotland_e", "sea_oland_s", "airfield-syd"], 210, 6500, ["air_patrol", "isr"], 0),
        MobileSpec("fw-02", "Patrol Baltic 02", "fixed_wing", "Air Wing South", "fighter", ["airfield-syd", "sea_oresund", "sea_kattegat", "sea_oresund", "airfield-syd"], 200, 5500, ["air_patrol"], 300),
        MobileSpec("fw-03", "Patrol Norr 01", "fixed_wing", "Air Wing North", "fighter", ["airfield-norr", "sea_bothnia_bay", "haparanda", "kiruna", "gallivare", "airfield-norr"], 220, 7000, ["air_patrol", "isr"], 120),
        MobileSpec("fw-04", "Transport Mitt 01", "fixed_wing", "Air Wing Centre", "transport", ["airfield-mitt", "ostersund", "airfield-norr", "umea", "airfield-mitt"], 140, 4000, ["transport"], 600),
        MobileSpec("fw-05", "ISR Gotland 01", "fixed_wing", "Air Wing Centre", "isr", ["airfield-mitt", "sea_stockholm_e", "sea_gotland_e", "visby", "sea_landsort", "airfield-mitt"], 160, 8000, ["isr", "sigint"], 60),
        MobileSpec("fw-06", "Transport Syd 01", "fixed_wing", "Air Wing South", "transport", ["airfield-syd", "visby", "airfield-ost", "airfield-syd"], 130, 3500, ["transport"], 900),
    ]
    # Helicopters (AGL altitudes)
    specs += [
        MobileSpec("heli-01", "Helicopter Mitt 01", "helicopter", "Helicopter Wing", "helicopter", ["airfield-ost", "norrkoping", "nykoping", "hospital-mitt", "airfield-ost"], 60, 300, ["medevac", "transport"], 200),
        MobileSpec("heli-02", "Helicopter Norr 01", "helicopter", "Helicopter Wing", "helicopter", ["airfield-norr", "garrison-norr", "arvidsjaur", "garrison-fjall", "airfield-norr"], 62, 350, ["transport", "sar"], 400),
        MobileSpec("heli-03", "Helicopter Syd 01", "helicopter", "Helicopter Wing", "helicopter", ["airfield-syd", "navbase-syd", "sea_bornholm_n", "navbase-syd", "airfield-syd"], 58, 250, ["asw", "sar"], 100),
        MobileSpec("heli-04", "Helicopter Gotland 01", "helicopter", "Helicopter Wing", "helicopter", ["garrison-gotland", "radar-gotland", "sea_gotland_e", "garrison-gotland"], 55, 200, ["sar", "transport"], 700),
        MobileSpec("heli-05", "Helicopter Väst 01", "helicopter", "Helicopter Wing", "helicopter", ["navbase-vast", "sea_kattegat", "uddevalla", "navbase-vast"], 57, 220, ["sar"], 50),
        MobileSpec("heli-06", "Medevac Mitt 02", "helicopter", "Medical Battalion", "helicopter", ["hospital-mitt", "vasteras", "orebro", "hospital-mitt"], 60, 280, ["medevac"], 1200),
        MobileSpec("heli-07", "SAR Norrland 01", "helicopter", "Helicopter Wing", "helicopter", ["comms-norr", "harnosand", "ornskoldsvik", "sea_bothnia_m", "sundsvall", "comms-norr"], 58, 260, ["sar", "medevac"], 150),
    ]
    # Multirotor drones (short loops, AGL)
    for i, (home, a, b) in enumerate([("garrison-norr", (0.9, 0.4), (1.2, -0.6)), ("garrison-syd", (-0.8, 0.5), (0.6, 0.9)), ("garrison-gotland", (1.1, 0.3), (0.4, 1.0)),
                                       ("garrison-mitt", (0.7, 0.7), (-0.5, 0.9)), ("navbase-ost", (1.5, -0.4), (2.0, 0.6)), ("garrison-vast", (0.5, 1.0), (1.3, 0.4)),
                                       ("depot-mitt", (0.8, 0.2), (0.3, 0.9)), ("garrison-fjall", (1.0, 1.2), (-0.6, 1.5))], 1):
        specs.append(MobileSpec(f"uav-{i:02d}", f"Recon drone {i:02d}", "multirotor", "Recon Company", "multirotor", [home, ("rel", home, a), ("rel", home, b), home], 16, 120, ["isr"], 30 * i, True, 60, home=home))
    # Ground vehicles: convoys along road-like waypoints
    roads = {
        "E4-north": ["garrison-norr", "lulea", "skelleftea", "umea", "ornskoldsvik", "harnosand", "sundsvall"],
        "E4-south": ["garrison-mitt", "nykoping", "norrkoping", "linkoping", "jonkoping", "vaxjo", "garrison-syd"],
        "E20": ["garrison-vast", "orebro", "eskilstuna", "garrison-mitt"],
        "E6": ["malmo", "helsingborg", "halmstad", "goteborg", "uddevalla"],
        "RV70": ["enkoping", "vasteras", "borlange", "mora"],
        "E45": ["ostersund", "arvidsjaur", "gallivare", "kiruna"],
        "gotland": ["garrison-gotland", "visby", "radar-gotland", "garrison-gotland"],
        "E12": ["depot-bothnia", "umea", "ostersund"],
    }
    gv = [
        ("tank", "Tank platoon", "Brigade North", "E4-north", 14.0, ["armour"]), ("tank", "Tank platoon", "Brigade South", "E4-south", 13.5, ["armour"]),
        ("tank", "Tank platoon", "Brigade West", "E20", 13.0, ["armour"]), ("apc", "Mechanised platoon", "Brigade Centre", "E4-south", 16.0, ["mech_infantry"]),
        ("apc", "Mechanised platoon", "Battlegroup Gotland", "gotland", 15.0, ["mech_infantry"]), ("apc", "Mechanised platoon", "Brigade North", "E45", 15.5, ["mech_infantry"]),
        ("truck", "Supply convoy", "Logistics Regiment", "E4-north", 19.0, ["supply"]), ("truck", "Supply convoy", "Logistics Regiment", "E20", 20.0, ["supply"]),
        ("truck", "Supply convoy", "Logistics Regiment", "E6", 21.0, ["supply"]), ("truck", "Supply convoy", "Logistics Regiment", "E12", 18.0, ["supply"]),
        ("fuel", "Fuel convoy", "Logistics Regiment", "E4-south", 18.5, ["fuel"]), ("fuel", "Fuel convoy", "Logistics Regiment", "E45", 17.0, ["fuel"]),
        ("fuel", "Fuel convoy", "Logistics Regiment", "RV70", 18.0, ["fuel"]), ("ambulance", "Medical team", "Medical Battalion", "E20", 22.0, ["medical"]),
        ("ambulance", "Medical team", "Medical Battalion", "E4-north", 22.0, ["medical"]), ("engineer", "Engineer group", "Engineer Battalion", "E6", 15.0, ["engineering", "bridging"]),
        ("engineer", "Engineer group", "Engineer Battalion", "E12", 14.5, ["engineering"]), ("airdef", "Air defence group", "Air Defence Battalion", "gotland", 12.0, ["air_defence"]),
        ("airdef", "Air defence group", "Air Defence Battalion", "E4-south", 12.5, ["air_defence"]), ("recovery", "Recovery team", "Maintenance Company", "E4-north", 16.0, ["maintenance"]),
        ("recovery", "Recovery team", "Maintenance Company", "E4-south", 16.0, ["maintenance"]), ("cp", "Mobile command post", "Brigade Centre", "RV70", 17.0, ["command"]),
        ("cp", "Mobile command post", "Brigade North", "E45", 17.0, ["command"]), ("apc", "Mechanised platoon", "Brigade South", "E6", 15.0, ["mech_infantry"]),
        ("tank", "Tank platoon", "Brigade South", "E6", 13.0, ["armour"]), ("truck", "Supply convoy", "Logistics Regiment", "E45", 19.0, ["supply"]),
        ("signals", "Signals detachment", "Signals Regiment", "E20", 18.0, ["comms_hub"]), ("signals", "Signals detachment", "Signals Regiment", "E4-north", 18.0, ["comms_hub"]),
        ("apc", "Mechanised platoon", "Brigade West", "E20", 15.0, ["mech_infantry"]), ("truck", "Supply convoy", "Logistics Regiment", "gotland", 19.0, ["supply"]),
    ]
    for i, (mk, label, unit, road, speed, caps) in enumerate(gv, 1):
        route = roads[road] if i % 2 else list(reversed(roads[road]))
        specs.append(MobileSpec(f"gv-{i:02d}", f"{label} {i:02d}", "ground_vehicle", unit, mk, route, speed, None, caps, 90 * i, True, 300))
    # Vessels
    specs += [
        MobileSpec("ves-01", "Corvette Syd 01", "vessel", "Naval Flotilla South", "corvette", ["navbase-syd", "sea_bornholm_n", "sea_oland_s", "sea_gotland_s", "navbase-syd"], 12, 0, ["asw", "surface", "sea_picture"], 0),
        MobileSpec("ves-02", "Corvette Syd 02", "vessel", "Naval Flotilla South", "corvette", ["navbase-syd", "sea_oland_s", "sea_gotland_e", "sea_stockholm_e", "sea_landsort", "navbase-ost"], 11, 0, ["asw", "surface"], 1800, False),
        MobileSpec("ves-03", "Patrol boat Öst 01", "vessel", "Naval Flotilla East", "patrol_boat", ["navbase-ost", "sea_landsort", "sea_stockholm_e", "navbase-ost"], 15, 0, ["patrol"], 200),
        MobileSpec("ves-04", "Patrol boat Öst 02", "vessel", "Naval Flotilla East", "patrol_boat", ["navbase-ost", "sea_gotland_e", "visby", "navbase-ost"], 14, 0, ["patrol"], 900),
        MobileSpec("ves-05", "Patrol boat Väst 01", "vessel", "Naval Station West", "patrol_boat", ["navbase-vast", "sea_kattegat", "sea_oresund", "sea_kattegat", "navbase-vast"], 14, 0, ["patrol", "coast_guard"], 100),
        MobileSpec("ves-06", "Logistics ship 01", "vessel", "Naval Flotilla South", "logistics_ship", ["navbase-syd", "sea_oland_s", "visby", "sea_gotland_e", "navbase-ost"], 8, 0, ["supply", "fuel"], 0, False),
        MobileSpec("ves-07", "Mine countermeasure 01", "vessel", "Naval Flotilla South", "mcm", ["navbase-syd", "sea_bornholm_n", "sea_oresund", "sea_bornholm_n", "navbase-syd"], 9, 0, ["mine_warfare"], 2400),
        MobileSpec("ves-08", "Icebreaker Bothnia (civil)", "vessel", "Maritime administration (public)", "icebreaker", ["port-lulea", "sea_bothnia_bay", "sea_bothnia_n", "port-lulea"], 7, 0, ["icebreaking"], 0, True, 0, "civil"),
        MobileSpec("ves-09", "Ferry Gotland (civil)", "vessel", "Ferry operator (public)", "ferry", ["nynashamn", "sea_landsort", "visby", "sea_landsort", "nynashamn"], 14, 0, ["transport"], 300, True, 900, "civil"),
        MobileSpec("ves-10", "Coast guard Bothnia 01", "vessel", "Coast Guard (public)", "patrol_boat", ["port-lulea", "sea_bothnia_bay", "sea_bothnia_n", "sea_bothnia_m", "sundsvall", "sea_bothnia_s", "gavle"], 12, 0, ["patrol", "sar"], 600, False, 0, "civil"),
    ]
    # Personnel units (dismounted, slow)
    for i, (home, caps) in enumerate([("garrison-norr", ["infantry"]), ("garrison-syd", ["infantry"]), ("garrison-gotland", ["infantry"]), ("garrison-fjall", ["rangers"]),
                                      ("garrison-mitt", ["infantry"]), ("garrison-vast", ["infantry"]), ("radar-gotland", ["guard"]), ("comms-mitt", ["guard"]),
                                      ("depot-mitt", ["guard"]), ("hq-joint", ["guard"])], 1):
        specs.append(MobileSpec(f"inf-{i:02d}", f"Infantry platoon {i:02d}" if "infantry" in caps else f"{caps[0].title()} group {i:02d}", "personnel", "Brigade", "personnel", [home, ("rel", home, (0.4, 0.3)), ("rel", home, (0.1, 0.6)), home], 1.4, None, caps, 100 * i, True, 600, home=home))
    # Unknown tracks (the uncertain part of the picture): sea and air contacts observed by sensors
    specs += [
        MobileSpec("unk-air-01", "Unknown air track A1", "unknown", "Air Surveillance (track)", "unknown_air", [(21.90, 57.20), (20.10, 57.60), (19.30, 58.00), (19.60, 58.60), (20.60, 58.40), (21.40, 57.70), (20.80, 57.00), (19.90, 56.80), (19.40, 57.30)], 190, 9000, [], 0, False, 0, "unknown"),
        MobileSpec("unk-air-02", "Unknown air track A2", "unknown", "Air Surveillance (track)", "unknown_air", [(24.80, 65.90), (23.60, 65.60), (22.70, 65.75), (23.20, 65.20), (24.30, 65.00), (24.60, 65.60)], 150, 6000, [], 400, False, 0, "unknown"),
        MobileSpec("unk-sea-01", "Unknown sea track S1", "unknown", "Sea Surveillance (track)", "unknown_sea", [(20.30, 56.60), (19.40, 57.10), (19.00, 57.55), (19.20, 58.10), (19.90, 58.30)], 9, 0, [], 0, False, 0, "unknown"),
        MobileSpec("unk-sea-02", "Unknown sea track S2", "unknown", "Sea Surveillance (track)", "unknown_sea", [(12.40, 55.95), (12.75, 56.30), (12.30, 56.60), (11.90, 57.00), (11.60, 57.50)], 7, 0, [], 600, False, 0, "unknown"),
    ]
    return specs


KIND_DOMAIN: dict[str, str] = {
    "fixed_wing": "air", "helicopter": "air", "multirotor": "air", "ground_vehicle": "land", "personnel": "land",
    "vessel": "sea", "facility": "site", "infrastructure": "infra", "unknown": "unknown",
}


@dataclass
class WorldEntity:
    spec: SiteSpec | MobileSpec
    base: SceneEntity
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    leg_lengths: list[float] = field(default_factory=list)
    total_length: float = 0.0
    readiness: Readiness | None = None
    condition: str = "normal"


class SyntheticWorld:
    """Deterministic national world. `seconds` is scenario time since the scenario epoch."""

    def __init__(self, seed: int = 20261016) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.entities: dict[str, WorldEntity] = {}
        self.sites: dict[str, tuple[float, float]] = {}
        for s in SITES:
            pos = _pt(s.near, *s.offset_km)
            self.sites[s.id] = pos
            ent = SceneEntity(
                id=s.id, resourceId=f"asset-{s.id}", kind=s.kind, domain=KIND_DOMAIN[s.kind], affiliation=s.affiliation,  # type: ignore[arg-type]
                label=s.label, unit=s.unit, modelKey=s.model_key, region=COUNTY_OF.get(s.near),
                position=GeoPosition(longitudeDeg=pos[0], latitudeDeg=pos[1], altitudeM=0, altitudeDatum="AGL"),
                capabilities=s.capabilities, sourceKind="simulated", visualPriority=3 if s.kind == "facility" else 2,
            )
            self.entities[s.id] = WorldEntity(spec=s, base=ent, readiness=self._site_readiness(s))
        for m in _mobile_specs():
            wps = [self._resolve(w) for w in m.route]
            legs = [geo.haversine_m(wps[i], wps[i + 1]) for i in range(len(wps) - 1)]
            ent = SceneEntity(
                id=m.id, resourceId=f"asset-{m.id}", kind=m.kind, domain=KIND_DOMAIN[m.kind], affiliation=m.affiliation,  # type: ignore[arg-type]
                label=m.label, unit=m.unit, modelKey=m.model_key, region=self._region_of(m),
                capabilities=m.capabilities, sourceKind="simulated" if m.affiliation != "unknown" else "observed",
                visualPriority=1 if m.kind != "unknown" else 4,
                track=Track(waypoints=[[w[0], w[1]] + ([m.altitude_m] if m.altitude_m is not None else []) for w in wps], speedMps=m.speed_mps, startAtS=m.start_s, loop=m.loop, holdS=m.hold_s),
            )
            self.entities[m.id] = WorldEntity(spec=m, base=ent, waypoints=wps, leg_lengths=legs, total_length=sum(legs), readiness=self._mobile_readiness(m))
        self.areas = self._areas()

    # ---- construction helpers -------------------------------------------------
    def _resolve(self, w) -> tuple[float, float]:
        if isinstance(w, tuple) and len(w) == 3 and w[0] == "rel":
            _, home, (east, north) = w
            return _pt(self.sites[home] if home in self.sites else home, east, north)
        if isinstance(w, str):
            if w in self.sites:
                return self.sites[w]
            return P[w]
        return w

    def _region_of(self, m: MobileSpec) -> str | None:
        first = m.home or (m.route[0] if isinstance(m.route[0], str) else None)
        if first is None:
            return None
        if first in COUNTY_OF:
            return COUNTY_OF[first]
        site = next((s for s in SITES if s.id == first), None)
        return COUNTY_OF.get(site.near) if site else None

    def _site_readiness(self, s: SiteSpec) -> Readiness:
        r = self.rng
        return Readiness(score=round(r.uniform(0.72, 0.98), 2), fuelPct=round(r.uniform(55, 100)) if "fuel" in s.capabilities else None,
                         ammunitionPct=round(r.uniform(60, 100)) if "ammunition" in s.capabilities else None,
                         crewPresent=r.randint(40, 400), crewRequired=400 if s.kind == "facility" else 12, commsStatus="nominal", maintenanceDueH=None, faults=[])

    def _mobile_readiness(self, m: MobileSpec) -> Readiness:
        r = self.rng
        crew_req = {"fixed_wing": 2, "helicopter": 4, "multirotor": 1, "ground_vehicle": 4, "vessel": 24, "personnel": 32, "unknown": 0}[m.kind]
        if m.affiliation == "unknown":
            return Readiness(score=0, commsStatus="n/a")
        fuel = round(r.uniform(35, 100))
        ammo = round(r.uniform(40, 100)) if m.kind in ("fixed_wing", "ground_vehicle", "vessel", "personnel", "helicopter") else None
        faults = [] if r.random() > 0.15 else [r.choice(["Hydraulic pressure low", "Radio set B intermittent", "Track tension warning", "Nav sensor drift", "Cooling loop pressure"])]
        score = round(min(1.0, 0.35 + 0.35 * fuel / 100 + (0.2 * (ammo / 100) if ammo else 0.2) + 0.1 - 0.25 * len(faults)), 2)
        return Readiness(score=score, fuelPct=fuel, ammunitionPct=ammo, crewPresent=crew_req, crewRequired=crew_req, commsStatus="nominal",
                         maintenanceDueH=round(r.uniform(4, 180), 1), faults=faults)

    def _areas(self) -> list[dict]:
        return [
            {"id": "area-gotland", "label": "Gotland defence sector", "kind": "operational_area", "ring": [[17.9, 56.8], [19.6, 56.8], [19.6, 58.1], [17.9, 58.1], [17.9, 56.8]], "requires": ["garrison-gotland", "radar-gotland", "heli-04"], "priority": 1},
            {"id": "area-oresund", "label": "Öresund approaches", "kind": "operational_area", "ring": [[12.2, 55.3], [13.4, 55.3], [13.4, 56.5], [12.2, 56.5], [12.2, 55.3]], "requires": ["navbase-syd", "radar-syd", "ves-05"], "priority": 2},
            {"id": "area-bothnia", "label": "Bothnia northern approaches", "kind": "operational_area", "ring": [[21.0, 64.3], [24.5, 64.3], [24.5, 66.2], [21.0, 66.2], [21.0, 64.3]], "requires": ["airfield-norr", "garrison-norr", "port-lulea"], "priority": 2},
            {"id": "area-malardalen", "label": "Mälardalen command region", "kind": "operational_area", "ring": [[16.0, 59.0], [18.9, 59.0], [18.9, 60.1], [16.0, 60.1], [16.0, 59.0]], "requires": ["hq-joint", "comms-mitt", "power-mitt", "telecom-stockholm"], "priority": 1},
            {"id": "area-vast", "label": "West coast approaches", "kind": "operational_area", "ring": [[11.0, 57.0], [12.6, 57.0], [12.6, 58.6], [11.0, 58.6], [11.0, 57.0]], "requires": ["navbase-vast", "port-goteborg", "radar-vast"], "priority": 3},
            {"id": "zone-exercise-skovde", "label": "Exercise area Väst (restricted, synthetic)", "kind": "restricted_zone", "ring": [[13.6, 58.3], [14.2, 58.3], [14.2, 58.6], [13.6, 58.6], [13.6, 58.3]], "requires": [], "priority": 4},
            {"id": "zone-sensor-gotland", "label": "Sensor coverage Gotland (model: 180 km nominal)", "kind": "coverage_model", "ring": [[p[0], p[1]] for p in geo.circle_ring(self.sites["radar-gotland"], 180_000, 64)], "requires": ["radar-gotland"], "priority": 5},
        ]

    # ---- kinematics -----------------------------------------------------------
    def state_at(self, ent: WorldEntity, t: float) -> tuple[tuple[float, float], float | None, float, float]:
        """Return ([lng, lat], altitude, heading_deg, speed_mps) for the entity at scenario time t (seconds)."""
        spec = ent.spec
        if isinstance(spec, SiteSpec) or not ent.waypoints:
            pos = ent.base.position
            return ((pos.longitudeDeg, pos.latitudeDeg), pos.altitudeM, 0.0, 0.0)
        alt = spec.altitude_m
        wps, legs, total = ent.waypoints, ent.leg_lengths, ent.total_length
        if t < spec.start_s or total <= 0:
            h = geo.bearing_deg(wps[0], wps[1]) if len(wps) > 1 else 0.0
            return (wps[0], alt, h, 0.0)
        elapsed = t - spec.start_s
        cycle = total / spec.speed_mps + spec.hold_s
        if spec.loop:
            elapsed = elapsed % cycle
        dist = elapsed * spec.speed_mps
        if dist >= total:  # holding at the end of the route
            h = geo.bearing_deg(wps[-2], wps[-1]) if len(wps) > 1 else 0.0
            return (wps[-1], alt, h, 0.0)
        for i, leg in enumerate(legs):
            if dist <= leg:
                f = dist / leg if leg > 0 else 0
                return (geo.interpolate(wps[i], wps[i + 1], f), alt, geo.bearing_deg(wps[i], wps[i + 1]), spec.speed_mps)
            dist -= leg
        return (wps[-1], alt, 0.0, 0.0)

    def samples(self, ent: WorldEntity, t_from: float, t_to: float, step_s: float) -> list[list[float]]:
        """Historical track samples [[lng, lat, altM|null, tS], ...] between two scenario times."""
        out = []
        t = max(0.0, t_from)
        while t <= t_to:
            (lng, lat), alt, _, _ = self.state_at(ent, t)
            out.append([round(lng, 6), round(lat, 6), alt, round(t, 1)])
            t += step_s
        return out

    def entity_at(self, ent: WorldEntity, t: float, observed_iso: str, revision: int) -> SceneEntity:
        (lng, lat), alt, heading, speed = self.state_at(ent, t)
        spec = ent.spec
        datum = "AGL" if isinstance(spec, SiteSpec) or spec.kind in ("multirotor", "helicopter", "personnel", "ground_vehicle") else "MSL"
        e = ent.base.model_copy(deep=True)
        e.position = GeoPosition(longitudeDeg=round(lng, 6), latitudeDeg=round(lat, 6), altitudeM=alt, altitudeDatum=datum if alt is not None else "UNKNOWN",
                                 horizontalAccuracyM=None if e.affiliation != "unknown" else 1500.0)
        e.kinematics = Kinematics(headingDeg=round(heading, 1), speedMps=round(speed, 2))
        e.condition = ent.condition  # type: ignore[assignment]
        e.readiness = ent.readiness.model_copy(deep=True) if ent.readiness else None
        if e.affiliation == "unknown":
            e.track = None  # the simulator's route is not something an operator could know
        e.observedAt = observed_iso
        e.worldRevision = revision
        return e
