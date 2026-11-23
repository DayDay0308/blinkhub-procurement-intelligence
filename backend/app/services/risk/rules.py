"""Explainable risk rules (case study Problem 6).

Each rule is one set-based SQL query that returns candidate flags:
    entity_type, entity_id, supplier_id, score (0-100), explanation (jsonb)

The explanation holds the evidence an investigator needs: numbers, the related records
and a plain-English reason. Thresholds come from risk.rules.params, so they can be tuned
without a deploy.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    code: str
    sql: str


DUP_INVOICE = Rule(
    "DUP_INVOICE",
    """
WITH inv AS (
  SELECT i.id, i.supplier_id, i.po_id, i.amount, i.invoice_number, i.status, i.invoice_date,
         i.received_at, po.created_at AS po_created
  FROM p2p.invoices i LEFT JOIN p2p.purchase_orders po ON po.id = i.po_id
  WHERE i.status <> 'REJECTED'
),
pairs AS (
  SELECT a.supplier_id, a.amount,
         a.id AS a_id, b.id AS b_id, a.invoice_number AS a_no, b.invoice_number AS b_no,
         a.status AS a_status, b.status AS b_status, a.received_at AS a_rec, b.received_at AS b_rec,
         abs(a.invoice_date - b.invoice_date) AS days_apart,
         (a.po_id IS NOT NULL AND a.po_id = b.po_id) AS same_po,
         (a.po_id IS NULL OR b.po_id IS NULL) AS missing_po,
         a.po_id IS NULL AS a_no_po, b.po_id IS NULL AS b_no_po,
         -- recurring orders (e.g. monthly contracts) have POs raised weeks apart: not duplicates
         abs(extract(epoch FROM a.po_created - b.po_created) / 86400) AS po_days_apart
  FROM inv a JOIN inv b
    ON a.supplier_id = b.supplier_id AND a.amount = b.amount AND a.id < b.id
),
scored AS (
  SELECT *,
    CASE WHEN same_po THEN 90
         WHEN missing_po AND days_apart <= (:p->>'no_po_window_days')::int THEN 75
         WHEN days_apart <= (:p->>'different_po_window_days')::int
              AND po_days_apart <= (:p->>'different_po_window_days')::int THEN 60
    END AS score,
    -- Which invoice to flag: the one that can't be matched to a PO; otherwise the one still
    -- to be paid; otherwise the later one.
    CASE WHEN a_no_po AND NOT b_no_po THEN 'a'
         WHEN b_no_po AND NOT a_no_po THEN 'b'
         WHEN a_status = 'PAID' AND b_status <> 'PAID' THEN 'b'
         WHEN b_status = 'PAID' AND a_status <> 'PAID' THEN 'a'
         WHEN (a_rec, a_no) > (b_rec, b_no) THEN 'a' ELSE 'b' END AS target
  FROM pairs
)
SELECT DISTINCT ON (entity_id)
  'INVOICE' AS entity_type,
  CASE WHEN target = 'a' THEN a_id ELSE b_id END AS entity_id,
  supplier_id, score,
  jsonb_build_object(
    'reason', CASE WHEN same_po THEN 'Same amount billed twice against the same purchase order'
                   WHEN missing_po THEN 'Same amount as another invoice from this supplier, without a PO to tell them apart'
                   ELSE 'Same amount as another invoice on a different PO only days apart' END,
    'matching_invoice', CASE WHEN target = 'a' THEN b_no ELSE a_no END,
    'matching_invoice_status', CASE WHEN target = 'a' THEN b_status ELSE a_status END,
    'amount', amount, 'days_apart', days_apart, 'same_po', same_po
  ) AS explanation
FROM (SELECT *, CASE WHEN target = 'a' THEN a_id ELSE b_id END AS entity_id FROM scored) s
WHERE score IS NOT NULL
ORDER BY entity_id, score DESC
""",
)

SPLIT_THRESHOLD = Rule(
    "SPLIT_THRESHOLD",
    """
