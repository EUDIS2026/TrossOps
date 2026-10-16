# TrossOps — Geospatial Engine Master Implementation Directive

> **Repository:** https://github.com/EUDIS2026/TrossOps.git  
> **Purpose:** Executable implementation brief for an autonomous/multi-agent coding team.  
> **Scope:** Rebuild and integrate TrossOps's operational map into a professional, fast, entity-driven geospatial workstation with optional immersive 3D, while preserving the underlying Operations / Sustainment / Intelligence system.  
> **Relationship to broader plan:** This is a specialized implementation companion to `TROSSOPS_MASTER_IMPLEMENTATION_PROMPT.md`, not a replacement for its domain, transaction, security, or analytical rules.  
> **Source-of-truth warning:** The authors of this prompt have **not inspected the repository in this session**. Technologies and APIs named here are design candidates; the implementation agent must examine the existing code, installed versions, licensing, environment, tests, and data before making changes.  
> **Status language:** Distinguish implemented, tested, partially functional, simulated, offline-only, adapter-only, blocked, and planned. Never present conceptual mockups as working integrations.

---

# 0. PRIME DIRECTIVE

You are the senior geospatial rendering, simulation-visualization, interaction design, and frontend engineering organization responsible for **TrossOps Geospatial**. Do not merely redesign a map page or replace circles with icons. Deliver a genuinely advanced, highly interactive **operational scene engine** integrated with TrossOps's authoritative state and enterprise workflows.

The desired result is a professional, geographically coherent, smooth and visually refined platform capable of presenting **air, land, maritime, infrastructure, geographic constraints, tracked entities, planned activity, operational services, and uncertain evidence** in connected 2D/2.5D/3D contexts.

A successful result looks and *behaves* like a serious operational workstation, not a map SDK example, a video-game HUD, a marker demo, or a static cinematic rendering. Every meaningful moving object and overlay is linked to typed TrossOps data. Every selection can lead to asset records, maintenance, inventory, incidents, capability dependencies, scenario comparisons, and evidence when those modules exist.

### Priority order

1. Preserve the functional application, existing code, and tested integrations. Inspect before editing.
2. Establish correct geospatial/entity semantics and one shared revision-aware scene contract.
3. Build a polished, fast and coherent primary 2D/2.5D operations map.
4. Replace generic DOM markers with efficient, recognizable, heading-aware GPU entities and intelligent LOD.
5. Implement realistic time-based entity motion, tracks, camera behavior, terrain, 3D facilities, and deep linked interactions.
6. Add operational overlays driven by genuine data or explicit synthetic models, not hand-drawn fiction.
7. Add a separate immersive Cesium-based 3D mode when it demonstrably improves the experience and the data/tiles permit it.
8. Make the scene engine reliable, measurable, responsive, locally reproducible, and accessible.
9. Extend it across Operations, Sustainment, Intelligence, replay, branching futures, multi-user collaboration, optional telemetry/video/robotics.
10. Leave precise integration-ready seams and a truthful feature/status matrix for anything unfinished.

**Ambition:** Assume an accomplished engineering team and substantial implementation latitude. Implement as many genuinely functioning features as available time/resources permit. Do not artificially reduce the vision to a minimal demo. But proceed **brick by brick**, maintaining a running, tested application and many clear Git commits. Do not let the most elaborate immersive feature delay a fully working primary map.

**Agency:** This document is a high-resolution design brief, not a mandate to use incompatible libraries. Adapt on evidence. If an alternative renderer/architecture is demonstrably superior for the repo and product requirements, choose it, write an Architecture Decision Record, preserve the contracts and acceptance criteria, and proceed. Do not ask for routine technical choices. Ask for missing credentials, legal permissions, required real-world integrations, and irreversible operations only when essential.

### Absolute prohibitions

- No generic colored circles as the *primary close-range representation* of aircraft, drones, vehicles, or vessels.
- No dozens/hundreds of independently mounted React DOM markers when GPU instancing is appropriate.
- No hardcoded map conclusions that differ from the server's analytical results.
- No animation pretending telemetry exists; simulated, estimated, observed, historical and planned positions must be distinguishable.
- No invented geographic positions, asset identities, real military locations, routes, permissions, sensor ranges, availability scores, or precision attributed to actual organizations.
- No unlicensed 3D assets, undisclosed proprietary basemap copying, or dependence on undocumented third-party services.
- No map components independently changing transactional maintenance/inventory states; commands flow through authorized backend APIs.
- No hiding broken third-party integrations behind simulated success indicators.
- No deleting substantial existing features to introduce a new rendering stack without tested replacement.
- No irreversible Git operations, broad force-pushes, or unapproved external deployments.

---

# 1. PRODUCT GOAL AND WHAT MAKES THE MAP DIFFERENT

TrossOps combines three domains:

- **Operations:** DELTA-inspired common operational picture (COP), tracks, reported events, spatial context, operating areas, incident reporting, playback and shared awareness. This is an *inspired functional implementation*, **not** a replica of or claimed connection to any government-operated DELTA system.
- **Sustainment:** PRIO/SAP-inspired ERP behavior, including asset condition, maintenance orders, facilities, warehouse parts, reservations, transfers, personnel and logistics. Again, implement representative workflows and standards-based adapters; do **not** claim access to actual PRIO.
- **Intelligence:** Capability feasibility, dependencies, operational effects, scarce resources, optimization, uncertainty, recovery alternatives, simulation and branching futures.

The scene is not only a geographic display. It is the **spatial front end to the shared operational model**.

A user selects a synthetic UAV moving over an operational sector. Its altitude-aware model and observed trajectory appear. A fault is recorded against that asset through the legitimate backend event flow. The scene updates its visual state, the linked incident/maintenance/part records become available in the inspector, affected requirements and dependencies become selectable, a recovery comparison can be run, and the map can show **hypothetical** future positions or capability coverage with explicit scenario labeling. The operator can switch to immersive 3D without losing the selected entity, scenario, or point in time.

This must feel like **one application working with one world**, not three screen recordings stitched together.

## 1.1 Visual difference versus generic competitors

Competing projects may show polished maps, live dots, maintenance tables, dashboards, or AI chat. The TrossOps demonstration should make visible the *consequences* of events and interventions:

- **Entity realism:** recognizable assets; correct heading, movement, dimensions, orientation, altitude, provenance and operational status.
- **Spatial intelligence:** selectable coverage, support influence, dependencies, service areas, constraints, and uncertainty—not only where things are.
- **Time:** historical and live modes, smooth tracks, playback, recorded-versus-effective time, planned-versus-observed distinctions.
- **Counterfactuals:** fork a scenario, apply an intervention, and compare alternate maps and outcomes using a shared starting revision.
- **Camera choreography:** operational zoom, selection fly-to, entity-follow, site inspection, altitude-aware 3D orbit, and frictionless return to overview.
- **Cross-system interaction:** open the specific maintenance work order, inventory reservation, requirement evaluation, or evidence record linked to the selected map object.
- **Demonstrable computation:** changing a source scenario event or requirement changes a calculated overlay after server-side evaluation, not a pre-authored color transition.

**Success metric:** A domain specialist should immediately recognize the geographic objects and understand why a visual change matters; an engineer should be able to trace that change to concrete data, geometry, algorithm and world revision.

---

# 2. REPOSITORY RECONNAISSANCE — FIRST ACTUAL TASK

Before writing new code:

1. Inspect repository root, current branch, uncommitted changes, recent commits, README, build scripts, Next.js routing/components, FastAPI apps, TypeScript settings, package managers, Docker, migrations, API contracts, tests and CI.
2. Identify all existing map/viewer components and dependent pages. Inventory mapping libraries and versions, tile sources, current model/entity schemas, shape and frequency of telemetry, selection state, scenario state, asset registry and any SpacetimeDB/NATS integration already working.
3. Run the current system and record reproducible baseline commands plus screenshots of the existing map. Preserve screenshots in documented QA artifacts, not committed secrets.
4. Record existing visual failures: poor map style, DOM markers, no entity types, flicker, inaccurate coordinates, broken camera, lack of terrain/LOD, insufficient performance, missing inspector, inconsistent scenario state, SSR issues.
5. Locate the previous master implementation brief, `AGENTS.md`, architectural decisions, and known unfinished integrations. Use them rather than duplicating conflicting core models.
6. Check existing 3D assets and their licensing; identify available synthetic scenarios and whether real coordinates might be sensitive.
7. Validate current APIs and vendor compatibility from official documentation, particularly pinned versions of Next.js, MapLibre, deck.gl, CesiumJS, browser WebGL2, React, and asset loaders. Choose stable mutually compatible versions and pin them.
8. Establish a **known-good commit/tag** before invasive map changes, subject to repository ownership rules. Never erase existing work.

**Required initial deliverable:** `docs/geospatial/baseline.md` containing what exists, what works, risks, target integration surfaces, actual packages/versions, tests and an ADR explaining the selected primary and optional immersive renderers. Proceed to build after this documentation; do not stop at reconnaissance.

---

# 3. RENDERER ARCHITECTURE AND ENGINE CHOICES

## 3.1 Primary production path

Default to:

- **MapLibre GL JS** for cartography, map projection, navigation, style control and terrain-capable geographic scene.
- **deck.gl** for performant entity rendering and analytical overlays: `IconLayer`, `TextLayer`, `PathLayer`, `TripsLayer`, `GeoJsonLayer`, `PolygonLayer`, `SimpleMeshLayer`, `ScenegraphLayer`, `H3HexagonLayer`/`H3ClusterLayer`, and supported filtering/collision extensions as appropriate.
- **`@deck.gl/maplibre`** `MapLibreOverlay`; prefer an interleaved/shared-WebGL context when supported by selected versions and when correct visual layer/depth ordering is needed. Use an overlaid mode if interleaved rendering introduces unacceptable terrain/custom-layer issues. Document the compromise and confirm in-browser.
- **glTF 2.0/GLB** models, with glTF Transform-based optimization and legally sourced materials, plus clean fallback icons/silhouettes.
- **Three.js custom layer** *only* for bespoke facilities/overlays or model behavior not practically supported by deck.gl, and only after a rendering spike confirms coordinate transformations and occlusion.
- **MapLibre terrain + elevation data, vector 3D buildings, imagery, atmosphere/fog** when compatible tiles/style/resources exist; gracefully disable unavailable enhancements.
- **MapLibre-compatible PMTiles** for offline/bundled region maps where licensing and operational constraints permit.

