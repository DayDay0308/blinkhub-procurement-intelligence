from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import Token, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(func.lower(User.email) == form.username.lower()))
    # Same message for unknown email and wrong password: don't reveal which accounts exist.
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise Unauthorized("Incorrect email or password.")
    return Token(
        access_token=create_access_token(user.id, user.role),
        expires_in=get_settings().access_token_minutes * 60,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
