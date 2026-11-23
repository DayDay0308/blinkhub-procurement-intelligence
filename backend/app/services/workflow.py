"""Invoice workflow (case study Problem 4: "The invoice that never gets paid").

Lifecycle:
    SUBMITTED -> 3-way match -> EXCEPTION (with reasons) | PENDING_APPROVAL (routed to a named approver)
    PENDING_APPROVAL -> APPROVED (owner becomes Finance) | REJECTED (reason required)
    APPROVED -> PAID

Every transition writes to the tamper-evident audit log, which also powers the
supplier's "where is my payment?" timeline.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden
from app.models import (
    BankAccount,
    GoodsReceipt,
    Invoice,
    InvoiceApproval,
    Payment,
    PurchaseOrder,
    Supplier,
    User,
)
from app.services import audit
from app.services.notifications import notify, supplier_users, users_with_role


class Unprocessable(AppError):
    status_code = 422
    code = "BUSINESS_RULE"


OPEN_STATUSES = (
    "SUBMITTED",
    "MATCHING",
    "EXCEPTION",
    "PENDING_APPROVAL",
    "APPROVED",
    "SCHEDULED",
    "ON_HOLD",
)
RECEIVABLE_PO_STATUSES = ("APPROVED", "PARTIALLY_RECEIVED")
INVOICEABLE_PO_STATUSES = ("APPROVED", "PARTIALLY_RECEIVED", "RECEIVED")


def _tolerance() -> Decimal:
    return Decimal(1) + Decimal(str(get_settings().match_tolerance_pct)) / 100


def _sync(db: Session, inv: Invoice) -> None:
    """Flush and reload so relationships (e.g. the new owner) reflect the change."""
    db.flush()
    db.refresh(inv)


def _snapshot(inv: Invoice) -> dict:
    return {
        "status": inv.status,
        "exceptions": list(inv.match_exceptions or []),
        "approver": inv.current_approver_id,
    }


# --------------------------------------------------------------------------- matching
def evaluate_match(db: Session, inv: Invoice) -> list[str]:
    """3-way match: invoice vs purchase order vs goods received. Returns exception codes."""
    po = inv.purchase_order or (db.get(PurchaseOrder, inv.po_id) if inv.po_id else None)
    if po is None:
        return ["MISSING_PO_REFERENCE"]

    exceptions: list[str] = []
    if po.status not in INVOICEABLE_PO_STATUSES:
        exceptions.append("PO_NOT_APPROVED")

    tol = _tolerance()
    billed_other = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.po_id == po.id, Invoice.id != inv.id, Invoice.status != "REJECTED"
        )
    )
    billed = Decimal(billed_other) + inv.amount
    if billed > po.total_amount * tol:
        exceptions.append("AMOUNT_EXCEEDS_PO")

    received = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(GoodsReceipt.amount_received), 0)).where(
                GoodsReceipt.po_id == po.id
            )
        )
    )
    if received == 0:
        exceptions.append("AWAITING_GOODS_RECEIPT")
    elif billed > received * tol:
        exceptions.append("EXCEEDS_GOODS_RECEIVED")
    return exceptions


def route_approver(db: Session, inv: Invoice) -> User | None:
    """Pick one accountable approver:
    1. approvers/finance officers whose limit covers the amount,
    2. never the person who raised the PO (segregation of duties),
    3. prefer the PO's department, then the lowest sufficient limit,
    4. fall back to a manager."""
    po = inv.purchase_order or (db.get(PurchaseOrder, inv.po_id) if inv.po_id else None)
    excluded = {po.created_by} if po else set()
    candidates = [
        u
        for u in db.scalars(
            select(User).where(
                User.role.in_(("APPROVER", "FINANCE_OFFICER")),
                User.is_active,
                User.approval_limit >= inv.amount,
            )
        )
        if u.id not in excluded
    ]
    if candidates:
        dept = po.department_id if po else None
        candidates.sort(key=lambda u: (u.department_id != dept, u.approval_limit))
        return candidates[0]
    managers = [
        u
        for u in db.scalars(select(User).where(User.role == "MANAGER", User.is_active))
        if u.id not in excluded
    ]
    managers.sort(key=lambda u: -(u.approval_limit or 0))
    return managers[0] if managers else None


def apply_match(db: Session, inv: Invoice, actor_id: UUID | None) -> Invoice:
    before = _snapshot(inv)
    exceptions = evaluate_match(db, inv)
    inv.match_exceptions = exceptions
    if exceptions:
        inv.status = "EXCEPTION"
        # Exceptions are owned by Finance until resolved, so nothing is ever ownerless.
        if inv.current_approver_id is None:
            finance = users_with_role(db, "FINANCE_OFFICER")
            inv.current_approver_id = finance[0] if finance else None
    else:
        inv.status = "PENDING_APPROVAL"
        approver = route_approver(db, inv)
        inv.current_approver_id = approver.id if approver else None
        if approver:
            step = (db.scalar(select(func.count()).where(InvoiceApproval.invoice_id == inv.id)) or 0) + 1
            db.add(InvoiceApproval(invoice_id=inv.id, step=step, approver_id=approver.id))
            notify(
                db,
                [approver.id],
                "INVOICE_ASSIGNED",
                "INVOICE",
                inv.id,
                f"Invoice {inv.invoice_number} needs your approval",
                f"R{inv.amount:,.2f} from {inv.supplier.legal_name}",
            )
    _sync(db, inv)
    audit.record(db, actor_id, "INVOICE_MATCHED", "INVOICE", inv.id, before, _snapshot(inv))
    return inv


# --------------------------------------------------------------------------- commands
def submit_invoice(
    db: Session,
    user: User,
    *,
    invoice_number: str,
    amount: Decimal,
    invoice_date: date,
    po_number: str | None,
    vat_amount: Decimal,
    supplier_id: UUID | None,
) -> Invoice:
    if user.role == "SUPPLIER":
        supplier_id = user.supplier_id
        channel = "PORTAL"
    else:
        if supplier_id is None:
            raise Unprocessable("supplier_id is required when staff capture an invoice.")
        channel = "MANUAL"

    supplier = db.get(Supplier, supplier_id)
    if supplier is None or supplier.status != "ACTIVE":
        raise Unprocessable("Invoices can only be submitted for active suppliers.")
    if invoice_date > date.today():
        raise Unprocessable("Invoice date cannot be in the future.")
    if invoice_date < date.today() - timedelta(days=365):
        raise Unprocessable("Invoice is older than 12 months; submit it through Finance.")

    po = None
    if po_number:
        po = db.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.po_number == po_number.strip().upper(),
                PurchaseOrder.supplier_id == supplier_id,
            )
        )
        if po is None:  # same message whether the PO is missing or belongs to someone else
            raise Unprocessable(f"Purchase order {po_number} was not found for this supplier.")

    norm = "".join(ch for ch in invoice_number.upper() if ch.isalnum())
    existing = db.scalar(
        select(Invoice).where(Invoice.supplier_id == supplier_id, Invoice.invoice_number_norm == norm)
    )
    if existing:
        raise Conflict(
            f"Invoice {invoice_number} has already been submitted.",
            {"existing_invoice_id": str(existing.id), "status": existing.status},
        )

    now = datetime.now(UTC)
    inv = Invoice(
        supplier_id=supplier_id,
        po_id=po.id if po else None,
        invoice_number=invoice_number,
        amount=amount,
        vat_amount=vat_amount,
        invoice_date=invoice_date,
        received_at=now,
        due_date=(now + timedelta(days=get_settings().payment_terms_days)).date(),
        status="SUBMITTED",
        channel=channel,
    )
    db.add(inv)
    db.flush()
    db.refresh(inv)
    audit.record(
        db,
        user.id,
        "INVOICE_SUBMITTED",
        "INVOICE",
        inv.id,
        None,
        {"invoice_number": invoice_number, "amount": amount, "po": po_number, "channel": channel},
    )
    return apply_match(db, inv, user.id)


def link_purchase_order(db: Session, user: User, inv: Invoice, po_number: str) -> Invoice:
    # Legacy (as-found) invoices may be PENDING_APPROVAL without ever having had a PO.
    legacy = inv.status == "PENDING_APPROVAL" and inv.po_id is None
    if inv.status not in ("SUBMITTED", "EXCEPTION") and not legacy:
        raise Unprocessable(f"Cannot change the PO of an invoice that is {inv.status}.")
    po = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.po_number == po_number.strip().upper(),
            PurchaseOrder.supplier_id == inv.supplier_id,
        )
    )
    if po is None:
        raise Unprocessable(f"Purchase order {po_number} was not found for this supplier.")
    audit.record(
        db,
        user.id,
        "INVOICE_PO_LINKED",
        "INVOICE",
        inv.id,
        {"po_id": inv.po_id},
        {"po_id": po.id, "po_number": po.po_number},
    )
    inv.po_id = po.id
    db.flush()
    db.refresh(inv)
    return apply_match(db, inv, user.id)


def record_goods_receipt(
    db: Session, user: User, po: PurchaseOrder, amount: Decimal, received_date: date
) -> GoodsReceipt:
    if po.status not in RECEIVABLE_PO_STATUSES:
        raise Unprocessable(f"Cannot receive goods against a PO that is {po.status}.")
    if received_date > date.today():
        raise Unprocessable("Received date cannot be in the future.")
    already = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(GoodsReceipt.amount_received), 0)).where(
                GoodsReceipt.po_id == po.id
            )
        )
    )
    if already + amount > po.total_amount * _tolerance():
        raise Unprocessable(
            "Total received would exceed the purchase order value.",
            {"po_total": po.total_amount, "already_received": already},
        )

    count = db.scalar(select(func.count()).select_from(GoodsReceipt)) or 0
    grn = GoodsReceipt(
        grn_number=f"GRN-{count + 1:05d}",
        po_id=po.id,
        received_date=received_date,
        amount_received=amount,
        received_by=user.id,
    )
    db.add(grn)
    po.status = "RECEIVED" if already + amount >= po.total_amount else "PARTIALLY_RECEIVED"
    db.flush()
    audit.record(
        db,
        user.id,
        "GOODS_RECEIVED",
        "PURCHASE_ORDER",
        po.id,
        None,
        {"grn": grn.grn_number, "amount": amount},
    )

    # Invoices that were waiting for delivery evidence are re-matched automatically.
    waiting = db.scalars(
        select(Invoice).where(Invoice.po_id == po.id, Invoice.status == "EXCEPTION")
    ).unique()
    for inv in waiting:
        apply_match(db, inv, user.id)
    return grn


def approve_invoice(db: Session, user: User, inv: Invoice, comment: str | None) -> Invoice:
    if inv.status != "PENDING_APPROVAL":
        raise Unprocessable(f"Only invoices pending approval can be approved (this is {inv.status}).")
    is_owner = inv.current_approver_id == user.id
    if not is_owner and user.role != "MANAGER":
        raise Forbidden("Only the assigned approver or a manager can approve this invoice.")
    if not is_owner and not comment:
        raise Unprocessable("A manager overriding the assigned approver must give a reason.")
    if (user.approval_limit or 0) < inv.amount:
        raise Forbidden("Invoice amount exceeds your approval limit.")
    po = inv.purchase_order
    if po and po.created_by == user.id:
        raise Forbidden("You raised this purchase order, so you cannot approve its invoice.")

    before = _snapshot(inv)
    step = db.scalar(
        select(InvoiceApproval)
        .where(InvoiceApproval.invoice_id == inv.id, InvoiceApproval.decision == "PENDING")
        .order_by(InvoiceApproval.step.desc())
    )
    now = datetime.now(UTC)
    if step:
        step.decision, step.decided_at, step.comment = "APPROVED", now, comment
        step.approver_id = user.id
    inv.status = "APPROVED"
    finance = users_with_role(db, "FINANCE_OFFICER")
    inv.current_approver_id = finance[0] if finance else None  # Finance now owns payment
    _sync(db, inv)
    audit.record(
        db,
        user.id,
        "INVOICE_APPROVED",
        "INVOICE",
        inv.id,
        before,
        {**_snapshot(inv), "comment": comment},
    )
    notify(
        db,
        supplier_users(db, inv.supplier_id),
        "INVOICE_APPROVED",
        "INVOICE",
        inv.id,
        f"Invoice {inv.invoice_number} approved",
        "Your invoice has been approved and is scheduled for payment.",
    )
    return inv


def reject_invoice(db: Session, user: User, inv: Invoice, reason: str) -> Invoice:
    if inv.status not in ("PENDING_APPROVAL", "EXCEPTION"):
        raise Unprocessable(f"Cannot reject an invoice that is {inv.status}.")
    if inv.current_approver_id != user.id and user.role not in ("MANAGER", "FINANCE_OFFICER"):
        raise Forbidden("Only the assigned approver, Finance or a manager can reject this invoice.")
    before = _snapshot(inv)
    step = db.scalar(
        select(InvoiceApproval).where(
            InvoiceApproval.invoice_id == inv.id, InvoiceApproval.decision == "PENDING"
        )
    )
    if step:
        step.decision, step.decided_at, step.comment = "REJECTED", datetime.now(UTC), reason
    inv.status, inv.current_approver_id = "REJECTED", None
    _sync(db, inv)
    audit.record(
        db,
        user.id,
        "INVOICE_REJECTED",
        "INVOICE",
        inv.id,
        before,
        {**_snapshot(inv), "reason": reason},
    )
    notify(
        db,
        supplier_users(db, inv.supplier_id),
        "INVOICE_REJECTED",
        "INVOICE",
        inv.id,
        f"Invoice {inv.invoice_number} rejected",
        reason,
    )
    return inv


def pay_invoice(db: Session, user: User, inv: Invoice) -> Payment:
    if inv.status != "APPROVED":
        raise Unprocessable(f"Only approved invoices can be paid (this is {inv.status}).")
    account = db.scalar(
        select(BankAccount).where(
            BankAccount.supplier_id == inv.supplier_id, BankAccount.effective_to.is_(None)
        )
    )
    if account is None or not account.verified:
        raise Unprocessable("Supplier has no verified bank account on file.")
    cooldown = timedelta(hours=get_settings().bank_change_cooldown_hours)
    now = datetime.now(UTC)
    if account.changed_by == user.id and now - account.effective_from < cooldown:
        raise Forbidden(
            "You changed this supplier's bank details recently; "
            "another Finance officer must release this payment."
        )

    payment = Payment(
        invoice_id=inv.id,
        bank_account_id=account.id,
        amount=inv.amount,
        paid_at=now,
        reference=f"PAY-{inv.invoice_number_norm}-{now:%y%m%d%H%M%S}",
    )
    db.add(payment)
    before = _snapshot(inv)
    inv.status, inv.paid_at, inv.current_approver_id = "PAID", now, None
    _sync(db, inv)
    audit.record(
        db,
        user.id,
        "INVOICE_PAID",
        "INVOICE",
        inv.id,
        before,
        {**_snapshot(inv), "reference": payment.reference, "account_last4": account.account_last4},
    )
    notify(
        db,
        supplier_users(db, inv.supplier_id),
        "INVOICE_PAID",
        "INVOICE",
        inv.id,
        f"Invoice {inv.invoice_number} paid",
        f"R{inv.amount:,.2f} paid to account ending {account.account_last4}. Reference {payment.reference}.",
    )
    return payment
