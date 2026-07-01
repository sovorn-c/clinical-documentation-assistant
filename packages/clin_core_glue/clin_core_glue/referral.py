"""Referral letter generation (execute-plan §8 point 3).

Net-new LLM call: none of M1/S2/S3/S1 generate a referral letter. Built here
as its own call, reusing ``clinical_core.llm.LLMClient`` (from S1) for the
provider-agnostic wrapper rather than adding a fifth LLM-calling pattern to
the app.

Implementation lands in Phase 2.
"""

from __future__ import annotations


def generate_referral(*args: object, **kwargs: object) -> str:
    """Generate a referral letter from the approved note + patient context."""
    raise NotImplementedError("Phase 2 — §8 point 3: referral letter generation")
