import asyncio, tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.models import ChatRequest, NoteCreate, NoteUpdate, ReminderCreate, ReminderUpdate
from app.core.runner import create_and_run, TASKS
from app.core.database import get_task, list_tasks
from app.tools.productivity import (
    list_notes, list_reminders, create_note, get_note, update_note, delete_note,
    create_reminder, update_reminder, delete_reminder,
)
from app.services.agent import agent
from app.tools.attachments import extract_text
from app.tools.files import read_document_text, write_document_text
from app.config import OLLAMA_MODEL, WHISPER_MODEL

router = APIRouter(prefix="/api")
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

_whisper_model = None

def get_whisper_model():
    # Cached across requests; GPU (CUDA/cuBLAS) builds often aren't installed, so this
    # loads on CPU, which works everywhere without extra driver setup.
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper_model

@router.post("/tasks")
async def create_task(request: ChatRequest):
    history = [{"role": h.role, "content": h.content} for h in request.history]
    attachments = [{"name": a.name, "text": a.text} for a in request.attachments]
    return await create_and_run(request.message.strip(), history, attachments)

@router.post("/attachments")
async def upload_attachment(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (8 MB limit).")
    try:
        text, truncated = extract_text(file.filename or "file", data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"name": file.filename or "file", "text": text, "truncated": truncated}

@router.get("/tasks/{task_id}")
async def task_status(task_id: str):
    task = TASKS.get(task_id) or get_task(task_id)
    if not task: raise HTTPException(status_code=404, detail="Task not found.")
    return task

@router.get("/tasks")
async def recent_tasks():
    return list_tasks()

@router.get("/notes")
async def notes():
    return list_notes()

@router.post("/notes")
async def new_note(body: NoteCreate):
    return create_note(body.content, body.title)

@router.get("/notes/{name}")
async def read_note(name: str):
    try:
        return get_note(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Note not found.")

@router.put("/notes/{name}")
async def edit_note(name: str, body: NoteUpdate):
    try:
        return update_note(name, body.content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Note not found.")

@router.delete("/notes/{name}")
async def remove_note(name: str):
    try:
        delete_note(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Note not found.")
    return {"deleted": name}

@router.get("/reminders")
async def reminders():
    return list_reminders()

@router.post("/reminders")
async def new_reminder(body: ReminderCreate):
    try:
        return create_reminder(body.message, body.minutes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.patch("/reminders/{reminder_id}")
async def edit_reminder(reminder_id: str, body: ReminderUpdate):
    try:
        return update_reminder(reminder_id, **body.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.delete("/reminders/{reminder_id}")
async def remove_reminder(reminder_id: str):
    try:
        delete_reminder(reminder_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"deleted": reminder_id}

@router.get("/documents/{name}")
async def read_document(name: str):
    try:
        return {"name": name, "text": read_document_text(name)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.put("/documents/{name}")
async def edit_document(name: str, body: NoteUpdate):
    try:
        return write_document_text(name, body.content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.get("/status")
async def local_status():
    available = agent.is_available()
    models = agent.list_models() if available else []
    return {"ollama_online":available,"configured_model":OLLAMA_MODEL,
            "model_installed":OLLAMA_MODEL in models,"models":models,
            "inference":"local","speech_model":WHISPER_MODEL}

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise HTTPException(status_code=503, detail="Install faster-whisper to enable local speech recognition.")
    suffix = Path(file.filename or "recording.webm").suffix or ".webm"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read()); temp_path = tmp.name
        model = await asyncio.to_thread(get_whisper_model)
        segments, _ = await asyncio.to_thread(lambda: model.transcribe(temp_path, beam_size=3, vad_filter=True))
        segments = list(segments)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return {"text":text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Local transcription failed: {exc}")
    finally:
        if temp_path and Path(temp_path).exists():
            Path(temp_path).unlink(missing_ok=True)
