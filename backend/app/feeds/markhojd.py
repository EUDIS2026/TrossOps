"""Lantmäteriet Markhöjd Direkt: ground elevation (national elevation model, 1–2 m grid) for points and lines.

Unlike the other feeds this one is queried on demand: `profile(coords)` samples the ground under a route and
`line_of_sight(a, b)` checks terrain masking between two points. The periodic `fetch` is only a health check so the
source panel shows whether the service answers.

The API takes SWEREF 99 TM (EPSG:3006) coordinates; `to_sweref99tm` is the Gauss–Krüger forward projection with
Lantmäteriet's published series. A LineString holds at most 1 000 vertices per request.

Free licence ("Användningsvillkor för värdefulla datamängder"), ordered on geotorget.lantmateriet.se. Credentials, first
match wins: `LANTMATERIET_USERNAME` + `LANTMATERIET_PASSWORD` (the Geotorget account, HTTP Basic, which is what an order
grants), a ready `LANTMATERIET_TOKEN` (Bearer), or `LANTMATERIET_CLIENT_ID` + `LANTMATERIET_CLIENT_SECRET` (OAuth2
client credentials via the API portal).
"""
from __future__ import annotations

import base64
import math
import os
import threading
import time
from collections import OrderedDict

import httpx

from .base import Feed, FeedError, describe, feeds_disabled

API = "https://api.lantmateriet.se/distribution/produkter/markhojd/v1"
TOKEN_URL = "https://apimanager.lantmateriet.se/oauth2/token"
MAX_VERTICES = 1000
NODATA = -9999
EARTH_R = 6_371_000.0
REFRACTION_K = 0.13  # standard atmospheric refraction coefficient for line of sight

# GRS80 / SWEREF 99 TM
_A, _F = 6378137.0, 1 / 298.257222101
_LON0, _K0, _FE = 15.0, 0.9996, 500_000.0
_E2 = _F * (2 - _F)
_N = _F / (2 - _F)
_AR = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_CA = _E2
_CB = (5 * _E2 ** 2 - _E2 ** 3) / 6
_CC = (104 * _E2 ** 3 - 45 * _E2 ** 4) / 120
_CD = 1237 * _E2 ** 4 / 1260
_BETA = (_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16 + 41 * _N ** 4 / 180,
         13 * _N ** 2 / 48 - 3 * _N ** 3 / 5 + 557 * _N ** 4 / 1440,
         61 * _N ** 3 / 240 - 103 * _N ** 4 / 140,
         49561 * _N ** 4 / 161280)


def to_sweref99tm(lng: float, lat: float) -> tuple[float, float]:
    """WGS84 / ETRS89 degrees -> SWEREF 99 TM (easting, northing) in metres."""
    phi, dl = math.radians(lat), math.radians(lng - _LON0)
    s = math.sin(phi) ** 2
    phi_c = phi - math.sin(phi) * math.cos(phi) * (_CA + _CB * s + _CC * s ** 2 + _CD * s ** 3)
    xi = math.atan2(math.tan(phi_c), math.cos(dl))
    eta = math.atanh(math.cos(phi_c) * math.sin(dl))
    x, y = xi, eta
    for j, b in enumerate(_BETA, start=1):
        x += b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        y += b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    return _K0 * _AR * y + _FE, _K0 * _AR * x


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(h)))


def resample(coords: list[tuple[float, float]], n: int) -> tuple[list[tuple[float, float]], list[float]]:
    """n points evenly spaced along the polyline, with their distance from the start (m)."""
    if len(coords) < 2:
        return list(coords), [0.0] * len(coords)
    seg = [_haversine(a, b) for a, b in zip(coords, coords[1:])]
    total = sum(seg)
    if total <= 0:
        return [coords[0]], [0.0]
    n = max(2, n)
    out, dist = [], []
    i, acc = 0, 0.0
    for k in range(n):
        d = total * k / (n - 1)
        while i < len(seg) - 1 and acc + seg[i] < d:
            acc += seg[i]
            i += 1
        f = 0.0 if seg[i] == 0 else min(1.0, max(0.0, (d - acc) / seg[i]))
        a, b = coords[i], coords[i + 1]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        dist.append(d)
    return out, dist


def in_sweden_box(lng: float, lat: float) -> bool:
    return 10.0 <= lng <= 24.5 and 55.0 <= lat <= 69.2


