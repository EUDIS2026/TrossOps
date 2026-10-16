# Integration matrix

Status vocabulary: `working` (tested end to end), `partial`, `simulated` (internally generated, labelled), `adapter-only`, `planned`, `blocked`.

| Capability | Status | Evidence / next step |
|---|---|---|
| Synthetic national world (114 entities, nine kinds, motion model) | simulated | `backend/tests/test_world.py`; every entity carries `sourceKind` |
| Input channels (14) with scripted live timeline and operator submission | working (simulated content) | `test_inputs.py`, E2E-06 |
| Rule engine: attention, alerts, interventions, outcome bands, area coverage, priorities, monitoring | working | `test_rules.py`, `docs/geospatial/rules.md` |
| Trajectory prediction with uncertainty, intercept geometry | working (declared model) | `predict.py`, E2E-02 |
| Strategy optimiser (Hungarian) with alternatives | working | `test_engine_api.py::test_optimiser_never_double_books`, E2E-07 |
| Revision-checked commands, SQLite persistence, replay | working | `test_engine_api.py`, E2E-08 |
| SSE live stream with reconnect | working | `api.ts`, E2E-01 (status chip `Live`) |
| Role → mode → layer views, server-side regional scope | working | `views.py`, E2E-10 |
| Layer attention dots | working | `layerAttention` in snapshot, rail |
| Clusters by level → sprites → 3D models | working | E2E-04, E2E-05 |
| Attention heatmap (2D) and columns (3D), clickable cells | working | E2E-09 |
| Dark basemap (OpenFreeMap), terrain (Mapterhorn), 3D buildings | working online; verified on the owner's machine (verification.md) | public services, no SLA |
| Imagery (EOX Sentinel-2 cloudless) | working online, non-commercial licence | attribution shown |
| Offline geography | working | E2E runs in the restricted workspace |
| SMHI forecasts | adapter-only until a live call succeeds on a networked host; `unavailable` otherwise | `weather.py`; never feeds rules as observations |
| Cesium immersive mode | planned (seam: `SceneSelection` in store, `CustomLayerInterface` already carries entity poses) | ADR-001 |
| Real telemetry, ERP, OGC feeds, NATS/SpacetimeDB | planned | contracts in `models.py`; adapters must declare `sourceKind` and status |
| AI layers (summaries, triage) | planned by design, excluded from the demo path | every rule output is traceable without them |
