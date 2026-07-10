# =============================================================================
# main.py — The entry point of the entire backend application.
#
# When Render runs "uvicorn app.main:app", it:
#   1. Imports this file
#   2. Finds the variable called "app" (the FastAPI instance below)
#   3. Starts a web server that listens for HTTP requests and routes them
#      to the right function based on the URL and HTTP method.
#
# Think of this file as the receptionist of the building — it doesn't do
# the actual work, but it knows which department (route file) handles what,
# and it sets up the rules everyone must follow (CORS, middleware).
# =============================================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.routes import users, tasks, explore, music
from app.db.database import engine
from sqlalchemy import text as sa_text

# load_dotenv() reads the .env file and injects its key=value pairs into
# os.environ. This is how DATABASE_URL, GEMINI_API_KEY, etc. become available.
# On Render in production, these are already in the environment (set in the
# dashboard), so load_dotenv() is a no-op there — harmless either way.
load_dotenv()


def run_migrations():
    """
    Safely applies database schema changes every time the server starts.

    WHY NOT JUST USE init_db.py FOR EVERYTHING?
    init_db.py runs once manually to create tables from scratch. But when you
    need to add a new column to a table that already has data in it (like when
    we added from_date and to_date to the tasks table after launch), you can't
    just drop and recreate the table — you'd lose everyone's data.

    Instead, ALTER TABLE ... ADD COLUMN IF NOT EXISTS adds the column only if
    it's missing. "IF NOT EXISTS" makes each statement safe to run on every
    server startup — it simply skips the change if it already happened.

    Think of it like: init_db builds the house, run_migrations adds rooms
    to the existing house without demolishing what's already there.
    """
    stmts = [
        # Add date range columns to tasks — used by one-time tasks to define
        # a visible window on the calendar (e.g., show this task from Jan 1 to Jan 15).
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS from_date VARCHAR(10)",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS to_date VARCHAR(10)",

        # Music knowledge graph tables. Created here (not in init_db) because
        # the music feature was added after the initial version launched.
        # JSONB is PostgreSQL's binary JSON column — lets us store lists like
        # ["Pop", "R&B"] without needing a separate genres table.
        """CREATE TABLE IF NOT EXISTS music_artists (
            id       VARCHAR PRIMARY KEY,
            name     VARCHAR(300) NOT NULL UNIQUE,
            genres   JSONB DEFAULT '[]',
            is_seed  VARCHAR(5) DEFAULT 'true'
        )""",
        """CREATE TABLE IF NOT EXISTS music_songs (
            id          VARCHAR PRIMARY KEY,
            name        VARCHAR(500) NOT NULL,
            artist_id   VARCHAR REFERENCES music_artists(id) ON DELETE SET NULL,
            artist_name VARCHAR(300) NOT NULL,
            year        INTEGER,
            genres      JSONB DEFAULT '[]',
            mbid        VARCHAR(50)
        )""",
        # PRIMARY KEY (user_id, artist_id) = composite key — enforces that
        # there is exactly ONE row per user-artist pair. When the user listens
        # again, we increment play_count rather than adding a new row.
        """CREATE TABLE IF NOT EXISTS user_artist_stats (
            user_id     VARCHAR REFERENCES users(id) ON DELETE CASCADE,
            artist_id   VARCHAR REFERENCES music_artists(id) ON DELETE CASCADE,
            play_count  INTEGER DEFAULT 1,
            last_played TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, artist_id)
        )""",
        """CREATE TABLE IF NOT EXISTS user_song_stats (
            user_id     VARCHAR REFERENCES users(id) ON DELETE CASCADE,
            song_id     VARCHAR REFERENCES music_songs(id) ON DELETE CASCADE,
            artist_id   VARCHAR REFERENCES music_artists(id) ON DELETE SET NULL,
            play_count  INTEGER DEFAULT 1,
            last_played TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, song_id)
        )""",
        # Pre-computed similarity scores between artists (0 = nothing in common,
        # 1 = identical). Stored so recommendations are just a fast lookup,
        # not a heavy calculation on every request.
        """CREATE TABLE IF NOT EXISTS artist_similarity (
            artist_a_id VARCHAR REFERENCES music_artists(id) ON DELETE CASCADE,
            artist_b_id VARCHAR REFERENCES music_artists(id) ON DELETE CASCADE,
            score       FLOAT DEFAULT 0.0,
            PRIMARY KEY (artist_a_id, artist_b_id)
        )""",
    ]

    # engine.connect() opens a raw database connection, bypassing SQLAlchemy's
    # ORM. Useful here because we're running raw SQL strings, not Python objects.
    with engine.connect() as conn:
        for stmt in stmts:
            conn.execute(sa_text(stmt))
        conn.commit()  # write all changes atomically in one transaction

    # Populate seed artists (famous musicians pre-loaded into the graph so new
    # users immediately get recommendations). ensure_seed_artists is idempotent
    # — if the artists already exist it skips them, so safe to call every time.
    from app.db.database import SessionLocal
    from app.services.music_service import ensure_seed_artists
    db = SessionLocal()
    try:
        ensure_seed_artists(db)
    finally:
        db.close()  # always release the DB connection, even if an error occurred


# =============================================================================
# The FastAPI app instance. uvicorn looks for a variable named "app" in the
# module specified in the start command (app.main:app → this file, this var).
# title and description appear on the auto-generated API docs at /docs.
# =============================================================================
app = FastAPI(
    title="Un Poco Loco API",
    description="ADHD Task Manager backend",
    version="1.0.0",
)

# =============================================================================
# CORS Middleware — Cross-Origin Resource Sharing.
#
# Browsers enforce a security rule: JavaScript running on domain A is NOT
# allowed to make HTTP requests to domain B unless domain B explicitly
# says "I allow requests from A." This is called the Same-Origin Policy.
#
# Example of the problem: our frontend is at un-poco-loco.netlify.app
# (domain A) and our backend is at focusflow-o1fz.onrender.com (domain B).
# Without CORS headers, the browser would silently block every API call.
#
# This middleware automatically adds the right "Access-Control-Allow-Origin"
# headers to every server response, telling the browser "yes, it's OK."
#
# allow_origins: who is allowed to make requests.
#   "*"  = everyone (convenient for local dev, risky in real production)
#   list = only these specific domains (what we use in production)
# =============================================================================
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if FRONTEND_URL == "*" else [FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],   # allow GET, POST, PATCH, DELETE, OPTIONS, etc.
    allow_headers=["*"],   # allow Content-Type, Authorization, etc.
)

# =============================================================================
# Route registration — connects URL prefixes to the handler files.
# FastAPI merges each router's routes into the main app.
#
# users.router   → /users/...    login / register
# tasks.router   → /tasks/...    create, read, update, delete tasks + progress
# explore.router → /explore/...  AI coach chat
# music.router   → /music/...    knowledge graph, recommendations, play logging
# =============================================================================
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(explore.router)
app.include_router(music.router)

# Run on every startup. All statements are idempotent (safe to re-run).
run_migrations()


@app.get("/")
def health():
    """
    Health check endpoint — the simplest possible test that the server is alive.

    Open https://focusflow-o1fz.onrender.com/ in your browser.
    If you see {"status": "ok"}, the server started successfully and is
    reachable from the internet. This is the first thing to check when
    something seems wrong — is the server even running?
    """
    return {"status": "ok", "app": "Un Poco Loco API"}