WITH limits AS (
  SELECT DISTINCT approval_limit AS lim FROM core.users
  WHERE approval_limit IS NOT NULL AND is_active
),
near AS (
  -- Splitting happens when orders are raised, so the window is measured on PO dates.
  SELECT i.id, i.supplier_id, po.department_id, i.amount, po.created_at::date AS order_date, l.lim
  FROM p2p.invoices i
  JOIN p2p.purchase_orders po ON po.id = i.po_id
  JOIN limits l ON i.amount >= l.lim * (:p->>'lower_pct')::numeric AND i.amount < l.lim
  WHERE i.status <> 'REJECTED'
),
win AS (
  SELECT n.*,
    (SELECT count(*) FROM near m
      WHERE m.supplier_id = n.supplier_id AND m.department_id = n.department_id AND m.lim = n.lim
        AND abs(m.order_date - n.order_date) <= (:p->>'window_days')::int) AS cnt,
    (SELECT sum(m.amount) FROM near m
      WHERE m.supplier_id = n.supplier_id AND m.department_id = n.department_id AND m.lim = n.lim
        AND abs(m.order_date - n.order_date) <= (:p->>'window_days')::int) AS cluster_total
  FROM near n
)
SELECT 'INVOICE', w.id, w.supplier_id, least(95, 55 + w.cnt * 8),
  jsonb_build_object(
    'reason', format('%s orders from this supplier for %s raised within %s days, each just under the R%s approval limit',
                     w.cnt, d.name, (:p->>'window_days'), to_char(w.lim, 'FM999G999G999')),
    'approval_limit', w.lim, 'amount', w.amount,
    'pct_of_limit', round(100 * w.amount / w.lim, 1),
    'orders_in_window', w.cnt, 'combined_value', w.cluster_total, 'department', d.name)
FROM win w JOIN core.departments d ON d.id = w.department_id
WHERE w.cnt >= (:p->>'min_count')::int
""",
)

NO_DELIVERY_EVIDENCE = Rule(
    "NO_DELIVERY_EVIDENCE",
    """
SELECT 'INVOICE', i.id, i.supplier_id,
  CASE WHEN i.status = 'PAID' THEN 70 ELSE 55 END,
  jsonb_build_object(
    'reason', CASE WHEN i.po_id IS NULL
                   THEN 'Invoice ' || lower(i.status::text) || ' with no purchase order or delivery evidence'
                   ELSE 'Invoice ' || lower(i.status::text) || ' but no goods receipt was recorded for ' || po.po_number END,
    'status', i.status, 'amount', i.amount, 'po_number', po.po_number)
FROM p2p.invoices i
LEFT JOIN p2p.purchase_orders po ON po.id = i.po_id
WHERE i.status IN ('APPROVED', 'SCHEDULED', 'PAID')
  AND (i.po_id IS NULL OR NOT EXISTS (SELECT 1 FROM p2p.goods_receipts g WHERE g.po_id = i.po_id))
""",
)

BANK_CHANGE_BEFORE_PAY = Rule(
    "BANK_CHANGE_BEFORE_PAY",
    """
SELECT 'INVOICE', p.invoice_id, b.supplier_id,
  greatest(70, 98 - 2 * extract(day FROM p.paid_at - b.effective_from))::int,
  jsonb_build_object(
    'reason', format('Paid R%s into a bank account that replaced the previous one %s days earlier',
                     to_char(p.amount, 'FM999G999G990D00'),
                     round(extract(epoch FROM p.paid_at - b.effective_from) / 86400, 1)),
    'days_after_change', round(extract(epoch FROM p.paid_at - b.effective_from) / 86400, 1),
    'new_account_last4', b.account_last4, 'previous_account_last4', prev.account_last4,
    'changed_by', u.full_name, 'payment_reference', p.reference)
FROM p2p.payments p
JOIN compliance.bank_accounts b ON b.id = p.bank_account_id
JOIN LATERAL (
  SELECT account_last4 FROM compliance.bank_accounts x
  WHERE x.supplier_id = b.supplier_id AND x.effective_from < b.effective_from
  ORDER BY x.effective_from DESC LIMIT 1
) prev ON true
LEFT JOIN core.users u ON u.id = b.changed_by
WHERE p.paid_at >= b.effective_from
  AND p.paid_at - b.effective_from <= make_interval(days => (:p->>'window_days')::int)
""",
)

QUOTE_SIMILARITY = Rule(
    "QUOTE_SIMILARITY",
    """
SELECT 'OPPORTUNITY', o.id, o.awarded_supplier_id, 80,
  jsonb_build_object(
    'reason', format('%s quotes within %s%% of each other (normal competition is usually 10%%+ apart)',
                     count(q.id), round(100 * (max(q.amount) - min(q.amount)) / min(q.amount), 2)),
    'opportunity', o.reference, 'quotes', count(q.id),
    'coefficient_of_variation', round(stddev_pop(q.amount) / avg(q.amount), 4),
    'lowest', min(q.amount), 'highest', max(q.amount),
    'bidders', jsonb_agg(s.legal_name ORDER BY q.amount))
