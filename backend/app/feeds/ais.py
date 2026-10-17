"""Vessel positions from Digitraffic Marine (Fintraffic) AIS, CC BY 4.0, no key.

`/api/ais/v1/locations` (GeoJSON FeatureCollection, every vessel the Finnish AIS network currently holds) is refreshed
every ~30 s; `/api/ais/v1/vessels` (static metadata) at most once an hour. Positions are filtered to the Sweden + Baltic
box and joined with metadata by MMSI. Coverage is strongest in the northern Baltic, Gulf of Bothnia and Gulf of Finland;
the Swedish west coast (Kattegat/Skagerrak) is largely outside the Finnish receiver network.
"""
from __future__ import annotations

import threading
import time
from collections import deque

import httpx

from .base import KT_TO_MPS, Feed, FeedError, describe, iso, num, parallel

LOCATIONS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"
VESSELS_URL = "https://meri.digitraffic.fi/api/ais/v1/vessels"
DIGITRAFFIC_HEADERS = {"Accept-Encoding": "gzip", "Digitraffic-User": "TrossOps/1.0"}
BBOX = (9.5, 53.8, 30.5, 66.2)  # lng min, lat min, lng max, lat max
METADATA_TTL_S = 3600.0
HISTORY_LEN = 60  # ~30 min at the 30 s TTL: long enough for loiter detection
HISTORY_FORGET_S = 3 * 3600.0

SHIP_TYPES = {30: "Fishing", 31: "Towing", 32: "Towing (large)", 33: "Dredging / underwater ops", 34: "Diving ops",
              35: "Military ops", 36: "Sailing", 37: "Pleasure craft", 50: "Pilot", 51: "Search and rescue", 52: "Tug",
              53: "Port tender", 54: "Anti-pollution", 55: "Law enforcement", 58: "Medical transport",
              59: "Non-combatant (RR Res. 18)"}
NAV_STATUS = {0: "Under way using engine", 1: "At anchor", 2: "Not under command", 3: "Restricted manoeuvrability",
              4: "Constrained by draught", 5: "Moored", 6: "Aground", 7: "Engaged in fishing", 8: "Under way sailing",
              11: "Towing astern", 12: "Pushing ahead / towing alongside", 14: "AIS-SART / MOB / EPIRB active",
              15: "Not defined"}


def ship_type_label(code) -> str | None:
    code = int(code) if isinstance(code, (int, float)) else None
    if code is None or code == 0:
        return None
    if code in SHIP_TYPES:
        return SHIP_TYPES[code]
    for lo, label in ((20, "Wing in ground"), (40, "High-speed craft"), (60, "Passenger"), (70, "Cargo"), (80, "Tanker"),
                      (90, "Other")):
        if lo <= code <= lo + 9:
            return label
    if code in (56, 57):
        return "Local vessel"
    return "Reserved"


def nav_status_label(code) -> str | None:
    if not isinstance(code, int):
        return None
    return NAV_STATUS.get(code, "Reserved")


def heading(value) -> float | None:
    v = num(value)
    return None if v is None or v >= 360 else v  # 511 = not available


def course(value) -> float | None:
    v = num(value)
    return None if v is None or v >= 360 else v  # 360 = not available


def speed_mps(sog_kn) -> float | None:
    v = num(sog_kn)
    return None if v is None or v >= 102.2 else round(v * KT_TO_MPS, 2)  # 102.3 = not available


def in_bbox(lng: float, lat: float) -> bool:
    return BBOX[0] <= lng <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]


def normalise_metadata(v: dict) -> dict:
    draught = num(v.get("draught"))
    return {"name": (v.get("name") or "").strip() or None, "callsign": (v.get("callSign") or "").strip() or None,
            "imo": v.get("imo") or None, "shipType": v.get("shipType"), "shipTypeLabel": ship_type_label(v.get("shipType")),
            "destination": (v.get("destination") or "").strip() or None,
            "draughtM": None if not draught else round(draught / 10.0, 1)}


def normalise_location(feature: dict, meta: dict | None) -> dict | None:
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    lng, lat = num(coords[0]), num(coords[1])
    if lng is None or lat is None or not in_bbox(lng, lat):
        return None
    p = feature.get("properties") or {}
    mmsi = p.get("mmsi", feature.get("mmsi"))
    meta = meta or {}
    return {"id": mmsi, "name": meta.get("name"), "callsign": meta.get("callsign"), "imo": meta.get("imo"),
            "shipType": meta.get("shipType"), "shipTypeLabel": meta.get("shipTypeLabel"), "lng": lng, "lat": lat,
            "speedMps": speed_mps(p.get("sog")), "courseDeg": course(p.get("cog")), "headingDeg": heading(p.get("heading")),
            "navStatus": p.get("navStat"), "navStatusLabel": nav_status_label(p.get("navStat")),
            "destination": meta.get("destination"), "draughtM": meta.get("draughtM"),
            "timestampMs": p.get("timestampExternal"), "source": "digitraffic"}


