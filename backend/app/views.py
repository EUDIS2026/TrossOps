"""Roles → modes → layers. The frontend renders exactly what this says; nothing about the view model is hardcoded there."""
from __future__ import annotations

from .models import LayerDef, ModeDef, RoleDef

LAYERS: list[LayerDef] = [
    LayerDef(id="units_air", label="Air units", group="Units", description="Own and allied fixed-wing, helicopters and drones", supports3d=True, sourceKinds=["simulated"], legend=[{"swatch": "own", "label": "Own"}, {"swatch": "allied", "label": "Allied"}]),
    LayerDef(id="units_land", label="Land units", group="Units", description="Armour, mechanised, logistics, medical, engineers, personnel", supports3d=True, sourceKinds=["simulated"]),
    LayerDef(id="units_sea", label="Sea units", group="Units", description="Naval and coast guard vessels, civil shipping of interest", supports3d=True, sourceKinds=["simulated"]),
    LayerDef(id="unknown_tracks", label="Unknown tracks", group="Picture", description="Sensor tracks without resolved identity", sourceKinds=["observed"], legend=[{"swatch": "unknown", "label": "Unidentified"}]),
    LayerDef(id="predictions", label="Predicted paths", group="Picture", description="Dead-reckoned 30 min paths with growing uncertainty", sourceKinds=["predicted"], legend=[{"swatch": "predicted", "label": "Predicted (dashed)"}]),
    LayerDef(id="plans", label="Planned movement", group="Picture", description="Declared routes of own units", sourceKinds=["planned"], legend=[{"swatch": "planned", "label": "Planned (dotted)"}]),
    LayerDef(id="trails", label="Track history", group="Picture", description="Last 20 minutes of observed positions", sourceKinds=["simulated", "observed"]),
    LayerDef(id="sites", label="Sites", group="Infrastructure", description="Garrisons, airfields, naval bases, depots, hospitals", supports3d=True, sourceKinds=["simulated"]),
    LayerDef(id="infrastructure", label="Critical infrastructure", group="Infrastructure", description="Sensor sites, comms nodes, grid nodes, ports, crossings, telecom", supports3d=True, sourceKinds=["simulated", "public"]),
    LayerDef(id="areas", label="Operational areas", group="Analysis", description="Defence sectors, restricted zones and modelled coverage", sourceKinds=["simulated"]),
    LayerDef(id="attention", label="Attention surface", group="Analysis", description="Rule-engine attention, 2D heat or 3D columns", supports3d=True, sourceKinds=["inferred"], legend=[{"swatch": "attention", "label": "Attention weight"}]),
    LayerDef(id="incidents", label="Incidents and reports", group="Analysis", description="Geolocated inputs from all channels", sourceKinds=["simulated", "observed", "public"]),
    LayerDef(id="interventions", label="Interventions", group="Analysis", description="Proposed and committed paths of action", sourceKinds=["inferred"]),
    LayerDef(id="counties", label="County boundaries", group="Geography", description="SCB county boundaries (public, CC0, display only)", sourceKinds=["public"]),
    LayerDef(id="weather", label="Weather", group="Geography", description="SMHI point forecasts and advisories (public)", sourceKinds=["public"]),
    LayerDef(id="labels", label="Labels", group="Geography", description="Entity labels (collision-managed)", minZoom=6),
]

CAM_NATIONAL = {"lng": 17.0, "lat": 62.3, "zoom": 4.4, "pitch": 0, "bearing": 0}
CAM_SOUTH = {"lng": 15.0, "lat": 57.3, "zoom": 6.0, "pitch": 0, "bearing": 0}
CAM_NORTH = {"lng": 20.5, "lat": 65.4, "zoom": 5.6, "pitch": 0, "bearing": 0}
CAM_BALTIC = {"lng": 18.6, "lat": 57.9, "zoom": 6.2, "pitch": 0, "bearing": 0}
CAM_WEST = {"lng": 12.2, "lat": 57.6, "zoom": 6.6, "pitch": 0, "bearing": 0}

UNIT_LAYERS = ["units_air", "units_land", "units_sea"]
PICTURE = ["unknown_tracks", "predictions"]


def mode(id_: str, label: str, desc: str, layers: list[str], cam: dict, kpis: list[str]) -> ModeDef:
    return ModeDef(id=id_, label=label, description=desc, layers=layers, camera=cam, kpis=kpis)


