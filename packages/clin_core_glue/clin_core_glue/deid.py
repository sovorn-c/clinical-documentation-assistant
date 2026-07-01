"""PHI de-identification boundary helper (execute-plan §8 point 1).

Wraps S2's ``phi.deidentify.deidentify()`` to produce the redacted copy of
transcript/note text that crosses the trust boundary into cloud-LLM calls
(suggest-codes, generate-referral). The clinician-facing canonical copy stored
in the DB and shown in the UI stays UN-redacted — a clinician needs real
identifiers to chart correctly. The audit log records each de-id event with
the privacy-safe counts from ``DeidResult.audit`` (never the PHI value).

Default config: ``mask`` strategy (no key needed), rules + NER on, LLM off
(§11 — leave S2's optional cloud LLM pass off). NER is local (spaCy) and the
Presidio analyzer is ``lru_cache``d in S2, so it's a one-time model load.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from phi.models import DeidConfig, DeidResult


def default_config() -> DeidConfig:
    from phi.models import DeidConfig

    return DeidConfig(strategy="mask", use_rules=True, use_ner=True, use_llm=False)


def redact_for_cloud(text: str, config: DeidConfig | None = None) -> DeidResult:
    """Run S2 de-identification on ``text`` for outbound cloud-LLM use."""
    from phi.deidentify import deidentify

    return deidentify(text, config or default_config())
