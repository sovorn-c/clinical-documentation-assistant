"""Status + audit vocabulary for the data layer.

Enums are stored as their string values in the DB so the schema is portable
(SQLite tests + Postgres prod) and human-readable in queries.
"""

from __future__ import annotations

from enum import StrEnum


class EncounterStatus(StrEnum):
    AUDIO_UPLOADED = "audio_uploaded"
    NOTE_DRAFTED = "note_drafted"
    NOTE_EDITED = "note_edited"
    CODES_SUGGESTED = "codes_suggested"
    REFERRAL_GENERATED = "referral_generated"
    APPROVED = "approved"
    EXPORTED = "exported"


class NoteSource(StrEnum):
    AI = "ai"
    HUMAN = "human"


class ArtifactType(StrEnum):
    ENCOUNTER = "encounter"
    TRANSCRIPT = "transcript"
    NOTE = "note"
    CODES = "codes"
    REFERRAL = "referral"
    APPROVAL = "approval"
    FHIR_EXPORT = "fhir_export"
    DEID = "deid"


class AuditActor(StrEnum):
    SYSTEM = "system"
    USER = "user"


class AuditAction(StrEnum):
    UPLOAD_AUDIO = "upload_audio"
    GENERATE_NOTE = "generate_note"
    EDIT_NOTE = "edit_note"
    DEIDENTIFY = "deidentify"
    SUGGEST_CODES = "suggest_codes"
    GENERATE_REFERRAL = "generate_referral"
    APPROVE_NOTE = "approve_note"
    APPROVE_CODES = "approve_codes"
    APPROVE_REFERRAL = "approve_referral"
    FHIR_EXPORT = "fhir_export"
    SUMMARIZE = "summarize"
    CREATE_PATIENT = "create_patient"
