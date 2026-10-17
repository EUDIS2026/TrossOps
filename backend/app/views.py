"""Roles → modes → layers. The frontend renders exactly what this says; nothing about the view model is hardcoded there.

Layers are dot-separated ids grouped into families (air, land, sea, sites, infra, civil, live, env, picture,
analysis, detail). A mode lists the layers it turns on; the operator can override any of them. Analysis layers
are mutually exclusive (one surface at a time keeps the picture readable). Detail layers apply when the camera is
inside a site (zoom ≥ 13): they split the installation into infrastructure, logistics, defence and personnel.
"""
from __future__ import annotations

from .models import LayerDef, ModeDef, RoleDef

G = {"air": "Air", "land": "Land", "sea": "Sea", "sites": "Sites", "infra": "Infrastructure", "civil": "Civil", "live": "Live (real feeds)",
     "env": "Environment (real)", "picture": "Picture", "analysis": "Analysis", "detail": "Site detail"}


def L(id_: str, label: str, desc: str, kinds: list[str] | None = None, **kw) -> LayerDef:
    return LayerDef(id=id_, label=label, group=G[id_.split(".")[0] if not id_.startswith("track.") else "picture"], description=desc, sourceKinds=kinds or ["simulated"], **kw)  # type: ignore[arg-type]


