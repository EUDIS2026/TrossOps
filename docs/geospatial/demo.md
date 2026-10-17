# Demo script (five minutes, no AI)

Start the API ten scenario-minutes in so the picture is populated, then the UI. The hosted build (Vercel) is
equivalent; feeds without keys there show `adapter-only`.

```powershell
cd backend; $env:TROSSOPS_START_S = "600"; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend; npm run dev        # open http://127.0.0.1:5173
```

Opening line: *"One map of Sweden. Every unit, site and report you see is synthetic; everything marked `real` is a
live public feed. There is no AI in this path: every conclusion is a named rule you can open."*

| Time | Do | Say (what is really happening) |
|---|---|---|
| 0:00 | National commander · Overview. Zoom from the national view into Skåne until a company opens into vehicles on its road. | Formations collapse into one APP-6 symbol and open by echelon inside a symbol budget; vehicles drive the OSM road graph, and every site stands on dry land off the roads. |
| 0:45 | Switch mode to **Threat**. Click the track **Tanker NORDIC STAR (AIS)**. Open **Why**, **Prediction**, **Deception**. | Admiralty-graded sources and corroboration; competing trajectory hypotheses with probabilities; deception indicators with log-odds weights and what would change the assessment (rule R01 and the deception model). |
| 1:30 | Press **D** (Decisions), **Optimise all**, then commit one option. | Hungarian assignment with no unit double-booked, compared with nearest-first and highest-success; the commit is revision-checked and persisted. |
| 2:00 | Press **S** (Simulate), inject **Drone swarm over Airbase Norr**. Open the new alert. | Synthetic UAS tracks appear; rule R16 raises a counter-UAS alert and intervention within one evaluation (2 s scenario grid). |
| 2:40 | Select **Corvette 4 Flot-3** (search `/`), Actions → **Plan a route…**, click open water east of Öland, compare options, **Execute**. | Routes on the sea grid with ETA, fuel and threat/weather exposure; with Lantmäteriet configured each option also carries a terrain profile. The ship then sails the plan. |
| 3:20 | Layers (**L**) → Analysis surface **Threat reach**, then press **3**. | H3 surface: minutes until an unknown track could reach each cell; in 3D the columns rise; click a cell for its reasons. |
| 3:50 | Role **Air operations** → **Air picture**. Hover live aircraft; open **I** (Data sources). | Real ADS-B traffic next to synthetic forces, each labelled; every feed's status is from the fixed vocabulary, keyed feeds without a key say `adapter-only`, nothing is mocked. |
| 4:30 | Role **Police & emergency services** → Patrol picture (Stockholm). Then Simulate ×60 for a few seconds, then **Live**. | Synthetic patrol cars on the real street graph with real police events and road incidents; simulation and replay run the same deterministic engine at any time. |

Close: *"Everything you saw is a rule with a trace, a declared model or a labelled public feed."*

Fallbacks: offline, set `TROSSOPS_FEEDS=off` (live layers empty, Sources shows `blocked`) and pick the Offline
basemap from the dock. If a step misbehaves, `npm run verify` reproduces each of these flows headlessly.
