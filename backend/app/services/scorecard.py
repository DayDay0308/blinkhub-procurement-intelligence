"""Supplier performance scorecard (Blink's "track supplier performance / KPI tracking").

Five KPIs over the last 12 months, each 0-100, combined with weights. A KPI with no data
(e.g. a supplier with no deliveries yet) is left out and the remaining weights re-scaled,
so new suppliers are not punished for missing history.

| KPI                  | Weight | Measures                                                      |
|----------------------|--------|---------------------------------------------------------------|
| delivery_reliability | 30%    | deliveries received on or before the expected date            |
| invoice_accuracy     | 25%    | invoices with a PO, within the PO value, not flagged as risky |
| compliance           | 20%    | valid, verified tax clearance and B-BBEE certificate          |
| risk_record          | 15%    | open or confirmed risk flags, weighted by severity            |
| price_competitiveness| 10%    | unit prices compared with the median for the same item        |
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

WEIGHTS = {
    "delivery_reliability": 30,
    "invoice_accuracy": 25,
    "compliance": 20,
    "risk_record": 15,
    "price_competitiveness": 10,
}

SQL = text("""
WITH sup AS (
  SELECT id, supplier_code, legal_name, supplier_type, province, bbbee_level
  FROM core.suppliers WHERE (CAST(:sid AS uuid) IS NULL OR id = CAST(:sid AS uuid))
    AND status IN ('ACTIVE', 'SUSPENDED')
),
delivery AS (
  SELECT po.supplier_id, count(*) AS n,
         100.0 * avg((g.received_date <= po.expected_delivery_date)::int) AS score,
         avg(greatest(0, g.received_date - po.expected_delivery_date)) AS avg_days_late
  FROM p2p.goods_receipts g JOIN p2p.purchase_orders po ON po.id = g.po_id
  WHERE po.expected_delivery_date IS NOT NULL AND g.received_date >= current_date - 365
  GROUP BY 1
),
accuracy AS (
  SELECT i.supplier_id, count(*) AS n,
         100.0 * avg((i.po_id IS NOT NULL AND i.amount <= po.total_amount * 1.02
                      AND NOT EXISTS (SELECT 1 FROM risk.flags f
                                      WHERE f.entity_type = 'INVOICE' AND f.entity_id = i.id
                                        AND f.rule_code IN ('DUP_INVOICE', 'NO_DELIVERY_EVIDENCE')
                                        AND f.status NOT IN ('DISMISSED')))::int) AS score
  FROM p2p.invoices i LEFT JOIN p2p.purchase_orders po ON po.id = i.po_id
  WHERE i.status <> 'REJECTED' AND i.invoice_date >= current_date - 365
  GROUP BY 1
),
compliance AS (
  SELECT s.id AS supplier_id,
         CASE WHEN tax.ok AND bee.ok THEN
                CASE WHEN least(tax.expiry, bee.expiry) <= current_date + 30 THEN 75 ELSE 100 END
              WHEN tax.ok OR bee.ok THEN 50 ELSE 0 END AS score,
         tax.expiry AS tax_expiry, bee.expiry AS bbbee_expiry
  FROM sup s
  LEFT JOIN LATERAL (SELECT bool_or(status = 'VERIFIED' AND coalesce(expiry_date, 'infinity') >= current_date) AS ok,
                            max(expiry_date) FILTER (WHERE status IN ('VERIFIED', 'EXPIRED')) AS expiry
                     FROM compliance.documents WHERE supplier_id = s.id AND doc_type = 'TAX_CLEARANCE') tax ON true
  LEFT JOIN LATERAL (SELECT bool_or(status = 'VERIFIED' AND coalesce(expiry_date, 'infinity') >= current_date) AS ok,
                            max(expiry_date) FILTER (WHERE status IN ('VERIFIED', 'EXPIRED')) AS expiry
                     FROM compliance.documents WHERE supplier_id = s.id
                       AND doc_type IN ('BBBEE_CERTIFICATE', 'BBBEE_AFFIDAVIT')) bee ON true
),
risk AS (
  SELECT supplier_id, count(*) AS n,
         greatest(0, 100 - sum(CASE severity WHEN 'CRITICAL' THEN 40 WHEN 'HIGH' THEN 25
                                             WHEN 'MEDIUM' THEN 10 ELSE 5 END
                               * CASE WHEN status = 'CONFIRMED' THEN 2 ELSE 1 END)) AS score
  FROM risk.flags WHERE status <> 'DISMISSED' AND supplier_id IS NOT NULL
    AND rule_code <> 'CONCENTRATION'  -- being chosen often is not the supplier's misconduct
  GROUP BY 1
),
market AS (
  SELECT item_code, percentile_cont(0.5) WITHIN GROUP (ORDER BY unit_price) AS med
  FROM p2p.purchase_order_lines WHERE item_code IS NOT NULL GROUP BY 1 HAVING count(*) >= 5
),
price AS (
  SELECT po.supplier_id, count(*) AS n,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY m.med / nullif(l.unit_price, 0)) AS ratio
  FROM p2p.purchase_order_lines l
  JOIN p2p.purchase_orders po ON po.id = l.po_id
  JOIN market m ON m.item_code = l.item_code
  GROUP BY 1
)
SELECT s.*, d.score AS delivery_reliability, d.n AS deliveries, round(d.avg_days_late, 1) AS avg_days_late,
       a.score AS invoice_accuracy, a.n AS invoices,
       c.score AS compliance, c.tax_expiry, c.bbbee_expiry,
       coalesce(r.score, 100) AS risk_record, coalesce(r.n, 0) AS open_flags,
       CASE WHEN p.ratio IS NOT NULL THEN least(100, greatest(0, 75 + (p.ratio - 1) * 250)) END
         AS price_competitiveness,
       round((((1 / p.ratio) - 1) * 100)::numeric, 1) AS price_vs_market_pct
