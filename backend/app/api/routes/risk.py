"""Risk monitoring: investigation queue, case management, rule tuning and evaluation.

Flags are risk indicators, not accusations. Only a person can CONFIRM or DISMISS a flag,
and doing so requires a written note; every decision goes to the tamper-evident audit log.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.errors import NotFound
from app.db.session import get_db
from app.models import FLAG_STATUSES, CaseNote, RiskFlag, RiskRule, User
from app.services import audit
from app.services.risk import run_risk_engine
from app.services.risk.evaluation import evaluate
from app.services.workflow import Unprocessable

router = APIRouter(prefix="/risk", tags=["risk"])

VIEWERS = require_roles("MANAGER", "AUDITOR", "FINANCE_OFFICER", "PROCUREMENT_OFFICER", "ADMIN")
INVESTIGATORS = require_roles("MANAGER", "AUDITOR")
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)]


class StatusChange(BaseModel):
    status: Literal["UNDER_REVIEW", "ESCALATED", "DISMISSED", "CONFIRMED", "OPEN"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class Assign(BaseModel):
    user_id: UUID


class NoteIn(BaseModel):
    note: Note


class RuleUpdate(BaseModel):
    params: dict | None = None
    is_enabled: bool | None = None


def _flag_out(f: RiskFlag, notes: list[CaseNote] | None = None) -> dict:
    out = {
        "id": f.id,
        "rule_code": f.rule_code,
        "rule_name": f.rule.name,
        "entity_type": f.entity_type,
        "entity_id": f.entity_id,
        "supplier": (
            {
                "id": f.supplier.id,
                "legal_name": f.supplier.legal_name,
                "supplier_type": f.supplier.supplier_type,
            }
            if f.supplier
            else None
        ),
        "score": float(f.score),
        "severity": f.severity,
        "status": f.status,
        "explanation": f.explanation,
        "assigned_to": f.assigned_to,
        "detected_at": f.detected_at,
        "last_seen_at": f.last_seen_at,
        "resolved_at": f.resolved_at,
    }
    if notes is not None:
        out["notes"] = [
            {
                "id": n.id,
                "author": n.author.full_name,
                "role": n.author.role,
                "note": n.note,
                "created_at": n.created_at,
            }
            for n in notes
        ]
    return out


@router.post("/run")
def run(db: Session = Depends(get_db), _: User = Depends(require_roles("MANAGER", "AUDITOR", "ADMIN"))):
    """Run every enabled rule now (also runs nightly in the worker)."""
    return run_risk_engine(db)


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(VIEWERS)):
    """Headline numbers for the risk dashboard."""
    by = (
        db.execute(
            text("""
        SELECT f.rule_code, r.name, f.severity::text AS severity, count(*) AS flags,
               coalesce(sum(i.amount), 0) AS invoice_value
        FROM risk.flags f JOIN risk.rules r ON r.code = f.rule_code
        LEFT JOIN p2p.invoices i ON f.entity_type = 'INVOICE' AND i.id = f.entity_id
        WHERE f.status IN ('OPEN', 'UNDER_REVIEW', 'ESCALATED')
        GROUP BY 1, 2, 3 ORDER BY 1, 3
    """)
        )
        .mappings()
        .all()
    )
    statuses = dict(db.execute(select(RiskFlag.status, func.count()).group_by(RiskFlag.status)).all())
    return {
        "open_flags": sum(r["flags"] for r in by),
        "value_under_review": sum(r["invoice_value"] for r in by),
        "by_rule_and_severity": [dict(r) for r in by],
        "by_status": {s: statuses.get(s, 0) for s in FLAG_STATUSES},
    }


@router.get("/flags")
def list_flags(
    status: str | None = Query(default=None, description="e.g. OPEN; default = open + in progress"),
    severity: str | None = None,
    rule_code: str | None = None,
    supplier_id: UUID | None = None,
    assigned_to_me: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(VIEWERS),
):
    stmt = select(RiskFlag)
    if status:
        stmt = stmt.where(RiskFlag.status == status.upper())
    else:
        stmt = stmt.where(RiskFlag.status.in_(("OPEN", "UNDER_REVIEW", "ESCALATED")))
    if severity:
        stmt = stmt.where(RiskFlag.severity == severity.upper())
    if rule_code:
        stmt = stmt.where(RiskFlag.rule_code == rule_code.upper())
    if supplier_id:
        stmt = stmt.where(RiskFlag.supplier_id == supplier_id)
    if assigned_to_me:
        stmt = stmt.where(RiskFlag.assigned_to == user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        db.scalars(
            stmt.order_by(RiskFlag.score.desc(), RiskFlag.detected_at.desc()).limit(limit).offset(offset)
        )
        .unique()
        .all()
    )
    return {"items": [_flag_out(f) for f in rows], "total": total}


def _get(db: Session, flag_id: UUID, lock: bool = False) -> RiskFlag:
    stmt = select(RiskFlag).where(RiskFlag.id == flag_id)
    if lock:
        stmt = stmt.with_for_update(of=RiskFlag)
    f = db.scalars(stmt).unique().first()
    if f is None:
        raise NotFound("Flag not found.")
    return f


@router.get("/flags/{flag_id}")
def get_flag(flag_id: UUID, db: Session = Depends(get_db), _: User = Depends(VIEWERS)):
    f = _get(db, flag_id)
    notes = (
        db.scalars(select(CaseNote).where(CaseNote.flag_id == f.id).order_by(CaseNote.created_at))
        .unique()
        .all()
    )
    return _flag_out(f, list(notes))


@router.post("/flags/{flag_id}/status")
def change_status(
    flag_id: UUID, data: StatusChange, db: Session = Depends(get_db), user: User = Depends(INVESTIGATORS)
):
    f = _get(db, flag_id, lock=True)
    final = data.status in ("DISMISSED", "CONFIRMED")
    if final and (not data.note or len(data.note) < 10):
        raise Unprocessable(
            "Confirming or dismissing a flag needs a note of at least 10 characters explaining the finding."
        )
    if f.status in ("DISMISSED", "CONFIRMED") and user.role != "MANAGER":
        raise Unprocessable("This flag is closed; only a manager can reopen it.")
    before = {"status": f.status}
    f.status = data.status
    f.resolved_at, f.resolved_by = (datetime.now(UTC), user.id) if final else (None, None)
    if data.note:
        db.add(CaseNote(flag_id=f.id, author_id=user.id, note=f"[{data.status}] {data.note}"))
    db.flush()
    audit.record(
        db,
        user.id,
        f"RISK_FLAG_{data.status}",
        "RISK_FLAG",
        f.id,
        before,
        {"status": f.status, "note": data.note},
    )
    return get_flag(flag_id, db, user)


@router.post("/flags/{flag_id}/assign")
def assign(flag_id: UUID, data: Assign, db: Session = Depends(get_db), user: User = Depends(INVESTIGATORS)):
    f = _get(db, flag_id, lock=True)
    assignee = db.get(User, data.user_id)
    if assignee is None or assignee.role not in (
        "AUDITOR",
        "MANAGER",
        "FINANCE_OFFICER",
        "PROCUREMENT_OFFICER",
    ):
        raise Unprocessable("Flags can only be assigned to internal investigators.")
    before = {"assigned_to": f.assigned_to}
    f.assigned_to = assignee.id
    if f.status == "OPEN":
        f.status = "UNDER_REVIEW"
    db.flush()
    audit.record(db, user.id, "RISK_FLAG_ASSIGNED", "RISK_FLAG", f.id, before, {"assigned_to": assignee.id})
    return _flag_out(f)


@router.post("/flags/{flag_id}/notes")
def add_note(flag_id: UUID, data: NoteIn, db: Session = Depends(get_db), user: User = Depends(VIEWERS)):
    f = _get(db, flag_id)
    db.add(CaseNote(flag_id=f.id, author_id=user.id, note=data.note))
    db.flush()
    return get_flag(flag_id, db, user)


@router.get("/rules")
def rules(db: Session = Depends(get_db), _: User = Depends(VIEWERS)):
    return [
        {
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "severity": r.severity,
            "params": r.params,
            "is_enabled": r.is_enabled,
        }
        for r in db.scalars(select(RiskRule).order_by(RiskRule.code))
    ]


@router.patch("/rules/{code}")
def update_rule(
    code: str, data: RuleUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN"))
):
    """Tune thresholds without a deploy. Only keys the rule already has can be changed."""
    rule = db.get(RiskRule, code.upper())
    if rule is None:
        raise NotFound("Rule not found.")
    before = {"params": rule.params, "is_enabled": rule.is_enabled}
    if data.params is not None:
        unknown = set(data.params) - set(rule.params)
        if unknown:
            raise Unprocessable(f"Unknown parameter(s) for {rule.code}: {sorted(unknown)}")
        rule.params = {**rule.params, **data.params}
    if data.is_enabled is not None:
        rule.is_enabled = data.is_enabled
    db.flush()
    audit.record(
        db,
        user.id,
        "RISK_RULE_UPDATED",
        "RISK_RULE",
        user.id,
        before,
        {"code": rule.code, "params": rule.params, "is_enabled": rule.is_enabled},
    )
    return {"code": rule.code, "params": rule.params, "is_enabled": rule.is_enabled}


@router.get("/evaluation")
def evaluation(
    db: Session = Depends(get_db), _: User = Depends(require_roles("MANAGER", "AUDITOR", "ADMIN"))
):
    """Precision and recall per rule against the planted anomalies in the synthetic data."""
    return evaluate(db)
