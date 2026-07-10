# =============================================================================
# routes/tasks.py — All task and completion endpoints.
#
# URL pattern: /tasks/{user_id}/...
# Every endpoint verifies the user exists first (get_user_or_404).
# Every write operation also verifies the task belongs to that user
# (task.user_id == user_id check) to prevent user A from editing user B's tasks.
#
# Endpoints:
#   GET    /tasks/{user_id}                → list all tasks with completions
#   POST   /tasks/{user_id}                → create a new task
#   PATCH  /tasks/{user_id}/{task_id}      → update fields on a task
#   DELETE /tasks/{user_id}/{task_id}      → delete a task and its completions
#   POST   /tasks/{user_id}/{task_id}/toggle → record/remove a completion for one day
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
import uuid

from app.db.database import get_db
from app.models.models import Task, Completion, User
from app.schemas.schemas import TaskCreate, TaskUpdate, TaskOut, RecordProgress

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_user_or_404(user_id: str, db: Session):
    """
    Reusable guard: fetch the user or immediately return a 404 error.
    Called at the start of every endpoint to prevent requests for non-existent
    users from reaching the database logic below.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def serialize_task(task, completions=None):
    """
    Convert a SQLAlchemy Task object into a TaskOut schema object.

    We do this manually (rather than relying on from_attributes alone) because:
    1. created_at is a Python Date object — we need to convert it to a string
       "YYYY-MM-DD" for JSON serialisation.
    2. completions might be passed in separately (when we just did a query
       that fetched them explicitly) to avoid redundant DB calls.
    """
    if completions is None:
        completions = task.completions
    return TaskOut(
        id=task.id,
        name=task.name,
        category=task.category,
        task_type=task.task_type,
        completed=task.completed,
        created_at=str(task.created_at),      # Date → "YYYY-MM-DD" string
        from_date=task.from_date,
        to_date=task.to_date,
        completions=[{"date": c.date, "progress": c.progress or "100"} for c in completions],
    )


# ── LIST ──────────────────────────────────────────────────────────────────────

@router.get("/{user_id}", response_model=List[TaskOut])
def get_tasks(user_id: str, db: Session = Depends(get_db)):
    """
    Return all tasks for a user, each with their full completion history.

    joinedload(Task.completions) tells SQLAlchemy to fetch all completions
    in the SAME query using a JOIN, rather than issuing a separate SELECT
    for each task's completions. Without it, loading 20 tasks would fire
    20 extra queries (N+1 query problem — a classic ORM pitfall).

    Data Science parallel: this is like doing a merge() once instead of
    repeatedly filtering a DataFrame in a loop.
    """
    get_user_or_404(user_id, db)
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id)
        .options(joinedload(Task.completions))  # fetch completions in one JOIN
        .order_by(Task.created_at.desc())       # newest tasks first
        .all()
    )
    return [serialize_task(t) for t in tasks]


# ── CREATE ────────────────────────────────────────────────────────────────────

@router.post("/{user_id}", response_model=TaskOut)
def create_task(user_id: str, payload: TaskCreate, db: Session = Depends(get_db)):
    """
    Create a new task for the user.

    payload is already validated by Pydantic (TaskCreate schema) before
    this function is called — if the frontend sent a malformed body,
    FastAPI would have already returned a 422 error.
    """
    get_user_or_404(user_id, db)
    task = Task(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=payload.name.strip(),    # strip whitespace from task names
        category=payload.category,
        task_type=payload.task_type,
        completed=False,              # new tasks always start incomplete
        created_at=payload.created_at,
        from_date=payload.from_date,
        to_date=payload.to_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return serialize_task(task, completions=[])  # no completions yet on a new task


# ── UPDATE ────────────────────────────────────────────────────────────────────

@router.patch("/{user_id}/{task_id}", response_model=TaskOut)
def update_task(user_id: str, task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)):
    """
    Partially update a task (PATCH = only change what you send).

    model_fields_set is a Pydantic property that tells us which fields the
    frontend actually included in the request body. If the frontend sends
    {"name": "New Name"}, model_fields_set = {"name"} — we only update name
    and leave everything else untouched.

    Without this check, a frontend sending {"name": "X"} with TaskUpdate
    would set all other Optional fields to None, accidentally clearing them.
    """
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    sent = payload.model_fields_set  # set of field names that were actually sent
    if "name"      in sent: task.name      = payload.name.strip()
    if "category"  in sent: task.category  = payload.category
    if "task_type" in sent: task.task_type = payload.task_type
    if "completed" in sent: task.completed = payload.completed
    if "from_date" in sent: task.from_date = payload.from_date  # None = clear the field
    if "to_date"   in sent: task.to_date   = payload.to_date

    db.commit()
    db.refresh(task)
    # Fetch completions separately after the update so we return accurate data
    completions = db.query(Completion).filter(Completion.task_id == task.id).all()
    return serialize_task(task, completions)


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.delete("/{user_id}/{task_id}")
def delete_task(user_id: str, task_id: str, db: Session = Depends(get_db)):
    """
    Delete a task and all its completion records.

    The cascade="all, delete-orphan" on the Task.completions relationship
    (defined in models.py) means SQLAlchemy automatically deletes all
    related Completion rows when the Task is deleted — no manual cleanup needed.
    """
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}


# ── RECORD PROGRESS / TOGGLE ──────────────────────────────────────────────────

@router.post("/{user_id}/{task_id}/toggle", response_model=TaskOut)
def record_progress(user_id: str, task_id: str, payload: RecordProgress, db: Session = Depends(get_db)):
    """
    Record or remove a completion for a task on a specific calendar day.
    Behaviour differs by task type:

    REPETITIVE tasks (e.g., "Guitar Practice every day"):
      - Clicking the checkbox toggles it: if no Completion exists for today,
        create one (progress="100"). If one exists, delete it (un-check).
      - No partial progress — it's binary: done or not done.
      - task.completed is NOT updated here — for repetitive tasks, "completed"
        means "done today", which is shown per-day, not as a persistent flag.

    ONE-TIME tasks (e.g., "Write project proposal"):
      - Progress can be 0–100 (slider in the day modal).
      - Setting 0 removes the completion record (like un-checking).
      - Setting 1–100 creates or updates the record.
      - task.completed is set to True when ANY day reaches 100% progress,
        False if no days have 100%.
      - db.flush() sends pending changes to the DB within the transaction
        (making them visible to subsequent queries) without committing yet.
        We need this so the "has_full" query below sees the updated progress.
    """
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check if there's already a completion record for this task on this date
    existing = db.query(Completion).filter(
        Completion.task_id == task_id,
        Completion.date == payload.date
    ).first()

    if task.task_type == "repetitive":
        if existing:
            db.delete(existing)   # was checked → uncheck it
        else:
            db.add(Completion(id=str(uuid.uuid4()), task_id=task_id,
                              date=payload.date, progress="100"))

    else:
        # One-time task — handle partial progress
        pct = payload.progress if payload.progress is not None else 100
        pct = max(0, min(100, pct))  # clamp to valid range 0–100

        if pct == 0:
            if existing:
                db.delete(existing)   # zero progress = remove the record
        else:
            if existing:
                existing.progress = str(pct)   # update existing record
            else:
                db.add(Completion(id=str(uuid.uuid4()), task_id=task_id,
                                  date=payload.date, progress=str(pct)))

        db.flush()  # flush so the COUNT query below sees the latest progress

        # A one-time task is "completed" if any day has 100% progress
        has_full = db.query(Completion).filter(
            Completion.task_id == task_id,
            Completion.progress == "100"
        ).count() > 0
        task.completed = has_full

    db.commit()
    db.refresh(task)
    completions = db.query(Completion).filter(Completion.task_id == task.id).all()
    return serialize_task(task, completions)
