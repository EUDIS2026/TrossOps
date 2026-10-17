"""Live public-data endpoints (`/api/sources`, `/api/live/*`, `/api/env/*`, `/api/civil/*`).

Every payload carries `status`, `source`, `licence`, `attribution`, `fetchedAt` and `stale` from the feed contract.
Handlers are sync `def` so FastAPI runs them in its threadpool; each feed serialises its own upstream fetches.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from . import feeds
from .feeds.ais import merge_vessels
from .feeds import markhojd
from .feeds.base import FeedError, feeds_disabled, parallel

router = APIRouter(prefix="/api")


@router.get("/sources")
def sources(probe: bool = Query(True, description="Fetch every feed (TTL-cached) so statuses are current")) -> dict:
    if probe and not feeds_disabled():
        parallel(lambda f: f.get(), list(feeds.FEEDS.values()), max_workers=len(feeds.FEEDS))
    rows = feeds.statuses()
    return {"disabled": feeds_disabled(), "sources": rows,
            "attribution": [f"{r['label']}: {r['attribution']} ({r['licence']})" for r in rows]}


@router.get("/live/aircraft")
def aircraft() -> dict:
    return feeds.ADSB.get()


@router.get("/live/aircraft/{hex_id}/trail")
def aircraft_trail(hex_id: str) -> dict:
    points = feeds.ADSB.trail(hex_id)
    if not points:
        raise HTTPException(404, f"no trail for {hex_id} in this process")
    st = feeds.ADSB.status()
    return {"id": hex_id.lower(), "points": points, "status": st["status"], "source": st["label"], "licence": st["licence"],
            "attribution": st["attribution"], "fetchedAt": st["lastOkAt"], "stale": st["stale"]}


@router.get("/live/gnss")
def gnss() -> dict:
    payload = feeds.ADSB.get()
    samples = feeds.ADSB.gnss()
    return {"status": payload["status"], "source": payload["source"], "licence": payload["licence"],
            "attribution": payload["attribution"], "fetchedAt": payload["fetchedAt"], "stale": payload["stale"],
            "note": "Airborne ADS-B (non-MLAT) positions; degraded = NIC < 7 or NACp < 8. Indicative only: low integrity "
                    "can also come from old avionics; aggregate many aircraft before inferring interference.",
            "samples": samples, "count": len(samples), "degradedCount": sum(1 for s in samples if s["degraded"])}


@router.get("/live/vessels")
def vessels() -> dict:
    payload = feeds.AIS.get()
    stream = feeds.AISSTREAM.get()
    if stream["status"] in ("working", "partial") and stream.get("items"):
        payload["items"] = merge_vessels(payload.get("items") or [], stream["items"])
        payload["count"] = len(payload["items"])
        payload["source"] = f"{payload['source']} + {stream['source']}"
        payload["attribution"] = f"{payload['attribution']}; {stream['attribution']}"
    payload["streams"] = {"aisstream": {"status": stream["status"], "note": stream["note"], "count": stream["count"]}}
    return payload


@router.get("/live/vessels/{mmsi}/history")
def vessel_history(mmsi: int) -> dict:
    points = feeds.AIS.history(mmsi)
    if not points:
        raise HTTPException(404, f"no history for MMSI {mmsi} in this process")
    st = feeds.AIS.status()
    return {"id": mmsi, "points": points, "status": st["status"], "source": st["label"], "licence": st["licence"],
            "attribution": st["attribution"], "fetchedAt": st["lastOkAt"], "stale": st["stale"]}


@router.get("/env/observations")
def observations() -> dict:
    return feeds.SMHI_OBS.get()


@router.get("/env/warnings")
def warnings() -> dict:
    return feeds.SMHI_WARNINGS.get()


@router.get("/env/grid")
def grid() -> dict:
    return feeds.OPEN_METEO.get()


@router.get("/env/radar")
def radar() -> dict:
    return feeds.RAINVIEWER.get()


@router.get("/env/space")
def space() -> dict:
    return feeds.SWPC.get()


@router.get("/civil/police")
def police() -> dict:
    return feeds.POLISEN.get()


@router.get("/civil/crisis")
def crisis() -> dict:
    return feeds.KRISINFO.get()


@router.get("/civil/traffic")
def traffic() -> dict:
    return feeds.TRAFIKVERKET.get()


@router.get("/env/fires")
def fires() -> dict:
    return feeds.FIRMS.get()


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


@router.get("/terrain/los")
def terrain_los(a: str = Query(..., description="observer lng,lat"), b: str = Query(..., description="target lng,lat"),
                ha: float = Query(2.0, ge=0, le=20_000), hb: float = Query(2.0, ge=0, le=20_000)) -> dict:
    pa, pb = _lnglat(a), _lnglat(b)
    try:
        return _terrain().line_of_sight(pa, pb, ha, hb)
    except FeedError as exc:
        raise HTTPException(502, str(exc)) from None
