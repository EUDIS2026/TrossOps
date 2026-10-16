"""SMHI open-data point forecasts (public). Status is `connected` only when a live response was parsed;
otherwise `unavailable` with the reason. Values never feed the rule engine as observations — they are forecasts."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

SMHI_URL = "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1/geotype/point/lon/{lon:.4f}/lat/{lat:.4f}/data.json"

PUBLIC_POINTS: dict[str, dict] = {
    "stockholm": {"label": "Stockholm", "point": [18.0686, 59.3293]},
    "goteborg": {"label": "Göteborg", "point": [11.9746, 57.7089]},
    "malmo": {"label": "Malmö", "point": [13.0038, 55.6050]},
    "visby": {"label": "Visby", "point": [18.2948, 57.6348]},
    "lulea": {"label": "Luleå", "point": [22.1547, 65.5848]},
    "ostersund": {"label": "Östersund", "point": [14.6357, 63.1792]},
    "kiruna": {"label": "Kiruna", "point": [20.2253, 67.8558]},
}
WANTED = {"air_temperature": "t", "wind_speed": "ws", "wind_from_direction": "wd", "wind_speed_of_gust": "gust", "cloud_area_fraction": "tcc_mean",
          "probability_of_precipitation": "pcat", "visibility": "vis"}


def parse_forecast(payload: dict, location: str) -> dict:
    series = payload.get("timeSeries") or []
    now = datetime.now(timezone.utc)
    chosen = None
    for entry in series:
        valid = datetime.fromisoformat(entry["validTime"].replace("Z", "+00:00"))
        if valid >= now:
            chosen = entry
            break
    chosen = chosen or (series[0] if series else None)
    if not chosen:
        raise ValueError("empty forecast")
    data: dict[str, float | None] = {}
    units: dict[str, str] = {}
    for param in chosen.get("parameters", []):
        name = param.get("name")
        for key, legacy in WANTED.items():
            if name in (key, legacy):
                values = param.get("values") or [None]
                data[key] = values[0]
                units[key] = param.get("unit", "")
    coords = (payload.get("geometry") or {}).get("coordinates") or [[None, None]]
    meta = PUBLIC_POINTS[location]
    return {"status": "connected", "source": "SMHI SNOW1G point forecast (public)", "kind": "forecast", "location": location, "label": meta["label"],
            "sourceUrl": SMHI_URL.format(lon=meta["point"][0], lat=meta["point"][1]), "requestedPoint": meta["point"], "gridPoint": coords[0],
            "referenceTime": payload.get("referenceTime"), "approvedTime": payload.get("approvedTime"), "validTime": chosen.get("validTime"), "data": data, "units": units}


class WeatherService:
    def __init__(self, ttl_s: float = 600) -> None:
        self.ttl = ttl_s
        self.cache: dict[str, tuple[float, dict]] = {}

    def get(self, location: str) -> dict:
        meta = PUBLIC_POINTS[location]
        hit = self.cache.get(location)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        try:
            with httpx.Client(timeout=6.0) as client:
                response = client.get(SMHI_URL.format(lon=meta["point"][0], lat=meta["point"][1]))
                response.raise_for_status()
                result = parse_forecast(response.json(), location)
        except Exception as exc:  # network, parsing or schema change: report, never guess
            result = {"status": "unavailable", "source": "SMHI SNOW1G point forecast (public)", "kind": "forecast", "location": location, "label": meta["label"],
                      "requestedPoint": meta["point"], "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}
        self.cache[location] = (time.time(), result)
        return result
