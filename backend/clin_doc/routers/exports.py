"""Approval-gate + FHIR-export + audit endpoints.

``export_fhir`` is gated: it 409s unless the note (and codes/referral, if
present) have approval records. Phase 4 adds the net-new Condition/Claim
resources alongside M1's R5 DocumentReference.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from clin_doc.auth import get_current_user
from clin_doc.db.repositories import FhirExportRepo
from clin_doc.db.session import DbSession
from clin_doc.deps import PipelineDep
from clin_doc.schemas import ApproveRequest, AuditOut, FhirExportOut

router = APIRouter(prefix="/encounters", tags=["exports"], dependencies=[Depends(get_current_user)])


@router.post("/{encounter_id}/approve-note", status_code=200)
def approve_note(encounter_id: str, body: ApproveRequest, svc: PipelineDep) -> dict[str, Any]:
    try:
        note_id = svc.approve_note(encounter_id, body.approver_name, body.approver_role)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"note_id": note_id, "approved": True}


@router.post("/{encounter_id}/export-fhir", response_model=list[FhirExportOut])
def export_fhir(encounter_id: str, svc: PipelineDep, session: DbSession) -> list[dict[str, Any]]:
    try:
        svc.export_fhir(encounter_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"fhir export unavailable: {e}") from e
    return [r.model_dump() for r in FhirExportRepo(session).get_by_encounter(encounter_id)]


@router.get("/{encounter_id}/exports", response_model=list[FhirExportOut])
def list_exports(encounter_id: str, session: DbSession) -> list[dict[str, Any]]:
    return [r.model_dump() for r in FhirExportRepo(session).get_by_encounter(encounter_id)]


@router.get("/{encounter_id}/audit", response_model=list[AuditOut])
def list_audit(encounter_id: str, svc: PipelineDep) -> list[dict[str, Any]]:
    return svc.list_audit(encounter_id)
