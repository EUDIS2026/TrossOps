"""Build the TrossOps geospatial routing artefacts in backend/data/geo/.

Inputs (all public, see scripts/data/README.md):
  * OpenFreeMap vector tiles (OpenMapTiles schema, (c) OpenStreetMap contributors, ODbL)
      - layer `transportation` -> national road graph (z11) and city street graphs (z14)
      - layer `water` (class=ocean, plus sea-connected river reaches) -> sea mask (z10)
  * frontend/public/data/sweden_counties.geojson (SCB counties, CC0) -> which tiles to fetch

Outputs:
  backend/data/geo/national.json.gz      road graph (motorway..tertiary)
  backend/data/geo/city_<name>.json.gz   street graphs (motorway..minor)
  backend/data/geo/sea.bin               water mask + navigable routing grid

The script has no third-party dependencies beyond httpx (already a backend runtime
dependency). Downloaded tiles are cached outside the repo and treated as untrusted
bytes; run it isolated:  python -I scripts/data/build_geonet.py --cache <dir>
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import gzip
import json
import math
import os
import struct
import sys
import threading
import time
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COUNTIES = REPO / "frontend" / "public" / "data" / "sweden_counties.geojson"
OUT_DIR = REPO / "backend" / "data" / "geo"
TILEJSON_URL = "https://tiles.openfreemap.org/planet"
USER_AGENT = "TrossOps-databuild/1.0 (research demo)"
LICENCE = "ODbL (c) OpenStreetMap contributors; tiles via OpenFreeMap (OpenMapTiles schema)"
EXTENT = 4096

ROAD_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "minor", "service"]
NATIONAL_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary"]
CITY_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "minor"]

CITIES = {
    "stockholm": (18.07, 59.33, 14), "goteborg": (11.97, 57.71, 10), "malmo": (13.00, 55.60, 8),
    "uppsala": (17.64, 59.86, 6), "linkoping": (15.62, 58.41, 5), "orebro": (15.21, 59.27, 5),
    "vasteras": (16.55, 59.61, 5), "helsingborg": (12.69, 56.05, 5), "norrkoping": (16.19, 58.59, 5),
    "jonkoping": (14.16, 57.78, 5), "umea": (20.26, 63.83, 5), "lulea": (22.15, 65.58, 5),
    "sundsvall": (17.31, 62.39, 4), "visby": (18.29, 57.64, 3), "karlskrona": (15.59, 56.16, 4),
    "ostersund": (14.64, 63.18, 4), "kiruna": (20.22, 67.86, 3), "boden": (21.69, 65.82, 3),
    "gavle": (17.14, 60.67, 4), "kalmar": (16.36, 56.66, 4),
}

# Sea grid: fine water mask (is_water) and a 2x2-coarser navigable routing grid.
SEA_BBOX = (9.5, 53.8, 30.5, 66.2)  # lng0, lat0, lng1, lat1
SEA_FINE = (0.005, 0.0025)  # dlng, dlat degrees (~280 m)
SEA_ROUTE_FACTOR = 2  # routing cell = 2x2 fine cells (~560 m)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------------------
# Minimal MVT (protobuf) decoder. Input is untrusted: malformed data -> ValueError.
# ---------------------------------------------------------------------------

def _varint(buf, i):
    shift = result = 0
    n = len(buf)
    while True:
        if i >= n:
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def _fields(buf):
    i, n = 0, len(buf)
    while i < n:
        key, i = _varint(buf, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(buf, i)
        elif wt == 2:
            ln, i = _varint(buf, i)
            if i + ln > n:
                raise ValueError("truncated field")
            v = buf[i:i + ln]
            i += ln
        elif wt == 1:
            v = buf[i:i + 8]
            i += 8
        elif wt == 5:
            v = buf[i:i + 4]
            i += 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        yield fn, wt, v


def _packed(buf):
    out = []
    i, n = 0, len(buf)
    while i < n:
        v, i = _varint(buf, i)
        out.append(v)
    return out


def _zz(n):
    return (n >> 1) ^ -(n & 1)


def _value(buf):
    for fn, _wt, v in _fields(buf):
        if fn == 1:
            return v.decode("utf-8", "replace")
        if fn == 2:
            return struct.unpack("<f", v)[0]
        if fn == 3:
            return struct.unpack("<d", v)[0]
        if fn == 4:
            return v - (1 << 64) if v >= (1 << 63) else v
        if fn == 5:
            return v
        if fn == 6:
            return _zz(v)
        if fn == 7:
            return bool(v)
    return None


def decode_geometry(cmds):
    """Geometry command stream -> list of parts (lines or unclosed rings), tile-local ints."""
    parts = []
    cur = None
    x = y = 0
    i, n = 0, len(cmds)
    while i < n:
        c = cmds[i]
        i += 1
        cid, cnt = c & 7, c >> 3
        if cid in (1, 2):
            if i + 2 * cnt > n:
                raise ValueError("truncated geometry")
            for _ in range(cnt):
                x += _zz(cmds[i])
                y += _zz(cmds[i + 1])
                i += 2
                if cid == 1:
                    cur = [(x, y)]
                    parts.append(cur)
                elif cur is None:
                    raise ValueError("LineTo before MoveTo")
                else:
                    cur.append((x, y))
        elif cid != 7:
            raise ValueError(f"bad geometry command {cid}")
    return parts


def decode_layer(data: bytes, layer: str, want=None):
    """Decode one layer. `want(props) -> bool` filters before geometry decoding.
    Returns (extent, [(geom_type, props, parts)])."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    for fn, wt, lbuf in _fields(data):
        if fn != 3 or wt != 2:
            continue
        # The layer name is field 1; peek it before decoding everything.
        name = None
        for lfn, _lwt, v in _fields(lbuf):
            if lfn == 1:
                name = v.decode("utf-8", "replace")
                break
        if name != layer:
            continue
        extent = EXTENT
        keys, values, feats_raw = [], [], []
        for lfn, _lwt, v in _fields(lbuf):
            if lfn == 2:
                feats_raw.append(v)
            elif lfn == 3:
                keys.append(v.decode("utf-8", "replace"))
            elif lfn == 4:
                values.append(_value(v))
            elif lfn == 5:
                extent = v
        feats = []
        for fb in feats_raw:
            tags, gtype, geom = [], 0, b""
            for ffn, fwt, v in _fields(fb):
                if ffn == 2:
                    tags = _packed(v) if fwt == 2 else [v]
                elif ffn == 3:
                    gtype = v
                elif ffn == 4:
                    geom = v
            props = {}
            for k in range(0, len(tags) - 1, 2):
                ki, vi = tags[k], tags[k + 1]
                if ki < len(keys) and vi < len(values):
                    props[keys[ki]] = values[vi]
            if want is not None and not want(props):
                continue
            cmds = _packed(geom) if isinstance(geom, (bytes, bytearray)) else [geom]
            feats.append((gtype, props, decode_geometry(cmds)))
        return extent, feats
    return EXTENT, []


