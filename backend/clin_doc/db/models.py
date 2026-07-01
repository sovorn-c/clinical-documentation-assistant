"""SQLModel table models — shaped to the upstream return types (§7).

Design: complex nested upstream Pydantic types (SOAPNote, Dialogue utterances,
Provenance, DeidResult spans/audit, CodeSuggestion evidence, Summary, FHIR
resources) are stored as JSON columns via ``model_dump(mode="json")`` so they
round-trip losslessly (``Model.model_validate(dict)`` recovers them). Key
scalars are denormalized into real columns for indexing/queryability.

Tables (execute-plan §9 Phase 1): patients, encounters, transcripts, notes,
code_suggestions, referrals, approvals, fhir_exports, audit_log.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    """A clinician who can authenticate and approve artifacts."""

    __tablename__ = "users"

    id: str = Field(primary_key=True, default_factory=_uuid)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    display_name: str | None = None
    role: str = Field(default="clinician")  # clinician | admin
    created_at: datetime = Field(default_factory=_now)


class Patient(SQLModel, table=True):
    """Reference to a FHIR Patient (context loaded via S1 ``load_bundle``)."""

    __tablename__ = "patients"

    id: str = Field(primary_key=True, default_factory=_uuid)
    patient_ref: str = Field(index=True, unique=True)  # FHIR Patient id
    display_name: str | None = None
    fhir_bundle_path: str | None = None  # for reloading context
    created_at: datetime = Field(default_factory=_now)


class Encounter(SQLModel, table=True):
    """One consultation: audio → … → FHIR export."""

    __tablename__ = "encounters"

    id: str = Field(primary_key=True, default_factory=_uuid)
    patient_id: str = Field(foreign_key="patients.id", index=True)
    encounter_ref: str  # FHIR Encounter id
    status: str = Field(default="audio_uploaded", index=True)
    audio_path: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Transcript(SQLModel, table=True):
    """M1 ``Dialogue`` (utterances) + a flattened rendering for display/de-id."""

    __tablename__ = "transcripts"

    id: str = Field(primary_key=True, default_factory=_uuid)
    encounter_id: str = Field(foreign_key="encounters.id", index=True)
    utterances: list[dict] = Field(sa_column=Column(JSON, nullable=False))
    transcript_text: str | None = Field(sa_column=Column(Text))
    asr_id: str | None = None
    diarizer_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Note(SQLModel, table=True):
    """A SOAP note version. AI draft (source=ai, v1) + human edits (source=human)."""

    __tablename__ = "notes"

    id: str = Field(primary_key=True, default_factory=_uuid)
    encounter_id: str = Field(foreign_key="encounters.id", index=True)
    version: int = 1
    source: str = Field(default="ai", index=True)  # NoteSource
    note: dict = Field(sa_column=Column(JSON, nullable=False))  # SOAPNote
    provenance: dict | None = Field(sa_column=Column(JSON))  # M1 Provenance
    draft_id: str | None = None  # M1 Draft.id for the AI draft
    created_at: datetime = Field(default_factory=_now)


class CodeSuggestionRow(SQLModel, table=True):
    """One S3 ``CodeSuggestion`` (relational for queryability)."""

    __tablename__ = "code_suggestions"

    id: str = Field(primary_key=True, default_factory=_uuid)
    encounter_id: str = Field(foreign_key="encounters.id", index=True)
    note_id: str | None = Field(foreign_key="notes.id", index=True)
    code: str = Field(index=True)
    description: str | None = None
    confidence: float = 0.0
    rank: int = 1
    evidence: dict = Field(sa_column=Column(JSON, nullable=False))  # EvidenceSpan
    approved: bool = False
    created_at: datetime = Field(default_factory=_now)


class Referral(SQLModel, table=True):
    """Generated referral letter (§8.3, net-new LLM call)."""

    __tablename__ = "referrals"

    id: str = Field(primary_key=True, default_factory=_uuid)
    encounter_id: str = Field(foreign_key="encounters.id", index=True)
    note_id: str | None = Field(foreign_key="notes.id", index=True)
    letter_text: str = Field(sa_column=Column(Text, nullable=False))
    model: str | None = None
    approved: bool = False
    created_at: datetime = Field(default_factory=_now)


class Approval(SQLModel, table=True):
    """An explicit approval-gate record (note/codes/referral/export)."""

    __tablename__ = "approvals"

    id: str = Field(primary_key=True, default_factory=_uuid)
    encounter_id: str = Field(foreign_key="encounters.id", index=True)
    approver_name: str
    approver_role: str = "clinician"
    artifact_type: str  # ArtifactType
    artifact_id: str
    approved_at: datetime = Field(default_factory=_now)


class FhirExport(SQLModel, table=True):
    """An exported FHIR resource (M1 R5 DocumentReference; R4 Condition/Claim)."""

    __tablename__ = "fhir_exports"

    id: str = Field(primary_key=True, default_factory=_uuid)
    encounter_id: str = Field(foreign_key="encounters.id", index=True)
    resource_type: str  # DocumentReference | Condition | Claim
    fhir_version: str  # R4 | R5
    resource: dict = Field(sa_column=Column(JSON, nullable=False))
    json_text: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=_now)


class AuditLog(SQLModel, table=True):
    """Append-only audit trail. Every state change writes exactly one row.

    ``before``/``after`` hold the artifact state (JSON) so Phase 3 can diff
    AI output vs human edits. ``meta`` carries action-specific detail, e.g.
    S2 de-id counts (``DeidResult.audit``) or LLM token usage + model ids.
    """

    __tablename__ = "audit_log"

    id: str = Field(primary_key=True, default_factory=_uuid)
    encounter_id: str | None = Field(default=None, index=True)
    actor: str  # AuditActor
    actor_name: str | None = None
    action: str  # AuditAction
    artifact_type: str | None = None
    artifact_id: str | None = None
    before: dict | None = Field(default=None, sa_column=Column(JSON))
    after: dict | None = Field(default=None, sa_column=Column(JSON))
    meta: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)
