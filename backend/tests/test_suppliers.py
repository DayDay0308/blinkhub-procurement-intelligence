NEW = {
    "legal_name": "Lesedi Hygiene Services",
    "registration_number": "2023/445566/07",
    "province": "NORTH_WEST",
    "supplier_type": "SMME",
    "bbbee_level": 1,
}


def test_internal_user_can_list_and_filter(client, token):
    r = client.get(
        "/api/v1/suppliers",
        params={"supplier_type": "SMME", "province": "LIMPOPO"},
        headers=token("procurement@mics.demo"),
    )
    assert r.status_code == 200
    assert {s["legal_name"] for s in r.json()["items"]} == {"Thuto Supplies", "Sisonke Trading"}


def test_supplier_role_cannot_list_all_suppliers(client, token):
    r = client.get("/api/v1/suppliers", headers=token("accounts@thutosupplies.demo"))
    assert r.status_code == 403


def test_register_supplier_starts_pending(client, token):
    r = client.post("/api/v1/suppliers", json=NEW, headers=token("procurement@mics.demo"))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "PENDING"  # not ACTIVE until documents are verified


def test_exact_duplicate_registration_number_blocked(client, token):
    dup = {**NEW, "legal_name": "Totally Different Name"}
    r = client.post("/api/v1/suppliers", json=dup, headers=token("procurement@mics.demo"))
    assert r.status_code == 409
    assert r.json()["error"]["details"]["existing"][0]["legal_name"] == NEW["legal_name"]


def test_similar_name_needs_acknowledgement(client, token):
    body = {**NEW, "legal_name": "Ubuntu Cleaning Pty", "registration_number": "2023/999001/07"}
    first = client.post("/api/v1/suppliers", json=body, headers=token("procurement@mics.demo"))
    assert first.status_code == 409
    assert first.json()["error"]["details"]["similar"][0]["legal_name"] == "Ubuntu Cleaning"

    ack = client.post(
        "/api/v1/suppliers",
        json={**body, "acknowledge_similar": True},
        headers=token("procurement@mics.demo"),
    )
    assert ack.status_code == 201


def test_validation_errors_name_the_field(client, token):
    bad = {**NEW, "registration_number": "12345", "bbbee_level": 9}
    r = client.post("/api/v1/suppliers", json=bad, headers=token("procurement@mics.demo"))
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"registration_number", "bbbee_level"} <= fields


def test_women_ownership_cannot_exceed_black_ownership(client, token):
    bad = {
        **NEW,
        "registration_number": "2023/777777/07",
        "black_owned_pct": 51,
        "black_women_owned_pct": 60,
    }
    r = client.post("/api/v1/suppliers", json=bad, headers=token("procurement@mics.demo"))
    assert r.status_code == 422


def test_finance_officer_cannot_register_suppliers(client, token):
    r = client.post(
        "/api/v1/suppliers",
        json={**NEW, "registration_number": "2023/123123/07"},
        headers=token("finance@mics.demo"),
    )
    assert r.status_code == 403
