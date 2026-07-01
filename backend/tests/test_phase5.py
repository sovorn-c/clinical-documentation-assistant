"""Phase 5 tests — faster-whisper ASR adapter + rate limiting.

The faster-whisper dep is optional (``[cloud]`` extra) and not installed in the
test env, so the adapter test injects a fake ``faster_whisper`` module via
``sys.modules`` and exercises the real output mapping (TranscriptSeg/WordTiming)
that the downstream DialogueExtractor depends on.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from clin_doc.asr import FasterWhisperTranscriber
from fastapi.testclient import TestClient
from scribe.domain.types import Audio, TimeSpan

# --- FasterWhisperTranscriber ------------------------------------------------


class _FakeWord:
    def __init__(self, word: str, start: float, end: float) -> None:
        self.word = word
        self.start = start
        self.end = end


class _FakeSeg:
    def __init__(self, text: str, start: float, end: float, words: list[_FakeWord]) -> None:
        self.text = text
        self.start = start
        self.end = end
        self.words = words


class _FakeWhisperModel:
    """Records construction args; returns canned segments from transcribe()."""

    last_init: dict[str, object] = {}

    def __init__(self, model_id: str, device: str, compute_type: str) -> None:
        self.model_id = model_id
        self.device = device
        self.compute_type = compute_type
        _FakeWhisperModel.last_init = {
            "model_id": model_id,
            "device": device,
            "compute_type": compute_type,
        }

    def transcribe(self, path: str, word_timestamps: bool = False):
        segs = [
            _FakeSeg(
                text=" Hello, what brings you in?",
                start=0.0,
                end=3.0,
                words=[_FakeWord(" Hello,", 0.0, 0.6), _FakeWord(" what", 0.6, 1.0)],
            ),
            _FakeSeg(
                text=" I've been thirsty and tired.",
                start=3.2,
                end=6.0,
                words=[_FakeWord(" I've", 3.2, 3.5)],
            ),
        ]
        info = types.SimpleNamespace(language="en")
        return iter(segs), info


@pytest.fixture
def fake_faster_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = _FakeWhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def test_faster_whisper_identifier() -> None:
    t = FasterWhisperTranscriber({"model_id": "large-v3-turbo", "device": "cpu"})
    assert t.identifier == "faster-whisper:large-v3-turbo"


def test_faster_whisper_transcribe_maps_to_transcript_segs(
    fake_faster_whisper: None, tmp_path: Path
) -> None:
    audio_file = tmp_path / "a.wav"
    audio_file.write_bytes(b"RIFF...")
    t = FasterWhisperTranscriber({"model_id": "base", "compute_type": "int8"})
    segs = t.transcribe(Audio(source="file", path=str(audio_file)))

    assert len(segs) == 2
    assert segs[0].text == "Hello, what brings you in?"  # stripped
    assert segs[0].time_span == TimeSpan(start=0.0, end=3.0)
    assert segs[0].word_timings[0].word == "Hello,"
    assert segs[0].word_timings[0].time_span == TimeSpan(start=0.0, end=0.6)
    assert segs[1].text == "I've been thirsty and tired."
    # Construction forwarded cfg through to WhisperModel.
    assert _FakeWhisperModel.last_init["compute_type"] == "int8"
    assert _FakeWhisperModel.last_init["model_id"] == "base"


def test_faster_whisper_requires_path(fake_faster_whisper: None) -> None:
    t = FasterWhisperTranscriber()
    with pytest.raises(ValueError, match="audio.path"):
        t.transcribe(Audio(source="file"))  # no path


def test_faster_whisper_conforms_to_transcriber_abc() -> None:
    from scribe.dialogue.transcriber.base import Transcriber

    assert isinstance(FasterWhisperTranscriber(), Transcriber)


# --- Rate limiting ------------------------------------------------------------


def _limited_app(per_minute: int) -> TestClient:
    """A minimal FastAPI app wrapped with RateLimitMiddleware (no global settings)."""
    from clin_doc.rate_limit import RateLimitMiddleware
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/whatever")
    def whatever() -> dict[str, str]:
        return {"ok": "true"}

    app.add_middleware(RateLimitMiddleware, per_minute=per_minute)
    return TestClient(app)


def test_rate_limit_returns_429_after_threshold() -> None:
    client = _limited_app(2)
    assert client.get("/health").status_code == 200  # exempt
    r1 = client.get("/api/whatever")
    r2 = client.get("/api/whatever")
    r3 = client.get("/api/whatever")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.headers.get("Retry-After") is not None
    assert r3.json()["detail"] == "rate limit exceeded"


def test_health_exempt_from_rate_limit() -> None:
    client = _limited_app(1)
    for _ in range(5):
        assert client.get("/health").status_code == 200  # never throttled


def test_maybe_add_rate_limit_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from clin_doc import rate_limit as rl
    from fastapi import FastAPI

    class _FakeSettings:
        rate_limit_enabled = False
        rate_limit_per_minute = 5

    monkeypatch.setattr(rl, "get_settings", lambda: _FakeSettings())
    app = FastAPI()
    rl.maybe_add_rate_limit(app)
    # When disabled, no RateLimitMiddleware is added.
    assert not any("RateLimit" in m.cls.__name__ for m in app.user_middleware)


def test_maybe_add_rate_limit_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from clin_doc import rate_limit as rl
    from fastapi import FastAPI

    class _FakeSettings:
        rate_limit_enabled = True
        rate_limit_per_minute = 10

    monkeypatch.setattr(rl, "get_settings", lambda: _FakeSettings())
    app = FastAPI()
    rl.maybe_add_rate_limit(app)
    assert any("RateLimit" in m.cls.__name__ for m in app.user_middleware)
