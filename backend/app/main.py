"""TrossOps national scene API. Everything served here is synthetic unless the payload says `public` or `observed`."""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from . import envfile  # noqa: F401  (loads backend/.env before any feed reads its key)
from . import httpcache, planner, rules, views
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
_t_engine = time.perf_counter()
engine = Engine(_db, speed=_speed, start_s=_start_s, epoch=_epoch_from_env(_speed, _start_s))
# cold-start diagnostics (serverless): how long the world took and whether the committed route cache covered it
BOOT = {"engineS": round(time.perf_counter() - _t_engine, 2), "routeCacheEntries": len(engine.world.orbat.cache.data),
        "routeCacheMissed": bool(engine.world.orbat.cache.dirty), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
weather = WeatherService()

app = FastAPI(title="TrossOps National Scene API", version=API_VERSION)
app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=httpcache.GZIP_LEVEL)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "If-None-Match"], max_age=600)

SECURITY_HEADERS = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"), (b"x-frame-options", b"DENY"),
                    (b"cross-origin-resource-policy", b"same-site")]


class SecurityHeaders:
    """Pure ASGI (no BaseHTTPMiddleware: that buffers and breaks the SSE stream). Adds headers a public JSON API
    should carry unless the handler already set them."""

    def __init__(self, inner) -> None:
        self.inner = inner

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [(k, v) for k, v in SECURITY_HEADERS if k not in present]
            await send(message)
        await self.inner(scope, receive, send_with_headers)


app.add_middleware(SecurityHeaders)

# Public demo: POSTs that only compute (route options, optimiser) stay open; everything that changes the shared world
# (reports, acknowledgements, decisions, plans, events, scenario injection) is refused for visitors.
READ_ONLY_POSTS = {"/api/plan/route", "/api/strategy/optimize"}
PUBLIC_READ_ONLY = "Read-only public demo: reports, decisions, plans and scenario injection are disabled here. Run TrossOps locally to use them."
TERRAIN_PER_MIN = 30  # terrain requests per client per minute (each one is a call on the operator's Lantmäteriet account)


class PublicDemo:
    """Pure ASGI (keeps the SSE stream unbuffered). Active only with TROSSOPS_PUBLIC=1. The terrain limit is per
    serverless instance, so it bounds abuse rather than metering exactly."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.hits: dict[str, list[float]] = {}

    @staticmethod
    def _client(scope) -> str:
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-for":
                return v.decode("latin-1").split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "?"

    def _over_limit(self, ip: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self.hits.get(ip, []) if now - t < 60.0]
        if len(recent) >= TERRAIN_PER_MIN:
            self.hits[ip] = recent
            return True
        recent.append(now)
        self.hits[ip] = recent
        if len(self.hits) > 10_000:  # bounded memory: forget idle clients
            self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < 60.0}
        return False

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not envfile.public_mode():
            await self.inner(scope, receive, send)
            return
        path, method = scope.get("path", ""), scope.get("method", "GET")
        if method in ("POST", "PUT", "PATCH", "DELETE") and path not in READ_ONLY_POSTS:
            await JSONResponse({"detail": PUBLIC_READ_ONLY}, status_code=403)(scope, receive, send)
            return
        if path.startswith("/api/terrain/") and self._over_limit(self._client(scope)):
            await JSONResponse({"detail": f"Terrain requests are limited to {TERRAIN_PER_MIN} a minute on the public demo."}, status_code=429,
                               headers={"Retry-After": "60"})(scope, receive, send)
            return
        await self.inner(scope, receive, send)


app.add_middleware(PublicDemo)


def _loc(err: dict) -> str:
    return ".".join(str(p) for p in err.get("loc", ()) if p not in ("body",)) or "request"


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with a readable `detail` string (the frontend shows `detail`) plus the structured `errors`.
    The offending input is not echoed back."""
    errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
    detail = "; ".join(f"{_loc(e)}: {e['msg']}" for e in errors)[:500] or "Invalid request"
    return JSONResponse({"detail": detail, "errors": errors[:20]}, status_code=422)


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


# ---- shared parameter types (finite, bounded) -------------------------------------------------------------------
MAX_AT_S = 366 * 86_400.0  # scenario seconds: one year of replay / simulation is plenty
AtQuery = Annotated[float | None, Query(ge=0, le=MAX_AT_S, allow_inf_nan=False, description="scenario seconds (default: now)")]
RoleQuery = Annotated[str | None, Query(max_length=64)]
IdPath = Annotated[str, PathParam(min_length=1, max_length=128)]
MAX_TRACK_SAMPLES = 5_000


def _check_role(role: str | None) -> None:
    if role and role not in {r.id for r in views.ROLES}:
        raise HTTPException(404, "Unknown role")


def _now_or(at: float | None) -> float:
    return engine.now_s() if at is None else at


