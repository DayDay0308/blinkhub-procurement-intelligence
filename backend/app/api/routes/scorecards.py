from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, internal_only
from app.core.errors import Forbidden, NotFound
from app.db.session import get_db
from app.models import User
from app.services.scorecard import WEIGHTS, scorecards

router = APIRouter(tags=["supplier performance"])


@router.get("/scorecards")
def list_scorecards(
    supplier_type: Literal["SMME", "LARGE_ENTERPRISE"] | None = None,
    grade: Literal["A", "B", "C", "D", "E", "N/A"] | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(internal_only),
):
    """Supplier performance ranking, best first. Weights: delivery 30%, invoice accuracy 25%,
    compliance 20%, risk record 15%, price 10%. Suppliers with no activity are 'N/A'."""
    cards = scorecards(db)
    if supplier_type:
        cards = [c for c in cards if c["supplier"]["supplier_type"] == supplier_type]
    if grade:
        cards = [c for c in cards if c["grade"] == grade]
    return {"items": cards[offset : offset + limit], "total": len(cards), "weights": WEIGHTS}


@router.get("/suppliers/{supplier_id}/scorecard")
def supplier_scorecard(
    supplier_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Suppliers can see their own scorecard: knowing how they're measured helps them improve."""
    if user.role == "SUPPLIER" and user.supplier_id != supplier_id:
        raise Forbidden("Suppliers can only view their own scorecard.")
    cards = scorecards(db, supplier_id)
    if not cards:
        raise NotFound("No scorecard for this supplier (not active or not found).")
    return {**cards[0], "weights": WEIGHTS}
