"""Live public-data endpoints (`/api/sources`, `/api/live/*`, `/api/env/*`, `/api/civil/*`).

Every payload carries `status`, `source`, `licence`, `attribution`, `fetchedAt` and `stale` from the feed contract.
Handlers are sync `def` so FastAPI runs them in its threadpool; each feed serialises its own upstream fetches.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from . import feeds
from .feeds.ais import merge_vessels
from .feeds.base import feeds_disabled, parallel

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
