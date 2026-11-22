"""Load the case-study sample data and demo users.

uv run python -m seed.run            # load if the database is empty
uv run python -m seed.run --reset    # wipe transactional + master data first
"""

import argparse
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Category, Department, Invoice, PurchaseOrder, Supplier, User
from seed import case_study as cs

DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "Demo@2026!")


def reset(db: Session) -> None:
    db.execute(
        text(
            "TRUNCATE risk.case_notes, risk.flags, p2p.payments, p2p.invoice_approvals, "
            "p2p.invoices, p2p.goods_receipts, p2p.purchase_order_lines, p2p.purchase_orders, "
            "p2p.contracts, sourcing.quotations, sourcing.opportunities, compliance.bank_accounts, "
            "compliance.documents, core.supplier_categories, core.users, core.budgets, "
            "core.suppliers, core.categories, core.departments CASCADE"
        )
    )


def load(db: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)

    depts = {name: Department(code=code, name=name) for code, name in cs.DEPARTMENTS}
    cats = {name: Category(code=code, name=name) for code, name in cs.CATEGORIES}
    db.add_all([*depts.values(), *cats.values()])

    suppliers = {}
    for i, (name, prov, typ, level, status) in enumerate(cs.SUPPLIERS, start=1):
        suppliers[name] = Supplier(
            supplier_code=f"SUP-{i:05d}",
            legal_name=name,
            province=prov,
            supplier_type=typ,
            bbbee_level=level,
            status=status,
            registration_number=f"2019/{100000 + i:06d}/07",  # demo value
        )
    db.add_all(suppliers.values())
    db.flush()

    users = {}
    pw = hash_password(DEMO_PASSWORD)
    for email, name, role, dept, sup, limit in cs.DEMO_USERS:
        users[role if role != "SUPPLIER" else email] = User(
            email=email,
            full_name=name,
            role=role,
            password_hash=pw,
            department_id=depts[dept].id if dept else None,
            supplier_id=suppliers[sup].id if sup else None,
            approval_limit=Decimal(limit) if limit else None,
        )
    db.add_all(users.values())
    db.flush()

    for po_no, sup, cat, dept, amount in cs.PURCHASE_ORDERS:
        db.add(
            PurchaseOrder(
                po_number=po_no,
                supplier_id=suppliers[sup].id,
                department_id=depts[dept].id,
                category_id=cats[cat].id,
                total_amount=Decimal(amount),
                status="APPROVED",
                delivery_province=suppliers[sup].province,
                created_by=users["PROCUREMENT_OFFICER"].id,
                approved_by=users["APPROVER"].id,
                approved_at=now,
            )
        )

    for inv_no, sup, amount, days, status in cs.INVOICES:
        received = now - timedelta(days=days)
        paid = status == "Paid"
        db.add(
            Invoice(
                invoice_number=inv_no,
                supplier_id=suppliers[sup].id,
                amount=Decimal(amount),
                invoice_date=received.date(),
                received_at=received,
                due_date=(received + timedelta(days=30)).date(),
                status="PAID" if paid else "PENDING_APPROVAL",
                paid_at=received + timedelta(days=days) if paid else None,
                channel="EMAIL",  # case study: invoices arrive via various email addresses
            )
        )
    db.flush()
    return {
        "suppliers": len(suppliers),
        "purchase_orders": len(cs.PURCHASE_ORDERS),
        "invoices": len(cs.INVOICES),
        "users": len(users),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db, db.begin():
        if args.reset:
            reset(db)
        elif db.scalar(select(func.count()).select_from(Supplier)):
            print("Database already has data; skipping (use --reset to reload).")
            return
        counts = load(db)
    print("Seeded case-study data:", counts)
    print(f"Demo users share the password {DEMO_PASSWORD!r} (demo only).")


if __name__ == "__main__":
    main()
