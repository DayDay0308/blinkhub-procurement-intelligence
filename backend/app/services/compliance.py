"""Supplier compliance: are each supplier's documents present, verified and in date?

Requirements (configurable in REQUIREMENTS):
  TAX_CLEARANCE  - SARS tax compliance status (tax clearance) PIN letter
  BBBEE          - a B-BBEE certificate, or a sworn affidavit for EMEs/QSEs

State of each requirement, worst first:
  EXPIRED               the last verified document has passed its expiry date
  MISSING               nothing verified has ever been received
  PENDING_VERIFICATION  a document was uploaded and is waiting for procurement to check it
  EXPIRING              verified, but expires within `compliance_warning_days` (30)
  VALID                 verified and in date

Flow: supplier (or procurement) uploads -> UPLOADED -> procurement verifies with the
issue/expiry dates from the certificate -> VERIFIED (or REJECTED with a reason).
A daily job marks verified documents past their expiry as EXPIRED and reminds suppliers
and procurement once per document (notifications are idempotent).

Payment is not blocked here: the INCOMPLETE_COMPLIANCE risk rule flags payments made
to non-compliant suppliers, and the scorecard's compliance KPI uses the same documents.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound
from app.models import Document, Supplier, User
from app.services import audit
from app.services.notifications import notify, supplier_users, users_with_role
from app.services.workflow import Unprocessable

log = logging.getLogger(__name__)

REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "TAX_CLEARANCE": ("TAX_CLEARANCE",),
    "BBBEE": ("BBBEE_CERTIFICATE", "BBBEE_AFFIDAVIT"),
}
REQUIREMENT_LABEL = {"TAX_CLEARANCE": "Tax clearance", "BBBEE": "B-BBEE certificate or affidavit"}
STATE_ORDER = ["EXPIRED", "MISSING", "PENDING_VERIFICATION", "EXPIRING", "VALID"]
REVIEW_ROLES = ("PROCUREMENT_OFFICER", "ADMIN")

# Accepted files, recognised by their first bytes (not by the file name the client sends).
_SIGNATURES = {
    b"%PDF-": ("application/pdf", ".pdf"),
    b"\x89PNG": ("image/png", ".png"),
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
}

_STATUS_SQL = """
WITH req(requirement, doc_types) AS (
  VALUES ('TAX_CLEARANCE', ARRAY['TAX_CLEARANCE']::compliance.doc_type[]),
         ('BBBEE', ARRAY['BBBEE_CERTIFICATE','BBBEE_AFFIDAVIT']::compliance.doc_type[])
)
SELECT s.id AS supplier_id, r.requirement,
       v.id AS document_id, v.doc_type::text AS doc_type, v.expiry_date,
       (v.expiry_date - current_date) AS days_left,
       last_doc.id AS last_document_id, last_doc.expiry_date AS last_expiry,
       pending.id AS pending_document_id,
       CASE
         WHEN v.id IS NULL AND pending.id IS NOT NULL THEN 'PENDING_VERIFICATION'
         WHEN v.id IS NULL AND last_doc.id IS NOT NULL THEN 'EXPIRED'
         WHEN v.id IS NULL THEN 'MISSING'
         WHEN v.expiry_date < current_date + :warn THEN 'EXPIRING'
         ELSE 'VALID'
       END AS state
FROM core.suppliers s
CROSS JOIN req r
LEFT JOIN LATERAL (   -- best verified, in-date document
  SELECT d.id, d.doc_type, d.expiry_date FROM compliance.documents d
  WHERE d.supplier_id = s.id AND d.doc_type = ANY (r.doc_types) AND d.status = 'VERIFIED'
    AND coalesce(d.expiry_date, 'infinity') >= current_date
  ORDER BY d.expiry_date DESC NULLS FIRST LIMIT 1) v ON true
LEFT JOIN LATERAL (   -- last document that was ever valid (to tell EXPIRED from MISSING)
  SELECT d.id, d.expiry_date FROM compliance.documents d
  WHERE d.supplier_id = s.id AND d.doc_type = ANY (r.doc_types) AND d.status IN ('VERIFIED','EXPIRED')
  ORDER BY d.expiry_date DESC NULLS FIRST LIMIT 1) last_doc ON true
