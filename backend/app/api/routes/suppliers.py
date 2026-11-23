from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, internal_only, require_roles
from app.core.errors import Forbidden, NotFound
from app.db.session import get_db
from app.models import Supplier, User
from app.schemas import Page, Province, SupplierCreate, SupplierOut, SupplierType
from app.services.suppliers import register_supplier

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=Page[SupplierOut])
def list_suppliers(
    q: str | None = Query(default=None, max_length=100, description="Search name or code"),
    province: Province | None = None,
    supplier_type: SupplierType | None = None,
    status_: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(internal_only),
):
    stmt = select(Supplier)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Supplier.legal_name.ilike(like) | Supplier.supplier_code.ilike(like))
    if province:
        stmt = stmt.where(Supplier.province == province)
    if supplier_type:
        stmt = stmt.where(Supplier.supplier_type == supplier_type)
    if status_:
        stmt = stmt.where(Supplier.status == status_.upper())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Supplier.legal_name).limit(limit).offset(offset)).all()
    return Page(items=[SupplierOut.model_validate(s) for s in items], total=total or 0)


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Suppliers may only see their own profile.
    if user.role == "SUPPLIER" and user.supplier_id != supplier_id:
        raise Forbidden("Suppliers can only view their own profile.")
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFound("Supplier not found.")
    return supplier


@router.post("", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(
    data: SupplierCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("PROCUREMENT_OFFICER", "ADMIN")),
):
    return register_supplier(db, data)
