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

## Run B — owner's Windows machine (Playwright Chromium, hardware GPU, online), 16 October 2026

Setup (`scripts\setup-windows.cmd`): pip install ok; `npm install` 132 packages; `tsc` clean; vitest 4 passed; `vite build` ok (1.33 MB JS); Playwright Chromium installed.

### B1 — first run (commit `9a7f…`, before the worker fix)

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend; python -m pytest -q` | **fail** — 13 passed, 10 errors: `PermissionError` creating `%TEMP%\pytest-of-<user>`; fixed by `backend/pytest.ini` (`--basetemp=.pytest_tmp`), re-run pending |
| API and UI start | `scripts\run-windows.cmd` | **pass** — `/api/health` working, 114 entities, UI 200 |
| Browser acceptance | `node scripts\verify-browser.mjs` | **fail** — 8/11. E2E-02 (no prediction geometry), E2E-09 (no attention cell), E2E-11 (console: `Worker failed to load`, HelpPanel key warning). Screenshots show an empty map. |

Root cause: MapLibre 6 resolves its web worker relative to `import.meta.url`; under Vite that URL points into `.vite/deps`, where no worker file exists, so every GeoJSON and vector source failed to load. The error message also matched the basemap fallback regex, which switched the map to offline geography. The restricted-workspace bundle copied the worker next to the bundle by hand, which masked the defect. Fix: `setWorkerUrl` with the worker imported as a Vite asset (`?url`) in `scene/controller.ts`; fallback regex now ignores worker errors; HelpPanel rows keyed with `Fragment`.

### B2 — after the fix

Fill in from `_logs\verify.txt`, `_logs\pytest.txt`, `_logs\push.txt` after re-running `scripts\run-windows.cmd`:

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend; python -m pytest -q` | not-run |
| Browser acceptance online | `node scripts\verify-browser.mjs` | not-run |
| Dark basemap, terrain, imagery, buildings render; SMHI `connected` | manual | not-run |

## Known limits observed

- Under software GL the symbol source's 2 Hz refresh keeps tiles in `reloading` for noticeable periods; picking therefore retries once after 160 ms. On a hardware GPU reloads are near-instant.
- Labels are baked images: crisp at 2× but not vector-hinted; this is the price of identical offline/online typography.
