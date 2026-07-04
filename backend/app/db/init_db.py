"""
Run this once to create all tables in your Supabase database:
    python -m app.db.init_db
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.db.database import engine, Base
from app.models.models import User, Task, Completion  # noqa: F401 — imported for side effects


def init_db():
    print("Creating tables in Supabase...")
    Base.metadata.create_all(bind=engine)
    print("Done! Tables created: users, tasks, completions")


if __name__ == "__main__":
    init_db()
