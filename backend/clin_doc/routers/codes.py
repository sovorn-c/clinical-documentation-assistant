"""Code-suggestion endpoints (S3, behind the de-id boundary)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from clin_doc.auth import get_current_user
from clin_doc.db.repositories import CodeRepo
from clin_doc.db.session import DbSession
from clin_doc.deps import PipelineDep
from clin_doc.schemas import ApproveRequest, CodeSuggestionOut

router = APIRouter(prefix="/encounters", tags=["codes"], dependencies=[Depends(get_current_user)])


@router.post("/{encounter_id}/suggest-codes", response_model=list[CodeSuggestionOut])
def suggest_codes(encounter_id: str, svc: PipelineDep) -> list[dict[str, Any]]:
    try:
        return svc.suggest_codes(encounter_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"coding unavailable: {e}") from e


@router.get("/{encounter_id}/codes", response_model=list[CodeSuggestionOut])
def list_codes(encounter_id: str, session: DbSession) -> list[dict[str, Any]]:
    return [r.model_dump() for r in CodeRepo(session).get_by_encounter(encounter_id)]


@router.post("/{encounter_id}/approve-codes", status_code=204)
def approve_codes(encounter_id: str, body: ApproveRequest, svc: PipelineDep) -> None:
    try:
        svc.approve_codes(encounter_id, body.approver_name, body.approver_role)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
