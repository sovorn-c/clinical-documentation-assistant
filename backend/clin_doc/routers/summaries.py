"""Summary endpoints (S1 summarizer)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from clin_doc.auth import get_current_user
from clin_doc.deps import PipelineDep

router = APIRouter(prefix="/patients", tags=["summaries"], dependencies=[Depends(get_current_user)])


@router.post("/{patient_id}/summarize")
def summarize(patient_id: str, svc: PipelineDep) -> dict[str, Any]:
    try:
        return svc.summarize_patient(patient_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"summarize unavailable: {e}") from e
