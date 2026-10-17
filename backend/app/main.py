"""TrossOps national scene API. Everything served here is synthetic unless the payload says `public` or `observed`."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import envfile  # noqa: F401  (loads backend/.env before any feed reads its key)
from . import planner, rules, views
from .engine import Engine
from .inputs import CHANNEL_META
from .models import CommitIn, EventIn, InputIn
from .weather import PUBLIC_POINTS, WeatherService

API_VERSION = "2.0.0"
default_db = Path(__file__).parents[1] / "data" / "trossops.sqlite"


def _epoch_from_env(speed: float, start_s: float):
    """Serverless hosts (Vercel) start a fresh process per instance: with TROSSOPS_EPOCH=hourly every instance
    derives the same scenario epoch from the wall clock, so the picture agrees across instances and restarts
    hourly instead of running away. An ISO timestamp pins the epoch exactly; unset keeps the local behaviour."""
    from datetime import datetime, timedelta, timezone
    raw = os.environ.get("TROSSOPS_EPOCH")
    if not raw:
        return None
    if raw == "hourly":
        now = datetime.now(timezone.utc)
        return now.replace(minute=0, second=0, microsecond=0) - timedelta(seconds=start_s / speed)
    return datetime.fromisoformat(raw)


_speed = float(os.environ.get("TROSSOPS_CLOCK_SPEED", "1"))
_start_s = float(os.environ.get("TROSSOPS_START_S", "0"))
_db = Path(os.environ["TROSSOPS_DB_PATH"]) if os.environ.get("TROSSOPS_DB_PATH") else (Path("/tmp/trossops.sqlite") if os.environ.get("VERCEL") else default_db)
engine = Engine(_db, speed=_speed, start_s=_start_s, epoch=_epoch_from_env(_speed, _start_s))
weather = WeatherService()

app = FastAPI(title="TrossOps National Scene API", version=API_VERSION)
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])

try:  # real public feeds (adsb.lol, Digitraffic, SMHI, Open-Meteo, RainViewer, polisen.se, Krisinformation, NOAA)
    from .routes_live import router as live_router
    from . import feed_inputs
    app.include_router(live_router)
    engine.external_inputs = feed_inputs.inputs_for_engine
except ImportError:  # pragma: no cover - feeds package not installed in this build
    live_router = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "working", "mode": "synthetic", "apiVersion": API_VERSION, "clock": engine.clock(), "rules": len(rules.RULES),
            "entities": len(engine.world.entities), "formations": len(engine.world.formations), "feeds": live_router is not None}


@app.get("/api/clock")
def clock() -> dict:
    return engine.clock()


@app.get("/api/views")
def get_views() -> dict:
    return {"roles": [r.model_dump() for r in views.ROLES], "layers": [l.model_dump() for l in views.LAYERS], "rules": rules.rule_catalogue(),
            "channels": [{"id": k, **v} for k, v in CHANNEL_META.items()], "regionScope": views.REGION_SCOPE, "exclusiveGroups": views.EXCLUSIVE_GROUPS}


@app.get("/api/world")
def world() -> dict:
    """Order of battle, declared motion and shared route geometry (changes only when `catalogRevision` does)."""
    return engine.catalog()


@app.get("/api/sites/{site_id}/layout")
def site_layout(site_id: str) -> dict:
    lay = engine.world.layouts.get(site_id)
    if not lay:
        raise HTTPException(404, "Site not found")
    return lay.to_api()


@app.get("/api/scene/snapshot")
def snapshot(at: float | None = Query(default=None, ge=0), role: str | None = None) -> dict:
    if role and role not in {r.id for r in views.ROLES}:
        raise HTTPException(404, "Unknown role")
    return engine.snapshot(at, role)


@app.get("/api/scene/entities")
def entities(at: float | None = Query(default=None, ge=0)) -> dict:
    return engine.kinematics(at)


@app.get("/api/scene/tracks/{entity_id}")
def tracks(entity_id: str, from_s: float = Query(default=None, alias="from"), to_s: float = Query(default=None, alias="to"), step: float = Query(default=30, ge=1)) -> dict:
    if entity_id not in engine.world.entities:
        raise HTTPException(404, "Entity not found")
    now = engine.now_s()
    to_s = now if to_s is None else min(to_s, now)
    from_s = max(0.0, to_s - 1200) if from_s is None else from_s
    return engine.tracks(entity_id, from_s, to_s, step)


@app.get("/api/scene/attention")
def attention(at: float | None = None, resolution: str = "regional", role: str | None = None) -> dict:
    return engine.attention(at, resolution, role)


@app.get("/api/scene/predictions")
def predictions(at: float | None = None) -> dict:
    ev = engine.evaluate(engine.now_s() if at is None else at)
    return {"atS": round(ev.t, 1), "worldRevision": ev.revision, "predictions": [p.model_dump() for p in ev.fx.predictions]}


@app.get("/api/entities/{entity_id}")
def entity_detail(entity_id: str, at: float | None = None) -> dict:
    try:
        return engine.entity_detail(entity_id, at)
    except KeyError:
        raise HTTPException(404, "Entity not found") from None


@app.get("/api/inputs")
def list_inputs(at: float | None = None, channel: str | None = None) -> dict:
    ev = engine.evaluate(engine.now_s() if at is None else at)
    items = [i.model_dump() for i in ev.inputs if channel is None or i.channel == channel]
    return {"atS": round(ev.t, 1), "worldRevision": ev.revision, "count": len(items), "inputs": items}


@app.post("/api/inputs", status_code=201)
def post_input(body: InputIn) -> dict:
    report = engine.post_input(body)
    return {"input": report.model_dump(), "worldRevision": engine.revision}


@app.get("/api/alerts")
def alerts(at: float | None = None) -> dict:
    ev = engine.evaluate(engine.now_s() if at is None else at)
    return {"atS": round(ev.t, 1), "worldRevision": ev.revision, "alerts": [a.model_dump() for a in ev.fx.alerts]}


@app.post("/api/alerts/{alert_id}/ack")
def ack(alert_id: str) -> dict:
    return engine.ack(alert_id)


@app.get("/api/interventions")
def interventions(at: float | None = None) -> dict:
    ev = engine.evaluate(engine.now_s() if at is None else at)
    return {"atS": round(ev.t, 1), "worldRevision": ev.revision, "interventions": [i.model_dump() for i in ev.fx.interventions]}


@app.post("/api/interventions/{intervention_id}/commit")
def commit(intervention_id: str, body: CommitIn) -> dict:
    try:
        return engine.commit(intervention_id, body.optionId, body.expectedRevision)
    except ValueError:
        raise HTTPException(409, "World revision changed; refresh before committing") from None
    except KeyError:
        raise HTTPException(404, "Intervention or option not found") from None


@app.post("/api/interventions/{intervention_id}/abort")
def abort(intervention_id: str) -> dict:
    return engine.abort(intervention_id)


@app.post("/api/strategy/optimize")
def optimise(at: float | None = None) -> dict:
    return engine.optimise(at)


@app.post("/api/events")
def apply_event(event: EventIn) -> dict:
    try:
        return engine.apply_event(event)
    except ValueError:
        raise HTTPException(409, "World revision changed; refresh before applying an event") from None
    except KeyError:
        raise HTTPException(404, "Asset not found") from None


class PlanIn(BaseModel):
    entityId: str
    to: list[float] = Field(min_length=2, max_length=2)


class PlanCommitIn(BaseModel):
    entityId: str
    path: list[list[float | None]]
    speeds: list[float]
    airborne: bool = False
    label: str = "Planned route"
    expectedRevision: int = Field(ge=1)


@app.post("/api/plan/route")
def plan_route(body: PlanIn) -> dict:
    ev = engine.evaluate(engine.now_s())
    e = ev.entities.get(body.entityId)
    if not e:
        raise HTTPException(404, "Entity not found")
    restricted = [a for a in engine.world.areas if a["kind"] == "restricted_zone"]
    warnings = [{"title": i.title, "center": (i.position.longitudeDeg, i.position.latitudeDeg), "radiusM": i.radiusM or 50_000}
                for i in ev.inputs if i.channel == "weather_advisory" and i.position]
    try:
        try:
            from .feeds import TRAFIKVERKET
            incidents = (getattr(TRAFIKVERKET, '_data', None) or {}).get('items', [])
        except ImportError:
            incidents = []
        result = planner.plan(e, (body.to[0], body.to[1]), ev.fx.predictions, restricted, warnings, incidents)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {**result, "worldRevision": engine.revision, "atS": round(ev.t, 1)}


@app.post("/api/plan/commit")
def plan_commit(body: PlanCommitIn) -> dict:
    if len(body.speeds) != len(body.path) - 1 or len(body.path) < 2:
        raise HTTPException(422, "speeds must have one entry per segment")
    e = engine.evaluate(engine.now_s()).entities.get(body.entityId)
    fuel = e.readiness.fuelPct if e and e.readiness else None
    plan = {"path": body.path, "speeds": body.speeds, "startS": round(engine.now_s(), 1), "airborne": body.airborne, "label": body.label,
            "fuelStart": fuel, "fuelBurnPerKm": planner.BURN_PER_KM.get(e.kind, 0.1) if e else 0.0}
    try:
        return engine.commit_plan(body.entityId, plan, body.expectedRevision)
    except ValueError:
        raise HTTPException(409, "World revision changed; refresh before committing") from None
    except KeyError:
        raise HTTPException(404, "Entity not found") from None


class InjectIn(BaseModel):
    preset: str


@app.get("/api/scenario/presets")
def scenario_presets() -> dict:
    from . import scenario
    return {"presets": [{"id": k, "label": v} for k, v in scenario.PRESETS.items()]}


@app.post("/api/scenario/inject")
def scenario_inject(body: InjectIn) -> dict:
    try:
        return engine.inject(body.preset)
    except KeyError:
        raise HTTPException(404, "Unknown preset") from None


@app.post("/api/plan/{entity_id}/cancel")
def plan_cancel(entity_id: str) -> dict:
    return engine.cancel_plan(entity_id)


@app.get("/api/environment/points")
def environment_points() -> dict:
    return {"source": "public city reference points", "points": PUBLIC_POINTS}


@app.get("/api/environment/forecast/{location}")
def environment_forecast(location: str) -> dict:
    if location not in PUBLIC_POINTS:
        raise HTTPException(404, "Forecast point not found")
    return weather.get(location)


@app.get("/api/stream")
async def stream(interval: float = Query(default=1.0, ge=0.25, le=10)) -> StreamingResponse:
    """Server-sent events: `tick` (observed tracks) every interval, `revision` on any mutation."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def listener(msg: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, msg)

    engine.listeners.append(listener)

    async def gen():
        try:
            yield f"event: hello\ndata: {json.dumps(engine.clock())}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=interval)
                    yield f"event: {msg['type']}\ndata: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    tick = await asyncio.to_thread(engine.kinematics)
                    yield f"event: tick\ndata: {json.dumps(tick)}\n\n"
        finally:
            if listener in engine.listeners:
                engine.listeners.remove(listener)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
