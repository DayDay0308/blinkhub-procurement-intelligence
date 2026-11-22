from collections.abc import Callable
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

INTERNAL_ROLES = (
    "ADMIN",
    "PROCUREMENT_OFFICER",
    "FINANCE_OFFICER",
    "APPROVER",
    "MANAGER",
    "AUDITOR",
)


def get_current_user(token: str | None = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    if not token:
        raise Unauthorized("Not signed in.")
    try:
        claims = decode_access_token(token)
        user = db.get(User, UUID(claims["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise Unauthorized("Session is invalid or has expired.") from exc
    if user is None or not user.is_active:
        raise Unauthorized("Account is not active.")
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    """Route guard: `user = Depends(require_roles("FINANCE_OFFICER", "ADMIN"))`."""

    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise Forbidden(f"Role {user.role} cannot perform this action.")
        return user

    return guard


internal_only = require_roles(*INTERNAL_ROLES)
