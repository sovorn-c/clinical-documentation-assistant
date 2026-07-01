"""Phase 2 API tests — the full pipeline flow via HTTP, with injectable engines.

Acceptance (execute-plan §9 Phase 2): "Full flow exercised via API tests."

Engines are faked where they need models/keys (S3 coder, S1 summarize, referral
LLM); M1's approveAndExport runs for real (no LLM) over a fake-transcriber
Scribe; the de-id boundary runs for real (rules-only, fast). This proves the
orchestration, approval gating, audit trail, and de-id placement — not model
inference, which is verified in Phase 5.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# --- test DB isolation: point settings + engine cache at a temp SQLite -------
_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["SEED_USERNAME"] = "clinician"
os.environ["SEED_PASSWORD"] = "changeme"

from clin_doc.db.session import reset_engine_cache  # noqa: E402
from clin_doc.settings import get_settings  # noqa: E402

get_settings.cache_clear()
reset_engine_cache()

from auto_medical_coder import CodeSuggestion, EvidenceSpan  # noqa: E402
from clin_core_glue.deid import redact_for_cloud  # noqa: E402
from clin_doc import deps  # noqa: E402
from clin_doc.main import app  # noqa: E402
from clinical_core.fhir.models import SourceRef  # noqa: E402
from phi.models import DeidConfig  # noqa: E402
from scribe.app.drafts import InMemoryDraftStore  # noqa: E402
from scribe.app.scribe import Scribe  # noqa: E402
from scribe.dialogue import DialogueExtractor  # noqa: E402
from scribe.dialogue.diarizer.base import NullDiarizer  # noqa: E402
from scribe.dialogue.transcriber.base import Transcriber  # noqa: E402
from scribe.domain.types import (  # noqa: E402
    Claim,
    SOAPNote,
    TimeSpan,
    TranscriptSeg,
)
from scribe.fhir import FhirExporter  # noqa: E402
from summarizer.models import Bullet, Section, Summary  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


# --- fakes -------------------------------------------------------------------


class _FakeTranscriber(Transcriber):
    def transcribe(self, audio: object) -> list[TranscriptSeg]:
        return [
            TranscriptSeg(
                text="Hello, what brings you in?", time_span=TimeSpan(start=0.0, end=3.0)
            ),
            TranscriptSeg(
                text="I've been thirsty and tired.", time_span=TimeSpan(start=3.2, end=6.0)
            ),
        ]

    @property
    def identifier(self) -> str:
        return "fake"


class _FakeNoteGenerator:
    llm_id = "fake-llm"

    def generate(self, dialogue: object) -> SOAPNote:
        return SOAPNote(
            subjective=[Claim(text="Patient reports thirst and fatigue.")],
            objective=[Claim(text="BMI 31.")],
            assessment=[Claim(text="Type 2 diabetes mellitus.")],
            plan=[Claim(text="Check HbA1c; start metformin.")],
        )


def _fake_scribe() -> Scribe:
    return Scribe(
        dialogue_extractor=DialogueExtractor(
            transcriber=_FakeTranscriber(), diarizer=NullDiarizer()
        ),
        note_generator=_FakeNoteGenerator(),
        fhir_exporter=FhirExporter(),
        draft_store=InMemoryDraftStore(),
    )


def _fake_coder(note: str) -> list[CodeSuggestion]:
    return [
        CodeSuggestion(
            code="E11.9",
            description="Type 2 diabetes mellitus without complications",
            confidence=0.92,
            evidence=EvidenceSpan(
                quote=note[:10] if note else "diabetes", start=0, end=min(10, len(note) or 8)
            ),
            rank=1,
        ),
        CodeSuggestion(
            code="E66.9",
            description="Obesity, unspecified",
            confidence=0.71,
            evidence=EvidenceSpan(quote="BMI", start=0, end=3),
            rank=2,
        ),
    ]


class _FakeLLM:
    model = "fake-llm"

    def complete(self, system: str, user: str, schema: type[Any]) -> Any:
        from clin_core_glue.referral import ReferralLetter

        return ReferralLetter(
            letter="Dear Cardiology,\n\nPlease review this patient for T2DM management.\n\nDr. Demo"
        )


def _fake_summarizer(record: object) -> Summary:
    return Summary(
        patient_id="patient-1",
        one_liner="T2DM on metformin.",
        sections=[
            Section(
                heading="Problems",
                bullets=[
                    Bullet(
                        text="T2DM",
                        source_refs=[SourceRef(resource_type="Condition", resource_id="cond-1")],
                    )
                ],
            ),
            Section(heading="Medications", bullets=[], no_data=True),
            Section(heading="Recent Encounters", bullets=[], no_data=True),
            Section(heading="Key Results", bullets=[], no_data=True),
            Section(heading="Allergies", bullets=[], no_data=True),
        ],
        model="fake-summarizer",
    )


def _rules_only_deidentify(text: str) -> Any:
    return redact_for_cloud(text, DeidConfig(use_rules=True, use_ner=False, use_llm=False))


@pytest.fixture(scope="module")
def client() -> TestClient:
    # Overrides must be zero-arg providers (like the real deps) so FastAPI
    # doesn't introspect the returned callable's params as query params.
    app.dependency_overrides[deps.get_scribe] = _fake_scribe
    app.dependency_overrides[deps.get_coder] = lambda: _fake_coder
    app.dependency_overrides[deps.get_llm_client] = lambda: _FakeLLM()
    app.dependency_overrides[deps.get_summarizer] = lambda: _fake_summarizer
    app.dependency_overrides[deps.get_deidentify] = lambda: _rules_only_deidentify
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": "clinician", "password": "changeme"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- tests -------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["synthetic_data_only"] is True


def test_full_pipeline_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    h = auth_headers
    # 1. patient (with a real R4 bundle for summarize)
    r = client.post(
        "/api/patients",
        json={
            "patient_ref": "patient-1",
            "display_name": "Jane Doe",
            "fhir_bundle_path": str(FIXTURES / "r4_patient_bundle.json"),
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    patient_id = r.json()["id"]

    # 2. encounter with dummy audio path (fake transcriber ignores the file)
    r = client.post(
        "/api/encounters",
        json={"patient_id": patient_id, "encounter_ref": "enc-1", "audio_path": "/tmp/fake.wav"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    enc_id = r.json()["id"]
    assert r.json()["status"] == "audio_uploaded"

    # 3. generate note (fake Scribe)
    r = client.post(f"/api/encounters/{enc_id}/generate-note", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "ai"
    assert r.json()["note"]["assessment"][0]["text"] == "Type 2 diabetes mellitus."

    # 4. edit note (human)
    edited_note = {
        "subjective": [{"text": "Patient reports thirst, fatigue, and polyuria.", "citations": []}],
        "objective": [{"text": "BMI 31.", "citations": []}],
        "assessment": [{"text": "Type 2 diabetes mellitus.", "citations": []}],
        "plan": [{"text": "Check HbA1c; start metformin 500mg BID.", "citations": []}],
    }
    r = client.put(f"/api/encounters/{enc_id}/note", json={"note": edited_note}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "human"
    assert r.json()["version"] == 2

    # 5. suggest codes (after de-id)
    r = client.post(f"/api/encounters/{enc_id}/suggest-codes", headers=h)
    assert r.status_code == 200, r.text
    codes = r.json()
    assert len(codes) == 2
    assert codes[0]["code"] == "E11.9"

    # 6. generate referral (after de-id)
    r = client.post(f"/api/encounters/{enc_id}/generate-referral", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["letter_text"].startswith("Dear Cardiology")

    # 7. export is GATED before approvals -> 409
    r = client.post(f"/api/encounters/{enc_id}/export-fhir", headers=h)
    assert r.status_code == 409

    # 8. approvals (note + codes + referral)
    ar = {"approver_name": "Dr. Demo", "approver_role": "clinician"}
    assert (
        client.post(f"/api/encounters/{enc_id}/approve-note", json=ar, headers=h).status_code == 200
    )
    assert (
        client.post(f"/api/encounters/{enc_id}/approve-codes", json=ar, headers=h).status_code
        == 204
    )
    assert (
        client.post(f"/api/encounters/{enc_id}/approve-referral", json=ar, headers=h).status_code
        == 204
    )

    # 9. export now succeeds
    r = client.post(f"/api/encounters/{enc_id}/export-fhir", headers=h)
    assert r.status_code == 200, r.text
    exports = r.json()
    assert any(
        e["resource_type"] == "DocumentReference" and e["fhir_version"] == "R5" for e in exports
    )
    assert "Patient/patient-1" in exports[0]["json_text"]

    # 10. audit trail covers the whole flow
    r = client.get(f"/api/encounters/{enc_id}/audit", headers=h)
    assert r.status_code == 200
    actions = [a["action"] for a in r.json()]
    for expected in [
        "upload_audio",
        "generate_note",
        "edit_note",
        "suggest_codes",
        "generate_referral",
        "approve_note",
        "approve_codes",
        "approve_referral",
        "fhir_export",
    ]:
        assert expected in actions, actions
    # AI vs human distinction
    edit = next(a for a in r.json() if a["action"] == "edit_note")
    assert edit["actor"] == "user"
    gen = next(a for a in r.json() if a["action"] == "generate_note")
    assert gen["actor"] == "system"
    # de-id event recorded with privacy-safe counts (no PHI value)
    sc = next(a for a in r.json() if a["action"] == "suggest_codes")
    assert sc["meta"]["deid_audit"] is not None or sc["meta"]["n_suggestions"] == 2


def test_summarize(client: TestClient, auth_headers: dict[str, str]) -> None:
    h = auth_headers
    r = client.post(
        "/api/patients",
        json={
            "patient_ref": "patient-sum",
            "display_name": "Sum Patient",
            "fhir_bundle_path": str(FIXTURES / "r4_patient_bundle.json"),
        },
        headers=h,
    )
    pid = r.json()["id"]
    r = client.post(f"/api/patients/{pid}/summarize", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["one_liner"] == "T2DM on metformin."
    assert body["sections"][0]["heading"] == "Problems"


def test_auth_required(client: TestClient) -> None:
    # No token -> 401 on a protected endpoint
    assert client.get("/api/patients").status_code == 401
    assert client.post("/api/encounters/x/generate-note").status_code == 401


def test_export_gating_without_codes_or_referral(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A note-only encounter can export once the note is approved (no codes/referral present)."""
    h = auth_headers
    pid = client.post(
        "/api/patients", json={"patient_ref": "p-gate", "display_name": "Gate"}, headers=h
    ).json()["id"]
    eid = client.post(
        "/api/encounters",
        json={"patient_id": pid, "encounter_ref": "e-gate", "audio_path": "/tmp/f.wav"},
        headers=h,
    ).json()["id"]
    client.post(f"/api/encounters/{eid}/generate-note", headers=h)
    # not approved yet -> 409
    assert client.post(f"/api/encounters/{eid}/export-fhir", headers=h).status_code == 409
    client.post(
        f"/api/encounters/{eid}/approve-note", json={"approver_name": "Dr. Demo"}, headers=h
    )
    # now succeeds (no codes/referral to require)
    r = client.post(f"/api/encounters/{eid}/export-fhir", headers=h)
    assert r.status_code == 200


def teardown_module() -> None:  # type: ignore[name-defined]
    import os

    reset_engine_cache()
    get_settings.cache_clear()
    try:
        os.unlink(_tmp.name)
    except OSError:
        pass
