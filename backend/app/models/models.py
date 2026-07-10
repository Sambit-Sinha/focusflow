# =============================================================================
# models.py — Defines the database tables as Python classes (SQLAlchemy ORM).
#
# ORM stands for Object-Relational Mapper. The idea: instead of writing raw
# SQL strings everywhere, you define Python classes. Each class = one table.
# Each Column() = one column. SQLAlchemy translates between them.
#
# Data Science parallel: think of each class as defining the schema of a
# pandas DataFrame, but with enforced types, constraints, and relationships.
#
# The three tables here cover the core app:
#   User        → who is using the app
#   Task        → what they want to do
#   Completion  → evidence that they did it on a specific day
# =============================================================================

from sqlalchemy import Column, String, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.database import Base


def gen_uuid():
    """
    Generates a random UUID string like "f47ac10b-58cc-4372-a567-0e02b2c3d479".

    We use UUIDs instead of auto-incrementing integers (1, 2, 3...) as primary
    keys for two reasons:
    1. IDs can be generated in Python before the row is written to the DB,
       which simplifies some operations.
    2. They don't leak information — sequential IDs reveal how many records
       exist (user id=5 tells you there are only 5 users).
    """
    return str(uuid.uuid4())


class User(Base):
    """
    Represents one person using the app.

    Login is name-only — no password. If you type "Sambit" and a user named
    "Sambit" exists, you get that user. If not, a new user is created.
    Simple, low-friction, suitable for a personal productivity app.
    """
    __tablename__ = "users"

    id         = Column(String, primary_key=True, default=gen_uuid)
    name       = Column(String(100), unique=True, nullable=False, index=True)
    # server_default=func.now() means the database sets this value automatically
    # at insert time. We don't need to pass it from Python.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # relationship() defines a Python-level link, not a new DB column.
    # "back_populates" keeps both sides in sync: user.tasks gives you all tasks;
    # task.user gives you the parent user.
    # cascade="all, delete-orphan" means: when a User is deleted, all their
    # Tasks are automatically deleted too (no orphaned rows left behind).
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")


class Task(Base):
    """
    Represents one thing a user wants to track — either a one-time goal
    or a daily habit.

    task_type controls how the calendar renders this task:
      "repetitive" → shows every day from created_at onwards (habit tracking)
      "one-time"   → shows only within [from_date, to_date] and disappears
                     once it reaches 100% progress on any single day
    """
    __tablename__ = "tasks"

    id       = Column(String, primary_key=True, default=gen_uuid)

    # ForeignKey("users.id") creates the link to the users table.
    # ondelete="CASCADE" tells PostgreSQL: when the parent user row is deleted,
    # automatically delete all their task rows too. Matches the Python-level
    # cascade on the User relationship above — both need to agree.
    user_id  = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name     = Column(String(500), nullable=False)
    category = Column(String(50), nullable=False, default="misc")
    completed = Column(Boolean, default=False)

    # "one-time" | "repetitive" — stored as a string rather than a boolean
    # because it's more readable in the DB and leaves room to add more types later.
    task_type  = Column(String(20), nullable=False, default="one-time")

    # Date (not DateTime) — stored as YYYY-MM-DD with no time component.
    # This is intentional: we don't care what time of day the task was created,
    # only which calendar day it belongs to.
    created_at = Column(Date, nullable=False)

    # Visible date range for one-time tasks. NULL for repetitive tasks.
    from_date  = Column(String(10), nullable=True)   # "YYYY-MM-DD" or None
    to_date    = Column(String(10), nullable=True)   # "YYYY-MM-DD" or None

    user        = relationship("User", back_populates="tasks")
    completions = relationship("Completion", back_populates="task", cascade="all, delete-orphan")


class Completion(Base):
    """
    Records that a specific task was worked on (or completed) on a specific day.

    Instead of a single "completed" boolean on Task, we store one Completion
    row per day. This enables streak tracking, calendar view (which days were
    tasks done?), and partial progress for one-time tasks.

    Example: "Guitar Practice" completed on 2026-07-01, 2026-07-03, 2026-07-07
    would be 3 Completion rows, not 3 updates to the task row.
    """
    __tablename__ = "completions"

    id      = Column(String, primary_key=True, default=gen_uuid)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)

    # Date stored as a plain string "YYYY-MM-DD". Using String instead of Date
    # avoids timezone conversion issues — the frontend sends a string and we
    # store exactly that string, no parsing ambiguity.
    date    = Column(String(10), nullable=False)

    # Progress as a string "0"–"100".
    # Repetitive tasks: always "100" (done or not done — no in-between).
    # One-time tasks: can be any value 0–100 (e.g., "60" = 60% done today).
    # Stored as String to keep the JSON responses consistent (no int/string
    # type mismatch between Python and JavaScript).
    progress = Column(String(3), nullable=False, default="100")

    task = relationship("Task", back_populates="completions")
