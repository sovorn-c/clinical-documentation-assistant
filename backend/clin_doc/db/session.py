"""Engine + session factory.

Repos take a ``Session`` so tests can drive them against an in-memory SQLite
engine; production uses the FastAPI ``get_session`` dependency over Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from clin_doc.settings import get_settings

_engine: Engine | None = None


def get_engine(database_url: str | None = None) -> Engine:
    global _engine
    if _engine is None or database_url is not None:
        url = database_url or get_settings().database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        engine = create_engine(url, connect_args=connect_args)
        if database_url is None:
            _engine = engine
        return engine
    return _engine


def init_db(engine: Engine | None = None) -> None:
    """Create all tables on ``engine`` (or the default engine)."""
    from clin_doc.db import models  # noqa: F401 — register tables on metadata

    SQLModel.metadata.create_all(engine or get_engine())


def reset_engine_cache() -> None:
    """Drop the cached engine (tests use per-test engines)."""
    global _engine
    _engine = None


def get_session() -> Iterator[Session]:
    # expire_on_commit=False so post-commit reads (e.g. service-level
    # model_dump for response payloads) don't hit expired/empty attributes.
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session


DbSession = Annotated[Session, Depends(get_session)]
