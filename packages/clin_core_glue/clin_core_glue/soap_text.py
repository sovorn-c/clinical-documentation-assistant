"""SOAPNote -> flat text adapter (execute-plan §8 point 2).

S3's ``auto_medical_coder.code()`` takes a flat string; M1's ``Draft.note`` is
a structured ``SOAPNote`` (four claim lists). This flattens it into text before
coding, preserving section headers so the coder sees clinical context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scribe.domain.types import SOAPNote

_SECTION_ORDER = ("subjective", "objective", "assessment", "plan")


def flatten_soap(note: SOAPNote) -> str:
    """Render ``note`` as ``SECTION:\\n- claim`` text suitable for ``code()``."""
    lines: list[str] = []
    for section in _SECTION_ORDER:
        claims = getattr(note, section)
        if not claims:
            continue
        lines.append(f"{section.upper()}:")
        for claim in claims:
            lines.append(f"- {claim.text}")
    return "\n".join(lines).strip()
