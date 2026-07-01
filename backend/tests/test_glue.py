"""Tests for the §8 glue modules implemented in Phase 2.

soap_text — SOAPNote -> flat text (§8.2)
deid      — de-id boundary helper wrapping S2 (§8.1)
referral  — net-new referral letter via LLMClient (§8.3), with a fake LLM
"""

from __future__ import annotations

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
