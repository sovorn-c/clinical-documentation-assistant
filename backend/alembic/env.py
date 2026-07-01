"""Alembic environment.

Target metadata is the SQLModel metadata (populated by importing the table
models), so ``alembic revision --autogenerate`` diffs against the real schema.
The database URL comes from ``clin_doc.settings`` (DATABASE_URL), overridable
via the standard ``-x url=...`` or the ``sqlalchemy.url`` ini key.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

# Importing the models registers every table on SQLModel.metadata.
from clin_doc.db import models  # noqa: F401
from clin_doc.settings import get_settings
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the URL: ini override > env > settings default.
ini_url = config.get_main_option("sqlalchemy.url")
config.set_main_option(
    "sqlalchemy.url",
    ini_url or os.getenv("DATABASE_URL") or get_settings().database_url,
)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=url_is_sqlite(config.get_main_option("sqlalchemy.url")),
        )
        with context.begin_transaction():
            context.run_migrations()


def url_is_sqlite(url: str | None) -> bool:
    return bool(url and url.startswith("sqlite"))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
