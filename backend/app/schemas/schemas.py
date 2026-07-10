# =============================================================================
# schemas.py — Pydantic models that define the shape of API request/response data.
#
# WHY DO WE NEED SCHEMAS WHEN WE ALREADY HAVE ORM MODELS?
# ORM models (models.py) describe the database structure.
# Schemas describe the JSON structure the API sends and receives.
#
# They're intentionally separate because:
#   - The DB might have columns you don't want to expose (passwords, internal IDs)
#   - The API might accept fields that aren't DB columns (computed values,
#     convenience fields)
#   - Input validation lives here — Pydantic rejects bad data before it even
#     reaches your route handler
#
# When a POST request arrives with a JSON body, FastAPI automatically:
#   1. Parses the JSON
#   2. Validates it against the schema (wrong type → 422 error automatically)
#   3. Passes a typed Python object to your function
#
# Data Science parallel: think of schemas as type annotations + validation
# for your API's inputs and outputs, similar to how you'd validate a
# DataFrame's columns and types before processing it.
# =============================================================================

from pydantic import BaseModel, field_validator
from typing import Optional, List


# =============================================================================
# USER SCHEMAS
# =============================================================================

class UserLogin(BaseModel):
    """
    What the frontend sends when a user tries to log in.
    Only field: their chosen name (no password — this app is name-only auth).
    """
    name: str


class UserOut(BaseModel):
    """
    What the server sends back after a successful login.
    The frontend stores this object in localStorage and uses "id" for all
    subsequent API calls to identify who is making the request.

    model_config = {"from_attributes": True} tells Pydantic it can convert
    a SQLAlchemy ORM object (User from models.py) directly into this schema.
    Without it, Pydantic would refuse because ORM objects aren't plain dicts.
    """
    id: str
    name: str
    model_config = {"from_attributes": True}


# =============================================================================
# TASK SCHEMAS
# =============================================================================

class TaskCreate(BaseModel):
    """
    Validated shape of the JSON body when creating a new task.
    Fields with defaults are optional — the frontend can omit them.

    created_at is sent as a "YYYY-MM-DD" string from the frontend rather than
    letting the server use today's date. This matters for one-time tasks:
    the user might be adding a task that starts in the future.
    """
    name: str
    category: str = "misc"          # work | personal | health | study | misc
    task_type: str = "one-time"     # "one-time" | "repetitive"
    created_at: str                 # "YYYY-MM-DD" — which day this task belongs to
    from_date: Optional[str] = None # visible from this date (one-time tasks)
    to_date:   Optional[str] = None # visible until this date (one-time tasks)


class TaskUpdate(BaseModel):
    """
    Partial update schema — every field is Optional because a PATCH request
    should only update the fields that were actually sent.

    We use model_fields_set in the route handler to know which fields the
    frontend actually included (vs. which ones are just None because they
    weren't mentioned). This prevents accidentally overwriting fields with
    None when the frontend only wanted to update one specific thing.
    """
    name:      Optional[str]  = None
    category:  Optional[str]  = None
    task_type: Optional[str]  = None
    completed: Optional[bool] = None
    from_date: Optional[str]  = None
    to_date:   Optional[str]  = None


class CompletionOut(BaseModel):
    """
    A single completion record sent back to the frontend.
    Contains the date it happened and the progress percentage.
    """
    date:     str
    progress: str = "100"   # "0"–"100" as a string to stay consistent with how
                             # the frontend handles it (avoids int/string confusion in JS)
    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    """
    The full task object sent back to the frontend — used for both the
    task list and the calendar. Includes the list of all completion records
    so the frontend can render checkboxes and streaks without additional calls.
    """
    id:        str
    name:      str
    category:  str
    task_type: str
    completed: bool
    created_at: str
    from_date:  Optional[str] = None
    to_date:    Optional[str] = None
    completions: List[CompletionOut] = []  # empty list if never completed
    model_config = {"from_attributes": True}


# =============================================================================
# CALENDAR SCHEMAS
# =============================================================================

class RecordProgress(BaseModel):
    """
    Sent when the user clicks a checkbox on the calendar or sets a progress
    percentage for a one-time task.

    progress is Optional:
      - None (not sent)  → binary toggle for repetitive tasks
      - 0–100            → set exact progress for one-time tasks
    """
    date:     str              # "YYYY-MM-DD" — which calendar day was ticked
    progress: Optional[int] = None


# =============================================================================
# EXPLORE / AI COACH SCHEMAS
# =============================================================================

class ChatMessage(BaseModel):
    """One message in the conversation history."""
    role:    str   # "user" or "assistant"
    content: str


class ExploreRequest(BaseModel):
    """
    Sent to the /explore/chat endpoint.

    We send the full conversation history (messages) so the AI can
    maintain context across multiple turns in a session.

    task_summary is a plain-text description of the user's current tasks,
    injected into the AI's system prompt so it can give context-aware advice
    (e.g., "I see you have Guitar Practice due — want help scheduling it?").
    """
    user_id:      str
    messages:     List[ChatMessage]
    task_summary: Optional[str] = ""
