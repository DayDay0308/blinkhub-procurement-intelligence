"""Invoice ageing and SLA rules (case study Problem 4).

Kept as pure functions so they are trivial to unit-test and reuse in the
risk engine and dbt models.
"""

from datetime import UTC, datetime

from app.core.config import get_settings
from app.models import Invoice
from app.schemas import InvoiceOut, SupplierRef, UserRef

FINAL_STATUSES = {"PAID", "REJECTED"}


def days_outstanding(inv: Invoice, now: datetime | None = None) -> int:
    """Days from receipt until payment (if paid) or until now."""
    end = inv.paid_at or now or datetime.now(UTC)
    return max(0, (end - inv.received_at).days)


def ageing_bucket(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def sla_state(inv: Invoice, days: int) -> str:
    """Escalation ladder: warn the approver, escalate to the manager, then breach."""
    if inv.status == "PAID":
        return "PAID"
    s = get_settings()
    if days > s.payment_terms_days:
        return "BREACHED"
    if days >= s.sla_escalation_days:
        return "ESCALATED"
    if days >= s.sla_warning_days:
        return "WARNING"
    return "ON_TRACK"


def exceptions(inv: Invoice) -> list[str]:
    """Reasons this invoice cannot flow straight through to payment: the stored 3-way-match
    result, plus gaps visible in records that never went through matching (as-found data)."""
    out = set(inv.match_exceptions or [])
    if inv.status not in FINAL_STATUSES:
        if inv.po_id is None:
            out.add("MISSING_PO_REFERENCE")
        elif inv.purchase_order and inv.amount > inv.purchase_order.total_amount:
            out.add("AMOUNT_EXCEEDS_PO")
        if inv.current_approver_id is None:
            out.add("NO_ACCOUNTABLE_APPROVER")
    return sorted(out)


def to_out(inv: Invoice, now: datetime | None = None) -> InvoiceOut:
    days = days_outstanding(inv, now)
    return InvoiceOut(
        id=inv.id,
        invoice_number=inv.invoice_number,
        supplier=SupplierRef.model_validate(inv.supplier),
        po_number=inv.purchase_order.po_number if inv.purchase_order else None,
        amount=inv.amount,
        status=inv.status,
        invoice_date=inv.invoice_date,
        received_at=inv.received_at,
        due_date=inv.due_date,
        paid_at=inv.paid_at,
        days_outstanding=days,
        ageing_bucket=ageing_bucket(days),
        sla_state=sla_state(inv, days),
        exceptions=exceptions(inv),
        current_owner=(UserRef.model_validate(inv.current_approver) if inv.current_approver else None),
    )
