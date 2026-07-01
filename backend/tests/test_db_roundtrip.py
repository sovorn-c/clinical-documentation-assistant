"""Phase 1 tests — schema round-trips every §7 Pydantic type; every write audited.

Acceptance (execute-plan §9 Phase 1): "Every state change audited; schema
round-trips each Pydantic model from §7 without lossy conversion."

Complex nested types live in JSON columns (``model_dump(mode="json")``) and
reload via ``model_validate``; codes are stored relationally (one row per
CodeSuggestion) and reconstructed. The audit trail gets one row per write,
with before/after for diffing AI output vs human edits.
"""

from __future__ import annotations

from datetime import UTC, datetime

from clin_doc.db.audit import AuditMeta
from clin_doc.db.enums import (
    ArtifactType,
    AuditAction,
    AuditActor,
    EncounterStatus,
)
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
    deid_from_dict,
    deid_to_dict,
    documentref_from_dict,
    provenance_from_dict,
    provenance_to_dict,
    soap_from_dict,
    soap_to_dict,
    summary_from_dict,
    summary_to_dict,
)
from scribe.domain.types import (
    Claim,
    Dialogue,
    DocumentRef,
    Provenance,
    SOAPNote,
    SpanRef,
    TimeSpan,
    Utterance,
)
from scribe.domain.types import Role as ScribeRole
from sqlmodel import Session


def _audit(action: AuditAction, actor: AuditActor = AuditActor.SYSTEM) -> AuditMeta:
    return AuditMeta(actor=actor, action=action)


def _seed_encounter(session: Session) -> str:
    patient = PatientRepo(session).upsert(
        patient_ref="patient-1",
        display_name="Jane Doe",
        audit=_audit(AuditAction.CREATE_PATIENT),
    )
    enc = EncounterRepo(session).create(
        patient_id=patient.id,
        encounter_ref="enc-1",
        audit=_audit(AuditAction.UPLOAD_AUDIO),
    )
    return enc.id


# ── round-trip: each §7 Pydantic type ─────────────────────────────────────────


def test_roundtrip_soap_note(db_session: Session) -> None:
    note = SOAPNote(
        subjective=[Claim(text="Patient reports thirst.", citations=[SpanRef(utterance_id="u1", char_span=(0, 7))])],
        objective=[Claim(text="BMI 31.", citations=[SpanRef(utterance_id="u2")])],
        assessment=[Claim(text="Type 2 diabetes.")],
        plan=[Claim(text="Check HbA1c.", citations=[SpanRef(utterance_id="u3", char_span=(6, 11))])],
    )
    enc_id = _seed_encounter(db_session)
    NoteRepo(db_session).create_draft(
        encounter_id=enc_id,
        note=soap_to_dict(note),
        provenance=provenance_to_dict(
            Provenance(model_id="qwen2.5-7b", asr_id="mlx-whisper", diarizer_id="null")
        ),
        audit=_audit(AuditAction.GENERATE_NOTE),
    )
    db_session.commit()

    latest = NoteRepo(db_session).get_latest(enc_id)
    assert latest is not None
    assert soap_from_dict(latest.note) == note  # lossless
    assert provenance_from_dict(latest.provenance).asr_id == "mlx-whisper"


def test_roundtrip_dialogue(db_session: Session) -> None:
    dialogue = Dialogue(
        utterances=[
            Utterance(
                id="u1",
                role=ScribeRole.CLINICIAN,
                text="Hello.",
                time_span=TimeSpan(start=0.0, end=1.0),
                speaker_id="spk0",
            ),
            Utterance(
                id="u2",
                role=ScribeRole.PATIENT,
                text="I'm tired.",
                time_span=TimeSpan(start=1.2, end=2.5),
                speaker_id="spk1",
            ),
        ]
    )
    enc_id = _seed_encounter(db_session)
    TranscriptRepo(db_session).save(
        encounter_id=enc_id,
        utterances=[u.model_dump(mode="json") for u in dialogue.utterances],
        transcript_text="CLINICIAN: Hello.\nPATIENT: I'm tired.",
        asr_id="fake",
        diarizer_id="null",
        audit=_audit(AuditAction.GENERATE_NOTE),
    )
    db_session.commit()

    row = TranscriptRepo(db_session).get_by_encounter(enc_id)
    assert row is not None
    restored = Dialogue(utterances=[Utterance.model_validate(u) for u in row.utterances])
    assert restored == dialogue


def test_roundtrip_deid_result() -> None:
    from phi.models import AuditEntry, DeidResult, EntityType, PHISpan

    result = DeidResult(
        redacted_text="Contact [REDACTED:EMAIL]",
        spans=[PHISpan(start=8, end=24, type=EntityType.EMAIL, text="smith@hospital.org", source="rule")],
        audit=[AuditEntry(type=EntityType.EMAIL, count=1)],
    )
    assert deid_from_dict(deid_to_dict(result)) == result


