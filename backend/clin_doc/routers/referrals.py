"""Referral endpoints (§8.3, behind the de-id boundary)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from clin_doc.auth import get_current_user
from clin_doc.db.repositories import ReferralRepo
from clin_doc.db.session import DbSession
from clin_doc.deps import PipelineDep
from clin_doc.schemas import ApproveRequest, ReferralOut

router = APIRouter(
    prefix="/encounters", tags=["referrals"], dependencies=[Depends(get_current_user)]
)


@router.post("/{encounter_id}/generate-referral", response_model=ReferralOut)
def generate_referral(encounter_id: str, svc: PipelineDep, session: DbSession) -> dict[str, Any]:
    try:
        svc.generate_referral(encounter_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"referral generation unavailable: {e}") from e
    ref = ReferralRepo(session).get_by_encounter(encounter_id)
    assert ref is not None
    return ref.model_dump()


@router.get("/{encounter_id}/referral", response_model=ReferralOut)
def get_referral(encounter_id: str, session: DbSession) -> dict[str, Any]:
    ref = ReferralRepo(session).get_by_encounter(encounter_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="no referral for encounter")
    return ref.model_dump()


@router.post("/{encounter_id}/approve-referral", status_code=204)
def approve_referral(encounter_id: str, body: ApproveRequest, svc: PipelineDep) -> None:
    try:
        svc.approve_referral(encounter_id, body.approver_name, body.approver_role)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
