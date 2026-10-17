# TrossOps

A national operational picture for Sweden on one map. The whole defence is represented as a synthetic order of battle
at national scale, and a deterministic rule engine fuses every input channel, including real public air and sea
traffic, weather, police and crisis feeds. Zoom from the national picture down to a single vehicle on its road, or into
an airbase where the shelters, aircraft, fuel and ammunition each sit on their own layer. No AI in the demo path.

All units, sites and reports are **synthetic** and labelled as such. Real public feeds are labelled `real`.

![National picture](docs/geospatial/screens/v2/01-national.png)

| | |
|---|---|
| ![Convoy on its road in 3D](docs/geospatial/screens/v2/03-convoy-3d.png) | ![Airbase in 3D](docs/geospatial/screens/v2/04b-airbase-3d.png) |
| ![Threat reach in 3D](docs/geospatial/screens/v2/05-threat-3d.png) | ![Deception assessment](docs/geospatial/screens/v2/06-deception.png) |

## What it does

- **Order of battle at national scale.** ~1,000 platforms in 262 formations: air wings fly sorties from their shelters
  (taxi, take-off, combat air patrol, landing), brigades road-march on the real road network, flotillas patrol on water
  routes, the Home Guard protects critical sites, and police cars and ambulances roam real city streets.
- **Zoom by echelon.** Formations collapse into one NATO APP-6 symbol while their units fit together on screen, and open
  into battalions, companies and single vehicles as they spread out. A per-zoom symbol budget keeps density readable.
- **Site detail.** Airbases, naval bases, garrisons and depots are laid out procedurally. Runways, taxiways, hardened
  shelters, fuel tanks (by fill level), ammunition storage, piers and motor pools sit on their own detail layers.
- **3D.** 53 procedural models with true attitude (climb, bank, road curvature) on terrain, with spinning rotors and
  radars, and a cinematic fly-in and orbit when you select a site.
- **Fusion that explains itself.** The inspector has **Why** (sources graded A1–F6 on the Admiralty scale,
  corroboration across independent channels, identity hypotheses), **Prediction** (competing trajectory hypotheses
  with probabilities and their basis), **Deception** (named indicators with log-odds weights and the collection that
  would change the assessment) and **Actions**.
- **Analysis surfaces** on H3 hexagons, replacing the heat map: fusion attention, threat reach (minutes), sensor and
  air-defence coverage gaps, response time, flight conditions (real weather) and GNSS interference (real ADS-B).
- **Trajectory planning.** Pick a destination and get route options on roads, water or in the air, each with ETA,
  fuel needed against fuel available, and exposure to threat corridors and weather warnings. Executing an option
  makes the unit drive, sail or fly it.
- **Simulation.** Run the scenario at ×10 to ×300, replay the past, or look up to 3 h ahead. Inject events (drone swarm,
  cable damage, air raid, GNSS jamming, power outage, disinformation) and watch every rule react.
- **Roles and modes.** National commander, air, maritime, army, intelligence, police and emergency services, civil
  defence, logistics and regional commanders. Each role's modes set a curated layer preset; the layer tree overrides it.

## Real public data

| Feed | Licence | Notes |
|---|---|---|
| Aircraft — adsb.lol (OpenSky fallback) | ODbL / OpenSky terms | live positions, military flag, GNSS integrity |
| Ships — Digitraffic (Fintraffic) | CC BY 4.0 | northern Baltic and Bothnia; AISStream with a free key for the whole coast |
| SMHI observations and warnings | CC BY 4.0 | warnings feed the rule engine |
| Open-Meteo (DWD ICON) | CC BY 4.0, non-commercial | wind and flight-condition grid |
| RainViewer | free tier | precipitation radar |
| Polisen, Krisinformation | public APIs | police events, crisis information |
| NOAA SWPC | public domain | Kp index |
| Trafikverket | free key | road situations; planner avoids obstructions (adapter-only without a key) |
| NASA FIRMS | free map key | VIIRS active fires, last 24 h (adapter-only without a key) |
| OpenStreetMap via OpenFreeMap; Mapterhorn; EOX Sentinel-2 | ODbL; open; CC BY-NC-SA | basemap, terrain, imagery, road and sea graphs |

The **Data sources** drawer shows each feed's live status (`working`, `partial`, `blocked` or `adapter-only`).

## Run

```powershell
python -m pip install -r backend\requirements.txt
cd backend; $env:TROSSOPS_START_S = "1300"; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend; npm install; npm run dev        # http://127.0.0.1:5173
```

Optional keys (environment variables, or a gitignored `backend/.env`): `AISSTREAM_API_KEY`, `TRAFIKVERKET_API_KEY`,
`FIRMS_MAP_KEY`, `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET`. To work offline, set `TROSSOPS_FEEDS=off`.

Shortcuts: `/` search · `L` layers · `A` alerts · `D` decisions · `S` simulate · `R` report · `I` sources · `3` 3D ·
`F` follow · `Space` pause/resume · `Esc` close · `Home` reset.

## Check

```powershell
cd backend;  python -m pytest -q                                   # 81 tests
cd frontend; npm run typecheck; npm test; npm run build             # 63 tests
cd frontend; $env:BROWSER_CHANNEL="msedge"; npm run verify          # 12 browser acceptance steps
```

## Deploy (Vercel)

`vercel.json` builds `frontend/` as the static site and serves the FastAPI backend as one Python function
(`api/index.py`). The project is connected to this GitHub repository, so every push to `main` deploys.
`TROSSOPS_EPOCH=hourly` keeps serverless instances in agreement. Commits are stored per instance.

## Layout

```
backend/app    orbat · sitegen · motion · world · geonet · rules · fusion · deception · predict · planner ·
               scenario · engine · feeds/ · feed_inputs · routes_live · main
backend/data   geo/ (road, street and sea graphs) · world_routes.json.gz (route cache)
frontend/src   core (api, clock, motion, world, session, store) · scene (controller, sprites, symbols, models3d,
               three/, analysis, overlays, basemap, camera) · ui (TopBar, Dock, Inspector, Overlays)
scripts/data   reproducible build of the road, street and sea graphs
docs           product · briefs · decisions (ADR-001, ADR-002) · geospatial
```
