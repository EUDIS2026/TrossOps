# Geospatial routing data (`backend/data/geo/`)

Artefacts that keep ground vehicles on real roads, police cars on real city streets and ships in real
water. They are consumed by `backend/app/geonet.py` (standard library only) and built by
`scripts/data/build_geonet.py`.

| File | What | Size |
|---|---|---|
| `national.json.gz` | National road graph: motorway, trunk, primary, secondary, tertiary (OMT z11) | 2.7 MB |
| `city_<name>.json.gz` × 20 | City street graphs: motorway … minor (incl. residential), z14 | 1.4 MB total (Stockholm 0.46 MB) |
| `city_gotland.json.gz` | Region graph for the whole of Gotland incl. Fårö (minor and up, plus the Fårösund ferry), z13 | 0.15 MB |
| `sea.bin` | Sea mask (~280 m) + navigable routing grid (~560 m) | 0.2 MB |
| `land.bin` | Land/water mask incl. lakes and rivers (~110 m), for placement | 1.2 MB |

Total ≈ 4.5 MB. Region graphs load through `geonet.city(name)` and are listed by `geonet.cities()` like the cities.

## Provenance and licence

* **Roads and water:** OpenFreeMap vector tiles, OpenMapTiles schema, planet build
  `20261011_080001_pt` (recorded in each file's `source`). Data © OpenStreetMap contributors,
  licensed under the **Open Database License (ODbL) 1.0**. The derived graphs are a
  *Derivative Database* under the ODbL: attribution "© OpenStreetMap contributors" must be shown
  wherever routes derived from them are displayed (the basemap attribution already covers this),
  and the derived database must remain available under the ODbL.
  Layers used: `transportation` (`class`, `oneway`, `access`) and `water` (`class` = `ocean`, `river`).
* **Sweden footprint:** `frontend/public/data/sweden_counties.geojson` (SCB county borders, CC0),
  used only to select which tiles to fetch.
* These are **public datasets**. Nothing here is a military location; operational entities that
  move along these networks remain synthetic.

## Reproduce

```sh
pip install -r scripts/data/requirements.txt        # httpx only (already a backend dependency)
python -I scripts/data/build_geonet.py --cache <dir outside the repo>
# subsets: --steps national,cities,regions,sea  --cities stockholm,visby,gotland
```

* About 19,000 tiles (national z11: 6,276; cities z14: 2,991; Gotland z13: 1,457; sea z10: 4,320), about 370 MB on disk.
  A cold run takes about 6 minutes on a fast connection, and a cached rerun about 2 minutes.
* Polite fetching: at most 6 concurrent requests, User-Agent `TrossOps-databuild/1.0 (research demo)`,
  every tile is cached on disk under `<cache>/tiles/<planet version>/z/x/y.pbf` and never refetched.
  The TileJSON is cached too, so reruns are pinned to the same planet build. Delete
  `<cache>/tilejson.json` to move to a newer build.
* The downloaded tiles are untrusted input. The protobuf/MVT decoder is a small pure-Python
  implementation inside the build script that raises on malformed data. Run the build with `python -I`.
  The script refuses a cache directory inside the repository.
* `GEONET_DEBUG=1` logs where the largest dropped components are.

## How the graphs are built

1. Decode `transportation` lines of the wanted classes. Features with `access` = `no`/`private` are skipped.
2. **Clip every line to its own tile square** (MVT tiles carry a 64-unit buffer, so unclipped
   geometry would duplicate segments). All work is in global tile-pixel coordinates at the build
   zoom (`x = tile_x * 4096 + local_x`), so identical OSM vertices from different tiles coincide exactly.
3. **Seams:** clip points on the same tile boundary line within ~1.5 units (≈ 3.5 m at z11,
   ≈ 0.5 m at z14) are merged.
4. **Junctions** come only from shared vertices. Roads crossing on bridges or in tunnels share
   no vertex, so they are not connected. Low-zoom simplification sometimes drops the junction vertex
   from the through road, so a dangling line end lying within that tolerance of another segment's
   interior is spliced into it (21k such T-junctions nationally; this only ever joins a line *end*,
   so over/underpasses stay separate).
5. Degree-2 vertices are collapsed into edge shapes, splitting wherever class or one-way changes.
   Shapes are Douglas-Peucker simplified (national 2 m, cities 0.7 m).
6. Keep the largest **strongly** connected component (cities have `oneway` from z14). City graphs
   are built from tiles covering `r + max(1.5 km, 0.3 r)` so connections through the outskirts
   count, then cropped to edges touching the radius-`r` circle and reduced to the largest SCC again.

### Zoom choices

Measured against z14 geometry (Stockholm sample, motorway..secondary vertices to the low-zoom line):

| zoom | median | p99 / max deviation | tiles for Sweden |
|---|---|---|---|
| z9 | 2.6–4.5 m | 18 / 19 m | 455 |
| z10 | 1.6–2.6 m | 8.5 / 9 m | 1,649 |
| **z11** | **0.7–0.9 m** | **4.6 / 5.7 m** | **6,276** |
| z12 | 0.3–0.4 m | 2.0 / 2.2 m | ≈25,000 |

**National = z11.** Vehicles are drawn on the OpenFreeMap basemap at up to z15 (≈2.4 m/px at
60° N). At z11 the worst-case offset (~5 m, 2 px) stays inside the drawn road casing, while z10's
9 m is visible. Tertiary roads first appear at z11 and the whole graph is only 2.7 MB, so they are
included (68,000 km of the 115,000 km total). z12 would quadruple the downloads for an
invisible gain. **Cities = z14** (full detail, includes `minor` and one-way).
**Sea = z10** water polygons, much finer than the 280 m raster.

### Graph statistics

National (z11): 65,272 nodes, 92,743 edges, 669,769 shape points, 114,778 km
(motorway 5,347 · trunk 9,702 · primary 10,214 · secondary 21,177 · tertiary 68,338 km).
Before component filtering there were 314 components. The largest keeps 97.7 % of the length; the
rest is islands without fixed links (Gotland, small archipelago islands; Öland is connected by its bridge) and
fragments at the tile-selection border in Norway and Finland. No one-way information exists at z11
(see limitations).

| city | r km | nodes | edges | one-way edges | km | length kept | KB |
|---|---|---|---|---|---|---|---|
| boden | 3 | 737 | 965 | 71 | 166 | 96.9% | 15 |
| gavle | 4 | 1742 | 2331 | 417 | 336 | 90.0% | 33 |
| goteborg | 10 | 12479 | 15783 | 4308 | 2007 | 94.1% | 229 |
| helsingborg | 5 | 2402 | 3226 | 797 | 401 | 92.7% | 41 |
| jonkoping | 5 | 2079 | 2706 | 553 | 383 | 89.7% | 41 |
| kalmar | 4 | 992 | 1388 | 366 | 173 | 94.6% | 17 |
| karlskrona | 4 | 603 | 782 | 131 | 91 | 78.8% | 11 |
| kiruna | 3 | 534 | 704 | 71 | 105 | 98.4% | 11 |
| linkoping | 5 | 3122 | 4062 | 1072 | 473 | 85.1% | 53 |
| lulea | 5 | 1526 | 2033 | 428 | 340 | 91.2% | 34 |
| malmo | 8 | 5726 | 7696 | 1891 | 1100 | 92.9% | 98 |
| norrkoping | 5 | 2656 | 3574 | 793 | 507 | 94.5% | 51 |
| orebro | 5 | 2749 | 3679 | 902 | 505 | 94.4% | 52 |
| ostersund | 4 | 1175 | 1604 | 282 | 239 | 93.4% | 22 |
| stockholm | 14 | 25525 | 33019 | 6689 | 4194 | 95.0% | 461 |
| sundsvall | 4 | 1516 | 2084 | 514 | 271 | 90.4% | 30 |
| umea | 5 | 1903 | 2644 | 473 | 434 | 94.7% | 39 |
| uppsala | 6 | 3058 | 4091 | 876 | 581 | 94.3% | 56 |
| vasteras | 5 | 3228 | 4222 | 997 | 526 | 93.9% | 58 |
| visby | 3 | 974 | 1338 | 208 | 144 | 95.3% | 17 |
| **gotland** (region, z13) | bbox 18.05–19.35, 56.88–57.98 | 5001 | 6238 | 248 | 3114 | 98.0% | 146 |

**Gotland region graph.** It covers the whole island bbox, so there is no crop circle, and it is
built at **z13** rather than z14. Minor roads are already present at z13, which needs 1,457 tiles
instead of 5,640 (most of the bbox is sea) for about 1 m less fidelity. It holds 3,114 km of road
(secondary 429, tertiary 1,068, minor 1,614 km). The **Fårösund ferry** (class `ferry`, 2.6 km of
line, 4 m/s at runtime) is the only link to Fårö:

* Ferry line ends join the road graph through shared vertices, or a connector to the nearest road
  within 300 m.
* Ferry spurs that still dead-end, such as the Visby–mainland lines clipped at the region edge, are
  pruned.
* `random_loop` rarely takes the ferry (weight ×0.05).
* Gotland's one-way information is sparse at z13: 248 edges, mostly roundabouts and Visby streets.

Dropped city length is mostly streets reachable only via excluded `service` roads, private or
`access=no` areas (Karlskrona's naval base and islands), and one-way stubs at the crop edge.

## File formats

### Road graphs (`*.json.gz`, gzip JSON)

```jsonc
{
  "version": 1, "kind": "roadnet", "name": "national", "zoom": 11,
  "source": "OpenFreeMap <planet build> transportation z11", "licence": "ODbL …", "scale": 100000,
  "classes": ["motorway", "trunk", "primary", "secondary", "tertiary"],   // class index -> name
  "bbox": [minLng, minLat, maxLng, maxLat],
  "nodes":   [x0, y0, dx1, dy1, …],      // integer 1e-5 degrees, delta-coded in Morton order
  "edges":   [a, b, flags, len_dm, …],   // 4 ints per edge; flags = classIdx | oneway << 4
  "shape_n": [n, …],                     // interior shape points per edge
  "shape":   [dx, dy, …],                // per edge: first point relative to node a, then to previous
  "stats":   {…}                         // build statistics (see above)
}
```

* `oneway = 1` means the edge may be travelled a→b only. One-way edges are stored in their
  allowed direction.
* `len_dm` is the polyline length in decimetres, computed from the stored (rounded) geometry, so
  route lengths equal the drawn polyline length.
* Coordinates are rounded to 5 decimals (≈ 1 m).

### Sea grid (`sea.bin`)

`b"TROSSEA1"`, then a uint32 LE header length, then the UTF-8 JSON header, then two zlib blocks:

1. **Fine water mask**: 4200 × 4960 cells of 0.005° lng × 0.0025° lat (~280 m) over
   lng 9.5–30.5, lat 53.8–66.2. Rows run from the north, bits are LSB-first, and 1 = sea. Sea means
   OSM `ocean` polygons (from the OSM coastline), plus `river` polygons connected to the sea for up
   to 60 cells (~17 km, e.g. Göta älv through Göteborg). Lakes (Vänern, Vättern, Mälaren) are land.
2. **Routing grid**: 2100 × 2480 bytes (~560 m). A cell is navigable only if all 4 fine cells are
   water and it is in the main 8-connected sea component. Values: 0 = not navigable,
   1 = open water, 2 = two cells from land, 3 = adjacent to land (cost ×1, ×1.15 and ×1.6).

### Land mask (`land.bin`, step `land`)

`b"TROSLND1"`, then a uint32 LE header length, the UTF-8 JSON header, and two zlib bit arrays of 7000 × 14200 cells
(0.002° lng × 0.001° lat, ~110 m north-south) over lng 10.4–24.4, lat 55.0–69.2, rows from the north, LSB-first:

1. **Water**: 1 where the cell centre lies inside any z11 OSM `water` polygon of class `ocean`, `lake`, `river`,
   `pond` or `dock` (intermittent water excluded).
2. **Known**: 1 where a fetched Sweden tile (8 km buffer) covers the cell. Elsewhere the runtime falls back to the
   sea mask.

`geonet.land()` uses it to keep every site footprint, parked unit and off-road leg on dry ground
(`is_dry`, `nearest_dry`, `candidates`), and rasterises the road graphs onto the same grid (`road_cells`, ~4 s,
only when a placement is not already in `world_routes.json.gz`) so buildings are not placed on roads.

## Runtime behaviour (`backend/app/geonet.py`)

* **Roads:** A* on travel time with military-convoy class speeds (motorway 25, trunk 22,
  primary 19, secondary 16, tertiary 13, minor 9, service 6 m/s), optionally capped by
  `max_speed_mps`. Each edge touching an `avoid` polygon costs ×1000 + 1 h, so it is used only when
  there is no way around. Start and end join the nearest node with straight access legs at 5 m/s,
  reported as `classes_m["access"]`, only where the leg crosses dry ground (`access="dry"`, the default);
  `access="none"` starts and ends on the network (marching columns). Output polylines are densified to ≤ 1 km spacing.
* **`random_loop`:** a seeded random walk that prefers unvisited edges, avoids U-turns and favours
  going straight on. It stops once the walked distance plus 1.3 × the straight distance home reaches
  `length_m`, then takes the fastest path back. The loop starts and ends at the node nearest the start
  (no access legs), and is closed and deterministic for the same seed, start and length.
* **`nodes_within`:** junctions and shape vertices within a radius, nearest first, optionally
  filtered by class. The first call builds a vertex index (~0.7 s for the national graph).
* **Sea:** 8-connected A* (weight 1.25, no corner cutting) on the routing grid, with land-proximity
  penalties, then line-of-sight string pulling (exact grid traversal) so tracks are straight legs
  rather than staircases.
  * Endpoints that are not in open water reach it by a fine-grid (280 m) search through channels:
    harbours, archipelagos, river ports.
  * A point on land first takes a short straight leg (≤ 3 km) to nearby water, falling back to the
    nearest navigable cell within 30 km.
  * `snapped` is true when an overland leg was used.
  * `duration_s` assumes 1 m/s; scale it by the vessel speed.

Measured on the development machine (CPython 3.12, Windows 11): module import 0.06 s; `national()`
first load 0.27 s; Stockholm→Uppsala 0.05 s; Malmö→Kiruna (1,843 km) 0.14 s; Stockholm city load
0.09 s; `sea()` load 0.01 s; Karlskrona→Luleå sea 0.10 s; Göteborg→Stockholm sea (889 km) 0.84 s.

## Limitations

* **No one-way information in the national graph** (OMT drops `oneway` below z14). Dual
  carriageways are separate lines, so a convoy may be drawn on the opposite carriageway, about
  10–20 m off. City graphs do respect one-way streets.
* **Ferries are not modelled in the national graph.** Gotland and other islands without fixed links
  are outside its main component, and a `national().route()` from Visby would start with a long
  straight access leg. For anything on Gotland use `city("gotland")` (or `city("visby")`). The
  Fårösund ferry exists only in the Gotland region graph, and its duration ignores waiting time.
* **Canals and locks are not modelled.** Göta kanal, Södertälje kanal, Trollhätte kanal, Mälaren
  and the large lakes are not reachable by sea routing.
* Sea channels narrower than ~280 m can be missed by the fine mask. Narrow archipelago passages
  below ~560 m are followed only near endpoints, not mid-route.
* Speeds are class-based and ignore real speed limits, gradients, bridge weight limits and seasonal
  closures.
* `nearest_node` snaps to junctions or ends, not to the nearest point on an edge, so an access leg
  can cut a corner of up to a few hundred metres in sparse rural areas.