def test_roundtrip_code_suggestion(db_session: Session) -> None:
    from auto_medical_coder import CodeSuggestion, EvidenceSpan

    s = CodeSuggestion(
        code="E11.9",
        description="Type 2 diabetes mellitus without complications",
        confidence=0.92,
        evidence=EvidenceSpan(quote="Type 2 diabetes", start=0, end=15),
        rank=1,
    )
    enc_id = _seed_encounter(db_session)
    note = NoteRepo(db_session).create_draft(
        encounter_id=enc_id,
        note=soap_to_dict(SOAPNote(assessment=[Claim(text="Type 2 diabetes.")])),
        audit=_audit(AuditAction.GENERATE_NOTE),
    )
    db_session.commit()

    CodeRepo(db_session).save_suggestions(
        encounter_id=enc_id,
        note_id=note.id,
        suggestions=[s.model_dump(mode="json")],
        audit=_audit(AuditAction.SUGGEST_CODES),
    )
    db_session.commit()

    rows = CodeRepo(db_session).get_by_encounter(enc_id)
    assert len(rows) == 1
    r = rows[0]
    restored = CodeSuggestion(
        code=r.code,
        description=r.description,
        confidence=r.confidence,
        evidence=EvidenceSpan(**r.evidence),
        rank=r.rank,
    )
    assert restored.model_dump(mode="json") == s.model_dump(mode="json")


def test_roundtrip_summary() -> None:
    from clinical_core.fhir.models import SourceRef
    from summarizer.models import Bullet, Section, Summary

    summary = Summary(
        patient_id="patient-1",
        one_liner="T2DM, well controlled on metformin.",
        sections=[
            Section(heading="Problems", bullets=[Bullet(text="T2DM", source_refs=[SourceRef(resource_type="Condition", resource_id="cond-1")])]),
            Section(heading="Medications", bullets=[], no_data=True),
            Section(heading="Recent Encounters", bullets=[], no_data=True),
            Section(heading="Key Results", bullets=[], no_data=True),
            Section(heading="Allergies", bullets=[], no_data=True),
        ],
        model="anthropic/claude-opus-4-8",
    )
    assert summary_from_dict(summary_to_dict(summary)) == summary


def test_roundtrip_document_ref(db_session: Session) -> None:
    doc = DocumentRef(
        resource={"resourceType": "DocumentReference", "status": "current", "subject": {"reference": "Patient/patient-1"}},
        json_text='{"resourceType":"DocumentReference"}',
    )
    enc_id = _seed_encounter(db_session)
    FhirExportRepo(db_session).save(
        encounter_id=enc_id,
        resource_type="DocumentReference",
        fhir_version="R5",
        resource=doc.resource,
        json_text=doc.json_text,
        audit=_audit(AuditAction.FHIR_EXPORT),
    )
    db_session.commit()

    exports = FhirExportRepo(db_session).get_by_encounter(enc_id)
    assert len(exports) == 1
    restored = documentref_from_dict({"resource": exports[0].resource, "json_text": exports[0].json_text})
    assert restored == doc


# ── audit: every state change writes exactly one audit row ────────────────────


def test_every_write_is_audited(db_session: Session) -> None:
    enc_id = _seed_encounter(db_session)  # 2 writes: patient + encounter

    note = NoteRepo(db_session).create_draft(
        encounter_id=enc_id,
        note=soap_to_dict(SOAPNote(subjective=[Claim(text="thirst.")])),
        audit=_audit(AuditAction.GENERATE_NOTE),
    )  # 1 write
    NoteRepo(db_session).save_edit(
        encounter_id=enc_id,
        note=soap_to_dict(SOAPNote(subjective=[Claim(text="Patient reports thirst and polyuria.")])),
        audit=_audit(AuditAction.EDIT_NOTE, AuditActor.USER),
    )  # 1 write
    CodeRepo(db_session).save_suggestions(
        encounter_id=enc_id,
        note_id=note.id,
        suggestions=[],
        audit=_audit(AuditAction.SUGGEST_CODES),
    )  # 1 write
    ReferralRepo(db_session).save(
        encounter_id=enc_id,
        note_id=note.id,
        letter_text="Dear colleague...",
        model="anthropic/claude-opus-4-8",
        audit=_audit(AuditAction.GENERATE_REFERRAL),
    )  # 1 write
    ApprovalRepo(db_session).record(
        encounter_id=enc_id,
        approver_name="Dr. Test",
        approver_role="clinician",
        artifact_type=ArtifactType.NOTE,
        artifact_id=note.id,
        audit=_audit(AuditAction.APPROVE_NOTE, AuditActor.USER),
    )  # 1 write
    FhirExportRepo(db_session).save(
        encounter_id=enc_id,
        resource_type="DocumentReference",
        fhir_version="R5",
        resource={"resourceType": "DocumentReference"},
        json_text="{}",
        audit=_audit(AuditAction.FHIR_EXPORT),
    )  # 1 write
    EncounterRepo(db_session).update_status(enc_id, EncounterStatus.EXPORTED, _audit(AuditAction.FHIR_EXPORT))  # 1 write
    db_session.commit()

    rows = AuditRepo(db_session).list_for_encounter(enc_id)
    actions = [r.action for r in rows]
    # 1 (encounter create) + 7 (above) = 8 encounter-scoped audit rows. The
    # patient-creation audit is encounter_id=None (patients aren't scoped).
    assert len(rows) == 8, actions
    assert actions.count("generate_note") == 1
    assert actions.count("edit_note") == 1
    assert actions.count("fhir_export") == 2  # export save + status update

    # The patient-creation audit is on the global trail, unscoped.
    all_rows = AuditRepo(db_session).list_all()
    assert any(r.action == "create_patient" and r.encounter_id is None for r in all_rows)


