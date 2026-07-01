"""Shared fakes + fixtures for engine smoke tests and the data-layer suite.

The fakes exercise M1's real ``Scribe`` facade + ``DialogueExtractor`` without
mlx-whisper (Apple-Silicon ASR) or ollama (note LLM) — the smoke test's job is
to prove the public surface is importable and callable, not to run models.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from clin_doc.db.session import init_db
from scribe.dialogue.transcriber.base import Transcriber
from scribe.domain.types import (
    Audio,
    Claim,
    Dialogue,
    PatientContext,
    SOAPNote,
    TimeSpan,
    TranscriptSeg,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_session() -> Session:
    """A fresh in-memory SQLite session with all Phase 1 tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


class FakeTranscriber(Transcriber):
    """Returns canned transcript segments — no ASR runtime needed."""

    def transcribe(self, audio: Audio) -> list[TranscriptSeg]:
        return [
            TranscriptSeg(
                text="Hello, what brings you in today?",
                time_span=TimeSpan(start=0.0, end=3.0),
            ),
            TranscriptSeg(
                text="I've been feeling thirsty and tired.",
                time_span=TimeSpan(start=3.2, end=6.0),
            ),
        ]

    @property
    def identifier(self) -> str:
        return "fake"


class FakeNoteGenerator:
    """Duck-typed stand-in for ``scribe.notes.NoteGenerator``."""

    llm_id = "fake-llm"

    def generate(self, dialogue: Dialogue) -> SOAPNote:
        return SOAPNote(
            subjective=[Claim(text="Patient reports thirst and fatigue.")],
            objective=[],
            assessment=[Claim(text="Possible diabetes mellitus.")],
            plan=[Claim(text="Check fasting glucose.")],
        )


@pytest.fixture
def fake_transcriber() -> Transcriber:
    return FakeTranscriber()


@pytest.fixture
def fake_note_generator() -> FakeNoteGenerator:
    return FakeNoteGenerator()


@pytest.fixture
def patient_ctx() -> PatientContext:
    return PatientContext(
        patient_ref="patient-1",
        encounter_ref="enc-1",
        patient_display="Jane Doe",
    )


@pytest.fixture
def r4_bundle_path() -> Path:
    return FIXTURES / "r4_patient_bundle.json"
