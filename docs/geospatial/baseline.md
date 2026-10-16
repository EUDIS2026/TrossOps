# Baseline

16 October 2026. This repository started empty by the owner's decision; an earlier experiment in another folder was not reused. GitHub `EUDIS2026/TrossOps` had no commits when work began.

## What exists after this increment

- `backend/`: FastAPI 0.143 service, synthetic national world, rule engine, optimiser, SSE stream, SQLite-persisted mutations. 23 pytest cases.
- `frontend/`: Vite 7 + React 19 + TypeScript 5.9 workstation on MapLibre GL JS 6.14 with two custom WebGL layers. Type-checked; 11-step Playwright acceptance script.
- `docs/`: vision, brief, ADR-001, architecture, rules, styles, API contracts, verification ledger, integration matrix, demo script.

## Environment notes

- Built and verified first in a network-restricted workspace (no npm or PyPI access): the frontend was bundled with esbuild and exercised in headless Chromium with software GL against the live API; online basemaps could not load there, so the offline geography was what those screenshots show. The same acceptance script runs on the owner's Windows machine with the real basemaps (see verification.md for both ledgers).
- Pinned versions: see `backend/requirements.txt` and `frontend/package.json`.

## Known limits

- Basemap and imagery providers are public services without SLA; the app falls back to offline geography when the style cannot load.
- Trajectory prediction is straight-line dead reckoning with a declared uncertainty model; it is not a route prediction.
- Intervention success figures are declared synthetic planning formulas (documented in rules.md), not calibrated probabilities.
- No Cesium immersive mode in this increment (ADR-001); the seam is documented in the integration matrix.
