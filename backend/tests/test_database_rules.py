"""Controls enforced by PostgreSQL itself, so no code path (UI, API, script) can bypass them."""

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InternalError, ProgrammingError

from app.models import Invoice, PurchaseOrder, Supplier, User


def _supplier(db, name):
    return db.query(Supplier).filter_by(legal_name=name).one()


def test_duplicate_invoice_number_blocked_even_with_different_formatting(db):
    ubuntu = _supplier(db, "Ubuntu Cleaning")
    db.add(
        Invoice(
            supplier_id=ubuntu.id,
            invoice_number="inv-001",
            amount=85_000,
            invoice_date=date.today(),
            due_date=date.today(),
        )
    )
    with pytest.raises(IntegrityError, match="ux_invoice_supplier_number"):
        db.flush()


def test_same_invoice_number_allowed_for_different_suppliers(db):
    metro = _supplier(db, "Metro Logistics")
    db.add(
        Invoice(
            supplier_id=metro.id,
            invoice_number="INV001",
            amount=10,
            invoice_date=date.today(),
            due_date=date.today(),
        )
    )
    db.flush()  # no error


def test_requester_cannot_approve_own_purchase_order(db):
    po = db.query(PurchaseOrder).filter_by(po_number="PO001").one()
    po.approved_by = po.created_by
    with pytest.raises(IntegrityError, match="check"):
        db.flush()


def test_paid_status_requires_payment_date(db):
    inv = db.query(Invoice).filter_by(invoice_number="INV002").one()
    inv.status = "PAID"
    with pytest.raises(IntegrityError):
        db.flush()


def test_supplier_user_must_be_linked_to_a_supplier(db):
    db.add(User(email="x@y.demo", full_name="X", password_hash="x", role="SUPPLIER"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_audit_log_is_hash_chained_and_append_only(db):
    db.execute(
        text(
            "INSERT INTO audit.events(action, entity_type, entity_id) "
            "VALUES ('A','INVOICE',gen_random_uuid()), ('B','INVOICE',gen_random_uuid())"
        )
    )
    rows = db.execute(text("SELECT prev_hash, hash FROM audit.events ORDER BY id DESC LIMIT 2"))
    newest, older = rows.all()
    assert newest.prev_hash == older.hash
    with pytest.raises((InternalError, ProgrammingError), match="append-only"):
        db.execute(text("DELETE FROM audit.events"))