FROM sup s
LEFT JOIN delivery d ON d.supplier_id = s.id
LEFT JOIN accuracy a ON a.supplier_id = s.id
LEFT JOIN compliance c ON c.supplier_id = s.id
LEFT JOIN risk r ON r.supplier_id = s.id
LEFT JOIN price p ON p.supplier_id = s.id
""")


def grade(score: float) -> str:
    return "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "E"


def scorecards(db: Session, supplier_id: UUID | None = None) -> list[dict]:
    out = []
    for row in db.execute(SQL, {"sid": supplier_id}).mappings():
        kpis = {k: (round(float(row[k]), 1) if row[k] is not None else None) for k in WEIGHTS}
        # Without any transactions there is no performance to score: compliance alone
        # must not rank an inactive supplier above suppliers with a real track record.
        has_activity = bool(row["invoices"] or row["deliveries"])
        used = {k: w for k, w in WEIGHTS.items() if kpis[k] is not None} if has_activity else {}
        total_w = sum(used.values())
        overall = round(sum(kpis[k] * w for k, w in used.items()) / total_w, 1) if total_w else None
        out.append(
            {
                "supplier": {
                    "id": row["id"],
                    "supplier_code": row["supplier_code"],
                    "legal_name": row["legal_name"],
                    "supplier_type": row["supplier_type"],
                    "province": row["province"],
                    "bbbee_level": row["bbbee_level"],
                },
                "overall": overall,
                "grade": grade(overall) if overall is not None else "N/A",
                "status": "SCORED" if overall is not None else "INSUFFICIENT_DATA",
                "kpis": kpis,
                "weights_used": used,
                "evidence": {
                    "deliveries": row["deliveries"] or 0,
                    "avg_days_late": row["avg_days_late"],
                    "invoices": row["invoices"] or 0,
                    "open_flags": row["open_flags"],
                    "tax_clearance_expiry": row["tax_expiry"],
                    "bbbee_expiry": row["bbbee_expiry"],
                    "price_vs_market_pct": row["price_vs_market_pct"],
                },
            }
        )
    out.sort(key=lambda c: (c["overall"] is None, -(c["overall"] or 0)))
    return out
