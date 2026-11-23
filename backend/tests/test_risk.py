"""Risk engine on the case-study sample, through the API."""

MANAGER, AUDITOR, FINANCE, ADMIN = (
    "manager@mics.demo",
    "auditor@mics.demo",
    "finance@mics.demo",
    "admin@mics.demo",
)
UBUNTU = "accounts@ubuntucleaning.demo"


def _flags(client, token, **params):
    return client.get("/api/v1/risk/flags", params={"limit": 500, **params}, headers=token(AUDITOR)).json()[
        "items"
    ]


def _invoice_numbers(client, token):
    items = client.get("/api/v1/invoices", headers=token(AUDITOR)).json()["items"]
    return {i["id"]: i["invoice_number"] for i in items}


def test_run_engine_on_case_study(client, token):
    r = client.post("/api/v1/risk/run", headers=token(MANAGER))
    assert r.status_code == 200, r.text
    counts = r.json()["flags_by_rule"]
    assert counts["ANOMALY_ML"] == 0  # 8 invoices: too few for a meaningful model


def test_case_study_duplicates_are_flagged(client, token):
    numbers = _invoice_numbers(client, token)
    dups = {numbers[f["entity_id"]]: f for f in _flags(client, token, rule_code="DUP_INVOICE")}
    # Thuto INV002/INV008: same amount, same day, no PO -> the later one is flagged
    assert dups["INV008"]["explanation"]["matching_invoice"] == "INV002"
    # Ubuntu INV006 matches INV001, which was already PAID -> flag the one still to be paid
    assert dups["INV006"]["explanation"]["matching_invoice"] == "INV001"
    assert dups["INV006"]["explanation"]["matching_invoice_status"] == "PAID"


def test_paid_without_po_or_delivery_is_flagged(client, token):
    numbers = _invoice_numbers(client, token)
    flagged = {numbers[f["entity_id"]] for f in _flags(client, token, rule_code="NO_DELIVERY_EVIDENCE")}
    assert {"INV001", "INV004", "INV007"} <= flagged


def test_concentration_names_the_dominant_supplier(client, token):
    flags = _flags(client, token, rule_code="CONCENTRATION")
    by_category = {f["explanation"]["category"]: f["explanation"] for f in flags}
    assert by_category["Transport"]["top_supplier"] == "Metro Logistics"
    assert by_category["Transport"]["share_pct"] > 80


def test_rerunning_does_not_duplicate_flags(client, token):
    before = client.get("/api/v1/risk/summary", headers=token(MANAGER)).json()["open_flags"]
    client.post("/api/v1/risk/run", headers=token(MANAGER))
    after = client.get("/api/v1/risk/summary", headers=token(MANAGER)).json()["open_flags"]
    assert before == after


def test_suppliers_never_see_risk_flags(client, token):
    assert client.get("/api/v1/risk/flags", headers=token(UBUNTU)).status_code == 403


def test_dismissing_needs_a_reason_and_survives_reruns(client, token):
    flag = _flags(client, token, rule_code="CONCENTRATION")[0]
    url = f"/api/v1/risk/flags/{flag['id']}/status"
    assert client.post(url, json={"status": "DISMISSED"}, headers=token(AUDITOR)).status_code == 422
    r = client.post(
        url,
        json={
            "status": "DISMISSED",
            "note": "Sole qualified supplier under a competitively tendered contract.",
        },
        headers=token(AUDITOR),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "DISMISSED" and r.json()["notes"][0]["role"] == "AUDITOR"

    client.post("/api/v1/risk/run", headers=token(MANAGER))  # the engine must not reopen it
    again = client.get(f"/api/v1/risk/flags/{flag['id']}", headers=token(AUDITOR)).json()
    assert again["status"] == "DISMISSED"


def test_only_investigators_decide_and_only_managers_reopen(client, token):
    flag = _flags(client, token, rule_code="NO_DELIVERY_EVIDENCE")[0]
    url = f"/api/v1/risk/flags/{flag['id']}/status"
    body = {"status": "CONFIRMED", "note": "No delivery note exists for this payment."}
    assert client.post(url, json=body, headers=token(FINANCE)).status_code == 403
    assert client.post(url, json=body, headers=token(AUDITOR)).status_code == 200
    reopen = {"status": "UNDER_REVIEW", "note": "Delivery note found in a shared mailbox."}
    assert client.post(url, json=reopen, headers=token(AUDITOR)).status_code == 422
    assert client.post(url, json=reopen, headers=token(MANAGER)).json()["status"] == "UNDER_REVIEW"


def test_assigning_moves_flag_under_review(client, token):
    flag = _flags(client, token, status="OPEN")[0]
    me = client.get("/api/v1/auth/me", headers=token(AUDITOR)).json()
    r = client.post(
        f"/api/v1/risk/flags/{flag['id']}/assign", json={"user_id": me["id"]}, headers=token(MANAGER)
    )
    assert r.json()["status"] == "UNDER_REVIEW"
    mine = client.get("/api/v1/risk/flags", params={"assigned_to_me": True}, headers=token(AUDITOR))
    assert flag["id"] in {f["id"] for f in mine.json()["items"]}


def test_rule_thresholds_are_tunable_by_admin_only(client, token):
    url = "/api/v1/risk/rules/SPLIT_THRESHOLD"
    assert client.patch(url, json={"params": {"min_count": 4}}, headers=token(MANAGER)).status_code == 403
    assert client.patch(url, json={"params": {"bogus": 1}}, headers=token(ADMIN)).status_code == 422
    r = client.patch(url, json={"params": {"min_count": 4}}, headers=token(ADMIN))
    assert r.json()["params"]["min_count"] == 4 and r.json()["params"]["window_days"] == 30
    client.patch(url, json={"params": {"min_count": 3}}, headers=token(ADMIN))


def test_scorecards(client, token):
    r = client.get("/api/v1/scorecards", headers=token(MANAGER)).json()
    assert r["weights"]["delivery_reliability"] == 30
    ubuntu = next(c for c in r["items"] if c["supplier"]["legal_name"] == "Ubuntu Cleaning")
    assert ubuntu["kpis"]["compliance"] == 100.0
    assert ubuntu["kpis"]["invoice_accuracy"] == 0.0  # no invoice carries a PO reference (as found)

    own = client.get(f"/api/v1/suppliers/{ubuntu['supplier']['id']}/scorecard", headers=token(UBUNTU))
    assert own.status_code == 200
    other = next(c for c in r["items"] if c["supplier"]["legal_name"] == "Metro Logistics")
    assert (
        client.get(
            f"/api/v1/suppliers/{other['supplier']['id']}/scorecard", headers=token(UBUNTU)
        ).status_code
        == 403
    )


def test_inactive_supplier_is_not_scored(client, token):
    r = client.get("/api/v1/scorecards", params={"grade": "N/A"}, headers=token(MANAGER)).json()
    assert all(c["overall"] is None for c in r["items"])
