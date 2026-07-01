"""FastAPI application root.

Wires the routers, CORS, rate limiting, structured logging, and a lifespan that
initializes the DB + seeds a demo clinician when running on SQLite (dev/demo).
Production (Postgres) is managed by Alembic migrations + an explicit seed step,
so the lifespan skips table creation there. Engine providers (deps.py) are
overridable for tests.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from clin_doc.auth import seed_user
from clin_doc.db.session import get_engine, init_db
from clin_doc.rate_limit import maybe_add_rate_limit
from clin_doc.routers import api_router
from clin_doc.settings import assert_production_secrets, cors_origin_list, get_settings

log = logging.getLogger("clin_doc")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    # Phase 6 secrets hygiene: refuse to boot a production DB with the default
    # JWT secret (the demo opts out via ALLOW_INSECURE_SECRETS).
    assert_production_secrets()
    # Dev/demo on SQLite: create tables + seed the demo clinician. Prod
    # (Postgres) uses `alembic upgrade head` + an explicit seed instead.
    if s.database_url.startswith("sqlite"):
        init_db()
        with Session(get_engine()) as session:
            seed_user(session)
    log.info(
        "clin_doc started | db=%s | asr=%s | synthetic_data_only=%s",
        _mask_db(s.database_url),
        s.asr_backend,
        s.synthetic_data_only,
    )
    yield
    log.info("clin_doc stopping")


def _mask_db(url: str) -> str:
    """Hide credentials in the startup log line."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        return f"{scheme}://***@{host}"
    return url


def create_app() -> FastAPI:
    s = get_settings()
    # Structured-ish logging: one line per event with level + logger name.
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [%(name)s] %(message)s",
    )
    app = FastAPI(title="Clinical Documentation Assistant", version="0.1.0", lifespan=lifespan)

    # CORS (Phase 6): explicit origin allowlist instead of "*"+credentials.
    origins = cors_origin_list()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Rate limiting (Phase 5) — no-op unless RATE_LIMIT_ENABLED=true.
    maybe_add_rate_limit(app)
    app.include_router(api_router())

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, object]:
        return {"status": "ok", "synthetic_data_only": s.synthetic_data_only}

    return app


app = create_app()
