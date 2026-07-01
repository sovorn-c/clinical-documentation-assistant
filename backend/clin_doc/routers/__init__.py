"""API routers (Phase 2). Each is a thin wrapper over PipelineService."""

from __future__ import annotations

from fastapi import APIRouter

from clin_doc.routers import auth, codes, encounters, exports, patients, referrals, summaries


def api_router() -> APIRouter:
    router = APIRouter(prefix="/api")
    for r in (
        auth.router,
        patients.router,
        encounters.router,
        codes.router,
        referrals.router,
        summaries.router,
        exports.router,
    ):
        router.include_router(r)
    return router
