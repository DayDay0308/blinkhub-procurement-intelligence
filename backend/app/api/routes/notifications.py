from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.errors import NotFound
from app.db.session import get_db
from app.models import Notification, User
from app.schemas import NotificationOut, Page
from app.services.sla import run_sla_check

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=Page[NotificationOut])
def my_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(100)).all()
    return Page(items=[NotificationOut.model_validate(n) for n in items], total=len(items))


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise NotFound("Notification not found.")
    n.read_at = n.read_at or datetime.now(UTC)
    return n


@router.post("/jobs/sla-check", tags=["jobs"])
def trigger_sla_check(db: Session = Depends(get_db), _: User = Depends(require_roles("MANAGER", "ADMIN"))):
    """Run the payment-SLA check now (it also runs on a schedule in the worker)."""
    return run_sla_check(db)
