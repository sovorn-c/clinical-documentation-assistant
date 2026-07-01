"""Patient endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from clin_doc.auth import get_current_user
from clin_doc.db.models import Patient
from clin_doc.db.session import DbSession
from clin_doc.deps import PipelineDep
from clin_doc.schemas import PatientCreate, PatientOut

router = APIRouter(prefix="/patients", tags=["patients"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[PatientOut])
def list_patients(session: DbSession) -> list[Patient]:
    return list(session.exec(select(Patient)).all())


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(body: PatientCreate, svc: PipelineDep) -> Patient:
    return svc.create_patient(
        patient_ref=body.patient_ref,
        display_name=body.display_name,
        fhir_bundle_path=body.fhir_bundle_path,
    )


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: str, session: DbSession) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="patient not found")
    return patient
