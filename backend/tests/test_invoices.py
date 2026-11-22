from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.invoices import ageing_bucket, sla_state


# ---- pure business rules -------------------------------------------------
@pytest.mark.parametrize(
    "days,bucket",
    [(0, "0-30"), (30, "0-30"), (31, "31-60"), (60, "31-60"), (61, "61-90"), (91, "90+")],
)
def test_ageing_bucket_boundaries(days, bucket):
    assert ageing_bucket(days) == bucket


@pytest.mark.parametrize(
    "days,state",
    [(5, "ON_TRACK"), (20, "WARNING"), (25, "ESCALATED"), (30, "ESCALATED"), (31, "BREACHED")],
)
def test_sla_escalation_ladder(days, state):
    assert sla_state(SimpleNamespace(status="PENDING_APPROVAL"), days) == state


def test_paid_invoice_is_never_breached():
    assert sla_state(SimpleNamespace(status="PAID"), 200) == "PAID"


# ---- case-study findings, through the API ----------------------------------
def test_case_study_overdue_invoices(client, token):
    r = client.get("/api/v1/invoices", params={"overdue": True}, headers=token("finance@mics.demo"))
    items = r.json()["items"]
    # Sorted by days outstanding, most urgent first
    assert [i["invoice_number"] for i in items][:2] == ["INV003", "INV006"]
    assert {i["invoice_number"] for i in items} == {
        "INV002",
        "INV003",
        "INV005",
        "INV006",
        "INV008",
    }
    assert sum(float(i["amount"]) for i in items) == 955_000


def test_as_found_data_shows_process_gaps(client, token):
    """The source invoices have no PO reference and no owner: the API makes that visible."""
    items = client.get(
        "/api/v1/invoices",
        params={"status": "PENDING_APPROVAL"},
        headers=token("manager@mics.demo"),
    ).json()["items"]
    assert items and all(
        {"MISSING_PO_REFERENCE", "NO_ACCOUNTABLE_APPROVER"} <= set(i["exceptions"]) for i in items
    )


def test_supplier_sees_only_own_invoices(client, token):
    items = client.get("/api/v1/invoices", headers=token("accounts@ubuntucleaning.demo")).json()[
        "items"
    ]
    assert {i["invoice_number"] for i in items} == {"INV001", "INV006"}
    assert {i["supplier"]["legal_name"] for i in items} == {"Ubuntu Cleaning"}


def test_supplier_cannot_open_another_suppliers_invoice(client, token):
    metro = next(
        i
        for i in client.get("/api/v1/invoices", headers=token("auditor@mics.demo")).json()["items"]
        if i["invoice_number"] == "INV003"
    )
    r = client.get(f"/api/v1/invoices/{metro['id']}", headers=token("accounts@thutosupplies.demo"))
    assert r.status_code == 404  # not 403: don't confirm the invoice exists


def test_paid_invoice_days_are_frozen_at_payment(db):
    from app.models import Invoice
    from app.services.invoices import days_outstanding

    inv = db.query(Invoice).filter_by(invoice_number="INV007").one()
    later = datetime.now(UTC) + timedelta(days=100)
    assert days_outstanding(inv, later) == 8
