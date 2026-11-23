"""Write to the append-only, hash-chained audit log (audit.events)."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def record(
    db: Session,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.execute(
        text(
            "INSERT INTO audit.events (actor_id, action, entity_type, entity_id, "
            "before_state, after_state) "
            "VALUES (:actor, :action, :etype, :eid, CAST(:before AS jsonb), CAST(:after AS jsonb))"
        ),
        {
            "actor": actor_id,
            "action": action,
            "etype": entity_type,
            "eid": entity_id,
            "before": json.dumps(before, default=str) if before is not None else None,
            "after": json.dumps(after, default=str) if after is not None else None,
        },
    )
