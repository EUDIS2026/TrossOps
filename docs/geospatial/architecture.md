# Architecture (v2)

```
 scripts/data ──► backend/data/geo (road graph, city streets, sea mask)          real public feeds (backend/app/feeds)
                         │                                                    adsb.lol · OpenSky · Digitraffic AIS · SMHI
 orbat.py (order of battle) + sitegen.py (site layouts) + motion.py           Open-Meteo · RainViewer · Polisen · Krisinfo
                         │                                                    NOAA SWPC · (AISStream, Trafikverket: key)
                  world.py (evaluate any t)                                          │
                         │            scripted inputs · operator reports · injections · feed_inputs.py
                         ▼                                    │
              rules.py (R01–R18) ──► fusion.py · deception.py · predict.py (hypotheses) · optimize.py
                         │
        engine.py: catalog (motion, routes, sites)  ·  snapshot (status, alerts, interventions, predictions,
                   fusion, deception)  ·  observed tracks  ·  planner.py (routes on roads / water / air)
                         │
     FastAPI: /api/world · /api/scene/snapshot · /api/stream (SSE) · /api/sites/{id}/layout · /api/plan/*
              /api/scenario/inject · /api/live/* · /api/env/* · /api/civil/* · /api/sources
                         │
 Session (clock, buffer, polling) ─► WorldModel (motion.ts per frame, aggregation, budgeted cut)
                         │
 SceneController: MapLibre style · overlays · sprite layer (APP-6, RTC) · models3d (three.js) · H3 surfaces
                  · site detail · real traffic · weather · cinematic camera · declutter · picking
```

## Payloads

| Endpoint | Changes when | Size (gzip) |
|---|---|---|
| `/api/world` | a plan is committed or an injection spawns tracks (`catalogRevision`) | ~260 kB |
| `/api/scene/snapshot` | every evaluation (2 s grid) | ~35 kB |
| `/api/stream` | SSE `tick` 1 Hz (observed tracks only) and `revision` | < 1 kB per tick |

## Time

- Scenario time `t` advances at `speed` × wall clock from the epoch (`TROSSOPS_EPOCH=hourly` on Vercel).
- The browser clock (`core/clock.ts`) is live or simulated at ×1–×300, into the past or up to +3 h. Motion is
  evaluated locally at that `t`; the evaluated picture is fetched on a 10 s scenario grid. Real feeds show only live.

## Zoom semantics

| Zoom | You see | Mechanism |
|---|---|---|
| national | brigades, air wings, flotillas, Home Guard battalions, sites, unknown tracks | budgeted cut by spread, declutter + leader lines |
| regional | battalions and companies; convoys open into vehicles as they string out | same cut, budget grows with zoom |
| local (≥ 11) | single platforms with heading arrows; site layouts load | instanced sprites; `/api/sites/{id}/layout` |
| street (3D) | procedural 3D models with attitude, shelters, hangars, fuel tanks by fill level | three.js custom layer, fill-extrusion |

Analysis surfaces (H3) are national and regional tools and fade out by zoom 11.

## Provenance

Every entity and input carries `sourceKind`. Unknown tracks never expose their simulated route. Real feeds are marked
`real` in the layer tree and in the inspector; synthetic content is stated in the data notice and in Sources.
