"""Geospatial routing networks: real roads for ground units, real water for ships.

Data artefacts live in backend/data/geo/ and are produced by scripts/data/build_geonet.py
from OpenFreeMap vector tiles (OpenMapTiles schema, ODbL (c) OpenStreetMap contributors).
See scripts/data/README.md for provenance, file format and how to rebuild.

Everything loads lazily on first use and is cached as a process-wide singleton:

    from app import geonet
    r = geonet.national().route((18.07, 59.33), (17.64, 59.86))
    loop = geonet.city("stockholm").random_loop(seed=1, start=(18.07, 59.33), length_m=8000)
    s = geonet.sea().route((15.59, 56.16), (18.29, 57.64))

Coordinates are (longitude, latitude) degrees, distances metres, durations seconds.
Standard library only.
"""
from __future__ import annotations

import gzip
import heapq
import json
import math
import random
import struct
import threading
import zlib
from dataclasses import dataclass, field
from itertools import accumulate
from pathlib import Path

LngLat = tuple[float, float]

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "geo"
EARTH_RADIUS_M = 6_371_008.8
M_PER_DEG = math.pi * EARTH_RADIUS_M / 180.0  # ~111 195 m per degree of latitude

# Military convoy speeds per road class (m/s).
CLASS_SPEED_MPS: dict[str, float] = {
    "motorway": 25.0, "trunk": 22.0, "primary": 19.0, "secondary": 16.0,
    "tertiary": 13.0, "minor": 9.0, "service": 6.0,
    "ferry": 4.0,  # short car ferries in region graphs (e.g. Farosund on Gotland), crossing only
}
ACCESS_SPEED_MPS = 5.0  # straight off-network legs to/from the nearest node
AVOID_FACTOR = 1000.0  # travel-time multiplier for edges touching an avoid polygon
SEA_SNAP_M = 30_000.0  # max distance from a port/base to navigable water
SEA_SPEED_MPS = 1.0  # sea routes report duration_s at 1 m/s; callers scale by vessel speed
MAX_SEGMENT_M = 1000.0  # output polylines are densified to at most this spacing


@dataclass
class Route:
    coords: list[LngLat]  # full polyline including access legs, first = start, last = end
    length_m: float
    duration_s: float
    classes_m: dict[str, float] = field(default_factory=dict)  # metres per road class (+ "access" / "sea")
    snapped: bool = False  # True when start/end were connected to the network by access legs


