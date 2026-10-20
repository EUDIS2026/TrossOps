# Architecture (v2)

```
 scripts/data/build_geonet.py ─► backend/data/geo: national.json.gz (roads) · city_*.json.gz (streets)
                                                   sea.bin (sea mask + routing grid) · land.bin + roads.bin (placement masks)
                         │                                       real public feeds (backend/app/feeds, TTL-cached)
 orbat.py (order of battle, placement) + sitegen.py (layouts)    adsb.lol/OpenSky · Digitraffic/AISStream · SMHI
   + motion.py (declared motion)                                 Open-Meteo · RainViewer · Polisen · Krisinformation
                         │                                       SWPC · Trafikverket · FIRMS · Lantmäteriet Markhöjd
                  world.py (evaluate any t)                                         │
                         │      scripted inputs · operator reports · injections · feed_inputs.py
                         ▼                                  │
              rules.py (19 rules) ─► fusion.py · deception.py · predict.py · optimize.py
                         │
        engine.py: catalog (motion, routes, sites) · snapshot (status, alerts, interventions, predictions,
                   fusion, deception) · observed tracks · planner.py (roads / water / air, + terrain)
                         │
     FastAPI main.py: /api/world · /api/scene/* · /api/stream (SSE) · /api/sites/{id}/layout · /api/plan/*
                      /api/scenario/* · /api/entities/* · /api/inputs · /api/alerts · /api/interventions
     routes_live.py:  /api/sources · /api/live/* · /api/env/* · /api/civil/* · /api/terrain/*
                         │
 Session (clock, entity buffer, polling) ─► WorldModel (motion.ts per frame, aggregation, budgeted cut)
                         │
 SceneController: MapLibre style · overlays · sprite layer (APP-6) · models3d (three.js custom layer) · H3 surfaces
                  · site detail · real traffic · wind · cinematic camera · declutter · picking · repaint pacing
```

Full route list and payload types: [api-contracts.md](api-contracts.md).

## Payloads

| Endpoint | Changes when | Size (gzip) |
|---|---|---|
| `/api/world` | a plan is committed or an injection spawns tracks (`catalogRevision`) | ~260 kB |
| `/api/scene/snapshot` | every evaluation (2 s scenario grid) | ~35 kB |
| `/api/stream` | SSE `tick` 1 Hz (observed tracks only) and `revision` | < 1 kB per tick |

## Time

- Scenario time `t` advances at `speed` × wall clock from the epoch (`TROSSOPS_EPOCH=hourly` on Vercel). Rules are
  evaluated on a 2 s scenario grid; motion is continuous.
- The browser clock (`core/clock.ts`) is live or simulated (×1, ×10, ×60, ×300), into the past or ahead. Motion is
  evaluated locally at that `t`; the picture is refetched every 6 s live and every 10 scenario seconds while
  simulating. Real feeds describe only the present and are shown only live.

## Ground truth for placement (land/water mask)

`backend/data/geo/land.bin` is a ~110 m land/water raster over Sweden built from every OpenStreetMap water polygon
(sea, lakes, rivers, ponds, docks; OpenFreeMap z11 tiles) by `scripts/data/build_geonet.py`; outside the fetched tiles
it falls back to the sea mask in `sea.bin`. `roads.bin` adds a mask of every road class (incl. minor roads, z12)
around sites and parked units. `geonet.LandMask` answers `is_water`, `nearest_dry`, `leg_dry` and
rasterises road networks into cells. The world uses it as follows (`orbat.py`):

- **Sites** (`_place_site`): the declared position (town + offset) is only a seed. Built surfaces (runways, taxiways,
  aprons, shelters, buildings) must be clear of every road in `roads.bin`, and the fenced footprint must avoid water
  and national roads; naval bases also need their berths in water and a channel in navigable sea. The
  nearest fitting position is searched (axis turned if needed), preferring ground free of every road, then free of
  graph roads, then merely dry. Placements are cached in `world_routes.json.gz`; an airbase's cache key carries
  `sitegen.AIRBASE_LAYOUT`, so bumping it after changing the airbase's built surfaces re-places only the airbases.
- **Airbase layout** (`sitegen.airbase`): a local frame with u along the runway and v to its right. Airside
  (parallel taxiway A, apron, maintenance, dispersal loops) is on +v; the QRA compound, navaids, helipads, the reserve
  road strip and the weapons storage area are on −v; the cantonment is by the main gate at −u. The taxiways form a
  `TaxiNet` graph. `taxi_out` and `taxi_in` are shortest paths on it (runway edges cost ×6, so back-taxiing is a last
  resort), and every parking spot carries its graph node.
- **Parked and dispersed ground units** (`on_ground`, `in_field`): snapped to the nearest dry, road-free point.
  Columns and patrol loops stay on the road network; ground paths cross water only on roads (bridges, ferries).
- **Ships** (`at_sea`): harbour positions need sea with ~150 m of water around them; ships leave through their base's
  channel and unknown sea tracks follow the sea grid.

Placements are cached in `world_routes.json.gz`, so the world is identical across processes. `test_ground.py` pins
all of this (nothing on water, no sites on roads, ships at sea, no router leg across water).

## Terrain (Lantmäteriet Markhöjd Direkt)

`feeds/markhojd.py` queries ground elevation (RH 2000) from the national elevation model, converting WGS84 to
SWEREF 99 TM and batching vertices; results are LRU-cached in process. It serves four things, all only when
credentials are set (otherwise the feed is `adapter-only` and the endpoints return 503; nothing is invented):

- `planner.annotate_terrain`: ground profile and total climb for land and sea options; minimum terrain clearance for
  air options, with a risk penalty and a note below 150 m.
- `GET /api/terrain/elevation?at=lng,lat`: one point.
- `GET /api/terrain/profile?path=…`: ground sampled along a polyline (the measure tool).
- `GET /api/terrain/los?a&b&ha&hb`: bare-earth line of sight with earth curvature and refraction (no trees or
  buildings), returning the obstruction point and the clearance profile.

The 3D basemap terrain in the browser is separate (Mapterhorn DEM tiles).

## Zoom semantics

| Zoom | You see | Mechanism |
|---|---|---|
| national | brigades, air wings, flotillas, Home Guard battalions, sites, unknown tracks | budgeted cut by spread, declutter + leader lines |
| regional | battalions and companies; convoys open into vehicles as they string out | same cut, budget grows with zoom |
| local (≥ 11) | single platforms with heading arrows; site layouts load | instanced sprites; `/api/sites/{id}/layout` |
| street (3D) | procedural 3D models with attitude, shelters, hangars, fuel tanks by fill level | three.js custom layer, fill-extrusion |

Analysis surfaces (H3) are national and regional tools and fade out by zoom 11.

## Rendering loop and repaint scheduling

`SceneController` runs one `requestAnimationFrame` loop: it advances the clock, evaluates motion for visible nodes,
updates the sprite and model layers, and throttles slower work (labels every 250 ms; analysis surface, environment
and trails every 1.5 s). MapLibre redraws the whole map on every repaint, so the controller does not repaint every
frame: `schedulePaint` requests one only when something visibly changed (a sprite moved at least 0.35 px, 3D models
or wind particles report `wantsFrame()`), paced by a moving average of frame cost: at most 60 Hz while frames are
cheap, 30 Hz once they are expensive. Camera movement and tile loads repaint on their own. Static 3D site props sit
in cached instance buffers and labels are re-sent only when they change on screen.

## Provenance

Every entity and input carries `sourceKind`. Unknown tracks never expose their simulated route. Real feeds are marked
`real` in the layer tree and in the inspector; synthetic content is stated in the data notice and in Sources.
