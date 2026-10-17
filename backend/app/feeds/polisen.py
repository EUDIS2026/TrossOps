"""Swedish Police Authority public event feed (`https://polisen.se/api/events`, latest ~500 events).

Locations are coarse: `location.gps` is a "lat,lng" string at a municipality centroid, or at a county centroid when
`location.name` is a county ("... län"); `precision` reports which. (Observed 2026-10: all 500 events carried county
centroids, i.e. only 20 distinct points.) The municipality/place is the last comma-separated part of `name`
("16 oktober 21.08, Mord/dråp, försök, Stockholm") and is exposed as `placeName`. `datetime` looks like
"2026-09-30 0:00:12 +02:00" (not ISO; the hour is not zero-padded) and is normalised to ISO 8601.
"""
from __future__ import annotations

import re

import httpx

from .base import Feed, FeedError, num

EVENTS_URL = "https://polisen.se/api/events"
BASE = "https://polisen.se"
KEYWORDS: dict[str, re.Pattern] = {
    "drone": re.compile(r"drönar|\bdrone|\buav\b|obemannad", re.I),
    "sabotage": re.compile(r"sabotage", re.I),
    "explosion": re.compile(r"explosion|detonation|spräng", re.I),
    "fire": re.compile(r"\bbrand", re.I),
    "shooting": re.compile(r"skottlossning|skjutning|skott avlo", re.I),
    "bomb-threat": re.compile(r"bombhot", re.I),
    "suspicious-object": re.compile(r"(misstänkt|farligt) föremål", re.I),
}
_DT_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2}):(\d{2})\s*([+-]\d{2}):?(\d{2})\s*$")


def parse_gps(text) -> tuple[float | None, float | None]:
    """'59.602496,18.138438' (lat,lng) -> (lng, lat)."""
    if not isinstance(text, str) or "," not in text:
        return None, None
    lat_s, lng_s = text.split(",", 1)
    lat, lng = num(lat_s.strip()), num(lng_s.strip())
    if lat is None or lng is None:
        return None, None
    return lng, lat


def parse_datetime(text) -> str | None:
    m = _DT_RE.match(text or "")
    if not m:
        return text or None
    y, mo, d, h, mi, s, oh, om = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}T{int(h):02d}:{mi}:{s}{oh}:{om}"


def keywords(*texts) -> list[str]:
    blob = " ".join(t for t in texts if isinstance(t, str))
    return [k for k, pat in KEYWORDS.items() if pat.search(blob)]


def place_name(name) -> str | None:
    if not isinstance(name, str) or "," not in name:
        return None
    return name.rsplit(",", 1)[1].strip() or None


def normalise(ev: dict) -> dict:
    loc = ev.get("location") or {}
    lng, lat = parse_gps(loc.get("gps"))
    name = loc.get("name")
    path = ev.get("url") or ""
    return {"id": ev.get("id"), "datetime": parse_datetime(ev.get("datetime")), "name": ev.get("name"),
            "summary": ev.get("summary"), "type": ev.get("type"),
            "url": path if path.startswith("http") else (BASE + path if path else None), "locationName": name,
            "placeName": place_name(ev.get("name")),
            "lng": lng, "lat": lat,
            "precision": "county" if isinstance(name, str) and name.strip().lower().endswith(" län") else "municipality",
            "keywords": keywords(ev.get("type"), ev.get("name"), ev.get("summary"))}


class PolisenFeed(Feed):
    id = "polisen"
    label = "Polisen public events"
    category = "civil"
    url = EVENTS_URL
    licence = "Public API from the Swedish Police Authority (öppna data); verify reuse terms on polisen.se"
    attribution = "Källa: Polisen (polisen.se)"
    ttl_s = 300.0
    note = ("Published police event notices; positions are county or municipality centroids (see `precision`), never "
            "incident locations.")

    def fetch(self, client: httpx.Client) -> dict:
        r = client.get(EVENTS_URL)
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, list):
            raise FeedError("unexpected payload (expected a list)")
        return {"items": [normalise(e) for e in body if isinstance(e, dict)]}
