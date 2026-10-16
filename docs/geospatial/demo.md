# Demo script (five minutes, no AI)

Start the API with the scenario already ten minutes in so the picture is populated, then the UI:

```powershell
cd backend
$env:TROSSOPS_START_S = "600"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm run dev
```

Open http://127.0.0.1:5173 as **National commander · Readiness**.

| Time | What to show | What is really happening |
|---|---|---|
| 0:00 | Sweden as one picture: clusters with counts, attention heat, KPIs. Hover a cluster, click it to open the Stockholm region. | MapLibre clustering of the live snapshot; attention cells from the rule engine at national resolution |
| 0:40 | Switch to **Threat**. Unknown tracks (hollow orchid) with dashed predicted paths and uncertainty wedges. Click `Unknown sea track S1`. | R01: dead reckoning, closest approach to own sites, intervention options ranked by intercept time and success |
| 1:20 | Open **Decisions** (D). Read the options: success, time to effect, best/expected/worst. Press **Optimise the plan**; compare the Hungarian plan with nearest-first and highest-success. Commit one option. | `/api/strategy/optimize`; commit is revision-checked and persisted; the intervention line turns solid |
| 2:10 | Press **R**, submit a field report as a soldier: "Unknown drone over depot-mitt perimeter". The revision increments, the report appears in the feed, the depot gains attention. | Rule-based parsing (severity, entity id, tags), re-evaluation, SSE revision event |
| 2:50 | Layers (L): turn on **Attention surface** 3D and press **3**. Columns rise where the rules concentrate. Click a column to read why. | fill-extrusion of cells; reasons and contributors per cell |
| 3:30 | Search (/) `Tank platoon 01`, press **F** to follow, zoom in to 16: the sprite becomes a 3D model, heading preserved, terrain and buildings in 3D. Record a fault, then a repair, from the inspector. | sprite → model handoff at zoom 13; events through `/api/events` |
| 4:20 | Drag the time slider back ten minutes: the picture as it was, labelled Replay. Return to live. | `at=` evaluation of the same engine |
| 4:45 | Switch role to **Regional commander South**: scope, modes and camera change. End on **Civil functions** with the 112 incident and grid outage. | role-scoped snapshot; R05/R06 |

Everything on screen is synthetic and labelled; public datasets (SCB, SMHI) are the only real data.
