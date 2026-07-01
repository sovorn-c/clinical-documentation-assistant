"""Referral letter generation (execute-plan §8 point 3).

Net-new LLM call: none of M1/S2/S3/S1 generate a referral letter. Built here
as its own call, reusing ``clinical_core.llm.LLMClient`` (from S1) for the
provider-agnostic wrapper rather than adding a fifth LLM-calling pattern to
the app. The ``llm`` is passed in so tests inject a fake and prod injects a
real ``LLMClient``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from clinical_core.llm.client import LLMClient


class ReferralLetter(BaseModel):
    """Structured output schema for the referral-letter LLM call."""

    letter: str = Field(description="A complete referral letter, ready to send.")


_SYSTEM = """\
You are a clinician writing a concise, professional referral letter from the
approved SOAP note and patient context provided. Address it to the relevant
specialist, summarise the reason for referral, relevant history, examination
findings, and the question you want answered. Use only the information given;
do not invent clinical details. Output the full letter text in the `letter`
field.
"""


def generate_referral(
    *,
    note_text: str,
    patient_context: str,
    llm: LLMClient,
) -> str:
    """Generate a referral letter from the approved note + patient context."""
    user = f"## Approved SOAP note\n{note_text}\n\n## Patient context\n{patient_context}"
    result = llm.complete(_SYSTEM, user, ReferralLetter)
    return result.letter
