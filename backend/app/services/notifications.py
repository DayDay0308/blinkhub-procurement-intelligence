from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Notification, User


def notify(
    db: Session,
    user_ids: Iterable[UUID],
    kind: str,
    entity_type: str,
    entity_id: UUID,
    title: str,
    body: str | None = None,
) -> int:
    """Create one notification per user. Idempotent: the same (user, kind, entity) is never
    created twice, so scheduled jobs can re-run safely."""
    rows = [
        {
            "user_id": uid,
            "kind": kind,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": title,
            "body": body,
        }
        for uid in set(user_ids)
    ]
    if not rows:
        return 0
    stmt = (
        insert(Notification)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["user_id", "kind", "entity_id"])
        .returning(Notification.id)
    )
    return len(db.execute(stmt).all())


def users_with_role(db: Session, *roles: str) -> list[UUID]:
    return list(db.scalars(select(User.id).where(User.role.in_(roles), User.is_active)))


def supplier_users(db: Session, supplier_id: UUID) -> list[UUID]:
    return list(db.scalars(select(User.id).where(User.supplier_id == supplier_id, User.is_active)))
