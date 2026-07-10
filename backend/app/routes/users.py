# =============================================================================
# routes/users.py — Handles everything to do with user accounts.
#
# Currently just one endpoint: /users/login
# This doubles as both login AND registration — no separate "sign up" step.
# If the name exists → log in. If not → create a new account automatically.
# This keeps friction low for a personal productivity app.
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User
from app.schemas.schemas import UserLogin, UserOut
import uuid

# APIRouter groups related endpoints together. The prefix="/users" means
# every route defined here is automatically prefixed — so @router.post("/login")
# becomes POST /users/login in the full API.
# tags=["users"] groups these endpoints together in the /docs page.
router = APIRouter(prefix="/users", tags=["users"])


@router.post("/login", response_model=UserOut)
def login_or_register(payload: UserLogin, db: Session = Depends(get_db)):
    """
    Find-or-create a user by name.

    Flow:
      1. Strip whitespace from the name (prevents " Sambit" and "Sambit"
         being treated as two different users)
      2. Query the DB for an existing user with that name
      3. If found → return them (login)
      4. If not found → create a new user and return them (registration)

    response_model=UserOut tells FastAPI to serialise the return value
    through the UserOut schema — only exposing id and name, not any
    internal fields that might be added to the User model later.

    HTTPException(status_code=400) sends a 400 Bad Request back to the
    browser with a JSON body {"detail": "Name cannot be empty"}.
    FastAPI handles the JSON formatting automatically.
    """
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    # db.query(User) builds a SELECT query on the users table.
    # .filter(User.name == name) adds WHERE name = 'Sambit'.
    # .first() executes it and returns the first result, or None if no match.
    user = db.query(User).filter(User.name == name).first()

    if not user:
        # New user — generate a UUID and insert a row.
        user = User(id=str(uuid.uuid4()), name=name)
        db.add(user)      # queue the INSERT (not written yet)
        db.commit()       # write to the database
        db.refresh(user)  # reload from DB to get server-generated fields (created_at)

    return user
