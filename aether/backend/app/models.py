from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Literal, Optional

class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list)

class TaskStep(BaseModel):
    name: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    detail: str = ""

class TaskView(BaseModel):
    task_id: str
    instruction: str
    status: str
    message: str
    steps: list[TaskStep] = []
    output_path: Optional[str] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