Do not assume every renderer feature composes cleanly with every other. Verify terrain occlusion, interleaved deck ordering, building extrusions, transparent volumes, picking, custom effects, WebGL context lifecycle, clipping and browser fallback in the actual pinned stack.

## 3.2 Immersive 3D mode

Prefer **CesiumJS** as a separately mounted, lazily loaded, optionally licensed immersive 3D viewer when the 3D data makes it worthwhile:

- Terrain / ellipsoid coordinate handling; height above terrain and altitude.
- Streamed **3D Tiles** for cities/facilities, with support for compatible photogrammetry services where actually licensed and covered.
- glTF entities and altitude-aware motion/attitude.
- Orbit, follow, inspect, fly-through; geographic selections synchronized with the main COP.
- Contours, volumes, geometry overlays, trajectory playback, approved image/terrain data and modelled footprints.
- Same selected entity, scenario, time, model revision and evidence status as MapLibre.

**Do not** run two expensive independent geographic engines concurrently by default. Provide explicit mode transition; unmount/suspend the inactive viewer and clean up GPU resources/listeners. Do not pretend a MapLibre perspective extrusion is equivalent to true Cesium terrain/altitude rendering. If Cesium integration is blocked, leave a working contract, feature-flagged route and handoff; never sacrifice the primary renderer.

## 3.3 Technology selection matrix

| Concern | Preferred | Alternative / condition |
|---|---|---|
| Primary operational map | MapLibre + deck.gl | Mapbox when approved licensing, style API and cost demonstrably justify it |
| Regional basemap | Custom vector topographic + raster/satellite hybrid | Licensed commercial style or packaged offline vector tiles |
| Close-range 3D entities | deck.gl `SimpleMeshLayer` / `ScenegraphLayer` | MapLibre custom Three.js layer if special behaviors demand it |
| Detailed photorealistic world | CesiumJS + 3D Tiles + legally available terrain | Cesium ion/Google data only with proper keys, coverage and terms |
| Large geospatial aggregates | deck.gl GPU layers + H3 / PostGIS | CPU pre-aggregation for constrained devices |
| Scene UI | Existing Next.js/React | Client-only lazy map boundaries to avoid SSR failures |
| Authoritative entities | TrossOps backend/PostgreSQL | SpacetimeDB subscribed projection, explicitly non-authoritative for ERP transactions |
| Realtime delivery | Existing SpacetimeDB + NATS-derived projections | SSE/WebSocket if repo architecture requires, no duplicate live truths |
| Scenario/replay | Existing versioned backend simulation | Synthetic fixture adapter while engine is developed |
| Asset/model storage | Local/public files, object storage with manifest | Signed URLs when access control requires |
| High-performance processing | deck.gl binary typed arrays, workers, layer memoization | Native code only after profiling proves a bottleneck |

**Important:** It is acceptable to diverge when measurements and integration reality justify a better approach. Preserve the public behavior contracts.

---

# 4. SHARED GEOSPATIAL DOMAIN CONTRACT

The *map scene* is a projection of the operational model, not a second source of truth. Define shared types between backend and frontend, preferably via existing Pydantic/OpenAPI contracts and generated TypeScript clients. Adopt or extend existing types; do not introduce conflicting duplicate definitions.

## 4.1 Minimal scene entity shape

```ts
type SceneSourceKind =
  | 'observed' | 'simulated' | 'inferred' | 'predicted'
  | 'planned' | 'unknown';

type AltitudeDatum = 'WGS84_ELLIPSOID' | 'MSL' | 'AGL' | 'UNKNOWN';

type EntityKind =
  | 'fixed_wing' | 'helicopter' | 'multirotor'
  | 'ground_vehicle' | 'vessel' | 'facility'
  | 'personnel' | 'infrastructure' | 'unknown';

interface GeoPosition {
  longitudeDeg: number; // [-180, 180]
  latitudeDeg: number;  // [-90, 90]
  altitudeM?: number;
  altitudeDatum: AltitudeDatum;
  horizontalAccuracyM?: number; // only if grounded in the source/model
  verticalAccuracyM?: number;
}

interface EntityAttitude {
  headingDeg?: number;  // define frame; do not confuse bearing with yaw
  pitchDeg?: number;
  rollDeg?: number;
  quaternion?: [number, number, number, number];
  frame: 'ENU' | 'NED' | 'BODY' | 'UNKNOWN';
}

interface SceneEntity {
  id: string;
  resourceId?: string; // authoritative domain linkage
  kind: EntityKind;
  label: string;
  modelKey?: string;
  position?: GeoPosition;
  attitude?: EntityAttitude;
  observedAt?: string;
  receivedAt?: string;
  condition: 'normal' | 'degraded' | 'unavailable' | 'unknown';
  sourceKind: SceneSourceKind;
  sourceId?: string;
  stale: boolean;
  scenarioId: string;
  worldRevision: number;
  modelVersion: string;
  visualPriority?: number;
  metadataRef?: string; // resolve through authorized inspector API
}
```

The actual schema can be richer. Preserve exact data provenance and identity; include unique timestamp semantics. Do not smuggle hidden simulator truth into operator views. If altitude reference or position is unknown, show a truthful fallback—do not set `0 m` and imply a measured ground-level position.

## 4.2 Separate scene structures

Define distinct typed layers for:

1. **Assets:** resource identity, physical pose and status.
2. **Tracks:** past observed/simulated samples and freshness.
3. **Plans:** routes and *proposed* movement; visibly different from observed tracks.
4. **Sites:** bases, facilities, warehouses, communications, maintenance, ports and support infrastructure.
5. **Operational demand:** service requirements, regions, deadlines and fulfillment.
6. **Capabilities:** computed geographic service areas, feasibility and dependencies.
7. **Incidents:** reports, faults, disruptions, evidence links and timestamps.
8. **Constraints:** exclusion/permission zones, environmental conditions, restricted regions or physical limits, only when appropriately sourced/simulated.
9. **Scenarios:** branch context and overlays for alternatives.
10. **Evidence:** provenance, staleness, uncertainty, received/effective time, confidence only where calibrated.

Every geometry belongs to an identifiable source and revision. Standardize on WGS84 (`EPSG:4326`) for API lng/lat positions with `[longitude, latitude]` ordering, while keeping projected analytical geometries in declared CRS. Use PostGIS/PROJ transformations at boundaries and preserve altitude semantics explicitly.

## 4.3 Additional API contracts

Declare/implement normalized equivalents (adapt to existing API):

```text
GET  /api/scene/snapshot?scenario_id=...&revision=...
GET  /api/scene/entities?scenario_id=...&bbox=...&at=...
GET  /api/scene/tracks/{entity_id}?from=...&to=...
GET  /api/scene/layers
GET  /api/scene/asset-models
GET  /api/scene/tiles/manifest
GET  /api/scene/analysis/{analysis_id}
POST /api/scene/scenario/query
POST /api/scene/command        [authorization + revision check]
GET  /api/scene/events/stream  [or existing SpacetimeDB subscription]
```

Return a world reference on every result: `scenarioId`, `worldRevision`, `modelVersion`, `atTime`, result status and relevant source IDs. Define pagination/viewport bounds, projection metadata and conditional HTTP caching as appropriate. Implement authorization and rate limits at the server boundary. Do not expose NATS credentials to the browser.

## 4.4 Shared selected-context contract

```ts
interface SceneSelection {
  selectedEntityIds: string[];
  selectedServiceId?: string;
  selectedIncidentId?: string;
  selectedAnalysisId?: string;
  scenarioId: string;
  worldRevision: number;
  atTime: string;
  viewMode: 'operations' | 'immersive';
}
```

Changes to the shared selected context must update the map, entity inspector, timeline, dependency X-ray and analytic views coherently. Switching renderers must not deselect the asset or reset time unintentionally.

---
# 5. VISUAL SYSTEM — DESIGN A WORKSTATION, NOT A MARKER DEMO

## 5.1 Visual design principles

- **Professional minimalism:** compact, high-signal typography, sober colors, legible overlays, clear hierarchy, few ornamental elements. No fake radar sweeps, glowing sci-fi ornaments, giant unnecessary headings or constantly pulsing symbols.
- **Full-screen-first map:** the operational picture is the canvas; UI uses floating docked/resizable panels, restrained toolbars and collapsible inspectors.
- **Short page titles only:** e.g., `Operations`, `Terrain`, `Replay`, `Scenarios`, `Assets`, `Layers`. **No descriptive subtitle below page titles.** Within inspector panels, functional concise labels are fine.
- **One selection, one context:** when a service, asset or incident is selected, visually de-emphasize unrelated geometry rather than dumping all relationships simultaneously.
- **Data provenance visible:** observed, simulated, estimated, stale, unknown and proposed have consistent visual treatment. Color alone is insufficient; use line styles, shape changes, small badges or tooltips.
- **Camera movement serves a question:** smooth but quick selection fly-to, orbit, follow and reset. No cinematic animation delaying everyday tasks.
- **Accessible contrast:** distinguish terrain from operational overlays; support keyboard navigation, focus indicators, usable touch targets and reduced-motion preference.
- **Real objects, accurate semantics:** type-correct vehicle silhouettes and model scale, consistent altitudes, realistic motion only when supported by a defined motion model.
- **Density control:** fleet clusters at broad scale; operational symbols at middle scale; realistic 3D models only where size, zoom and GPU budget justify them.
- **Responsive:** desktop gets the full multi-panel geospatial workstation; tablet gets collapsible docks; phone gets entity lookup, events, map, tracking and a simple inspector rather than a forced miniature desktop.

