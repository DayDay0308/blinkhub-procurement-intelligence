"""Live dashboard figures for the web app.

Same definitions as the dbt marts (spend = committed PO value, B-BBEE recognition levels,
30-day terms), computed straight from the operational tables so the screens are always
current. Power BI reads the dbt marts; both agree on the case-study numbers.

data_source: CASE_STUDY (the 8 sample suppliers), SYNTHETIC (generated demo year) or ALL.
"""

from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

DataSource = Literal["CASE_STUDY", "SYNTHETIC", "ALL"]

SUPPLIERS = """
  SELECT s.*, CASE WHEN s.supplier_code LIKE 'SYN-%' THEN 'SYNTHETIC' ELSE 'CASE_STUDY' END AS src,
         CASE s.bbbee_level WHEN 1 THEN 1.35 WHEN 2 THEN 1.25 WHEN 3 THEN 1.10 WHEN 4 THEN 1.00
              WHEN 5 THEN 0.80 WHEN 6 THEN 0.60 WHEN 7 THEN 0.50 WHEN 8 THEN 0.10 ELSE 0 END AS recog
  FROM core.suppliers s
"""

WITH = f"""
WITH sup AS ({SUPPLIERS}),
s AS (SELECT * FROM sup WHERE :src = 'ALL' OR src = :src),
po AS (
  SELECT po.*, s.supplier_type = 'SMME' AS is_smme, s.recog, s.province, s.legal_name, s.bbbee_level
  FROM p2p.purchase_orders po JOIN s ON s.id = po.supplier_id WHERE po.status <> 'CANCELLED'
),
inv AS (
  SELECT i.*, s.supplier_type = 'SMME' AS is_smme,
         current_date - i.received_at::date AS age_days,
         extract(epoch FROM i.paid_at - i.received_at) / 86400 AS days_to_pay
  FROM p2p.invoices i JOIN s ON s.id = i.supplier_id
)
"""


def _rows(db: Session, sql: str, src: str) -> list[dict]:
    return [dict(r) for r in db.execute(text(WITH + sql), {"src": src}).mappings()]


def overview(db: Session, src: DataSource = "CASE_STUDY") -> dict:
    totals = _rows(
        db,
        """
        SELECT coalesce(sum(total_amount), 0) AS spend,
               coalesce(sum(total_amount) FILTER (WHERE is_smme), 0) AS smme_spend,
               coalesce(sum(total_amount * recog), 0) AS bbbee_recognised_spend,
               count(*) AS purchase_orders, count(DISTINCT supplier_id) AS suppliers_paid
        FROM po""",
        src,
    )[0]
    spend = float(totals["spend"]) or 1.0
    totals["smme_share"] = round(float(totals["smme_spend"]) / spend, 4)
    totals["bbbee_recognition"] = round(float(totals["bbbee_recognised_spend"]) / spend, 4)

    invoices = _rows(
        db,
        """
        SELECT count(*) FILTER (WHERE status NOT IN ('PAID','REJECTED')) AS open_invoices,
               count(*) FILTER (WHERE status NOT IN ('PAID','REJECTED') AND age_days > 30) AS overdue_invoices,
               coalesce(sum(amount) FILTER (WHERE status NOT IN ('PAID','REJECTED') AND age_days > 30), 0) AS overdue_value,
               count(*) FILTER (WHERE status NOT IN ('PAID','REJECTED') AND age_days > 30 AND is_smme) AS overdue_smme_invoices,
               avg((days_to_pay <= 30)::int) FILTER (WHERE status = 'PAID') AS pct_paid_within_terms,
               avg(days_to_pay) FILTER (WHERE status = 'PAID' AND is_smme) AS avg_days_to_pay_smme,
               avg(days_to_pay) FILTER (WHERE status = 'PAID' AND NOT is_smme) AS avg_days_to_pay_large,
               avg((po_id IS NULL)::int) AS pct_without_po,
               count(*) FILTER (WHERE status NOT IN ('PAID','REJECTED') AND current_approver_id IS NULL) AS open_without_owner
        FROM inv""",
        src,
    )[0]
    invoices = {
        k: (round(float(v), 4) if v is not None and not isinstance(v, int) else v)
        for k, v in invoices.items()
    }

    ageing = _rows(
        db,
        """
        SELECT bucket, count(*) AS invoices, sum(amount) AS value FROM (
          SELECT amount, CASE WHEN age_days <= 30 THEN '0-30' WHEN age_days <= 60 THEN '31-60'
                              WHEN age_days <= 90 THEN '61-90' ELSE '90+' END AS bucket
          FROM inv WHERE status NOT IN ('PAID','REJECTED')) x
        GROUP BY bucket ORDER BY bucket""",
        src,
    )

    by_category = _rows(
        db,
        """
        SELECT c.name AS category, sum(total_amount) AS spend,
               coalesce(sum(total_amount) FILTER (WHERE is_smme), 0) AS smme_spend,
               coalesce(sum(total_amount) FILTER (WHERE NOT is_smme), 0) AS large_spend
        FROM po JOIN core.categories c ON c.id = po.category_id GROUP BY 1 ORDER BY 2 DESC""",
        src,
    )

    by_department = _rows(
        db,
        """
        SELECT d.name AS department, sum(total_amount) AS spend
        FROM po JOIN core.departments d ON d.id = po.department_id GROUP BY 1 ORDER BY 2 DESC""",
        src,
    )

    by_province = _rows(
        db,
        """
        SELECT province::text AS province, sum(total_amount) AS spend,
               coalesce(sum(total_amount) FILTER (WHERE is_smme), 0) AS smme_spend
        FROM po GROUP BY 1 ORDER BY 2 DESC""",
        src,
    )

    monthly = _rows(
        db,
        """
        SELECT to_char(date_trunc('month', created_at), 'YYYY-MM') AS month, sum(total_amount) AS spend,
               coalesce(sum(total_amount) FILTER (WHERE is_smme), 0) AS smme_spend
        FROM po GROUP BY 1 ORDER BY 1""",
        src,
    )

    top_suppliers = _rows(
        db,
        """
        SELECT supplier_id, legal_name AS supplier, bool_or(is_smme) AS is_smme,
               max(bbbee_level) AS bbbee_level, sum(total_amount) AS spend
        FROM po GROUP BY 1, 2 ORDER BY spend DESC LIMIT 10""",
        src,
    )
    for t in top_suppliers:
        t["share"] = round(float(t["spend"]) / spend, 4)

    risk = _rows(
        db,
        """
        SELECT count(*) AS open_flags,
               count(*) FILTER (WHERE f.severity IN ('CRITICAL','HIGH')) AS critical_high,
               coalesce(sum(i.amount), 0) AS value_under_review
        FROM risk.flags f
        LEFT JOIN p2p.invoices i ON f.entity_type = 'INVOICE' AND i.id = f.entity_id
        WHERE f.status IN ('OPEN','UNDER_REVIEW','ESCALATED')
          AND (f.supplier_id IN (SELECT id FROM s) OR f.supplier_id IS NULL AND :src = 'ALL')""",
        src,
    )[0]

    return {
        "data_source": src,
        "spend": totals,
        "invoices": invoices,
        "ageing": ageing,
        "by_category": by_category,
        "by_department": by_department,
        "by_province": by_province,
        "monthly": monthly,
        "top_suppliers": top_suppliers,
        "risk": risk,
    }
