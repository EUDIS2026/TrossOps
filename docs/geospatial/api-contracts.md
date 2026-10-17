# API contracts

Base: `http://127.0.0.1:8000` locally (the Vite dev server proxies `/api`), `/api` on Vercel. TypeScript mirrors live in `frontend/src/contracts/types.ts`; the Pydantic models in `backend/app/models.py` and the payloads in `backend/app/engine.py` are the authority. Interactive schema: `GET /docs` (FastAPI OpenAPI).

`backend/tests/test_contracts.py` fails when a route below is missing from this page, when the frontend `Channel` / `FeedStatus` unions drift from the backend, or when a layer has no renderer.

## Synthetic scene (rule engine)

Scene reads carry `worldRevision` and accept `at` (scenario seconds) for replay and simulation.

| Method and path | Purpose | TS type / notes |
|---|---|---|
| `GET /api/health` | status, clock, rule / entity / formation counts, `feeds` (router loaded) | `mode: synthetic` |
| `GET /api/clock` | epoch, `nowS`, `serverNow`, speed, revisions | `Clock` |
| `GET /api/views` | roles → modes → layers, layer catalogue, rule catalogue, input channels, region scope, exclusive groups | `Views`; drives the whole UI |
| `GET /api/world` | order of battle with declared motion, shared route geometry, sites, areas, cables, committed plans | `WorldCatalog`; refetch only when `catalogRevision` changes |
| `GET /api/sites/{site_id}/layout` | synthetic site layout (GeoJSON features, parking spots, runway, footprint) | `SiteLayout`; 404 unknown site |
| `GET /api/scene/snapshot?at&role` | status rows, observed rows, areas, alerts, interventions, predictions, inputs, events, KPIs, layer attention, rule trace, priorities, fusion, deception | `Snapshot`; `statusColumns` names the `StatusRow` columns; 404 unknown role |
| `GET /api/scene/entities?at` | compact rows `[id, lng, lat, altM, headingDeg, speedMps, condition]` | `KinematicsTick`; what stream ticks carry |
| `GET /api/scene/tracks/{entity_id}?from&to&step` | reconstructed samples | `TrackResponse`; `to` clamped to now, default window 20 min |
| `GET /api/scene/attention?at&resolution&role` | cells (score, peak, reasons, contributors) and raw contributions | `AttentionResponse` |
| `GET /api/scene/predictions?at` | trajectory hypotheses with probabilities and uncertainty rings | `PredictedPath[]` |
| `GET /api/entities/{entity_id}?at` | inspector detail: entity or formation, related inputs, alerts, interventions, predictions, plan, fusion, deception, rule trace | `EntityDetail \| FormationDetail`; 404 |
| `GET /api/inputs?at&channel` | reports from every channel (scripted, posted, injected and real-feed derived) | `InputReport[]` |
| `POST /api/inputs` | submit a report; rules extract severity, entity ids, places, tags; bumps the revision | body `InputIn`; feed-only channels (`police_event`, `crisis_info`) are rejected with 422 |
| `GET /api/alerts?at` · `POST /api/alerts/{alert_id}/ack` | alerts / acknowledge (persisted) | `Alert` |
| `GET /api/interventions?at` | proposals with options, outcome bands, progress | `Intervention` |
| `POST /api/interventions/{intervention_id}/commit` | commit an option, body `{optionId, expectedRevision}` | 409 stale revision, 404 unknown |
| `POST /api/interventions/{intervention_id}/abort` | abort | |
| `POST /api/strategy/optimize?at` | Hungarian assignment of units to interventions plus alternatives | `PlanResult` |
| `POST /api/events` | `fault`, `repair`, `resupply`, `comms_loss`, `comms_restored` on an asset, with `expectedRevision` | 409 / 404 |
| `POST /api/plan/route` | route options for an entity to `to: [lng, lat]` (road graph for land, water grid for sea, great circle with climb/cruise/descent for air; fastest and threat-avoiding variants scored on threat exposure, SMHI warnings and fuel; ground routes avoid Trafikverket incidents) | `RoutePlan`; options carry `terrain` only when Lantmäteriet is configured; 422 infeasible |
| `POST /api/plan/commit` | commit a chosen route (`path`, `speeds`, `airborne`, `label`, `expectedRevision`) | 409 / 404 / 422 |
| `POST /api/plan/{entity_id}/cancel` | drop a committed plan | |
| `GET /api/scenario/presets` · `POST /api/scenario/inject` | list / inject a synthetic scenario preset (`{preset}`) | 404 unknown preset |
| `GET /api/environment/points` · `GET /api/environment/forecast/{location}` | SMHI point forecasts for public city reference points | 404 unknown point |
| `GET /api/stream?interval` | SSE: `hello`, `tick` (kinematics every interval, 0.25–10 s), `revision` on mutation | browser reconnects after 2.5 s |

