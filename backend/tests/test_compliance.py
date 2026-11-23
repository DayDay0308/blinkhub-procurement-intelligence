"""Supplier compliance documents: status, upload, verification, reminders."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.core.config import get_settings

MANAGER, PROCUREMENT, ADMIN = "manager@mics.demo", "procurement@mics.demo", "admin@mics.demo"
THUTO, UBUNTU = "accounts@thutosupplies.demo", "accounts@ubuntucleaning.demo"
PDF = b"%PDF-1.4\n% demo certificate\n"


@pytest.fixture(autouse=True)
def _document_dir(tmp_path):
    settings = get_settings()
    old, settings.document_dir = settings.document_dir, str(tmp_path)
    yield
    settings.document_dir = old


def _overview(client, token):
    r = client.get("/api/v1/compliance/overview", headers=token(MANAGER))
    assert r.status_code == 200, r.text
    return {i["supplier"]["legal_name"]: i for i in r.json()["items"]}, r.json()


def _supplier_id(client, token, name):
    return _overview(client, token)[0][name]["supplier"]["id"]


def _req(item, requirement):
    return next(r for r in item["requirements"] if r["requirement"] == requirement)


def test_overview_states_for_case_study(client, token):
    items, body = _overview(client, token)
    thuto, khula, rapid = items["Thuto Supplies"], items["Khula Electrical"], items["Rapid Transport"]

    assert _req(thuto, "TAX_CLEARANCE")["state"] == "EXPIRING"
    assert _req(thuto, "TAX_CLEARANCE")["days_left"] == 12
    assert _req(thuto, "BBBEE")["state"] == "EXPIRED"
    assert thuto["state"] == "EXPIRED"  # worst requirement wins

    assert khula["state"] == "EXPIRING"
    assert _req(khula, "TAX_CLEARANCE")["pending_document_id"]  # renewal already sent

    assert rapid["state"] == "MISSING"
    assert items["Ubuntu Cleaning"]["state"] == "VALID"
    assert "Sisonke Trading" not in items  # inactive suppliers aren't checked

    states = [i["state"] for i in body["items"]]
    order = ["EXPIRED", "MISSING", "PENDING_VERIFICATION", "EXPIRING", "VALID"]
    assert states == sorted(states, key=order.index)  # worst first
    assert body["awaiting_verification"] >= 1


def test_suppliers_see_only_their_own_documents(client, token):
    thuto = _supplier_id(client, token, "Thuto Supplies")
    ubuntu = _supplier_id(client, token, "Ubuntu Cleaning")
    own = client.get(f"/api/v1/suppliers/{thuto}/documents", headers=token(THUTO))
    assert own.status_code == 200 and own.json()["state"] == "EXPIRED"
    assert client.get(f"/api/v1/suppliers/{ubuntu}/documents", headers=token(THUTO)).status_code == 403
    assert client.get("/api/v1/compliance/overview", headers=token(THUTO)).status_code == 403


def _upload(client, token, who, supplier_id, content=PDF, doc_type="BBBEE_CERTIFICATE", name="cert.pdf"):
    return client.post(
        f"/api/v1/suppliers/{supplier_id}/documents",
        data={"doc_type": doc_type},
        files={"file": (name, content, "application/pdf")},
        headers=token(who),
    )


def test_upload_validates_files(client, token):
    thuto = _supplier_id(client, token, "Thuto Supplies")
    # The file type comes from the content, not the name
    r = _upload(client, token, THUTO, thuto, content=b"MZ\x90 not a pdf", name="cert.pdf")
    assert r.status_code == 422 and "PDF" in r.json()["error"]["message"]
    big = b"%PDF-" + b"0" * (get_settings().document_max_mb * 1024 * 1024)
    assert _upload(client, token, THUTO, thuto, content=big).status_code == 422
    ubuntu = _supplier_id(client, token, "Ubuntu Cleaning")
    assert _upload(client, token, THUTO, ubuntu).status_code == 403  # not their supplier
    assert _upload(client, token, MANAGER, thuto).status_code == 403  # managers don't upload


def test_upload_verify_flow_restores_compliance(client, token):
    thuto = _supplier_id(client, token, "Thuto Supplies")
    content = PDF + b"thuto-bbbee-2027"
    up = _upload(client, token, THUTO, thuto, content=content)
    assert up.status_code == 201, up.text
    doc = up.json()
    assert doc["status"] == "UPLOADED" and doc["has_file"]
    assert _upload(client, token, THUTO, thuto, content=content).status_code == 409  # same file again

    items, _ = _overview(client, token)
    assert _req(items["Thuto Supplies"], "BBBEE")["state"] == "PENDING_VERIFICATION"

    # The supplier can download its own file; procurement is told there is something to check
    assert (
        client.get(f"/api/v1/compliance/documents/{doc['id']}/file", headers=token(THUTO)).content == content
    )
    notes = client.get("/api/v1/notifications", headers=token(PROCUREMENT)).json()["items"]
    assert any(n["kind"] == "DOC_UPLOADED" and n["entity_id"] == doc["id"] for n in notes)

    url = f"/api/v1/compliance/documents/{doc['id']}/verify"
    today = date.today()
    assert (
        client.post(
            url, json={"issue_date": str(today), "expiry_date": str(today)}, headers=token(PROCUREMENT)
        ).status_code
        == 422
    )
    expired = {"issue_date": str(today - timedelta(days=400)), "expiry_date": str(today - timedelta(days=35))}
    assert client.post(url, json=expired, headers=token(PROCUREMENT)).status_code == 422
    assert (
        client.post(
            url,
            json={"issue_date": str(today), "expiry_date": str(today + timedelta(days=365))},
            headers=token(THUTO),
        ).status_code
        == 403
    )

    ok = client.post(
        url,
        json={"issue_date": str(today), "expiry_date": str(today + timedelta(days=365))},
        headers=token(PROCUREMENT),
    )
    assert ok.status_code == 200 and ok.json()["status"] == "VERIFIED"
    assert (
        client.post(
            url,
            json={"issue_date": str(today), "expiry_date": str(today + timedelta(days=365))},
            headers=token(PROCUREMENT),
        ).status_code
        == 409
    )

    items, _ = _overview(client, token)
    assert _req(items["Thuto Supplies"], "BBBEE")["state"] == "VALID"
    supplier_notes = client.get("/api/v1/notifications", headers=token(THUTO)).json()["items"]
    assert any(n["kind"] == "DOC_VERIFIED" for n in supplier_notes)


def test_uploader_cannot_verify_own_upload(client, token):
    rapid = _supplier_id(client, token, "Rapid Transport")
    doc = _upload(client, token, PROCUREMENT, rapid, content=PDF + b"rapid", doc_type="TAX_CLEARANCE").json()
    body = {"issue_date": str(date.today()), "expiry_date": str(date.today() + timedelta(days=365))}
    r = client.post(f"/api/v1/compliance/documents/{doc['id']}/verify", json=body, headers=token(PROCUREMENT))
    assert r.status_code == 403
    assert (
        client.post(
            f"/api/v1/compliance/documents/{doc['id']}/verify", json=body, headers=token(ADMIN)
        ).status_code
        == 200
    )


def test_reject_needs_a_reason_and_tells_the_supplier(client, token):
    thuto = _supplier_id(client, token, "Thuto Supplies")
    doc = _upload(client, token, THUTO, thuto, content=PDF + b"blurry", doc_type="TAX_CLEARANCE").json()
    url = f"/api/v1/compliance/documents/{doc['id']}/reject"
    assert client.post(url, json={"reason": "no"}, headers=token(PROCUREMENT)).status_code == 422
    r = client.post(url, json={"reason": "The PIN on the letter is unreadable"}, headers=token(PROCUREMENT))
    assert r.status_code == 200 and r.json()["rejection_reason"].startswith("The PIN")
    notes = client.get("/api/v1/notifications", headers=token(THUTO)).json()["items"]
    assert any(n["kind"] == "DOC_REJECTED" and n["body"].startswith("The PIN") for n in notes)


def test_daily_check_expires_documents_and_reminds_once(client, token, db):
    ubuntu = _supplier_id(client, token, "Ubuntu Cleaning")
    # Ubuntu's tax clearance quietly passes its expiry date
    db.execute(
        text(
            "UPDATE compliance.documents SET expiry_date = current_date - 1, issue_date = current_date - 366 "
            "WHERE supplier_id = :s AND doc_type = 'TAX_CLEARANCE'"
        ),
        {"s": ubuntu},
    )
    db.commit()
    try:
        first = client.post("/api/v1/jobs/compliance-check", headers=token(MANAGER)).json()
        assert first["documents_expired"] >= 1
        assert (
            first["reminders_expiring"] >= 2
            and first["reminders_expired"] >= 1
            and first["reminders_missing"] >= 1
        )
        again = client.post("/api/v1/jobs/compliance-check", headers=token(MANAGER)).json()
        assert again == {
            "documents_expired": 0,
            "reminders_expiring": 0,
            "reminders_expired": 0,
            "reminders_missing": 0,
        }

        notes = client.get("/api/v1/notifications", headers=token(UBUNTU)).json()["items"]
        assert any(n["kind"] == "DOC_EXPIRED" for n in notes)
        items, _ = _overview(client, token)
        assert items["Ubuntu Cleaning"]["state"] == "EXPIRED"
        assert client.post("/api/v1/jobs/compliance-check", headers=token(UBUNTU)).status_code == 403
    finally:
        db.execute(
            text(
                "UPDATE compliance.documents SET status = 'VERIFIED', expiry_date = current_date + 300, "
                "issue_date = current_date - 65 WHERE supplier_id = :s AND doc_type = 'TAX_CLEARANCE'"
            ),
            {"s": ubuntu},
        )
        db.commit()
