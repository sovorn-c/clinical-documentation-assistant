"""FastAPI dependencies: DB session, current user, and the injectable engines.

The engine providers (``get_scribe``, ``get_coder``, ``get_llm_client``,
``get_summarizer``, ``get_deidentify``) return the real upstream callables in
production. They import lazily so the app starts without models/keys present,
and so API tests can override them with fakes via ``app.dependency_overrides``
to exercise the full flow without mlx-whisper/ollama/catalogue/cloud-LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Protocol, TypeVar

from fastapi import Depends

from clin_doc.auth import CurrentUser
from clin_doc.db.session import DbSession
from clin_doc.services import PipelineService

__all__ = [
    "CurrentUser",
    "DbSession",
    "ScribeDep",
    "CoderDep",
    "LLMClientDep",
    "SummarizerDep",
    "DeidentifyDep",
    "PipelineDep",
    "get_pipeline_service",
    "get_scribe",
    "get_coder",
    "get_llm_client",
    "get_summarizer",
    "get_deidentify",
]

T = TypeVar("T", bound=object)


# --- engine protocols / callables -------------------------------------------


class ScribeLike(Protocol):
    def generateDraft(self, audio: object, ctx: object) -> object: ...
    def approveAndExport(self, edited: object, approver: object) -> object: ...


# A coder takes note text and returns a list[CodeSuggestion]-shaped objects.
CoderFn = Callable[[str], list[object]]
# A summarizer takes a PatientRecord and returns a Summary-shaped object.
SummarizerFn = Callable[[object], object]
# A de-identifier takes text and returns a DeidResult-shaped object.
DeidentifyFn = Callable[[str], object]


def get_scribe() -> ScribeLike:
    """Real M1 Scribe graph.

    ASR backend is chosen by ``ASR_BACKEND`` (Phase 0 Decision B, executed in
    Phase 5):

    - ``mlx_whisper`` (default; local Apple-Silicon dev): M1's ``build_scribe``
      factory, which imports ``MlxWhisperTranscriber`` at call time.
    - ``faster_whisper`` (cloud/demo): B1 constructs the ``Scribe`` graph
      directly with ``FasterWhisperTranscriber`` injected at the transcriber
      seam, reusing M1's other per-seam factories for the note generator
      (ollama), diarizer, draft store, and FHIR exporter. This is adapter-level
      wiring in B1 — M1's ``build_scribe`` is not edited.

    Both paths need their runtime (mlx-whisper/ollama, or faster-whisper/ollama)
    present; the app starts regardless (imports are lazy). Tests override this dep.
    """
    from clin_doc.settings import get_settings

    backend = get_settings().asr_backend.lower()
    cfg = {
        "audio_source": "file",
        "audio_path": "",
        "transcriber": {},
        "diarizer": {},
        "llm": {},
        "draft_store": "memory",
    }

    if backend == "faster_whisper":
        # Construct the graph directly with B1's transcriber injected; reuse
        # M1's factories for every other seam (composition.py call sequence).
        from scribe.app.drafts import InMemoryDraftStore
        from scribe.app.scribe import Scribe
        from scribe.composition import (
            _build_diarizer,
            _build_fhir_exporter,
            _build_model_host,
            _build_note_generator,
        )
        from scribe.dialogue import DialogueExtractor

        from clin_doc.asr import FasterWhisperTranscriber

        scribe = Scribe(
            dialogue_extractor=DialogueExtractor(
                transcriber=FasterWhisperTranscriber(cfg.get("transcriber", {})),
                diarizer=_build_diarizer(cfg),
            ),
            note_generator=_build_note_generator(cfg),
            fhir_exporter=_build_fhir_exporter(cfg),
            draft_store=InMemoryDraftStore(),
            model_host=_build_model_host(cfg),
        )
        return scribe  # type: ignore[return-value]

    # Local Apple-Silicon dev path: M1's factory (mlx-whisper).
    from scribe.composition import build_scribe

    return build_scribe(cfg)  # type: ignore[return-value]


def get_coder() -> CoderFn:
    """Real S3 ``code`` (needs the built catalogue/index + API key)."""
    from auto_medical_coder import code

    return code


def get_llm_client() -> object:
    """Real ``clinical_core.llm.LLMClient`` (needs API_KEY)."""
    from clinical_core.llm.client import LLMClient

    return LLMClient()


def get_summarizer() -> SummarizerFn:
    """Real S1 ``summarize`` (needs API_KEY)."""
    from summarizer.pipeline import summarize

    return summarize


def get_deidentify() -> DeidentifyFn:
    """S2 de-id boundary helper (local; no API key needed)."""
    from clin_core_glue.deid import redact_for_cloud

    return redact_for_cloud


ScribeDep = Annotated[ScribeLike, Depends(get_scribe)]
CoderDep = Annotated[CoderFn, Depends(get_coder)]
LLMClientDep = Annotated[object, Depends(get_llm_client)]
SummarizerDep = Annotated[SummarizerFn, Depends(get_summarizer)]
DeidentifyDep = Annotated[DeidentifyFn, Depends(get_deidentify)]


def get_pipeline_service(
    session: DbSession,
    actor: CurrentUser,
    scribe: ScribeDep,
    coder: CoderDep,
    llm_client: LLMClientDep,
    summarizer: SummarizerDep,
    deidentify: DeidentifyDep,
) -> PipelineService:
    return PipelineService(
        session=session,
        actor=actor,
        scribe=scribe,
        coder=coder,
        llm_client=llm_client,
        summarizer=summarizer,
        deidentify=deidentify,
    )


PipelineDep = Annotated[PipelineService, Depends(get_pipeline_service)]
