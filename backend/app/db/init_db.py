# =============================================================================
# init_db.py — One-time script to create all database tables.
#
# Run this ONCE when connecting a brand-new database (e.g., after switching
# from Supabase to Neon). It reads the ORM model definitions and translates
# them into CREATE TABLE statements that PostgreSQL executes.
#
# How to run:
#   cd /Users/koushik/focusflow/backend
#   source venv/bin/activate
#   python -m app.db.init_db
#
# Safe to run again — create_all() uses CREATE TABLE IF NOT EXISTS internally,
# so existing tables and their data are never touched.
#
# After the initial setup, ongoing schema changes (adding new columns or
# tables) are handled by run_migrations() in main.py, because those need
# to modify existing tables without dropping them.
# =============================================================================

import sys
import os

# Add the project root to sys.path so Python can find the "app" package
# when this script is invoked directly with "python -m app.db.init_db".
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.db.database import engine, Base

# Importing the model classes registers them with Base's metadata.
# Even though we don't use User/Task/Completion directly below, the import
# is essential — SQLAlchemy only knows a table exists if its class has been
# imported at least once. Without this, create_all() would create zero tables.
# "# noqa: F401" tells the linter not to warn about "imported but unused".
from app.models.models import User, Task, Completion  # noqa: F401


def init_db():
    print("Creating tables in the database...")

    # create_all() inspects every class that inherits from Base,
    # builds the SQL for each table, and runs CREATE TABLE IF NOT EXISTS.
    # It resolves foreign key order automatically (users before tasks,
    # tasks before completions) so no manual ordering is needed.
    Base.metadata.create_all(bind=engine)

    print("Done! Tables created: users, tasks, completions")


if __name__ == "__main__":
    init_db()
