"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PatientCreate(BaseModel):
    patient_ref: str
    display_name: str | None = None
    fhir_bundle_path: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_ref: str
    display_name: str | None
    fhir_bundle_path: str | None


class EncounterCreate(BaseModel):
    patient_id: str
    encounter_ref: str
    audio_path: str | None = None


class EncounterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    encounter_ref: str
    status: str
    audio_path: str | None
    created_at: datetime


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    encounter_id: str
    version: int
    source: str
    note: dict[str, Any]
    provenance: dict[str, Any] | None
    draft_id: str | None
    created_at: datetime


class NoteEdit(BaseModel):
    note: dict[str, Any]  # SOAPNote model_dump


class CodeSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    description: str | None
    confidence: float
    rank: int
    evidence: dict[str, Any]
    approved: bool


class ReferralOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    encounter_id: str
    letter_text: str
    model: str | None
    approved: bool
    created_at: datetime


class ApproveRequest(BaseModel):
    approver_name: str
    approver_role: str = "clinician"


class FhirExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    resource_type: str
    fhir_version: str
    resource: dict[str, Any]
    json_text: str
    created_at: datetime


class SummaryOut(BaseModel):
    patient_id: str
    one_liner: str
    sections: list[Any]
    model: str
    generated_at: datetime
    faithfulness: dict[str, Any] | None = None


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    encounter_id: str | None
    actor: str
    actor_name: str | None
    action: str
    artifact_type: str | None
    artifact_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    meta: dict[str, Any] | None
    created_at: datetime
