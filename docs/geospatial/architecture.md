# Architecture

```
inputs (14 channels)      synthetic world (114 entities, waypoint motion)
        │                            │
        └────────► rule engine (14 rules, deterministic) ◄── persisted mutations (events, commits, acks)
                     │  attention contributions · alerts · interventions (options, outcome bands)
                     │  predictions (dead reckoning + uncertainty) · area status · priorities · traces
                     ▼
         evaluation cache keyed by (scenario second, world revision)
                     │
   ┌─────────────────┼──────────────────────────────────────────────┐
   │ /api/scene/snapshot?at&role   /api/scene/attention?resolution  │ FastAPI
   │ /api/scene/entities (compact) /api/scene/tracks/{id}            │
   │ /api/entities/{id} (detail + trace) /api/strategy/optimize      │
   │ /api/stream  (SSE: tick 1 Hz, revision)                         │
   └─────────────────┬──────────────────────────────────────────────┘
                     ▼
   Session (snapshot, detail, commands)  ──►  store (role, mode, layers, selection, time)
   EntityBuffer (sample ring, interpolation, bounded extrapolation, stale)
                     ▼
   SceneController: MapLibre sources/layers · sprite layer (display rate) · model layer (3D) · camera intents
```

## Authority and provenance

- The API is the only source of truth. The browser never computes a status it then displays as fact; it interpolates positions between server samples and labels extrapolation beyond 3 s as stale.
- Every entity carries `sourceKind` (`simulated`, `observed`, `predicted`, `planned`, `public`) and the UI renders them differently: unknown tracks are hollow orchid diamonds, predictions are dashed with an uncertainty wedge, plans are dotted, public datasets are labelled.
- Unknown tracks never expose the simulator's route; the operator sees observed samples and the engine's prediction only.

## Time

- Scenario time `t` (seconds since epoch) advances at `speed` × wall clock. `at=` on any read evaluates the past; `/api/stream` ticks carry `atS`.
- `renderTime = lastTick.atS + elapsed − 1 s buffer`; poses are interpolated between the two bracketing samples with heading wrap, dead-reckoned up to 3 s, then frozen and marked stale.
- Replay sets a fixed `t`; the picture (entities, alerts, interventions, attention) is re-evaluated as of that second. Mutations are disabled in replay.

## Views

`/api/views` declares roles → modes → layers, camera presets and KPIs. Regional roles are scoped server-side. Operator layer switches override mode defaults until the mode changes. Layer attention dots come from unacknowledged alerts whose `layerIds` touch the layer.

## Zoom semantics

| Zoom | What you see | Mechanism |
|---|---|---|
| < 8 | Activity clusters (count, worst condition colour), sites inside clusters, attention heatmap | MapLibre clustering, `clusterProperties` |
| 8.3 – 13 | Heading-aware unit sprites, site glyphs, labels with collision, halos | sprite layer + symbol layers |
| ≥ 13 (3D on) | Metre-scaled 3D models, attention columns, buildings, terrain | custom 3D layer, fill-extrusion, raster-dem |
| any | Trails (20 min), predictions, plans, areas, incidents, intervention lines | GeoJSON sources |

Attention resolution follows zoom: national 0.5°, regional 0.15°, local 0.04° cells; cells are clickable and explain their score.
