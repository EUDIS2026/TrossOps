# ADR-001: Renderer — MapLibre GL JS 6 native layers plus two custom WebGL layers, no deck.gl

Status: accepted, 16 October 2026.

## Context

The brief proposes MapLibre + deck.gl (`MapLibreOverlay`) as the primary stack and Cesium as an optional immersive mode. The product needs: clusters that open by level, heading-aware unit symbols that move smoothly at display rate, an attention surface in 2D and 3D, terrain, 3D buildings, labels with collision handling, exact picking, and a very small dependency surface that installs and builds in one step.

## Decision

- **MapLibre GL JS 6.14** owns the camera, basemaps, terrain, globe, clustering, label collision, fills, lines, heatmap, extrusions and picking of static geometry.
- **Two custom layers** written against MapLibre's `CustomLayerInterface`:
  - `unit-sprites` (2D): instanced, heading-rotated billboards of the same icon images the symbol layer uses, fed directly from interpolated poses every frame. MapLibre re-tiles a GeoJSON source on every `setData`, which cannot follow per-frame motion and starves picking; the symbol source is therefore refreshed at 2 Hz (labels, clusters, fallback picking) while the sprite layer is exact.
  - `entity-models` (3D): procedural, metre-scaled low-poly classes (tank, APC, trucks, fighter, transport, ISR, helicopter, multirotor, vessels, personnel, unknown air/sea) with simple lighting, shared depth with terrain and buildings, altitude honoured (MSL for aircraft, ground-clamped otherwise) and a minimum on-screen size so a 10 m tank stays legible at zoom 13.
- **No deck.gl.** It would duplicate what MapLibre 6 now does natively, add ~1.5 MB and three dependency families, and its overlay cannot drape onto MapLibre terrain. **No Cesium** in this increment: the 3D need (columns, models at altitude, terrain, buildings) is met inside one renderer with one camera and one selection; a Cesium viewer remains a documented, feature-flagged seam (see integration matrix).
- **No third-party 3D assets.** All geometry is generated in code; no licensing exposure and no download at runtime.

## Consequences

- One WebGL context, one camera, one selection model across 2D and 3D. Switching modes never loses selection, time or layers.
- The sprite layer draws viewport-aligned billboards rotated by heading minus bearing; under pitch the brief's "true" map-aligned foreshortening is not applied — models take over above zoom 13 where it would matter.
- Labels lag the sprite by at most 500 ms of motion at display scale (sub-pixel below zoom 14 for ground units).
- Offline mode has no glyph server, so labels and cluster counts are baked into images on the client (`drawLabel`), which also keeps typography identical across basemaps.
