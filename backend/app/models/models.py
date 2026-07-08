from sqlalchemy import Column, String, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    category = Column(String(50), nullable=False, default="misc")
    completed = Column(Boolean, default=False)
    task_type = Column(String(20), nullable=False, default="one-time")  # "one-time" | "repetitive"
    created_at = Column(Date, nullable=False)  # stored as YYYY-MM-DD
    from_date = Column(String(10), nullable=True)   # one-time tasks: start of visible range
    to_date   = Column(String(10), nullable=True)   # one-time tasks: end of visible range

    user = relationship("User", back_populates="tasks")
    completions = relationship("Completion", back_populates="task", cascade="all, delete-orphan")


class Completion(Base):
    """Records that a task was marked done on a specific calendar date."""
    __tablename__ = "completions"

    id = Column(String, primary_key=True, default=gen_uuid)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(String(10), nullable=False)  # "YYYY-MM-DD"
    progress = Column(String(3), nullable=False, default="100")  # "0"–"100"; repetitive always "100"

    task = relationship("Task", back_populates="completions")