# ---------------------------------------------------------------------------
# Tile maths and fetching
# ---------------------------------------------------------------------------

def lng2x(lng, z):
    return (lng + 180.0) / 360.0 * (1 << z)


def lat2y(lat, z):
    return (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * (1 << z)


def x2lng(x, z):
    return x / (1 << z) * 360.0 - 180.0


def y2lat(y, z):
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / (1 << z)))))


def tile_bbox(z, x, y):
    return x2lng(x, z), y2lat(y + 1, z), x2lng(x + 1, z), y2lat(y, z)


def tiles_in_bbox(z, lng0, lat0, lng1, lat1):
    x0, x1 = int(lng2x(lng0, z)), int(lng2x(lng1, z))
    y0, y1 = int(lat2y(lat1, z)), int(lat2y(lat0, z))
    return [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


class Fetcher:
    def __init__(self, cache: Path, workers: int = 6):
        import httpx  # build-time only

        self.cache = cache
        self.workers = max(1, min(6, workers))
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=True)
        self.template = self._template()
        self.version = self.template.split("/planet/")[-1].split("/")[0] if "/planet/" in self.template else "unknown"
        self.lock = threading.Lock()
        self.fetched = 0

    def _template(self) -> str:
        p = self.cache / "tilejson.json"
        if p.exists():
            tj = json.loads(p.read_text(encoding="utf-8"))
        else:
            r = self.client.get(TILEJSON_URL)
            r.raise_for_status()
            tj = r.json()
            self.cache.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(tj), encoding="utf-8")
        t = tj["tiles"][0]
        if not t.startswith("https://tiles.openfreemap.org/"):
            raise ValueError(f"unexpected tile template {t!r}")
        return t

    def path(self, z, x, y) -> Path:
        return self.cache / "tiles" / self.version / str(z) / str(x) / f"{y}.pbf"

    def _get(self, z, x, y) -> Path:
        p = self.path(z, x, y)
        if p.exists():
            return p
        url = self.template.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
        for attempt in range(5):
            try:
                r = self.client.get(url)
                if r.status_code in (204, 404):
                    data = b""
                else:
                    r.raise_for_status()
                    data = r.content
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".part")
                tmp.write_bytes(data)
                os.replace(tmp, p)
                with self.lock:
                    self.fetched += 1
                return p
            except Exception as e:  # network hiccup: back off politely
                if attempt == 4:
                    raise
                log(f"retry {z}/{x}/{y}: {e}")
                time.sleep(2 ** attempt)
        return p

    def fetch_all(self, tiles) -> None:
        todo = [t for t in tiles if not self.path(*t).exists()]
        log(f"tiles: {len(tiles)} needed, {len(todo)} to download")
        if not todo:
            return
        done = 0
        with cf.ThreadPoolExecutor(self.workers) as ex:
            for _ in ex.map(lambda t: self._get(*t), todo):
                done += 1
                if done % 500 == 0:
                    log(f"  downloaded {done}/{len(todo)}")


# ---------------------------------------------------------------------------
# Sweden footprint (counties) -> tile selection
# ---------------------------------------------------------------------------

def load_sweden():
    d = json.loads(COUNTIES.read_text(encoding="utf-8"))
    rings = []
    for f in d["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                rings.append([(float(a), float(b)) for a, b in ring])
    return rings


def point_in_rings(p, rings):
    x, y = p
    inside = False
    for ring in rings:
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside


def sweden_tiles(z, rings, buffer_km=4.0):
    pts = [p for r in rings for p in r]
    lng0 = min(p[0] for p in pts) - 0.2
    lng1 = max(p[0] for p in pts) + 0.2
    lat0 = min(p[1] for p in pts) - 0.1
    lat1 = max(p[1] for p in pts) + 0.1
    out = []
    for (tz, tx, ty) in tiles_in_bbox(z, lng0, lat0, lng1, lat1):
        w, s, e, n = tile_bbox(tz, tx, ty)
        bl = buffer_km / 111.0
        bw = bl / math.cos(math.radians((s + n) / 2))
        W, S, E, N = w - bw, s - bl, e + bw, n + bl
        hit = any(W <= px <= E and S <= py <= N for px, py in pts)
        if not hit:
            for q in ((w, s), (w, n), (e, s), (e, n), ((w + e) / 2, (s + n) / 2)):
                if point_in_rings(q, rings):
                    hit = True
                    break
        if hit:
            out.append((tz, tx, ty))
    return out


def circle_tiles(z, lng, lat, radius_km):
    dl = radius_km / 111.0
    dw = dl / math.cos(math.radians(lat))
    out = []
    for t in tiles_in_bbox(z, lng - dw, lat - dl, lng + dw, lat + dl):
        w, s, e, n = tile_bbox(*t)
        cx = min(max(lng, w), e)
        cy = min(max(lat, s), n)
        if haversine((lng, lat), (cx, cy)) <= radius_km * 1000.0:
            out.append(t)
    return out


def haversine(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, h)))


# ---------------------------------------------------------------------------
# Road graph construction
# ---------------------------------------------------------------------------

def _clip_t(x1, y1, x2, y2, lo, hi):
    """Liang-Barsky: parametric [t0, t1] of segment inside [lo,hi]^2, or None."""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - lo), (dx, hi - x1), (-dy, y1 - lo), (dy, hi - y1)):
        if p == 0:
            if q < 0:
                return None
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return None
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return None
                if r < t1:
                    t1 = r
    if t1 - t0 <= 0:
        return None
    return t0, t1


