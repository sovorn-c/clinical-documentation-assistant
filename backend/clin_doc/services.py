"""Pipeline orchestration (execute-plan §9 Phase 2).

Thin wrappers over the §7 entrypoints + the §8 glue, persisted via the Phase 1
repositories with an audit row per state change. Human-approval checkpoints
extend M1's Draft→EditedDraft→ApprovedNote pattern to codes and referral:
nothing reaches ``export_fhir`` without the matching approval records.

Engines are injected (see deps.py) so the full flow is exercisable with fakes.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from clin_core_glue.referral import generate_referral as _generate_referral
from clin_core_glue.soap_text import flatten_soap
from scribe.domain.types import (
    Approver,
    Audio,
    Dialogue,
    EditedDraft,
    PatientContext,
    Provenance,
    Utterance,
)
from sqlmodel import Session

from clin_doc.db.audit import AuditMeta
from clin_doc.db.enums import (
    ArtifactType,
    AuditAction,
    AuditActor,
    EncounterStatus,
)
from clin_doc.db.models import Encounter, Note, Patient, User
from clin_doc.db.repositories import (
    ApprovalRepo,
    AuditRepo,
    CodeRepo,
    EncounterRepo,
    FhirExportRepo,
    NoteRepo,
    PatientRepo,
    ReferralRepo,
    TranscriptRepo,
)
from clin_doc.db.roundtrip import (
    deid_to_dict,
    flatten_dialogue,
    provenance_from_dict,
    provenance_to_dict,
    soap_from_dict,
    soap_to_dict,
    summary_to_dict,
)


class PipelineService:
    def __init__(
        self,
        session: Session,
        actor: User,
        scribe: object,
        coder: object,
        llm_client: object,
        summarizer: object,
        deidentify: object,
    ) -> None:
        self.s = session
        self.actor = actor
        self.scribe = scribe
        self.coder = coder
        self.llm = llm_client
        self.summarizer = summarizer
        self.deidentify = deidentify

    # --- audit helpers -------------------------------------------------------
    def _audit(self, action: AuditAction, actor: AuditActor = AuditActor.USER) -> AuditMeta:
        return AuditMeta(
            actor=actor,
            actor_name=self.actor.display_name or self.actor.username,
            action=action,
        )

    # --- patients / encounters ----------------------------------------------
    def create_patient(
        self, *, patient_ref: str, display_name: str | None, fhir_bundle_path: str | None
    ) -> Patient:
        patient = PatientRepo(self.s).upsert(
            patient_ref=patient_ref,
            display_name=display_name,
            fhir_bundle_path=fhir_bundle_path,
            audit=self._audit(AuditAction.CREATE_PATIENT, AuditActor.USER),
        )
        self.s.commit()
        return patient

    def create_encounter(
        self, *, patient_id: str, encounter_ref: str, audio_path: str | None
    ) -> Encounter:
        enc = EncounterRepo(self.s).create(
            patient_id=patient_id,
            encounter_ref=encounter_ref,
            audio_path=audio_path,
            audit=self._audit(AuditAction.UPLOAD_AUDIO, AuditActor.USER),
        )
        self.s.commit()
        return enc

    def upload_audio(self, encounter_id: str, data: bytes, filename: str) -> Encounter:
        """Persist uploaded audio bytes and record the path on the encounter."""
        from pathlib import Path

        from clin_doc.db.audit import write_audit
        from clin_doc.settings import get_settings

        enc = self._require_encounter(encounter_id)
        upload_dir = Path(get_settings().upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe = filename.replace("/", "_")
        dest = upload_dir / f"{encounter_id}_{safe}"
        dest.write_bytes(data)
        before = {"audio_path": enc.audio_path}
        enc.audio_path = str(dest)
        self.s.add(enc)
        self.s.flush()
        write_audit(
            self.s,
            encounter_id,
            self._audit(AuditAction.UPLOAD_AUDIO, AuditActor.USER).model_copy(
                update={
                    "artifact_type": ArtifactType.ENCOUNTER,
                    "artifact_id": enc.id,
                    "before": before,
                    "after": {"audio_path": enc.audio_path},
                    "meta": {"filename": safe, "bytes": len(data)},
                }
            ),
        )
        self.s.commit()
        return enc

    # --- M1: audio -> SOAP note ---------------------------------------------
    def generate_note(self, encounter_id: str) -> Note:
        enc = self._require_encounter(encounter_id)
        if not enc.audio_path:
            raise ValueError("encounter has no audio; upload audio first")
        patient = PatientRepo(self.s).get(enc.patient_id)
        if patient is None:
            raise KeyError(f"no patient {enc.patient_id}")
        ctx = PatientContext(
            patient_ref=patient.patient_ref,
            encounter_ref=enc.encounter_ref,
            patient_display=patient.display_name,
        )
        audio = Audio(source="file", path=enc.audio_path)
        draft = self.scribe.generateDraft(audio, ctx)  # type: ignore[attr-defined]

        TranscriptRepo(self.s).save(
            encounter_id=encounter_id,
            utterances=[u.model_dump(mode="json") for u in draft.dialogue.utterances],
            transcript_text=flatten_dialogue(draft.dialogue),
            asr_id=draft.provenance.asr_id,
            diarizer_id=draft.provenance.diarizer_id,
            audit=self._audit(AuditAction.GENERATE_NOTE, AuditActor.SYSTEM),
        )
        note = NoteRepo(self.s).create_draft(
            encounter_id=encounter_id,
            note=soap_to_dict(draft.note),
            provenance=provenance_to_dict(draft.provenance),
            draft_id=draft.id,
            audit=self._audit(AuditAction.GENERATE_NOTE, AuditActor.SYSTEM),
        )
        EncounterRepo(self.s).update_status(
            encounter_id, EncounterStatus.NOTE_DRAFTED, self._audit(AuditAction.GENERATE_NOTE)
        )
        self.s.commit()
        return note

    def edit_note(self, encounter_id: str, note_dict: dict[str, Any]) -> Note:
        # Validate the payload parses as a SOAPNote before persisting — a
        # malformed note would round-trip fine into the JSON column but break
        # the export path later. Reject early with a clear error.
        soap_from_dict(note_dict)
        NoteRepo(self.s).save_edit(
            encounter_id=encounter_id,
            note=note_dict,
            audit=self._audit(AuditAction.EDIT_NOTE, AuditActor.USER),
        )
        EncounterRepo(self.s).update_status(
            encounter_id, EncounterStatus.NOTE_EDITED, self._audit(AuditAction.EDIT_NOTE)
        )
        self.s.commit()
        return NoteRepo(self.s).get_latest(encounter_id)  # type: ignore[return-value]

    # --- S3: suggest codes (de-id boundary first) ---------------------------
    def suggest_codes(self, encounter_id: str) -> list[dict[str, Any]]:
        latest = NoteRepo(self.s).get_latest(encounter_id)
        if latest is None:
            raise KeyError("no note for encounter")
        note_text = flatten_soap(soap_from_dict(latest.note))
        deid = self.deidentify(note_text)
        redacted = deid.redacted_text if hasattr(deid, "redacted_text") else note_text

        suggestions = self.coder(redacted)  # list[CodeSuggestion]
        sug_dicts = [s.model_dump(mode="json") for s in suggestions]

        rows = CodeRepo(self.s).save_suggestions(
            encounter_id=encounter_id,
            note_id=latest.id,
            suggestions=sug_dicts,
            audit=self._audit(AuditAction.SUGGEST_CODES, AuditActor.SYSTEM).model_copy(
                update={
                    "meta": {
                        "deid_audit": deid_to_dict(deid)["audit"]
                        if hasattr(deid, "model_dump")
                        else None,
                        "n_suggestions": len(sug_dicts),
                    }
                }
            ),
        )
        EncounterRepo(self.s).update_status(
            encounter_id, EncounterStatus.CODES_SUGGESTED, self._audit(AuditAction.SUGGEST_CODES)
        )
        self.s.commit()
        return [r.model_dump(mode="json") for r in rows]

    # --- §8.3: referral letter (de-id boundary first) -----------------------
    def generate_referral(self, encounter_id: str) -> str:
        latest = NoteRepo(self.s).get_latest(encounter_id)
        if latest is None:
            raise KeyError("no note for encounter")
        enc = self._require_encounter(encounter_id)
        patient = PatientRepo(self.s).get(enc.patient_id)
        note_text = flatten_soap(soap_from_dict(latest.note))
        ctx_text = self._patient_context_text(patient, enc)
        deid_note = self.deidentify(note_text)
        deid_ctx = self.deidentify(ctx_text)
        redacted_note = (
            deid_note.redacted_text if hasattr(deid_note, "redacted_text") else note_text
        )
        redacted_ctx = deid_ctx.redacted_text if hasattr(deid_ctx, "redacted_text") else ctx_text

        model_id = getattr(self.llm, "model", "unknown")
        letter = _generate_referral(
            note_text=redacted_note,
            patient_context=redacted_ctx,
            llm=self.llm,  # type: ignore[arg-type]
        )
        ReferralRepo(self.s).save(
            encounter_id=encounter_id,
            note_id=latest.id,
            letter_text=letter,
            model=model_id,
            audit=self._audit(AuditAction.GENERATE_REFERRAL, AuditActor.SYSTEM).model_copy(
                update={"meta": {"model": model_id, "deid": True}}
            ),
        )
        EncounterRepo(self.s).update_status(
            encounter_id,
            EncounterStatus.REFERRAL_GENERATED,
            self._audit(AuditAction.GENERATE_REFERRAL),
        )
        self.s.commit()
        return letter

    # --- S1: summarize ------------------------------------------------------
    def summarize_patient(self, patient_id: str) -> dict[str, Any]:
        from clinical_core.fhir import load_bundle

        patient = PatientRepo(self.s).get(patient_id)
        if patient is None or not patient.fhir_bundle_path:
            raise KeyError("patient has no fhir_bundle_path")
        record = load_bundle(patient.fhir_bundle_path)
        summary = self.summarizer(record)
        write_audit_summary(
            self.s, patient_id, summary, self._audit(AuditAction.SUMMARIZE, AuditActor.SYSTEM)
        )
        self.s.commit()
        return summary.model_dump(mode="json") if hasattr(summary, "model_dump") else dict(summary)

    # --- approvals (the gate) -----------------------------------------------
    def approve_note(self, encounter_id: str, approver_name: str, approver_role: str) -> str:
        latest = NoteRepo(self.s).get_latest(encounter_id)
        if latest is None:
            raise KeyError("no note for encounter")
        ApprovalRepo(self.s).record(
            encounter_id=encounter_id,
            approver_name=approver_name,
            approver_role=approver_role,
            artifact_type=ArtifactType.NOTE,
            artifact_id=latest.id,
            audit=self._audit(AuditAction.APPROVE_NOTE, AuditActor.USER),
        )
        self.s.commit()
        return latest.id

    def approve_codes(self, encounter_id: str, approver_name: str, approver_role: str) -> None:
        rows = CodeRepo(self.s).get_by_encounter(encounter_id)
        if not rows:
            raise KeyError("no codes for encounter")
        for r in rows:
            CodeRepo(self.s).set_approved(
                r.id, True, self._audit(AuditAction.APPROVE_CODES, AuditActor.USER)
            )
        ApprovalRepo(self.s).record(
            encounter_id=encounter_id,
            approver_name=approver_name,
            approver_role=approver_role,
            artifact_type=ArtifactType.CODES,
            artifact_id=encounter_id,
            audit=self._audit(AuditAction.APPROVE_CODES, AuditActor.USER),
        )
        self.s.commit()

    def approve_referral(self, encounter_id: str, approver_name: str, approver_role: str) -> str:
        ref = ReferralRepo(self.s).get_by_encounter(encounter_id)
        if ref is None:
            raise KeyError("no referral for encounter")
        ReferralRepo(self.s).set_approved(
            ref.id, True, self._audit(AuditAction.APPROVE_REFERRAL, AuditActor.USER)
        )
        ApprovalRepo(self.s).record(
            encounter_id=encounter_id,
            approver_name=approver_name,
            approver_role=approver_role,
            artifact_type=ArtifactType.REFERRAL,
            artifact_id=ref.id,
            audit=self._audit(AuditAction.APPROVE_REFERRAL, AuditActor.USER),
        )
        self.s.commit()
        return ref.id

    # --- FHIR export (gated; Phase 4 adds Condition/Claim) ------------------
    def export_fhir(self, encounter_id: str) -> list[dict[str, Any]]:
        from clin_core_glue.fhir_codes import codes_to_conditions

        self._require_approvals(encounter_id)
        enc = self._require_encounter(encounter_id)
        patient = PatientRepo(self.s).get(enc.patient_id)
        edited = self._build_edited_draft(encounter_id, enc, patient)
        approver = Approver(
            name=self.actor.display_name or self.actor.username, role=self.actor.role
        )
        doc = self.scribe.approveAndExport(edited, approver)  # type: ignore[attr-defined]

        exports: list[dict[str, Any]] = []
        FhirExportRepo(self.s).save(
            encounter_id=encounter_id,
            resource_type="DocumentReference",
            fhir_version="R5",
            resource=doc.resource,
            json_text=doc.json_text,
            audit=self._audit(AuditAction.FHIR_EXPORT, AuditActor.USER),
        )
        exports.append({"resource_type": "DocumentReference", "fhir_version": "R5"})

        # §8.4: map approved CodeSuggestions -> validated R4 Condition resources.
        # Only approved codes are exported (the gate already required codes
        # approval when codes exist). Nothing is fabricated — the ICD-10-CM
        # codes come from S3; patient/encounter refs from the encounter.
        code_rows = CodeRepo(self.s).get_by_encounter(encounter_id)
        approved = [r for r in code_rows if r.approved]
        if approved:
            suggestions = [
                {
                    "code": r.code,
                    "description": r.description,
                    "confidence": r.confidence,
                    "evidence": r.evidence,
                    "rank": r.rank,
                }
                for r in approved
            ]
            patient_ref = patient.patient_ref if patient else enc.encounter_ref
            conditions = codes_to_conditions(
                suggestions, patient_ref=patient_ref, encounter_ref=enc.encounter_ref
            )
            for cond in conditions:
                FhirExportRepo(self.s).save(
                    encounter_id=encounter_id,
                    resource_type="Condition",
                    fhir_version="R4",
                    resource=cond,
                    json_text=json.dumps(cond),
                    audit=self._audit(AuditAction.FHIR_EXPORT, AuditActor.USER),
                )
                exports.append({"resource_type": "Condition", "fhir_version": "R4"})

        EncounterRepo(self.s).update_status(
            encounter_id, EncounterStatus.EXPORTED, self._audit(AuditAction.FHIR_EXPORT)
        )
        self.s.commit()
        return exports

    # --- read helpers --------------------------------------------------------
    def list_audit(self, encounter_id: str) -> list[dict[str, Any]]:
        return [
            r.model_dump(mode="json") for r in AuditRepo(self.s).list_for_encounter(encounter_id)
        ]

    # --- internals -----------------------------------------------------------
    def _require_encounter(self, encounter_id: str) -> Encounter:
        enc = EncounterRepo(self.s).get(encounter_id)
        if enc is None:
            raise KeyError(f"no encounter {encounter_id}")
        return enc

    def _require_approvals(self, encounter_id: str) -> None:
        approvals = {
            a.artifact_type: a for a in ApprovalRepo(self.s).get_by_encounter(encounter_id)
        }
        if "note" not in approvals:
            raise PermissionError("note is not approved; cannot export")
        if CodeRepo(self.s).get_by_encounter(encounter_id) and "codes" not in approvals:
            raise PermissionError("codes are not approved; cannot export")
        if ReferralRepo(self.s).get_by_encounter(encounter_id) and "referral" not in approvals:
            raise PermissionError("referral is not approved; cannot export")

    def _patient_context_text(self, patient: Patient | None, enc: Encounter) -> str:
        name = patient.display_name if patient else "Unknown"
        return f"Patient: {name}. Encounter: {enc.encounter_ref}."

    def _build_edited_draft(
        self, encounter_id: str, enc: Encounter, patient: Patient | None
    ) -> EditedDraft:
        latest = NoteRepo(self.s).get_latest(encounter_id)
        if latest is None:
            raise KeyError("no note to export")
        transcript = TranscriptRepo(self.s).get_by_encounter(encounter_id)
        utterances = (
            [Utterance.model_validate(u) for u in transcript.utterances] if transcript else []
        )
        dialogue = Dialogue(utterances=utterances)
        provenance = (
            provenance_from_dict(latest.provenance)
            if latest.provenance
            else Provenance(model_id="unknown", asr_id="unknown", diarizer_id="unknown")
        )
        ctx = PatientContext(
            patient_ref=patient.patient_ref if patient else enc.encounter_ref,
            encounter_ref=enc.encounter_ref,
            patient_display=patient.display_name if patient else None,
        )
        return EditedDraft(
            id=latest.draft_id or str(uuid4()),
            ctx=ctx,
            dialogue=dialogue,
            note=soap_from_dict(latest.note),
            provenance=provenance,
        )


def write_audit_summary(session: Session, patient_id: str, summary: Any, audit: AuditMeta) -> None:
    from clin_doc.db.audit import write_audit

    meta = {"model": getattr(summary, "model", None)}
    after = summary_to_dict(summary) if hasattr(summary, "model_dump") else None
    write_audit(
        session,
        None,
        audit.model_copy(
            update={
                "artifact_type": ArtifactType.ENCOUNTER,
                "artifact_id": patient_id,
                "after": after,
                "meta": meta,
            }
        ),
    )
