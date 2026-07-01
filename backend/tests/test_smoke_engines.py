"""Phase 0 smoke tests — all four engines importable and individually callable.

Per execute-plan §9 Phase 0 acceptance: "Engines importable and individually
callable." Real model calls that need prerequisites are deferred and noted:

  * M1 ``generateDraft`` / ``approveAndExport`` — exercised with fakes (the
    real path needs mlx-whisper + ollama; the facade + DialogueExtractor +
    FhirExporter are what matter here).
  * S2 ``deidentify`` — real rules-only call (no spaCy model load needed).
  * S3 ``code`` — importable + signature/model contract; a real call needs the
    built catalogue + Chroma index and an API key (baked in Phase 5).
  * S1 ``load_bundle`` — real call on a fixture bundle (no LLM); ``summarize``
    is importable + signature-checked (a real call needs an API key).
"""

from __future__ import annotations

import inspect

from scribe.app.drafts import InMemoryDraftStore
from scribe.app.scribe import Scribe
from scribe.dialogue import DialogueExtractor
from scribe.dialogue.diarizer.base import NullDiarizer
from scribe.domain.types import Approver, Audio, EditedDraft, PatientContext
from scribe.fhir import FhirExporter


def test_m1_generate_draft(
    fake_transcriber: object,
    fake_note_generator: object,
    patient_ctx: PatientContext,
) -> None:
    scribe = Scribe(
        dialogue_extractor=DialogueExtractor(transcriber=fake_transcriber, diarizer=NullDiarizer()),  # type: ignore[arg-type]
        note_generator=fake_note_generator,  # type: ignore[arg-type]
        fhir_exporter=FhirExporter(),
        draft_store=InMemoryDraftStore(),
    )
    draft = scribe.generateDraft(Audio(source="fake"), patient_ctx)

    assert draft.ctx.patient_ref == "patient-1"
    assert draft.note.subjective[0].text.startswith("Patient reports")
    assert draft.note.assessment[0].text == "Possible diabetes mellitus."
    assert draft.dialogue.utterances  # aligner + role labeller produced utterances
    assert draft.provenance.asr_id == "fake"


def test_m1_approve_and_export(
    fake_transcriber: object,
    fake_note_generator: object,
    patient_ctx: PatientContext,
) -> None:
    scribe = Scribe(
        dialogue_extractor=DialogueExtractor(transcriber=fake_transcriber, diarizer=NullDiarizer()),  # type: ignore[arg-type]
        note_generator=fake_note_generator,  # type: ignore[arg-type]
        fhir_exporter=FhirExporter(),
        draft_store=InMemoryDraftStore(),
    )
    draft = scribe.generateDraft(Audio(source="fake"), patient_ctx)
    edited = EditedDraft(**draft.model_dump())

    doc = scribe.approveAndExport(edited, Approver(name="Dr. Test", role="clinician"))

    assert doc.resource["resourceType"] == "DocumentReference"
    assert "Patient/patient-1" in doc.json_text
    assert "Encounter/enc-1" in doc.json_text


def test_s2_deidentify_rules_only() -> None:
    from phi.deidentify import deidentify
    from phi.models import DeidConfig

    # Rules-only (use_ner=False) avoids loading the 560MB spaCy model. The rule
    # layer is region-tuned (PHI_REGIONS=NZ,AU): it reliably catches structured
    # identifiers (email, MRN) regardless of region; phone detection is
    # region-specific, so we assert on the region-independent catches.
    text = "Contact Dr. Smith at smith@hospital.org (MRN 12345)."
    result = deidentify(text, DeidConfig(use_rules=True, use_ner=False, use_llm=False))

    assert "smith@hospital.org" not in result.redacted_text
    assert "12345" not in result.redacted_text
    assert result.spans
    assert result.audit  # privacy-safe counts/types only, never the PHI value


def test_s3_code_importable_and_contract() -> None:
    from auto_medical_coder import CodeSuggestion, code, code_result

    assert callable(code) and callable(code_result)
    sig = inspect.signature(code)
    assert "note" in sig.parameters
    assert list(CodeSuggestion.model_fields) >= [
        "code",
        "description",
        "confidence",
        "evidence",
        "rank",
    ]


def test_s1_load_bundle(r4_bundle_path) -> None:
    from clinical_core.fhir import load_bundle

    record = load_bundle(r4_bundle_path)

    assert record.patient.id == "patient-1"
    assert record.patient.name == "Jane Doe"
    assert record.conditions  # diabetes
    assert record.medications  # metformin
    assert record.encounters
    assert record.allergies


def test_s1_summarize_importable() -> None:
    from summarizer.pipeline import summarize

    assert callable(summarize)
    assert "record" in inspect.signature(summarize).parameters
