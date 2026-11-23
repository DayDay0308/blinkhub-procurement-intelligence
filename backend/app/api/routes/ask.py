from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import internal_only
from app.db.session import get_db
from app.models import User
from app.services import ai
from app.services import ask as ask_service

router = APIRouter(prefix="/ask", tags=["ask"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.get("/suggestions")
def get_suggestions(_: User = Depends(internal_only)):
    """Questions that always work, with or without an AI model."""
    return {"ai_enabled": ai.enabled(), "suggestions": ask_service.suggestions()}


@router.post("")
def ask(body: AskIn, db: Session = Depends(get_db), user: User = Depends(internal_only)):
    """Answer a question about the procurement data. Read-only; logged in the audit trail."""
    return ask_service.ask(db, user, body.question)
