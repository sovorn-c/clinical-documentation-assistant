"""SOAPNote -> flat text adapter (execute-plan §8 point 2).

S3's ``auto_medical_coder.code()`` takes a flat string; M1's ``Draft.note`` is
a structured ``SOAPNote`` (four claim lists). This flattens the note into text
before coding, preserving section structure so the coder sees context.

Implementation lands in Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scribe.domain.types import SOAPNote


def flatten_soap(note: SOAPNote) -> str:
    """Return a flat-text rendering of ``note`` suitable for ``code()``."""
    raise NotImplementedError("Phase 2 — §8 point 2: SOAPNote -> text adapter")
