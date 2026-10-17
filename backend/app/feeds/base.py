"""Shared contract for public-data feeds.

Every feed fetches on demand, caches the normalised payload in memory for `ttl_s`, and serves the last good payload
(marked `stale`) when the upstream fails. No background work is required: the module is safe on a stateless serverless
instance as well as in a long-lived uvicorn process.

Status vocabulary (AGENTS.md): `working` after a successful parse, `partial` when some sub-requests failed or when the
last good payload is being served after an error, `blocked` on errors with no data (or when disabled by configuration),
`adapter-only` when credentials are required and absent or before the first fetch in this process.
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import httpx

USER_AGENT = "TrossOps/1.0 (operational picture research demo)"
TIMEOUT_S = 8.0
CONNECT_RETRIES = 1
ERROR_BACKOFF_MAX_S = 60.0

# Shared edge cache (Vercel CDN) in front of the feed endpoints. Serverless instances do not share memory, so without it
# every instance (and every cold start) re-fetches upstream and shared-IP rate limits (adsb.lol 420/429) bite. The edge
# keeps one copy per URL fresh for half the feed TTL (5 s .. 5 min) and may serve it stale for one more TTL while it
# revalidates in the background. Payloads carry `fetchedAt` (upstream time) and `generatedAt` (function time), so a
# client can always tell how old an edge copy is. Responses without data are cached only briefly.
EDGE_FRESH_MIN_S, EDGE_FRESH_MAX_S = 5, 300
EDGE_SWR_MIN_S, EDGE_SWR_MAX_S = 10, 3600
EDGE_NO_DATA_S = 5

KT_TO_MPS = 0.514444
FT_TO_M = 0.3048
FPM_TO_MPS = 0.00508


def feeds_disabled() -> bool:
    return os.environ.get("TROSSOPS_FEEDS", "").strip().lower() in {"off", "0", "false", "no", "disabled"}


def on_vercel() -> bool:
    return bool(os.environ.get("VERCEL"))


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def iso_ms(ms: float | int | None) -> str | None:
    return None if ms is None else iso(float(ms) / 1000.0)


def num(value: Any) -> float | None:
    """Float or None; tolerates strings, '' and NaN."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def parallel(fn: Callable[[Any], Any], args: Iterable[Any], max_workers: int = 6) -> list[tuple[Any, Any, Exception | None]]:
    """Run `fn` over `args` concurrently; returns [(arg, result, error)] in input order. Never raises."""
    args = list(args)

    def wrap(arg: Any) -> tuple[Any, Any, Exception | None]:
        try:
            return arg, fn(arg), None
        except Exception as exc:  # noqa: BLE001 - collected and reported per sub-request
            return arg, None, exc

    if len(args) <= 1:
        return [wrap(a) for a in args]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(args))) as pool:
        return list(pool.map(wrap, args))


def edge_cache_header(ttl_s: float, status: str) -> str:
    """`Vercel-CDN-Cache-Control` value for a feed payload with this TTL and status (consumed by Vercel's CDN only;
    browsers get `Cache-Control: max-age=0, must-revalidate` so polling clients never read their own stale copy)."""
    if status not in ("working", "partial"):
        return f"max-age={EDGE_NO_DATA_S}"
    fresh = int(min(max(ttl_s / 2, EDGE_FRESH_MIN_S), EDGE_FRESH_MAX_S))
    swr = int(min(max(ttl_s, EDGE_SWR_MIN_S), EDGE_SWR_MAX_S))
    return f"max-age={fresh}, stale-while-revalidate={swr}"


class FeedError(Exception):
    """Upstream or parse failure with a short human-readable reason."""


