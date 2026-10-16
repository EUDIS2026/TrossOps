# API contracts

Base: `http://127.0.0.1:8000`. All responses carry `worldRevision`; reads accept `at` (scenario seconds) for replay. Types are mirrored in `frontend/src/contracts/types.ts`; the Pydantic models in `backend/app/models.py` are the authority.

| Method and path | Purpose | Notes |
|---|---|---|
| `GET /api/health` | status, clock, rule and entity counts | `mode: synthetic` |
| `GET /api/clock` | epoch, `nowS`, speed, revision | |
| `GET /api/views` | roles → modes → layers, rule catalogue, channels, region scope | drives the whole UI |
| `GET /api/scene/snapshot?at&role` | entities, areas (with status), alerts, interventions, predictions, last 80 inputs, events, KPIs, layer attention, rule trace, priorities | role scopes entities server-side |
| `GET /api/scene/entities?at` | compact kinematics rows `[id, lng, lat, altM, headingDeg, speedMps, condition]` | what the stream ticks carry |
| `GET /api/scene/tracks/{id}?from&to&step` | reconstructed samples `[lng, lat, altM, tS]` | `to` is clamped to now |
| `GET /api/scene/attention?at&resolution&role` | cells (score, peak, reasons, contributors) and raw contributions | resolution `national` 0.5°, `regional` 0.15°, `local` 0.04° |
| `GET /api/scene/predictions?at` | dead-reckoned paths with uncertainty rings | |
| `GET /api/entities/{id}?at` | entity, related inputs, alerts, interventions, predictions, areas, events, rule trace | inspector detail |
| `GET /api/inputs?at&channel` · `POST /api/inputs` | list / submit a report | submission is parsed by rules (severity, entity ids, places, tags), increments the revision |
| `GET /api/alerts?at` · `POST /api/alerts/{id}/ack` | alerts / acknowledge | acknowledgement is persisted and clears layer dots |
| `GET /api/interventions?at` · `POST /api/interventions/{id}/commit` · `POST …/abort` | proposals / commit an option (409 on stale `expectedRevision`) / abort | progress and monitoring are re-evaluated on every read |
| `POST /api/strategy/optimize?at` | Hungarian assignment plus alternatives | |
| `POST /api/events` | `fault`, `repair`, `resupply`, `comms_loss`, `comms_restored` on an asset, with `expectedRevision` | 409 on revision mismatch |
| `GET /api/environment/points` · `GET /api/environment/forecast/{location}` | SMHI public forecasts | `connected` or `unavailable` with reason |
| `GET /api/stream?interval` | SSE: `hello`, `tick` (kinematics every interval), `revision` on mutation | the browser reconnects automatically |

Errors are JSON `{detail}`; 404 for unknown ids, 409 for revision conflicts. CORS is limited to the local dev/preview origins.
