"""HTTP-level caching helpers for the API: pre-serialised, pre-compressed JSON with validators, and memoisation of
payloads derived from one engine evaluation.

- `Encoded` holds the JSON bytes of an immutable payload, its gzip encoding (computed once, in the request thread
  rather than the event loop) and a weak ETag over the content. `respond()` answers `If-None-Match` with 304 and picks
  the encoding from `Accept-Encoding`; the GZip middleware passes responses that already carry `Content-Encoding`.
- `PerEvaluation` memoises payloads (snapshot per role, attention per resolution) for as long as `engine.evaluate`
  keeps returning the same `Evaluation` object, so the cache can never outlive the engine's own.
"""
from __future__ import annotations

import gzip
import hashlib
import threading
from typing import Any, Callable

from fastapi import Request, Response
from pydantic import TypeAdapter

_json = TypeAdapter(Any)
GZIP_LEVEL = 6  # level 9 costs ~5x the CPU for ~1 % smaller bodies


def dump_json(obj: Any) -> bytes:
    """Same bytes FastAPI's default JSON response produces for a plain dict (pydantic-core serialiser)."""
    return _json.dump_json(obj)


class Encoded:
    __slots__ = ("raw", "etag", "_gz", "_lock")

    def __init__(self, obj: Any) -> None:
        self.raw = dump_json(obj)
        self.etag = 'W/"' + hashlib.blake2b(self.raw, digest_size=12).hexdigest() + '"'
        self._gz: bytes | None = None
        self._lock = threading.Lock()

    def gz(self) -> bytes:
        if self._gz is None:
            with self._lock:
                if self._gz is None:
                    self._gz = gzip.compress(self.raw, GZIP_LEVEL, mtime=0)
        return self._gz


def etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    if header.strip() == "*":
        return True
    bare = etag.removeprefix("W/")
    return any(tag.strip().removeprefix("W/") == bare for tag in header.split(","))


def respond(request: Request, enc: Encoded, cache_control: str = "no-cache") -> Response:
    headers = {"ETag": enc.etag, "Cache-Control": cache_control, "Vary": "Accept-Encoding"}
    if etag_matches(request.headers.get("if-none-match"), enc.etag):
        return Response(status_code=304, headers=headers)
    accept = request.headers.get("accept-encoding", "")
    if "gzip" in accept and len(enc.raw) >= 1024:
        return Response(enc.gz(), media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(enc.raw, media_type="application/json", headers=headers)


class Memo:
    """Encoded payload keyed on the identity of a source object (e.g. the engine's cached catalog dict)."""

    def __init__(self) -> None:
        self._src: Any = None
        self._enc: Encoded | None = None
        self._lock = threading.Lock()

    def get(self, src: Any, build: Callable[[], Any] | None = None) -> Encoded:
        with self._lock:
            if self._src is src and self._enc is not None:
                return self._enc
        enc = Encoded(build() if build else src)
        with self._lock:
            self._src, self._enc = src, enc
        return enc


class PerEvaluation:
    """Payloads derived from one Evaluation object; dropped as soon as the engine hands out a different one."""

    def __init__(self) -> None:
        self._ev: Any = None
        self._items: dict[tuple, Any] = {}
        self._lock = threading.Lock()

    def get(self, ev: Any, key: tuple, build: Callable[[], Any]) -> Any:
        with self._lock:
            if self._ev is not ev:
                self._ev, self._items = ev, {}
            hit = self._items.get(key)
        if hit is not None:
            return hit
        value = build()
        with self._lock:
            if self._ev is ev:
                self._items[key] = value
        return value
