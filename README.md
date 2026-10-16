# TrossOps

National-level operational picture for Sweden: one map, role-based views, mode-based maps, separable 2D/3D layers, and a deterministic rule engine that turns every input channel into attention, alerts, interventions and predictions. No AI in the demo path.

All operational content is **synthetic**. Public datasets (SCB county boundaries, SMHI forecasts) are labelled as public.

Specification: [`docs/product/vision.md`](docs/product/vision.md) and [`docs/briefs/`](docs/briefs/). Decisions: [`docs/decisions/`](docs/decisions/).

## Run

Backend (Python 3.12+):

```powershell
python -m pip install -r backend\requirements.txt
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend (Node 20+):

```powershell
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173.

## Check

```powershell
cd backend; python -m pytest -q
cd ..\frontend; npm run typecheck; npm run build
```
