"""Seed synthetic demo data (Phase 5).

Idempotent: safe to run repeatedly. Creates the demo clinician (if no users
exist) and a demo patient wired to the bundled R4 fixture bundle, so the demo
is login-able and has a patient to start an encounter from without any live
engine calls.

Run against the configured DB (SQLite dev or Postgres prod — tables must exist,
i.e. ``alembic upgrade head`` for Postgres or ``init_db`` for SQLite):

    python -m clin_doc.seed

Synthetic data only (§11) — never real PHI.
"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from clin_doc.auth import seed_user
from clin_doc.db.audit import AuditMeta
from clin_doc.db.enums import AuditAction, AuditActor
from clin_doc.db.models import Patient
from clin_doc.db.repositories import PatientRepo
from clin_doc.db.session import get_engine, init_db
from clin_doc.settings import get_settings

# Bundled R4 fixture (Phase 0) — ships in the image so the demo patient always
# has FHIR context for the summarize endpoint.
_FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "r4_patient_bundle.json"


def seed(force_tables: bool = False) -> None:
    s = get_settings()
    if s.database_url.startswith("sqlite") or force_tables:
        init_db()
    with Session(get_engine()) as session:
        user = seed_user(session)
        if user is not None:
            print(f"seeded demo clinician: {user.username}")
        else:
            print("demo clinician already present")

        existing = session.exec(select(Patient).where(Patient.patient_ref == "patient-1")).first()
        if existing is not None:
            print(f"demo patient already present: {existing.display_name}")
            return
        patient = PatientRepo(session).upsert(
            patient_ref="patient-1",
            display_name="Jane Doe (synthetic)",
            fhir_bundle_path=str(_FIXTURE),
            audit=AuditMeta(
                actor=AuditActor.SYSTEM,
                action=AuditAction.CREATE_PATIENT,
                actor_name="seed",
            ),
        )
        session.commit()
        print(f"seeded demo patient: {patient.display_name} ({patient.id})")


if __name__ == "__main__":  # pragma: no cover
    seed()
