"""FastAPI application root.

Wires the routers, CORS, and a lifespan that initializes the DB + seeds a demo
clinician when running on SQLite (dev/demo). Production (Postgres) is managed
by Alembic migrations + an explicit seed step, so the lifespan skips table
creation there. Engine providers (deps.py) are overridable for tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from clin_doc.auth import seed_user
from clin_doc.db.session import get_engine, init_db
from clin_doc.routers import api_router
from clin_doc.settings import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    # Dev/demo on SQLite: create tables + seed the demo clinician. Prod
    # (Postgres) uses `alembic upgrade head` + an explicit seed instead.
    if s.database_url.startswith("sqlite"):
        init_db()
        with Session(get_engine()) as session:
            seed_user(session)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Clinical Documentation Assistant", version="0.1.0", lifespan=lifespan)

    # Tighten allow_origins in Phase 6; permissive for the local demo only.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router())

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, object]:
        return {"status": "ok", "synthetic_data_only": s.synthetic_data_only}

    return app


app = create_app()
