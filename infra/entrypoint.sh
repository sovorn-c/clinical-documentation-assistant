#!/bin/sh
# Backend container entrypoint (Phase 5).
# 1. Run Alembic migrations (Postgres). For SQLite dev the app lifespan creates
#    tables, so a failed migration is non-fatal.
# 2. Seed the demo clinician + synthetic demo patient (idempotent).
# 3. Start uvicorn.
set -e

echo "[entrypoint] running alembic migrations (if Postgres)..."
uv run alembic upgrade head || echo "[entrypoint] alembic skipped (likely sqlite dev)"

echo "[entrypoint] seeding synthetic demo data..."
uv run python -m clin_doc.seed

echo "[entrypoint] starting uvicorn..."
exec uv run uvicorn clin_doc.main:app --host 0.0.0.0 --port 8000 --proxy-headers
