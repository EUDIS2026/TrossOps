"""SMHI open data: latest-hour station observations (metobs) and impact-based weather warnings (IBWW). CC BY 4.0.

metobs: one request per parameter (`station-set/all/period/latest-hour`), each returning every active station with a
`value` list (usually one entry, empty when the station did not report). Values are strings; joined per station key.
Warnings: a list of events, each with `warningAreas`; one normalised item per warning area, geometry passed through
from `area.geometry` (mostly Polygon/MultiPolygon; coastal sea-level warnings can be LineString).
"""
from __future__ import annotations

import httpx

from .base import Feed, FeedError, describe, iso_ms, num, parallel

METOBS_URL = "https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}/station-set/all/period/latest-hour/data.json"
# SMHI parameter id -> normalised field
PARAMETERS: dict[int, str] = {1: "airTempC", 4: "windMps", 3: "windDirDeg", 21: "gustMps", 12: "visibilityM",
                              16: "cloudPct", 7: "precipMm"}
WARNINGS_URL = "https://opendata-download-warnings.smhi.se/ibww/api/version/1/warning.json"
LEVELS = {"YELLOW": "yellow", "ORANGE": "orange", "RED": "red", "MESSAGE": "message"}


def latest_value(station: dict) -> tuple[float | None, int | None]:
    values = [v for v in station.get("value") or [] if isinstance(v, dict) and num(v.get("value")) is not None]
    if not values:
        return None, None
    best = max(values, key=lambda v: v.get("date") or 0)
    return num(best.get("value")), best.get("date")


def join_stations(payloads: dict[int, dict]) -> list[dict]:
    stations: dict[str, dict] = {}
    for param, payload in payloads.items():
        field = PARAMETERS[param]
        for st in payload.get("station") or []:
            value, date = latest_value(st)
            if value is None:
                continue
            key = str(st.get("key"))
            lat, lng = num(st.get("latitude")), num(st.get("longitude"))
            if lat is None or lng is None:
                continue
            row = stations.get(key)
            if row is None:
                row = stations[key] = {"id": key, "name": st.get("name"), "lng": lng, "lat": lat,
                                       **{f: None for f in PARAMETERS.values()}, "_observed": 0}
            row[field] = value
            row["_observed"] = max(row["_observed"], date or 0)
    out = []
    for row in stations.values():
        row["observedAt"] = iso_ms(row.pop("_observed") or None)
        out.append(row)
    return sorted(out, key=lambda r: r["id"])


class SmhiObservationsFeed(Feed):
    id = "smhi-obs"
    label = "SMHI station observations (latest hour)"
    category = "weather"
    url = METOBS_URL.format(p="{p}")
    licence = "CC BY 4.0"
    attribution = "Källa: SMHI"
    ttl_s = 600.0
    note = "Observed values; parameters 1, 3, 4, 7, 12, 16, 21 joined per station. Not every station reports every parameter."

    def _param(self, client: httpx.Client, p: int) -> dict:
        r = client.get(METOBS_URL.format(p=p))
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, dict) or "station" not in body:
            raise FeedError("unexpected payload")
        return body

    def fetch(self, client: httpx.Client) -> dict:
        results = parallel(lambda p: self._param(client, p), PARAMETERS)
        ok = {p: body for p, body, err in results if not err}
        failures = [f"parameter {p}: {describe(err)}" for p, _, err in results if err]
        if not ok:
            raise FeedError("; ".join(failures))
        data = {"items": join_stations(ok), "parameters": {PARAMETERS[p]: p for p in ok}}
        if failures:
            data["_partial"] = failures
        return data


def _text(obj, *langs: str) -> str | None:
    if not isinstance(obj, dict):
        return obj if isinstance(obj, str) else None
    for lang in langs:
        if obj.get(lang):
            return obj[lang]
    return None


def normalise_warnings(events: list) -> list[dict]:
    out = []
    for ev in events or []:
        event = ev.get("event") or {}
        for wa in ev.get("warningAreas") or []:
            level = (wa.get("warningLevel") or {}).get("code")
            descriptions = [_text(d.get("text"), "en", "sv") for d in wa.get("descriptions") or [] if isinstance(d, dict)]
            area = wa.get("area") or {}
            out.append({
                "id": f"{ev.get('id')}-{wa.get('id')}", "event": _text(event, "en", "sv"), "eventSv": _text(event, "sv"),
                "eventCode": event.get("code"), "level": LEVELS.get(level, (level or "").lower() or None),
                "headline": _text(wa.get("eventDescription"), "en", "sv"),
                "headlineSv": _text(wa.get("eventDescription"), "sv"),
                "description": "\n\n".join(d for d in descriptions if d) or None,
                "validFrom": wa.get("approximateStart"), "validTo": wa.get("approximateEnd"),
                "published": wa.get("published"), "areaName": _text(wa.get("areaName"), "sv", "en"),
                "affectedAreas": [_text(a, "sv", "en") for a in wa.get("affectedAreas") or []],
                "geometry": area.get("geometry") if isinstance(area, dict) else None,
            })
    return out


class SmhiWarningsFeed(Feed):
    id = "smhi-warnings"
    label = "SMHI weather warnings (impact-based)"
    category = "weather"
    url = WARNINGS_URL
    licence = "CC BY 4.0"
    attribution = "Källa: SMHI"
    ttl_s = 600.0
    note = "One item per warning area. Level 'message' is an informational notice below yellow. validTo null = until further notice."

    def fetch(self, client: httpx.Client) -> dict:
        r = client.get(WARNINGS_URL)
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, list):
            raise FeedError("unexpected payload (expected a list of events)")
        return {"items": normalise_warnings(body)}
