# Verification ledger

Status words: `pass`, `fail`, `blocked`, `not-run`. Evidence lives next to this file.

## Run C — v2 on the owner's Windows machine (Edge 141 headless, hardware GPU, online), 17 October 2026

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend; python -m pytest -q` | **pass** — 81 passed (motion fixture, world, rules R01–R18, fusion, deception, planner, scenario, geonet, feeds offline) |
| Frontend type check | `npm run typecheck` | **pass** |
| Frontend unit tests | `npm test` | **pass** — 63 (motion twin vs Python fixture, entity buffer, 56 model checks) |
| Production build | `npm run build` | **pass** — vendor chunks: maplibre 283 kB, milsymbol 197 kB, three 140 kB, h3 64 kB, app 131 kB (gzip) |
| Browser acceptance E2E-01 … E2E-12 | `BROWSER_CHANNEL=msedge node scripts/verify-browser.mjs` | **pass** — 12/12, ledger `screens/v2/results.json` |
| Frame rate, all layers on, 942 symbols + 1,014 real ships | probe in headless Edge | 36 fps mean, 50 ms worst frame |

Steps: live picture · echelon budget and zoom-to-vehicle · vehicles on rendered roads · cinematic airbase with layout ·
3D models · fusion/prediction/deception tabs · all analysis surfaces · route planning and execution · simulation clock ·
injected drone swarm raises R16 · source status vocabulary · police role in Stockholm.

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

## Run B — owner's Windows machine (Playwright Chromium, hardware GPU, online), 16 October 2026

Setup (`scripts\setup-windows.cmd`): pip install ok; `npm install` 132 packages; `tsc` clean; vitest 4 passed; `vite build` ok (1.33 MB JS); Playwright Chromium installed.

### B1 — first run (history up to `e51b48d`, before the worker fix)

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend; python -m pytest -q` | **fail** — 13 passed, 10 errors: `PermissionError` creating `%TEMP%\pytest-of-<user>`; fixed by `backend/pytest.ini` (`--basetemp=.pytest_tmp`), re-run pending |
| API and UI start | `scripts\run-windows.cmd` | **pass** — `/api/health` working, 114 entities, UI 200 |
| Browser acceptance | `node scripts\verify-browser.mjs` | **fail** — 8/11. E2E-02 (no prediction geometry), E2E-09 (no attention cell), E2E-11 (console: `Worker failed to load`, HelpPanel key warning). Screenshots show an empty map. |

Root cause: MapLibre 6 resolves its web worker relative to `import.meta.url`; under Vite that URL points into `.vite/deps`, where no worker file exists, so every GeoJSON and vector source failed to load. The error message also matched the basemap fallback regex, which switched the map to offline geography. The restricted-workspace bundle copied the worker next to the bundle by hand, which masked the defect. Fix: `setWorkerUrl` with the worker imported as a Vite asset (`?url`) in `scene/controller.ts`; fallback regex now ignores worker errors; HelpPanel rows keyed with `Fragment`.

### B2 — after the worker fix (history up to `4943fd3`), 21:50 local

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend; python -m pytest -q` | **pass** — 23 passed (pytest.ini basetemp fix confirmed) |
| API and UI start | `scripts\run-windows.cmd` | **pass** — health working, 114 entities, UI 200 |
| Browser acceptance online | `node scripts\verify-browser.mjs` | **pass** — 11/11; attribution shows `OpenFreeMap © OpenMapTiles`; 14 predictions; `errors: 0`. Screenshots in `_logs\verify\` on the machine. |
| Push | `git push -u origin main` | **pass** — `main` on github.com/EUDIS2026/TrossOps at `4943fd3` |
| Dark basemap, terrain, 3D buildings | manual, built-in browser at 127.0.0.1:5173 | **pass** — OpenFreeMap dark style, Mapterhorn terrain (`getTerrain()` set, hillshade visible), `buildings-3d` visible at zoom 15.5 / pitch 60 |
| SMHI point forecast | `/api/environment/forecast/stockholm` | **fail → fixed** — live SNOW1G returned `unavailable: KeyError 'validTime'`: the real schema is `timeSeries[].time` + flat `data{}`; parser rewritten against the live payload (tests in `test_weather.py`), and the Weather layer now fetches and labels the seven reference cities. Re-check in B3. |

### B3 — after the SMHI fix

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` | not-run |
| Browser acceptance online | `node scripts\verify-browser.mjs` | not-run |
| SMHI `connected`; Weather layer labels | manual | not-run |

## Known limits observed

- Under software GL the symbol source's 2 Hz refresh keeps tiles in `reloading` for noticeable periods; picking therefore retries once after 160 ms. On a hardware GPU reloads are near-instant.
- Labels are baked images: crisp at 2× but not vector-hinted; this is the price of identical offline/online typography.
