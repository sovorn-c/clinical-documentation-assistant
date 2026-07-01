"""PHI de-identification boundary helper (execute-plan §8 point 1).

Wraps S2's ``phi.deidentify.deidentify()`` to produce the redacted copy of
transcript/note text that crosses the trust boundary into cloud-LLM calls
(suggest-codes, generate-referral). The clinician-facing canonical copy
stored in the DB and shown in the UI stays UN-redacted — a clinician needs
real identifiers to chart correctly. The audit log records each de-id event.

Implementation lands in Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from phi.models import DeidConfig, DeidResult


def redact_for_cloud(text: str, config: DeidConfig | None = None) -> DeidResult:
    """Run S2 de-identification on ``text`` for outbound cloud-LLM use."""
    raise NotImplementedError("Phase 2 — §8 point 1: de-id boundary helper")