_world_memo = httpcache.Memo()
_views_memo = httpcache.Memo()
_layout_memo: dict[str, httpcache.Encoded] = {}
_per_eval = httpcache.PerEvaluation()

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
            "entities": len(engine.world.entities), "formations": len(engine.world.formations), "feeds": live_router is not None, "boot": BOOT}


@app.get("/api/clock")
def clock() -> dict:
    return engine.clock()


@app.get("/api/views")
def get_views(request: Request) -> Response:
    """Static per deployment: served from pre-encoded bytes with an ETag."""
    enc = _views_memo.get(views, lambda: {
        "roles": [r.model_dump() for r in views.ROLES], "layers": [l.model_dump() for l in views.LAYERS], "rules": rules.rule_catalogue(),
        "channels": [{"id": k, **v} for k, v in CHANNEL_META.items()], "regionScope": views.REGION_SCOPE, "exclusiveGroups": views.EXCLUSIVE_GROUPS,
        "publicDemo": envfile.public_mode()})
    return httpcache.respond(request, enc)


@app.get("/api/world")
def world(request: Request) -> Response:
    """Order of battle, declared motion and shared route geometry (changes only when `catalogRevision` does).
    ~2 MB of JSON: encoded and gzipped once per catalog, revalidated by ETag (304 when unchanged)."""
    return httpcache.respond(request, _world_memo.get(engine.catalog()))


@app.get("/api/sites/{site_id}/layout")
def site_layout(request: Request, site_id: IdPath) -> Response:
    enc = _layout_memo.get(site_id)
    if enc is None:
        lay = engine.world.layouts.get(site_id)
        if not lay:
            raise HTTPException(404, "Site not found")
        enc = _layout_memo[site_id] = httpcache.Encoded(lay.to_api())
    return httpcache.respond(request, enc, "public, max-age=300")


@app.get("/api/scene/snapshot")
def snapshot(at: AtQuery = None, role: RoleQuery = None) -> dict:
    _check_role(role)
    t = _now_or(at)
    ev = engine.evaluate(t)
    base = _per_eval.get(ev, ("snapshot", role), lambda: engine.snapshot(t, role))
    now = engine.now_s()  # per-request fields; everything else is a function of the evaluation
    return {**base, "serverNow": datetime.now(timezone.utc).isoformat(), "nowS": round(now, 1), "live": t >= now - 2, "future": t > now + 5}


@app.get("/api/scene/entities")
def entities(at: AtQuery = None) -> dict:
    return engine.kinematics(at)


@app.get("/api/scene/tracks/{entity_id}")
def tracks(entity_id: IdPath, from_s: float | None = Query(default=None, alias="from", ge=0, le=MAX_AT_S, allow_inf_nan=False),
           to_s: float | None = Query(default=None, alias="to", ge=0, le=MAX_AT_S, allow_inf_nan=False),
           step: float = Query(default=30, ge=1, le=86_400, allow_inf_nan=False)) -> dict:
    if entity_id not in engine.world.entities:
        raise HTTPException(404, "Entity not found")
    now = engine.now_s()
    to_s = now if to_s is None else min(to_s, now)
    from_s = max(0.0, to_s - 1200) if from_s is None else from_s
    if (to_s - from_s) / step > MAX_TRACK_SAMPLES:
        raise HTTPException(422, f"too many samples: (to - from) / step must be at most {MAX_TRACK_SAMPLES}")
    return engine.tracks(entity_id, from_s, to_s, step)


@app.get("/api/scene/attention")
def attention(at: AtQuery = None, resolution: Literal["national", "regional", "local"] = "regional", role: RoleQuery = None) -> dict:
    _check_role(role)
    t = _now_or(at)
    ev = engine.evaluate(t)
    base = _per_eval.get(ev, ("attention", resolution, role), lambda: engine.attention(t, resolution, role))
    return {**base, "atS": round(t, 1)}


@app.get("/api/scene/predictions")
def predictions(at: AtQuery = None) -> dict:
    ev = engine.evaluate(_now_or(at))
    return {"atS": round(ev.t, 1), "worldRevision": ev.revision, "predictions": [p.model_dump() for p in ev.fx.predictions]}


@app.get("/api/entities/{entity_id}")
def entity_detail(entity_id: IdPath, at: AtQuery = None) -> dict:
    try:
        return engine.entity_detail(entity_id, at)
    except KeyError:
        raise HTTPException(404, "Entity not found") from None


@app.get("/api/inputs")
def list_inputs(at: AtQuery = None, channel: Annotated[str | None, Query(max_length=64)] = None) -> dict:
    ev = engine.evaluate(_now_or(at))
    items = [i.model_dump() for i in ev.inputs if channel is None or i.channel == channel]
    return {"atS": round(ev.t, 1), "worldRevision": ev.revision, "count": len(items), "inputs": items}


