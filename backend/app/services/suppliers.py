"""Supplier onboarding rules (case study Problem 1: duplicate profiles)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import Supplier
from app.schemas import SupplierCreate

NAME_SIMILARITY_THRESHOLD = 0.6  # pg_trgm similarity, 0..1


def find_exact_duplicates(db: Session, data: SupplierCreate) -> list[Supplier]:
    conds = [Supplier.registration_number == data.registration_number]
    if data.vat_number:
        conds.append(Supplier.vat_number == data.vat_number)
    if data.csd_number:
        conds.append(Supplier.csd_number == data.csd_number)
    return list(db.scalars(select(Supplier).where(or_(*conds))))


def find_similar_names(db: Session, name: str) -> list[tuple[Supplier, float]]:
    sim = func.similarity(Supplier.legal_name, name)
    rows = db.execute(
        select(Supplier, sim).where(sim >= NAME_SIMILARITY_THRESHOLD).order_by(sim.desc()).limit(5)
    )
    return [(s, round(float(score), 2)) for s, score in rows]


def next_supplier_code(db: Session) -> str:
    n = db.scalar(select(func.count()).select_from(Supplier)) or 0
    return f"SUP-{n + 1:05d}"


def register_supplier(db: Session, data: SupplierCreate) -> Supplier:
    """New suppliers start as PENDING: they cannot be ACTIVE until documents are verified."""
    exact = find_exact_duplicates(db, data)
    if exact:
        raise Conflict(
            "A supplier with the same registration, VAT or CSD number already exists.",
            {"existing": [{"id": str(s.id), "legal_name": s.legal_name} for s in exact]},
        )
    if not data.acknowledge_similar:
        similar = find_similar_names(db, data.legal_name)
        if similar:
            raise Conflict(
                "Possible duplicate: suppliers with similar names exist. "
                "Check them, then resubmit with acknowledge_similar=true "
                "if this is a new supplier.",
                {
                    "similar": [
                        {"id": str(s.id), "legal_name": s.legal_name, "similarity": score}
                        for s, score in similar
                    ]
                },
            )
    fields = data.model_dump(exclude={"acknowledge_similar"})
    supplier = Supplier(**fields, supplier_code=next_supplier_code(db), status="PENDING")
    db.add(supplier)
    db.flush()
    db.refresh(supplier)
    return supplier
