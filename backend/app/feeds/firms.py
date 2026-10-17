"""NASA FIRMS active fires (VIIRS S-NPP / NOAA-20 / NOAA-21, near real time) over Sweden and the Baltic.

GET `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{DAYS}` returns CSV rows with
latitude, longitude, bright_ti4, frp, confidence, acq_date, acq_time, satellite, daynight. A free MAP_KEY is required
(`FIRMS_MAP_KEY`); without it the feed is adapter-only. Detections are thermal anomalies (fires, flares, industrial
heat), not confirmed fires.
"""
from __future__ import annotations

import csv
import io
import os

import httpx

from .base import Feed, FeedError, num

AREA = "9.5,54.0,31.0,69.5"
SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{area}/{days}"


def parse_csv(text: str, source: str) -> list[dict]:
    if text.lstrip().lower().startswith(("invalid", "error")):
        raise FeedError(text.strip()[:160])
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        lat, lng = num(row.get("latitude")), num(row.get("longitude"))
        if lat is None or lng is None:
            continue
        t = (row.get("acq_time") or "0000").zfill(4)
        out.append({"id": f"{source}-{row.get('acq_date')}-{t}-{lat:.4f}-{lng:.4f}", "lng": lng, "lat": lat, "frpMw": num(row.get("frp")),
                    "brightnessK": num(row.get("bright_ti4")), "confidence": row.get("confidence"), "acquired": f"{row.get('acq_date')}T{t[:2]}:{t[2:]}:00Z",
                    "satellite": row.get("satellite"), "daynight": row.get("daynight"), "source": source})
    return out


class FirmsFeed(Feed):
    id = "firms"
    label = "NASA FIRMS active fires (VIIRS)"
    category = "weather"
    url = "https://firms.modaps.eosdis.nasa.gov/api/"
    licence = "NASA open data (no restrictions); cite LANCE FIRMS"
    attribution = "Fire data: NASA FIRMS (LANCE)"
    ttl_s = 1800.0
    credential_env = ("FIRMS_MAP_KEY",)
    note = "Thermal anomalies from three VIIRS satellites, last 24 h. Not every detection is a wildfire (flares, industry)."

    def fetch(self, client: httpx.Client) -> dict:
        key = os.environ["FIRMS_MAP_KEY"]
        items, errors = [], []
        for source in SOURCES:
            try:
                r = client.get(URL.format(key=key, source=source, area=AREA, days=1))
                r.raise_for_status()
                items += parse_csv(r.text, source)
            except Exception as exc:  # noqa: BLE001 - one satellite failing leaves the others
                errors.append(f"{source}: {str(exc)[:100]}")
        if errors and not items:
            raise FeedError("; ".join(errors))
        return {"items": items, "_partial": errors}

    def count_of(self, data: dict) -> int:
        return len(data.get("items", []))

    def empty(self) -> dict:
        return {"items": []}
