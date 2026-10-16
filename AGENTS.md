# TrossOps — working agreement

TrossOps is a national-level operational picture for Sweden: one map, role-based views, mode-based maps, separable layers, a deterministic rule engine over every input channel, and no AI in the demo path.

- Specification: `docs/briefs/TROSSOPS_GEOSPATIAL_MASTER_IMPLEMENTATION_PROMPT.md` plus `docs/product/vision.md`.
- Architecture decisions live in `docs/decisions/`. Read ADR-001 before touching the renderer.
- Status vocabulary everywhere (docs, UI, API): `working`, `partial`, `simulated`, `adapter-only`, `planned`, `blocked`. Never present a mock as an integration.
- All operational entities, sites, routes and reports are **synthetic**. Public datasets (SCB counties, SMHI forecasts) are labelled as such. No real military locations or identities.
- Stack: Python 3.12+ / FastAPI backend, React 19 + TypeScript + Vite frontend, MapLibre GL JS 6 (native layers + custom WebGL layer). Pin versions.
- Git: many small conventional commits (`feat`, `fix`, `test`, `perf`, `docs`, `chore`). Never force-push `main`.
- Keep the app running at every commit: `backend` pytest green, `frontend` typecheck green, browser smoke passing.
