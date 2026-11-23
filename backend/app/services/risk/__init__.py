"""Risk engine: runs every enabled rule and stores the results as flags for investigation.

Flags are upserted on (rule, entity): re-running updates the score and evidence but never
duplicates a flag or overwrites an investigator's decision (status, assignee, notes).
"""

import json
import time

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import RiskRule
from app.services.risk import ml
from app.services.risk.rules import SQL_RULES


def severity_for(score: float) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "LOW"


UPSERT = text("""
INSERT INTO risk.flags (rule_code, entity_type, entity_id, supplier_id, score, severity, explanation,
                        detected_at, last_seen_at)
VALUES (:rule, :etype, :eid, :sid, :score, CAST(:severity AS risk.severity), CAST(:explanation AS jsonb),
        now(), now())
ON CONFLICT (rule_code, entity_type, entity_id) DO UPDATE
SET score = EXCLUDED.score, severity = EXCLUDED.severity, explanation = EXCLUDED.explanation,
    supplier_id = EXCLUDED.supplier_id, last_seen_at = now()
""")


def run_risk_engine(db: Session) -> dict:
    started = time.perf_counter()
    rules = {r.code: r for r in db.scalars(select(RiskRule).where(RiskRule.is_enabled))}
    results: dict[str, int] = {}

    candidates: list[tuple[str, tuple]] = []
    for rule in SQL_RULES:
        if rule.code not in rules:
            continue
        sql = rule.sql.replace(":p->>", "CAST(:p AS jsonb)->>")
        rows = db.execute(text(sql), {"p": json.dumps(rules[rule.code].params)}).all()
        candidates += [(rule.code, tuple(r)) for r in rows]
        results[rule.code] = len(rows)

    if "ANOMALY_ML" in rules:
        rows = ml.detect(db, rules["ANOMALY_ML"].params)
        candidates += [("ANOMALY_ML", r) for r in rows]
        results["ANOMALY_ML"] = len(rows)

    if candidates:
        db.execute(
            UPSERT,
            [
                {
                    "rule": code,
                    "etype": etype,
                    "eid": eid,
                    "sid": sid,
                    "score": score,
                    "severity": severity_for(score),
                    "explanation": json.dumps(expl, default=str),
                }
                for code, (etype, eid, sid, score, expl) in candidates
            ],
        )
    db.flush()
    return {
        "flags_by_rule": results,
        "total": len(candidates),
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }
