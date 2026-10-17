"""Live public-data endpoints (`/api/sources`, `/api/live/*`, `/api/env/*`, `/api/civil/*`).

Every payload carries `status`, `source`, `licence`, `attribution`, `fetchedAt` and `stale` from the feed contract.
Handlers are sync `def` so FastAPI runs them in its threadpool; each feed serialises its own upstream fetches.
Feed payloads carry a `Vercel-CDN-Cache-Control` header derived from the feed TTL (see `base.edge_cache_header`) so the
edge serves one copy to every user instead of each serverless instance hitting the upstream.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from . import feeds
from .feeds.ais import merge_vessels
from .feeds import markhojd
from .feeds.base import FeedError, edge_cache_header, feeds_disabled, parallel

router = APIRouter(prefix="/api")
BROWSER_CACHE = "public, max-age=0, must-revalidate"
SOURCES_EDGE_CACHE = "max-age=30, stale-while-revalidate=120"


def _edge(response: Response, payload: dict, ttl_s: float) -> dict:
    response.headers["Cache-Control"] = BROWSER_CACHE
    response.headers["Vercel-CDN-Cache-Control"] = edge_cache_header(ttl_s, payload.get("status", ""))
    return payload


def _feed(response: Response, feed) -> dict:
    return _edge(response, feed.get(), feed.ttl_s)


@router.get("/sources")
def sources(response: Response,
            probe: bool = Query(True, description="Fetch every feed (TTL-cached) so statuses are current")) -> dict:
    if probe and not feeds_disabled():
        parallel(lambda f: f.get(), list(feeds.FEEDS.values()), max_workers=len(feeds.FEEDS))
    rows = feeds.statuses()
    if probe:
        response.headers["Cache-Control"] = BROWSER_CACHE
        response.headers["Vercel-CDN-Cache-Control"] = SOURCES_EDGE_CACHE
    return {"disabled": feeds_disabled(), "sources": rows,
            "attribution": [f"{r['label']}: {r['attribution']} ({r['licence']})" for r in rows]}


@router.get("/live/aircraft")
def aircraft(response: Response) -> dict:
    return _feed(response, feeds.ADSB)


@router.get("/live/aircraft/{hex_id}/trail")
def aircraft_trail(hex_id: str) -> dict:
    points = feeds.ADSB.trail(hex_id)
    if not points:
        raise HTTPException(404, f"no trail for {hex_id} in this process")
    st = feeds.ADSB.status()
    return {"id": hex_id.lower(), "points": points, "status": st["status"], "source": st["label"], "licence": st["licence"],
            "attribution": st["attribution"], "fetchedAt": st["lastOkAt"], "stale": st["stale"]}


@router.get("/live/gnss")
def gnss(response: Response) -> dict:
    payload = feeds.ADSB.get()
    samples = feeds.ADSB.gnss()
    body = {"status": payload["status"], "source": payload["source"], "licence": payload["licence"],
            "attribution": payload["attribution"], "fetchedAt": payload["fetchedAt"], "stale": payload["stale"],
            "note": "Airborne ADS-B (non-MLAT) positions; degraded = NIC < 7 or NACp < 8. Indicative only: low integrity "
                    "can also come from old avionics; aggregate many aircraft before inferring interference.",
            "generatedAt": payload["generatedAt"], "samples": samples, "count": len(samples),
            "degradedCount": sum(1 for s in samples if s["degraded"])}
    return _edge(response, body, feeds.ADSB.ttl_s)


@router.get("/live/vessels")
def vessels(response: Response) -> dict:
    payload = feeds.AIS.get()
    stream = feeds.AISSTREAM.get()
    if stream["status"] in ("working", "partial") and stream.get("items"):
        payload["items"] = merge_vessels(payload.get("items") or [], stream["items"])
        payload["count"] = len(payload["items"])
        payload["source"] = f"{payload['source']} + {stream['source']}"
        payload["attribution"] = f"{payload['attribution']}; {stream['attribution']}"
    payload["streams"] = {"aisstream": {"status": stream["status"], "note": stream["note"], "count": stream["count"]}}
    return _edge(response, payload, feeds.AIS.ttl_s)


@router.get("/live/vessels/{mmsi}/history")
def vessel_history(mmsi: int) -> dict:
    points = feeds.AIS.history(mmsi)
    if not points:
        raise HTTPException(404, f"no history for MMSI {mmsi} in this process")
    st = feeds.AIS.status()
    return {"id": mmsi, "points": points, "status": st["status"], "source": st["label"], "licence": st["licence"],
            "attribution": st["attribution"], "fetchedAt": st["lastOkAt"], "stale": st["stale"]}


@router.get("/env/observations")
def observations(response: Response) -> dict:
    return _feed(response, feeds.SMHI_OBS)


@router.get("/env/warnings")
def warnings(response: Response) -> dict:
    return _feed(response, feeds.SMHI_WARNINGS)


@router.get("/env/grid")
def grid(response: Response) -> dict:
    return _feed(response, feeds.OPEN_METEO)


@router.get("/env/radar")
def radar(response: Response) -> dict:
    return _feed(response, feeds.RAINVIEWER)


@router.get("/env/space")
def space(response: Response) -> dict:
    return _feed(response, feeds.SWPC)


@router.get("/civil/police")
def police(response: Response) -> dict:
    return _feed(response, feeds.POLISEN)


@router.get("/civil/crisis")
def crisis(response: Response) -> dict:
    return _feed(response, feeds.KRISINFO)


@router.get("/civil/traffic")
def traffic(response: Response) -> dict:
    return _feed(response, feeds.TRAFIKVERKET)


@router.get("/env/fires")
def fires(response: Response) -> dict:
    return _feed(response, feeds.FIRMS)


def _lnglat(text: str) -> tuple[float, float]:
    try:
        lng, lat = (float(v) for v in text.split(","))
    except ValueError:
        raise HTTPException(422, "expected 'lng,lat'") from None
    if not markhojd.in_sweden_box(lng, lat):
        raise HTTPException(422, "point outside Sweden (Lantmäteriet elevation covers Sweden only)")
    return lng, lat


def _terrain():
    if not feeds.MARKHOJD.available():
        raise HTTPException(503, "terrain not configured: " + feeds.MARKHOJD.status()["note"])
    return feeds.MARKHOJD


@router.get("/terrain/elevation")
def terrain_elevation(at: str = Query(..., description="lng,lat")) -> dict:
    p = _lnglat(at)
    try:
        z = _terrain().elevations([p])[0]
    except FeedError as exc:
        raise HTTPException(502, str(exc)) from None
    return {"lng": p[0], "lat": p[1], "groundM": z, "datum": "RH 2000", "source": feeds.MARKHOJD.attribution}


@router.get("/terrain/profile")
def terrain_profile(path: str = Query(..., description="lng,lat;lng,lat;... (2-100 vertices)"),
                    samples: int = Query(200, ge=2, le=1000)) -> dict:
    """Ground elevation sampled evenly along a polyline (measure tool, ad-hoc paths)."""
    parts = [p for p in path.split(";") if p.strip()]
    if not 2 <= len(parts) <= 100:
        raise HTTPException(422, "path needs 2-100 'lng,lat' vertices separated by ';'")
    coords = [_lnglat(p) for p in parts]
    try:
        return _terrain().profile(coords, samples)
    except FeedError as exc:
        raise HTTPException(502, str(exc)) from None


@router.get("/terrain/los")
def terrain_los(a: str = Query(..., description="observer lng,lat"), b: str = Query(..., description="target lng,lat"),
                ha: float = Query(2.0, ge=0, le=20_000), hb: float = Query(2.0, ge=0, le=20_000)) -> dict:
    pa, pb = _lnglat(a), _lnglat(b)
    try:
        return _terrain().line_of_sight(pa, pb, ha, hb)
    except FeedError as exc:
        raise HTTPException(502, str(exc)) from None
