"""ORM mappings for the tables the API uses.

The schema itself is owned by SQL migrations (migrations/sql); these classes map
onto it and never create tables. Postgres enum types already exist, hence
create_type=False.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Computed, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def pg_enum(name: str, schema: str, *values: str) -> ENUM:
    return ENUM(*values, name=name, schema=schema, create_type=False)


PROVINCES = (
    "GAUTENG",
    "LIMPOPO",
    "KWAZULU_NATAL",
    "MPUMALANGA",
    "NORTH_WEST",
    "FREE_STATE",
    "EASTERN_CAPE",
    "WESTERN_CAPE",
    "NORTHERN_CAPE",
)
ROLES = (
    "ADMIN",
    "PROCUREMENT_OFFICER",
    "FINANCE_OFFICER",
    "APPROVER",
    "MANAGER",
    "AUDITOR",
    "SUPPLIER",
)
INVOICE_STATUSES = (
    "SUBMITTED",
    "MATCHING",
    "EXCEPTION",
    "PENDING_APPROVAL",
    "APPROVED",
    "SCHEDULED",
    "PAID",
    "REJECTED",
    "ON_HOLD",
)

Province = pg_enum("province", "core", *PROVINCES)
UserRole = pg_enum("user_role", "core", *ROLES)
SupplierType = pg_enum("supplier_type", "core", "SMME", "LARGE_ENTERPRISE")
EnterpriseSize = pg_enum("enterprise_size", "core", "EME", "QSE", "GENERIC")
SupplierStatus = pg_enum("supplier_status", "core", "PENDING", "ACTIVE", "SUSPENDED", "INACTIVE", "BLOCKED")
PoStatus = pg_enum(
    "po_status",
    "p2p",
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "PARTIALLY_RECEIVED",
    "RECEIVED",
    "CLOSED",
    "CANCELLED",
)
InvoiceStatus = pg_enum("invoice_status", "p2p", *INVOICE_STATUSES)
Severity = pg_enum("severity", "risk", "LOW", "MEDIUM", "HIGH", "CRITICAL")
FLAG_STATUSES = ("OPEN", "UNDER_REVIEW", "ESCALATED", "DISMISSED", "CONFIRMED")
FlagStatus = pg_enum("flag_status", "risk", *FLAG_STATUSES)
DocType = pg_enum(
    "doc_type",
    "compliance",
    "TAX_CLEARANCE",
    "BBBEE_CERTIFICATE",
    "BBBEE_AFFIDAVIT",
    "CIPC_REGISTRATION",
    "BANK_CONFIRMATION",
    "CSD_REPORT",
    "COID_LETTER",
    "OTHER",
)
DocStatus = pg_enum("doc_status", "compliance", "UPLOADED", "EXTRACTED", "VERIFIED", "REJECTED", "EXPIRED")
OpportunityStatus = pg_enum(
    "opportunity_status", "sourcing", "DRAFT", "OPEN", "CLOSED", "EVALUATING", "AWARDED", "CANCELLED"
)
ApprovalDecision = pg_enum("approval_decision", "p2p", "PENDING", "APPROVED", "REJECTED", "ESCALATED")


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = {"schema": "core"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    province: Mapped[str | None] = mapped_column(Province)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = {"schema": "core"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.categories.id"))


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = {"schema": "core"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    supplier_code: Mapped[str] = mapped_column(String(20), unique=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    trading_name: Mapped[str | None] = mapped_column(String(200))
    registration_number: Mapped[str | None] = mapped_column(String(30), unique=True)
    vat_number: Mapped[str | None] = mapped_column(String(15), unique=True)
    csd_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    province: Mapped[str] = mapped_column(Province)
    supplier_type: Mapped[str] = mapped_column(SupplierType)
    enterprise_size: Mapped[str | None] = mapped_column(EnterpriseSize)
    bbbee_level: Mapped[int | None]
    black_owned_pct: Mapped[Decimal | None]
    black_women_owned_pct: Mapped[Decimal | None]
    status: Mapped[str] = mapped_column(SupplierStatus, server_default="PENDING")
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(String(200), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(UserRole)
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.departments.id"))
    supplier_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.suppliers.id"))
    approval_limit: Mapped[Decimal | None]
    is_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = {"schema": "p2p"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    po_number: Mapped[str] = mapped_column(String(20), unique=True)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("core.suppliers.id"))
    department_id: Mapped[UUID] = mapped_column(ForeignKey("core.departments.id"))
    category_id: Mapped[UUID] = mapped_column(ForeignKey("core.categories.id"))
    contract_id: Mapped[UUID | None]
    delivery_province: Mapped[str | None] = mapped_column(Province)
    total_amount: Mapped[Decimal]
    status: Mapped[str] = mapped_column(PoStatus, server_default="DRAFT")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("core.users.id"))
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("core.users.id"))
    approved_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expected_delivery_date: Mapped[date | None]

    supplier: Mapped[Supplier] = relationship(lazy="joined")
    department: Mapped[Department] = relationship(lazy="joined")
    category: Mapped[Category] = relationship(lazy="joined")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = {"schema": "p2p"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("core.suppliers.id"))
    po_id: Mapped[UUID | None] = mapped_column(ForeignKey("p2p.purchase_orders.id"))
    invoice_number: Mapped[str] = mapped_column(String(40))
    invoice_number_norm: Mapped[str] = mapped_column(
        String(40),
        Computed("upper(regexp_replace(invoice_number, '[^A-Za-z0-9]', '', 'g'))", persisted=True),
    )
    amount: Mapped[Decimal]
    vat_amount: Mapped[Decimal] = mapped_column(server_default="0")
    invoice_date: Mapped[date]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    due_date: Mapped[date]
    status: Mapped[str] = mapped_column(InvoiceStatus, server_default="SUBMITTED")
    channel: Mapped[str] = mapped_column(String(20), server_default="PORTAL")
    current_approver_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.users.id"))
    document_key: Mapped[str | None]
    paid_at: Mapped[datetime | None]
    match_exceptions: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")

    supplier: Mapped[Supplier] = relationship(lazy="joined")
    purchase_order: Mapped[PurchaseOrder | None] = relationship(lazy="joined")
    current_approver: Mapped[User | None] = relationship(lazy="joined")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    __table_args__ = {"schema": "p2p"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    grn_number: Mapped[str] = mapped_column(String(20), unique=True)
    po_id: Mapped[UUID] = mapped_column(ForeignKey("p2p.purchase_orders.id"))
    received_date: Mapped[date]
    amount_received: Mapped[Decimal]
    received_by: Mapped[UUID] = mapped_column(ForeignKey("core.users.id"))
    evidence_key: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class InvoiceApproval(Base):
    __tablename__ = "invoice_approvals"
    __table_args__ = {"schema": "p2p"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("p2p.invoices.id"))
    step: Mapped[int]
    approver_id: Mapped[UUID] = mapped_column(ForeignKey("core.users.id"))
    decision: Mapped[str] = mapped_column(ApprovalDecision, server_default="PENDING")
    comment: Mapped[str | None]
    assigned_at: Mapped[datetime] = mapped_column(server_default=func.now())
    decided_at: Mapped[datetime | None]


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    __table_args__ = {"schema": "compliance"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("core.suppliers.id"))
    bank_name: Mapped[str] = mapped_column(String(80))
    account_number_enc: Mapped[bytes] = mapped_column(LargeBinary)
    account_last4: Mapped[str] = mapped_column(String(4))
    branch_code: Mapped[str] = mapped_column(String(10))
    verified: Mapped[bool] = mapped_column(server_default="false")
    effective_from: Mapped[datetime] = mapped_column(server_default=func.now())
    effective_to: Mapped[datetime | None]
    changed_by: Mapped[UUID | None] = mapped_column(ForeignKey("core.users.id"))


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = {"schema": "p2p"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("p2p.invoices.id"))
    bank_account_id: Mapped[UUID] = mapped_column(ForeignKey("compliance.bank_accounts.id"))
    amount: Mapped[Decimal]
    paid_at: Mapped[datetime]
    reference: Mapped[str] = mapped_column(String(40), unique=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = {"schema": "core"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(ForeignKey("core.users.id"))
    kind: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    read_at: Mapped[datetime | None]


class SupplierCategory(Base):
    __tablename__ = "supplier_categories"
    __table_args__ = {"schema": "core"}
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("core.suppliers.id"), primary_key=True)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("core.categories.id"), primary_key=True)


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = {"schema": "p2p"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    po_id: Mapped[UUID] = mapped_column(ForeignKey("p2p.purchase_orders.id"))
    line_no: Mapped[int]
    item_code: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal]
    unit: Mapped[str] = mapped_column(String(20), server_default="EA")
    unit_price: Mapped[Decimal]
    line_total: Mapped[Decimal] = mapped_column(Computed("round(quantity * unit_price, 2)", persisted=True))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "compliance"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("core.suppliers.id"))
    doc_type: Mapped[str] = mapped_column(DocType)
    storage_key: Mapped[str]
    sha256: Mapped[str] = mapped_column(String(64))
    issue_date: Mapped[date | None]
    expiry_date: Mapped[date | None]
    status: Mapped[str] = mapped_column(DocStatus, server_default="UPLOADED")
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)
    extraction_confidence: Mapped[Decimal | None]
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("core.users.id"))
    verified_at: Mapped[datetime | None]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    uploaded_by: Mapped[UUID | None] = mapped_column(ForeignKey("core.users.id"))
    original_filename: Mapped[str | None] = mapped_column(String(200))
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None]
    rejection_reason: Mapped[str | None]


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = {"schema": "sourcing"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    reference: Mapped[str] = mapped_column(String(30), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None]
    category_id: Mapped[UUID] = mapped_column(ForeignKey("core.categories.id"))
    department_id: Mapped[UUID] = mapped_column(ForeignKey("core.departments.id"))
    province: Mapped[str | None] = mapped_column(Province)
    estimated_value: Mapped[Decimal | None]
    smme_set_aside: Mapped[bool] = mapped_column(server_default="false")
    closes_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(OpportunityStatus, server_default="DRAFT")
    awarded_supplier_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.suppliers.id"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("core.users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Quotation(Base):
    __tablename__ = "quotations"
    __table_args__ = {"schema": "sourcing"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    opportunity_id: Mapped[UUID] = mapped_column(ForeignKey("sourcing.opportunities.id"))
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("core.suppliers.id"))
    amount: Mapped[Decimal]
    submitted_at: Mapped[datetime] = mapped_column(server_default=func.now())
    score: Mapped[Decimal | None]


class RiskRule(Base):
    __tablename__ = "rules"
    __table_args__ = {"schema": "risk"}
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str]
    severity: Mapped[str] = mapped_column(Severity)
    params: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    is_enabled: Mapped[bool] = mapped_column(server_default="true")


class RiskFlag(Base):
    __tablename__ = "flags"
    __table_args__ = {"schema": "risk"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    rule_code: Mapped[str] = mapped_column(ForeignKey("risk.rules.code"))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[UUID]
    supplier_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.suppliers.id"))
    score: Mapped[Decimal]
    severity: Mapped[str] = mapped_column(Severity)
    explanation: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(FlagStatus, server_default="OPEN")
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("core.users.id"))
    detected_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("core.users.id"))

    rule: Mapped[RiskRule] = relationship(lazy="joined")
    supplier: Mapped[Supplier | None] = relationship(lazy="joined")


class CaseNote(Base):
    __tablename__ = "case_notes"
    __table_args__ = {"schema": "risk"}
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    flag_id: Mapped[UUID] = mapped_column(ForeignKey("risk.flags.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("core.users.id"))
    note: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    author: Mapped[User] = relationship(lazy="joined")
