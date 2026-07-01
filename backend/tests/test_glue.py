"""Tests for the §8 glue modules.

soap_text  — SOAPNote -> flat text (§8.2)
deid       — de-id boundary helper wrapping S2 (§8.1)
referral   — net-new referral letter via LLMClient (§8.3), with a fake LLM
fhir_codes — CodeSuggestion -> R4 Condition/Claim (§8.4, Phase 4)
"""

from __future__ import annotations

import pytest
from clin_core_glue.deid import default_config, redact_for_cloud
from clin_core_glue.referral import ReferralLetter, generate_referral
from clin_core_glue.soap_text import flatten_soap
from scribe.domain.types import Claim, SOAPNote


def test_flatten_soap_preserves_sections_and_claims() -> None:
    note = SOAPNote(
        subjective=[Claim(text="Patient reports thirst and polyuria.")],
        objective=[Claim(text="BMI 31. Blood pressure 138/88.")],
        assessment=[Claim(text="Type 2 diabetes mellitus.")],
        plan=[Claim(text="Check HbA1c; start metformin.")],
    )
    text = flatten_soap(note)
    assert "SUBJECTIVE:" in text
    assert "ASSESSMENT:" in text
    assert "- Patient reports thirst and polyuria." in text
    assert "- Type 2 diabetes mellitus." in text


def test_flatten_soap_skips_empty_sections() -> None:
    note = SOAPNote(subjective=[Claim(text="thirst.")], objective=[], assessment=[], plan=[])
    assert flatten_soap(note) == "SUBJECTIVE:\n- thirst."


def test_redact_for_cloud_redacts_identifiers() -> None:
    from phi.models import DeidConfig

    text = "Contact smith@hospital.org (MRN 12345) regarding Jane Doe."
    # Rules-only config keeps the test fast (no 560MB spaCy model load).
    result = redact_for_cloud(text, DeidConfig(use_rules=True, use_ner=False, use_llm=False))
    assert "smith@hospital.org" not in result.redacted_text
    assert "12345" not in result.redacted_text
    assert result.spans
    # The canonical (input) text is untouched — redaction is on the copy only.
    assert "smith@hospital.org" in text


def test_default_deid_config_is_mask_no_llm() -> None:
    cfg = default_config()
    assert cfg.strategy == "mask"  # no PHI_HASH_KEY needed
    assert cfg.use_llm is False  # §11 — S2's cloud LLM pass stays off


class _FakeLLM:
    """Stand-in for clinical_core.llm.LLMClient.complete."""

    def __init__(self, letter: str) -> None:
        self._letter = letter
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, schema: type[ReferralLetter]) -> ReferralLetter:
        self.calls.append((system, user))
        return ReferralLetter(letter=self._letter)


def test_generate_referral_uses_llm_client() -> None:
    fake = _FakeLLM("Dear Cardiology,\n\nPlease review this patient.\n\nDr. Test")
    letter = generate_referral(
        note_text="ASSESSMENT:\n- Type 2 diabetes mellitus.",
        patient_context="Jane Doe, 46F, T2DM on metformin.",
        llm=fake,
    )
    assert letter.startswith("Dear Cardiology")
    assert len(fake.calls) == 1
    system, user = fake.calls[0]
    assert "referral" in system.lower()
    assert "Type 2 diabetes" in user
    assert "Jane Doe" in user


# --- §8.4: CodeSuggestion -> FHIR R4 Condition/Claim (Phase 4) ---------------


def _suggestions() -> list[dict]:
    return [
        {
            "code": "E11.9",
            "description": "Type 2 diabetes mellitus without complications",
            "confidence": 0.92,
            "evidence": {"quote": "Type 2 diabetes", "start": 0, "end": 15},
            "rank": 1,
        },
        {
            "code": "E66.9",
            "description": "Obesity, unspecified",
            "confidence": 0.71,
            "evidence": {"quote": "BMI 31", "start": 0, "end": 6},
            "rank": 2,
        },
    ]


