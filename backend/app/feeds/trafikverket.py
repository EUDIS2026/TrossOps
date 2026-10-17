"""Trafikverket open API (road situations: accidents, obstructions, restrictions/closures).

POST `https://api.trafikinfo.trafikverket.se/v2/data.json` with an XML query body; requires a free key in
`TRAFIKVERKET_API_KEY`. Response: `{"RESPONSE": {"RESULT": [{"Situation": [{"Deviation": [...]}]}]}}`; an error is
reported as `RESULT[0].ERROR` (e.g. HTTP 401 "Invalid authentication"). One item per deviation. Geometry is a WKT
string — `Geometry.Point.WGS84` (schema 1.5) or `Geometry.WGS84` (older schemas); the first coordinate is used.
"""
from __future__ import annotations

import os
import re
from xml.sax.saxutils import quoteattr

import httpx

from .base import Feed, FeedError, num

DATA_URL = "https://api.trafikinfo.trafikverket.se/v2/data.json"
MESSAGE_TYPES = ("Olycka", "Hinder", "Restriktion", "Viktig trafikinformation")
_WKT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")


def query_xml(key: str, limit: int = 1000) -> str:
    types = "".join(f'<EQ name="Deviation.MessageType" value={quoteattr(t)} />' for t in MESSAGE_TYPES)
    return (f"<REQUEST><LOGIN authenticationkey={quoteattr(key)} />"
            f'<QUERY objecttype="Situation" schemaversion="1.5" limit="{int(limit)}">'
            f"<FILTER><OR>{types}</OR></FILTER></QUERY></REQUEST>")


def wkt_point(geometry) -> tuple[float | None, float | None]:
    if not isinstance(geometry, dict):
        return None, None
    wkt = (geometry.get("Point") or {}).get("WGS84") if isinstance(geometry.get("Point"), dict) else None
    wkt = wkt or geometry.get("WGS84") or ((geometry.get("Line") or {}).get("WGS84") if isinstance(geometry.get("Line"), dict) else None)
    m = _WKT_RE.search(wkt or "")
    if not m:
        return None, None
    return num(m.group(1)), num(m.group(2))


def normalise(body: dict) -> list[dict]:
    results = ((body or {}).get("RESPONSE") or {}).get("RESULT") or []
    if results and isinstance(results[0], dict) and results[0].get("ERROR"):
        err = results[0]["ERROR"]
        raise FeedError(f"{err.get('SOURCE', 'API')}: {err.get('MESSAGE', 'error')}")
    out = []
    for result in results:
        for situation in result.get("Situation") or []:
            for dev in situation.get("Deviation") or []:
                lng, lat = wkt_point(dev.get("Geometry"))
                out.append({"id": dev.get("Id"), "type": dev.get("MessageType"), "severity": dev.get("SeverityText"),
                            "severityCode": dev.get("SeverityCode"), "message": dev.get("Message") or dev.get("Header"),
                            "roadNumber": dev.get("RoadNumber"), "location": dev.get("LocationDescriptor"),
                            "lng": lng, "lat": lat, "start": dev.get("StartTime"), "end": dev.get("EndTime")})
    return out


class TrafikverketFeed(Feed):
    id = "trafikverket"
    label = "Trafikverket road situations"
    category = "civil"
    url = DATA_URL
    licence = "Trafikverket open data (CC0 1.0 per Trafikverket API terms; verify on data.trafikverket.se)"
    attribution = "Källa: Trafikverket"
    ttl_s = 300.0
    note = "Accidents, obstructions, restrictions and important traffic information on state roads."
    credential_env = ("TRAFIKVERKET_API_KEY",)
    credential_help = ("Register for a free key at https://data.trafikverket.se (Trafikverket öppna API, "
                       "'Skapa konto' then 'Mina sidor' > 'Nycklar') and set TRAFIKVERKET_API_KEY.")

    def fetch(self, client: httpx.Client) -> dict:
        r = client.post(DATA_URL, content=query_xml(os.environ["TRAFIKVERKET_API_KEY"]).encode("utf-8"),
                        headers={"Content-Type": "text/xml"})
        if r.status_code in (400, 401, 403):
            try:
                normalise(r.json())
            except FeedError:
                raise
            except Exception:  # noqa: BLE001
                pass
        r.raise_for_status()
        return {"items": normalise(r.json())}
