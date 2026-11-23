"""Generate a synthetic year in a separate database and hold the risk engine to measured
detection rates. If a change to a rule or the generator lowers precision or recall, CI fails."""

import os
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import PurchaseOrder
from app.services.risk import run_risk_engine
from app.services.risk.evaluation import evaluate
from app.services.scorecard import scorecards
from seed.run import load
from seed.synthetic import Config, generate

MIGRATIONS = sorted((Path(__file__).resolve().parents[1] / "migrations" / "sql").glob("*.sql"))


@pytest.fixture(scope="module")
def synth():
    url = make_url(os.environ["DATABASE_URL"]).set(database="blinkhub_test_synthetic")
    admin = (
        f"host={url.host} port={url.port or 5432} user={url.username} password={url.password} dbname=postgres"
    )
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{url.database}"')
    engine = create_engine(url)
    with engine.begin() as conn:
        for sql in MIGRATIONS:
            conn.exec_driver_sql(sql.read_text())
    with Session(engine) as db, db.begin():
        load(db)
        counts = generate(db, Config())
        run = run_risk_engine(db)
    session = Session(engine)
    yield session, counts, run
    session.close()
    engine.dispose()


def test_synthetic_year_matches_the_brief(synth):
    db, counts, _ = synth
    assert counts["suppliers"] + 8 == 450
    spend = float(db.scalar(select(func.sum(PurchaseOrder.total_amount))))
    assert 80e6 < spend < 90e6  # brief: ~R85m a year


def test_rules_meet_detection_targets(synth):
    db, _, _ = synth
    ev = evaluate(db)
    rules = {r["code"]: r for r in ev["rules"]}
    for code, r in rules.items():
        if code == "ANOMALY_ML":
            continue
        assert r["recall"] >= 0.95, (code, r)
        assert r["precision_any"] >= 0.95, (code, r)
    assert rules["ANOMALY_ML"]["recall"] >= 0.8
    assert ev["overall"]["recall"] >= 0.95
    assert ev["overall"]["precision"] >= 0.85


def test_engine_runs_fast_enough_for_a_nightly_job(synth):
    _, _, run = synth
    assert run["duration_ms"] < 15_000


def test_scorecards_cover_active_suppliers(synth):
    db, _, _ = synth
    cards = scorecards(db)
    scored = [c for c in cards if c["status"] == "SCORED"]
    assert len(scored) > 300  # some active suppliers simply had no orders this year
    assert all(0 <= c["overall"] <= 100 for c in scored)
