"""FastAPI application root (Phase 0 skeleton).

The pipeline endpoints land in Phase 2; for now a health check makes the
scaffold runnable and proves the full import graph (FastAPI + the four
upstream engines via path deps) resolves cleanly.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Clinical Documentation Assistant", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
