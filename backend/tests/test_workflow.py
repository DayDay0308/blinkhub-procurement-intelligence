"""End-to-end invoice workflow, written as the story we demo:

Thuto Supplies (an SMME) submits an invoice on the portal -> it waits for delivery evidence ->
procurement records the goods receipt -> it is routed to a named approver -> approved ->
paid -> the supplier follows every step on its timeline.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

THUTO = "accounts@thutosupplies.demo"
UBUNTU = "accounts@ubuntucleaning.demo"
FINANCE = "finance@mics.demo"
APPROVER = "approver@mics.demo"
PROCUREMENT = "procurement@mics.demo"
MANAGER = "manager@mics.demo"
TODAY = date.today().isoformat()


def submit(client, token, who, **body):
    body.setdefault("invoice_date", TODAY)
    return client.post("/api/v1/invoices", json=body, headers=token(who))


def grn(client, token, po, amount):
    return client.post(
        f"/api/v1/purchase-orders/{po}/goods-receipts",
        json={"amount_received": amount, "received_date": TODAY},
        headers=token(PROCUREMENT),
    )


@pytest.fixture(scope="module")
def story(client, token):
    """Shared state for the happy-path story (tests below run in order)."""
    return {}


# ---- the happy path ---------------------------------------------------------------
def test_1_supplier_submits_and_invoice_waits_for_delivery(client, token, story):
    r = submit(client, token, THUTO, invoice_number="TS-1001", po_number="PO010", amount=42000)
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["status"] == "EXCEPTION"
    assert inv["exceptions"] == ["AWAITING_GOODS_RECEIPT"]
    assert inv["current_owner"]["role"] == "FINANCE_OFFICER"  # never ownerless
    assert inv["due_date"] == (date.today() + timedelta(days=30)).isoformat()
    story["id"] = inv["id"]


def test_2_resubmitting_same_invoice_number_is_blocked(client, token):
    r = submit(client, token, THUTO, invoice_number="ts 1001", po_number="PO010", amount=42000)
    assert r.status_code == 409
    assert "already been submitted" in r.json()["error"]["message"]


def test_3_goods_receipt_triggers_rematch_and_routing(client, token, story):
    assert grn(client, token, "PO010", 42000).status_code == 201
    inv = client.get(f"/api/v1/invoices/{story['id']}", headers=token(THUTO)).json()
    assert inv["status"] == "PENDING_APPROVAL"
    assert inv["exceptions"] == []
    assert inv["current_owner"]["role"] == "APPROVER"


def test_4_approver_is_notified_and_sees_it_in_their_queue(client, token, story):
    notes = client.get("/api/v1/notifications", headers=token(APPROVER)).json()["items"]
    assert any(n["kind"] == "INVOICE_ASSIGNED" and n["entity_id"] == story["id"] for n in notes)
    queue = client.get("/api/v1/invoices", params={"assigned_to_me": True}, headers=token(APPROVER)).json()[
        "items"
    ]
    assert story["id"] in {i["id"] for i in queue}


def test_5_only_the_assigned_approver_can_approve(client, token, story):
    r = client.post(f"/api/v1/invoices/{story['id']}/approve", json={}, headers=token(FINANCE))
    assert r.status_code == 403


def test_6_approve_hands_ownership_to_finance(client, token, story):
    r = client.post(
        f"/api/v1/invoices/{story['id']}/approve",
        json={"comment": "Delivered OK"},
        headers=token(APPROVER),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"
    assert r.json()["current_owner"]["role"] == "FINANCE_OFFICER"


def test_7_supplier_cannot_pay_but_finance_can(client, token, story):
    assert client.post(f"/api/v1/invoices/{story['id']}/pay", headers=token(THUTO)).status_code == 403
    r = client.post(f"/api/v1/invoices/{story['id']}/pay", headers=token(FINANCE))
    assert r.status_code == 200, r.text
    assert r.json()["reference"].startswith("PAY-TS1001-")


def test_8_paid_twice_is_impossible(client, token, story):
    r = client.post(f"/api/v1/invoices/{story['id']}/pay", headers=token(FINANCE))
    assert r.status_code == 422


def test_9_supplier_timeline_shows_every_step(client, token, story):
    events = client.get(f"/api/v1/invoices/{story['id']}/timeline", headers=token(THUTO)).json()
    assert [e["action"] for e in events] == [
        "INVOICE_SUBMITTED",
        "INVOICE_MATCHED",
        "INVOICE_MATCHED",
        "INVOICE_APPROVED",
        "INVOICE_PAID",
    ]
    assert [e["status"] for e in events][1:] == [
        "EXCEPTION",
        "PENDING_APPROVAL",
        "APPROVED",
        "PAID",
    ]
    notes = client.get("/api/v1/notifications", headers=token(THUTO)).json()["items"]
    assert {"INVOICE_APPROVED", "INVOICE_PAID"} <= {n["kind"] for n in notes}


# ---- validation and controls -------------------------------------------------------
def test_supplier_cannot_bill_another_suppliers_po(client, token):
    r = submit(client, token, THUTO, invoice_number="TS-X", po_number="PO004", amount=1000)
    assert r.status_code == 422
    assert "not found for this supplier" in r.json()["error"]["message"]


@pytest.mark.parametrize(
    "body",
    [
        {"invoice_date": (date.today() + timedelta(days=3)).isoformat()},  # future-dated
        {"vat_amount": 999999},  # VAT larger than the invoice
        {"amount": -5},
    ],
)
def test_invoice_input_validation(client, token, body):
    r = submit(
        client,
        token,
        THUTO,
        **{"invoice_number": "TS-V", "po_number": "PO010", "amount": 100, **body},
    )
    assert r.status_code == 422


def test_staff_capture_of_emailed_invoice_flags_amount_over_po(client, token):
    suppliers = client.get("/api/v1/suppliers", params={"q": "Khula"}, headers=token(FINANCE)).json()["items"]
    r = submit(
        client,
        token,
        FINANCE,
        invoice_number="KE-7781",
        po_number="PO005",
        amount=120000,
        supplier_id=suppliers[0]["id"],
    )
    assert r.status_code == 201, r.text
    assert set(r.json()["exceptions"]) == {"AMOUNT_EXCEEDS_PO", "AWAITING_GOODS_RECEIPT"}


def test_receiving_more_than_ordered_is_blocked(client, token):
    r = grn(client, token, "PO012", 200000)  # PO012 is R125,000
    assert r.status_code == 422


def test_linking_po_exposes_the_thuto_duplicate(client, token):
    """Case study: INV002 and INV008 are both R35,000 from Thuto. Linking both to PO003
    (R35,000) makes the 3-way match flag the second one as billing more than was ordered."""
    items = client.get("/api/v1/invoices", headers=token(FINANCE)).json()["items"]
    ids = {i["invoice_number"]: i["id"] for i in items}
    first = client.post(
        f"/api/v1/invoices/{ids['INV002']}/link-po",
        json={"po_number": "PO003"},
        headers=token(FINANCE),
    ).json()
    assert first["exceptions"] == ["AWAITING_GOODS_RECEIPT"]
    second = client.post(
        f"/api/v1/invoices/{ids['INV008']}/link-po",
        json={"po_number": "PO003"},
        headers=token(FINANCE),
    ).json()
    assert "AMOUNT_EXCEEDS_PO" in second["exceptions"]


def test_manager_override_requires_reason(client, token):
    r = submit(client, token, UBUNTU, invoice_number="UC-5501", po_number="PO008", amount=95000)
    inv_id = r.json()["id"]
    grn(client, token, "PO008", 95000)
    no_reason = client.post(f"/api/v1/invoices/{inv_id}/approve", json={}, headers=token(MANAGER))
    assert no_reason.status_code == 422
    ok = client.post(
        f"/api/v1/invoices/{inv_id}/approve",
        json={"comment": "Approver on leave; SMME waiting"},
        headers=token(MANAGER),
    )
    assert ok.status_code == 200


def test_rejection_needs_a_real_reason(client, token):
    r = submit(client, token, UBUNTU, invoice_number="UC-5502", po_number="PO001", amount=85000)
    inv_id = r.json()["id"]
    short = client.post(f"/api/v1/invoices/{inv_id}/reject", json={"reason": "no"}, headers=token(FINANCE))
    assert short.status_code == 422
    ok = client.post(
        f"/api/v1/invoices/{inv_id}/reject",
        json={"reason": "PO001 was already invoiced and paid (INV001)."},
        headers=token(FINANCE),
    )
    assert ok.json()["status"] == "REJECTED"


def test_whoever_changed_bank_details_cannot_release_payment(client, token):
    from sqlalchemy import select, text

    from app.db.session import SessionLocal
    from app.models import User

    r = submit(client, token, UBUNTU, invoice_number="UC-5503", po_number="PO008", amount=1)
    inv_id = r.json()["id"]
    # Shortcut to an approved invoice, then simulate the same Finance officer having just
    # changed this supplier's bank details.
    with SessionLocal() as db, db.begin():
        finance_id = db.scalar(select(User.id).where(User.email == FINANCE))
        db.execute(text("UPDATE p2p.invoices SET status='APPROVED' WHERE id=:i"), {"i": inv_id})
        db.execute(
            text(
                "UPDATE compliance.bank_accounts SET changed_by=:u, effective_from=:t "
                "WHERE supplier_id=(SELECT supplier_id FROM p2p.invoices WHERE id=:i)"
            ),
            {"u": finance_id, "t": datetime.now(UTC), "i": inv_id},
        )
    r = client.post(f"/api/v1/invoices/{inv_id}/pay", headers=token(FINANCE))
    assert r.status_code == 403
    assert "bank details recently" in r.json()["error"]["message"]


# ---- SLA job -----------------------------------------------------------------------
def test_sla_job_alerts_managers_with_smme_priority_and_is_idempotent(client, token):
    first = client.post("/api/v1/jobs/sla-check", headers=token(MANAGER)).json()
    assert first["BREACHED"] >= 5
    assert first["notifications_created"] > 0
    again = client.post("/api/v1/jobs/sla-check", headers=token(MANAGER)).json()
    assert again["notifications_created"] == 0  # re-running never spams

    notes = client.get("/api/v1/notifications", headers=token(MANAGER)).json()["items"]
    titles = [n["title"] for n in notes if n["kind"] == "SLA_BREACHED"]
    assert any(t.startswith("[SMME priority]") and "INV006" in t for t in titles)
    assert any("INV003" in t and not t.startswith("[SMME") for t in titles)


def test_sla_job_requires_manager(client, token):
    assert client.post("/api/v1/jobs/sla-check", headers=token(FINANCE)).status_code == 403
