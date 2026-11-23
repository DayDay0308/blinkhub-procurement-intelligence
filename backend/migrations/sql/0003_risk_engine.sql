-- Migration 0003: risk engine + supplier performance
--  * expected delivery date on POs (delivery-reliability KPI)
--  * risk rule catalogue with tunable thresholds
--  * flag bookkeeping (last seen, who resolved)
--  * synthetic schema: the answer key for planted anomalies, kept apart from real data

ALTER TABLE p2p.purchase_orders ADD COLUMN expected_delivery_date date;

ALTER TABLE risk.flags
  ADD COLUMN last_seen_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN resolved_by  uuid REFERENCES core.users(id);
CREATE INDEX ix_flags_supplier ON risk.flags (supplier_id);

CREATE SCHEMA IF NOT EXISTS synthetic;
COMMENT ON SCHEMA synthetic IS
  'Demonstration only. Labels for anomalies deliberately planted in generated data, '
  'used to measure detection precision and recall. Never part of real MICS data.';

CREATE TABLE synthetic.anomaly_labels (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  anomaly_type  varchar(40) NOT NULL,
  entity_type   varchar(30) NOT NULL,
  entity_id     uuid NOT NULL,
  detail        jsonb NOT NULL DEFAULT '{}',
  UNIQUE (anomaly_type, entity_type, entity_id)
);

INSERT INTO risk.rules (code, name, description, severity, params) VALUES
('DUP_INVOICE', 'Possible duplicate invoice',
 'Same supplier and amount as another invoice: on the same PO, without a PO within a window, or very close in time on different POs.',
 'HIGH', '{"no_po_window_days": 60, "different_po_window_days": 7}'),
('SPLIT_THRESHOLD', 'Payments just below an approval limit',
 'Several invoices from one supplier to one department, each just under an approval limit, within a short window.',
 'HIGH', '{"lower_pct": 0.90, "window_days": 30, "min_count": 3}'),
('NO_DELIVERY_EVIDENCE', 'Paid without delivery evidence',
 'Approved or paid invoices with no purchase order or no goods receipt.',
 'MEDIUM', '{}'),
('BANK_CHANGE_BEFORE_PAY', 'Bank details changed shortly before payment',
 'A payment made into a bank account that replaced the previous one only days earlier.',
 'CRITICAL', '{"window_days": 14}'),
('QUOTE_SIMILARITY', 'Unusually similar quotations',
 'Competing quotes on one opportunity are almost identical (possible collusion or cover pricing).',
 'HIGH', '{"min_quotes": 3, "max_cv": 0.02}'),
('CONCENTRATION', 'Supplier concentration in a category',
 'One supplier receives a disproportionate share of a category''s spend over the last 12 months.',
 'MEDIUM', '{"max_share": 0.40, "min_category_spend": 500000}'),
('INCOMPLETE_COMPLIANCE', 'Paid while non-compliant',
 'An active supplier paid recently without a valid, verified tax clearance on file.',
 'MEDIUM', '{"lookback_days": 90}'),
('ANOMALY_ML', 'Unusual invoice (machine learning)',
 'Isolation Forest flags invoices that are unlike the rest, e.g. far above the supplier''s usual amounts.',
 'MEDIUM', '{"contamination": 0.01, "min_invoices": 200}');