## 5.2 Map styles — deliver real, visually excellent cartography

Deliver three selectable modes when compatible licensed data exists:

**Operational Dark (default)**

- Muted, detailed topographic vector style; restrained terrain/hillshade, roads and water; subtle landuse.
- Sparse place labels that do not compete with operational text and models.
- Crisp north arrow, scale bar, appropriate coordinates, terrain elevation details if supported.
- Controlled amber/orange for caution and red for actual model-defined critical conditions; consistent selected entity accent.
- No dramatic effects at the expense of objective readability.

**Satellite Hybrid**

- High-quality licensed satellite/ortho imagery with subdued administrative, road, and place labels.
- Switch imagery style without losing camera, selection, scenario, active overlays or time position.
- Handle missing/high-latitude coverage gracefully; show licensing attribution.

**Terrain / 3D**

- Support DEM-backed terrain and pitch/bearing controls; building extrusion or approved 3D Tiles if actually available.
- Use environment/lighting that clarifies relief; avoid unrealistic shadows and overly aggressive vertical exaggeration by default.
- Correct model placement relative to terrain and altitude datum.
- Provide simple accessible control to return to top-down operational view.

Tile sources may use licensed commercial providers, self-hosted OSM-derived vector tiles, compatible PMTiles packages or existing organizational infrastructure. Do not silently scrape map tiles or ship restricted providers' content in the repository. Include attribution, API-key management and capability flags for sources requiring credentials. Provide a visually complete **offline fallback** for at least one documented demo area using legally distributable data.

## 5.3 Desired top-level UI

Design the Operations workspace as:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ TROSSOPS    Operations  Sustainment  Intelligence  Scenarios  Evidence │
├─────────────────────────────────────────────────────────────────────────┤
│ [Search / Command] [Layers] [Style] [2D / 3D] [Replay] [Scenario] [⚙] │
│ ┌──────────────────────────────────────────────────┐ ┌──────────────┐ │
│ │                                                  │ │ ASSET /      │ │
│ │      GPU GEOSPATIAL OPERATIONAL SCENE             │ │ SERVICE      │ │
│ │      models, sites, tracks, terrain, reports      │ │ INSPECTOR    │ │
│ │      coverage, scenario effects, labels          │ │              │ │
│ │                                                  │ │ Records      │ │
│ │            [contextual selection]                │ │ Links        │ │
│ │                                                  │ │ Actions      │ │
│ └──────────────────────────────────────────────────┘ └──────────────┘ │
│ [Event feed]    [Time: live / replay]   [Attribution]  [Status]        │
└─────────────────────────────────────────────────────────────────────────┘
```

Actual layout must adapt to app design, screen size and existing shell. Panels must be resizable/collapsible and not permanently cover essential map content. Provide shortcuts for selecting, resetting camera, toggling layers, following an asset and exiting immersive mode.

## 5.4 Scene visual grammar

Document and implement a centralized token system for map rendering (not arbitrary color in each component):

- Entity category → silhouette/model family.
- Condition → border/halo/fill or emissive treatment, not only color.
- Evidence kind → solid/dashed/translucent/label distinction.
- Selected → prominent outline/highlight and linked label.
- Hovered → light preview, never mistaken for active selection.
- Stale → visibly faded/striped and timestamped, no continuing motion as fact.
- Planned → dashed trajectories and clearly labeled future/proposal time.
- Simulated → persistent `SIMULATION` mode indicator at app/scene level.
- Service area → translucent polygons/hexagons whose values come from computation; legend shows meaning, units and time.
- Restricted/controlled region → distinct semantic hatch/edge; only based on genuine/synthetic source data.

Construct these in a `SceneTheme`/`VisualSemantics` module and test mappings. Design tokens should adapt to light and dark if the product supports both.

---

# 6. ENTITY RENDERING — FROM ABSTRACT SYMBOLS TO REAL OBJECTS

## 6.1 Build a dedicated entity-rendering pipeline

Required entity classes (at minimum):

- Fixed-wing aircraft.
- Helicopters.
- Multirotor drones.
- Ground transport/support vehicles.
- Maritime vessels.
- Infrastructure/facilities.
- Generic unknown or unclassified types with clear non-deceptive fallback.

Each class needs a recognizable vector silhouette and, when close enough, a scaled/optimized glTF model. The asset catalogue must be data-driven: model IDs resolve to a manifest with type, scale, axes, origin, license/source, LOD alternatives, rendering caps and fallback.

Implement entity selection/picking across icon and 3D model LOD, using **stable domain IDs**. Models can disappear/reappear at LOD boundaries but selection, hover, labels and inspector context must not jump or reset.

## 6.2 Level of detail (LOD) and screen-space strategy

Do **not** hardcode one global zoom threshold as the only condition. Use zoom, estimated screen size, entity density, camera pitch and device performance tier. Hysteresis is necessary to avoid flicker as the camera crosses a threshold.

Suggested qualitative levels (numbers tuned experimentally):

| LOD | View context | Visible content | Implementation |
|---|---|---|---|
| L0 | National/regional | Fleet counts, incident density, geographic capacity aggregates | H3/cluster GPU layers |
| L1 | Regional operational | Recognizable 2D oriented silhouettes, compact labels, selected trails | `IconLayer`, `TextLayer`, collision filtering |
| L2 | Local operational | Larger silhouettes, selected 3D vehicles, infrastructure detail, altitude indicators | `SimpleMeshLayer` / `ScenegraphLayer` |
| L3 | Close inspection | Detailed selected vehicle/facility, camera follow/orbit, rich context | Selected high-quality GLB or Cesium entity |

Requirements:

1. Render broad-area aggregation without throwing away total entity counts or selection access.
2. Cross-fade or swap models without annoying popping; avoid 3D all-at-once loads.
3. Keep selected items prioritized and visible through LOD changes.
4. Enforce per-device dynamic model count, texture and triangle budgets.
5. Cluster based on source data where appropriate; aggregate categories/health truthfully rather than averaging incompatible metrics.
6. Render labels according to selection, severity, proximity and screen-space collision priority.
7. Use spatial indexing/viewport queries to avoid transferring an entire historical world to a small viewport.
8. Verify LOD under 2D north-up, pitched terrain, follow-camera and high-DPI.

## 6.3 3D model asset pipeline

Create a legally sourced or in-house model library. Prioritize visual consistency over gratuitously high polygon counts:

- Source manifest: model key, object category, author/source, usage license, attribution, geometry metadata, import conversion and version.
- Deliver `.glb` for web consumption and optional lower-LOD GLBs.
- Normalize physical scale; document meters and known size. Do not assume GLB units or pivot axes without inspection.
- Choose an agreed forward/up axis and transform model orientation at ingestion. Verify common differences between glTF conventions, Three.js/Cesium frames, NED/ENU vehicle attitudes and deck.gl `getOrientation` semantics.
- Optimize geometry/meshes using glTF Transform; reuse meshes and materials; compress textures only when decoder support exists and performance is measured.
- Simplify materials, preserve credible colors and PBR response, reduce texture memory and avoid huge uncompressed textures.
- Support mesh/scenegraph instancing when many entities use the same model.
- Load models asynchronously with visible fallback silhouettes; broken GLB must never blank the scene.
- Cache/dispose GPU resources correctly on asset change, scenario switch and viewer unmount.
- Verify attribution, asset paths and packaging in local/offline deployment.

Do not bundle restricted military CAD files or claim platform-exact accuracy unless authorized and substantiated. Stylized realistic generic platform classes are preferable to counterfeit specificity.

## 6.4 Render behavior by class

- **Aircraft:** align yaw/heading and pose; bank/attitude only if source data or explicit motion-model simulation provides them; reflect altitude honestly.
- **Helicopters:** oriented fuselage and plausible rotor animation in close view, with clear difference between simulation and observed flight state.
- **Multirotor:** correct multicopter scale; rotor animation optional and frame-rate efficient; stop/hover truthfully.
- **Ground assets:** align with route-bearing when a route exists; do not teleport onto roads merely to look realistic if the original observations disagree.
- **Vessels:** correct heading and smooth low-frequency movement; water appearance appropriate to base map.
- **Facilities:** stationary linked geospatial objects; use actual structures or generic GLB footprints; do not imply precise real-world structures without data.
- **Unknown:** simple neutral vector marker with explicit `Unknown type` status, not a misleading aircraft model.

## 6.5 Entity inspector

A selected entity must open a compact, data-backed, tabbed or sectional inspector:

- **Overview:** ID, class, name, position, observed time, speed/heading/altitude when available, condition, evidence category and staleness.
- **History:** position track, events, time range, last observations.
- **Sustainment:** equipment record, faults, maintenance notification/work order, personnel/inventory dependencies where APIs exist.
- **Capabilities:** requirements served, capability contribution, computed status and dependency X-ray link.
- **Scenarios:** ability to select an authorized simulated intervention and view effects.
- **Evidence:** underlying source reports, quality and relevant revisions.

Do not put fabricated metrics in the inspector. If a field is unavailable, use a clear unavailable/unknown state. Make deep links possible: URL route/query preserving selected entity, scenario and time. Respect authorization on all data fetches.

---

# 7. TIME, TRACKS, ORIENTATION AND MOTION

## 7.1 Introduce a dedicated simulation-aware render clock

The **render clock** is not the browser wall clock. Build a controller supporting:

- Live mode (buffered/interpolated observations).
- Historical replay mode (selected time, pause, speed multiplier, scrub, reverse stepping if feasible).
- Scenario mode (the selected fork and scenario time).
- Compare mode (aligned common time horizon across alternative branches).
- Follow mode (camera tracks selected entity while staying within renderer performance/UX limits).

Separate `eventEffectiveAt`, `receivedAt`, `positionSampleAt`, `scenarioTime`, `serverNow` and `renderTime`. Historical calculations must use the *information known as of the selected decision time* when the user explicitly requests that perspective, not later truth.

## 7.2 Motion interpolation pipeline

```text
Telemetry / simulated event / track fetch
      ↓ normalize & validate coordinate frame
