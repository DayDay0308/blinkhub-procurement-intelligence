from decimal import Decimal

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import internal_only, require_roles
from app.core.errors import NotFound
from app.db.session import get_db
from app.models import GoodsReceipt, Invoice, PurchaseOrder, User
from app.schemas import GoodsReceiptIn, GoodsReceiptOut, Page, PurchaseOrderOut, SupplierRef
from app.services.workflow import record_goods_receipt

router = APIRouter(prefix="/purchase-orders", tags=["purchase orders"])


def _sum_by_po(db: Session, column, po_col, *where) -> dict:
    rows = db.execute(select(po_col, func.sum(column)).where(*where).group_by(po_col))
    return {po_id: Decimal(total) for po_id, total in rows}


@router.get("", response_model=Page[PurchaseOrderOut])
def list_purchase_orders(db: Session = Depends(get_db), _: User = Depends(internal_only)):
    pos = db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.po_number)).unique().all()
    received = _sum_by_po(db, GoodsReceipt.amount_received, GoodsReceipt.po_id)
    invoiced = _sum_by_po(db, Invoice.amount, Invoice.po_id, Invoice.status != "REJECTED")
    items = [
        PurchaseOrderOut(
            id=po.id,
            po_number=po.po_number,
            supplier=SupplierRef.model_validate(po.supplier),
            department=po.department.name,
            category=po.category.name,
            total_amount=po.total_amount,
            status=po.status,
            received_amount=received.get(po.id, Decimal(0)),
            invoiced_amount=invoiced.get(po.id, Decimal(0)),
        )
        for po in pos
    ]
    return Page(items=items, total=len(items))


@router.post(
    "/{po_number}/goods-receipts",
    response_model=GoodsReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def receive_goods(
    po_number: str,
    data: GoodsReceiptIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("PROCUREMENT_OFFICER", "ADMIN")),
):
    """Record delivery evidence. Invoices waiting on this PO are re-matched automatically."""
    po = db.scalar(
        select(PurchaseOrder)
        .where(PurchaseOrder.po_number == po_number.upper())
        .with_for_update(of=PurchaseOrder)
    )
    if po is None:
        raise NotFound("Purchase order not found.")
    return record_goods_receipt(db, user, po, data.amount_received, data.received_date)
