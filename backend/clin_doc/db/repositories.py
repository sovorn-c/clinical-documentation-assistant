"""Repositories over the Phase 1 schema.

Each write performs its DB op and appends one ``AuditLog`` row in the same
session, so every state change is audited by construction. Read methods are
audit-free. Repositories take a ``Session`` so they're testable against any
engine (in-memory SQLite in tests, Postgres in prod).
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from sqlmodel import Session, select

from clin_doc.db.audit import AuditMeta, write_audit
from clin_doc.db.enums import (
    ArtifactType,
    EncounterStatus,
    NoteSource,
)
from clin_doc.db.models import (
    Approval,
    AuditLog,
    CodeSuggestionRow,
    Encounter,
    FhirExport,
    Note,
    Patient,
    Referral,
    Transcript,
)


def _row_dict(row: Any) -> dict[str, Any]:
    """Serializable view of a row for audit before/after.

    ``mode="json"`` turns datetimes into ISO strings so the audit JSON columns
    accept it (SQLAlchemy's JSON type uses ``json.dumps``).
    """
    return row.model_dump(mode="json")


class PatientRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def upsert(
        self,
        *,
        patient_ref: str,
        display_name: str | None = None,
        fhir_bundle_path: str | None = None,
        audit: AuditMeta,
    ) -> Patient:
        existing = self.s.exec(
            select(Patient).where(Patient.patient_ref == patient_ref)
        ).first()
        if existing is not None:
            return existing
        patient = Patient(
            patient_ref=patient_ref,
            display_name=display_name,
            fhir_bundle_path=fhir_bundle_path,
        )
        self.s.add(patient)
        self.s.flush()
        write_audit(
            self.s,
            None,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.ENCOUNTER,
                    "artifact_id": patient.id,
                    "after": _row_dict(patient),
                }
            ),
        )
        return patient

    def get(self, patient_id: str) -> Patient | None:
        return self.s.get(Patient, patient_id)

    def get_by_ref(self, patient_ref: str) -> Patient | None:
        return self.s.exec(select(Patient).where(Patient.patient_ref == patient_ref)).first()

    def list_all(self) -> list[Patient]:
        return list(self.s.exec(select(Patient)).all())


class EncounterRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create(
        self,
        *,
        patient_id: str,
        encounter_ref: str,
        audio_path: str | None = None,
        audit: AuditMeta,
    ) -> Encounter:
        enc = Encounter(
            patient_id=patient_id,
            encounter_ref=encounter_ref,
            status=EncounterStatus.AUDIO_UPLOADED.value,
            audio_path=audio_path,
        )
        self.s.add(enc)
        self.s.flush()
        write_audit(
            self.s,
            enc.id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.ENCOUNTER,
                    "artifact_id": enc.id,
                    "after": _row_dict(enc),
                }
            ),
        )
        return enc

    def get(self, encounter_id: str) -> Encounter | None:
        return self.s.get(Encounter, encounter_id)

    def list_by_patient(self, patient_id: str) -> list[Encounter]:
        return list(
            self.s.exec(
                select(Encounter).where(Encounter.patient_id == patient_id)
            ).all()
        )

    def update_status(
        self, encounter_id: str, status: EncounterStatus, audit: AuditMeta
    ) -> Encounter:
        enc = self.s.get(Encounter, encounter_id)
        if enc is None:
            raise KeyError(f"no encounter {encounter_id}")
        before = {"status": enc.status}
        enc.status = status.value
        from datetime import datetime

        enc.updated_at = datetime.now(UTC)
        self.s.add(enc)
        self.s.flush()
        write_audit(
            self.s,
            enc.id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.ENCOUNTER,
                    "artifact_id": enc.id,
                    "before": before,
                    "after": {"status": enc.status},
                }
            ),
        )
        return enc


class TranscriptRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def save(
        self,
        *,
        encounter_id: str,
        utterances: list[dict[str, Any]],
        transcript_text: str | None,
        asr_id: str | None = None,
        diarizer_id: str | None = None,
        audit: AuditMeta,
    ) -> Transcript:
        t = Transcript(
            encounter_id=encounter_id,
            utterances=utterances,
            transcript_text=transcript_text,
            asr_id=asr_id,
            diarizer_id=diarizer_id,
        )
        self.s.add(t)
        self.s.flush()
        write_audit(
            self.s,
            encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.TRANSCRIPT,
                    "artifact_id": t.id,
                    "after": _row_dict(t),
                }
            ),
        )
        return t

    def get_by_encounter(self, encounter_id: str) -> Transcript | None:
        return self.s.exec(
            select(Transcript).where(Transcript.encounter_id == encounter_id)
        ).first()


class NoteRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create_draft(
        self,
        *,
        encounter_id: str,
        note: dict[str, Any],
        provenance: dict[str, Any] | None = None,
        draft_id: str | None = None,
        audit: AuditMeta,
    ) -> Note:
        latest = self._latest_version(encounter_id)
        n = Note(
            encounter_id=encounter_id,
            version=latest + 1,
            source=NoteSource.AI.value,
            note=note,
            provenance=provenance,
            draft_id=draft_id,
        )
        self.s.add(n)
        self.s.flush()
        write_audit(
            self.s,
            encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.NOTE,
                    "artifact_id": n.id,
                    "after": _row_dict(n),
                }
            ),
        )
        return n

    def save_edit(
        self,
        *,
        encounter_id: str,
        note: dict[str, Any],
        audit: AuditMeta,
    ) -> Note:
        prev = self._latest(encounter_id)
        before = _row_dict(prev) if prev else None
        n = Note(
            encounter_id=encounter_id,
            version=(prev.version + 1) if prev else 1,
            source=NoteSource.HUMAN.value,
            note=note,
        )
        self.s.add(n)
        self.s.flush()
        write_audit(
            self.s,
            encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.NOTE,
                    "artifact_id": n.id,
                    "before": before,
                    "after": _row_dict(n),
                }
            ),
        )
        return n

    def get(self, note_id: str) -> Note | None:
        return self.s.get(Note, note_id)

    def get_versions(self, encounter_id: str) -> list[Note]:
        return list(
            self.s.exec(
                select(Note).where(Note.encounter_id == encounter_id).order_by(Note.version)
            ).all()
        )

    def get_latest(self, encounter_id: str) -> Note | None:
        return self._latest(encounter_id)

    def _latest(self, encounter_id: str) -> Note | None:
        rows = self.get_versions(encounter_id)
        return rows[-1] if rows else None

    def _latest_version(self, encounter_id: str) -> int:
        latest = self._latest(encounter_id)
        return latest.version if latest else 0


class CodeRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def save_suggestions(
        self,
        *,
        encounter_id: str,
        note_id: str | None,
        suggestions: list[dict[str, Any]],
        audit: AuditMeta,
    ) -> list[CodeSuggestionRow]:
        """Replace the encounter's suggestions (one row per CodeSuggestion)."""
        old = list(
            self.s.exec(
                select(CodeSuggestionRow).where(
                    CodeSuggestionRow.encounter_id == encounter_id
                )
            ).all()
        )
        before = [_row_dict(r) for r in old]
        for r in old:
            self.s.delete(r)
        self.s.flush()

        rows: list[CodeSuggestionRow] = []
        for sg in suggestions:
            ev = sg.get("evidence") or {}
            row = CodeSuggestionRow(
                encounter_id=encounter_id,
                note_id=note_id,
                code=sg.get("code", ""),
                description=sg.get("description"),
                confidence=float(sg.get("confidence", 0.0)),
                rank=int(sg.get("rank", 1)),
                evidence=ev,
                approved=False,
            )
            self.s.add(row)
            rows.append(row)
        self.s.flush()
        write_audit(
            self.s,
            encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.CODES,
                    "artifact_id": encounter_id,
                    "before": {"suggestions": before},
                    "after": {"suggestions": [_row_dict(r) for r in rows]},
                }
            ),
        )
        return rows

    def get_by_encounter(self, encounter_id: str) -> list[CodeSuggestionRow]:
        return list(
            self.s.exec(
                select(CodeSuggestionRow)
                .where(CodeSuggestionRow.encounter_id == encounter_id)
                .order_by(CodeSuggestionRow.rank)
            ).all()
        )

    def set_approved(
        self, suggestion_id: str, approved: bool, audit: AuditMeta
    ) -> CodeSuggestionRow:
        row = self.s.get(CodeSuggestionRow, suggestion_id)
        if row is None:
            raise KeyError(f"no code suggestion {suggestion_id}")
        before = {"approved": row.approved}
        row.approved = approved
        self.s.add(row)
        self.s.flush()
        write_audit(
            self.s,
            row.encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.CODES,
                    "artifact_id": row.id,
                    "before": before,
                    "after": {"approved": row.approved},
                }
            ),
        )
        return row


class ReferralRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def save(
        self,
        *,
        encounter_id: str,
        note_id: str | None,
        letter_text: str,
        model: str | None = None,
        audit: AuditMeta,
    ) -> Referral:
        prev = self.s.exec(
            select(Referral).where(Referral.encounter_id == encounter_id)
        ).first()
        before = _row_dict(prev) if prev else None
        r = Referral(
            encounter_id=encounter_id,
            note_id=note_id,
            letter_text=letter_text,
            model=model,
        )
        self.s.add(r)
        self.s.flush()
        write_audit(
            self.s,
            encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.REFERRAL,
                    "artifact_id": r.id,
                    "before": before,
                    "after": _row_dict(r),
                }
            ),
        )
        return r

    def get_by_encounter(self, encounter_id: str) -> Referral | None:
        return self.s.exec(
            select(Referral).where(Referral.encounter_id == encounter_id)
        ).first()

    def set_approved(
        self, referral_id: str, approved: bool, audit: AuditMeta
    ) -> Referral:
        r = self.s.get(Referral, referral_id)
        if r is None:
            raise KeyError(f"no referral {referral_id}")
        before = {"approved": r.approved}
        r.approved = approved
        self.s.add(r)
        self.s.flush()
        write_audit(
            self.s,
            r.encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.REFERRAL,
                    "before": before,
                    "after": {"approved": r.approved},
                    "artifact_id": r.id,
                }
            ),
        )
        return r


class ApprovalRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def record(
        self,
        *,
        encounter_id: str,
        approver_name: str,
        approver_role: str,
        artifact_type: ArtifactType,
        artifact_id: str,
        audit: AuditMeta,
    ) -> Approval:
        ap = Approval(
            encounter_id=encounter_id,
            approver_name=approver_name,
            approver_role=approver_role,
            artifact_type=artifact_type.value,
            artifact_id=artifact_id,
        )
        self.s.add(ap)
        self.s.flush()
        write_audit(
            self.s,
            encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.APPROVAL,
                    "artifact_id": ap.id,
                    "after": _row_dict(ap),
                }
            ),
        )
        return ap

    def get_by_encounter(self, encounter_id: str) -> list[Approval]:
        return list(
            self.s.exec(
                select(Approval).where(Approval.encounter_id == encounter_id)
            ).all()
        )


class FhirExportRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def save(
        self,
        *,
        encounter_id: str,
        resource_type: str,
        fhir_version: str,
        resource: dict[str, Any],
        json_text: str,
        audit: AuditMeta,
    ) -> FhirExport:
        row = FhirExport(
            encounter_id=encounter_id,
            resource_type=resource_type,
            fhir_version=fhir_version,
            resource=resource,
            json_text=json_text,
        )
        self.s.add(row)
        self.s.flush()
        write_audit(
            self.s,
            encounter_id,
            audit.model_copy(
                update={
                    "artifact_type": ArtifactType.FHIR_EXPORT,
                    "artifact_id": row.id,
                    "after": _row_dict(row),
                }
            ),
        )
        return row

    def get_by_encounter(self, encounter_id: str) -> list[FhirExport]:
        return list(
            self.s.exec(
                select(FhirExport).where(FhirExport.encounter_id == encounter_id)
            ).all()
        )


class AuditRepo:
    """Read-only access to the audit trail."""

    def __init__(self, session: Session) -> None:
        self.s = session

    def list_for_encounter(self, encounter_id: str) -> list[AuditLog]:
        return list(
            self.s.exec(
                select(AuditLog)
                .where(AuditLog.encounter_id == encounter_id)
                .order_by(AuditLog.created_at)
            ).all()
        )

    def list_all(self) -> list[AuditLog]:
        return list(self.s.exec(select(AuditLog).order_by(AuditLog.created_at)).all())