Timestamped bounded entity sample buffer
      ↓ drop duplicates / flag gaps / order samples
Time controller chooses render time
      ↓ position / orientation interpolation
GPU attribute and model transform updates
      ↓ deck.gl / Cesium renders frame
```

- Keep a short rolling sample buffer for live entities and a paged/chunked history store for replay.
- Use defensible geographic interpolation (geodesic or ECEF/local tangent transforms where appropriate) rather than naive longitude/latitude linear interpolation across discontinuities, poles or long distances.
- Use quaternion interpolation for orientations where available; properly wrap headings through 360° instead of rotating nearly a full circle.
- Restrict extrapolation. Define a maximum allowed horizon; after that, freeze/fade/mark `stale` and distinguish estimated from observed positions.
- Break tracks across severe data gaps or teleports; do not draw a false continuous path across missing samples.
- Use explicit motion models only for synthetic simulations, not assumed real observations.
- Use per-entity/per-class speed and acceleration sanity checks to flag anomalies for inspection, never silently rewrite original data.
- Avoid React state updates at 60Hz for every entity. Use a dedicated typed-array/GPU update path and stable component instances; React handles coarse UI state.
- Minimize WebSocket/SpacetimeDB subscriptions in individual leaf components; normalize data once into the entity store.

## 7.3 Altitude and reference frames

Document and test transformations among WGS84 ellipsoid height, mean sea level and height above ground where the relevant elevation/geoid model is available. If transformations cannot be performed defensibly, preserve and display the source datum, and avoid cross-datum geometric claims.

- Define reference frames (`ECEF`, local `ENU`, vehicle `NED`, body) and their handedness/axis conventions.
- Verify GLB forward/up axes and camera orientation against map bearing.
- Handle longitude wrapping/dateline, near-pole inputs if applicable, map projection limits, missing terrain tiles, altitude unknown and below-terrain outliers.
- Site markers should be ground-clamped only when the data represents a ground feature.
- Do not clamp an aircraft to terrain or invent a flight altitude.
- In Cesium, correctly specify position height reference and orientation, and validate sampled position interpolation.

## 7.4 Trails and time playback

- `TripsLayer` or equivalent time-aware trails with fading behind moving entities; selectively show tracks for all or only selected assets.
- Tail length measured in **time**, not only map pixels.
- Show a play/pause, scrub, playback speed, current time, live/replay badge, and jump-to-event controls.
- Display observed and planned trajectories with distinct styles and legends.
- Event markers on timeline open the linked entity/incident and seek to the relevant time.
- In branching scenario mode, compare aligned timestamps and mark different projected positions/availability.
- Keep animations deterministic given the same timeline, sample data and render settings.

---

# 8. CAMERA, INTERACTION AND IMMERSIVE PRESENTATION

## 8.1 Camera controller API

Implement one high-level semantic camera interface, backed by viewer-specific adapters:

```ts
interface GeoCameraController {
  flyToEntity(id: string, opts?: { durationMs?: number; pitchDeg?: number }): void;
  followEntity(id: string, mode?: 'chase' | 'orbit' | 'topdown'): void;
  orbitEntity(id: string, opts?: { radiusM?: number; speed?: number }): void;
  flyToArea(areaId: string): void;
  fitEntities(ids: string[]): void;
  setBearing(deg: number): void;
  setPitch(deg: number): void;
  resetOverview(): void;
  stopAnimation(): void;
}
```

MapLibre and Cesium adapters can implement materially different camera mechanics under one intent-level contract. A camera transition must not mutate the entity's real position. Preserve last useful viewpoint when switching tabs and scene modes.

## 8.2 Required interactions

- Click/select entity with reliable 2D/3D GPU picking; multi-select and deselect.
- Hover preview with concise type/name/status.
- Camera fly-to on asset selection; optional easing and `prefers-reduced-motion` respected.
- Follow moving entity smoothly without uncontrolled oscillation or motion sickness.
- Orbit selected 3D entity or facility in immersive mode; top-down reset.
- Search by identifier/type/location; search results pan/zoom and select.
- Fit current selection, affected entities or an operational area.
- Toggle layers individually and in presets; preserve user preferences if product persistence allows.
- Box/lasso selection when feasible; avoid misrepresenting dense clusters as individual selectable items.
- Spatial measurement tools (distance in meters/kilometers, area in square kilometers), preferably 3D-aware when needed; accurately label straight-line vs surface distance.
- Coordinates on click and pointer, configurable decimal/degrees format, always known datum.
- Scenario fork/compare controls preserving camera, map style, selected objects and relative time.
- Keyboard shortcuts and accessible control alternatives to drag-only actions.

## 8.3 Camera choreography for the showcase

Deliver subtle, professional transitions with named camera presets:

1. **Fleet overview:** wide operational view showing the scope of the synthetic environment.
2. **Event focus:** smoothly focus affected asset and reveal context, not an excessively dramatic camera move.
3. **Dependency focus:** highlight geographically affected resources and optional graph X-ray links.
4. **Recovery alternatives:** fit competing resources and routes; compare scenario result overlays.
5. **Asset inspection:** optional pitch/orbit/3D facility with detailed model.
6. **Return to operations:** one click resets to useful overview.

Keep a short scripted **demo itinerary as UI actions**, but all outcomes must come from the actual source scenario and backend computations. The scene must still work when a user selects a different asset or failure.

---
# 9. GEOSPATIAL LAYERS THAT ARE ACTUALLY OPERATIONAL

Implement a typed, reusable `LayerRegistry` with visible toggles, ordering, zoom bounds, prerequisites, legends, data-state indicators, style presets, performance hints and world revisions. An overlay must declare source semantics and the transformation producing its geometry.

## 9.1 Required layers

| Layer | Renderer / method | Required source semantics | User interaction |
|---|---|---|---|
| Basemap/terrain | MapLibre map style, DEM | Licensed geographic tiles, CRS, attribution | Style switch, pitch, hillshade |
| Assets | deck.gl Icon/Scenegraph/Mesh | Valid scene entities + model manifest | Pick, select, focus, inspect |
| Asset labels | Text/collision layer | IDs, type, priority, condition | Hover, search, filter |
| Historical tracks | Trips/Path layer | Timestamped position samples | Time scrub, selected tails |
| Planned routes | Path/GeoJSON | Declared *planned* paths and validity windows | Inspect plan/assumptions |
| Facilities | GeoJSON, 3D buildings, GLB | Grounded site geometry and linked resources | Open work orders / inventory |
| Events and incidents | GPU symbol layers | Source report, category, time, state | Seek event, open evidence |
| Operational areas | GeoJSON/Polygon | Requirement location, permissions, boundaries | Inspect demand and context |
| Service capability | H3/Polygon/heatmap | Backend-computed feasibility or capacity under a specific scenario | Inspect metric/assumption |
| Dependency influence | Filtered paths/linked highlights | Backend impact graph + geolocated entities | Explain why affected |
| Recovery logistics | Planned paths/flow arcs | Actual solver-produced transfer/repair proposals | Open linked intervention |
| Scenario alternative | Distinct ghost/proposed geometry | Branch ID, future time, predictive status | Compare, toggle, inspect |
| Uncertainty/staleness | Shader/icon/legend treatment | Observation age/quality, unresolved state | Inspect provenance |
| Optional media footprints | Polygons/volumes | Real calibration or explicit synthetic parameters | Jump to associated evidence |

Do not conflate a coverage polygon with a valid operational capability: service areas must follow a declared geometric/analytic model. A circle drawn from a guessed radius is a **synthetic illustration**, not a verified radio, sensor or rescue-service footprint.

## 9.2 Dependency X-ray on the map

When the operator selects a service/asset/event:

1. Query the existing dependency/impact engine, not a frontend reimplementation.
2. Receive affected entities and typed relationships plus world revision.
3. Highlight geolocatable nodes on the map and reveal a focused React Flow graph in a resizable panel.
4. Visually distinguish direct prerequisites, shared support, substitutable resources, computed blockers and unrelated objects.
5. Click a graph node to focus the corresponding geographic entity, and vice versa.
6. Display the applicable evidence/time and constraint explanation.
7. Handle non-geolocatable resources (technicians, inventory, software constraints) in the graph/inspector without fabricating map coordinates.
8. Use computed output to show consequence counts; do not count simple graph adjacency as mission impact.

## 9.3 Capability geography and H3

Use H3 **when it improves regional aggregation**; it is not required for every geospatial problem. When using hexagons:

- Clearly define resolution, cell area, normalization and aggregation rule.
- Display exact units (e.g., service-hours per cell, assets within range, conditional service feasibility).
- Avoid averaging Boolean feasible/infeasible outcomes into misleading readiness values without explaining the aggregation.
- Select cell to inspect contributing resources and analysis assumptions.
- Support playback and scenario comparison for computed regions.
- Recalculate server-side when relevant state/requirements change; cache by scenario revision and analysis parameters.

## 9.4 Spatial calculations and correctness

- Use PostGIS and/or reliable geodesic/geometric libraries for distance, intersection and spatial queries rather than writing unchecked lat/lon arithmetic.
- Differentiate angular degrees from metric distances; no hidden conversion assumptions.
- Document whether a route distance is straight-line geodesic, drivable road route, planned trajectory length, or simulated path.
- If third-party road routing is missing, show straight-line/geodesic with an explicit label rather than pretending it follows streets.
- For altitude/LOS/radio features, establish terrain/elevation availability and a declared physical model before presenting numeric results.
- Be precise about `EPSG:4326` versus projected metric coordinate systems; only perform metric buffer operations in appropriate projections/geography semantics.

---

# 10. IMMERSIVE 3D INTEGRATION

Build an optional `CesiumScene` package that shares `SceneSelection`, `GeoSceneState`, entity references, time and scenario. This is not a separate app with its own fake world.

## 10.1 Cesium-specific requirements

- Load Cesium only within a client-side boundary; verify bundler static assets/workers under actual Next.js version, CSP and production build.
- Use terrain provider and 3D Tiles sources whose licenses, keys and geographic coverage have been verified.
- Create entities/models from the normalized scene entity adapter, not from a second hardcoded dataset.
- Convert attitude, quaternions, height references and timestamps consistently; test against map renderer.
- Support primitive/entity pooling for large dynamic sets; measure Cesium entity API scaling before committing to one object per high-frequency sample.
- Manage 3D Tiles screen-space error, caching, high-DPI, material complexity and model LOD.
- Provide camera fly-to, follow, orbit, atmospheric context and measurement tools where appropriate.
- Provide correct occlusion/clamping behavior and clear distinction of ground vehicles vs aircraft altitude.
- Avoid adding an opaque external token into client code; use appropriate scoped/restricted public tile credentials and keep true secrets server-side.
- Handle restricted data or missing photogrammetry gracefully with Cesium terrain/OSM-available geometry or conventional map fallback.
- Maintain map selection and timeline exactly across mode switches.
- Destroy Cesium Viewer, event handlers, subscriptions and GPU resources on unmount; prevent WebGL context leaks when switching repeatedly.

## 10.2 3D site digital twin (separate optional module)

For a showcase installation, warehouse, maintenance facility or charging site, build a focused site inspection view:

- Optimized generic 3D site geometry with licensed textures.
- Click warehouse/bay/resource to open linked work order, inventory or site-resource availability.
- Visualize spatially valid movement/activities when simulation provides them.
- Highlight support dependency paths between a facility and other assets.
- Preserve plan-versus-actual labels and state revisions.

Only add React Three Fiber or custom Three.js site-specific tooling if needed beyond Cesium/MapLibre. Keep it behind an explicit interface to the shared scene entity model.

## 10.3 3D asset placement acceptance cases

Implement reproducible cases:

1. Ground building model correctly placed at known synthetic facility coordinate and altitude reference.
2. UAV GLB above terrain at a declared height; no accidental ground snapping.
3. Heading zero/east/south/west verified against map compass and physical model forward axis.
4. Roll/pitch supported without inconsistent handedness or inverted rotations.
5. Terrain tiles unavailable → scene still renders an honest fallback.
6. Switching from map to Cesium retains selected UAV, viewpoint intent, selected time and scenario revision.
7. Repeated switching does not continuously increase WebGL contexts or memory.

---

# 11. STATE DELIVERY, BACKEND INTEGRATION AND MULTI-USER PROJECTIONS

TrossOps's original stack includes **Next.js, FastAPI, PostgreSQL/PostGIS, SpacetimeDB, NATS, DuckDB and OR-Tools**. Keep those roles explicit.

## 11.1 Authority boundaries

- **PostgreSQL:** source of truth for enterprise state: assets, facilities, work orders, parts, personnel, resource reservations, approvals and audit events.
- **PostGIS:** authoritative/geometric queries for stored facilities/regions and spatial relationships, where these are part of backend domain state.
- **Simulation/scenario engine:** authoritative *within a synthetic scenario branch*, not in the real-world enterprise database.
- **SpacetimeDB:** optional realtime read model/projected operational scene and collaborative presence; it must not independently own ERP balances and maintenance transactions.
- **NATS JetStream:** durable inter-module events and replay; do not expose the broker directly to untrusted browser clients.
- **DuckDB/Parquet:** analytical/historical querying, not authoritative mutable live transactions.
- **FastAPI:** commands, backend analysis, validation, authorization and inspector queries.
- **Client-side scene store:** interpolation and presentation only; not a source of physical or enterprise truth.

## 11.2 Event propagation to scene

```text
Observation / simulated scenario event
    → ingestion validation + source classification
    → authoritative domain event / scenario event
    → transactional outbox (for committed enterprise changes)
    → NATS JetStream (or existing reliable project transport)
    → scene projection consumer (idempotent)
    → SpacetimeDB and/or SSE projection
    → normalized frontend entity buffer
    → GPU scene + inspector + linked views