class AisFeed(Feed):
    id = "ais-digitraffic"
    label = "AIS vessels (Digitraffic Marine / Fintraffic)"
    category = "sea"
    url = LOCATIONS_URL
    licence = "CC BY 4.0"
    attribution = "Source: Fintraffic / digitraffic.fi, license CC 4.0 BY"
    ttl_s = 30.0
    note = "Finnish AIS receiver network: dense in the northern Baltic, sparse on the Swedish west coast."

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        super().__init__(transport)
        self._meta: dict[int, dict] = {}
        self._meta_at: float | None = None
        self._history: dict[int, deque] = {}
        self._history_lock = threading.Lock()

    def reset(self) -> None:
        super().reset()
        self._meta, self._meta_at = {}, None
        with self._history_lock:
            self._history.clear()

    def _get_json(self, client: httpx.Client, url: str):
        r = client.get(url, headers=DIGITRAFFIC_HEADERS)
        r.raise_for_status()
        return r.json()

    def fetch(self, client: httpx.Client) -> dict:
        need_meta = self._meta_at is None or time.time() - self._meta_at > METADATA_TTL_S
        urls = [LOCATIONS_URL] + ([VESSELS_URL] if need_meta else [])
        results = {u: (body, err) for u, body, err in parallel(lambda u: self._get_json(client, u), urls)}
        loc_body, loc_err = results[LOCATIONS_URL]
        if loc_err:
            raise FeedError(f"locations: {describe(loc_err)}")
        if not isinstance(loc_body, dict) or not isinstance(loc_body.get("features"), list):
            raise FeedError("locations: unexpected payload")
        partial: list[str] = []
        if need_meta:
            meta_body, meta_err = results[VESSELS_URL]
            if meta_err or not isinstance(meta_body, list):
                partial.append(f"vessel metadata: {describe(meta_err) if meta_err else 'unexpected payload'}")
            else:
                self._meta = {v["mmsi"]: normalise_metadata(v) for v in meta_body if isinstance(v, dict) and "mmsi" in v}
                self._meta_at = time.time()
        items = []
        for feature in loc_body["features"]:
            mmsi = (feature.get("properties") or {}).get("mmsi", feature.get("mmsi"))
            item = normalise_location(feature, self._meta.get(mmsi))
            if item and item["id"] is not None:
                items.append(item)
        data = {"items": items, "dataUpdatedTime": loc_body.get("dataUpdatedTime"), "bbox": list(BBOX),
                "metadataAt": iso(self._meta_at)}
        if partial:
            data["_partial"] = partial
        return data

    # -- history ------------------------------------------------------------------------------------------------------
    def record(self, item: dict) -> None:
        ts = item.get("timestampMs")
        if ts is None:
            return
        with self._history_lock:
            ring = self._history.setdefault(item["id"], deque(maxlen=HISTORY_LEN))
            if ring and ring[-1]["timestampMs"] >= ts:
                return
            ring.append({"timestampMs": ts, "lng": item["lng"], "lat": item["lat"], "speedMps": item["speedMps"],
                         "courseDeg": item["courseDeg"], "headingDeg": item["headingDeg"], "navStatus": item["navStatus"],
                         "source": item.get("source")})

    def on_success(self, data: dict) -> None:
        for item in data["items"]:
            self.record(item)
        cutoff = (time.time() - HISTORY_FORGET_S) * 1000
        with self._history_lock:
            for mmsi in [m for m, ring in self._history.items() if not ring or ring[-1]["timestampMs"] < cutoff]:
                del self._history[mmsi]

    def history(self, mmsi: int) -> list[dict]:
        with self._history_lock:
            return list(self._history.get(int(mmsi), ()))


def merge_vessels(primary: list[dict], extra: list[dict]) -> list[dict]:
    """Merge vessel lists by MMSI, keeping the most recent position and filling missing metadata from the other."""
    out: dict = {v["id"]: dict(v) for v in primary}
    for v in extra:
        cur = out.get(v["id"])
        if cur is None:
            out[v["id"]] = dict(v)
            continue
        newer, older = (v, cur) if (v.get("timestampMs") or 0) > (cur.get("timestampMs") or 0) else (cur, v)
        merged = dict(newer)
        for key, value in older.items():
            if merged.get(key) is None and value is not None:
                merged[key] = value
        out[v["id"]] = merged
    return list(out.values())
