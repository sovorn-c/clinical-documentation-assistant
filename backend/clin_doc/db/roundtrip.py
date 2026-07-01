"""Lossless round-trip helpers for the upstream Pydantic types (§7).

Upstream models carry ``model_dump``/``model_validate``, so the mapping is
thin — these helpers centralize it and import the engines lazily so the DB
layer imports without pulling torch/chroma/spacy. Dumps use ``mode="json"``
so datetimes (e.g. ``Provenance.created_at``) become ISO strings that
``model_validate`` parses back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from auto_medical_coder import CodeSuggestion
    from phi.models import DeidResult
    from scribe.domain.types import Dialogue, DocumentRef, Provenance, SOAPNote
    from summarizer.models import Summary


def dump(obj: Any) -> dict[str, Any]:
    return obj.model_dump(mode="json")


# --- M1 ---
def soap_to_dict(note: SOAPNote) -> dict[str, Any]:
    return dump(note)


def soap_from_dict(d: dict[str, Any]) -> SOAPNote:
    from scribe.domain.types import SOAPNote

    return SOAPNote.model_validate(d)


def dialogue_to_dict(dialogue: Dialogue) -> dict[str, Any]:
    return dump(dialogue)


def dialogue_from_dict(d: dict[str, Any]) -> Dialogue:
    from scribe.domain.types import Dialogue

    return Dialogue.model_validate(d)


def provenance_to_dict(p: Provenance) -> dict[str, Any]:
    return dump(p)


def provenance_from_dict(d: dict[str, Any]) -> Provenance:
    from scribe.domain.types import Provenance

    return Provenance.model_validate(d)


def documentref_to_dict(doc: DocumentRef) -> dict[str, Any]:
    return {"resource": doc.resource, "json_text": doc.json_text}


def documentref_from_dict(d: dict[str, Any]) -> DocumentRef:
    from scribe.domain.types import DocumentRef

    return DocumentRef.model_validate(d)


# --- S2 ---
def deid_to_dict(result: DeidResult) -> dict[str, Any]:
    return dump(result)


def deid_from_dict(d: dict[str, Any]) -> DeidResult:
    from phi.models import DeidResult

    return DeidResult.model_validate(d)


# --- S3 ---
def suggestion_to_dict(s: CodeSuggestion) -> dict[str, Any]:
    return dump(s)


def suggestion_from_dict(d: dict[str, Any]) -> CodeSuggestion:
    from auto_medical_coder import CodeSuggestion

    return CodeSuggestion.model_validate(d)


# --- S1 ---
def summary_to_dict(summary: Summary) -> dict[str, Any]:
    return dump(summary)


def summary_from_dict(d: dict[str, Any]) -> Summary:
    from summarizer.models import Summary

    return Summary.model_validate(d)


def flatten_dialogue(dialogue: Dialogue) -> str:
    """Flatten a Dialogue into 'ROLE: text' lines for display / de-id input."""
    lines = [f"{u.role.value}: {u.text}" for u in dialogue.utterances]
    return "\n".join(lines)
