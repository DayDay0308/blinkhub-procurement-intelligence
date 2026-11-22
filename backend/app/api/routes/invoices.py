from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import NotFound
from app.db.session import get_db
from app.models import Invoice, User
from app.schemas import InvoiceOut, Page
from app.services.invoices import to_out

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _scoped(user: User):
    """Row-level security in the API: a supplier only ever sees its own invoices."""
    stmt = select(Invoice)
    if user.role == "SUPPLIER":
        stmt = stmt.where(Invoice.supplier_id == user.supplier_id)
    return stmt


@router.get("", response_model=Page[InvoiceOut])
def list_invoices(
    status: str | None = None,
    supplier_id: UUID | None = None,
    overdue: bool | None = Query(default=None, description="Only invoices past payment terms"),
    sort: Literal["days_desc", "amount_desc", "received_desc"] = "days_desc",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = _scoped(user)
    if status:
        stmt = stmt.where(Invoice.status == status.upper())
    if supplier_id:
        stmt = stmt.where(Invoice.supplier_id == supplier_id)
    now = datetime.now(UTC)
    items = [to_out(inv, now) for inv in db.scalars(stmt).unique()]
    if overdue is not None:
        items = [i for i in items if (i.sla_state == "BREACHED") == overdue]
    key = {
        "days_desc": lambda i: -i.days_outstanding,
        "amount_desc": lambda i: -i.amount,
        "received_desc": lambda i: -i.received_at.timestamp(),
    }[sort]
    items.sort(key=key)
    return Page(items=items, total=len(items))


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    inv = db.scalars(_scoped(user).where(Invoice.id == invoice_id)).unique().first()
    if inv is None:
        # 404 rather than 403 for other suppliers' invoices: don't confirm they exist.
        raise NotFound("Invoice not found.")
    return to_out(inv)