class MarkhojdFeed(Feed):
    id = "lm-markhojd"
    label = "Lantmäteriet Markhöjd Direkt"
    category = "terrain"
    url = "https://geotorget.lantmateriet.se/geodataprodukter/markhojd-direkt-api"
    licence = "Lantmäteriet, användningsvillkor för värdefulla datamängder (free)"
    attribution = "Elevation © Lantmäteriet"
    ttl_s = 900.0
    note = "Ground elevation from the national elevation model; sampled along planned routes and for line of sight."
    credential_help = "Order Markhöjd Direkt (free) on geotorget.lantmateriet.se."

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        super().__init__(transport)
        self._token: tuple[str, float] | None = None
        self._token_lock = threading.Lock()
        self._cache: OrderedDict[tuple, list[float | None]] = OrderedDict()

    def reset(self) -> None:
        super().reset()
        self._token = None
        self._cache.clear()

    def missing_credentials(self) -> list[str]:
        if os.environ.get("LANTMATERIET_TOKEN"):
            return []
        for pair in (("LANTMATERIET_USERNAME", "LANTMATERIET_PASSWORD"), ("LANTMATERIET_CLIENT_ID", "LANTMATERIET_CLIENT_SECRET")):
            if all(os.environ.get(k) for k in pair):
                return []
        return ["LANTMATERIET_USERNAME", "LANTMATERIET_PASSWORD"]

    def available(self) -> bool:
        return not feeds_disabled() and not self.missing_credentials()

    def _headers(self, client: httpx.Client) -> dict:
        user, password = os.environ.get("LANTMATERIET_USERNAME"), os.environ.get("LANTMATERIET_PASSWORD")
        if user and password:
            basic = base64.b64encode(f"{user}:{password}".encode()).decode()
            return {"Authorization": f"Basic {basic}", "Accept": "application/json"}
        static = os.environ.get("LANTMATERIET_TOKEN")
        if static:
            return {"Authorization": f"Bearer {static}", "Accept": "application/json"}
        with self._token_lock:
            if self._token is None or time.time() > self._token[1] - 60:
                r = client.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                                auth=(os.environ["LANTMATERIET_CLIENT_ID"], os.environ["LANTMATERIET_CLIENT_SECRET"]))
                r.raise_for_status()
                body = r.json()
                self._token = (body["access_token"], time.time() + float(body.get("expires_in", 3600)))
            return {"Authorization": f"Bearer {self._token[0]}", "Accept": "application/json"}

    def fetch(self, client: httpx.Client) -> dict:
        e, n = to_sweref99tm(18.0686, 59.3293)  # health check: one point in central Stockholm
        r = client.get(f"{API}/hojd", params={"srid": 3006, "e": round(e, 2), "n": round(n, 2)}, headers=self._headers(client))
        r.raise_for_status()
        z = r.json()["geometry"]["coordinates"][2]
        return {"count": 1, "probe": {"lng": 18.0686, "lat": 59.3293, "elevationM": z}}

    def count_of(self, data: dict) -> int:
        return int(data.get("count") or 0)

    def empty(self) -> dict:
        return {"count": 0}

    # ---- on-demand queries ------------------------------------------------------------------------------------------
    def elevations(self, points: list[tuple[float, float]]) -> list[float | None]:
        """Ground elevation (m, RH 2000) under each lng/lat point; None where there is no data. Raises FeedError."""
        if not self.available():
            raise FeedError("Markhöjd Direkt not configured")
        key = tuple((round(p[0], 5), round(p[1], 5)) for p in points)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        client = self.client()
        out: list[float | None] = []
        try:
            for i in range(0, len(points), MAX_VERTICES):
                chunk = points[i:i + MAX_VERTICES]
                if len(chunk) == 1:  # a one-vertex LineString is rejected (HTTP 400): use the point query
                    e, n = to_sweref99tm(*chunk[0])
                    r = client.get(f"{API}/hojd", params={"srid": 3006, "e": round(e, 2), "n": round(n, 2)}, headers=self._headers(client))
                    r.raise_for_status()
                    z = r.json()["geometry"]["coordinates"][2]
                    out.append(None if z is None or z <= NODATA + 1 else round(float(z), 1))
                    continue
                geom = {"type": "LineString", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3006"}},
                        "coordinates": [[round(c, 2) for c in to_sweref99tm(*p)] for p in chunk]}
                r = client.post(f"{API}/hojd", json=geom, headers={**self._headers(client), "Content-Type": "application/json"})
                r.raise_for_status()
                coords = r.json()["geometry"]["coordinates"]
                zs = [None if len(c) < 3 or c[2] is None or c[2] <= NODATA + 1 else round(float(c[2]), 1) for c in coords]
                out += zs[:len(points[i:i + MAX_VERTICES])]
        except FeedError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._last_error, self._last_error_at = describe(exc), time.time()
            raise FeedError(describe(exc)) from exc
        self._cache[key] = out
        while len(self._cache) > 64:
            self._cache.popitem(last=False)
        return out

    def profile(self, coords: list[tuple[float, float]], samples: int = 200) -> dict:
        pts, dist = resample(coords, samples)
        zs = self.elevations(pts)
        valid = [z for z in zs if z is not None]
        climb = sum(max(0.0, b - a) for a, b in zip(valid, valid[1:]))
        return {"distanceM": [round(d) for d in dist], "groundM": zs, "points": [[round(p[0], 6), round(p[1], 6)] for p in pts],
                "minM": min(valid) if valid else None, "maxM": max(valid) if valid else None, "climbM": round(climb),
                "source": self.attribution}

    def line_of_sight(self, a: tuple[float, float], b: tuple[float, float], h_a: float = 2.0, h_b: float = 2.0, samples: int = 300) -> dict:
        """Terrain masking between two points with earth curvature and standard refraction (bare earth: no trees or buildings)."""
        prof = self.profile([a, b], samples)
        d, g = prof["distanceM"], prof["groundM"]
        if g[0] is None or g[-1] is None:
            raise FeedError("no elevation at an end point (outside Sweden?)")
        total = d[-1] or 1.0
        za, zb = g[0] + h_a, g[-1] + h_b
        r_eff = EARTH_R / (1 - REFRACTION_K)
        worst, block = math.inf, None
        clearance = []
        for di, gi, p in zip(d, g, prof["points"]):
            if gi is None or di in (0, total):
                clearance.append(None)
                continue
            sight = za + (zb - za) * di / total - di * (total - di) / (2 * r_eff)
            c = sight - gi
            clearance.append(round(c, 1))
            if c < worst:
                worst = c
                block = {"lng": p[0], "lat": p[1], "distanceM": di, "groundM": gi}
        return {"visible": worst > 0, "minClearanceM": None if worst is math.inf else round(worst, 1), "obstruction": block if worst <= 0 else None,
                "distanceM": round(total), "observerM": h_a, "targetM": h_b, "profile": {**prof, "clearanceM": clearance},
                "method": f"bare-earth line of sight, {samples} samples, earth curvature with refraction k={REFRACTION_K}"}
