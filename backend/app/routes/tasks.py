from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
import uuid

from app.db.database import get_db
from app.models.models import Task, Completion, User
from app.schemas.schemas import TaskCreate, TaskUpdate, TaskOut, RecordProgress

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_user_or_404(user_id: str, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def serialize_task(task, completions=None):
    if completions is None:
        completions = task.completions
    return TaskOut(
        id=task.id,
        name=task.name,
        category=task.category,
        task_type=task.task_type,
        completed=task.completed,
        created_at=str(task.created_at),
        completions=[{"date": c.date, "progress": c.progress or "100"} for c in completions],
    )


# ——— LIST ———
@router.get("/{user_id}", response_model=List[TaskOut])
def get_tasks(user_id: str, db: Session = Depends(get_db)):
    get_user_or_404(user_id, db)
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id)
        .options(joinedload(Task.completions))
        .order_by(Task.created_at.desc())
        .all()
    )
    return [serialize_task(t) for t in tasks]


# ——— CREATE ———
@router.post("/{user_id}", response_model=TaskOut)
def create_task(user_id: str, payload: TaskCreate, db: Session = Depends(get_db)):
    get_user_or_404(user_id, db)
    task = Task(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=payload.name.strip(),
        category=payload.category,
        task_type=payload.task_type,
        completed=False,
        created_at=payload.created_at,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return serialize_task(task, completions=[])


# ——— UPDATE ———
@router.patch("/{user_id}/{task_id}", response_model=TaskOut)
def update_task(user_id: str, task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.name is not None:      task.name      = payload.name.strip()
    if payload.category is not None:  task.category  = payload.category
    if payload.task_type is not None: task.task_type = payload.task_type
    if payload.completed is not None: task.completed = payload.completed
    db.commit()
    db.refresh(task)
    completions = db.query(Completion).filter(Completion.task_id == task.id).all()
    return serialize_task(task, completions)


# ——— DELETE ———
@router.delete("/{user_id}/{task_id}")
def delete_task(user_id: str, task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}


# ——— RECORD PROGRESS / TOGGLE ———
@router.post("/{user_id}/{task_id}/toggle", response_model=TaskOut)
def record_progress(user_id: str, task_id: str, payload: RecordProgress, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    existing = db.query(Completion).filter(
        Completion.task_id == task_id,
        Completion.date == payload.date
    ).first()

    if task.task_type == "repetitive":
        # Binary toggle — progress is always 100
        if existing:
            db.delete(existing)
        else:
            db.add(Completion(id=str(uuid.uuid4()), task_id=task_id,
                              date=payload.date, progress="100"))
        # task.completed is never touched by calendar for repetitive tasks

    else:
        # One-time task — record the percentage (0 = remove record)
        pct = payload.progress if payload.progress is not None else 100
        pct = max(0, min(100, pct))  # clamp 0–100

        if pct == 0:
            if existing:
                db.delete(existing)
        else:
            if existing:
                existing.progress = str(pct)
            else:
                db.add(Completion(id=str(uuid.uuid4()), task_id=task_id,
                                  date=payload.date, progress=str(pct)))

        db.flush()
        # Mark completed if any day has 100%; incomplete if no 100% records remain
        has_full = db.query(Completion).filter(
            Completion.task_id == task_id,
            Completion.progress == "100"
        ).count() > 0
        task.completed = has_full

    db.commit()
    db.refresh(task)
    completions = db.query(Completion).filter(Completion.task_id == task.id).all()
    return serialize_task(task, completions)
