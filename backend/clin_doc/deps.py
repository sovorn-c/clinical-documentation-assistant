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
    """Real M1 Scribe (mlx-whisper + ollama by default; needs models running).

    Raises at call time if the ASR/note-LLM runtime isn't set up — the demo
    deployment (Phase 5) configures that, and tests override this dep.
    """
    from scribe.composition import build_scribe

    cfg = {
        "audio_source": "file",
        "audio_path": "",
        "transcriber": {},
        "diarizer": {},
        "llm": {},
        "draft_store": "memory",
    }
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
