import asyncio, tempfile, uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.models import ChatRequest, NoteCreate, NoteUpdate, ReminderCreate, ReminderUpdate, VariantSelect
from app.core.runner import create_and_run, TASKS, select_variant
from app.core.database import get_task, list_tasks
from app.tools.productivity import (
    list_notes, list_reminders, create_note, get_note, update_note, delete_note,
    create_reminder, update_reminder, delete_reminder,
)
from app.services.agent import agent
from app.tools.attachments import extract_text
from app.tools.files import read_document_text, write_document_text
from app.tools.knowledge import looks_factual, wikipedia_summary
from app.core.variants import stream_variants
from app.config import AI_MODEL, AI_PROVIDER, WHISPER_MODEL

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

@router.get("/sampling-presets")
async def sampling_presets():
    # Surfaced so the UI can show what each strategy means without hardcoding the
    # explanatory text twice (here and in the frontend).
    return agent.SAMPLING_PRESETS

COMPARE_JOBS = {}

@router.post("/compare")
async def compare_sampling(request: ChatRequest):
    # A dedicated endpoint, not a `general` action in the task-routing pipeline: a user
    # reaching for this is explicitly asking to see how temperature/top-p change the
    # output, not asking AETHER to take some action; it would be wrong to let the
    # classifier ever route an ordinary message here instead of to a real action.
    #
    # Starts the 6 strategies as a background job instead of blocking the request: the
    # Playground polls GET /api/compare/{job_id} the same way task polling already
    # works elsewhere, so cards appear as each strategy finishes (fastest first)
    # instead of the whole page waiting for the slowest one (usually beam search's
    # local decode loop) before showing anything at all.
    message = request.message.strip()
    history = [{"role": h.role, "content": h.content} for h in request.history]
    context = None
    if looks_factual(message):
        context = await asyncio.to_thread(wikipedia_summary, message)
    job_id = str(uuid.uuid4())
    job = {"status": "running", "message": message, "context": context, "variants": []}
    COMPARE_JOBS[job_id] = job

    async def on_variant(variant):
        job["variants"].append(variant)

    async def run():
        await stream_variants(message, history, context, is_document=False, on_variant=on_variant)
        job["status"] = "done"

    asyncio.create_task(run())
    return {"job_id": job_id, "message": message, "context": context, "variants": []}

@router.get("/compare/{job_id}")
async def compare_status(job_id: str):
    job = COMPARE_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Comparison job not found.")
    return job

@router.post("/tasks/{task_id}/select")
async def pick_task_variant(task_id: str, body: VariantSelect):
    try:
        return await select_variant(task_id, body.variant_key, body.candidate_index)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
    return {"api_online":available,"configured_model":AI_MODEL,"provider":AI_PROVIDER,
            "models":models,"inference":f"cloud ({AI_PROVIDER})","speech_model":WHISPER_MODEL}

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
