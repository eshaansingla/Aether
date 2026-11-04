import asyncio, tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from app.models import ChatRequest
from app.core.runner import create_and_run, TASKS
from app.core.database import get_task, list_tasks
from app.tools.productivity import list_notes, list_reminders
from app.services.agent import agent
from app.config import OLLAMA_MODEL, WHISPER_MODEL

router = APIRouter(prefix="/api")

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
    return await create_and_run(request.message.strip(), history)

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

@router.get("/reminders")
async def reminders():
    return list_reminders()

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
