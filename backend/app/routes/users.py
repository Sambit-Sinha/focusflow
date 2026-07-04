from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User
from app.schemas.schemas import UserLogin, UserOut
import uuid

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/login", response_model=UserOut)
def login_or_register(payload: UserLogin, db: Session = Depends(get_db)):
    """
    If a user with this name exists, return them.
    If not, create a new user. Name is the only identifier.
    """
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    user = db.query(User).filter(User.name == name).first()
    if not user:
        user = User(id=str(uuid.uuid4()), name=name)
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
