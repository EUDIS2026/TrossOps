# ADR-002: National picture v2 — client-evaluated motion, echelon aggregation, NATO symbology, real feeds

Status: accepted, 17 October 2026. Amends ADR-001 (renderer stays MapLibre-native plus custom layers).

## Context

The owner's review of v1: too many switches and panels, too little of the operational core. Units were placeholders
that did not follow roads, the heat map was a blur with no operational meaning, there was no real data, and zooming
in did not reveal more. The target is a national picture at the scale of the whole defence, readable at every zoom,
with real public feeds, explainable fusion and deception assessments, trajectory planning and simulation.

## Decisions

1. **Order of battle at representative national scale, still synthetic.** ~1,000 platforms in 262 formations
   (`backend/app/orbat.py`). Designations and sites stay fictional (AGENTS.md); platform *classes* are public
   generic types. Sites are procedurally laid out (`sitegen.py`) so an airbase can be inspected down to shelters,
   fuel tanks and ammunition storage, each feature tagged with a detail sub-layer.
2. **Real geometry for movement.** Ground units route on an OSM-derived national road graph, police and ambulances
   roam real city street graphs, ships follow a water mask (`geonet.py`, data built by `scripts/data`). Routes are
   computed once and cached in `backend/data/world_routes.json.gz` so cold starts never re-route.
3. **Motion evaluated in the browser.** The motion model (`motion.py`) has a TypeScript twin (`motion.ts`) pinned by
   a shared fixture. `/api/world` publishes declared motion once; the client evaluates ~1,000 platforms per frame at
   any scenario time, so simulation speed costs nothing and only observed tracks are streamed. Attitude (heading,
   pitch, bank) is derived from the path itself, so aircraft climb and bank and vehicles follow road curvature.
4. **Aggregation by echelon and spread, under a budget.** The client cuts the formation tree greedily: the formation
   with the widest on-screen spread (2.5 × RMS radius) opens first until either everything fits in 44 px or the symbol
   budget for the zoom is used. Colliding aggregates are decluttered with leader lines. Brigades become battalions,
   companies and finally single vehicles as they physically separate on screen.
5. **NATO APP-6 / MIL-STD-2525C symbols** via milsymbol (MIT), drawn into a GPU atlas and rendered by an instanced
   relative-to-centre sprite layer. Real public traffic uses plain silhouettes so it never competes with the order of
   battle.
6. **three.js inside a MapLibre custom layer** for 3D platforms and site props. Models are procedural (53 classes, no
   third-party assets, consistent with ADR-001). Because mercator space is left-handed, shading uses a small two-sided
   shader with true outward normals.
7. **Analysis surfaces replace the heat map.** H3 hexagons (h3-js) for six questions — fusion attention, threat reach,
   sensor/AD coverage gaps, response time, flight conditions, GNSS interference. One surface at a time; each cell
   explains its value. Surfaces fade out before street zoom.
8. **Assessment layers are deterministic.** Fusion uses Admiralty grading and combines the best source per
   independent channel; deception sums declared log-odds weights of named indicators; prediction offers competing
   hypotheses (constant velocity, goal-seeking, continued turn) with probabilities and their basis.
9. **Real public feeds are integrations, not decoration.** adsb.lol/OpenSky, Digitraffic AIS, SMHI, Open-Meteo,
   RainViewer, Polisen, Krisinformation and NOAA SWPC are live; AISStream and Trafikverket are adapter-only until a key
   is set. Real warnings, police drone reports, emergency squawks and GNSS-integrity clusters become rule inputs.
10. **Map-first shell.** One dock with one drawer at a time, a tabbed inspector, a timeline that runs ±3 h, and a
    hierarchical layer tree with role/mode presets instead of a flat list of switches.

## Consequences

- The client bundle grows (MapLibre, three.js, milsymbol, h3-js), split into cacheable vendor chunks.
- Motion semantics live in two languages; the shared fixture test fails if they diverge.
- Any change to `orbat.py` routing inputs regenerates the route cache on first build; commit the regenerated file.
- Real feeds can be empty at night or rate-limited; every feed reports `working`/`partial`/`blocked`/`adapter-only`.
