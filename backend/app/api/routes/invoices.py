from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.errors import NotFound
from app.db.session import get_db
from app.models import Invoice, User
from app.schemas import (
    Decision,
    InvoiceOut,
    InvoiceSubmit,
    LinkPo,
    Page,
    PaymentOut,
    Rejection,
    TimelineEvent,
)
from app.services import workflow
from app.services.invoices import to_out

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _scoped(user: User):
    """Row-level security in the API: a supplier only ever sees its own invoices."""
    stmt = select(Invoice)
    if user.role == "SUPPLIER":
        stmt = stmt.where(Invoice.supplier_id == user.supplier_id)
    return stmt


def _load(db: Session, user: User, invoice_id: UUID, lock: bool = False) -> Invoice:
    stmt = _scoped(user).where(Invoice.id == invoice_id)
    if lock:  # row lock: two people can't approve or pay the same invoice at once
        stmt = stmt.with_for_update(of=Invoice)
    inv = db.scalars(stmt).unique().first()
    if inv is None:
        # 404 rather than 403 for other suppliers' invoices: don't confirm they exist.
        raise NotFound("Invoice not found.")
    return inv


@router.get("", response_model=Page[InvoiceOut])
def list_invoices(
    status: str | None = None,
    supplier_id: UUID | None = None,
    overdue: bool | None = Query(default=None, description="Only invoices past payment terms"),
    assigned_to_me: bool = Query(default=False, description="Only invoices I must act on"),
    sort: Literal["days_desc", "amount_desc", "received_desc"] = "days_desc",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = _scoped(user)
    if status:
        stmt = stmt.where(Invoice.status == status.upper())
    if supplier_id:
        stmt = stmt.where(Invoice.supplier_id == supplier_id)
    if assigned_to_me:
        stmt = stmt.where(Invoice.current_approver_id == user.id)
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


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def submit_invoice(
    data: InvoiceSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("SUPPLIER", "FINANCE_OFFICER", "ADMIN")),
):
    """Suppliers submit through the portal; Finance captures emailed invoices (channel MANUAL).
    The invoice is 3-way matched immediately and routed to an approver or to an exception."""
    inv = workflow.submit_invoice(db, user, **data.model_dump())
    return to_out(inv)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return to_out(_load(db, user, invoice_id))


@router.post("/{invoice_id}/link-po", response_model=InvoiceOut)
def link_po(
    invoice_id: UUID,
    data: LinkPo,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("FINANCE_OFFICER", "PROCUREMENT_OFFICER", "ADMIN")),
):
    """Attach the missing PO reference to an invoice, then re-run the 3-way match."""
    inv = _load(db, user, invoice_id, lock=True)
    return to_out(workflow.link_purchase_order(db, user, inv, data.po_number))


@router.post("/{invoice_id}/approve", response_model=InvoiceOut)
def approve(
    invoice_id: UUID,
    data: Decision,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("APPROVER", "FINANCE_OFFICER", "MANAGER")),
):
    inv = _load(db, user, invoice_id, lock=True)
    return to_out(workflow.approve_invoice(db, user, inv, data.comment))


@router.post("/{invoice_id}/reject", response_model=InvoiceOut)
def reject(
    invoice_id: UUID,
    data: Rejection,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("APPROVER", "FINANCE_OFFICER", "MANAGER")),
):
    inv = _load(db, user, invoice_id, lock=True)
    return to_out(workflow.reject_invoice(db, user, inv, data.reason))


@router.post("/{invoice_id}/pay", response_model=PaymentOut)
def pay(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("FINANCE_OFFICER")),
):
    inv = _load(db, user, invoice_id, lock=True)
    return workflow.pay_invoice(db, user, inv)


@router.get("/{invoice_id}/timeline", response_model=list[TimelineEvent])
def timeline(invoice_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """'Where is my payment?': every step this invoice has been through, from the audit log.
    Shows roles, not names, so suppliers see progress without staff personal details."""
    _load(db, user, invoice_id)
    rows = db.execute(
        text(
            "SELECT e.occurred_at, e.action, u.role::text AS role, "
            "e.after_state->>'status' AS status, "
            "coalesce(e.after_state->>'reason', e.after_state->>'comment', "
            "         e.after_state->>'reference') AS note "
            "FROM audit.events e LEFT JOIN core.users u ON u.id = e.actor_id "
            "WHERE e.entity_type = 'INVOICE' AND e.entity_id = :id ORDER BY e.id"
        ),
        {"id": invoice_id},
    )
    return [
        TimelineEvent(at=r.occurred_at, action=r.action, by_role=r.role, status=r.status, note=r.note)
        for r in rows
    ]
