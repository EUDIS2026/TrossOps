"""SMHI open-data point forecasts (public). Status is `connected` only when a live response was parsed;
otherwise `unavailable` with the reason. Values never feed the rule engine as observations — they are forecasts."""
from __future__ import annotations

import os
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
# SNOW1G point forecasts: each time-series entry is {"time": ISO, "data": {parameter: value}} (flat, no unit fields).
WANTED = ("air_temperature", "wind_speed", "wind_from_direction", "wind_speed_of_gust", "cloud_area_fraction",
          "probability_of_precipitation", "visibility_in_air", "precipitation_amount_mean", "symbol_code")
UNITS = {"air_temperature": "°C", "wind_speed": "m/s", "wind_from_direction": "°", "wind_speed_of_gust": "m/s", "cloud_area_fraction": "%",
         "probability_of_precipitation": "%", "visibility_in_air": "km", "precipitation_amount_mean": "mm", "symbol_code": ""}


def _valid_time(entry: dict) -> str | None:
    return entry.get("time") or entry.get("validTime")


def _values(entry: dict) -> dict:
    """Flat SNOW1G `data` object, or the older pmp3g `parameters` list, reduced to {name: value}."""
    if isinstance(entry.get("data"), dict):
        return entry["data"]
    out: dict = {}
    for param in entry.get("parameters", []) or []:
        values = param.get("values") or [None]
        out[param.get("name")] = values[0]
    return out


def parse_forecast(payload: dict, location: str) -> dict:
    series = payload.get("timeSeries") or []
    now = datetime.now(timezone.utc)
    chosen = None
    for entry in series:
        valid = _valid_time(entry)
        if valid and datetime.fromisoformat(valid.replace("Z", "+00:00")) >= now:
            chosen = entry
            break
    chosen = chosen or (series[0] if series else None)
    if not chosen:
        raise ValueError("empty forecast")
    values = _values(chosen)
    data = {key: values[key] for key in WANTED if key in values}
    units = {key: UNITS[key] for key in data}
    coords = (payload.get("geometry") or {}).get("coordinates") or [None, None]
    if coords and isinstance(coords[0], list):
        coords = coords[0]
    meta = PUBLIC_POINTS[location]
    return {"status": "connected", "source": "SMHI SNOW1G point forecast (public)", "kind": "forecast", "location": location, "label": meta["label"],
            "sourceUrl": SMHI_URL.format(lon=meta["point"][0], lat=meta["point"][1]), "requestedPoint": meta["point"], "gridPoint": coords,
            "referenceTime": payload.get("referenceTime"), "createdTime": payload.get("createdTime") or payload.get("approvedTime"),
            "validTime": _valid_time(chosen), "data": data, "units": units}


class WeatherService:
    def __init__(self, ttl_s: float = 600) -> None:
        self.ttl = ttl_s
        self.cache: dict[str, tuple[float, dict]] = {}

    def get(self, location: str) -> dict:
        meta = PUBLIC_POINTS[location]
        hit = self.cache.get(location)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        if os.environ.get("TROSSOPS_FEEDS", "").strip().lower() in {"off", "0", "false", "no", "disabled"}:  # same switch as app.feeds
            return {"status": "unavailable", "source": "SMHI SNOW1G point forecast (public)", "kind": "forecast", "location": location, "label": meta["label"],
                    "requestedPoint": meta["point"], "reason": "disabled by configuration (TROSSOPS_FEEDS=off)"}
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