FROM sourcing.opportunities o
JOIN sourcing.quotations q ON q.opportunity_id = o.id
JOIN core.suppliers s ON s.id = q.supplier_id
GROUP BY o.id
HAVING count(q.id) >= (:p->>'min_quotes')::int
   AND stddev_pop(q.amount) / avg(q.amount) < (:p->>'max_cv')::numeric
""",
)

CONCENTRATION = Rule(
    "CONCENTRATION",
    """
WITH spend AS (
  SELECT po.category_id, po.supplier_id, sum(po.total_amount) AS amt
  FROM p2p.purchase_orders po
  WHERE po.status <> 'CANCELLED' AND po.created_at >= now() - interval '12 months'
  GROUP BY 1, 2
),
cat AS (
  SELECT category_id, sum(amt) AS total, count(*) AS suppliers,
         round(sum(power(amt, 2)) / power(sum(amt), 2) * 10000) AS hhi
  FROM spend GROUP BY 1
),
top AS (
  SELECT DISTINCT ON (s.category_id) s.category_id, s.supplier_id, s.amt
  FROM spend s ORDER BY s.category_id, s.amt DESC
)
SELECT 'CATEGORY', c.category_id, t.supplier_id,
  least(90, 40 + 50 * t.amt / c.total)::int,
  jsonb_build_object(
    'reason', format('%s receives %s%% of %s spend (R%s) across %s suppliers',
                     sup.legal_name, round(100 * t.amt / c.total), cg.name,
                     to_char(c.total, 'FM999G999G999'), c.suppliers),
    'category', cg.name, 'top_supplier', sup.legal_name,
    'share_pct', round(100 * t.amt / c.total, 1), 'category_spend', c.total,
    'suppliers_in_category', c.suppliers, 'hhi', c.hhi,
    'hhi_band', CASE WHEN c.hhi > 2500 THEN 'highly concentrated'
                     WHEN c.hhi > 1500 THEN 'moderately concentrated' ELSE 'competitive' END)
FROM cat c
JOIN top t ON t.category_id = c.category_id
JOIN core.categories cg ON cg.id = c.category_id
JOIN core.suppliers sup ON sup.id = t.supplier_id
WHERE t.amt / c.total > (:p->>'max_share')::numeric
  AND c.total >= (:p->>'min_category_spend')::numeric
""",
)

INCOMPLETE_COMPLIANCE = Rule(
    "INCOMPLETE_COMPLIANCE",
    """
SELECT 'SUPPLIER', s.id, s.id, 60,
  jsonb_build_object(
    'reason', CASE WHEN d.expiry_date IS NULL THEN 'Paid recently with no verified tax clearance on file'
                   ELSE format('Paid recently although tax clearance expired on %s', d.expiry_date) END,
    'tax_clearance_expiry', d.expiry_date,
    'paid_last_period', (SELECT sum(i.amount) FROM p2p.invoices i
                         WHERE i.supplier_id = s.id AND i.status = 'PAID'
                           AND i.paid_at >= now() - make_interval(days => (:p->>'lookback_days')::int)))
FROM core.suppliers s
LEFT JOIN LATERAL (
  SELECT max(expiry_date) AS expiry_date FROM compliance.documents
  WHERE supplier_id = s.id AND doc_type = 'TAX_CLEARANCE'
) d ON true
WHERE s.status = 'ACTIVE'
  AND EXISTS (SELECT 1 FROM p2p.invoices i WHERE i.supplier_id = s.id AND i.status = 'PAID'
                AND i.paid_at >= now() - make_interval(days => (:p->>'lookback_days')::int))
  AND NOT EXISTS (SELECT 1 FROM compliance.documents doc
                  WHERE doc.supplier_id = s.id AND doc.doc_type = 'TAX_CLEARANCE'
                    AND doc.status = 'VERIFIED' AND coalesce(doc.expiry_date, 'infinity') >= current_date)
""",
)

SQL_RULES = [
    DUP_INVOICE,
    SPLIT_THRESHOLD,
    NO_DELIVERY_EVIDENCE,
    BANK_CHANGE_BEFORE_PAY,
    QUOTE_SIMILARITY,
    CONCENTRATION,
    INCOMPLETE_COMPLIANCE,
]