def clip_polyline(pts, lo=0, hi=EXTENT):
    """Clip to the tile square. Returns [(points, start_clipped, end_clipped)]."""
    pieces = []
    cur = None
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        r = _clip_t(x1, y1, x2, y2, lo, hi)
        if r is None:
            cur = None
            continue
        t0, t1 = r
        dx, dy = x2 - x1, y2 - y1
        p = (x1 + t0 * dx, y1 + t0 * dy) if t0 > 0 else (x1, y1)
        q = (x1 + t1 * dx, y1 + t1 * dy) if t1 < 1 else (x2, y2)
        if cur is None or t0 > 0:
            cur = [[p], t0 > 0, False]
            pieces.append(cur)
        cur[0].append(q)
        if t1 < 1:
            cur[2] = True
            cur = None
    return [(c[0], c[1], c[2]) for c in pieces if len(c[0]) >= 2]


def tile_roads(args):
    """Worker: decode one tile -> clipped road pieces in global tile-pixel coords."""
    path, z, tx, ty, classes = args
    data = Path(path).read_bytes()
    if not data:
        return []
    cls_idx = {c: i for i, c in enumerate(classes)}

    def want(p):
        if p.get("class") not in cls_idx:
            return False
        if p.get("access") in ("no", "private"):
            return False
        return True

    try:
        _extent, feats = decode_layer(data, "transportation", want)
    except ValueError as e:
        print(f"bad tile {z}/{tx}/{ty}: {e}", file=sys.stderr)
        return []
    ox, oy = tx * EXTENT, ty * EXTENT
    out = []
    for gtype, props, parts in feats:
        if gtype != 2:
            continue
        ci = cls_idx[props["class"]]
        ow = props.get("oneway", 0)
        ow = 1 if ow in (1, "1", True) else (-1 if ow in (-1, "-1") else 0)
        for part in parts:
            if len(part) < 2:
                continue
            for pts, sc, ec in clip_polyline(part):
                flat = []
                for x, y in pts:
                    flat.append(ox + x)
                    flat.append(oy + y)
                out.append((ci, ow, flat, sc, ec))
    return out


class UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        p = self.p
        root = a
        while p.get(root, root) != root:
            root = p[root]
        while p.get(a, a) != root:
            p[a], a = root, p[a]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def build_graph(name, z, pieces, classes, tol_units, simplify_units, crop=None, ferry_class=None, ferry_tol_units=0.0):
    """pieces: [(cls, oneway, flat global coords, start_clipped, end_clipped)].
    crop(gx, gy) -> bool optionally limits the output to edges touching the crop area.
    ferry_class: class index of ferry lines. Their loose ends are linked to the nearest road
    within ferry_tol_units, and ferry spurs that still dead-end (lines leaving the region) are
    pruned."""
    t0 = time.time()
    # 1. seam snapping of clip points on the same tile boundary line
    seam = collections.defaultdict(list)
    for pi, (_c, _o, flat, sc, ec) in enumerate(pieces):
        for flag, k in ((sc, 0), (ec, len(flat) - 2)):
            if not flag:
                continue
            x, y = flat[k], flat[k + 1]
            if abs(x / EXTENT - round(x / EXTENT)) < 1e-9:
                seam[("x", round(x))].append((y, pi, k))
            elif abs(y / EXTENT - round(y / EXTENT)) < 1e-9:
                seam[("y", round(y))].append((x, pi, k))
    nsnap = 0
    for key, lst in seam.items():
        lst.sort()
        cluster = [lst[0]]
        for item in lst[1:] + [None]:
            if item is not None and item[0] - cluster[-1][0] <= tol_units:
                cluster.append(item)
                continue
            if len(cluster) > 1:
                pos = sum(c[0] for c in cluster) / len(cluster)
                for _pos, pi, k in cluster:
                    flat = pieces[pi][2]
                    if key[0] == "x":
                        flat[k + 1] = pos
                    else:
                        flat[k] = pos
                nsnap += len(cluster)
            if item is not None:
                cluster = [item]
    # 2. vertices + segments
    vid = {}
    coords = []

    def V(x, y):
        k = (round(x, 3), round(y, 3))
        i = vid.get(k)
        if i is None:
            i = vid[k] = len(coords)
            coords.append(k)
        return i

    seg = {}  # (u, v) u<v -> [cls, fwd_ok, bwd_ok]
    for ci, ow, flat, _sc, _ec in pieces:
        prev = V(flat[0], flat[1])
        for k in range(2, len(flat), 2):
            cur = V(flat[k], flat[k + 1])
            if cur == prev:
                continue
            u, v = (prev, cur) if prev < cur else (cur, prev)
            f = ow >= 0 if prev < cur else ow <= 0  # travel allowed u->v
            b = ow <= 0 if prev < cur else ow >= 0
            s = seg.get((u, v))
            if s is None:
                seg[(u, v)] = [ci, f, b]
            else:
                s[0] = min(s[0], ci)
                s[1] = s[1] or f
                s[2] = s[2] or b
            prev = cur
    log(f"  [{name}] {len(pieces)} pieces, {nsnap} seam points snapped, {len(coords)} vertices, {len(seg)} segments")
    # 3. T-junctions: dangling true endpoints lying on another segment's interior
    nbrs = collections.defaultdict(set)
    for (u, v) in seg:
        nbrs[u].add(v)
        nbrs[v].add(u)
    cell = max(tol_units * 4, 16.0)
    grid = collections.defaultdict(list)

    def add_seg_grid(u, v):
        (x1, y1), (x2, y2) = coords[u], coords[v]
        for gx in range(int(min(x1, x2) // cell) - 0, int(max(x1, x2) // cell) + 1):
            for gy in range(int(min(y1, y2) // cell), int(max(y1, y2) // cell) + 1):
                grid[(gx, gy)].append((u, v))

    for (u, v) in seg:
        add_seg_grid(u, v)
    ntj = 0
    for w in [i for i, s in nbrs.items() if len(s) == 1]:
        if len(nbrs[w]) != 1:
            continue
        px, py = coords[w]
        best = None
        for gx in range(int((px - tol_units) // cell), int((px + tol_units) // cell) + 1):
            for gy in range(int((py - tol_units) // cell), int((py + tol_units) // cell) + 1):
                for (u, v) in grid.get((gx, gy), ()):
                    if u == w or v == w or (u, v) not in seg:
                        continue
                    (x1, y1), (x2, y2) = coords[u], coords[v]
                    dx, dy = x2 - x1, y2 - y1
                    L = dx * dx + dy * dy
                    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
                    d = math.hypot(px - x1 - t * dx, py - y1 - t * dy)
                    if d <= tol_units and (best is None or d < best[0]):
                        best = (d, u, v, t)
        if best is None:
            continue
        _d, u, v, t = best
        n0 = next(iter(nbrs[w]))
        if n0 in (u, v):
            continue
        ntj += 1
        if t <= 1e-9 or t >= 1 - 1e-9:
            # endpoint coincides with an existing vertex: re-attach w's segment to it
            tgt = u if t <= 1e-9 else v
            if tgt == n0:
                continue
            a, b = (w, n0) if w < n0 else (n0, w)
            s = seg.pop((a, b))
            fw = s[1] if a == n0 else s[2]  # n0 -> w allowed
            bw = s[2] if a == n0 else s[1]
            a2, b2 = (n0, tgt) if n0 < tgt else (tgt, n0)
            ns = [s[0], fw if a2 == n0 else bw, bw if a2 == n0 else fw]
            if (a2, b2) in seg:
                o = seg[(a2, b2)]
                o[0] = min(o[0], ns[0]); o[1] = o[1] or ns[1]; o[2] = o[2] or ns[2]
            else:
                seg[(a2, b2)] = ns
                add_seg_grid(a2, b2)
            nbrs[w].discard(n0); nbrs[n0].discard(w); nbrs[n0].add(tgt); nbrs[tgt].add(n0)
        else:
            s = seg.pop((u, v))
            seg[(min(u, w), max(u, w))] = [s[0], s[1] if u < w else s[2], s[2] if u < w else s[1]]
            seg[(min(w, v), max(w, v))] = [s[0], s[1] if w < v else s[2], s[2] if w < v else s[1]]
            add_seg_grid(u, w)
            add_seg_grid(w, v)
            nbrs[u].discard(v); nbrs[v].discard(u)
            nbrs[u].add(w); nbrs[w].add(u); nbrs[v].add(w); nbrs[w].add(v)
    log(f"  [{name}] {ntj} T-junctions joined")
    if ferry_class is not None:
        nf = 0
        for w in [i for i, s in nbrs.items() if len(s) == 1]:
            n0 = next(iter(nbrs[w]))
            if seg[(min(w, n0), max(w, n0))][0] != ferry_class:
                continue
            px, py = coords[w]
            best = None
            for gx in range(int((px - ferry_tol_units) // cell), int((px + ferry_tol_units) // cell) + 1):
                for gy in range(int((py - ferry_tol_units) // cell), int((py + ferry_tol_units) // cell) + 1):
                    for (u, v) in grid.get((gx, gy), ()):
                        sg = seg.get((u, v))
                        if sg is None or sg[0] == ferry_class or w in (u, v):
                            continue
                        (x1, y1), (x2, y2) = coords[u], coords[v]
                        dx, dy = x2 - x1, y2 - y1
                        L = dx * dx + dy * dy
                        t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
                        d = math.hypot(px - x1 - t * dx, py - y1 - t * dy)
                        if d <= ferry_tol_units and (best is None or d < best[0]):
                            best = (d, u, v, t)
            if best is None:
                continue
            _d, u, v, t = best
            if t <= 1e-9 or t >= 1 - 1e-9:
                tgt = u if t <= 1e-9 else v
            else:  # split the road segment at the foot point
                (x1, y1), (x2, y2) = coords[u], coords[v]
                tgt = V(x1 + t * (x2 - x1), y1 + t * (y2 - y1))
                sg = seg.pop((u, v))
                seg[(min(u, tgt), max(u, tgt))] = [sg[0], sg[1] if u < tgt else sg[2], sg[2] if u < tgt else sg[1]]
                seg[(min(tgt, v), max(tgt, v))] = [sg[0], sg[1] if tgt < v else sg[2], sg[2] if tgt < v else sg[1]]
                add_seg_grid(u, tgt)
                add_seg_grid(tgt, v)
                nbrs[u].discard(v); nbrs[v].discard(u)
                nbrs[u].add(tgt); nbrs[tgt].add(u); nbrs[v].add(tgt); nbrs[tgt].add(v)
            if tgt == w:
                continue
            seg[(min(w, tgt), max(w, tgt))] = [ferry_class, True, True]
            nbrs[w].add(tgt)
            nbrs[tgt].add(w)
            nf += 1
        log(f"  [{name}] {nf} ferry ends linked to roads")

    # 4. collapse degree-2 vertices into edge shapes
    def attrs(a, b):
        """(cls, can a->b, can b->a)"""
        s = seg[(a, b)] if a < b else seg[(b, a)]
        return (s[0], s[1], s[2]) if a < b else (s[0], s[2], s[1])

    is_node = {}
    for w, s in nbrs.items():
        if not s:
            continue
        if len(s) != 2:
            is_node[w] = True
            continue
        a, b = tuple(s)
        ca, af, ab = attrs(a, w)  # a->w, w->a
        cb, bf, bb = attrs(w, b)  # w->b, b->w
        is_node[w] = not (ca == cb and af == bf and ab == bb)
    edges = []  # (a, b, cls, fwd, bwd, [vertex chain])
    used = set()
    for w in [w for w, n in is_node.items() if n]:
        for nb in nbrs[w]:
            key = (min(w, nb), max(w, nb))
            if key in used:
                continue
            chain = [w, nb]
            used.add(key)
            prev, cur = w, nb
            while not is_node.get(cur, True):
                nxt = [q for q in nbrs[cur] if q != prev]
                if not nxt:
                    break
                nq = nxt[0]
                k2 = (min(cur, nq), max(cur, nq))
                if k2 in used:
                    break
                used.add(k2)
                chain.append(nq)
                prev, cur = cur, nq
            c, f, b = attrs(chain[0], chain[1])
            edges.append((chain[0], chain[-1], c, f, b, chain))
    # pure cycles without any node
    for (u, v) in list(seg):
        if (u, v) in used:
            continue
        is_node[u] = True
        chain = [u, v]
        used.add((u, v))
        prev, cur = u, v
        while cur != u:
            nxt = [q for q in nbrs[cur] if q != prev and (min(cur, q), max(cur, q)) not in used]
            if not nxt:
                break
            nq = nxt[0]
            used.add((min(cur, nq), max(cur, nq)))
            chain.append(nq)
            prev, cur = cur, nq
        c, f, b = attrs(chain[0], chain[1])
        edges.append((chain[0], chain[-1], c, f, b, chain))
    edges = [e for e in edges if e[3] or e[4]]
    if ferry_class is not None:  # prune ferry spurs that dead-end (e.g. routes leaving the region)
        while True:
            deg = collections.Counter()
            for e in edges:
                deg[e[0]] += 1
                deg[e[1]] += 1
            keep_e = [e for e in edges if not (e[2] == ferry_class and (deg[e[0]] == 1 or deg[e[1]] == 1))]
            if len(keep_e) == len(edges):
                break
            edges = keep_e
    for e in edges:
        is_node[e[0]] = True
        is_node[e[1]] = True
    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
    log(f"  [{name}] collapsed: {len(nodes)} nodes, {len(edges)} edges")

    # 5. largest strongly connected component (== connected component when no oneways).
    #    Connectivity is computed on the full fetched area first, then the optional crop
    #    is applied and the largest component recomputed (so roads that link up just
    #    outside the crop circle still count as connected).
    km_total = sum(_chain_len_units(e[5], coords) for e in edges)
    stats = {"nodes_before": len(nodes), "edges_before": len(edges)}
    kept, ncomp = _largest_scc(edges, z, coords)
    stats["components"] = ncomp
    if crop is not None:
        kept = [e for e in kept if any(crop(*coords[v]) for v in e[5])]
        km_total = sum(_chain_len_units(e[5], coords) for e in edges if any(crop(*coords[v]) for v in e[5]))
        stats["edges_in_crop"] = len(kept)
        kept, _n = _largest_scc(kept, z, coords)
    km_kept = sum(_chain_len_units(e[5], coords) for e in kept)
    stats["edges_kept"] = len(kept)
    stats["length_share_kept"] = round(km_kept / km_total, 4) if km_total else 1.0
    log(f"  [{name}] components {ncomp}, kept {len(kept)}/{len(edges)} edges,"
        f" {stats['length_share_kept'] * 100:.1f}% of length (within crop)")
    # 6. simplify shapes, convert to lng/lat ints (1e-5 deg)
    scale = 100000
    n2 = 1 << z
    world = EXTENT * n2

    def ll(v):
        gx, gy = coords[v]
        lng = gx / world * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * gy / world))))
        return round(lng * scale), round(lat * scale)

    kept_nodes = sorted({e[0] for e in kept} | {e[1] for e in kept}, key=lambda v: morton(*coords[v]))
    nid = {v: i for i, v in enumerate(kept_nodes)}
    node_ll = [ll(v) for v in kept_nodes]
    out_edges = []
    for a, b, c, f, bw, chain in kept:
        pts = [coords[v] for v in chain]
        keep_idx = douglas_peucker(pts, simplify_units) if simplify_units > 0 else range(len(pts))
        shape = [ll(chain[i]) for i in keep_idx][1:-1]
        A, B = nid[a], nid[b]
        if not f:  # only b->a allowed: flip so that the stored direction is the allowed one
            A, B, shape = B, A, shape[::-1]
            f, bw = True, False
        full = [node_ll[A]] + shape + [node_ll[B]]
        length = sum(haversine((full[i][0] / scale, full[i][1] / scale), (full[i + 1][0] / scale, full[i + 1][1] / scale))
                     for i in range(len(full) - 1))
        oneway = 0 if bw else 1
        out_edges.append((A, B, c, oneway, max(1, round(length * 10)), shape))
    out_edges.sort(key=lambda e: (e[0], e[1]))
    nodes_flat = []
    px = py = 0
    for x, y in node_ll:
        nodes_flat += [x - px, y - py]
        px, py = x, y
    e_flat, shape_n, shape_flat = [], [], []
    for A, B, c, ow, L, shape in out_edges:
        e_flat += [A, B, c | (ow << 4), L]
        shape_n.append(len(shape))
        px, py = node_ll[A]
        for x, y in shape:
            shape_flat += [x - px, y - py]
            px, py = x, y
    lngs = [p[0] for p in node_ll]
    lats = [p[1] for p in node_ll]
    stats.update(nodes=len(node_ll), edges=len(out_edges), shape_points=len(shape_flat) // 2,
                 oneway_edges=sum(1 for e in out_edges if e[3]),
                 length_km=round(sum(e[4] for e in out_edges) / 10000.0, 1),
                 km_by_class={classes[i]: round(sum(e[4] for e in out_edges if e[2] == i) / 10000.0, 1)
                              for i in range(len(classes))})
    log(f"  [{name}] done in {time.time() - t0:.1f}s: {stats['nodes']} nodes, {stats['edges']} edges,"
        f" {stats['shape_points']} shape pts, {stats['length_km']} km")
    return {
        "nodes": nodes_flat, "edges": e_flat, "shape_n": shape_n, "shape": shape_flat,
        "bbox": [min(lngs) / scale, min(lats) / scale, max(lngs) / scale, max(lats) / scale],
        "stats": stats,
    }


def _largest_scc(edges, z, coords):
    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges})
    idx = {v: i for i, v in enumerate(nodes)}
    out_adj = [[] for _ in nodes]
    in_adj = [[] for _ in nodes]
    for a, b, _c, f, bw, _ch in edges:
        ia, ib = idx[a], idx[b]
        if f:
            out_adj[ia].append(ib)
            in_adj[ib].append(ia)
        if bw:
            out_adj[ib].append(ia)
            in_adj[ia].append(ib)
    comp = scc(len(nodes), out_adj, in_adj)
    sizes = collections.Counter(comp)
    big, _bigsize = sizes.most_common(1)[0]
    if os.environ.get("GEONET_DEBUG"):
        world = EXTENT * (1 << z)
        for cid, cnt in sizes.most_common(8)[1:]:
            gx, gy = coords[nodes[comp.index(cid)]]
            log(f"    component {cid}: {cnt} nodes near {gx / world * 360 - 180:.5f},{y2lat(gy / EXTENT, z):.5f}")
    return [e for e in edges if comp[idx[e[0]]] == big and comp[idx[e[1]]] == big], len(sizes)


def _chain_len_units(chain, coords):
    s = 0.0
    for i in range(len(chain) - 1):
        (x1, y1), (x2, y2) = coords[chain[i]], coords[chain[i + 1]]
        s += math.hypot(x2 - x1, y2 - y1)
    return s


def morton(x, y):
    x, y = int(x) >> 6, int(y) >> 6
    r = 0
    for i in range(24):
        r |= ((x >> i) & 1) << (2 * i) | ((y >> i) & 1) << (2 * i + 1)
    return r


def douglas_peucker(pts, tol):
    n = len(pts)
    if n <= 2:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        (x1, y1), (x2, y2) = pts[i], pts[j]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        best, bk = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            if L == 0:
                d = math.hypot(px - x1, py - y1)
            else:
                d = abs(dy * (px - x1) - dx * (py - y1)) / L
            if d > best:
                best, bk = d, k
        if bk >= 0 and best > tol:
            keep[bk] = True
            stack.append((i, bk))
            stack.append((bk, j))
    return [k for k in range(n) if keep[k]]


def scc(n, out_adj, in_adj):
    """Kosaraju, iterative. Returns component id per node."""
    order = []
    seen = [False] * n
    for s in range(n):
        if seen[s]:
            continue
        seen[s] = True
        stack = [(s, 0)]
        while stack:
            v, i = stack[-1]
            if i < len(out_adj[v]):
                stack[-1] = (v, i + 1)
                w = out_adj[v][i]
                if not seen[w]:
                    seen[w] = True
                    stack.append((w, 0))
            else:
                stack.pop()
                order.append(v)
    comp = [-1] * n
    c = 0
    for s in reversed(order):
        if comp[s] != -1:
            continue
        comp[s] = c
        stack = [s]
        while stack:
            v = stack.pop()
            for w in in_adj[v]:
                if comp[w] == -1:
                    comp[w] = c
                    stack.append(w)
        c += 1
    return comp


def write_graph(path: Path, meta: dict, g: dict):
    doc = dict(meta)
    doc.update(g)
    raw = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(gzip.compress(raw, compresslevel=9, mtime=0))
    log(f"  wrote {path.relative_to(REPO)}: {path.stat().st_size / 1e6:.2f} MB (raw {len(raw) / 1e6:.1f} MB)")


def collect_pieces(fetcher, tiles, classes, procs):
    jobs = [(str(fetcher.path(*t)), t[0], t[1], t[2], classes) for t in tiles]
    pieces = []
    with cf.ProcessPoolExecutor(procs) as ex:
        for res in ex.map(tile_roads, jobs, chunksize=8):
            pieces.extend(res)
    return pieces


def units_per_m(z, lat):
    return EXTENT * (1 << z) / (40075016.686 * math.cos(math.radians(lat)))


def build_national(fetcher, args, rings):
    z = args.national_zoom
    tiles = sweden_tiles(z, rings)
    fetcher.fetch_all(tiles)
    log(f"national: decoding {len(tiles)} z{z} tiles")
    classes = NATIONAL_CLASSES if args.tertiary else NATIONAL_CLASSES[:4]
    pieces = collect_pieces(fetcher, tiles, classes, args.procs)
    upm = units_per_m(z, 62.0)
    g = build_graph("national", z, pieces, classes, tol_units=max(1.5, 2.0 * upm),
                    simplify_units=args.national_simplify_m * upm)
    meta = {"version": 1, "kind": "roadnet", "name": "national", "zoom": z, "classes": classes,
            "source": f"OpenFreeMap {fetcher.version} transportation z{z}", "licence": LICENCE, "scale": 100000,
            "tiles": len(tiles)}
    write_graph(OUT_DIR / "national.json.gz", meta, g)
    return g["stats"]


def city_fetch_radius(r_km):
    """Fetch a margin around each city so connectivity through the outskirts is known."""
    return r_km + max(1.5, 0.3 * r_km)


# Whole-island / region street graphs, exposed like cities. Built at z13 (minor roads are
# present from z13; z14 would need ~4x the tiles for ~1 m of extra fidelity on mostly-sea tiles).
REGIONS = {
    "gotland": {"bbox": (18.05, 56.88, 19.35, 57.98), "zoom": 13, "ferries": True},
}


def build_regions(fetcher, args):
    stats = {}
    for nm, spec in REGIONS.items():
        if args.cities and nm not in args.cities.split(","):
            continue
        z = spec["zoom"]
        tiles = tiles_in_bbox(z, *spec["bbox"])
        fetcher.fetch_all(tiles)
        classes = CITY_CLASSES + (["ferry"] if spec.get("ferries") else [])
        log(f"region {nm}: {len(tiles)} z{z} tiles")
        pieces = collect_pieces(fetcher, tiles, classes, args.procs)
        lat = (spec["bbox"][1] + spec["bbox"][3]) / 2
        upm = units_per_m(z, lat)
        g = build_graph(nm, z, pieces, classes, tol_units=max(1.5, 1.0 * upm),
                        simplify_units=args.city_simplify_m * upm,
                        ferry_class=classes.index("ferry") if spec.get("ferries") else None,
                        ferry_tol_units=300.0 * upm)
        meta = {"version": 1, "kind": "roadnet", "name": nm, "zoom": z, "classes": classes,
                "source": f"OpenFreeMap {fetcher.version} transportation z{z}", "licence": LICENCE,
                "scale": 100000, "region_bbox": list(spec["bbox"])}
        write_graph(OUT_DIR / f"city_{nm}.json.gz", meta, g)
        stats[nm] = g["stats"]
    return stats


def build_cities(fetcher, args):
    z = 14
    names = [n for n in CITIES if not args.cities or n in args.cities.split(",")]
    if not names:
        return {}
    allt = {}
    for nm in names:
        lng, lat, r = CITIES[nm]
        allt[nm] = circle_tiles(z, lng, lat, city_fetch_radius(r))
    fetcher.fetch_all(sorted({t for v in allt.values() for t in v}))
    stats = {}
    for nm in names:
        lng, lat, r = CITIES[nm]
        log(f"city {nm}: {len(allt[nm])} tiles")
        pieces = collect_pieces(fetcher, allt[nm], CITY_CLASSES, args.procs)
        upm = units_per_m(z, lat)
        cx, cy = lng2x(lng, z) * EXTENT, lat2y(lat, z) * EXTENT
        rr = r * 1000.0 * upm

        def crop(gx, gy, cx=cx, cy=cy, rr=rr):
            return (gx - cx) ** 2 + (gy - cy) ** 2 <= rr * rr

        g = build_graph(nm, z, pieces, CITY_CLASSES, tol_units=max(1.5, 1.0 * upm),
                        simplify_units=args.city_simplify_m * upm, crop=crop)
        meta = {"version": 1, "kind": "roadnet", "name": nm, "zoom": z, "classes": CITY_CLASSES,
                "source": f"OpenFreeMap {fetcher.version} transportation z{z}", "licence": LICENCE,
                "scale": 100000, "center": [lng, lat], "radius_km": r}
        write_graph(OUT_DIR / f"city_{nm}.json.gz", meta, g)
        stats[nm] = g["stats"]
    return stats


# ---------------------------------------------------------------------------
# Sea mask
# ---------------------------------------------------------------------------

def sea_dims():
    lng0, lat0, lng1, lat1 = SEA_BBOX
    dlng, dlat = SEA_FINE
    return round((lng1 - lng0) / dlng), round((lat1 - lat0) / dlat)


def tile_ocean_spans(args):
    """Worker: rasterise class=ocean/river polygons of one tile into fine-grid row spans
    [(kind, row, col0, col1)] with kind 1 = ocean, 2 = river."""
    path, z, tx, ty = args
    data = Path(path).read_bytes()
    if not data:
        return []
    try:
        extent, feats = decode_layer(data, "water", lambda p: p.get("class") in ("ocean", "river"))
    except ValueError as e:
        print(f"bad tile {z}/{tx}/{ty}: {e}", file=sys.stderr)
        return []
    if not feats:
        return []
    lng0, lat0, lng1, lat1 = SEA_BBOX
    dlng, dlat = SEA_FINE
    W, H = sea_dims()
    tw, ts, te, tn = tile_bbox(z, tx, ty)
    # fine rows whose centre latitude lies inside this tile
    r0 = max(0, math.ceil((lat1 - tn) / dlat - 0.5))
    r1 = min(H - 1, math.floor((lat1 - ts) / dlat - 0.5))
    c0 = max(0, math.ceil((tw - lng0) / dlng - 0.5))
    c1 = min(W - 1, math.floor((te - lng0) / dlng - 0.5))
    if r0 > r1 or c0 > c1:
        return []
    n = 1 << z
    rows_y = {}
    for r in range(r0, r1 + 1):
        lat = lat1 - (r + 0.5) * dlat
        rows_y[r] = (lat2y(lat, z) - ty) * extent
    ys_sorted = sorted((y, r) for r, y in rows_y.items())
    ys_only = [y for y, _ in ys_sorted]
    import bisect
    spans = []
    for gtype, props, parts in feats:
        if gtype != 3:
            continue
        kind = 1 if props.get("class") == "ocean" else 2
        cross = collections.defaultdict(list)
        for ring in parts:
            m = len(ring)
            for i in range(m):
                x1, y1 = ring[i]
                x2, y2 = ring[(i + 1) % m]
                if y1 == y2:
                    continue
                ya, yb = (y1, y2) if y1 < y2 else (y2, y1)
                k = bisect.bisect_left(ys_only, ya)
                while k < len(ys_only) and ys_only[k] < yb:
                    yr, r = ys_sorted[k]
                    x = x1 + (yr - y1) * (x2 - x1) / (y2 - y1)
                    cross[r].append(x)
                    k += 1
        for r, xs in cross.items():
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                la = x2lng(tx + xs[i] / extent, z)
                lb = x2lng(tx + xs[i + 1] / extent, z)
                ca = max(c0, math.ceil((la - lng0) / dlng - 0.5))
                cb = min(c1, math.ceil((lb - lng0) / dlng - 0.5) - 1)
                if ca <= cb:
                    spans.append((kind, r, ca, cb))
    return spans


def build_sea(fetcher, args):
    z = args.sea_zoom
    tiles = tiles_in_bbox(z, *SEA_BBOX)
    fetcher.fetch_all(tiles)
    W, H = sea_dims()
    log(f"sea: rasterising {len(tiles)} z{z} tiles into {W}x{H} fine grid")
    fine = bytearray(W * H)
    river = bytearray(W * H)
    jobs = [(str(fetcher.path(*t)), *t) for t in tiles]
    with cf.ProcessPoolExecutor(args.procs) as ex:
        for spans in ex.map(tile_ocean_spans, jobs, chunksize=8):
            for kind, r, a, b in spans:
                o = r * W
                (fine if kind == 1 else river)[o + a:o + b + 1] = b"\x01" * (b - a + 1)
    log(f"  ocean share {sum(fine) / len(fine):.3f}")
    # River polygons count as sea only where they connect to the ocean, up to
    # args.river_cells fine cells upstream (harbour reaches such as Gota alv in Goteborg).
    frontier = []
    i = river.find(1)
    while i != -1:
        if not fine[i]:
            r, c = divmod(i, W)
            if any(fine[rr * W + cc] for rr in (r - 1, r, r + 1) for cc in (c - 1, c, c + 1)
                   if 0 <= rr < H and 0 <= cc < W):
                frontier.append(i)
        i = river.find(1, i + 1)
    added = 0
    for i in frontier:
        fine[i] = 1
    for _depth in range(args.river_cells):
        added += len(frontier)
        nxt = []
        for i in frontier:
            r, c = divmod(i, W)
            for rr in (r - 1, r, r + 1):
                for cc in (c - 1, c, c + 1):
                    if 0 <= rr < H and 0 <= cc < W:
                        j = rr * W + cc
                        if river[j] and not fine[j]:
                            fine[j] = 1
                            nxt.append(j)
        frontier = nxt
        if not frontier:
            break
    log(f"  {added} sea-connected river cells added; water share {sum(fine) / len(fine):.3f}")
    # routing grid: cell navigable iff all fine sub-cells are water
    F = SEA_ROUTE_FACTOR
    RW, RH = W // F, H // F
    route = bytearray(RW * RH)
    for R in range(RH):
        rows = [fine[(R * F + k) * W:(R * F + k + 1) * W] for k in range(F)]
        base = R * RW
        for C in range(RW):
            ok = 1
            for row in rows:
                if 0 in row[C * F:(C + 1) * F]:
                    ok = 0
                    break
            route[base + C] = ok
    # keep the largest 8-connected (no corner cutting) water component
    comp = bytearray(RW * RH)
    best_seed, best_n = -1, 0
    label_seen = bytearray(RW * RH)
    for start in range(RW * RH):
        if not route[start] or label_seen[start]:
            continue
        n = _flood(route, label_seen, start, RW, RH)
        if n > best_n:
            best_seed, best_n = start, n
    _flood(route, comp, best_seed, RW, RH)
    log(f"  main navigable component: {best_n} cells of {sum(route)}")
    # clearance classes: 1 = >=3 cells from land, 2 = 2 cells, 3 = adjacent to land
    land = bytes(1 - v for v in comp)
    dist = bytearray(RW * RH)
    frontier = [i for i in range(RW * RH) if land[i]]
    for i in frontier:
        dist[i] = 0
    level = bytearray(RW * RH)
    for i in frontier:
        level[i] = 1
    cur = frontier
    ring_cls = {1: 3, 2: 2}
    for d in (1, 2):
        nxt = []
        for i in cur:
            r, c = divmod(i, RW)
            for dr in (-1, 0, 1):
                rr = r + dr
                if rr < 0 or rr >= RH:
                    continue
                for dc in (-1, 0, 1):
                    cc = c + dc
                    if 0 <= cc < RW:
                        j = rr * RW + cc
                        if not level[j]:
                            level[j] = 1
                            nxt.append(j)
        for j in nxt:
            dist[j] = ring_cls[d]
        cur = nxt
    out = bytearray(RW * RH)
    for i in range(RW * RH):
        if comp[i]:
            out[i] = dist[i] if dist[i] else 1
    # pack fine mask bits (LSB first)
    packed = bytearray((W * H + 7) // 8)
    for i in range(0, W * H, 8):
        chunk = fine[i:i + 8]
        v = 0
        for k, bit in enumerate(chunk):
            if bit:
                v |= 1 << k
        packed[i >> 3] = v
    header = {
        "version": 1, "kind": "seagrid", "bbox": list(SEA_BBOX), "fine": {"w": W, "h": H, "dlng": SEA_FINE[0], "dlat": SEA_FINE[1]},
        "route": {"w": RW, "h": RH, "factor": F, "values": {"0": "not navigable", "1": "open water",
                                                              "2": "2 cells from land", "3": "adjacent to land"}},
        "source": f"OpenFreeMap {fetcher.version} water class=ocean (+ sea-connected river, {args.river_cells} cells) z{z}", "licence": LICENCE,
        "row0": "north", "bits": "LSB-first, row-major from the north-west corner",
    }
    a = zlib.compress(bytes(packed), 9)
    b = zlib.compress(bytes(out), 9)
    header["fine"]["zlen"] = len(a)
    header["route"]["zlen"] = len(b)
    hj = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path = OUT_DIR / "sea.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"TROSSEA1")
        fh.write(struct.pack("<I", len(hj)))
        fh.write(hj)
        fh.write(a)
        fh.write(b)
    log(f"  wrote {path.relative_to(REPO)}: {path.stat().st_size / 1e6:.2f} MB")
    return {"fine": [W, H], "route": [RW, RH], "main_component_cells": best_n, "water_share": round(sum(fine) / len(fine), 4)}


def _flood(grid, mark, start, W, H):
    """8-connected flood fill without corner cutting; marks cells with 1, returns count."""
    mark[start] = 1
    stack = [start]
    n = 0
    while stack:
        i = stack.pop()
        n += 1
        r, c = divmod(i, W)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            rr, cc = r + dr, c + dc
            if rr < 0 or rr >= H or cc < 0 or cc >= W:
                continue
            j = rr * W + cc
            if not grid[j] or mark[j]:
                continue
            if dr and dc and not (grid[r * W + cc] and grid[rr * W + c]):
                continue
            mark[j] = 1
            stack.append(j)
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", required=True, help="tile cache directory (outside the repo)")
    ap.add_argument("--steps", default="national,cities,regions,sea")
    ap.add_argument("--cities", default="", help="comma-separated subset of cities")
    ap.add_argument("--national-zoom", type=int, default=11)
    ap.add_argument("--tertiary", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--national-simplify-m", type=float, default=2.0)
    ap.add_argument("--city-simplify-m", type=float, default=0.7)
    ap.add_argument("--sea-zoom", type=int, default=10)
    ap.add_argument("--river-cells", type=int, default=60, help="fine cells (~280 m) of sea-connected river kept as water")
    ap.add_argument("--workers", type=int, default=6, help="concurrent downloads (max 6)")
    ap.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 1), help="decode processes")
    args = ap.parse_args()
    cache = Path(args.cache).resolve()
    if REPO in cache.parents or cache == REPO:
        sys.exit("cache directory must be outside the repository")
    fetcher = Fetcher(cache, args.workers)
    log(f"tiles: {fetcher.template}")
    steps = set(args.steps.split(","))
    report = {}
    rings = load_sweden()
    if "national" in steps:
        report["national"] = build_national(fetcher, args, rings)
    if "cities" in steps:
        report["cities"] = build_cities(fetcher, args)
    if "regions" in steps:
        report["regions"] = build_regions(fetcher, args)
    if "sea" in steps:
        report["sea"] = build_sea(fetcher, args)
    log(f"downloaded {fetcher.fetched} tiles this run")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
