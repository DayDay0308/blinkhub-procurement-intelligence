from tests.conftest import PASSWORD


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


def test_login_and_me(client, token):
    r = client.get("/api/v1/auth/me", headers=token("finance@mics.demo"))
    assert r.status_code == 200
    assert r.json()["role"] == "FINANCE_OFFICER"


def test_login_is_case_insensitive_on_email(client):
    r = client.post("/api/v1/auth/login", data={"username": "Finance@MICS.demo", "password": PASSWORD})
    assert r.status_code == 200


def test_wrong_password_and_unknown_email_look_identical(client):
    wrong = client.post("/api/v1/auth/login", data={"username": "finance@mics.demo", "password": "nope"})
    unknown = client.post("/api/v1/auth/login", data={"username": "ghost@mics.demo", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_protected_route_requires_token(client):
    r = client.get("/api/v1/invoices")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_tampered_token_rejected(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401
