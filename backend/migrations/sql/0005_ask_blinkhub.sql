-- 0005: Ask BlinkHub (questions in plain English -> SQL)
--
-- Generated SQL never touches the operational tables. It runs on its own database login,
-- blinkhub_ask, which can only SELECT from the views in schema `ask` (a separate login, not
-- SET ROLE, so a query can't switch back to the application's user). The views expose business columns
-- with plain names and leave out what nobody should query this way: bank details, password
-- hashes, contact details, uploaded file paths, audit internals.
-- The API adds a read-only transaction, a 5-second timeout and a row limit on top.

CREATE SCHEMA ask;

CREATE VIEW ask.suppliers AS
SELECT s.id AS supplier_id, s.supplier_code, s.legal_name AS supplier_name,
       s.supplier_type::text AS supplier_type,            -- 'SMME' or 'LARGE_ENTERPRISE'
       s.province::text AS province, s.bbbee_level, s.black_owned_pct, s.status::text AS status,
       CASE WHEN starts_with(s.supplier_code, 'SYN-') THEN 'SYNTHETIC' ELSE 'CASE_STUDY' END AS data_source
FROM core.suppliers s;

CREATE VIEW ask.purchase_orders AS
SELECT po.po_number, po.supplier_id, d.name AS department, c.name AS category,
       po.created_at::date AS order_date, po.total_amount, po.status::text AS status,
       po.expected_delivery_date,
       coalesce((SELECT sum(g.amount_received) FROM p2p.goods_receipts g WHERE g.po_id = po.id), 0) AS amount_received,
       CASE WHEN starts_with(s.supplier_code, 'SYN-') THEN 'SYNTHETIC' ELSE 'CASE_STUDY' END AS data_source
FROM p2p.purchase_orders po
JOIN core.suppliers s ON s.id = po.supplier_id
JOIN core.departments d ON d.id = po.department_id
JOIN core.categories c ON c.id = po.category_id;

CREATE VIEW ask.invoices AS
SELECT i.invoice_number, i.supplier_id, po.po_number, i.amount, i.status::text AS status,
       i.invoice_date, i.received_at::date AS received_date, i.due_date, i.paid_at::date AS paid_date,
       CASE WHEN i.paid_at IS NOT NULL THEN i.paid_at::date - i.received_at::date
            ELSE current_date - i.received_at::date END AS days_outstanding,
       (i.paid_at IS NULL AND i.status <> 'REJECTED' AND current_date > i.due_date) AS is_overdue,
       (i.po_id IS NULL) AS has_no_po,
       CASE WHEN starts_with(s.supplier_code, 'SYN-') THEN 'SYNTHETIC' ELSE 'CASE_STUDY' END AS data_source
FROM p2p.invoices i
JOIN core.suppliers s ON s.id = i.supplier_id
LEFT JOIN p2p.purchase_orders po ON po.id = i.po_id;

CREATE VIEW ask.risk_flags AS
SELECT f.rule_code, r.name AS rule_name, f.severity::text AS severity, f.status::text AS status,
       f.score, f.supplier_id, f.detected_at::date AS detected_date, f.explanation->>'reason' AS reason
FROM risk.flags f
JOIN risk.rules r ON r.code = f.rule_code;

CREATE VIEW ask.compliance_documents AS
SELECT d.supplier_id, d.doc_type::text AS doc_type, d.status::text AS status, d.issue_date, d.expiry_date
FROM compliance.documents d;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'blinkhub_ask') THEN
    CREATE ROLE blinkhub_ask LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END $$;
-- Set every time, in case the role already exists from another database on this server.
ALTER ROLE blinkhub_ask LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
-- (the password is set by the Alembic migration from ASK_DB_PASSWORD)

-- Every session of this login is read-only, short and small, whatever the query says.
ALTER ROLE blinkhub_ask SET default_transaction_read_only = on;
ALTER ROLE blinkhub_ask SET statement_timeout = '5s';
ALTER ROLE blinkhub_ask SET work_mem = '16MB';
ALTER ROLE blinkhub_ask SET search_path = ask;

GRANT USAGE ON SCHEMA ask TO blinkhub_ask;
GRANT SELECT ON ALL TABLES IN SCHEMA ask TO blinkhub_ask;
-- No temporary tables either (the login can't write anything at all).
DO $$
BEGIN
  EXECUTE 'REVOKE TEMPORARY ON DATABASE ' || quote_ident(current_database()) || ' FROM PUBLIC';
END $$;
