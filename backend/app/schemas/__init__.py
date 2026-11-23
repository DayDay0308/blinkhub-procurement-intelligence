from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

Province = Literal[
    "GAUTENG",
    "LIMPOPO",
    "KWAZULU_NATAL",
    "MPUMALANGA",
    "NORTH_WEST",
    "FREE_STATE",
    "EASTERN_CAPE",
    "WESTERN_CAPE",
    "NORTHERN_CAPE",
]
SupplierType = Literal["SMME", "LARGE_ENTERPRISE"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORM):
    id: UUID
    email: str
    full_name: str
    role: str
    department_id: UUID | None
    supplier_id: UUID | None


# ---------- suppliers ----------
class SupplierOut(ORM):
    id: UUID
    supplier_code: str
    legal_name: str
    trading_name: str | None
    registration_number: str | None
    csd_number: str | None
    province: str
    supplier_type: str
    enterprise_size: str | None
    bbbee_level: int | None
    status: str
    email: str | None


Str = Annotated[str, StringConstraints(strip_whitespace=True)]


class SupplierCreate(BaseModel):
    legal_name: Annotated[Str, StringConstraints(min_length=2, max_length=200)]
    trading_name: Annotated[Str, StringConstraints(max_length=200)] | None = None
    # CIPC format, e.g. 2021/631175/07
    registration_number: Annotated[Str, StringConstraints(pattern=r"^\d{4}/\d{6}/\d{2}$")]
    # SA VAT numbers are 10 digits starting with 4
    vat_number: Annotated[Str, StringConstraints(pattern=r"^4\d{9}$")] | None = None
    # National Treasury Central Supplier Database number
    csd_number: Annotated[Str, StringConstraints(pattern=r"^MAAA\d{7}$")] | None = None
    province: Province
    supplier_type: SupplierType
    bbbee_level: int | None = Field(default=None, ge=1, le=8)
    black_owned_pct: Decimal | None = Field(default=None, ge=0, le=100)
    black_women_owned_pct: Decimal | None = Field(default=None, ge=0, le=100)
    email: EmailStr | None = None
    phone: Annotated[Str, StringConstraints(pattern=r"^\+?[0-9 ]{9,15}$")] | None = None
    acknowledge_similar: bool = Field(
        default=False,
        description="Set true to register even though a supplier with a similar name exists.",
    )

    @model_validator(mode="after")
    def women_owned_within_black_owned(self):
        if (
            self.black_owned_pct is not None
            and self.black_women_owned_pct is not None
            and self.black_women_owned_pct > self.black_owned_pct
        ):
            raise ValueError("black_women_owned_pct cannot exceed black_owned_pct")
        return self


# ---------- invoices ----------
SlaState = Literal["PAID", "ON_TRACK", "WARNING", "ESCALATED", "BREACHED"]


class SupplierRef(ORM):
    id: UUID
    legal_name: str
    supplier_type: str


class UserRef(ORM):
    id: UUID
    full_name: str
    role: str


class InvoiceOut(BaseModel):
    id: UUID
    invoice_number: str
    supplier: SupplierRef
    po_number: str | None
    amount: Decimal
    status: str
    invoice_date: date
    received_at: datetime
    due_date: date
    paid_at: datetime | None
    days_outstanding: int
    ageing_bucket: Literal["0-30", "31-60", "61-90", "90+"]
    sla_state: SlaState
    exceptions: list[str]
    current_owner: UserRef | None = None


class InvoiceSubmit(BaseModel):
    invoice_number: Annotated[Str, StringConstraints(min_length=1, max_length=40)]
    po_number: Annotated[Str, StringConstraints(max_length=20)] | None = None
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    vat_amount: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=2)
    invoice_date: date
    supplier_id: UUID | None = Field(
        default=None, description="Required when staff capture an invoice; ignored for suppliers."
    )

    @model_validator(mode="after")
    def vat_not_more_than_total(self):
        if self.vat_amount > self.amount:
            raise ValueError("vat_amount cannot exceed amount")
        return self


class LinkPo(BaseModel):
    po_number: Annotated[Str, StringConstraints(min_length=1, max_length=20)]


class Decision(BaseModel):
    comment: Annotated[Str, StringConstraints(max_length=1000)] | None = None


class Rejection(BaseModel):
    reason: Annotated[Str, StringConstraints(min_length=5, max_length=1000)]


class PaymentOut(ORM):
    id: UUID
    invoice_id: UUID
    amount: Decimal
    paid_at: datetime
    reference: str


class TimelineEvent(BaseModel):
    at: datetime
    action: str
    by_role: str | None
    status: str | None
    note: str | None


class GoodsReceiptIn(BaseModel):
    amount_received: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    received_date: date


class GoodsReceiptOut(ORM):
    id: UUID
    grn_number: str
    po_id: UUID
    received_date: date
    amount_received: Decimal


class PurchaseOrderOut(BaseModel):
    id: UUID
    po_number: str
    supplier: SupplierRef
    department: str
    category: str
    total_amount: Decimal
    status: str
    received_amount: Decimal
    invoiced_amount: Decimal


class NotificationOut(ORM):
    id: UUID
    kind: str
    entity_type: str
    entity_id: UUID
    title: str
    body: str | None
    created_at: datetime
    read_at: datetime | None


class Page[T](BaseModel):
    items: list[T]
    total: int
