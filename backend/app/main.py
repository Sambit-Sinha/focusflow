from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.routes import users, tasks, explore, music
from app.db.database import engine
from sqlalchemy import text as sa_text

load_dotenv()


def run_migrations():
    stmts = [
        # existing
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS from_date VARCHAR(10)",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS to_date VARCHAR(10)",
        # music graph tables
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
        """CREATE TABLE IF NOT EXISTS artist_similarity (
            artist_a_id VARCHAR REFERENCES music_artists(id) ON DELETE CASCADE,
            artist_b_id VARCHAR REFERENCES music_artists(id) ON DELETE CASCADE,
            score       FLOAT DEFAULT 0.0,
            PRIMARY KEY (artist_a_id, artist_b_id)
        )""",
    ]
    with engine.connect() as conn:
        for stmt in stmts:
            conn.execute(sa_text(stmt))
        conn.commit()

    # seed artists + similarity (idempotent)
    from app.db.database import SessionLocal
    from app.services.music_service import ensure_seed_artists
    db = SessionLocal()
    try:
        ensure_seed_artists(db)
    finally:
        db.close()


app = FastAPI(
    title="Un Poco Loco API",
    description="ADHD Task Manager backend",
    version="1.0.0",
)

# ——— CORS ———
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if FRONTEND_URL == "*" else [FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ——— ROUTES ———
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(explore.router)
app.include_router(music.router)


run_migrations()


@app.get("/")
def health():
    return {"status": "ok", "app": "Un Poco Loco API"}
