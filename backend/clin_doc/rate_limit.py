"""Basic in-process rate limiting (Phase 5).

A dep-free sliding-window limiter keyed by client IP, sufficient for the
single-instance demo. For a multi-worker/multi-instance deployment, swap this
for a shared store (Redis) — the ``RateLimiter`` interface stays the same.

Disabled by default (``rate_limit_enabled=False``); the demo env enables it via
``RATE_LIMIT_ENABLED=true``. Authenticated clinicians share the global budget,
which keeps the public demo stable without blocking a signed-in reviewer.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from clin_doc.settings import get_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-IP limiter. Returns 429 with Retry-After when exceeded."""

    def __init__(self, app: ASGIApp, per_minute: int) -> None:
        super().__init__(app)
        self.window = 60.0
        self.limit = per_minute
        self._hits: dict[str, deque[float]] = {}

    def _client(self, request: Request) -> str:
        # Trust X-Forwarded-For from the demo's reverse proxy; fall back to the
        # direct client.
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in ("/health",) or request.url.path.startswith("/api/auth/"):
            return await call_next(request)
        now = time.monotonic()
        ip = self._client(request)
        bucket = self._hits.setdefault(ip, deque())
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry = max(1, int(self.window - (now - bucket[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
                headers={"Retry-After": str(retry)},
            )
        bucket.append(now)
        return await call_next(request)


def maybe_add_rate_limit(app: ASGIApp) -> None:
    """Add the limiter middleware if ``rate_limit_enabled`` is set in settings."""
    s = get_settings()
    if s.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware, per_minute=s.rate_limit_per_minute)  # type: ignore[arg-type]
