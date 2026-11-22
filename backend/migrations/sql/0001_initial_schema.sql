-- =====================================================================
-- BlinkHub Procurement Intelligence & Risk Engine — operational schema (migration 0001)
-- PostgreSQL 16
-- Schemas:
--   core      : master data (users, departments, suppliers, categories)
--   compliance: supplier documents and bank details
--   p2p       : procure-to-pay transactions (contracts, POs, GRNs, invoices, payments)
--   sourcing  : opportunities and quotations (SMME marketplace)
--   risk      : risk rules, flags and investigation cases
--   audit     : tamper-evident audit log
--   analytics : dbt-managed marts (created by dbt, not here)
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), encryption helpers
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy matching for duplicate detection

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS compliance;
CREATE SCHEMA IF NOT EXISTS p2p;
CREATE SCHEMA IF NOT EXISTS sourcing;
CREATE SCHEMA IF NOT EXISTS risk;
CREATE SCHEMA IF NOT EXISTS audit;

-- ---------------------------------------------------------------------
-- Enumerations
-- ---------------------------------------------------------------------
CREATE TYPE core.province AS ENUM
  ('GAUTENG','LIMPOPO','KWAZULU_NATAL','MPUMALANGA','NORTH_WEST',
   'FREE_STATE','EASTERN_CAPE','WESTERN_CAPE','NORTHERN_CAPE');
CREATE TYPE core.user_role AS ENUM
  ('ADMIN','PROCUREMENT_OFFICER','FINANCE_OFFICER','APPROVER','MANAGER','AUDITOR','SUPPLIER');
CREATE TYPE core.supplier_type AS ENUM ('SMME','LARGE_ENTERPRISE');
CREATE TYPE core.enterprise_size AS ENUM ('EME','QSE','GENERIC');   -- B-BBEE size band, when known
CREATE TYPE core.supplier_status AS ENUM ('PENDING','ACTIVE','SUSPENDED','INACTIVE','BLOCKED');
CREATE TYPE compliance.doc_type AS ENUM
  ('TAX_CLEARANCE','BBBEE_CERTIFICATE','BBBEE_AFFIDAVIT','CIPC_REGISTRATION',
   'BANK_CONFIRMATION','CSD_REPORT','COID_LETTER','OTHER');
CREATE TYPE compliance.doc_status AS ENUM ('UPLOADED','EXTRACTED','VERIFIED','REJECTED','EXPIRED');
CREATE TYPE p2p.contract_status AS ENUM ('DRAFT','ACTIVE','EXPIRED','TERMINATED');
CREATE TYPE p2p.po_status AS ENUM ('DRAFT','PENDING_APPROVAL','APPROVED','PARTIALLY_RECEIVED','RECEIVED','CLOSED','CANCELLED');
CREATE TYPE p2p.invoice_status AS ENUM
  ('SUBMITTED','MATCHING','EXCEPTION','PENDING_APPROVAL','APPROVED','SCHEDULED','PAID','REJECTED','ON_HOLD');
CREATE TYPE p2p.approval_decision AS ENUM ('PENDING','APPROVED','REJECTED','ESCALATED');
CREATE TYPE sourcing.opportunity_status AS ENUM ('DRAFT','OPEN','CLOSED','EVALUATING','AWARDED','CANCELLED');
CREATE TYPE risk.severity AS ENUM ('LOW','MEDIUM','HIGH','CRITICAL');
CREATE TYPE risk.flag_status AS ENUM ('OPEN','UNDER_REVIEW','ESCALATED','DISMISSED','CONFIRMED');