ROLES: list[RoleDef] = [
    RoleDef(id="national_commander", label="National commander", scope="national", description="Sweden as one asset: readiness, threats, sustainment and civil functions.", defaultModeId="readiness", modes=[
        mode("readiness", "Readiness", "Force readiness and condition across the country", UNIT_LAYERS + ["sites", "attention", "labels"], CAM_NATIONAL, ["readiness", "unavailable", "alerts"]),
        mode("threat", "Threat", "Unknown tracks, predictions and sensor coverage", PICTURE + ["units_air", "units_sea", "areas", "attention", "infrastructure", "labels"], CAM_NATIONAL, ["unknown", "critical", "coverage"]),
        mode("sustainment", "Sustainment", "Fuel, supply, maintenance and depots", ["units_land", "units_sea", "sites", "interventions", "attention", "labels"], CAM_NATIONAL, ["fuel", "faults", "interventions"]),
        mode("civil", "Civil functions", "Power, telecom, transport and emergencies", ["infrastructure", "incidents", "attention", "weather", "counties", "labels"], CAM_NATIONAL, ["infra", "incidents", "weather"]),
        mode("decisions", "Decisions", "Alerts, interventions and the optimised plan", ["interventions", "incidents", "attention"] + UNIT_LAYERS + ["labels"], CAM_NATIONAL, ["alerts", "interventions", "plan"]),
    ]),
    RoleDef(id="regional_south", label="Regional commander South", scope="regional", description="Skåne, Blekinge, Kronoberg, Kalmar, Gotland and the southern Baltic.", defaultModeId="operations", modes=[
        mode("operations", "Operations", "Units, areas and tracks in the southern region", UNIT_LAYERS + PICTURE + ["sites", "areas", "labels"], CAM_SOUTH, ["readiness", "unknown", "alerts"]),
        mode("sustainment", "Sustainment", "Southern logistics and maintenance", ["units_land", "sites", "interventions", "attention", "labels"], CAM_SOUTH, ["fuel", "faults", "interventions"]),
        mode("civil", "Civil", "Civil functions in the south", ["infrastructure", "incidents", "weather", "counties", "attention", "labels"], CAM_SOUTH, ["infra", "incidents", "weather"]),
    ]),
    RoleDef(id="regional_north", label="Regional commander North", scope="regional", description="Norrbotten, Västerbotten and the Gulf of Bothnia.", defaultModeId="operations", modes=[
        mode("operations", "Operations", "Units, areas and tracks in the north", UNIT_LAYERS + PICTURE + ["sites", "areas", "labels"], CAM_NORTH, ["readiness", "unknown", "alerts"]),
        mode("sustainment", "Sustainment", "Northern logistics and winter maintenance", ["units_land", "sites", "interventions", "attention", "labels"], CAM_NORTH, ["fuel", "faults", "interventions"]),
    ]),
    RoleDef(id="air_ops", label="Air operations", scope="functional", description="Air picture, patrols, airfields and weather.", defaultModeId="picture", modes=[
        mode("picture", "Air picture", "Air units, unknown air tracks and predictions", ["units_air", "unknown_tracks", "predictions", "infrastructure", "weather", "labels"], CAM_BALTIC, ["unknown", "airReady", "weather"]),
        mode("airfields", "Airfields", "Airfield status and fuel", ["units_air", "sites", "interventions", "labels"], CAM_NATIONAL, ["fuel", "faults", "interventions"]),
    ]),
    RoleDef(id="maritime_ops", label="Maritime operations", scope="functional", description="Sea picture, vessels, ports and approaches.", defaultModeId="picture", modes=[
        mode("picture", "Sea picture", "Vessels, unknown sea tracks and approaches", ["units_sea", "unknown_tracks", "predictions", "areas", "infrastructure", "labels"], CAM_BALTIC, ["unknown", "seaReady", "coverage"]),
        mode("west", "West coast", "Kattegat and Öresund", ["units_sea", "unknown_tracks", "predictions", "areas", "infrastructure", "labels"], CAM_WEST, ["unknown", "seaReady", "coverage"]),
    ]),
    RoleDef(id="logistics", label="Logistics", scope="functional", description="Depots, convoys, fuel autonomy and recovery.", defaultModeId="supply", modes=[
        mode("supply", "Supply", "Depots, convoys and resupply interventions", ["units_land", "units_sea", "sites", "interventions", "plans", "labels"], CAM_NATIONAL, ["fuel", "faults", "interventions"]),
        mode("maintenance", "Maintenance", "Faults, recovery teams and workshops", ["units_land", "sites", "interventions", "attention", "labels"], CAM_NATIONAL, ["faults", "unavailable", "interventions"]),
    ]),
    RoleDef(id="intelligence", label="Intelligence", scope="functional", description="Reports, assessments, unknown tracks and attention.", defaultModeId="assessment", modes=[
        mode("assessment", "Assessment", "All channels, attention surface and unknown tracks", ["incidents", "attention", "unknown_tracks", "predictions", "areas", "labels"], CAM_NATIONAL, ["inputs", "unknown", "critical"]),
        mode("coverage", "Sensor coverage", "Sensor sites and modelled coverage", ["infrastructure", "areas", "unknown_tracks", "labels"], CAM_BALTIC, ["coverage", "unknown", "alerts"]),
    ]),
    RoleDef(id="civil_defence", label="Civil defence", scope="functional", description="Emergencies, infrastructure and public information.", defaultModeId="emergencies", modes=[
        mode("emergencies", "Emergencies", "112 events, medevac and medical assets", ["incidents", "units_air", "units_land", "infrastructure", "weather", "counties", "labels"], CAM_NATIONAL, ["incidents", "infra", "weather"]),
        mode("infrastructure", "Infrastructure", "Grid, telecom, ports and crossings", ["infrastructure", "incidents", "attention", "counties", "labels"], CAM_NATIONAL, ["infra", "incidents", "alerts"]),
    ]),
]

REGION_SCOPE: dict[str, list[str]] = {
    "regional_south": ["06", "07", "08", "09", "10", "12", "13"],
    "regional_north": ["22", "23", "24", "25"],
}
