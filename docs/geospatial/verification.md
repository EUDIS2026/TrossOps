# Verification ledger

Status words: `pass`, `fail`, `blocked`, `not-run`. Evidence lives next to this file.

## Run A — restricted workspace (Linux, headless Chromium 1194 with SwiftShader software GL, 1440 × 900), 16 October 2026

Network: no npm, PyPI or tile access. Frontend bundled with esbuild from the same sources; API started with `TROSSOPS_START_S=600`.

| Check | Command | Result |
|---|---|---|
| Backend unit and API tests | `cd backend; python -m pytest -q` | **pass** — 23 passed |
| Frontend type check | `cd frontend; npm run typecheck` (tsc 6.0 in the workspace, 5.9 pinned) | **pass** |
| Browser acceptance E2E-01 … E2E-11 | `node scripts/verify-browser.mjs` (`SOFTWARE_GL=1`) | **pass** — 11/11, twice in a row against one persisted store; ledger `screens/results-container.json`, screenshots `screens/*.png` |
| Frontend unit tests (vitest) | `npm test` | **not-run** here (vitest unavailable offline) — see Run B |
| Online basemaps, terrain, imagery, 3D buildings, SMHI | — | **blocked** here (no network); offline geography exercised instead — see Run B |

Acceptance steps: load useful scene with KPIs, layers and moving units · Threat mode shows predictions · select an unknown track by search with `observed` provenance · regional LOD and exact picking at zoom 11 · 3D model layer and follow at zoom 16 · submit a field report, revision increments, feed shows it · optimise and commit an intervention, progress shown · replay and return to live · attention cell explains itself · regional role scopes entities, civil mode changes layers · no page errors.

## Run B — owner's Windows machine (Edge / Chromium, real GPU, online)

Fill in after running the same commands there:

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend; python -m pytest -q` | not-run |
| Install, type check, build | `cd frontend; npm install; npm run typecheck; npm run build` | not-run |
| Frontend unit tests | `npm test` | not-run |
| Browser acceptance online | `npm run verify` | not-run |
| Dark basemap, terrain, imagery, buildings render; SMHI `connected` | manual | not-run |

## Known limits observed

- Under software GL the symbol source's 2 Hz refresh keeps tiles in `reloading` for noticeable periods; picking therefore retries once after 160 ms. On a hardware GPU reloads are near-instant.
- Labels are baked images: crisp at 2× but not vector-hinted; this is the price of identical offline/online typography.
