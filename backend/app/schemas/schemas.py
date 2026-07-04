from pydantic import BaseModel, field_validator
from typing import Optional, List


# ——— USER ———

class UserLogin(BaseModel):
    name: str


class UserOut(BaseModel):
    id: str
    name: str
    model_config = {"from_attributes": True}


# ——— TASK ———

class TaskCreate(BaseModel):
    name: str
    category: str = "misc"
    task_type: str = "one-time"
    created_at: str


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    task_type: Optional[str] = None
    completed: Optional[bool] = None


class CompletionOut(BaseModel):
    date: str
    progress: str = "100"   # "0"–"100" as string to keep JSON consistent
    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: str
    name: str
    category: str
    task_type: str
    completed: bool
    created_at: str
    completions: List[CompletionOut] = []
    model_config = {"from_attributes": True}


# ——— CALENDAR ———

class RecordProgress(BaseModel):
    date: str                        # "YYYY-MM-DD"
    progress: Optional[int] = None   # None = binary toggle (repetitive); 0-100 for one-time


# ——— EXPLORE / AI ———

class ChatMessage(BaseModel):
    role: str
    content: str


class ExploreRequest(BaseModel):
    user_id: str
    messages: List[ChatMessage]
    task_summary: Optional[str] = ""