## Real public feeds

Every payload carries the feed contract from `backend/app/feeds/base.py`: `id`, `status` (vocabulary below), `source`, `licence`, `attribution`, `url`, `fetchedAt`, `stale`, `note`, `lastError`, `count`, plus the feed's own keys (usually `items`). Payloads are cached per feed TTL and never raise; failures become `partial` (last good data, `stale: true`) or `blocked`. `TROSSOPS_FEEDS=off` turns every feed into `blocked` without network calls.

| Method and path | Feed id(s) | Items |
|---|---|---|
| `GET /api/sources?probe` | all | `SourceStatus[]` (+ `ttlS`, `latencyMs`, `attribution`); `probe=true` fetches every feed first |
| `GET /api/live/aircraft` · `GET /api/live/aircraft/{hex_id}/trail` | `adsb` | `LiveAircraft`; trail is per process (404 when none) |
| `GET /api/live/gnss` | `adsb` | NIC/NACp samples, `degradedCount` |
| `GET /api/live/vessels` · `GET /api/live/vessels/{mmsi}/history` | `ais-digitraffic` (+ `aisstream` when keyed) | `LiveVessel`; `streams.aisstream` reports the stream status |
| `GET /api/env/observations` | `smhi-obs` | station observations, latest hour |
| `GET /api/env/warnings` | `smhi-warnings` | impact-based warnings with geometry |
| `GET /api/env/grid` | `open-meteo` | wind / visibility / cloud grid (`points`, `lngStep`, `latStep`) |
| `GET /api/env/radar` | `rainviewer` | radar `frames`, `nowcast`, tile size |
| `GET /api/env/space` | `swpc-kp` | Kp index, 24 h series, storm scale |
| `GET /api/env/fires` | `firms` | `FireDetection` (VIIRS, last 24 h); `adapter-only` without `FIRMS_MAP_KEY` |
| `GET /api/civil/police` | `polisen` | police events (municipality-level positions) |
| `GET /api/civil/crisis` | `krisinformation` | news and VMA public warnings |
| `GET /api/civil/traffic` | `trafikverket` | `TrafficIncident`; `adapter-only` without `TRAFIKVERKET_API_KEY` |

## Terrain (Lantmäteriet Markhöjd Direkt, `lm-markhojd`)

| Method and path | Response | Errors |
|---|---|---|
| `GET /api/terrain/elevation?at=lng,lat` | `TerrainElevation` `{lng, lat, groundM, datum: "RH 2000", source}` | 422 malformed or outside Sweden; 503 not configured; 502 upstream |
| `GET /api/terrain/los?a=lng,lat&b=lng,lat&ha&hb` | `LineOfSight`: `visible`, `minClearanceM`, `obstruction`, sampled `profile` with clearance; bare earth (no trees or buildings), earth curvature with refraction | same; `ha`/`hb` 0–20 000 m above ground |

503 means credentials are absent (`LANTMATERIET_USERNAME`/`PASSWORD`, or `CLIENT_ID`/`CLIENT_SECRET`, or `TOKEN`) or feeds are disabled: the API never invents elevation.

## Status vocabulary

`working`, `partial`, `simulated`, `adapter-only`, `planned`, `blocked` (`FeedStatus` in TS). Errors are JSON `{detail}`: 404 unknown id, 409 revision conflict, 422 validation, 502 upstream failure, 503 integration not configured. CORS is limited to the local dev/preview origins.