def test_codes_to_conditions_validates_as_r4() -> None:
    from clin_core_glue.fhir_codes import codes_to_conditions
    from fhir.resources.R4B.condition import Condition as R4Condition

    conds = codes_to_conditions(
        _suggestions(), patient_ref="patient-1", encounter_ref="enc-1"
    )
    assert len(conds) == 2
    # Each dict is a valid R4B Condition (construction re-validates) and
    # carries the FHIR resourceType key.
    for c in conds:
        assert c["resourceType"] == "Condition"
        cond = R4Condition(**c)
        assert cond.subject.reference == "Patient/patient-1"
        assert cond.encounter.reference == "Encounter/enc-1"
        assert cond.clinicalStatus.coding[0].code == "active"
    # ICD-10-CM system + codes preserved, display carried from description.
    codes = {R4Condition(**c).code.coding[0].code for c in conds}
    assert codes == {"E11.9", "E66.9"}
    e11 = R4Condition(**conds[0])
    assert e11.code.coding[0].system == "http://hl7.org/fhir/sid/icd-10-cm"
    assert e11.code.coding[0].display == "Type 2 diabetes mellitus without complications"
    # Stable, slug-based ids (no dots/spaces — FHIR id rules).
    assert all(c["id"].replace("-", "").isalnum() for c in conds)


def test_codes_to_conditions_accepts_pydantic_objects() -> None:
    from auto_medical_coder import CodeSuggestion, EvidenceSpan
    from clin_core_glue.fhir_codes import codes_to_conditions

    objs = [
        CodeSuggestion(
            code="J45.909",
            description="Asthma, unspecified",
            confidence=0.8,
            evidence=EvidenceSpan(quote="asthma", start=0, end=6),
            rank=1,
        )
    ]
    conds = codes_to_conditions(objs, patient_ref="p2")
    assert len(conds) == 1
    assert conds[0]["code"]["coding"][0]["code"] == "J45.909"
    # No encounter_ref -> no encounter reference on the Condition.
    assert "encounter" not in conds[0]


def test_codes_to_conditions_skips_empty_codes() -> None:
    from clin_core_glue.fhir_codes import codes_to_conditions

    bad = [{"code": "", "description": "x"}, {"code": "E11.9", "description": "T2DM"}]
    conds = codes_to_conditions(bad, patient_ref="p1")  # type: ignore[arg-type]
    assert len(conds) == 1
    assert conds[0]["code"]["coding"][0]["code"] == "E11.9"


def test_codes_to_claim_validates_and_requires_billing_context() -> None:
    from clin_core_glue.fhir_codes import codes_to_claim
    from fhir.resources.R4B.claim import Claim as R4Claim

    claim = codes_to_claim(
        _suggestions(),
        patient_ref="patient-1",
        provider_ref="Organization/acme-clinic",
        coverage_ref="Coverage/cov-1",
        encounter_ref="enc-1",
    )
    parsed = R4Claim(**claim)
    assert claim["resourceType"] == "Claim"
    assert parsed.status == "active"
    assert parsed.use == "claim"
    assert parsed.patient.reference == "Patient/patient-1"
    assert parsed.provider.reference == "Organization/acme-clinic"
    assert parsed.insurance[0].focal is True
    assert parsed.insurance[0].coverage.reference == "Coverage/cov-1"
    # One diagnosis entry per Condition, sequenced.
    assert len(parsed.diagnosis) == 2
    assert [d.sequence for d in parsed.diagnosis] == [1, 2]
    refs = {d.diagnosisReference.reference for d in parsed.diagnosis}
    assert refs == {"Condition/cond-enc-1-e11-9", "Condition/cond-enc-1-e66-9"}

    # No suggestions -> explicit error (don't fabricate an empty Claim).
    with pytest.raises(ValueError):
        codes_to_claim(
            [], patient_ref="p1", provider_ref="o", coverage_ref="c"  # type: ignore[list-item]
        )
