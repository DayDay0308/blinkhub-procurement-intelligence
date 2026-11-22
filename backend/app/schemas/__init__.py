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


class Page[T](BaseModel):
    items: list[T]
    total: int