LAYERS: list[LayerDef] = [
    L("air.fighter", "Fighters", "Fighter wings: aircraft in shelters, on QRA and on combat air patrol", supports3d=True),
    L("air.transport", "Transport & surveillance", "Airlift, airborne early warning and signals intelligence aircraft", supports3d=True),
    L("air.rotary", "Helicopters", "Transport, SAR and medevac helicopters", supports3d=True),
    L("air.uav", "UAVs", "Tactical unmanned aircraft", supports3d=True),
    L("land.manoeuvre", "Manoeuvre units", "Mechanised, armoured and ranger units down to each vehicle", supports3d=True),
    L("land.fires", "Artillery", "Self-propelled artillery batteries", supports3d=True),
    L("land.ad", "Air defence", "Air-defence launchers and radars (engagement envelopes in Analysis → Coverage)", supports3d=True),
    L("land.support", "Command & support", "Headquarters, command posts and engineers", supports3d=True),
    L("land.logistics", "Logistics", "Supply and fuel convoys, recovery and medical", supports3d=True),
    L("land.homeguard", "Home Guard", "Territorial battalions protecting critical sites", supports3d=True),
    L("sea.combat", "Surface combatants", "Corvettes, patrol ships and mine countermeasures", supports3d=True),
    L("sea.amphib", "Amphibious", "Fast assault craft", supports3d=True),
    L("sea.sub", "Submarines", "Own submarines (submerged positions are own knowledge only)", supports3d=True),
    L("sea.support", "Support ships", "Logistics and support vessels", supports3d=True),
    L("sites.air", "Airbases", "Airbases and heliports with shelters, fuel and ammunition", supports3d=True),
    L("sites.land", "Garrisons & HQ", "Garrisons, motor pools and headquarters", supports3d=True),
    L("sites.sea", "Naval bases", "Naval bases, piers and berths", supports3d=True),
    L("sites.logistics", "Depots", "Ammunition, fuel and spares depots", supports3d=True),
    L("sites.medical", "Medical", "Field hospitals"),
    L("infra.sensors", "Sensor sites", "Air and sea surveillance radars"),
    L("infra.comms", "Comms nodes", "Military communications hubs"),
    L("infra.power", "Power grid", "Grid nodes (civil operator)", ["simulated", "public"]),
    L("infra.transport", "Ports & crossings", "Ports and fixed crossings (civil)", ["simulated", "public"]),
    L("infra.telecom", "Telecom", "Telecom cores (civil operator)", ["simulated", "public"]),
    L("infra.cables", "Undersea cables", "Cable and pipeline corridors (approximate public routes, illustrative)", ["public"]),
    L("civil.police", "Police patrols", "Patrol cars roaming city streets (synthetic fleet on real street networks)"),
    L("civil.ems", "Ambulances", "Ambulances on city streets (synthetic fleet on real street networks)"),
    L("civil.coastguard", "Coast guard", "Coast guard vessels (synthetic positions)"),
    L("civil.police_events", "Police events", "Public police event feed (polisen.se, real, municipality-level positions)", ["public"]),
    L("civil.crisis", "Crisis information", "Krisinformation.se news and public warnings (real)", ["public"]),
    L("civil.traffic", "Road incidents", "Trafikverket accidents, obstructions and restrictions (real); ground routes avoid them", ["public"]),
    L("live.air", "Air traffic", "Live ADS-B aircraft over Sweden and the Baltic (adsb.lol / OpenSky, real)", ["observed"], supports3d=True),
    L("live.air_mil", "Military-flagged aircraft", "Live ADS-B aircraft flagged as military in the public database (real)", ["observed"], supports3d=True),
    L("live.sea", "Ship traffic", "Live AIS vessel positions (Digitraffic / AISStream, real)", ["observed"], supports3d=True),
    L("env.radar", "Precipitation radar", "RainViewer radar mosaic (real, past 2 h animated)", ["public"]),
    L("env.wind", "Wind field", "Open-Meteo 10 m wind, animated streamlines (real)", ["public"]),
    L("env.obs", "Weather stations", "SMHI observations, latest hour (real)", ["public"]),
    L("env.warnings", "Weather warnings", "SMHI impact-based warnings (real)", ["public"]),
    L("env.daylight", "Day / night", "Solar terminator and twilight (computed)", ["public"]),
    L("env.fires", "Active fires", "NASA FIRMS VIIRS thermal anomalies, last 24 h (real)", ["public"]),
    L("track.unknown", "Unknown & suspect tracks", "Sensor tracks without resolved identity", ["observed"]),
    L("picture.predictions", "Predictions", "Competing trajectory hypotheses with probabilities", ["predicted"]),
    L("picture.plans", "Planned routes", "Committed trajectory plans and declared convoy routes", ["planned"]),
    L("picture.trails", "Track history", "Recent positions of the selected unit and unknown tracks"),
    L("picture.areas", "Operational areas", "Defence sectors, restricted zones and modelled coverage"),
    L("picture.reports", "Reports", "Geolocated inputs from all channels", ["simulated", "observed", "public"]),
    L("picture.interventions", "Interventions", "Proposed and committed courses of action", ["inferred"]),
    L("picture.labels", "Labels", "Unit designations and names"),
    L("analysis.fusion", "Fusion attention", "Where the rule engine says to look, with the reasons per cell", ["inferred"]),
    L("analysis.threat", "Threat reach", "Minutes until an unknown or suspect track could reach each cell", ["predicted"]),
    L("analysis.coverage", "Sensor & AD coverage", "Radar and air-defence coverage at 1,000 m; gaps highlighted", ["inferred"]),
    L("analysis.response", "Response time", "Minutes for the nearest ready fighter, helicopter or ground unit", ["inferred"]),
    L("analysis.weather", "Flight conditions", "VFR / marginal / IFR from visibility, cloud and wind (real data)", ["public"]),
    L("analysis.gnss", "GNSS interference", "Share of aircraft reporting degraded GNSS integrity (real ADS-B)", ["observed"]),
    L("detail.infra", "Infrastructure", "Runways, taxiways, shelters, piers and buildings inside a site", supports3d=True),
    L("detail.logistics", "Logistics", "Fuel farms with fill levels, ammunition storage, motor pools", supports3d=True),
    L("detail.defence", "Defence", "Perimeter, gates and defensive positions"),
    L("detail.personnel", "Personnel", "Barracks and accommodation", supports3d=True),
]

AIR = ["air.fighter", "air.transport", "air.rotary", "air.uav"]
LAND = ["land.manoeuvre", "land.fires", "land.ad", "land.support", "land.logistics"]
SEA = ["sea.combat", "sea.amphib", "sea.sub", "sea.support"]
SITES = ["sites.air", "sites.land", "sites.sea", "sites.logistics", "sites.medical"]
INFRA = ["infra.sensors", "infra.comms", "infra.power", "infra.transport", "infra.telecom"]
DETAIL = ["detail.infra", "detail.logistics", "detail.defence", "detail.personnel"]
BASE = ["picture.labels", "track.unknown"] + DETAIL

