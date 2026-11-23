"""Dashboard figures must match the case-study analysis (notebook, dbt marts, Power BI)."""


def test_case_study_overview_matches_the_analysis(client, token):
    r = client.get("/api/v1/analytics/overview", headers=token("manager@mics.demo"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert float(d["spend"]["spend"]) == 4_027_000
    assert d["spend"]["smme_share"] == 0.1631
    assert d["top_suppliers"][0]["supplier"] == "Metro Logistics"
    assert {c["category"] for c in d["by_category"]} >= {"Transport", "Construction", "Cleaning"}


def test_case_study_overdue_invoices(client, token):
    inv = client.get("/api/v1/analytics/overview", headers=token("manager@mics.demo")).json()["invoices"]
    assert inv["overdue_invoices"] == 5
    assert float(inv["overdue_value"]) == 955_000
    assert inv["overdue_smme_invoices"] == 4  # Ubuntu, Thuto x2, Rapid


def test_suppliers_cannot_see_organisation_analytics(client, token):
    r = client.get("/api/v1/analytics/overview", headers=token("accounts@ubuntucleaning.demo"))
    assert r.status_code == 403


def test_invalid_data_source_rejected(client, token):
    r = client.get(
        "/api/v1/analytics/overview", params={"data_source": "MADE_UP"}, headers=token("manager@mics.demo")
    )
    assert r.status_code == 422
