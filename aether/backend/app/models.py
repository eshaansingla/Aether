from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Literal, Optional

class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)

class AttachmentIn(BaseModel):
    name: str = Field(max_length=200)
    text: str = Field(max_length=20000)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list)
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=6)

class TaskStep(BaseModel):
    name: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    detail: str = ""

class NoteCreate(BaseModel):
    title: str = Field(default="Untitled note", max_length=70)
    content: str = Field(default="", max_length=50000)

class NoteUpdate(BaseModel):
    content: str = Field(max_length=50000)

class ReminderCreate(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    minutes: int = Field(ge=1, le=60 * 24 * 30)

class ReminderUpdate(BaseModel):
    message: Optional[str] = Field(default=None, min_length=1, max_length=500)
    minutes: Optional[int] = Field(default=None, ge=1, le=60 * 24 * 30)
    status: Optional[Literal["scheduled", "due", "done"]] = None

class TaskView(BaseModel):
    task_id: str
    instruction: str
    status: str
    message: str
    steps: list[TaskStep] = []
    output_path: Optional[str] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
