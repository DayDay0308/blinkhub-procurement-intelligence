"""Certificate reading: text rules without a key, AI with a key, and the checks."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services import ai, extraction

DEMO = Path(__file__).resolve().parents[2] / "demo-documents"
PROCUREMENT, THUTO = "procurement@mics.demo", "accounts@thutosupplies.demo"


def _pdf(name: str) -> bytes:
    path = DEMO / name
    if not path.exists():
        pytest.skip("demo-documents not generated")
    return path.read_bytes()


def test_text_rules_read_the_demo_certificate():
    r = extraction.extract(
        _pdf("Thuto_Supplies_BBBEE_Certificate_DEMO.pdf"),
        "application/pdf",
        "Thuto Supplies",
        "BBBEE_CERTIFICATE",
    )
    assert r["method"] == "TEXT_RULES"
    f = r["fields"]
    assert (
        f["entity_name"] == "Thuto Supplies"
        and f["bbbee_level"] == 1
        and f["reference_number"] == "DEMO-BEE-0001"
    )
    assert f["expiry_date"] > f["issue_date"]
    assert r["checks"] == {
        "name_matches": True,
        "name_similarity": 1.0,
        "not_expired": True,
        "type_matches": True,
        "dates_consistent": True,
    }
    assert r["confidence"] <= 0.75  # rules are never fully trusted
    assert "demonstration" in r["note"].lower()


def test_checks_catch_a_document_for_another_company():
    r = extraction.extract(
        _pdf("Rapid_Transport_BBBEE_Affidavit_DEMO.pdf"),
        "application/pdf",
        "Ubuntu Cleaning",
        "TAX_CLEARANCE",
    )
    assert r["checks"]["name_matches"] is False
    assert r["checks"]["type_matches"] is False  # an affidavit is not a tax clearance


def test_unreadable_files_fall_back_to_manual_entry():
    r = extraction.extract(b"\x89PNG\r\n\x1a\n...", "image/png", "Thuto Supplies", "TAX_CLEARANCE")
    assert r["method"] == "NONE" and "Enter the dates" in r["note"]


def test_names_compare_without_legal_suffixes():
    assert extraction.name_similarity("Marula Guarding (Pty) Ltd", "MARULA GUARDING") == 1.0
    assert extraction.name_similarity("Thuto Supplies", "Thabo Supplies") < 1.0


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")


def test_ai_result_is_used_when_a_key_is_set(with_key, monkeypatch):
    expiry = (date.today() + timedelta(days=200)).isoformat()
    seen = {}

    def fake(system, content, tool, max_tokens=1024):
        seen["kinds"] = [c["type"] for c in content]
        return {
            "entity_name": "THUTO SUPPLIES (PTY) LTD",
            "document_kind": "TAX_CLEARANCE",
            "issue_date": "2026-05-01",
            "expiry_date": expiry,
            "confidence": 0.93,
        }

    monkeypatch.setattr(ai, "structured", fake)
    r = extraction.extract(b"\x89PNG photo of a letter", "image/png", "Thuto Supplies", "TAX_CLEARANCE")
    assert seen["kinds"] == ["image", "text"]  # photos work with AI
    assert r["method"] == "AI" and r["confidence"] == 0.93
    assert r["fields"]["expiry_date"] == expiry and r["checks"]["name_matches"]


def test_ai_failure_falls_back_to_text_rules(with_key, monkeypatch):
    monkeypatch.setattr(ai, "structured", lambda *a, **k: None)  # timeout, bad key, outage...
    r = extraction.extract(
        _pdf("Thuto_Supplies_Tax_Compliance_DEMO.pdf"), "application/pdf", "Thuto Supplies", "TAX_CLEARANCE"
    )
    assert r["method"] == "TEXT_RULES" and r["fields"]["reference_number"] == "DEMO-PIN-0001"


def test_no_key_means_no_ai_call(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    assert ai.structured("s", [], {"name": "t"}) is None


def test_upload_stores_what_was_read(client, token, tmp_path):
    settings = get_settings()
    old, settings.document_dir = settings.document_dir, str(tmp_path)
    try:
        items = client.get("/api/v1/compliance/overview", headers=token(PROCUREMENT)).json()["items"]
        thuto = next(i for i in items if i["supplier"]["legal_name"] == "Thuto Supplies")["supplier"]["id"]
        r = client.post(
            f"/api/v1/suppliers/{thuto}/documents",
            data={"doc_type": "TAX_CLEARANCE"},
            files={"file": ("tcs.pdf", _pdf("Thuto_Supplies_Tax_Compliance_DEMO.pdf"), "application/pdf")},
            headers=token(THUTO),
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["status"] == "EXTRACTED"
        assert doc["extracted"]["method"] == "TEXT_RULES"
        assert doc["expiry_date"] == doc["extracted"]["fields"]["expiry_date"]  # pre-filled from the document
    finally:
        settings.document_dir = old
