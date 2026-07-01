"""Append-only audit log writer.

Every state-changing repository call accepts an ``AuditMeta`` and writes one
``AuditLog`` row in the same session/transaction — so "every state change is
audited" is structural, not a discipline the caller has to remember.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlmodel import Session

from clin_doc.db.enums import ArtifactType, AuditAction, AuditActor
from clin_doc.db.models import AuditLog


class AuditMeta(BaseModel):
    """Everything needed for one audit row."""

    actor: AuditActor
    actor_name: str | None = None
    action: AuditAction
    artifact_type: ArtifactType | None = None
    artifact_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


def write_audit(session: Session, encounter_id: str | None, am: AuditMeta) -> AuditLog:
    row = AuditLog(
        encounter_id=encounter_id,
        actor=am.actor.value,
        actor_name=am.actor_name,
        action=am.action.value,
        artifact_type=am.artifact_type.value if am.artifact_type else None,
        artifact_id=am.artifact_id,
        before=am.before,
        after=am.after,
        meta=am.meta,
    )
    session.add(row)
    session.flush()
    return row