-- ---------------------------------------------------------------------
-- CORE
-- ---------------------------------------------------------------------
CREATE TABLE core.departments (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code          varchar(20)  NOT NULL UNIQUE,
  name          varchar(120) NOT NULL UNIQUE,
  province      core.province,
  created_at    timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE core.budgets (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id  uuid NOT NULL REFERENCES core.departments(id),
  fiscal_year    smallint NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
  amount         numeric(14,2) NOT NULL CHECK (amount >= 0),
  UNIQUE (department_id, fiscal_year)
);

CREATE TABLE core.categories (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code       varchar(20)  NOT NULL UNIQUE,
  name       varchar(120) NOT NULL,
  parent_id  uuid REFERENCES core.categories(id)
);

CREATE TABLE core.suppliers (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  supplier_code          varchar(20)  NOT NULL UNIQUE,
  legal_name             varchar(200) NOT NULL,
  trading_name           varchar(200),
  registration_number    varchar(30)  UNIQUE,           -- CIPC number: dedup key
  vat_number             varchar(15)  UNIQUE,
  csd_number             varchar(20)  UNIQUE,           -- National Treasury CSD (MAAA...)
  province               core.province NOT NULL,
  supplier_type          core.supplier_type NOT NULL,
  enterprise_size        core.enterprise_size,
  bbbee_level            smallint CHECK (bbbee_level BETWEEN 1 AND 8),  -- NULL = non-compliant
  black_owned_pct        numeric(5,2) CHECK (black_owned_pct BETWEEN 0 AND 100),
  black_women_owned_pct  numeric(5,2) CHECK (black_women_owned_pct BETWEEN 0 AND 100),
  status                 core.supplier_status NOT NULL DEFAULT 'PENDING',
  email                  varchar(200),
  phone                  varchar(30),
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  CHECK (black_women_owned_pct IS NULL OR black_owned_pct IS NULL
         OR black_women_owned_pct <= black_owned_pct)
);
CREATE INDEX ix_suppliers_name_trgm ON core.suppliers USING gin (legal_name gin_trgm_ops);

CREATE TABLE core.supplier_categories (
  supplier_id  uuid NOT NULL REFERENCES core.suppliers(id) ON DELETE CASCADE,
  category_id  uuid NOT NULL REFERENCES core.categories(id),
  PRIMARY KEY (supplier_id, category_id)
);

CREATE TABLE core.users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          varchar(200) NOT NULL UNIQUE,
  full_name      varchar(150) NOT NULL,
  password_hash  text NOT NULL,
  role           core.user_role NOT NULL,
  department_id  uuid REFERENCES core.departments(id),
  supplier_id    uuid REFERENCES core.suppliers(id),
  approval_limit numeric(14,2) CHECK (approval_limit >= 0),
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  -- supplier users must belong to a supplier; internal users must not
  CHECK ((role = 'SUPPLIER') = (supplier_id IS NOT NULL))
);

-- ---------------------------------------------------------------------
-- COMPLIANCE
-- ---------------------------------------------------------------------
CREATE TABLE compliance.documents (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  supplier_id     uuid NOT NULL REFERENCES core.suppliers(id) ON DELETE CASCADE,
  doc_type        compliance.doc_type NOT NULL,
  storage_key     text NOT NULL,                 -- object key in MinIO / S3
  sha256          char(64) NOT NULL,             -- detects the same file uploaded twice
  issue_date      date,
  expiry_date     date,
  status          compliance.doc_status NOT NULL DEFAULT 'UPLOADED',
  extracted_data  jsonb,                         -- fields pulled by the document-AI step
  extraction_confidence numeric(4,3),
  verified_by     uuid REFERENCES core.users(id),
  verified_at     timestamptz,
  uploaded_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (expiry_date IS NULL OR issue_date IS NULL OR expiry_date > issue_date)
);
CREATE INDEX ix_documents_expiry ON compliance.documents (expiry_date) WHERE status = 'VERIFIED';

CREATE TABLE compliance.bank_accounts (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  supplier_id        uuid NOT NULL REFERENCES core.suppliers(id),
  bank_name          varchar(80) NOT NULL,
  account_number_enc bytea NOT NULL,             -- encrypted at rest (POPIA)
  account_last4      char(4) NOT NULL,           -- only value shown in the UI
  branch_code        varchar(10) NOT NULL,
  verified           boolean NOT NULL DEFAULT false,
  effective_from     timestamptz NOT NULL DEFAULT now(),
  effective_to       timestamptz,                -- history kept: needed for the bank-change rule
  changed_by         uuid REFERENCES core.users(id)
);
CREATE UNIQUE INDEX ux_bank_current ON compliance.bank_accounts (supplier_id) WHERE effective_to IS NULL;

-- ---------------------------------------------------------------------
-- P2P (procure-to-pay)
-- ---------------------------------------------------------------------
CREATE TABLE p2p.contracts (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_number  varchar(30) NOT NULL UNIQUE,
  supplier_id      uuid NOT NULL REFERENCES core.suppliers(id),
  department_id    uuid NOT NULL REFERENCES core.departments(id),
  category_id      uuid REFERENCES core.categories(id),
  title            varchar(200) NOT NULL,
  contract_value   numeric(14,2) NOT NULL CHECK (contract_value > 0),
  start_date       date NOT NULL,
  end_date         date NOT NULL,
  owner_id         uuid REFERENCES core.users(id),
  status           p2p.contract_status NOT NULL DEFAULT 'DRAFT',
  CHECK (end_date > start_date)
);

