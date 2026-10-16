# Basemaps, geography and assets

| Mode | Source | Licence / terms | Status |
|---|---|---|---|
| Dark (default) | [OpenFreeMap](https://openfreemap.org) `styles/dark` (OpenMapTiles schema, OpenStreetMap data) | Free, key-less, attribution shown; no SLA | working online; falls back to Offline when the style cannot load |
| Imagery | [EOX Sentinel-2 cloudless 2023](https://s2maps.eu) WMTS | CC BY-NC-SA 4.0, contains modified Copernicus Sentinel data; attribution shown; non-commercial use | working online (raster), county outlines overlaid |
| Offline | Bundled SCB county polygons as land, no tiles | SCB digital boundaries, CC0 | working with no network at all |
| Terrain | [Mapterhorn](https://mapterhorn.com) elevation TileJSON, hillshade | open data, attribution from TileJSON | working online (Dark/Imagery) |
| 3D buildings | OpenFreeMap vector tiles, `building` layer, `render_height` | as Dark | working online in 3D above zoom 14 |
| County boundaries | `frontend/public/data/sweden_counties.geojson` (21 counties, WGS84, simplified by SCB for thematic display) | CC0 | working |
| Weather | SMHI SNOW1G point forecasts, seven public city points | public open data; forecast, not observation | `connected` when SMHI answers, otherwise `unavailable` with the reason |

No basemap tiles are bundled. Labels and cluster counts are rendered from client-generated images, so every mode has identical typography and the offline mode needs no glyph server.

## Icons and models

All silhouettes (`frontend/src/scene/semantics.ts`) and 3D classes (`frontend/src/scene/models3d.ts`) are drawn in code. Classes: fighter, transport, ISR, helicopter, multirotor, tank, APC, truck, fuel, ambulance, engineer, air defence, recovery, command post, signals, personnel, corvette, patrol boat, logistics ship, mine countermeasure, icebreaker, ferry, unknown air, unknown sea, and site glyphs (HQ, garrison, airfield, naval base, depot, hospital, sensor, comms, grid, port, crossing, telecom). Models are nose-north before the heading rotation, metre-scaled, and never smaller than 34 px on screen (a declared visual exaggeration below the zoom where true scale is legible).

## Visual grammar

- Own: light fill, dark outline. Allied: sage. Civil: grey. Unknown: hollow orchid diamond with a question mark.
- Degraded: amber ring. Unavailable: red ring and strike. Stale: 45 % opacity, frozen.
- Selected: blue halo. Hovered: light halo.
- Predicted: dashed orchid line with an uncertainty wedge. Planned: dotted grey line. Trails: fading white line, last 20 minutes.
- Areas: covered blue, degraded amber, uncovered red; restricted zones dashed; coverage models dotted.
- Attention: orange→red heatmap (2D) or extruded columns (3D) with a legend stating the unit and peak.
