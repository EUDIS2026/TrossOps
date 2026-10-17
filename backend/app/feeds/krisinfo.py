"""Krisinformation.se (MSB) v3 API: news (`/v3/news?days=3`) and VMA public warnings (`/v3/vmas`).

v3 responses are lists of camelCase objects (`identifier`, `headline`, `preamble`, `published`, `web`, `area[]` with
`type`, `description`, `coordinate`, `coordinateObject`). Field casing is matched case-insensitively so the parser
also accepts the PascalCase variant used by older API versions. Area coordinates are optional; when present the item
gets the mean of the area points. The coordinate string order (lat,lng vs lng,lat) is resolved by Swedish value
ranges (lat 54-70, lng 10-25 never overlap).
"""
from __future__ import annotations

import re

import httpx

from .base import Feed, FeedError, describe, parallel

NEWS_URL = "https://api.krisinformation.se/v3/news?days=3"
VMAS_URL = "https://api.krisinformation.se/v3/vmas"
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def field(obj: dict, name: str):
    if not isinstance(obj, dict):
        return None
    if name in obj:
        return obj[name]
    lname = name.lower()
    for key, value in obj.items():
        if key.lower() == lname:
            return value
    return None


def _order(a: float, b: float) -> tuple[float, float] | None:
    """Return (lng, lat) from an unordered Swedish coordinate pair."""
    if 53 <= a <= 71 and 4 <= b <= 32:
        return b, a
    if 53 <= b <= 71 and 4 <= a <= 32:
        return a, b
    return None


def area_point(area: dict) -> tuple[float, float] | None:
    obj = field(area, "coordinateObject")
    if isinstance(obj, dict):
        lat, lng = field(obj, "latitude"), field(obj, "longitude")
        try:
            return float(lng), float(lat)
        except (TypeError, ValueError):
            pass
    text = field(area, "coordinate")
    if isinstance(text, str):
        nums = [float(n) for n in _NUM_RE.findall(text)]
        if len(nums) >= 2:
            return _order(nums[0], nums[1])
    return None


def normalise(item: dict, kind: str) -> dict:
    areas = [a for a in field(item, "area") or [] if isinstance(a, dict)]
    points = [p for p in (area_point(a) for a in areas) if p]
    lng = round(sum(p[0] for p in points) / len(points), 5) if points else None
    lat = round(sum(p[1] for p in points) / len(points), 5) if points else None
    ident = field(item, "identifier") or field(item, "contentId")
    return {"id": f"{kind}-{ident}", "headline": field(item, "headline"), "preamble": field(item, "preamble"),
            "published": field(item, "published"), "updated": field(item, "updated"), "url": field(item, "web"),
            "areas": [field(a, "description") for a in areas if field(a, "description")],
            "areaTypes": [field(a, "type") for a in areas if field(a, "type")], "lng": lng, "lat": lat, "kind": kind,
            "event": field(item, "event")}



def decode_json(raw: bytes):
    """Krisinformation declares UTF-8 but has been seen serving Latin-1 bytes; decode strictly, then fall back."""
    import json
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return json.loads(raw.decode("cp1252"))


class KrisinfoFeed(Feed):
    id = "krisinformation"
    label = "Krisinformation.se news and VMA"
    category = "civil"
    url = "https://api.krisinformation.se/v3/"
    licence = "Open API from MSB / Krisinformation.se; verify reuse terms on krisinformation.se"
    attribution = "Källa: Krisinformation.se (MSB)"
    ttl_s = 300.0
    note = "Official crisis news (last 3 days) and active VMA (Viktigt meddelande till allmänheten). Empty VMA list = no active VMA."

    def _get(self, client: httpx.Client, url: str) -> list:
        r = client.get(url)
        r.raise_for_status()
        body = decode_json(r.content)
        if not isinstance(body, list):
            raise FeedError("unexpected payload (expected a list)")
        return body

    def fetch(self, client: httpx.Client) -> dict:
        results = parallel(lambda u: self._get(client, u), [NEWS_URL, VMAS_URL])
        failures = [f"{'news' if u == NEWS_URL else 'vmas'}: {describe(e)}" for u, _, e in results if e]
        if len(failures) == len(results):
            raise FeedError("; ".join(failures))
        news = [normalise(x, "news") for x in (results[0][1] or []) if isinstance(x, dict)]
        vmas = [normalise(x, "vma") for x in (results[1][1] or []) if isinstance(x, dict)]
        data = {"items": vmas + news, "vmaCount": len(vmas), "newsCount": len(news)}
        if failures:
            data["_partial"] = failures
        return data