```

A single event can also trigger capability impact evaluation. This is a separate derived analysis with its own result revision, not a direct forced color change.

### Correctness requirements

- Every event carries stable `eventId`, entity/domain ID, source, scenario, schema version, relevant clocks and correlation ID.
- Ensure transactional outbox for committed enterprise updates; use idempotent consumers for at-least-once delivery.
- Projection carries **last applied world revision** and visible delay/health metadata.
- The UI must not display projection revision 12 with capability result revision 10 as if both describe one current state.
- Avoid broadcasting the complete fleet on every 100 ms tick; support deltas, snapshots, backpressure, viewport filtering and resync.
- Incoming stale or out-of-order positions must not silently overwrite newer records. Define late-event handling and bitemporal replay semantics.
- Source changes must not result in duplicate visual entities for one actual domain ID.
- Preserve ability to run full synthetic/offline mode with the same frontend contracts.

## 11.3 Live entity buffer implementation

A preferred architecture:

```text
Server snapshot + delta stream
          ↓
Validated typed `GeoSceneAdapter`
          ↓
EntityStore: Map<ID, TimedEntityBuffer>
          ↓                  ↘
Interaction state          History worker/cache
          ↓                  ↙
Render clock + interpolation
          ↓
GPU layer accessor attributes / model transforms
          ↓
Frame render (not React component rerender-per-asset)
```

Use stable IDs and a compact ring buffer per tracked entity. Workers may preprocess historical tracks into typed arrays, simplified segments, and layer-ready binary attributes. Prefer transferable buffers when appropriate. Profile actual memory/copy cost.

## 11.4 External adapters and truthful states

Support an explicit source status vocabulary:

- `live-connected`: authorized, tested stream exists.
- `simulated`: internally generated event stream.
- `imported`: verified static/historical dataset.
- `configured-not-connected`: adapter/config exists but no tested live stream.
- `unavailable`: provider/key/service unavailable.
- `planned`: not yet implemented.

Potential adapters (only when requested/authorized and technically available): ROS 2/PX4/MAVSDK and MAVLink telemetry, OGC SensorThings, GeoJSON/OGC API Features, properly licensed aviation/maritime datasets, SAP-compatible OData equipment/maintenance APIs, live media event references, H3/PostGIS service tiles.

Never claim a direct connection to actual PRIO or DELTA. The system is **functionally inspired** by those categories, not a clone of restricted internal services.

---

# 12. FRONTEND ENGINEERING WITH NEXT.JS

Respect the existing application's Next.js version and routing architecture. Make WebGL renderers client-only; dynamically import MapLibre/deck/Cesium bundles so SSR does not attempt to access `window`, `document`, WebGL or browser APIs.

## 12.1 Suggested feature package structure

Adapt to repo rather than blindly transplanting it:

```text
frontend/
  src/
    features/
      geoscene/
        contracts/
          entities.ts
          layers.ts
          scenario.ts
        core/
          EntityStore.ts
          SceneClock.ts
          Interpolator.ts
          SceneSelection.ts
          GeoCoordinateFrames.ts
          LayerRegistry.ts
          PerformanceTier.ts
          CameraIntent.ts
        adapters/
          DomainSceneAdapter.ts
          SimulatedSceneAdapter.ts
          RealtimeSceneAdapter.ts
          HistoricalTrackAdapter.ts
        renderers/
          MapLibreScene.tsx
          DeckLayers.ts
          CesiumScene.tsx
        layers/
          EntityIconLayer.ts
          EntityModelLayer.ts
          EntityLabelLayer.ts
          TrackLayer.ts
          FacilityLayer.ts
          IncidentLayer.ts
          CapabilityAreaLayer.ts
          DependencyHighlightLayer.ts
          ScenarioAlternativeLayer.ts
        components/
          SceneToolbar.tsx
          MapStylePicker.tsx
          EntityInspector.tsx
          LayerExplorer.tsx
          TimelineTransport.tsx
          CameraControls.tsx
          SceneLegend.tsx
          ScenarioCompare.tsx
        assets/
          models/
          sprites/
          manifest.json
        styles/
          operational-dark.json
          satellite-hybrid.json
          terrain.json
      ...existing product features...
