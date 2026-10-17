# Integration matrix

Status vocabulary: `working` (tested end to end), `partial`, `simulated` (internally generated, labelled), `adapter-only`, `planned`, `blocked`.

| Capability | Status | Evidence / next step |
|---|---|---|
| Synthetic order of battle (~1,000 platforms, 262 formations) | simulated | `orbat.py`, `test_world.py` |
| Road / street / sea routing (OSM-derived, ODbL) | working | `geonet.py`, `test_geonet.py`, E2E-03 |
| Motion model with TS twin | working | `test_motion.py` + `motion.test.ts` (shared fixture) |
| Site layouts (airbase, naval base, garrison, depot, radar) | simulated | `sitegen.py`, E2E-04/05 |
| Rule engine R01–R18 | working | `test_rules.py`, `test_scenario.py` |
| Source fusion (Admiralty grading) | working | `fusion.py`, E2E-06 |
| Deception indicators | working (declared weights) | `deception.py`, E2E-06 |
| Multi-hypothesis prediction | working (declared models) | `predict.py`, E2E-06 |
| Trajectory planner + execution | working | `planner.py`, `test_engine_api.py`, E2E-08 |
| Scenario injection (6 presets) | working (simulated content) | `scenario.py`, E2E-10 |
| H3 analysis surfaces (6) | working | `scene/analysis.ts`, E2E-07 |
| NATO APP-6 symbology | working | milsymbol 3.0.4 |
| 3D procedural models (53) | working | `scene/three`, `models.test.ts`, E2E-05 |
| ADS-B aircraft — adsb.lol (ODbL) | working | rate-limited ~1 req/10 s; OpenSky fallback |
| GNSS integrity from ADS-B | working | NIC/NACp; sparse at night |
| AIS — Digitraffic (CC BY 4.0) | working | coverage: northern Baltic and Bothnia only |
| AIS — AISStream | working (keyed) | whole Swedish coast; long-lived stream locally, 6 s bursts per minute on Vercel |
| SMHI observations and warnings (CC BY 4.0) | working | warnings feed rule R07 |
| Open-Meteo grid (CC BY 4.0, non-commercial) | working | 288 points hourly, inside free quota |
| RainViewer radar | working | max zoom 7 on the free tier |
| Polisen events | working | county-level positions; drone keywords feed R16 / deception |
| Krisinformation | working | |
| NOAA SWPC Kp | working | |
| Trafikverket road situations | working (keyed) | accidents, obstructions, restrictions; land route planning avoids them |
| Active fires — NASA FIRMS (VIIRS) | working (keyed) | `FIRMS_MAP_KEY`; 24 h thermal anomalies, Sweden + Baltic |
| OpenSky OAuth | working (keyed) | `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET`; ADS-B fallback |
| Imagery (EOX Sentinel-2) | working | 10 m, non-commercial; Lantmäteriet orthophoto planned (key) |
| Real military sites and identities | not in scope | AGENTS.md: synthetic only |
| AI layers | planned by design | excluded from the demo path |