def test_note_edit_records_before_after_for_diff(db_session: Session) -> None:
    enc_id = _seed_encounter(db_session)
    ai_note = SOAPNote(subjective=[Claim(text="thirst.")])
    NoteRepo(db_session).create_draft(
        encounter_id=enc_id,
        note=soap_to_dict(ai_note),
        audit=_audit(AuditAction.GENERATE_NOTE),
    )
    human_note = SOAPNote(subjective=[Claim(text="Patient reports thirst and polyuria.")])
    NoteRepo(db_session).save_edit(
        encounter_id=enc_id,
        note=soap_to_dict(human_note),
        audit=_audit(AuditAction.EDIT_NOTE, AuditActor.USER),
    )
    db_session.commit()

    audit = AuditRepo(db_session).list_for_encounter(enc_id)
    edit_row = next(r for r in audit if r.action == "edit_note")
    assert edit_row.actor == "user"
    assert edit_row.before is not None
    assert edit_row.before["note"]["subjective"][0]["text"] == "thirst."
    assert edit_row.after["note"]["subjective"][0]["text"] == "Patient reports thirst and polyuria."
    # AI generation has no before (created from nothing) and actor=system.
    gen_row = next(r for r in audit if r.action == "generate_note")
    assert gen_row.actor == "system"
    assert gen_row.before is None


def test_deid_event_recorded_in_audit_meta(db_session: Session) -> None:
    from phi.models import AuditEntry, DeidResult, EntityType, PHISpan

    result = DeidResult(
        redacted_text="x [REDACTED:EMAIL]",
        spans=[PHISpan(start=2, end=18, type=EntityType.EMAIL, text="a@b.com", source="rule")],
        audit=[AuditEntry(type=EntityType.EMAIL, count=1)],
    )
    enc_id = _seed_encounter(db_session)
    # The service layer (Phase 2) records the de-id event with the privacy-safe
    # counts in meta — never the PHI value.
    from clin_doc.db.audit import write_audit

    write_audit(
        db_session,
        enc_id,
        AuditMeta(
            actor=AuditActor.SYSTEM,
            action=AuditAction.DEIDENTIFY,
            artifact_type=ArtifactType.DEID,
            meta={"deid_audit": deid_to_dict(result)["audit"]},
        ),
    )
    db_session.commit()

    rows = AuditRepo(db_session).list_for_encounter(enc_id)
    deid = next(r for r in rows if r.action == "deidentify")
    assert deid.meta["deid_audit"] == [{"type": "EMAIL", "count": 1}]
    assert "a@b.com" not in str(deid.meta)  # never the PHI value


def test_provenance_datetime_roundtrips(db_session: Session) -> None:
    enc_id = _seed_encounter(db_session)
    prov = Provenance(
        model_id="qwen2.5-7b",
        asr_id="mlx-whisper",
        diarizer_id="null",
        created_at=datetime(2026, 7, 1, 9, 30, tzinfo=UTC),
    )
    NoteRepo(db_session).create_draft(
        encounter_id=enc_id,
        note=soap_to_dict(SOAPNote()),
        provenance=provenance_to_dict(prov),
        audit=_audit(AuditAction.GENERATE_NOTE),
    )
    db_session.commit()

    latest = NoteRepo(db_session).get_latest(enc_id)
    restored = provenance_from_dict(latest.provenance)
    assert restored.created_at == prov.created_at  # datetime, not a string