CREATE TABLE p2p.purchase_orders (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  po_number      varchar(20) NOT NULL UNIQUE,
  supplier_id    uuid NOT NULL REFERENCES core.suppliers(id),
  department_id  uuid NOT NULL REFERENCES core.departments(id),
  category_id    uuid NOT NULL REFERENCES core.categories(id),
  contract_id    uuid REFERENCES p2p.contracts(id),
  delivery_province core.province,
  total_amount   numeric(14,2) NOT NULL CHECK (total_amount > 0),
  status         p2p.po_status NOT NULL DEFAULT 'DRAFT',
  created_by     uuid NOT NULL REFERENCES core.users(id),
  approved_by    uuid REFERENCES core.users(id),
  approved_at    timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  -- segregation of duties: the requester cannot approve their own PO
  CHECK (approved_by IS NULL OR approved_by <> created_by)
);
CREATE INDEX ix_po_supplier ON p2p.purchase_orders (supplier_id);
CREATE INDEX ix_po_dept_created ON p2p.purchase_orders (department_id, created_at);

CREATE TABLE p2p.purchase_order_lines (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  po_id        uuid NOT NULL REFERENCES p2p.purchase_orders(id) ON DELETE CASCADE,
  line_no      smallint NOT NULL,
  item_code    varchar(40),                       -- enables price comparison across regions
  description  varchar(300) NOT NULL,
  quantity     numeric(12,3) NOT NULL CHECK (quantity > 0),
  unit         varchar(20) NOT NULL DEFAULT 'EA',
  unit_price   numeric(14,2) NOT NULL CHECK (unit_price >= 0),
  line_total   numeric(14,2) GENERATED ALWAYS AS (round(quantity * unit_price, 2)) STORED,
  UNIQUE (po_id, line_no)
);

