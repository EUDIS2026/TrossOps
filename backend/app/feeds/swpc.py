"""NOAA SWPC planetary K-index (3-hourly, last 7 days).

The product is a JSON list of objects `{"time_tag", "Kp", "a_running", "station_count"}`; the legacy format was a
list of lists with a header row (`["time_tag", "Kp", ...]`, values as strings). Both are accepted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from .base import Feed, FeedError, num

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"


def _ts(tag: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(tag).replace(" ", "T").replace("Z", ""))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc)


def rows(body) -> list[dict]:
    if not isinstance(body, list) or not body:
        raise FeedError("unexpected payload")
    if isinstance(body[0], list):
        header = [str(h) for h in body[0]]
        body = [dict(zip(header, r)) for r in body[1:]]
    out = []
    for r in body:
        dt, kp = _ts(r.get("time_tag")), num(r.get("Kp", r.get("kp")))
        if dt and kp is not None:
            out.append({"time": dt.isoformat().replace("+00:00", "Z"), "kp": kp, "_dt": dt})
    if not out:
        raise FeedError("no Kp values")
    return sorted(out, key=lambda r: r["_dt"])


def storm_scale(kp: float) -> str | None:
    if kp >= 9:
        return "G5"
    if kp >= 5:
        return f"G{min(5, int(kp) - 4)}"
    return None


def normalise(body) -> dict:
    series = rows(body)
    latest = series[-1]
    cutoff = latest["_dt"] - timedelta(hours=24)
    last24 = [{"time": r["time"], "kp": r["kp"]} for r in series if r["_dt"] > cutoff]
    kp = latest["kp"]
    max24 = max(r["kp"] for r in last24)
    if kp >= 5:
        note = "Geomagnetic storm: HF and GNSS degradation likely at high latitudes"
    elif kp >= 4:
        note = "Active geomagnetic conditions: minor HF/GNSS effects possible at high latitudes"
    else:
        note = "Quiet to unsettled: no significant HF/GNSS impact expected"
    return {"kp": kp, "time": latest["time"], "stormScale": storm_scale(kp), "max24h": max24, "series24h": last24,
            "impact": note, "items": last24}


class SwpcFeed(Feed):
    id = "swpc-kp"
    label = "NOAA SWPC planetary K-index"
    category = "space"
    url = KP_URL
    licence = "Public domain (US Government work)"
    attribution = "Data: NOAA Space Weather Prediction Center"
    ttl_s = 1800.0
    note = "Kp from the ground-magnetometer network, 3-hourly; latest value may be provisional."

    def fetch(self, client: httpx.Client) -> dict:
        r = client.get(KP_URL)
        r.raise_for_status()
        return normalise(r.json())

    def empty(self) -> dict:
        return {"kp": None, "series24h": [], "items": []}