LEFT JOIN LATERAL (   -- waiting for procurement to check
  SELECT d.id FROM compliance.documents d
  WHERE d.supplier_id = s.id AND d.doc_type = ANY (r.doc_types) AND d.status IN ('UPLOADED','EXTRACTED')
  ORDER BY d.uploaded_at DESC LIMIT 1) pending ON true
WHERE s.status IN ('ACTIVE','PENDING') {where}
"""


def _rows(db: Session, supplier_id: UUID | None = None) -> list[dict]:
    where = "AND s.id = :sid" if supplier_id else ""
    params = {"warn": get_settings().compliance_warning_days, "sid": supplier_id}
    return [dict(r) for r in db.execute(text(_STATUS_SQL.format(where=where)), params).mappings()]


def _worst(states: list[str]) -> str:
    return min(states, key=STATE_ORDER.index) if states else "VALID"


def overview(db: Session) -> dict:
    """Compliance for every active or pending supplier, worst first, plus headline counts."""
    rows = _rows(db)
    suppliers = {
        s.id: s for s in db.scalars(select(Supplier).where(Supplier.id.in_({r["supplier_id"] for r in rows})))
    }
    paid_90 = dict(
        db.execute(
            text(
                "SELECT supplier_id, sum(amount) FROM p2p.invoices WHERE status = 'PAID' "
                "AND paid_at >= now() - interval '90 days' GROUP BY supplier_id"
            )
        ).all()
    )
    by_supplier: dict[UUID, list[dict]] = {}
    for r in rows:
        by_supplier.setdefault(r["supplier_id"], []).append(r)

    items = []
    for sid, reqs in by_supplier.items():
        s = suppliers[sid]
        state = _worst([r["state"] for r in reqs])
        items.append(
            {
                "supplier": {
                    "id": s.id,
                    "supplier_code": s.supplier_code,
                    "legal_name": s.legal_name,
                    "supplier_type": s.supplier_type,
                    "status": s.status,
                },
                "state": state,
                "requirements": [_requirement_out(r) for r in sorted(reqs, key=lambda r: r["requirement"])],
                "next_expiry": min((r["expiry_date"] for r in reqs if r["expiry_date"]), default=None),
                "paid_last_90_days": paid_90.get(sid, 0),
            }
        )
    items.sort(
        key=lambda i: (
            STATE_ORDER.index(i["state"]),
            i["next_expiry"] or date.max,
            i["supplier"]["legal_name"],
        )
    )

    counts = {st: sum(1 for i in items if i["state"] == st) for st in STATE_ORDER}
    at_risk = sum(i["paid_last_90_days"] for i in items if i["state"] in ("EXPIRED", "MISSING"))
    return {
        "warning_days": get_settings().compliance_warning_days,
        "suppliers": len(items),
        "by_state": counts,
        "awaiting_verification": sum(1 for r in rows if r["pending_document_id"]),
        "paid_to_non_compliant_90_days": at_risk,
        "items": items,
    }


def _requirement_out(r: dict) -> dict:
    return {
        "requirement": r["requirement"],
        "label": REQUIREMENT_LABEL[r["requirement"]],
        "state": r["state"],
        "expiry_date": r["expiry_date"] or (r["last_expiry"] if r["state"] == "EXPIRED" else None),
        "days_left": r["days_left"],
        "document_id": r["document_id"],
        "pending_document_id": r["pending_document_id"],
    }


def _doc_out(d: Document) -> dict:
    return {
        "id": d.id,
        "doc_type": d.doc_type,
        "status": d.status,
        "issue_date": d.issue_date,
        "expiry_date": d.expiry_date,
        "original_filename": d.original_filename,
        "size_bytes": d.size_bytes,
        "uploaded_at": d.uploaded_at,
        "verified_at": d.verified_at,
        "rejection_reason": d.rejection_reason,
        "has_file": not d.storage_key.startswith(("demo/", "synthetic/")),
    }


def _check_access(user: User, supplier_id: UUID) -> None:
    if user.role == "SUPPLIER" and user.supplier_id != supplier_id:
        raise Forbidden("Suppliers can only see their own documents")


def supplier_documents(db: Session, user: User, supplier_id: UUID) -> dict:
    _check_access(user, supplier_id)
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise NotFound("Supplier not found")
    reqs = _rows(db, supplier_id)
    docs = db.scalars(
        select(Document).where(Document.supplier_id == supplier_id).order_by(Document.uploaded_at.desc())
    ).all()
    return {
        "supplier": {"id": supplier.id, "legal_name": supplier.legal_name, "status": supplier.status},
        "state": _worst([r["state"] for r in reqs]) if reqs else None,
        "requirements": [_requirement_out(r) for r in sorted(reqs, key=lambda r: r["requirement"])],
        "documents": [_doc_out(d) for d in docs],
    }


def _sniff(content: bytes) -> tuple[str, str]:
    for magic, kind in _SIGNATURES.items():
        if content.startswith(magic):
            return kind
    raise Unprocessable("Upload a PDF, PNG or JPG file")


def upload(
    db: Session,
    user: User,
    supplier_id: UUID,
    doc_type: str,
    filename: str,
    content: bytes,
    expiry_date: date | None = None,
) -> dict:
    """Store the file and record it as UPLOADED. Procurement then verifies it."""
    _check_access(user, supplier_id)
    if user.role not in ("SUPPLIER", *REVIEW_ROLES):
        raise Forbidden("Only the supplier or procurement can upload compliance documents")
    if not db.get(Supplier, supplier_id):
        raise NotFound("Supplier not found")
    settings = get_settings()
    if not content:
        raise Unprocessable("The file is empty")
    if len(content) > settings.document_max_mb * 1024 * 1024:
        raise Unprocessable(f"Files can be at most {settings.document_max_mb} MB")
    content_type, ext = _sniff(content)
    sha = hashlib.sha256(content).hexdigest()

    doc_id = uuid.uuid4()
    key = f"{supplier_id}/{doc_id}{ext}"
    doc = Document(
        id=doc_id,
        supplier_id=supplier_id,
        doc_type=doc_type,
        storage_key=key,
        sha256=sha,
        status="UPLOADED",
        expiry_date=expiry_date,  # as stated by the uploader; confirmed at verification
        uploaded_by=user.id,
        original_filename=Path(filename or "document").name[:200],
        content_type=content_type,
        size_bytes=len(content),
    )
    db.add(doc)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as e:
        raise Conflict("This exact file has already been uploaded for this supplier") from e

    path = Path(settings.document_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    audit.record(db, user.id, "DOCUMENT_UPLOADED", "DOCUMENT", doc.id, None, _snap(doc))
    supplier = db.get(Supplier, supplier_id)
    notify(
        db,
        users_with_role(db, "PROCUREMENT_OFFICER"),
        "DOC_UPLOADED",
        "DOCUMENT",
        doc.id,
        f"{supplier.legal_name} uploaded a {_doc_label(doc_type)} to verify",
    )
    db.refresh(doc)
    return _doc_out(doc)


def _doc_label(doc_type: str) -> str:
    return doc_type.replace("_", " ").replace("BBBEE", "B-BBEE").lower().replace("b-bbee", "B-BBEE")


def _snap(d: Document) -> dict:
    return {
        "status": d.status,
        "doc_type": d.doc_type,
        "issue_date": d.issue_date,
        "expiry_date": d.expiry_date,
    }


def _pending(db: Session, doc_id: UUID) -> Document:
    doc = db.get(Document, doc_id, with_for_update=True)
    if not doc:
        raise NotFound("Document not found")
    if doc.status not in ("UPLOADED", "EXTRACTED"):
        raise Conflict(f"This document is already {doc.status.lower()}")
    return doc


def verify(db: Session, user: User, doc_id: UUID, issue_date: date, expiry_date: date) -> dict:
    """Procurement checks the certificate and confirms its dates."""
    doc = _pending(db, doc_id)
    if doc.uploaded_by == user.id:
        raise Forbidden("Someone other than the uploader must verify a document")
    if expiry_date <= issue_date:
        raise Unprocessable("The expiry date must be after the issue date")
    if expiry_date < date.today():
        raise Unprocessable("This document has already expired. Reject it and ask for a current one.")
    before = _snap(doc)
    doc.issue_date, doc.expiry_date = issue_date, expiry_date
    doc.status, doc.verified_by, doc.verified_at = "VERIFIED", user.id, datetime.now(UTC)
    db.flush()
    audit.record(db, user.id, "DOCUMENT_VERIFIED", "DOCUMENT", doc.id, before, _snap(doc))
    notify(
        db,
        supplier_users(db, doc.supplier_id),
        "DOC_VERIFIED",
        "DOCUMENT",
        doc.id,
        f"Your {_doc_label(doc.doc_type)} was accepted",
        f"Valid until {expiry_date:%d %b %Y}.",
    )
    return _doc_out(doc)


def reject(db: Session, user: User, doc_id: UUID, reason: str) -> dict:
    doc = _pending(db, doc_id)
    before = _snap(doc)
    doc.status, doc.rejection_reason = "REJECTED", reason
    db.flush()
    audit.record(
        db, user.id, "DOCUMENT_REJECTED", "DOCUMENT", doc.id, before, {**_snap(doc), "reason": reason}
    )
    notify(
        db,
        supplier_users(db, doc.supplier_id),
        "DOC_REJECTED",
        "DOCUMENT",
        doc.id,
        f"Your {_doc_label(doc.doc_type)} was not accepted",
        reason,
    )
    return _doc_out(doc)


def document_file(db: Session, user: User, doc_id: UUID) -> tuple[Path, Document]:
    doc = db.get(Document, doc_id)
    if not doc:
        raise NotFound("Document not found")
    _check_access(user, doc.supplier_id)
    path = Path(get_settings().document_dir) / doc.storage_key
    if not path.is_file():
        raise NotFound("No file is stored for this document (demonstration record)")
    return path, doc


def run_compliance_check(db: Session) -> dict[str, int]:
    """Daily job: expire documents past their date, then remind suppliers and procurement.

    Each reminder is sent once per document (or once per missing requirement), so the
    job can run any number of times.
    """
    expired = db.execute(
        text(
            "UPDATE compliance.documents SET status = 'EXPIRED' "
            "WHERE status = 'VERIFIED' AND expiry_date < current_date RETURNING id"
        )
    ).all()
    for (doc_id,) in expired:
        audit.record(
            db, None, "DOCUMENT_EXPIRED", "DOCUMENT", doc_id, {"status": "VERIFIED"}, {"status": "EXPIRED"}
        )

    procurement = users_with_role(db, "PROCUREMENT_OFFICER")
    names = dict(db.execute(text("SELECT id, legal_name FROM core.suppliers")).all())
    sent = {"EXPIRING": 0, "EXPIRED": 0, "MISSING": 0}
    for r in _rows(db):
        if r["state"] not in sent:
            continue
        label = REQUIREMENT_LABEL[r["requirement"]]
        name = names[r["supplier_id"]]
        if r["state"] == "EXPIRING":
            entity, kind = r["document_id"], "DOC_EXPIRING"
            title = f"{label} for {name} expires in {r['days_left']} days"
            body = "Upload the renewed document before it expires."
        elif r["state"] == "EXPIRED":
            entity, kind = r["last_document_id"], "DOC_EXPIRED"
            title = f"{label} for {name} has expired"
            body = "Payments to this supplier will be flagged until a current document is verified."
        else:
            entity, kind = r["supplier_id"], f"DOC_MISSING_{r['requirement']}"
            title = f"{label} for {name} is missing"
            body = "Upload it so the supplier can be paid without a compliance flag."
        sent[r["state"]] += notify(
            db,
            [*supplier_users(db, r["supplier_id"]), *procurement],
            kind,
            "DOCUMENT" if kind != f"DOC_MISSING_{r['requirement']}" else "SUPPLIER",
            entity,
            title,
            body,
        )
    result = {"documents_expired": len(expired), **{f"reminders_{k.lower()}": v for k, v in sent.items()}}
    log.info("compliance_check %s", result)
    return result
