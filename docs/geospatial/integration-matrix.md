# Integration matrix

Status vocabulary: `working` (tested end to end), `partial`, `simulated` (internally generated, labelled),
`adapter-only` (code and parser ready, credentials or first fetch missing), `planned`, `blocked`.

Feed statuses are computed at run time by `backend/app/feeds/base.py` and shown in **Data sources** and
`GET /api/sources`: `working` after a good parse, `partial` when serving the last good data after an error (marked
`stale`) or when some sub-requests failed, `blocked` on errors with no data or with `TROSSOPS_FEEDS=off`,
`adapter-only` when a key is missing or before the first fetch. The column below is the status with its key
configured and the network up (observed on the owner's machine, 17 October 2026); without the key it is `adapter-only`.

## Synthetic scenario and engine

| Capability | Status | Evidence |
|---|---|---|
| Order of battle (~1,020 platforms, 267 formations, 42 sites) | simulated | `orbat.py`, `test_world.py` |
| Placement on the right ground (sites dry and road-free, units on land, ships at sea) | working | `orbat.py` (`_place_site`, `on_ground`, `at_sea`), `land.bin`, `test_ground.py` |
| Road / street / sea routing (OSM-derived, ODbL) | working | `geonet.py`, `test_geonet.py`, smoke E2E-07 |
| Motion model with TypeScript twin | working | `test_motion.py` + `motion.test.ts` (shared fixture) |
| Site layouts (airbase, naval base, garrison, depot, radar) | simulated | `sitegen.py`, smoke E2E-08 |
| Rule engine (18 rules, R01–R19) | working | `rules.py`, `test_rules.py`, `test_scenario.py` |
| Source fusion (Admiralty grading) | working | `fusion.py`, smoke E2E-10 |
| Deception indicators | working (declared weights) | `deception.py`, smoke E2E-10 |
| Multi-hypothesis prediction | working (declared models) | `predict.py`, smoke E2E-10 |
| Route planner + execution | working | `planner.py`, `test_engine_api.py`, smoke E2E-12/13 |
| Optimiser (Hungarian assignment) | working | `optimize.py`, `test_engine_api.py` |
| Scenario injection (6 presets) | working (simulated content) | `scenario.py`, smoke E2E-15 |
| Real feeds as rule inputs (SMHI warnings, police drone/sabotage events, squawks, GNSS clusters, R19 patterns) | working | `feed_inputs.py`, `test_feeds.py`, `test_contracts.py` |
| H3 analysis surfaces (6) | working | `scene/analysis.ts`, smoke E2E-11 |
| NATO APP-6 symbology | working | milsymbol 3.0.4 |
| 3D procedural models (53) | working | `scene/three`, `models.test.ts`, smoke E2E-09 |

## Real public feeds

| Feed (`id`) | Status with key | Key | Notes |
|---|---|---|---|
| ADS-B: adsb.lol, OpenSky fallback (`adsb`) | working | optional `OPENSKY_CLIENT_ID` / `_SECRET` | ODbL; ~1 req / 10 s; military flag from the adsb.lol database |
| GNSS integrity from ADS-B (`/api/live/gnss`) | working | — | NIC / NACp; sparse at night; indicative only |
| AIS: Digitraffic (`ais-digitraffic`) | working | none | CC BY 4.0; northern Baltic and Bothnia only |
| AIS: AISStream (`aisstream`) | working | `AISSTREAM_API_KEY` | whole coast; long-lived stream locally, short bursts on Vercel |
| SMHI observations (`smhi-obs`) and warnings (`smhi-warnings`) | working | none | CC BY 4.0; warnings feed R07 |
| SMHI point forecasts (`/api/environment/*`) | working | none | city reference points |
| Open-Meteo grid (`open-meteo`) | working | none | CC BY 4.0, non-commercial; wind and flight conditions |
| RainViewer (`rainviewer`) | working | none | max zoom 7 on the free tier |
| Polisen (`polisen`) | working | none | municipality / county centroids; drone keywords feed R16 and deception |
| Krisinformation (`krisinformation`) | working | none | news (3 days) and active VMA |
| NOAA SWPC Kp (`swpc-kp`) | working | none | public domain |
| Trafikverket road situations (`trafikverket`) | working | `TRAFIKVERKET_API_KEY` | ground routes avoid incidents |
| NASA FIRMS active fires (`firms`) | working | `FIRMS_MAP_KEY` | VIIRS ×3, last 24 h; not every detection is a wildfire |
| Lantmäteriet Markhöjd Direkt (`lm-markhojd`) | working | `LANTMATERIET_USERNAME` / `_PASSWORD` (or client id / secret, or token) | route ground profiles, air terrain clearance, `/api/terrain/elevation`, `/api/terrain/los`; 503 without credentials |

## Map and other

| Capability | Status | Notes |
|---|---|---|
| Basemap (OpenFreeMap), terrain (Mapterhorn), imagery (EOX Sentinel-2) | working | loaded by the browser; offline basemap fallback |
| Lantmäteriet orthophoto | not used | paid licence |
| Real military sites and identities | not in scope | AGENTS.md: synthetic only |
| AI layers | planned by design | excluded from the demo path |
