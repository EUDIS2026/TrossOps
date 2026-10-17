"""Aircraft positions from public ADS-B aggregators.

Primary: adsb.lol (`/v2/lat/{lat}/lon/{lon}/dist/{nm}`, max 250 nm, ODbL). Sweden and the Baltic are covered by three
overlapping 250 nm circles merged by ICAO hex.

adsb.lol rate-limits per IP (measured 2026-10: a burst of ~3 requests, then roughly one request per 10 s; excess gets
HTTP 429, or 420 when sustained). After a 420/429 the feed pauses adsb.lol requests for 30 s. So a cold start fetches all circles at once and every later refresh fetches only the stalest
circle; the published picture merges the latest snapshot of each circle by absolute position time, and `seenS` is the
age of each position at publication. A full cycle therefore takes ~3 x TTL.

Fallback when no circle snapshot is available: OpenSky Network `states/all` over a bounding box (anonymous, or OAuth2
client credentials when OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET are set), called at most once a minute because
anonymous OpenSky access is credit-limited.

Also keeps a per-process position trail per aircraft and derives GNSS-integrity samples from NIC / NACp.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import deque

import httpx

from .base import FPM_TO_MPS, FT_TO_M, KT_TO_MPS, Feed, FeedError, describe, iso, num, parallel

ADSB_LOL_URL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}"
CIRCLES: tuple[tuple[float, float, int], ...] = ((56.5, 15.0, 250), (60.5, 18.5, 250), (65.5, 19.5, 250))
CIRCLE_MAX_AGE_S = 120.0  # a circle snapshot older than this is dropped from the merged picture
POSITION_MAX_AGE_S = 90.0  # aircraft whose last position is older than this are dropped
OPENSKY_MIN_GAP_S = 60.0
OPENSKY_FAIL_BACKOFF_S = 600.0
RATE_LIMIT_COOLDOWN_S = 30.0  # after HTTP 420/429 from adsb.lol, send nothing for this long
OPENSKY_URL = "https://opensky-network.org/api/states/all"
OPENSKY_BBOX = {"lamin": 54.5, "lomin": 9.5, "lamax": 69.5, "lomax": 31.0}
OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

TRAIL_LEN = 120  # ~30 min at >= 15 s spacing: long enough to recognise orbits
TRAIL_MIN_GAP_S = 15.0
TRAIL_FORGET_S = 900.0

# GNSS integrity: airborne ADS-B positions with NIC < 7 (containment radius > 0.2 NM) or NACp < 8 (EPU >= 0.05 NM).
NIC_MIN = 7
NACP_MIN = 8
# readsb `type` values whose position comes from the aircraft's own navigation source (not MLAT / TIS-B).
ADSB_SOURCE_TYPES = {"adsb_icao", "adsb_icao_nt", "adsb_other", "adsr_icao", "adsr_other"}

# OpenSky `category` (extended=1) -> ADS-B emitter category.
OPENSKY_CATEGORY = {2: "A1", 3: "A2", 4: "A3", 5: "A4", 6: "A5", 7: "A6", 8: "A7", 9: "B1", 10: "B2", 11: "B3", 12: "B4",
                    14: "B6", 15: "B7", 16: "C1", 17: "C2", 18: "C3", 19: "C4", 20: "C5"}


def _clean(text) -> str | None:
    if text is None:
        return None
    text = str(text).strip()
    return text or None


def normalise_adsb_lol(ac: dict) -> dict | None:
    lat, lng = num(ac.get("lat")), num(ac.get("lon"))
    if lat is None or lng is None:
        return None
    baro = ac.get("alt_baro")
    on_ground = baro == "ground"
    geom_ft = num(ac.get("alt_geom"))
    baro_ft = None if on_ground else num(baro)
    if on_ground:
        alt_m, alt_source = 0.0, "ground"
    elif geom_ft is not None:
        alt_m, alt_source = round(geom_ft * FT_TO_M, 1), "geometric"
    elif baro_ft is not None:
        alt_m, alt_source = round(baro_ft * FT_TO_M, 1), "baro"
    else:
        alt_m, alt_source = None, None
    gs = num(ac.get("gs"))
    rate = num(ac.get("geom_rate"))
    if rate is None:
        rate = num(ac.get("baro_rate"))
    flags = ac.get("dbFlags") or 0
    emergency = _clean(ac.get("emergency"))
    return {
        "id": str(ac.get("hex", "")).lower(), "callsign": _clean(ac.get("flight")), "registration": _clean(ac.get("r")),
        "type": _clean(ac.get("t")), "category": _clean(ac.get("category")), "lng": lng, "lat": lat,
        "altM": alt_m, "altDatum": "MSL", "altSource": alt_source, "onGround": on_ground,
        "speedMps": None if gs is None else round(gs * KT_TO_MPS, 2), "headingDeg": num(ac.get("track")),
        "verticalRateMps": None if rate is None else round(rate * FPM_TO_MPS, 2), "squawk": _clean(ac.get("squawk")),
        "emergency": None if emergency in (None, "none") else emergency, "military": bool(int(flags) & 1),
        "nic": ac.get("nic"), "nacp": ac.get("nac_p"), "seenS": num(ac.get("seen_pos", ac.get("seen"))),
        "positionType": ac.get("type"), "source": "adsb.lol",
    }


def normalise_opensky(sv: list, now_s: float) -> dict | None:
    if not sv or len(sv) < 17:
        return None
    lng, lat = num(sv[5]), num(sv[6])
    if lat is None or lng is None:
        return None
    on_ground = bool(sv[8])
    geo, baro = num(sv[13]), num(sv[7])
    if on_ground:
        alt_m, alt_source = 0.0, "ground"
    elif geo is not None:
        alt_m, alt_source = round(geo, 1), "geometric"
    elif baro is not None:
        alt_m, alt_source = round(baro, 1), "baro"
    else:
        alt_m, alt_source = None, None
    squawk = _clean(sv[14])
    category = OPENSKY_CATEGORY.get(sv[17]) if len(sv) > 17 and isinstance(sv[17], int) else None
    t_pos = num(sv[3])
    return {
        "id": str(sv[0]).lower(), "callsign": _clean(sv[1]), "registration": None, "type": None, "category": category,
        "lng": lng, "lat": lat, "altM": alt_m, "altDatum": "MSL", "altSource": alt_source, "onGround": on_ground,
        "speedMps": num(sv[9]), "headingDeg": num(sv[10]), "verticalRateMps": num(sv[11]), "squawk": squawk,
        "emergency": {"7500": "unlawful", "7600": "nordo", "7700": "general"}.get(squawk or ""), "military": False,
        "nic": None, "nacp": None, "seenS": None if t_pos is None else round(max(0.0, now_s - t_pos), 1),
        "positionType": {0: "adsb", 1: "asterix", 2: "mlat", 3: "flarm"}.get(sv[16]), "source": "opensky",
    }


def _in_circle(ac: dict, circle: tuple[float, float, int]) -> bool:
    if ac.get("lat") is None or ac.get("lng") is None:
        return False
    dlat = math.radians(ac["lat"] - circle[0])
    dlng = math.radians(ac["lng"] - circle[1]) * math.cos(math.radians((ac["lat"] + circle[0]) / 2))
    return 6_371_000 * math.hypot(dlat, dlng) <= circle[2] * 1852


def is_gnss_sample(ac: dict) -> bool:
    return (ac.get("source") == "adsb.lol" and not ac.get("onGround") and ac.get("positionType") in ADSB_SOURCE_TYPES
            and isinstance(ac.get("nic"), int) and isinstance(ac.get("nacp"), int))


def is_degraded(ac: dict) -> bool:
    return ac["nic"] < NIC_MIN or ac["nacp"] < NACP_MIN


class AdsbFeed(Feed):
    id = "adsb"
    label = "ADS-B aircraft (adsb.lol, OpenSky fallback)"
    category = "air"
    url = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}"
    licence = "ODbL 1.0 (adsb.lol); OpenSky Network terms of use (fallback, non-commercial research)"
    attribution = "Aircraft data © adsb.lol contributors (ODbL 1.0); fallback: The OpenSky Network, opensky-network.org"
    ttl_s = 10.0
    note = "Public ADS-B; coverage depends on volunteer receivers. Military flag = adsb.lol database flag, not a classification."

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        super().__init__(transport)
        self._trails: dict[str, deque] = {}
        self._trail_lock = threading.Lock()
        self._token: tuple[str, float] | None = None
        self._snapshots: dict[int, tuple[float, list[dict]]] = {}
        self._circle_errors: dict[int, str] = {}
        self._opensky_cache: tuple[float, list[dict]] | None = None
        self._opensky_fail_until = 0.0
        self._cooldown_until = 0.0

    def reset(self) -> None:
        super().reset()
        self._snapshots.clear()
        self._circle_errors.clear()
        self._opensky_cache = None
        self._opensky_fail_until = 0.0
        self._cooldown_until = 0.0
        with self._trail_lock:
            self._trails.clear()

    # -- upstreams ----------------------------------------------------------------------------------------------------
    def _circle(self, client: httpx.Client, circle: tuple[float, float, int]) -> list[dict]:
        lat, lon, nm = circle
        r = client.get(ADSB_LOL_URL.format(lat=lat, lon=lon, nm=min(nm, 250)))
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, dict) or not isinstance(body.get("ac"), list):
            raise FeedError("adsb.lol: unexpected payload")
        return body["ac"]

    def _opensky_token(self, client: httpx.Client) -> str | None:
        cid, secret = os.environ.get("OPENSKY_CLIENT_ID"), os.environ.get("OPENSKY_CLIENT_SECRET")
        if not (cid and secret):
            return None
        if self._token and self._token[1] > time.time() + 30:
            return self._token[0]
        r = client.post(OPENSKY_TOKEN_URL, data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret})
        r.raise_for_status()
        body = r.json()
        self._token = (body["access_token"], time.time() + float(body.get("expires_in", 1800)))
        return self._token[0]

    def _opensky(self, client: httpx.Client) -> list[dict]:
        token = self._opensky_token(client)
        headers = {"Authorization": f"Bearer {token}"} if token else None
        r = client.get(OPENSKY_URL, params={**OPENSKY_BBOX, "extended": 1}, headers=headers)
        r.raise_for_status()
        body = r.json()
        now_s = num(body.get("time")) or time.time()
        out = [normalise_opensky(sv, now_s) for sv in body.get("states") or []]
        return [a for a in out if a]

    def _due_circles(self, now: float) -> list[int]:
        if now < self._cooldown_until:
            return []
        missing = [i for i in range(len(CIRCLES)) if i not in self._snapshots]
        if missing:
            return missing  # cold start: one burst of <= 3 requests is within the adsb.lol allowance
        return [min(range(len(CIRCLES)), key=lambda i: self._snapshots[i][0])]

    def fetch(self, client: httpx.Client) -> dict:
        now = time.time()
        due = self._due_circles(now)
        for i, acs, err in parallel(lambda i: self._circle(client, CIRCLES[i]), due):
            if err:
                self._circle_errors[i] = describe(err)
                if isinstance(err, httpx.HTTPStatusError) and err.response.status_code in (420, 429):
                    self._cooldown_until = time.time() + RATE_LIMIT_COOLDOWN_S
                continue
            self._circle_errors.pop(i, None)
            parsed = [a for a in (normalise_adsb_lol(raw) for raw in acs) if a and a["id"]]
            self._snapshots[i] = (time.time(), parsed)

        now = time.time()
        merged: dict[str, tuple[float, dict]] = {}
        live = {i: snap for i, snap in self._snapshots.items() if now - snap[0] <= CIRCLE_MAX_AGE_S}
        for fetched_at, acs in live.values():
            for ac in acs:
                pos_t = fetched_at - (ac["seenS"] or 0.0)
                if now - pos_t > POSITION_MAX_AGE_S:
                    continue
                prev = merged.get(ac["id"])
                if prev is None or pos_t > prev[0]:
                    merged[ac["id"]] = (pos_t, ac)
        partial = [f"adsb.lol circle {CIRCLES[i][0]}/{CIRCLES[i][1]}: {msg}" for i, msg in sorted(self._circle_errors.items())]
        partial += [f"adsb.lol circle {CIRCLES[i][0]}/{CIRCLES[i][1]}: no snapshot younger than {CIRCLE_MAX_AGE_S:.0f} s"
                    for i in range(len(CIRCLES)) if i not in live and i not in self._circle_errors]
        if now < self._cooldown_until:
            partial.append(f"adsb.lol rate limit: paused for {self._cooldown_until - now:.0f} s")
        source = "adsb.lol"
        gap_note = None
        if not live:
            try:
                if self._opensky_cache is None or now - self._opensky_cache[0] >= OPENSKY_MIN_GAP_S:
                    self._opensky_cache = (time.time(), self._opensky(client))
                merged = {a["id"]: (now - (a["seenS"] or 0.0), a) for a in self._opensky_cache[1]}
                source = "opensky"
                partial.append("adsb.lol unavailable; serving OpenSky fallback")
            except Exception as exc:  # noqa: BLE001
                raise FeedError("; ".join(partial + [f"opensky: {describe(exc)}"])) from exc
        elif len(live) < len(CIRCLES) and now < self._opensky_fail_until:
            partial.append(f"opensky gap fill: paused {self._opensky_fail_until - now:.0f} s after a failure")
        elif len(live) < len(CIRCLES) and os.environ.get("OPENSKY_CLIENT_ID") and os.environ.get("OPENSKY_CLIENT_SECRET"):
            # keyed OpenSky fills only the circles adsb.lol could not serve (shared serverless IPs get rate-limited)
            gaps = [CIRCLES[i] for i in range(len(CIRCLES)) if i not in live]
            try:
                if self._opensky_cache is None or now - self._opensky_cache[0] >= OPENSKY_MIN_GAP_S:
                    self._opensky_cache = (time.time(), self._opensky(client))
                filled = 0
                for a in self._opensky_cache[1]:
                    if a["id"] not in merged and any(_in_circle(a, c) for c in gaps):
                        merged[a["id"]] = (now - (a["seenS"] or 0.0), a)
                        filled += 1
                source = "adsb.lol+opensky"
                partial = [p for p in partial if not p.startswith("adsb.lol")]  # gaps and cooldown covered
                gap_note = f"{len(gaps)} adsb.lol circle(s) filled by OpenSky ({filled} aircraft)"
            except Exception as exc:  # noqa: BLE001
                self._opensky_fail_until = time.time() + OPENSKY_FAIL_BACKOFF_S  # e.g. cloud IPs that OpenSky drops
                partial.append(f"opensky gap fill: {describe(exc)}")
        items = []
        for pos_t, ac in merged.values():
            items.append({**ac, "seenS": round(max(0.0, now - pos_t), 1)})
        items.sort(key=lambda a: a["id"])
        data = {"items": items, "primary": source,
                "coverage": [{"lat": c[0], "lng": c[1], "radiusNm": c[2],
                              "fetchedAt": iso(self._snapshots[i][0]) if i in self._snapshots else None,
                              "error": self._circle_errors.get(i)} for i, c in enumerate(CIRCLES)]}
        if gap_note:
            data["gapFill"] = gap_note
        if partial:
            data["_partial"] = partial
        return data

    # -- history ------------------------------------------------------------------------------------------------------
    def on_success(self, data: dict) -> None:
        now = time.time()
        with self._trail_lock:
            for ac in data["items"]:
                seen_at = now - (ac.get("seenS") or 0.0)
                ring = self._trails.setdefault(ac["id"], deque(maxlen=TRAIL_LEN))
                if ring and seen_at - ring[-1]["t"] < TRAIL_MIN_GAP_S:
                    continue
                ring.append({"t": round(seen_at, 1), "lng": ac["lng"], "lat": ac["lat"], "altM": ac["altM"]})
            for hex_id in [h for h, ring in self._trails.items() if not ring or now - ring[-1]["t"] > TRAIL_FORGET_S]:
                del self._trails[hex_id]

    def trail(self, hex_id: str) -> list[dict]:
        with self._trail_lock:
            return list(self._trails.get(hex_id.lower(), ()))

    def gnss(self) -> list[dict]:
        items = (self._data or {}).get("items") or []
        return [{"hex": a["id"], "lng": a["lng"], "lat": a["lat"], "degraded": is_degraded(a), "nic": a["nic"], "nacp": a["nacp"]}
                for a in items if is_gnss_sample(a)]
