"""Scheduled payment-SLA check (runs every few minutes via Celery beat).

Escalation ladder, measured from the day the invoice was received:
    day 20 -> WARNING    : the accountable owner is reminded
    day 25 -> ESCALATED  : managers are alerted
    day 31 -> BREACHED   : managers and Finance are alerted
SMME suppliers are marked as priority, because late payment hurts them most
(the case study's cleaning company unpaid for 75 days).
"""

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice
from app.services.invoices import days_outstanding, sla_state
from app.services.notifications import notify, users_with_role
from app.services.workflow import OPEN_STATUSES


def run_sla_check(db: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    managers = users_with_role(db, "MANAGER")
    finance = users_with_role(db, "FINANCE_OFFICER")
    counts: Counter[str] = Counter()
    created = 0

    for inv in db.scalars(select(Invoice).where(Invoice.status.in_(OPEN_STATUSES))).unique():
        days = days_outstanding(inv, now)
        state = sla_state(inv, days)
        counts[state] += 1
        if state == "ON_TRACK":
            continue

        smme = inv.supplier.supplier_type == "SMME"
        tag = "[SMME priority] " if smme else ""
        what = f"{inv.invoice_number} · {inv.supplier.legal_name} · R{inv.amount:,.0f}"
        owner = [inv.current_approver_id] if inv.current_approver_id else []

        if state == "WARNING":
            recipients = owner or managers  # no owner -> straight to managers
            created += notify(
                db,
                recipients,
                "SLA_WARNING",
                "INVOICE",
                inv.id,
                f"{tag}Invoice due soon: {what}",
                f"Outstanding {days} days. Payment terms are 30 days.",
            )
        elif state == "ESCALATED":
            created += notify(
                db,
                [*owner, *managers],
                "SLA_ESCALATED",
                "INVOICE",
                inv.id,
                f"{tag}Escalated: {what}",
                f"Outstanding {days} days with no payment.",
            )
        elif state == "BREACHED":
            created += notify(
                db,
                [*owner, *managers, *finance],
                "SLA_BREACHED",
                "INVOICE",
                inv.id,
                f"{tag}Payment terms breached: {what}",
                f"Outstanding {days} days, past the 30-day terms.",
            )
    db.flush()
    return {**counts, "notifications_created": created}
