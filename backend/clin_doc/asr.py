"""Cloud ASR adapter — faster-whisper (Phase 0 Decision B, executed in Phase 5).

M1's ``MlxWhisperTranscriber`` is Apple-Silicon-only (``mlx-whisper``). For the
cross-platform cloud demo we swap to ``faster-whisper`` (CTranslate2, CPU-friendly,
same Whisper weights) — implemented here as a B1 adapter conforming to M1's
``Transcriber`` ABC, **not** a rewrite of M1. ``deps.get_scribe`` injects this
into the ``Scribe`` graph directly when ``ASR_BACKEND=faster_whisper`` (see
docs/ARCHITECTURE.md §7); the local Apple-Silicon dev path still uses M1's
``build_scribe`` factory (mlx-whisper).

The output mapping mirrors ``MlxWhisperTranscriber`` exactly (``TranscriptSeg``
+ ``WordTiming`` with ``TimeSpan``), so the downstream ``DialogueExtractor`` and
note generator see the same shapes regardless of which transcriber ran.
"""

from __future__ import annotations

from typing import Any

from scribe.dialogue.transcriber.base import Transcriber
from scribe.domain.types import Audio, TimeSpan, TranscriptSeg, WordTiming


class FasterWhisperTranscriber(Transcriber):
    """Real ASR adapter backed by faster-whisper (CTranslate2, CPU/cross-platform).

    The heavy ``faster_whisper`` import + model load are deferred to
    ``transcribe`` (mirroring M1's mlx-whisper adapter) so the module imports
    and the app starts without the optional dep installed; tests fake it.
    """

    def __init__(
        self,
        cfg: Any | None = None,
        model_id: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self.cfg = cfg or {}
        if isinstance(self.cfg, dict):
            self.model_id = self.cfg.get("model_id", model_id)
            self.device = self.cfg.get("device", device)
            self.compute_type = self.cfg.get("compute_type", compute_type)
        else:
            self.model_id = model_id
            self.device = device
            self.compute_type = compute_type

    @property
    def identifier(self) -> str:
        return f"faster-whisper:{self.model_id}"

    def transcribe(self, audio: Audio) -> list[TranscriptSeg]:
        if audio.path is None:
            raise ValueError("FasterWhisperTranscriber requires audio.path")
        try:
            from faster_whisper import WhisperModel  # local import — optional dep
        except ImportError as e:  # pragma: no cover — needs faster-whisper installed
            raise RuntimeError(
                "faster-whisper is not installed. Install with: pip install faster-whisper"
            ) from e

        model = WhisperModel(self.model_id, device=self.device, compute_type=self.compute_type)
        segments_iter, _info = model.transcribe(audio.path, word_timestamps=True)

        out: list[TranscriptSeg] = []
        for seg in segments_iter:
            word_timings = [
                WordTiming(
                    word=w.word.strip(),
                    time_span=TimeSpan(start=float(w.start), end=float(w.end)),
                )
                for w in (seg.words or [])
            ]
            out.append(
                TranscriptSeg(
                    text=seg.text.strip(),
                    time_span=TimeSpan(start=float(seg.start), end=float(seg.end)),
                    word_timings=word_timings,
                )
            )
        return out
