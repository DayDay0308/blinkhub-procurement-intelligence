"""Tests run against a real PostgreSQL database (not SQLite), because many business
rules live in Postgres constraints, enums and triggers."""

import os

os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://blinkhub:blinkhub@localhost:5432/blinkhub_test"
)
os.environ["ENVIRONMENT"] = "test"

from collections.abc import Iterator  # noqa: E402

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

PASSWORD = "Demo@2026!"


def _recreate_database(url: str) -> None:
    u = make_url(url)
    admin = f"host={u.host} port={u.port or 5432} user={u.username} password={u.password} dbname=postgres"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{u.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{u.database}"')


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    _recreate_database(os.environ["DATABASE_URL"])
    here = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "migrations"))
    command.upgrade(cfg, "head")

    from app.db.session import SessionLocal
    from seed.run import load

    with SessionLocal() as db, db.begin():
        load(db)
    yield


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="session")
def token(client):
    cache: dict[str, str] = {}

    def get(email: str) -> dict[str, str]:
        if email not in cache:
            r = client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD})
            assert r.status_code == 200, r.text
            cache[email] = r.json()["access_token"]
        return {"Authorization": f"Bearer {cache[email]}"}

    return get


@pytest.fixture
def db():
    """A session whose changes are always rolled back."""
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