```

## 12.2 State separation

- Use server query cache (e.g., existing TanStack Query) for authoritative snapshots, detail records and analytical results keyed by scenario+revision+parameters.
- Use a small client UI store (existing Zustand/context) for selected items, open panels, tool mode, map style and camera intent.
- Use a specialized render state buffer for high-rate entity poses and interpolated transforms. Keep it decoupled from full React reconciliation.
- Do not keep separate, divergent camera/selection/entity stores in different tabs.
- Keep layer configuration serializable for stable URLs, persistence or shareable incident workspaces.

## 12.3 Domain/UI actions

Clearly distinguish:

- UI-only action: focus entity, toggle layers, switch basemap, scrub local replay time.
- Analytical query: compute coverage, dependencies, availability, compare scenarios.
- Simulation action: change simulated event/branch, advance synthetic time.
- Authorized enterprise transaction: create fault notification, assign technician, reserve part, approve work order.

These actions must travel through different appropriate paths and permissions. A drag-and-drop visual resource repositioning must not silently commit a real-world assignment.

## 12.4 Responsiveness and interaction quality

- Desktop: map-dominant with inspector and bottom timeline; panel sizes persist where reasonable.
- Tablet: single expanded panel and flexible overlay controls.
- Mobile: essential map and selected asset inspector; no clipped modal dialogs or permanently hidden controls.
- Support reduced motion, keyboard navigation, arrow/escape interactions and visible focus.
- Show loading, partial data, offline and expired session states with clean UI, not unexplained blank map.
- Keep titles short with no explanatory subheading under main section titles.

---

# 13. PERFORMANCE ENGINEERING AND OBSERVABILITY

A visually ambitious platform cannot be called complete without instrumented performance.

## 13.1 Targets (starting design objectives, not promised guarantees)

Test on at least two documented device classes. Prioritize a realistic laptop GPU and a lower-spec/integrated-GPU machine.

| Scenario | Target | Test guidance |
|---|---|---|
| Ordinary COP with ~200 actively moving entities | Smooth interaction; aim for 60 FPS on representative desktop | 1440p or declared test resolution, actual models and overlays enabled |
| Dense 1,000–3,000 symbol view | Acceptable pan/filter; aim for 30+ FPS on representative laptop | Correct GPU layer, clustering, label controls |
| One selected detailed glTF model | No noticeable freeze during selection | Progressive asset load and camera transition |
| Camera pan/zoom | No multi-second blocking | Measure input-to-render response and dropped frames |
| Data delta delivery | No global React rerender per asset sample | React Profiler plus browser performance trace |
| Scenario switch | Clear visual loading and consistent world revision | No stale cross-branch overlays |
| Immersive viewer | Reasonable startup, progressive tiles | Record time-to-first-useful-frame and GPU memory trend |
| Viewer mount/unmount | Stable resource use across repeated switches | Check leaked WebGL contexts, subscriptions and handlers |

These are engineering targets **not benchmarks already achieved**. Do not invent benchmark numbers in the final report. Report hardware, browser, resolution, data set, LOD settings, measurement procedure, median/p95 frame time where feasible.

## 13.2 Rendering efficiency checklist

- GPU layers for large entity sets, not HTML markers.
- Instancing/shared geometry for repeated models; lower LOD at broad scale.
- Memoize stable layers/accessors and avoid unnecessary MapLibre/deck reinitialization.
- Keep parent React components from rerendering with every telemetry tick.
- Reuse GLB assets and texture/material caches; free unused resources.
- Dynamic render-quality tier: device-pixel-ratio cap, texture LOD, model count, optional shadows/lighting, trail lengths and label density.
- Viewport-based entity queries and spatial indexing; simplify long history tracks, query by time ranges.
- Geometry preprocessing/tiling in workers, typed arrays and transferable buffers where beneficial.
- Detect reduced-motion preference and software-renderer/WebGL limitations.
- Degrade to 2D icons or simpler basemap instead of crashing or indefinitely loading.
- Monitor main-thread long tasks, WebGL warnings, model load failures and client memory.
- Maintain an optional performance diagnostic overlay showing FPS, visible entities, selected LOD, active layers, model count and tile status.

## 13.3 Logging and tracing

Instrument:

`incoming event → projection revision → scene update → rendered frame`

and:

`user selects asset → detail query → capability analysis → layers update → inspector displays result`.

Use existing OpenTelemetry/Grafana stack if present; otherwise add lightweight structured timings without imposing major observability infrastructure. Correlate request IDs and scenario revisions. Never send sensitive operational payloads to third-party telemetry by default.

---
# 14. TESTING: PROVE IT IS NOT A PRETTY MOCKUP

The quality gate is not a screenshot. It is a reproducible browser-based, data-grounded interaction across frontend, state projection and backend.

## 14.1 Contract and algorithm tests

1. **Coordinate validity:** legal bounds, longitude/latitude ordering, datums and unit parsing; reject NaNs and impossible shapes.
2. **Orientation:** cardinal headings, heading wraparound, ENU/NED transforms and GLB forward-axis correction.
3. **Interpolation:** known tracks at multiple timestamps; stationary entity, route segment, dateline crossing, orientation slerp and gap handling.
4. **Staleness:** last observation expires and marker stops pretending to move as an observed fact.
5. **Track correctness:** historical trail never connects across a flagged discontinuity; planned route does not overwrite observed route.
6. **Revision identity:** stale result from another scenario/world revision is never displayed as current analysis.
7. **Layer correctness:** resource classes, condition/provenance visuals, legend and filter output match validated data.
8. **LOD consistency:** icon and model representations resolve to the same entity ID and selection.
9. **Scenario isolation:** a failure applied in scenario B does not alter parent A or sibling C.
10. **Analytical overlay:** computed service area matches a known golden scenario fixture and is not independently fabricated by the map.
11. **Authorization:** user cannot fetch another tenant's restricted track or mutate enterprise data through a map UI bypass.
12. **Realtime consistency:** duplicate/out-of-order events do not corrupt the projection or duplicate rendered objects.
13. **Altitude:** ground and aircraft example positions render according to declared reference.
14. **Backwards compatibility:** existing backend and product routes remain functional.

Use Vitest for pure TypeScript math/state logic, relevant backend pytest/Hypothesis for schemas and analysis, and contract tests on serialized responses. Add a small independent oracle for sampled interpolation and coordinate transforms rather than accepting implementation output as its own expected test data.

## 14.2 Browser acceptance with Playwright

Implement actual E2E scenarios:

**E2E-01 — Load useful scene:** Navigate to Operations, load licensed/offline basemap, see assets of at least three classes, layer picker, legend, attribution, status and no blocking console error.

**E2E-02 — Select and inspect:** Click a moving synthetic asset, inspect ID/class/status/source time, follow it, and open linked domain record without losing selection.

**E2E-03 — LOD:** Zoom from regional to local view; cluster → oriented icons → selected 3D GLB; verify stable IDs, correct heading and no flicker.

**E2E-04 — Time:** Scrub historical time; entity position and trail match fixture, information/freshness indicator updates; return to live/simulation time.

**E2E-05 — Fault event:** Apply a permitted synthetic event through the backend; resource condition updates in projected scene; incident/maintenance link appears; dependency/capability overlays refresh with a matching revision.

**E2E-06 — Branching:** Fork current scenario; apply a repair in branch B; compare B with A; original remains unchanged and the UI labels both states.

**E2E-07 — Terrain and 3D:** Pitch terrain; select model with correct altitude, orbit/follow and reset. If Cesium mode is complete, switch viewer and verify same selection/time.

**E2E-08 — Offline/degraded:** Disable external network or map endpoint; the app loads available offline style, local fixtures and fundamental interactions, with clear missing-layer status.

**E2E-09 — Mobile:** Open mobile viewport, search/select entity, show usable inspector, no off-screen controls, accessible nav.

**E2E-10 — Non-scripted:** Select a different synthetic event or asset not central to showcase, and verify the correct generic behavior rather than an ID-specific animation.

Collect representative screenshots and browser trace artifacts; check visual regressions where stable. If WebGL rendering is not supported in CI, run tests with suitable browser flags or containerized graphics and clearly label environment limits. Never mark E2E as passing when it was skipped.

## 14.3 GPU and asset verification

- Asset manifest references exist and legally required attribution/license metadata is present.
- GLB origin/scale/axis unit tests or golden visual scenes for heading at 0°, 90°, 180°, 270°.
- No 3D model treated as selected when its associated domain entity is unselected.
- GPU resource and browser memory footprint measured before/after 20 viewer switches or scenario swaps.
- Missing asset file produces fallback icon and non-blocking error log.
- Device tier downgrade changes LOD/render complexity without affecting domain truth.
- Tile request failures do not silently leave a blank unresponsive viewport.
- Repeated WebSocket/SpacetimeDB reconnection does not multiply subscribed listeners.

## 14.4 Test matrix and completion ledger

Maintain `docs/geospatial/verification.md` listing each acceptance case, test command, result, browser/device environment, evidence location, implementation status and open bugs. Use `pass`, `fail`, `blocked`, `not-run`; not merely checkboxes without execution.

---

# 15. CONCRETE SYNTHETIC WORLD AND LIVE-DEMO CONTENT

The scene must be compelling with no restricted data and no external live systems. Create a compact but rich, **explicitly synthetic** coastal emergency-support environment with geographies clearly labeled as fictional or synthetic. Use sensible geography or an explicitly fictional/test region without inventing actual military site details.

## 15.1 Initial world content

A representative dataset (adapt count and properties to repo data):

- 6–12 aerial assets (mix of fixed-wing, helicopter, multirotor) with varied trajectory altitude, motion and condition.
- 6–12 ground vehicles with logistics roles and maintenance/support assignments.
- 3–6 vessels with distinct movement/operational roles.
- 4–8 sites: maintenance, charging, logistics storage, communications and response headquarters.
- Selected technicians, parts, stock and work orders represented primarily in inspector/dependency graph where they do not have honest continuous geographic tracks.
- 3–5 explicit operational requirements, each with defined area, time horizon and resource prerequisites.
- A controlled event stream of motion, depletion, fault, report, repair, replenishment and transfer events.
- One scenario demonstrating shared infrastructure loss; one complementarity/resource bundle; one priority shift; one stale report; one branchable response comparison.

Do not seed hundreds of assets merely as decoration. The default world should be understandable from a map, and entity count should scale in an optional performance stress scenario.

## 15.2 Five-minute high-end demonstration

This is **a suggested presentation itinerary**, not hardcoded frontend state logic:

| Clock | Map/scene experience | Real technical behavior |
|---|---|---|
| 00:00–00:35 | Professional operational map opens, assets move smoothly, terrain subtly visible, 2D/3D symbol mix scales by zoom. | Bundled scenario, entity buffer, GPU layers, meaningful status |
| 00:35–01:05 | Select a UAV; camera flies to it, model heading/altitude and observed trail visible; inspector displays data and provenance. | Valid ID → asset/tracks/source records; animation from samples |
| 01:05–01:45 | Trigger a synthetic support fault. Geographic assets and event overlay update, affected service regions and dependency paths appear. | Backend event → revisioned projection → calculated impact |
| 01:45–02:25 | Open dependency X-ray and real linked enterprise record. Reveal a non-obvious shared bottleneck across multiple assets. | Domain impact engine + resource/maintenance API, not UI adjacency arithmetic |
| 02:25–03:20 | Select recovery plans; map shows proposed transfers, waiting vs repair trade-offs, capability overlays and time of recovery. | OR-Tools/SimPy results under explicit assumptions |
| 03:20–04:05 | Fork scene; synchronized futures A/B/C show separate tracks and outcomes; alternative plans marked hypothetical. | Independent branches from same revision and declared time horizon |
| 04:05–04:35 | Switch to 3D inspection; orbit selected synthetic asset/facility against terrain and structures. | Shared entity IDs and clock, Cesium optional, honest altitude |
| 04:35–05:00 | Audience changes one supported event/requirement; computed consequence updates. | Generic scenario API, no hardcoded result |

If immersive mode is not production-ready, use the time to demonstrate more robust scenario comparison. Never show a fake 3D feature as if complete.

## 15.3 Showcase quality bar

Judges should observe these facts without needing to take the developer's word for them:

1. The map is custom styled and polished, not default tiles with simple dots.
2. Different asset classes are immediately recognizable from silhouette and/or physical 3D models.
3. Motion is smooth and tied to a controllable clock rather than random jumping.
4. Selection persists and opens real linked asset/maintenance context.
5. Geographic overlays are linked to computational meaning, with legends and source time.
6. Changing the synthetic world updates the scene and relevant analyses through actual APIs.
7. Alternate scenarios are distinct, replayable and labeled.
8. 3D is coherent spatial inspection, not a separate unrelated game scene.
9. The application remains responsive and has a graceful degraded mode.
10. The team can demonstrate tests and reveal the exact event/analysis revision.

---

# 16. MULTI-AGENT CODING ORGANIZATION

Parallelize around actual seams, not just the number of visual features. The core contracts/renderer package should have one integration owner; multiple agents should not edit the same state-model files simultaneously.

| Agent | Ownership | Acceptance evidence |
|---|---|---|
| Integration architect | Existing repo reconnaissance, ADRs, typed scene contracts, overall rendering selection and merge policy | Stable shared interfaces, running baseline |
| Cartography/layer engineer | Licensed basemaps, styles, MapLibre/deck integration, layer registry, basemap modes, terrain | Real map with selectable layers, attribution and styles |
| Entity/asset engineer | Manifest, GLBs, axes/scale, LOD, sprites, GPU model rendering, picking | Multiple accurate classes, golden heading/selection tests |
| Temporal engineer | Event buffer, interpolator, tracks, replay clock, stale state | Deterministic replay and motion tests |
| Interaction/UI engineer | Shell, toolbar, inspector, camera intent, panels, keyboard/mobile UX | Playwright workflows and cohesive layout |
| Backend/projection engineer | Scene API, geospatial queries, SpacetimeDB/NATS/SSE, source/role checks | Revisioned snapshot and delta end to end |
| 3D specialist | Cesium viewer, terrain, 3D Tiles, altitudes, camera, resource cleanup | Same-scene 3D inspection tests |
| Test/performance engineer | Golden fixtures, WebGL E2E, frame-time profiling, failure modes, regressions | Measured independent results and trace artifacts |

Workstream order: architect freezes contracts and initial fixtures; cartography, model/assets, temporal and backend adapters can then proceed in independent worktrees; frontend integrates progressively. Cesium specialist should begin only after the scene contract and model manifests stabilize, or work against fixtures independently.

## 16.1 Agent handoff template

Each agent's task must state:

- **Goal** and user-visible acceptance behavior.
- **Starting branch/worktree** and files it may edit.
- **Required contracts** and fixture data.
- **Libraries/API versions** actually pinned, or version-resolution task.
- **Tests that must run**, with exact commands.
- **What it must not modify** without integration approval.
- **Evidence**: screenshots, test output, performance trace or schema samples.
- **Known limitations** and follow-up integration action.
- **Commit list**, preferably several logically separated feature/fix/test commits.

Do not accept claims like "implemented 3D" when only a component skeleton exists. Completion requires a visible testable path.

## 16.2 AI coding behavior

- Keep `AGENTS.md` concise and consistent with broader TrossOps instructions.
- Write code and tests, run the app, inspect browser behavior, then refine. Do not stop at code generation without execution.
- Make small commits as components reach green gates, not one giant final commit.
- Use existing packages when already configured and functioning; avoid duplicate state or mapping frameworks.
- Delegate cross-functional decisions to one integrator, document deviations as ADRs.
- Mock external services only behind an explicit adapter state; never mock the core scene contract when tests purport to exercise it.
- Implement adaptive fallback solutions if WebGL/tile provider/asset integrations fail.

---

# 17. COMMIT-BY-COMMIT BUILD PLAN — BRICK BY BRICK

The following are **proposed commit checkpoint names**. Adapt their granularity to actual repository structure and existing implementation. A checkpoint is complete only after relevant automated tests and a working application are preserved.

## Phase A — Foundation and compatibility

1. `docs(geoscene): audit map implementation and record rendering ADR`
2. `chore(geoscene): pin compatible map and rendering dependencies`
3. `feat(geoscene): introduce versioned scene and entity contracts`
4. `test(geoscene): add synthetic world and golden pose fixtures`
5. `feat(geoscene): implement shared scene selection context`
6. `feat(map): integrate MapLibre and deck overlay foundation`
7. `test(map): validate layer mounting picking and world revision`

**Gate A:** Existing TrossOps runs; an integrated map renders sources from typed fixtures; no lost backend capabilities.

## Phase B — Visual baseline and cartography

8. `feat(map): add premium operational dark basemap`
9. `feat(map): add satellite hybrid style and attribution`
10. `feat(map): add terrain hillshade and elevation fallback`
11. `feat(map): build typed layer registry and legends`
12. `feat(map): add accessible controls search and camera reset`
13. `test(map): validate style switching and offline fallback`

**Gate B:** The map itself looks professional, supports styles and controls, and remains useful offline.

## Phase C — GPU entities and 3D assets

14. `feat(entities): add domain-to-geoscene entity adapter`
15. `feat(assets): introduce glb manifest and licensed model catalogue`
16. `feat(entities): render oriented gpu asset silhouettes`
17. `feat(entities): add selected scenegraph and mesh rendering`
18. `feat(entities): implement density-aware lod and clustering`
19. `feat(entities): add labels collision and source-status styles`
20. `test(entities): verify model axes scale picking and lod`
21. `perf(entities): cache geometry and reduce draw calls`

**Gate C:** Type-specific moving assets are recognizable; broad scenes are responsive; close selection shows 3D model.

## Phase D — Time, pose and camera

22. `feat(time): implement entity sample buffers and scene clock`
23. `feat(time): implement geodetic interpolation and attitude handling`
24. `feat(tracks): show trails planned paths and stale data`
25. `feat(replay): add timeline controls and event seeking`
26. `feat(camera): add fly-to fit follow and overview presets`
27. `feat(camera): add orbit inspection and reduced-motion handling`
28. `test(time): verify deterministic replay and no false extrapolation`

**Gate D:** Motion reflects timestamps, paths and class semantics; camera behavior feels refined.

## Phase E — Product integration

29. `feat(scene-api): expose versioned snapshots and viewport queries`
30. `feat(realtime): connect authoritative projections and delta updates`
31. `feat(inspector): link asset history maintenance and evidence`
32. `feat(layers): add facility incidents and operational areas`
33. `feat(intelligence): render computed capability and dependency overlays`
34. `feat(scenarios): render branches and hypothetical proposals`
35. `test(geoscene): verify cross-tab selection and revision consistency`

**Gate E:** Real internal event → map state → linked enterprise and computed consequence, without hardcoded visual claims.

## Phase F — Deep geo/immersion

36. `feat(terrain): refine lighting 3d buildings and scene depth`
37. `feat(immersive): add feature-flagged Cesium viewer`
38. `feat(immersive): share entity time and camera intent adapters`
39. `feat(immersive): add terrain and gltf models`
40. `feat(immersive): add available licensed 3d tiles`
41. `test(immersive): verify altitude axes and viewer lifecycle`
42. `perf(immersive): tune tile detail model lod and memory`

**Gate F:** Immersive mode uses the **same world** as Operations and can be disabled cleanly without breaking primary mode.

## Phase G — Reliability and presentation

43. `feat(map): add responsive workstation panel composition`
44. `feat(map): add professional scene presets and saved views`
45. `test(e2e): cover entity select fault replay and scenario fork`
46. `test(e2e): cover offline fallback mobile and renderer switch`
47. `perf(geoscene): profile dense fleet scenarios and tune budgets`
48. `fix(geoscene): resolve lifecycle loading and consistency defects`
49. `docs(geoscene): publish asset attribution and integration guide`
50. `docs(demo): add reproducible geospatial demo walkthrough`
51. `chore(release): freeze verified scene build and benchmarks`

**Gate G:** Consistent, measured, rehearsable product; project still builds/runs from a clean checkout.

**Policy:** A named commit is earned by a verified increment. Do not create empty commits purely to satisfy a count, and do not squash away useful integration milestones if the project's workflow supports preserving them.

---
# 18. INTEGRATION HANDOFF — NO VAGUE "COMING SOON"

If any capability cannot be completed, create a **working extension seam** and an explicit integration note. A route or button should never imply functionality that is unavailable.

Maintain `docs/geospatial/integration-matrix.md`:

| Integration | Required contract | Live verification | Honest fallback |
|---|---|---|---|
| Operations assets | Scene snapshot/entities/track API | Selection opens matching domain asset | Labeled synthetic fixture |
| Maintain/repair ERP | Authorized maintenance/asset API | Open real internal work order via ID | Read-only context / adapter-not-connected |
| Inventory/logistics | Reserved stock/transfer API | Resource state changes are visible via projection | Scenario-only proposal |
| NATS events | Validated event stream with revision | Event reaches projection idempotently | Local deterministic event source |
| SpacetimeDB | Subscribed scene read model | Browser sees real projection changes | SSE or snapshot polling |
| Capability engine | Impact/feasibility API | Golden case changes computed overlay | Overlay disabled with explanation |
| Scenario engine | Branch/seek/compare API | Branch B does not change A | Replay-only mode |
| Cesium | Scene adapter + terrain/tile contract | Model and time agree with primary map | 2D/2.5D primary scene |
| GLB library | Asset catalogue + license manifest | Selected model loads in production build | Correct 2D silhouette |
| Offline basemap | Permitted tile package + manifest | Works without third-party network | Clearly bounded local demo geography |
| ROS 2/PX4 | Authorized telemetry adapter | Tested SITL/physical feed indicated explicitly | Synthetic test adapter |
| External geospatial layers | OGC/GeoJSON + access controls | Verified provider data and CRS | Bundled sample GeoJSON |
| External media | Event/video ID linkage | Actual authorized stream | Labeled prerecorded sample |

For every incomplete integration, create a compact handoff containing:

```text
Feature:
Current status:
Files/modules already implemented:
Stable types and endpoints:
Expected upstream source:
Expected downstream consumer:
Known dependencies and credentials:
Steps to complete:
Minimum test and acceptance command:
Observed blocking error or missing permission:
Working fallback:
Security/licensing notes:
```

Do not list an integration as working because the adapter initializes. A real source-to-render test is required.

---

# 19. DOCUMENTATION AND DELIVERY ARTIFACTS

Required, adapted to existing docs layout:

1. `docs/geospatial/baseline.md` — current repo state, migration constraints and browser baseline.
2. `docs/decisions/ADR-*-geospatial-renderers.md` — MapLibre/deck primary, Cesium conditional, and deviations justified.
3. `docs/geospatial/architecture.md` — scene data flow, authority boundaries, time semantics, rendering pipeline and diagrams.
4. `docs/geospatial/assets.md` — actual asset manifest, source/license attribution, axis/scale and optimization commands.
5. `docs/geospatial/styles.md` — basemap sources, licenses, allowed distribution, offline bundle and visual semantics.
6. `docs/geospatial/api-contracts.md` — routes, status, request IDs, world revisions, errors and client types.
7. `docs/geospatial/performance.md` — devices, benchmarks, frame timings, model/layer loads, remaining limits.
8. `docs/geospatial/verification.md` — executed tests, results, browser traces, regressions and known failures.
9. `docs/geospatial/integration-matrix.md` — working/partial/blocked/planned plus completion steps.
10. `docs/geospatial/demo.md` — exact scenario seed, command sequence, optional live audiences changes, fallback choreography.
11. Repo instructions and READMEs updated to show clean startup, `Docker Compose` setup, environment example, data import, map styles and optional API/tile keys.

Provide a few representative screenshots or recordings when available, with actual files and commands to reproduce them. Do not manufacture comparison screenshots.

### Reproducible setup

The final user should be able to follow concise commands equivalent to:

```text
1. Clone repository.
2. Install locked dependencies.
3. Configure non-secret demo environment.
4. Start backend/database/services as actually needed.
5. Import/init synthetic world.
6. Start frontend.
7. Open Operations.
8. Play verified demonstration scenario.
9. Run contract/unit/E2E/performance smoke tests.
```

These are steps, not yet-verified actual commands. Supply the repository's real commands after implementing them. `next build` success alone does not establish a working map.

---

# 20. FINAL DEFINITION OF DONE

The geospatial initiative is successful when the following are **actually true and tested**:

### Product / appearance

- [ ] Operations opens as a polished, map-dominant, responsive workstation with clean title and no decorative page subtext.
- [ ] At least one custom-styled, legally sourced operational basemap is working; attribution is correct.
- [ ] A useful offline/degraded geospatial mode is available.
- [ ] Assets of several distinct classes render as recognizable directional silhouettes or models.
- [ ] Selected close-range assets render with optimized actual 3D geometry where data/model is available.
- [ ] Terrain/buildings provide genuine geographic depth where source coverage allows it.
- [ ] Labels, categories, selected and stale states remain legible with dense entity sets.
- [ ] The map has meaningful layer controls, time controls, inspector, search and camera presets.

### Interaction / correctness

- [ ] Entity IDs are stable across LOD, style switches and 2D/3D mode changes.
- [ ] Motion derives from time-indexed samples, with correct source and altitude semantics.
- [ ] Tracks handle gaps, time scrubbing and staleness without deceptive extrapolation.
- [ ] The selected entity links to actual TrossOps asset/evidence/maintenance records or clearly declared mock adapters.
- [ ] Incident and service overlays have source/revision metadata and truthful interpretations.
- [ ] Scenario branch positions/results come from actual scenario state; parent remains unmodified.
- [ ] Map, intelligence and sustainment views agree on scenario and world revision.
- [ ] The application can handle at least one unplanned but supported synthetic event correctly.

### Engineering / integration

- [ ] API schemas/types are generated or maintained through one validated authority.
- [ ] Source-of-truth database, projection layer and render buffer boundaries are documented and enforced.
- [ ] No plaintext secrets or unauthorized external mapping assets are committed.
- [ ] Model asset licenses and attribution are documented.
- [ ] Relevant unit, contract, browser and scenario tests have been **run** and results recorded.
- [ ] Frame time, large-scene performance and GPU viewer lifecycle have been profiled with actual measurements.
- [ ] Code runs from clean setup; frontend gracefully degrades without optional Cesium, AI, telemetry or commercial tiles.
- [ ] Multiple meaningful `feat`, `test`, `fix`, `perf`, and `docs` commits/checkpoints exist and preserve a working application.
- [ ] Integration matrix truthfully identifies finished and unfinished components, with exact next steps.

### Conditional / stretch

- [ ] Cesium 3D inspection uses the same IDs/time/scenarios and proper altitude reference, if implemented.
- [ ] 3D Tiles are licensed, covered in the actual test area and loaded progressively, if implemented.
- [ ] External telemetry, ERP, OGC, robotics or media streams are connected and tested, **only if authorized**.
- [ ] Multi-user live scene projections remain revision-consistent, if SpacetimeDB is enabled.

Do not silently mark conditional items complete if they were not attempted or could not be verified.

---

# 21. PRIMARY DOCUMENTATION STARTING POINTS

These are relevant official documentation starting points. They are **not a claim that live compatibility was verified when this brief was written**; inspect the current documentation and the repository's pinned versions during implementation.

| Project | Documentation |
|---|---|
| MapLibre GL JS | https://maplibre.org/maplibre-gl-js/docs/ |
| MapLibre examples | https://maplibre.org/maplibre-gl-js/docs/examples/ |
| deck.gl | https://deck.gl/docs/ |
| deck.gl / MapLibre | https://deck.gl/docs/developer-guide/base-maps/using-with-maplibre |
| deck.gl ScenegraphLayer | https://deck.gl/docs/api-reference/mesh-layers/scenegraph-layer |
| deck.gl SimpleMeshLayer | https://deck.gl/docs/api-reference/mesh-layers/simple-mesh-layer |
| deck.gl TripsLayer | https://deck.gl/docs/api-reference/geo-layers/trips-layer |
| deck.gl performance | https://deck.gl/docs/developer-guide/performance |
| CesiumJS | https://cesium.com/learn/cesiumjs-learn/ |
| 3D Tiles standard | https://www.ogc.org/standard/3dtiles/ |
| glTF Transform | https://gltf-transform.dev/ |
| Three.js | https://threejs.org/docs/ |
| PMTiles / MapLibre | https://docs.protomaps.com/pmtiles/maplibre |
| PostGIS | https://postgis.net/documentation/ |
| H3 | https://h3geo.org/docs/ |
| SpacetimeDB | https://spacetimedb.com/docs/ |
| NATS JetStream | https://docs.nats.io/nats-concepts/jetstream |
| Next.js | https://nextjs.org/docs |
| FastAPI | https://fastapi.tiangolo.com/ |
| Playwright | https://playwright.dev/docs/intro |
| OpenTelemetry | https://opentelemetry.io/docs/ |

Prefer official provider docs, explicit license files and locally executed compatibility spikes to third-party copy-pasted snippets. Use current stable releases compatible with the repo, not unreviewed prereleases merely to gain an experimental feature.

---

# 22. MANDATORY FINAL REPORT FROM THE IMPLEMENTING AGENT

End implementation with a concise, evidence-based report in this exact order:

1. **Delivered:** What is genuinely working and demonstrable.
2. **Renderer decision:** MapLibre/deck/Cesium/alternative, versions and why; any ADRs.
3. **Operations demo:** Scenario, meaningful user path, commands to run, actual screenshots/trace paths.
4. **Integrations:** Which real or simulated backend/projection/ERP/analysis/data services were tested end to end.
5. **Performance:** Device, browser, resolution, entity counts, FPS/frame timing and known bottlenecks; no guessed numbers.
6. **Verification:** Tests executed, pass/fail/blocked counts, regression status and critical defects.
7. **Commits:** Chronological checkpoint commits with hashes and short purpose.
8. **Missing/partial:** Exact technical blockers and integration-ready steps; no vague placeholders.
9. **How to run:** Actual reproducible install/start/seed/demo commands.
10. **Recommendation:** The next highest-value engineering increment based on evidence, not untested ambition.

# FINAL OPERATING INSTRUCTION

Do not stop with a design document, initial asset gallery or visually improved marker map. **Implement the real geospatial subsystem**, build it step by step, inspect the results in a browser, commit working increments, and progressively connect it to the shared TrossOps world.

Your target experience is precise: **a premium operational map where actual rendered entities move coherently through geographic space and time, their condition and evidence are inspectable, operational dependencies can be revealed spatially, simulations can be compared, and a separate 3D mode can inspect the same world when supported**.

Prioritize genuine cross-system function and elegant usability over decoration. If the optimal architecture differs from this one, exercise engineering judgment and document why. If any integration cannot be finished, leave the strongest possible working foundation and a complete, testable handoff.