@app.post("/api/inputs", status_code=201)
def post_input(body: InputIn) -> dict:
    report = engine.post_input(body)
    return {"input": report.model_dump(), "worldRevision": engine.revision}


@app.get("/api/alerts")
def alerts(at: AtQuery = None) -> dict:
    ev = engine.evaluate(_now_or(at))
    return {"atS": round(ev.t, 1), "worldRevision": ev.revision, "alerts": [a.model_dump() for a in ev.fx.alerts]}


@app.post("/api/alerts/{alert_id}/ack")
def ack(alert_id: IdPath) -> dict:
    return engine.ack(alert_id)


@app.get("/api/interventions")
def interventions(at: AtQuery = None) -> dict:
    ev = engine.evaluate(_now_or(at))
    return {"atS": round(ev.t, 1), "worldRevision": ev.revision, "interventions": [i.model_dump() for i in ev.fx.interventions]}


@app.post("/api/interventions/{intervention_id}/commit")
def commit(intervention_id: IdPath, body: CommitIn) -> dict:
    try:
        return engine.commit(intervention_id, body.optionId, body.expectedRevision)
    except ValueError:
        raise HTTPException(409, "World revision changed; refresh before committing") from None
    except KeyError:
        raise HTTPException(404, "Intervention or option not found") from None


@app.post("/api/interventions/{intervention_id}/abort")
def abort(intervention_id: IdPath) -> dict:
    if intervention_id not in engine.commits:
        raise HTTPException(404, "Intervention not committed")
    return engine.abort(intervention_id)


@app.post("/api/strategy/optimize")
def optimise(at: AtQuery = None) -> dict:
    return engine.optimise(at)


@app.post("/api/events")
def apply_event(event: EventIn) -> dict:
    try:
        return engine.apply_event(event)
    except ValueError:
        raise HTTPException(409, "World revision changed; refresh before applying an event") from None
    except KeyError:
        raise HTTPException(404, "Asset not found") from None


def _check_lnglat(p: list) -> None:
    lng, lat = p[0], p[1]
    if lng is None or lat is None or not (-180 <= lng <= 180 and -90 <= lat <= 90):
        raise ValueError("points are [lng, lat(, altM)] in degrees (lng -180..180, lat -90..90)")


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
MAX_PLAN_POINTS = 20_000


class PlanIn(BaseModel):
    entityId: str = Field(min_length=1, max_length=128)
    to: list[FiniteFloat] = Field(min_length=2, max_length=2)

    @field_validator("to")
    @classmethod
    def _to_in_range(cls, v: list[float]) -> list[float]:
        _check_lnglat(v)
        return v


class PlanCommitIn(BaseModel):
    """Validated in full before it is persisted: a malformed plan in the mutation log would fail every replay."""
    entityId: str = Field(min_length=1, max_length=128)
    path: list[Annotated[list[FiniteFloat | None], Field(min_length=2, max_length=3)]] = Field(min_length=2, max_length=MAX_PLAN_POINTS)
    speeds: list[Annotated[float, Field(gt=0, le=1_000, allow_inf_nan=False)]] = Field(max_length=MAX_PLAN_POINTS)
    airborne: bool = False
    label: str = Field(default="Planned route", max_length=200)
    expectedRevision: int = Field(ge=1)

    @field_validator("path")
    @classmethod
    def _points_in_range(cls, v: list[list[float | None]]) -> list[list[float | None]]:
        for p in v:
            _check_lnglat(p)
        return [p if len(p) == 3 else [p[0], p[1], None] for p in v]  # motion.Path reads p[2] (altitude or None)

    @model_validator(mode="after")
    def _one_speed_per_segment(self) -> "PlanCommitIn":
        if len(self.speeds) != len(self.path) - 1:
            raise ValueError("speeds must have one entry per segment")
        return self


@app.post("/api/plan/route")
def plan_route(body: PlanIn) -> dict:
    if body.entityId not in engine.world.entities:
        raise HTTPException(404, "Entity not found")
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
        from .feeds import MARKHOJD
        if MARKHOJD.available() and e.domain != "sea":  # ground and air only: a ship route has no terrain to profile
            planner.annotate_terrain(result, MARKHOJD)
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
    preset: str = Field(min_length=1, max_length=64)


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
def plan_cancel(entity_id: IdPath) -> dict:
    if entity_id not in engine.world.entities:
        raise HTTPException(404, "Entity not found")
    return engine.cancel_plan(entity_id)


@app.get("/api/environment/points")
def environment_points() -> dict:
    return {"source": "public city reference points", "points": PUBLIC_POINTS}


@app.get("/api/environment/forecast/{location}")
def environment_forecast(location: IdPath) -> dict:
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
