"""Encounter endpoints: create, upload audio, generate note, edit note, transcript."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from clin_doc.auth import get_current_user
from clin_doc.db.models import Encounter, Note, Transcript
from clin_doc.db.repositories import NoteRepo, TranscriptRepo
from clin_doc.db.session import DbSession
from clin_doc.deps import PipelineDep
from clin_doc.schemas import EncounterCreate, EncounterOut, NoteEdit, NoteOut

router = APIRouter(
    prefix="/encounters", tags=["encounters"], dependencies=[Depends(get_current_user)]
)


@router.post("", response_model=EncounterOut, status_code=201)
def create_encounter(body: EncounterCreate, svc: PipelineDep) -> Encounter:
    return svc.create_encounter(
        patient_id=body.patient_id,
        encounter_ref=body.encounter_ref,
        audio_path=body.audio_path,
    )


@router.get("/{encounter_id}", response_model=EncounterOut)
def get_encounter(encounter_id: str, session: DbSession) -> Encounter:
    enc = session.get(Encounter, encounter_id)
    if enc is None:
        raise HTTPException(status_code=404, detail="encounter not found")
    return enc


@router.post("/{encounter_id}/audio", response_model=EncounterOut)
async def upload_audio(encounter_id: str, file: UploadFile, svc: PipelineDep) -> Encounter:
    """Accept a multipart audio upload, persist it, and set encounter.audio_path."""
    try:
        data = await file.read()
        return svc.upload_audio(encounter_id, data, file.filename or "audio.wav")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"audio upload failed: {e}") from e


@router.post("/{encounter_id}/generate-note", response_model=NoteOut)
def generate_note(encounter_id: str, svc: PipelineDep) -> Note:
    try:
        return svc.generate_note(encounter_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"note generation unavailable: {e}") from e


@router.put("/{encounter_id}/note", response_model=NoteOut)
def edit_note(encounter_id: str, body: NoteEdit, svc: PipelineDep) -> Note:
    try:
        return svc.edit_note(encounter_id, body.note)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{encounter_id}/note", response_model=NoteOut)
def get_latest_note(encounter_id: str, session: DbSession) -> Note:
    note = NoteRepo(session).get_latest(encounter_id)
    if note is None:
        raise HTTPException(status_code=404, detail="no note for encounter")
    return note


@router.get("/{encounter_id}/notes", response_model=list[NoteOut])
def get_note_versions(encounter_id: str, session: DbSession) -> list[Note]:
    """All note versions (AI draft + human edits) for the AI-vs-human diff."""
    return NoteRepo(session).get_versions(encounter_id)


@router.get("/{encounter_id}/transcript", response_model=Transcript)
def get_transcript(encounter_id: str, session: DbSession) -> Transcript:
    t = TranscriptRepo(session).get_by_encounter(encounter_id)
    if t is None:
        raise HTTPException(status_code=404, detail="no transcript for encounter")
    return t
