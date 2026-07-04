from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.routes import users, tasks, explore

load_dotenv()

app = FastAPI(
    title="FocusFlow API",
    description="ADHD Task Manager backend",
    version="1.0.0",
)

# ——— CORS ———
# During development: allow all. In production: set FRONTEND_URL in .env
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


@app.get("/")
def health():
    return {"status": "ok", "app": "FocusFlow API"}
