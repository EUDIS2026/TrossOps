"""RainViewer radar mosaic frames (public weather-maps.json index + XYZ PNG tiles).

Free-tier constraints encoded here: 256 px tiles, max zoom 7 (zoom 8+ returns a placeholder tile), colour scheme 2
("Universal Blue") with smoothing + snow (`1_1`); `nowcast` and satellite are currently empty in the free index.
Attribution with a link to rainviewer.com is required.
"""
from __future__ import annotations

import httpx

from .base import Feed, FeedError, iso

INDEX_URL = "https://api.rainviewer.com/public/weather-maps.json"
TILE_SIZE = 256
MAX_ZOOM = 7
COLOR_SCHEME = 2
OPTIONS = "1_1"


def tile_url(host: str, path: str) -> str:
    return f"{host}{path}/{TILE_SIZE}/{{z}}/{{x}}/{{y}}/{COLOR_SCHEME}/{OPTIONS}.png"


def normalise(body: dict) -> dict:
    host = body.get("host")
    radar = body.get("radar") or {}
    if not host or not isinstance(radar.get("past"), list):
        raise FeedError("unexpected payload (missing host/radar.past)")

    def frames(rows):
        return [{"time": f.get("time"), "timeIso": iso(f.get("time")), "path": f.get("path"),
                 "tileUrl": tile_url(host, f.get("path"))} for f in rows or [] if f.get("path")]

    past = frames(radar.get("past"))
    return {"host": host, "generated": iso(body.get("generated")), "frames": past, "nowcast": frames(radar.get("nowcast")),
            "latest": past[-1] if past else None, "maxZoom": MAX_ZOOM, "tileSize": TILE_SIZE, "colorScheme": COLOR_SCHEME,
            "options": OPTIONS}


class RainViewerFeed(Feed):
    id = "rainviewer"
    label = "RainViewer radar mosaic"
    category = "weather"
    url = INDEX_URL
    licence = "RainViewer API terms (free tier, attribution required)"
    attribution = "Radar: RainViewer (rainviewer.com)"
    ttl_s = 300.0
    note = "Composite radar tiles, 10-minute frames for the past ~2 h; free tier max zoom 7 (overzoom above)."

    def fetch(self, client: httpx.Client) -> dict:
        r = client.get(INDEX_URL)
        r.raise_for_status()
        return normalise(r.json())

    def count_of(self, data: dict) -> int:
        return len(data.get("frames") or [])

    def empty(self) -> dict:
        return {"frames": [], "nowcast": [], "maxZoom": MAX_ZOOM, "tileSize": TILE_SIZE}