def haversine_m(a: LngLat, b: LngLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def _fast_m(ax: float, ay: float, bx: float, by: float) -> float:
    """Equirectangular distance in metres; accurate to <0.5% for the spans used here."""
    k = math.cos(math.radians((ay + by) * 0.5))
    return math.hypot((bx - ax) * k, by - ay) * M_PER_DEG


def _densify(coords: list[LngLat], max_m: float = MAX_SEGMENT_M) -> list[LngLat]:
    out: list[LngLat] = coords[:1]
    for i in range(1, len(coords)):
        (ax, ay), (bx, by) = coords[i - 1], coords[i]
        d = _fast_m(ax, ay, bx, by)
        if d > max_m:
            n = int(d // max_m) + 1
            for k in range(1, n):
                f = k / n
                out.append((round(ax + (bx - ax) * f, 6), round(ay + (by - ay) * f, 6)))
        out.append(coords[i])
    return out


def _polyline_m(coords: list[LngLat]) -> float:
    return sum(haversine_m(coords[i - 1], coords[i]) for i in range(1, len(coords)))


def _point_in_ring(x: float, y: float, ring: list[LngLat]) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _segments_cross(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


class _Avoid:
    """Avoid polygons with a per-edge verdict cache."""

    def __init__(self, polys: list[list[LngLat]]):
        self.polys = []
        for ring in polys:
            ring = [(float(p[0]), float(p[1])) for p in ring]
            if len(ring) >= 3:
                xs, ys = [p[0] for p in ring], [p[1] for p in ring]
                self.polys.append((min(xs), min(ys), max(xs), max(ys), ring))
        self.cache: dict[int, bool] = {}

    def hits(self, pts: list[LngLat]) -> bool:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        for (a, b, c, d, ring) in self.polys:
            if x1 < a or x0 > c or y1 < b or y0 > d:
                continue
            if any(_point_in_ring(x, y, ring) for x, y in pts):
                return True
            for i in range(len(pts) - 1):
                for k in range(len(ring)):
                    if _segments_cross(pts[i], pts[i + 1], ring[k - 1], ring[k]):
                        return True
        return False


class RoadNet:
    """Road graph with A* routing on convoy travel time."""

    def __init__(self, name: str, doc: dict):
        self.name = name
        self.classes: list[str] = list(doc["classes"])
        self.source: str = doc.get("source", "")
        self.licence: str = doc.get("licence", "")
        self.stats: dict = doc.get("stats", {})
        sc = float(doc.get("scale", 100000))
        self._bbox = tuple(doc["bbox"])
        nodes = doc["nodes"]
        self.x = [v / sc for v in accumulate(nodes[0::2])]
        self.y = [v / sc for v in accumulate(nodes[1::2])]
        e = doc["edges"]
        self.ea: list[int] = e[0::4]
        self.eb: list[int] = e[1::4]
        flags = e[2::4]
        self.ecls: list[int] = [f & 15 for f in flags]
        self.eoneway: list[int] = [f >> 4 for f in flags]
        self.elen: list[float] = [v / 10.0 for v in e[3::4]]
        self._shape_n: list[int] = doc["shape_n"]
        self._shape_off: list[int] = list(accumulate([0] + [2 * n for n in self._shape_n]))
        self._shape: list[int] = doc["shape"]
        self._scale = sc
        n = len(self.x)
        adj: list[list[tuple[int, int]]] = [[] for _ in range(n)]
        for i, (a, b, ow) in enumerate(zip(self.ea, self.eb, self.eoneway)):
            adj[a].append((b, i))  # forward: edge index i
            if not ow:
                adj[b].append((a, ~i))  # reverse traversal encoded as ~i
        self.adj = adj
        self._grid: dict[tuple[int, int], list[int]] | None = None
        self._vgrid: dict[tuple[int, int], list[tuple[float, float, int]]] | None = None
        self._lock = threading.Lock()

    # -- geometry helpers ------------------------------------------------------------
    def bounds(self) -> tuple[float, float, float, float]:
        """(min_lng, min_lat, max_lng, max_lat)."""
        return self._bbox  # type: ignore[return-value]

    def node(self, i: int) -> LngLat:
        return (self.x[i], self.y[i])

    @property
    def nodes(self) -> list[LngLat]:
        """All junction/end node coordinates (index = node id). Prefer nodes_within() for
        spatial queries; this is a full list copy."""
        return list(zip(self.x, self.y))

    def edge_coords(self, i: int) -> list[LngLat]:
        """Full polyline of edge i (or of its reverse traversal when i < 0, i.e. ~edge)."""
        rev = i < 0
        if rev:
            i = ~i
        a, b = self.ea[i], self.eb[i]
        sc = self._scale
        ax, ay = round(self.x[a] * sc), round(self.y[a] * sc)
        out = [(self.x[a], self.y[a])]
        o, n = self._shape_off[i], self._shape_n[i]
        sh = self._shape
        for k in range(n):
            ax += sh[o + 2 * k]
            ay += sh[o + 2 * k + 1]
            out.append((ax / sc, ay / sc))
        out.append((self.x[b], self.y[b]))
        if rev:
            out.reverse()
        return out

    _CELL = 0.01  # degrees latitude per index cell (lng cell = 2x)

    def _index(self) -> dict[tuple[int, int], list[int]]:
        if self._grid is None:
            with self._lock:
                if self._grid is None:
                    g: dict[tuple[int, int], list[int]] = {}
                    c = self._CELL
                    for i, (x, y) in enumerate(zip(self.x, self.y)):
                        g.setdefault((int(x // (2 * c)), int(y // c)), []).append(i)
                    self._grid = g
        return self._grid

    def nearest_node(self, p: LngLat) -> tuple[int, float]:
        """(node index, distance m) of the network node closest to p."""
        g = self._index()
        c = self._CELL
        px, py = float(p[0]), float(p[1])
        cx, cy = int(px // (2 * c)), int(py // c)
        cell_m = c * M_PER_DEG * max(0.2, math.cos(math.radians(min(85.0, abs(py) + 1.0))))
        best, bd = -1, float("inf")
        for r in range(0, 400):
            if best >= 0 and (r - 1) * cell_m > bd:
                break
            for ix in range(cx - r, cx + r + 1):
                for iy in (range(cy - r, cy + r + 1) if ix in (cx - r, cx + r) else (cy - r, cy + r)):
                    for i in g.get((ix, iy), ()):
                        d = _fast_m(px, py, self.x[i], self.y[i])
                        if d < bd or (d == bd and i < best):
                            best, bd = i, d
        if best < 0:  # far outside the network: brute force
            best = min(range(len(self.x)), key=lambda i: _fast_m(px, py, self.x[i], self.y[i]))
        return best, haversine_m(p, (self.x[best], self.y[best]))

    def nodes_within(self, center: LngLat, radius_m: float, classes: set[str] | None = None) -> list[LngLat]:
        """Road vertices (junctions and shape points) within radius_m of center, nearest first.
        `classes` restricts to vertices on edges of those road classes. Deterministic order."""
        if self._vgrid is None:
            with self._lock:
                if self._vgrid is None:
                    vg: dict[tuple[int, int], list[tuple[float, float, int]]] = {}
                    c = self._CELL
                    for i in range(len(self.ea)):
                        cls = self.ecls[i]
                        for x, y in self.edge_coords(i):
                            vg.setdefault((int(x // (2 * c)), int(y // c)), []).append((x, y, cls))
                    self._vgrid = vg
        want = None if classes is None else {i for i, c in enumerate(self.classes) if c in classes}
        c = self._CELL
        px, py = float(center[0]), float(center[1])
        dy = int(radius_m / (c * M_PER_DEG)) + 1
        kx = max(0.05, math.cos(math.radians(min(89.0, abs(py) + 1.0))))
        dx = int(radius_m / (2 * c * M_PER_DEG * kx)) + 1
        cx, cy = int(px // (2 * c)), int(py // c)
        found: dict[LngLat, float] = {}
        for ix in range(cx - dx, cx + dx + 1):
            for iy in range(cy - dy, cy + dy + 1):
                for x, y, cls in self._vgrid.get((ix, iy), ()):
                    if want is not None and cls not in want:
                        continue
                    d = haversine_m((px, py), (x, y))
                    if d <= radius_m:
                        found[(x, y)] = d
        return [p for p, _d in sorted(found.items(), key=lambda kv: (kv[1], kv[0]))]

    # -- routing ----------------------------------------------------------------------
    def _astar(self, s: int, t: int, inv_speed: list[float], vmax: float, avoid: _Avoid | None):
        if s == t:
            return []
        x, y, adj, elen, ecls = self.x, self.y, self.adj, self.elen, self.ecls
        tx, ty = x[t], y[t]
        hk = 0.995 * M_PER_DEG / vmax  # admissible: straight distance at top speed

        def h(n: int) -> float:
            k = math.cos(math.radians(max(y[n], ty)))
            return math.hypot((x[n] - tx) * k, y[n] - ty) * hk

        g = {s: 0.0}
        prev: dict[int, tuple[int, int]] = {}
        heap = [(h(s), 0.0, s)]
        closed = set()
        while heap:
            f, gu, u = heapq.heappop(heap)
            if u == t:
                break
            if u in closed:
                continue
            closed.add(u)
            for v, e in adj[u]:
                if v in closed:
                    continue
                ei = e if e >= 0 else ~e
                cost = elen[ei] * inv_speed[ecls[ei]]
                if avoid is not None:
                    hit = avoid.cache.get(ei)
                    if hit is None:
                        hit = avoid.cache[ei] = avoid.hits(self.edge_coords(ei))
                    if hit:
                        cost = cost * AVOID_FACTOR + 3600.0
                ng = gu + cost
                if ng < g.get(v, float("inf")):
                    g[v] = ng
                    prev[v] = (u, e)
                    heapq.heappush(heap, (ng + h(v), ng, v))
        if t not in prev:
            return None
        path = []
        n = t
        while n != s:
            u, e = prev[n]
            path.append(e)
            n = u
        path.reverse()
        return path

    def _speeds(self, max_speed_mps: float | None) -> tuple[list[float], float]:
        cap = float("inf") if not max_speed_mps or max_speed_mps <= 0 else float(max_speed_mps)
        spd = [min(CLASS_SPEED_MPS.get(c, 9.0), cap) for c in self.classes]
        return [1.0 / v for v in spd], max(spd)

    def _assemble(self, start: LngLat, end: LngLat, s: int, t: int, edges: list[int],
                  inv_speed: list[float], access_speed: float, access: str = "dry") -> Route:
        """Edges s..t as one polyline. `access` decides the off-network legs start->s and t->end:
        "none" starts and ends on the network; "dry" (default) keeps a leg only where it crosses dry ground,
        otherwise the route starts/ends at the network node (a vehicle never drives straight across water)."""
        sx, sy = self.x[s], self.y[s]
        tx, ty = self.x[t], self.y[t]
        mask = _land_or_none() if access == "dry" else None
        if access == "none" or (mask is not None and not mask.leg_dry(start, (sx, sy))):
            start = (sx, sy)
        if access == "none" or (mask is not None and not mask.leg_dry((tx, ty), end)):
            end = (tx, ty)
        coords: list[LngLat] = [(float(start[0]), float(start[1]))]
        classes_m: dict[str, float] = {}
        length = duration = 0.0
        snapped = False
        lead = haversine_m(coords[0], (sx, sy))
        if lead > 0.5:
            snapped = True
            coords.append((sx, sy))
            classes_m["access"] = lead
            length += lead
            duration += lead / access_speed
        else:
            coords[0] = (sx, sy)
        for e in edges:
            ei = e if e >= 0 else ~e
            pts = self.edge_coords(e)
            coords.extend(pts[1:])
            L = self.elen[ei]
            cname = self.classes[self.ecls[ei]]
            classes_m[cname] = classes_m.get(cname, 0.0) + L
            length += L
            duration += L * inv_speed[self.ecls[ei]]
        tail = haversine_m((tx, ty), end)
        if tail > 0.5:
            snapped = True
            coords.append((float(end[0]), float(end[1])))
            classes_m["access"] = classes_m.get("access", 0.0) + tail
            length += tail
            duration += tail / access_speed
        if len(coords) == 1:
            coords.append(coords[0])
        return Route(coords=_densify(coords), length_m=round(length, 1), duration_s=round(duration, 1),
                     classes_m={k: round(v, 1) for k, v in classes_m.items()}, snapped=snapped)

    def route(self, a: LngLat, b: LngLat, avoid: list[list[LngLat]] | None = None,
              max_speed_mps: float | None = None, access: str = "dry") -> Route | None:
        """Fastest convoy route from a to b. `avoid` polygons (rings of (lng, lat)) make the
        edges touching them prohibitively expensive (still used if there is no way around).
        `access` ("dry" | "none"): see `_assemble`."""
        inv_speed, vmax = self._speeds(max_speed_mps)
        s, _ = self.nearest_node(a)
        t, _ = self.nearest_node(b)
        av = _Avoid(avoid) if avoid else None
        if av is not None and not av.polys:
            av = None
        path = self._astar(s, t, inv_speed, vmax, av)
        if path is None:
            return None
        return self._assemble(a, b, s, t, path, inv_speed, min(ACCESS_SPEED_MPS, vmax), access)

    def random_loop(self, seed: int, start: LngLat, length_m: float) -> Route:
        """Deterministic roaming loop on the network that returns to the node nearest `start` (the loop never
        leaves the network, so a start point off the streets, even in water, is harmless).
        Random walk (seeded) preferring unvisited edges, avoiding U-turns and favouring going
        straight on, until the walked distance plus the remaining way home reaches ~length_m;
        then the fastest path back. Same seed, start and length -> identical route."""
        rng = random.Random(int(seed))
        inv_speed, vmax = self._speeds(None)
        s, _ = self.nearest_node(start)
        cur, prev_e = s, None
        walked = 0.0
        visited: set[int] = set()
        walk: list[int] = []
        sx, sy = self.x[s], self.y[s]
        heading: tuple[float, float] | None = None
        ferry_idx = self.classes.index("ferry") if "ferry" in self.classes else None
        for _ in range(100_000):
            home = _fast_m(self.x[cur], self.y[cur], sx, sy) * 1.3
            if walk and walked + home >= length_m:
                break
            opts = self.adj[cur]
            if not opts:
                break
            if prev_e is not None and len(opts) > 1:
                pe = prev_e if prev_e >= 0 else ~prev_e
                opts = [o for o in opts if (o[1] if o[1] >= 0 else ~o[1]) != pe] or opts
            # weights: unvisited streets strongly preferred, then keeping roughly straight on
            weights = []
            k = math.cos(math.radians(self.y[cur]))
            for _v, e in opts:
                ei = e if e >= 0 else ~e
                w = 1.0 if ei not in visited else 0.08
                if ferry_idx is not None and self.ecls[ei] == ferry_idx:
                    w *= 0.05  # patrols rarely take the ferry
                if heading is not None:
                    pts = self.edge_coords(e)
                    dx, dy = (pts[1][0] - pts[0][0]) * k, pts[1][1] - pts[0][1]
                    n = math.hypot(dx, dy) * math.hypot(*heading)
                    if n > 0:
                        w *= 1.6 + (dx * heading[0] + dy * heading[1]) / n
                weights.append(w)
            pick = rng.random() * sum(weights)
            j = 0
            while j < len(opts) - 1 and pick >= weights[j]:
                pick -= weights[j]
                j += 1
            v, e = opts[j]
            ei = e if e >= 0 else ~e
            visited.add(ei)
            walk.append(e)
            walked += self.elen[ei]
            pts = self.edge_coords(e)
            heading = ((pts[-1][0] - pts[-2][0]) * k, pts[-1][1] - pts[-2][1])
            cur, prev_e = v, e
        back = self._astar(cur, s, inv_speed, vmax, None) or []
        r = self._assemble(start, start, s, s, walk + back, inv_speed, ACCESS_SPEED_MPS, access="none")
        r.coords[-1] = r.coords[0]
        return r


class SeaNet:
    """Water mask (~280 m) and an 8-connected navigable routing grid (~560 m) over the
    Skagerrak, Kattegat, Oresund, Baltic, Gulf of Bothnia and Gulf of Finland."""

    def __init__(self, path: Path):
        raw = path.read_bytes()
        if raw[:8] != b"TROSSEA1":
            raise ValueError(f"{path} is not a TrossOps sea grid")
        (hlen,) = struct.unpack("<I", raw[8:12])
        hdr = json.loads(raw[12:12 + hlen].decode("utf-8"))
        o = 12 + hlen
        fz, rz = hdr["fine"]["zlen"], hdr["route"]["zlen"]
        self.header = hdr
        self.source: str = hdr.get("source", "")
        self.fine = zlib.decompress(raw[o:o + fz])
        self.grid = zlib.decompress(raw[o + fz:o + fz + rz])
        self.lng0, self.lat0, self.lng1, self.lat1 = hdr["bbox"]
        self.fw, self.fh = hdr["fine"]["w"], hdr["fine"]["h"]
        self.fdlng, self.fdlat = hdr["fine"]["dlng"], hdr["fine"]["dlat"]
        self.w, self.h = hdr["route"]["w"], hdr["route"]["h"]
        f = hdr["route"]["factor"]
        self.dlng, self.dlat = self.fdlng * f, self.fdlat * f
        self.dy_m = self.dlat * M_PER_DEG
        self.dx_m = [self.dlng * M_PER_DEG * math.cos(math.radians(self.lat1 - (r + 0.5) * self.dlat))
                     for r in range(self.h)]
        self.mult = (0.0, 1.0, 1.15, 1.6)  # by grid value: 0 = blocked, 3 = adjacent to land

    def bounds(self) -> tuple[float, float, float, float]:
        return (self.lng0, self.lat0, self.lng1, self.lat1)

    def is_water(self, p: LngLat) -> bool:
        """True when p is sea (OSM coastline-derived ocean polygons). Lakes count as land."""
        c = int((p[0] - self.lng0) / self.fdlng)
        r = int((self.lat1 - p[1]) / self.fdlat)
        if not (0 <= c < self.fw and 0 <= r < self.fh) or p[0] < self.lng0 or p[1] > self.lat1:
            return False
        i = r * self.fw + c
        return bool((self.fine[i >> 3] >> (i & 7)) & 1)

    # grid <-> lng/lat (continuous grid coordinates: u east, v south; cell (c, r) spans [c, c+1))
    def _uv(self, p: LngLat) -> tuple[float, float]:
        return (p[0] - self.lng0) / self.dlng, (self.lat1 - p[1]) / self.dlat

    def _center(self, i: int) -> LngLat:
        r, c = divmod(i, self.w)
        return (round(self.lng0 + (c + 0.5) * self.dlng, 6), round(self.lat1 - (r + 0.5) * self.dlat, 6))

    def _snap(self, p: LngLat) -> tuple[int, bool] | None:
        """Navigable cell for p: its own cell if navigable, else the nearest within SEA_SNAP_M."""
        u, v = self._uv(p)
        c0, r0 = int(math.floor(u)), int(math.floor(v))
        g, w, h = self.grid, self.w, self.h
        if 0 <= c0 < w and 0 <= r0 < h and g[r0 * w + c0] and self.is_water(p):
            return r0 * w + c0, False
        lat = p[1]
        kx = math.cos(math.radians(lat))
        rmax_r = int(SEA_SNAP_M / self.dy_m) + 1
        rmax_c = int(SEA_SNAP_M / (self.dlng * M_PER_DEG * max(0.1, kx))) + 1
        best, bd = None, float("inf")
        for r in range(max(0, r0 - rmax_r), min(h, r0 + rmax_r + 1)):
            base = r * w
            for c in range(max(0, c0 - rmax_c), min(w, c0 + rmax_c + 1)):
                if g[base + c]:
                    q = self._center(base + c)
                    d = _fast_m(p[0], p[1], q[0], q[1]) * (1.0 + 0.05 * (g[base + c] - 1))
                    if d < bd:
                        best, bd = base + c, d
        if best is None or bd > SEA_SNAP_M * 1.2:
            return None
        return best, True

    def _astar(self, s: int, t: int) -> list[int] | None:
        g, w, h, mult, dxm, dym = self.grid, self.w, self.h, self.mult, self.dx_m, self.dy_m
        tr, tc = divmod(t, w)
        ky = dym
        weight = 1.25  # mildly greedy: far fewer expansions, routes still near-optimal

        def heur(i: int) -> float:
            r, c = divmod(i, w)
            ax = abs(c - tc) * dxm[min(r, tr) if self.lat1 > 0 else r] * 0.98
            ay = abs(r - tr) * ky
            return weight * (max(ax, ay) + 0.41421356 * min(ax, ay))

        best = {s: 0.0}
        prev = {s: -1}
        heap = [(heur(s), 0.0, s)]
        closed = bytearray(w * h)
        while heap:
            _f, gu, u = heapq.heappop(heap)
            if u == t:
                break
            if closed[u]:
                continue
            closed[u] = 1
            r, c = divmod(u, w)
            dx = dxm[r]
            diag = math.hypot(dx, dym)
            for dr, dc, step in ((-1, 0, dym), (1, 0, dym), (0, -1, dx), (0, 1, dx),
                                 (-1, -1, diag), (-1, 1, diag), (1, -1, diag), (1, 1, diag)):
                rr, cc = r + dr, c + dc
                if rr < 0 or rr >= h or cc < 0 or cc >= w:
                    continue
                j = rr * w + cc
                gv = g[j]
                if not gv or closed[j]:
                    continue
                if dr and dc and not (g[r * w + cc] and g[rr * w + c]):
                    continue  # no corner cutting between land cells
                ng = gu + step * mult[gv]
                if ng < best.get(j, float("inf")):
                    best[j] = ng
                    prev[j] = u
                    heapq.heappush(heap, (ng + heur(j), ng, j))
        if t not in prev:
            return None
        path = []
        n = t
        while n != -1:
            path.append(n)
            n = prev[n]
        path.reverse()
        return path

    @staticmethod
    def _traverse(a: tuple[float, float], b: tuple[float, float], ok) -> bool:
        """Amanatides-Woo: ok(col, row) holds for every grid cell the segment a->b touches
        (grid coordinates; cell (c, r) spans [c, c+1) x [r, r+1))."""
        (u0, v0), (u1, v1) = a, b
        c, r = int(math.floor(u0)), int(math.floor(v0))
        ce, re_ = int(math.floor(u1)), int(math.floor(v1))
        du, dv = u1 - u0, v1 - v0
        sc = 1 if du > 0 else -1
        sr = 1 if dv > 0 else -1
        tdu = abs(1.0 / du) if du else float("inf")
        tdv = abs(1.0 / dv) if dv else float("inf")
        tmu = ((c + 1 - u0) if du > 0 else (u0 - c)) * tdu if du else float("inf")
        tmv = ((r + 1 - v0) if dv > 0 else (v0 - r)) * tdv if dv else float("inf")
        for _ in range(abs(ce - c) + abs(re_ - r) + 2):
            if not ok(c, r):
                return False
            if c == ce and r == re_:
                return True
            if abs(tmu - tmv) < 1e-12:  # exactly through a corner: both side cells must be clear
                if not (ok(c + sc, r) and ok(c, r + sr)):
                    return False
                c += sc
                r += sr
                tmu += tdu
                tmv += tdv
            elif tmu < tmv:
                c += sc
                tmu += tdu
            else:
                r += sr
                tmv += tdv
        return False

    def _coarse_ok(self, allow3: bool):
        g, w, h = self.grid, self.w, self.h

        def ok(c: int, r: int) -> bool:
            if not (0 <= c < w and 0 <= r < h):
                return False
            v = g[r * w + c]
            return bool(v) and (allow3 or v != 3)
        return ok

    def _fine_water(self, c: int, r: int) -> bool:
        if not (0 <= c < self.fw and 0 <= r < self.fh):
            return False
        i = r * self.fw + c
        return bool((self.fine[i >> 3] >> (i & 7)) & 1)

    @staticmethod
    def _pull(pts: list[tuple[float, float]], visible) -> list[int]:
        """Greedy string pulling: indices of kept points; visible(i, j) is line of sight."""
        keep = [0]
        i, n = 0, len(pts)
        while i < n - 1:
            lo, step, hi = i + 1, 1, None
            while True:  # exponential then binary search for the farthest visible point
                j = min(n - 1, i + step)
                if visible(i, j):
                    lo = j
                    if j == n - 1:
                        break
                    step *= 2
                else:
                    hi = j
                    break
            if hi is not None:
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if visible(i, mid):
                        lo = mid
                    else:
                        hi = mid
            keep.append(lo)
            i = lo
        return keep

    def _approach(self, p: LngLat, search_m: float = 40_000.0, seed_m: float = 3_000.0):
        """Fine-grid (~280 m) Dijkstra from p through narrow channels to the nearest navigable
        routing cell. Seeds are fine water cells within seed_m of p (the cell of p itself at no
        cost when it is water; otherwise any nearby water at 3x straight-line cost, i.e. a
        short overland leg). Returns (fine cell path [(c, r)], routing cell, overland_leg)."""
        fdlng, fdlat = self.fdlng, self.fdlat
        fu, fv = (p[0] - self.lng0) / fdlng, (self.lat1 - p[1]) / fdlat
        c0, r0 = int(math.floor(fu)), int(math.floor(fv))
        fdy = fdlat * M_PER_DEG
        fdx = fdlng * M_PER_DEG * math.cos(math.radians(p[1]))
        lim_r, lim_c = int(search_m / fdy) + 1, int(search_m / max(1.0, fdx)) + 1
        sr_, sc_ = int(seed_m / fdy) + 1, int(seed_m / max(1.0, fdx)) + 1
        water = self._fine_water
        F = self.header["route"]["factor"]
        g, w = self.grid, self.w
        best: dict[tuple[int, int], float] = {}
        prev: dict[tuple[int, int], tuple[int, int] | None] = {}
        heap: list[tuple[float, int, int]] = []
        on_water = water(c0, r0)
        if on_water:
            best[(c0, r0)] = 0.0
            prev[(c0, r0)] = None
            heap.append((0.0, c0, r0))
        else:
            for r in range(r0 - sr_, r0 + sr_ + 1):
                for c in range(c0 - sc_, c0 + sc_ + 1):
                    if water(c, r):
                        d = math.hypot((c + 0.5 - fu) * fdx, (r + 0.5 - fv) * fdy)
                        if d <= seed_m:
                            best[(c, r)] = 3.0 * d
                            prev[(c, r)] = None
                            heap.append((3.0 * d, c, r))
            heapq.heapify(heap)
        diag = math.hypot(fdx, fdy)
        steps = ((1, 0, fdx), (-1, 0, fdx), (0, 1, fdy), (0, -1, fdy),
                 (1, 1, diag), (1, -1, diag), (-1, 1, diag), (-1, -1, diag))
        done = set()
        while heap:
            cost, c, r = heapq.heappop(heap)
            if (c, r) in done:
                continue
            done.add((c, r))
            R, C = r // F, c // F
            if 0 <= R < self.h and 0 <= C < w and g[R * w + C]:
                path = []
                node: tuple[int, int] | None = (c, r)
                while node is not None:
                    path.append(node)
                    node = prev[node]
                path.reverse()
                return path, R * w + C, not on_water
            for dc, dr, step in steps:
                cc, rr = c + dc, r + dr
                # diagonal steps may cut corners here: one-cell-wide channels in the ~280 m
                # mask are often only diagonally connected (rasterised rivers and sounds)
                if abs(cc - c0) > lim_c or abs(rr - r0) > lim_r or (cc, rr) in done or not water(cc, rr):
                    continue
                ng = cost + step
                if ng < best.get((cc, rr), float("inf")):
                    best[(cc, rr)] = ng
                    prev[(cc, rr)] = (c, r)
                    heapq.heappush(heap, (ng, cc, rr))
        return None

    def _endpoint(self, p: LngLat):
        """How p joins the routing grid: (routing cell, fine approach uv points, overland leg)."""
        u, v = self._uv(p)
        c0, r0 = int(math.floor(u)), int(math.floor(v))
        if 0 <= c0 < self.w and 0 <= r0 < self.h and self.grid[r0 * self.w + c0] and self.is_water(p):
            return r0 * self.w + c0, [], False
        ap = self._approach(p)
        if ap is not None:
            cells, cell, leg = ap
            pts = [(c + 0.5, r + 0.5) for c, r in cells]
            if not leg:
                pts[0] = ((p[0] - self.lng0) / self.fdlng, (self.lat1 - p[1]) / self.fdlat)
            ok = self._fine_water
            keep = self._pull(pts, lambda i, j: self._traverse(pts[i], pts[j], ok))
            return cell, [pts[k] for k in keep], leg
        sn = self._snap(p)
        if sn is None:
            return None
        return sn[0], [], True

    def _fine_ll(self, uv: tuple[float, float]) -> LngLat:
        return (round(self.lng0 + uv[0] * self.fdlng, 6), round(self.lat1 - uv[1] * self.fdlat, 6))

    def route(self, a: LngLat, b: LngLat) -> Route | None:
        """Ship track from a to b through navigable sea. Endpoints in archipelagos/harbours
        reach open water along fine-grid channels; points on land get a straight leg to the
        nearest water (up to ~30 km). Returns None if either end cannot reach the sea."""
        ea, eb = self._endpoint(a), self._endpoint(b)
        if ea is None or eb is None:
            return None
        (s, fine_a, leg_a), (t, fine_b, leg_b) = ea, eb
        cells = self._astar(s, t)
        if cells is None:
            return None
        pts = [((i % self.w) + 0.5, (i // self.w) + 0.5) for i in cells]
        vals = [self.grid[i] for i in cells]
        if not fine_a and not leg_a:
            pts[0] = self._uv(a)
        if not fine_b and not leg_b:
            pts[-1] = self._uv(b)
        ok3, ok = self._coarse_ok(True), self._coarse_ok(False)
        keep = self._pull(pts, lambda i, j: self._traverse(pts[i], pts[j], ok3 if 3 in (vals[i], vals[j]) else ok))
        coords: list[LngLat] = []
        if leg_a:
            coords.append((float(a[0]), float(a[1])))
        coords.extend(self._fine_ll(q) for q in fine_a)
        for k in keep:
            u, v = pts[k]
            coords.append((round(self.lng0 + u * self.dlng, 6), round(self.lat1 - v * self.dlat, 6)))
        coords.extend(self._fine_ll(q) for q in reversed(fine_b))
        if leg_b:
            coords.append((float(b[0]), float(b[1])))
        coords = [q for i, q in enumerate(coords) if i == 0 or q != coords[i - 1]]
        if len(coords) == 1:
            coords.append(coords[0])
        coords = _densify(coords)
        L = _polyline_m(coords)
        return Route(coords=coords, length_m=round(L, 1), duration_s=round(L / SEA_SPEED_MPS, 1),
                     classes_m={"sea": round(L, 1)}, snapped=leg_a or leg_b)


# ---------------------------------------------------------------------------------------
# Cached singletons
# ---------------------------------------------------------------------------------------

_lock = threading.Lock()
_cache: dict[str, object] = {}


class LandMask:
    """Where the ground is dry: every OSM water polygon (sea, lakes, rivers, ponds, docks) over Sweden at ~110 m,
    falling back to the sea mask outside the covered tiles. Placement of anything that stands or drives on the
    ground goes through `is_dry` / `nearest_dry` / `fits`."""

    def __init__(self, path: Path, sea: "SeaNet | None" = None, roads_path: Path | None = None):
        raw = path.read_bytes()
        if raw[:8] != b"TROSLND1":
            raise ValueError(f"{path} is not a TrossOps land mask")
        (hlen,) = struct.unpack("<I", raw[8:12])
        hdr = json.loads(raw[12:12 + hlen].decode("utf-8"))
        o = 12 + hlen
        wz, kz = hdr["water"]["zlen"], hdr["known"]["zlen"]
        self.header = hdr
        self.source: str = hdr.get("source", "")
        self.water = zlib.decompress(raw[o:o + wz])
        self.known = zlib.decompress(raw[o + wz:o + wz + kz])
        self.lng0, self.lat0, self.lng1, self.lat1 = hdr["bbox"]
        self.w, self.h, self.dlng, self.dlat = hdr["w"], hdr["h"], hdr["dlng"], hdr["dlat"]
        self.sea = sea
        self._roads: dict[str, set[int]] = {}
        # every road class incl. minor roads (z12) around placements, same grid (optional, see build step `roads`)
        self.road_bits: bytes | None = None
        if roads_path is not None and roads_path.exists():
            rr = roads_path.read_bytes()
            if rr[:8] == b"TROSRDS1":
                (rl,) = struct.unpack("<I", rr[8:12])
                rh = json.loads(rr[12:12 + rl].decode("utf-8"))
                if (rh["w"], rh["h"], rh["dlng"], rh["dlat"]) == (self.w, self.h, self.dlng, self.dlat):
                    ro = 12 + rl
                    self.road_bits = zlib.decompress(rr[ro:ro + rh["roads"]["zlen"]])

    def on_any_road(self, q: LngLat) -> bool:
        """A road of any class (incl. minor roads) crosses q's cell (only where roads.bin has coverage)."""
        if self.road_bits is None:
            return False
        c = self.cell(q)
        return c >= 0 and bool((self.road_bits[c >> 3] >> (c & 7)) & 1)

    def cell(self, p: LngLat) -> int:
        """Grid cell id of p (-1 outside the grid)."""
        c = int((p[0] - self.lng0) / self.dlng)
        r = int((self.lat1 - p[1]) / self.dlat)
        return r * self.w + c if 0 <= c < self.w and 0 <= r < self.h and p[0] >= self.lng0 and p[1] <= self.lat1 else -1

    def road_cells(self, net: "RoadNet", step_m: float = 35.0) -> set[int]:
        """Cells a road of `net` passes through (rasterised once per network, ~1 s for the national graph)."""
        hit = self._roads.get(net.name)
        if hit is None:
            hit = set()
            for e in range(len(net.elen)):
                pts = net.edge_coords(e)
                for a, b in zip(pts, pts[1:]):
                    n = max(1, int(_fast_m(a[0], a[1], b[0], b[1]) / step_m))
                    for k in range(n + 1):
                        c = self.cell((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
                        if c >= 0:
                            hit.add(c)
            self._roads[net.name] = hit
        return hit

    def is_water(self, p: LngLat) -> bool:
        c = int((p[0] - self.lng0) / self.dlng)
        r = int((self.lat1 - p[1]) / self.dlat)
        if 0 <= c < self.w and 0 <= r < self.h and p[0] >= self.lng0 and p[1] <= self.lat1:
            i = r * self.w + c
            if (self.known[i >> 3] >> (i & 7)) & 1:
                return bool((self.water[i >> 3] >> (i & 7)) & 1)
        return bool(self.sea and self.sea.is_water(p))

    def is_dry(self, p: LngLat) -> bool:
        return not self.is_water(p)

    def fits(self, pts: list[LngLat]) -> bool:
        return all(not self.is_water(q) for q in pts)

    def leg_dry(self, a: LngLat, b: LngLat, step_m: float = 50.0) -> bool:
        """True when the straight line a-b stays on dry ground (sampled every step_m)."""
        n = max(1, int(haversine_m(a, b) / step_m))
        return all(not self.is_water((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)) for k in range(n + 1))

    def nearest_dry(self, p: LngLat, max_m: float = 20_000.0, clearance_m: float = 0.0, blocked: set[int] | None = None) -> LngLat | None:
        """Closest point to p (searched on rings every ~half a cell) that is dry and not in a `blocked` cell (e.g.
        road cells), with `clearance_m` of dry ground around it when asked. p itself when it already qualifies;
        None if nothing within max_m."""
        # judged on the coordinate as stored (6 decimals): a point on a cell edge must not flip cells when rounded
        def ok(q: LngLat) -> bool:
            if self.is_water(q) or (blocked is not None and (self.cell(q) in blocked or self.on_any_road(q))):
                return False
            return clearance_m <= 0 or all(not self.is_water(_offset(q, b, clearance_m)) for b in range(0, 360, 45))
        p = (round(p[0], 6), round(p[1], 6))
        if ok(p):
            return p
        step = 55.0
        r = step
        while r <= max_m:
            n = max(8, int(2 * math.pi * r / step))
            for k in range(n):
                q = _offset(p, 360.0 * k / n, r)
                q = (round(q[0], 6), round(q[1], 6))
                if ok(q):
                    return q
            r += step
        return None

    def candidates(self, center: LngLat, samples: list[LngLat], max_m: float = 15_000.0, step_m: float = 120.0,
                   wet: list[LngLat] | None = None, blocked: set[int] | None = None, sea: list[LngLat] | None = None,
                   minor: bool = True, core: list[LngLat] | None = None):
        """Shifts (east m, north m) of a rigid shape, nearest first, for which every `samples` point is dry and, with
        `blocked`, clear of graph roads (and the `core` points of every road incl. minor ones when `minor`; without
        `core` all samples are held to that), every `wet` point is water
        (berths) and every `sea` point is navigable sea (a channel). Callers re-check the shape actually rebuilt at the
        shifted centre and take the first that passes. Samples are tested lazily in a fixed shuffled order, so a bad
        candidate is usually rejected after a handful of lookups."""
        k = math.cos(math.radians(center[1]))
        fx, fy = 1.0 / (M_PER_DEG * k), 1.0 / M_PER_DEG
        order = list(samples)
        random.Random(7).shuffle(order)
        strict = list(core) if core is not None else order
        if core is not None:
            random.Random(11).shuffle(strict)
        is_water, cell, any_road = self.is_water, self.cell, self.on_any_road

        def good(de: float, dn: float) -> bool:
            dx, dy = de * fx, dn * fy
            if wet:
                for q in wet:
                    if not is_water((q[0] + dx, q[1] + dy)):
                        return False
            if sea:
                for q in sea:
                    if not self.wet_ok((q[0] + dx, q[1] + dy), True):
                        return False
            for q in order:
                r = (q[0] + dx, q[1] + dy)
                if is_water(r) or (blocked is not None and cell(r) in blocked):
                    return False
            if blocked is not None and minor:
                for q in strict:
                    r = (q[0] + dx, q[1] + dy)
                    if any_road(r) or cell(r) in blocked:
                        return False
            return True
        if good(0.0, 0.0):
            yield (0.0, 0.0)
        r = step_m
        while r <= max_m:
            n = max(12, int(2 * math.pi * r / step_m))
            for j in range(n):
                a = 2 * math.pi * j / n
                de, dn = r * math.sin(a), r * math.cos(a)
                if good(de, dn):
                    yield (de, dn)
            r += step_m

    def dry_ok(self, pts: list[LngLat], blocked: set[int] | None = None, minor: bool = True, core: list[LngLat] | None = None) -> bool:
        """All points dry; with `blocked` (road cells of the graphs) also clear of graph roads, and with `minor` the
        `core` points (or all points when no core is given) clear of every road incl. minor ones."""
        if any(self.is_water(q) or (blocked is not None and self.cell(q) in blocked) for q in pts):
            return False
        if blocked is None or not minor:
            return True
        return not any(self.on_any_road(q) or self.cell(q) in blocked for q in (core if core is not None else pts))

    def wet_ok(self, q: LngLat, sea_only: bool = False) -> bool:
        return self.is_water(q) and (not sea_only or self.sea is None or self.sea.is_water(q))

    def shift(self, center: LngLat, de: float, dn: float) -> LngLat:
        return (center[0] + de / (M_PER_DEG * math.cos(math.radians(center[1]))), center[1] + dn / M_PER_DEG)


def _offset(p: LngLat, bearing_deg: float, dist_m: float) -> LngLat:
    a = math.radians(bearing_deg)
    return (p[0] + dist_m * math.sin(a) / (M_PER_DEG * math.cos(math.radians(p[1]))), p[1] + dist_m * math.cos(a) / M_PER_DEG)


def _land_or_none() -> "LandMask | None":
    try:
        return land()
    except (OSError, ValueError):  # mask not built: behave as before (access legs kept)
        return None


def _load_roadnet(name: str, path: Path) -> RoadNet:
    with gzip.open(path, "rb") as fh:
        doc = json.loads(fh.read())
    return RoadNet(name, doc)


def _cached(key: str, factory):
    obj = _cache.get(key)
    if obj is None:
        with _lock:
            obj = _cache.get(key)
            if obj is None:
                obj = _cache[key] = factory()
    return obj


def national() -> RoadNet:
    """National road graph (motorway, trunk, primary, secondary, tertiary)."""
    return _cached("national", lambda: _load_roadnet("national", DATA_DIR / "national.json.gz"))


def cities() -> list[str]:
    """Names of the available city street graphs."""
    return sorted(p.name[len("city_"):-len(".json.gz")] for p in DATA_DIR.glob("city_*.json.gz"))


def city(name: str) -> RoadNet:
    """City street graph (motorway..minor, no service/track/path). Also whole-island region graphs
    such as "gotland" (incl. the Farosund ferry to Faro). KeyError for unknown names."""
    if name not in cities():
        raise KeyError(name)
    return _cached(f"city:{name}", lambda: _load_roadnet(name, DATA_DIR / f"city_{name}.json.gz"))


def sea() -> SeaNet:
    """Sea mask and ship routing grid."""
    return _cached("sea", lambda: SeaNet(DATA_DIR / "sea.bin"))


def land() -> LandMask:
    """Land/water mask (lakes and rivers included) for placing sites and ground units."""
    sea_net = sea()  # outside _cached: the cache lock is not re-entrant
    return _cached("land", lambda: LandMask(DATA_DIR / "land.bin", sea_net, DATA_DIR / "roads.bin"))