CREATE TABLE p2p.goods_receipts (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  grn_number     varchar(20) NOT NULL UNIQUE,
  po_id          uuid NOT NULL REFERENCES p2p.purchase_orders(id),
  received_date  date NOT NULL,
  amount_received numeric(14,2) NOT NULL CHECK (amount_received > 0),
  received_by    uuid NOT NULL REFERENCES core.users(id),
  evidence_key   text,                            -- signed delivery note / photo
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE p2p.invoices (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  supplier_id            uuid NOT NULL REFERENCES core.suppliers(id),
  po_id                  uuid REFERENCES p2p.purchase_orders(id),   -- NULL = missing PO → exception
  invoice_number         varchar(40) NOT NULL,
  invoice_number_norm    varchar(40) GENERATED ALWAYS AS
                           (upper(regexp_replace(invoice_number, '[^A-Za-z0-9]', '', 'g'))) STORED,
  amount                 numeric(14,2) NOT NULL CHECK (amount > 0),
  vat_amount             numeric(14,2) NOT NULL DEFAULT 0 CHECK (vat_amount >= 0),
  invoice_date           date NOT NULL,
  received_at            timestamptz NOT NULL DEFAULT now(),
  due_date               date NOT NULL,
  status                 p2p.invoice_status NOT NULL DEFAULT 'SUBMITTED',
  channel                varchar(20) NOT NULL DEFAULT 'PORTAL',   -- PORTAL / EMAIL / MANUAL
  current_approver_id    uuid REFERENCES core.users(id),           -- always someone accountable
  document_key           text,
  paid_at                timestamptz,
  CHECK (due_date >= invoice_date),
  CHECK ((status = 'PAID') = (paid_at IS NOT NULL))
);
-- hard business rule: a supplier cannot submit the same invoice number twice
CREATE UNIQUE INDEX ux_invoice_supplier_number ON p2p.invoices (supplier_id, invoice_number_norm);
CREATE INDEX ix_invoice_status_due ON p2p.invoices (status, due_date);

CREATE TABLE p2p.invoice_approvals (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id   uuid NOT NULL REFERENCES p2p.invoices(id) ON DELETE CASCADE,
  step         smallint NOT NULL,
  approver_id  uuid NOT NULL REFERENCES core.users(id),
  decision     p2p.approval_decision NOT NULL DEFAULT 'PENDING',
  comment      text,
  assigned_at  timestamptz NOT NULL DEFAULT now(),
  decided_at   timestamptz,
  UNIQUE (invoice_id, step)
);

CREATE TABLE p2p.payments (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id       uuid NOT NULL REFERENCES p2p.invoices(id),
  bank_account_id  uuid NOT NULL REFERENCES compliance.bank_accounts(id),
  amount           numeric(14,2) NOT NULL CHECK (amount > 0),
  paid_at          timestamptz NOT NULL,
  reference        varchar(40) NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------
-- SOURCING (SMME opportunity marketplace)
-- ---------------------------------------------------------------------
CREATE TABLE sourcing.opportunities (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reference        varchar(30) NOT NULL UNIQUE,
  title            varchar(200) NOT NULL,
  description      text,
  category_id      uuid NOT NULL REFERENCES core.categories(id),
  department_id    uuid NOT NULL REFERENCES core.departments(id),
  province         core.province,
  estimated_value  numeric(14,2) CHECK (estimated_value > 0),
  smme_set_aside   boolean NOT NULL DEFAULT false,
  closes_at        timestamptz NOT NULL,
  status           sourcing.opportunity_status NOT NULL DEFAULT 'DRAFT',
  awarded_supplier_id uuid REFERENCES core.suppliers(id),
  created_by       uuid NOT NULL REFERENCES core.users(id),
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sourcing.quotations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  opportunity_id  uuid NOT NULL REFERENCES sourcing.opportunities(id),
  supplier_id     uuid NOT NULL REFERENCES core.suppliers(id),
  amount          numeric(14,2) NOT NULL CHECK (amount > 0),
  submitted_at    timestamptz NOT NULL DEFAULT now(),
  score           numeric(5,2),
  UNIQUE (opportunity_id, supplier_id)
);

-- ---------------------------------------------------------------------
-- RISK
-- ---------------------------------------------------------------------
CREATE TABLE risk.rules (
  code         varchar(40) PRIMARY KEY,           -- e.g. DUP_INVOICE, SPLIT_THRESHOLD
  name         varchar(120) NOT NULL,
  description  text NOT NULL,
  severity     risk.severity NOT NULL,
  params       jsonb NOT NULL DEFAULT '{}',       -- thresholds editable without a deploy
  is_enabled   boolean NOT NULL DEFAULT true
);

CREATE TABLE risk.flags (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_code     varchar(40) NOT NULL REFERENCES risk.rules(code),
  entity_type   varchar(30) NOT NULL,             -- INVOICE / SUPPLIER / PO / QUOTATION / PAYMENT
  entity_id     uuid NOT NULL,
  supplier_id   uuid REFERENCES core.suppliers(id),
  score         numeric(5,2) NOT NULL CHECK (score BETWEEN 0 AND 100),
  severity      risk.severity NOT NULL,
  explanation   jsonb NOT NULL,                   -- reason codes + evidence: a flag, never an accusation
  status        risk.flag_status NOT NULL DEFAULT 'OPEN',
  assigned_to   uuid REFERENCES core.users(id),
  detected_at   timestamptz NOT NULL DEFAULT now(),
  resolved_at   timestamptz,
  UNIQUE (rule_code, entity_type, entity_id)      -- reruns do not create duplicate flags
);
CREATE INDEX ix_flags_open ON risk.flags (status, severity) WHERE status IN ('OPEN','UNDER_REVIEW','ESCALATED');

CREATE TABLE risk.case_notes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  flag_id     uuid NOT NULL REFERENCES risk.flags(id) ON DELETE CASCADE,
  author_id   uuid NOT NULL REFERENCES core.users(id),
  note        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- AUDIT (append-only, hash-chained)
-- ---------------------------------------------------------------------
CREATE TABLE audit.events (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at  timestamptz NOT NULL DEFAULT now(),
  actor_id     uuid REFERENCES core.users(id),
  action       varchar(60) NOT NULL,              -- INVOICE_APPROVED, BANK_DETAILS_CHANGED, ...
  entity_type  varchar(30) NOT NULL,
  entity_id    uuid NOT NULL,
  before_state jsonb,
  after_state  jsonb,
  prev_hash    char(64),
  hash         char(64) NOT NULL                  -- sha256(prev_hash || row content)
);

CREATE FUNCTION audit.chain_hash() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  SELECT hash INTO NEW.prev_hash FROM audit.events ORDER BY id DESC LIMIT 1;
  NEW.hash := encode(digest(
      coalesce(NEW.prev_hash,'') || NEW.occurred_at::text || coalesce(NEW.actor_id::text,'')
      || NEW.action || NEW.entity_type || NEW.entity_id::text
      || coalesce(NEW.before_state::text,'') || coalesce(NEW.after_state::text,''),
      'sha256'), 'hex');
  RETURN NEW;
END $$;
CREATE TRIGGER trg_audit_chain BEFORE INSERT ON audit.events
  FOR EACH ROW EXECUTE FUNCTION audit.chain_hash();

CREATE FUNCTION audit.block_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit.events is append-only'; END $$;
CREATE TRIGGER trg_audit_immutable BEFORE UPDATE OR DELETE ON audit.events
  FOR EACH ROW EXECUTE FUNCTION audit.block_mutation();