CAM_NATIONAL = {"lng": 17.2, "lat": 61.2, "zoom": 4.7, "pitch": 0, "bearing": 0}
CAM_SOUTH = {"lng": 15.2, "lat": 56.9, "zoom": 6.3, "pitch": 30, "bearing": 0}
CAM_NORTH = {"lng": 21.0, "lat": 65.6, "zoom": 6.0, "pitch": 30, "bearing": 0}
CAM_BALTIC = {"lng": 18.4, "lat": 57.6, "zoom": 6.3, "pitch": 25, "bearing": 0}
CAM_WEST = {"lng": 12.0, "lat": 57.6, "zoom": 6.8, "pitch": 25, "bearing": 0}
CAM_STHLM = {"lng": 18.05, "lat": 59.33, "zoom": 11.2, "pitch": 45, "bearing": -10}
CAM_GOTLAND = {"lng": 19.1, "lat": 57.3, "zoom": 7.2, "pitch": 35, "bearing": 10}


def mode(id_: str, label: str, desc: str, layers: list[str], cam: dict, kpis: list[str]) -> ModeDef:
    return ModeDef(id=id_, label=label, description=desc, layers=list(dict.fromkeys(layers + BASE)), camera=cam, kpis=kpis)


ROLES: list[RoleDef] = [
    RoleDef(id="national_commander", label="National commander", scope="national", description="Sweden as one asset: forces, threats, sustainment and civil functions.", defaultModeId="overview", modes=[
        mode("overview", "Overview", "Every formation by echelon, sites and the fused attention picture", AIR + LAND + SEA + SITES + ["analysis.fusion"], CAM_NATIONAL, ["readiness", "airborne", "alerts"]),
        mode("threat", "Threat", "Unknown and suspect tracks, predictions, threat reach and coverage", ["picture.predictions", "air.fighter", "land.ad", "sea.combat", "infra.sensors", "infra.cables", "live.air_mil", "picture.areas", "analysis.threat"], CAM_BALTIC, ["unknown", "critical", "deception"]),
        mode("readiness", "Readiness", "Readiness by formation and the national response-time surface", AIR + LAND + SEA + SITES + ["land.homeguard", "analysis.response"], CAM_NATIONAL, ["readiness", "unavailable", "fuel"]),
        mode("civil", "Civil functions", "Power, telecom, transport, police events and warnings", INFRA + ["infra.cables", "civil.police_events", "civil.crisis", "env.warnings", "picture.reports", "analysis.fusion"], CAM_NATIONAL, ["infra", "incidents", "weather"]),
    ]),
    RoleDef(id="air_ops", label="Air operations", scope="functional", description="Air picture, combat air patrols, airbases and flight weather.", defaultModeId="picture", modes=[
        mode("picture", "Air picture", "Own air, real traffic, unknown tracks and coverage", AIR + ["live.air", "live.air_mil", "land.ad", "infra.sensors", "picture.predictions", "analysis.coverage"], CAM_BALTIC, ["airborne", "unknown", "airReady"]),
        mode("airbases", "Airbases", "Inside the bases: shelters, aircraft, fuel, ammunition, defence", AIR + ["sites.air", "land.ad", "env.obs"], {"lng": 14.37, "lat": 55.99, "zoom": 13.4, "pitch": 60, "bearing": -30}, ["airReady", "fuel", "faults"]),
        mode("weather", "Flight weather", "Flight conditions, radar, wind and warnings", AIR + ["analysis.weather", "env.radar", "env.wind", "env.warnings", "env.obs", "env.fires"], CAM_NATIONAL, ["airborne", "weather", "airReady"]),
    ]),
    RoleDef(id="maritime_ops", label="Maritime operations", scope="functional", description="Sea picture, real shipping, undersea infrastructure and approaches.", defaultModeId="picture", modes=[
        mode("picture", "Sea picture", "Own ships, real AIS traffic and unknown contacts", SEA + ["civil.coastguard", "live.sea", "picture.predictions", "infra.sensors", "sites.sea"], CAM_BALTIC, ["unknown", "seaReady", "deception"]),
        mode("infrastructure", "Undersea infrastructure", "Cable corridors, loitering and AIS anomalies", ["infra.cables", "live.sea", "sea.combat", "civil.coastguard", "picture.predictions", "analysis.fusion"], CAM_GOTLAND, ["deception", "unknown", "critical"]),
    ]),
    RoleDef(id="land_ops", label="Army operations", scope="functional", description="Brigades down to each vehicle on its road; fires, air defence and sustainment.", defaultModeId="manoeuvre", modes=[
        mode("manoeuvre", "Manoeuvre", "Brigades, battalions and companies on the road network", LAND + ["land.homeguard", "sites.land", "picture.plans", "analysis.response", "civil.traffic"], CAM_SOUTH, ["landReady", "moving", "alerts"]),
        mode("logistics", "Sustainment", "Supply convoys, fuel and depots", ["land.logistics", "sites.logistics", "sites.land", "sea.support", "picture.plans"], CAM_NATIONAL, ["fuel", "faults", "interventions"]),
    ]),
    RoleDef(id="intelligence", label="Intelligence", scope="functional", description="Fusion, deception indicators, predictions and coverage.", defaultModeId="assessment", modes=[
        mode("assessment", "Assessment", "All channels, fused attention and deception indicators", ["picture.predictions", "picture.reports", "infra.cables", "live.air_mil", "analysis.fusion"], CAM_NATIONAL, ["inputs", "unknown", "deception"]),
        mode("coverage", "Sensor coverage", "Radar and air-defence coverage with gaps", ["infra.sensors", "land.ad", "air.transport", "analysis.coverage"], CAM_BALTIC, ["coverage", "unknown", "alerts"]),
        mode("gnss", "GNSS interference", "Real ADS-B integrity reports aggregated into hexes", ["live.air", "analysis.gnss"], CAM_BALTIC, ["unknown", "alerts", "inputs"]),
    ]),
    RoleDef(id="police", label="Police & emergency services", scope="functional", description="Patrol cars and ambulances on city streets, police events and crisis information.", defaultModeId="patrol", modes=[
        mode("patrol", "Patrol picture", "Patrol cars and ambulances roaming city streets", ["civil.police", "civil.ems", "civil.police_events", "civil.crisis", "picture.reports", "civil.traffic"], CAM_STHLM, ["incidents", "alerts", "inputs"]),
        mode("national", "National events", "Police events and crisis information nationwide", ["civil.police_events", "civil.crisis", "env.warnings", "civil.police", "analysis.fusion"], CAM_NATIONAL, ["incidents", "weather", "alerts"]),
    ]),
    RoleDef(id="civil_defence", label="Civil defence", scope="functional", description="Emergencies, infrastructure and public information.", defaultModeId="emergencies", modes=[
        mode("emergencies", "Emergencies", "Incidents, medevac and medical capacity", ["picture.reports", "civil.ems", "air.rotary", "sites.medical", "env.warnings", "civil.crisis", "env.fires"], CAM_NATIONAL, ["incidents", "infra", "weather"]),
        mode("infrastructure", "Infrastructure", "Grid, telecom, ports, crossings and cables", INFRA + ["infra.cables", "civil.police_events", "picture.reports", "analysis.fusion"], CAM_NATIONAL, ["infra", "incidents", "alerts"]),
    ]),
    RoleDef(id="logistics", label="Logistics", scope="functional", description="Depots, convoys, fuel autonomy and recovery.", defaultModeId="supply", modes=[
        mode("supply", "Supply", "Depots, convoys and resupply interventions", ["land.logistics", "sites.logistics", "sites.land", "sea.support", "picture.plans", "picture.interventions"], CAM_NATIONAL, ["fuel", "faults", "interventions"]),
    ]),
    RoleDef(id="regional_south", label="Regional commander South", scope="regional", description="Skåne, Blekinge, Kronoberg, Kalmar, Gotland and the southern Baltic.", defaultModeId="operations", modes=[
        mode("operations", "Operations", "Units, areas and tracks in the southern region", AIR + LAND + SEA + SITES + ["picture.predictions", "picture.areas"], CAM_SOUTH, ["readiness", "unknown", "alerts"]),
        mode("sustainment", "Sustainment", "Southern logistics and maintenance", ["land.logistics", "sites.logistics", "sites.land", "picture.interventions"], CAM_SOUTH, ["fuel", "faults", "interventions"]),
    ]),
    RoleDef(id="regional_north", label="Regional commander North", scope="regional", description="Norrbotten, Västerbotten and the Gulf of Bothnia.", defaultModeId="operations", modes=[
        mode("operations", "Operations", "Units, areas and tracks in the north", AIR + LAND + SEA + SITES + ["picture.predictions", "picture.areas"], CAM_NORTH, ["readiness", "unknown", "alerts"]),
    ]),
]

REGION_SCOPE: dict[str, list[str]] = {
    "regional_south": ["06", "07", "08", "09", "10", "12", "13"],
    "regional_north": ["22", "23", "24", "25"],
}
EXCLUSIVE_GROUPS = ["analysis"]
