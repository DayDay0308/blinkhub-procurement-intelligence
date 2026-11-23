"""Snapshot the synthetic-year analytics marts to CSV, so the notebook runs without a database.

    cd analytics && uv run python ../analysis/export_synthetic_snapshot.py

Reads the dbt marts (schema `analytics`). Only rows with data_source = 'SYNTHETIC' are exported:
the case-study sample is analysed from the raw CSVs instead.
"""

import csv
import os
from pathlib import Path

import psycopg2

OUT = Path(__file__).parent / "data" / "synthetic"

QUERIES = {
    "monthly_kpis": """
        select month, spend, smme_spend, smme_share, bbbee_recognised_spend, purchase_orders,
               invoices_paid, avg_days_to_pay, avg_days_to_pay_smme, avg_days_to_pay_large,
               pct_paid_within_terms
        from analytics.mart_monthly_kpis where data_source = 'SYNTHETIC' and month is not null
        order by month""",
    "supplier_spend": """
        select s.supplier_code, s.supplier_type, s.province, s.bbbee_level_label,
               m.spend, m.spend_share, m.cumulative_share, m.spend_rank, m.abc_class
        from analytics.mart_supplier_spend m join analytics.dim_supplier s using (supplier_id)
        where m.data_source = 'SYNTHETIC' order by m.spend_rank""",
    "category_concentration": """
        select c.category_name, m.category_spend, m.suppliers, m.hhi, m.top_supplier_share,
               m.concentration_band
        from analytics.mart_category_concentration m join analytics.dim_category c using (category_id)
        where m.data_source = 'SYNTHETIC' order by m.hhi desc""",
    "payment_by_type": """
        select case when is_smme then 'SMME' else 'Large enterprise' end as supplier_type,
               count(*) as invoices_paid, round(avg(days_to_pay), 1) as avg_days_to_pay,
               round(avg(paid_within_terms::int), 3) as pct_within_30_days
        from analytics.fct_invoices where is_paid and data_source = 'SYNTHETIC' group by 1""",
    "province_spend": """
        select province, sum(po_amount) as spend,
               sum(po_amount) filter (where is_smme) as smme_spend
        from analytics.fct_purchase_orders where data_source = 'SYNTHETIC'
        group by 1 order by 2 desc""",
    "risk_flags": """
        select rule_name, severity, count(*) as flags, coalesce(sum(value_at_risk), 0) as value_at_risk
        from analytics.fct_risk_flags f join analytics.dim_supplier s using (supplier_id)
        where s.data_source = 'SYNTHETIC' group by 1, 2 order by 3 desc""",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(
        host=os.getenv("DBT_HOST", "localhost"), port=os.getenv("DBT_PORT", "5432"),
        user=os.getenv("DBT_USER", "blinkhub"), password=os.getenv("DBT_PASSWORD", "blinkhub"),
        dbname=os.getenv("DBT_DBNAME", "blinkhub"),
    )
    with conn, conn.cursor() as cur:
        for name, sql in QUERIES.items():
            cur.execute(sql)
            with open(OUT / f"{name}.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow([d[0] for d in cur.description])
                w.writerows(cur.fetchall())
            print(f"wrote {name}.csv ({cur.rowcount} rows)")


if __name__ == "__main__":
    main()