def describe(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from {exc.request.url.host}"
    if isinstance(exc, httpx.TimeoutException):
        phase = {httpx.ConnectTimeout: "connect", httpx.ReadTimeout: "read", httpx.WriteTimeout: "write",
                 httpx.PoolTimeout: "pool"}.get(type(exc), "read")
        limit, host = TIMEOUT_S, None
        try:
            limit = float((exc.request.extensions.get("timeout") or {}).get(phase) or TIMEOUT_S)
            host = exc.request.url.host
        except RuntimeError:  # exception raised without an attached request
            pass
        return f"{phase} timeout after {limit:g} s" + (f" from {host}" if host else "")
    if isinstance(exc, httpx.HTTPError):
        return f"{type(exc).__name__}: {exc}"[:200]
    return f"{type(exc).__name__}: {exc}"[:200]


class Feed:
    id: str = ""
    label: str = ""
    category: str = ""  # 'air' | 'sea' | 'weather' | 'civil' | 'space'
    url: str = ""
    licence: str = ""
    attribution: str = ""
    ttl_s: float = 300.0
    note: str = ""
    credential_env: tuple[str, ...] = ()  # all must be set, else `adapter-only`
    credential_help: str = ""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self.transport = transport
        self._http: httpx.Client | None = None
        self._http_transport: httpx.BaseTransport | None = None
        self._data: dict | None = None
        self._fetched_at: float | None = None  # monotonic-free wall clock of last good parse
        self._last_ok: float | None = None
        self._last_error: str | None = None
        self._last_error_at: float | None = None
        self._partial_errors: list[str] = []
        self._failing = False  # last fetch attempt raised (data, if any, is stale)
        self._latency_ms: float | None = None

    # ---- subclass hooks -------------------------------------------------------------------------------------------
    def fetch(self, client: httpx.Client) -> dict:
        """Fetch + normalise. Return a dict of payload keys (at least `items` or `count`). May set `_partial`
        (list[str]) in the returned dict to report failed sub-requests. Raise on total failure."""
        raise NotImplementedError

    def count_of(self, data: dict) -> int:
        items = data.get("items")
        if isinstance(items, list):
            return len(items)
        return int(data.get("count") or 0)

    def empty(self) -> dict:
        return {"items": []}

    def on_success(self, data: dict) -> None:
        """Hook for per-process history (trails, AIS tracks)."""

    # ---- plumbing ----------------------------------------------------------------------------------------------------
    def client(self) -> httpx.Client:
        if self._http is None or self._http_transport is not self.transport:
            # Real network: retry a failed connection once (DNS hiccup, reset during a cold start's TLS handshake).
            # httpx retries only connection errors, never a request the upstream has already seen.
            transport = self.transport or httpx.HTTPTransport(retries=CONNECT_RETRIES)
            self._http = httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True,
                                      transport=transport)
            self._http_transport = self.transport
        return self._http

    def missing_credentials(self) -> list[str]:
        return [name for name in self.credential_env if not os.environ.get(name)]

    def reset(self) -> None:
        with self._lock:
            self._data = None
            self._fetched_at = self._last_ok = self._last_error = self._last_error_at = None
            self._partial_errors = []
            self._failing = False

    def _fresh(self, now: float) -> bool:
        return self._data is not None and self._fetched_at is not None and now - self._fetched_at < self.ttl_s

    def _backing_off(self, now: float) -> bool:
        if not self._failing or self._last_error_at is None:
            return False
        return now - self._last_error_at < min(self.ttl_s, ERROR_BACKOFF_MAX_S)

    def refresh(self, force: bool = False) -> None:
        """Fetch if the cache is expired. One upstream request per feed at a time (lock), so concurrent API calls
        wait for the in-flight fetch instead of stampeding the upstream."""
        if feeds_disabled() or self.missing_credentials():
            return
        with self._lock:
            now = time.time()
            if not force and (self._fresh(now) or self._backing_off(now)):
                return
            started = time.perf_counter()
            try:
                data = self.fetch(self.client())
            except Exception as exc:  # noqa: BLE001 - never raise to the API layer
                self._last_error = describe(exc)
                self._last_error_at = time.time()
                self._failing = True
                self._latency_ms = round((time.perf_counter() - started) * 1000, 1)
                return
            self._latency_ms = round((time.perf_counter() - started) * 1000, 1)
            partial = list(data.pop("_partial", []) or [])
            self._data = data
            self._fetched_at = self._last_ok = time.time()
            self._partial_errors = partial
            self._failing = False
            self._last_error = "; ".join(partial)[:500] if partial else None
            self._last_error_at = self._fetched_at if partial else None
            try:
                self.on_success(data)
            except Exception:  # noqa: BLE001 - history is best effort
                pass

    def _status_value(self) -> tuple[str, bool, str]:
        if feeds_disabled():
            return "blocked", False, "disabled by configuration (TROSSOPS_FEEDS=off)"
        missing = self.missing_credentials()
        if missing:
            return "adapter-only", False, f"requires {', '.join(missing)}. {self.credential_help}".strip()
        if self._data is None:
            if self._last_error:
                return "blocked", False, f"upstream error, no data yet: {self._last_error}"
            return "adapter-only", False, "adapter ready; not fetched yet in this process"
        if self._failing:
            return "partial", True, f"serving last good data from {iso(self._fetched_at)}; latest error: {self._last_error}"
        if time.time() - (self._fetched_at or 0) > max(self.ttl_s * 3, 1.0):
            return "partial", True, f"cached data from {iso(self._fetched_at)} has not been refreshed (older than 3x TTL)"
        if self._partial_errors:
            return "partial", False, f"some sub-requests failed: {'; '.join(self._partial_errors)[:300]}"
        return "working", False, self.note

    def status(self) -> dict:
        status, stale, note = self._status_value()
        return {"id": self.id, "label": self.label, "category": self.category, "status": status,
                "lastOkAt": iso(self._last_ok), "lastError": self._last_error,
                "count": self.count_of(self._data) if self._data is not None else 0,
                "licence": self.licence, "attribution": self.attribution, "url": self.url, "note": note or self.note,
                "stale": stale, "ttlS": self.ttl_s, "latencyMs": self._latency_ms}

    def get(self) -> dict:
        """Normalised payload. Never raises."""
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            self._last_error = describe(exc)
        st = self.status()
        body = dict(self._data) if self._data is not None else self.empty()
        body.update({"id": self.id, "status": st["status"], "source": self.label, "licence": self.licence,
                     "attribution": self.attribution, "url": self.url, "fetchedAt": iso(self._fetched_at),
                     "stale": st["stale"], "note": st["note"], "lastError": st["lastError"], "count": st["count"],
                     "generatedAt": iso(time.time()), "ttlS": self.ttl_s})
        return body
