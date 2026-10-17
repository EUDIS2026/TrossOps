"""Open-Meteo current conditions on a regular grid over Sweden (free non-commercial tier, CC BY 4.0, no key).

Multi-location requests: comma-separated `latitude` / `longitude`; the response is a JSON list (one object per
location, in request order) when more than one location is requested, a single object otherwise. Each location counts
as one call against the free-tier limits (10 000/day, 5 000/hour, 600/minute), so the grid is batched and cached.
Points keep their *requested* grid coordinates so the frontend can render a regular raster; the model grid point
Open-Meteo snapped to is reported as `modelLng` / `modelLat`.
"""
from __future__ import annotations

import httpx

from .base import Feed, FeedError, describe, num, parallel

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT = ("wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility,cloud_cover,cloud_cover_low,precipitation,"
           "temperature_2m,freezing_level_height,weather_code")
FIELDS = {"wind_speed_10m": "windMps", "wind_direction_10m": "windDirDeg", "wind_gusts_10m": "gustMps",
          "visibility": "visibilityM", "cloud_cover": "cloudPct", "cloud_cover_low": "cloudLowPct",
          "precipitation": "precipMm", "temperature_2m": "tempC", "freezing_level_height": "freezingLevelM",
          "weather_code": "weatherCode"}
LNG_MIN, LNG_MAX, LNG_STEP = 10.0, 25.0, 1.0
LAT_MIN, LAT_MAX, LAT_STEP = 55.0, 69.0, 0.8
BATCH = 100
# The default `best_match` model over Scandinavia returns null `freezing_level_height` (observed 2026-10, all 504 points);
# DWD ICON (seamless ICON-D2/EU/global) returns every requested variable. At a 0.6-0.75 deg grid its resolution is ample.
MODEL = "icon_seamless"


def _axis(lo: float, hi: float, step: float) -> list[float]:
    n = int(round((hi - lo) / step + 1e-9))
    return [round(lo + i * step, 4) for i in range(n + 1) if lo + i * step <= hi + 1e-9]


def grid_points(lng_step: float = LNG_STEP, lat_step: float = LAT_STEP) -> list[tuple[float, float]]:
    return [(lng, lat) for lat in _axis(LAT_MIN, LAT_MAX, lat_step) for lng in _axis(LNG_MIN, LNG_MAX, lng_step)]


def normalise(points: list[tuple[float, float]], body) -> list[dict]:
    rows = body if isinstance(body, list) else [body]
    if len(rows) != len(points):
        raise FeedError(f"expected {len(points)} locations, got {len(rows)}")
    out = []
    for (lng, lat), row in zip(points, rows):
        cur = (row or {}).get("current") or {}
        point = {"lng": lng, "lat": lat, "modelLng": num(row.get("longitude")), "modelLat": num(row.get("latitude"))}
        for key, field in FIELDS.items():
            value = num(cur.get(key))
            point[field] = int(value) if field == "weatherCode" and value is not None else value
        point["time"] = cur.get("time")
        out.append(point)
    return out


class OpenMeteoFeed(Feed):
    id = "open-meteo"
    label = "Open-Meteo current-conditions grid"
    category = "weather"
    url = FORECAST_URL
    licence = "CC BY 4.0 (free tier: non-commercial use)"
    attribution = "Weather data by Open-Meteo.com (CC BY 4.0), model DWD ICON"
    ttl_s = 3600.0  # 16 × 18 points hourly ≈ 6.9k location-calls a day, inside the 10k free tier
    note = "DWD ICON model values (via Open-Meteo) for the current 15-minute step, not observations."

    def __init__(self, transport: httpx.BaseTransport | None = None, lng_step: float = LNG_STEP, lat_step: float = LAT_STEP) -> None:
        super().__init__(transport)
        self.lng_step, self.lat_step = lng_step, lat_step

    def _batch(self, client: httpx.Client, points: list[tuple[float, float]]) -> list[dict]:
        params = {"latitude": ",".join(f"{p[1]:g}" for p in points), "longitude": ",".join(f"{p[0]:g}" for p in points),
                  "current": CURRENT, "models": MODEL, "wind_speed_unit": "ms", "timezone": "GMT"}
        r = client.get(FORECAST_URL, params=params)
        if r.status_code in (400, 429):
            reason = ""
            try:
                reason = r.json().get("reason", "")
            except Exception:  # noqa: BLE001
                pass
            raise FeedError(f"HTTP {r.status_code}: {reason}"[:200])
        r.raise_for_status()
        return normalise(points, r.json())

    def fetch(self, client: httpx.Client) -> dict:
        points = grid_points(self.lng_step, self.lat_step)
        batches = [points[i:i + BATCH] for i in range(0, len(points), BATCH)]
        results = parallel(lambda b: self._batch(client, b), batches, max_workers=3)
        rows = [p for _, res, err in results if not err for p in res]
        failures = [f"batch {i}: {describe(err)}" for i, (_, _, err) in enumerate(results) if err]
        if not rows:
            raise FeedError("; ".join(failures))
        data = {"lngStep": self.lng_step, "latStep": self.lat_step, "bbox": [LNG_MIN, LAT_MIN, LNG_MAX, LAT_MAX], "model": MODEL,
                "points": rows, "count": len(rows)}
        if failures:
            data["_partial"] = failures
        return data

    def count_of(self, data: dict) -> int:
        return len(data.get("points") or [])

    def empty(self) -> dict:
        return {"lngStep": self.lng_step, "latStep": self.lat_step, "points": []}
