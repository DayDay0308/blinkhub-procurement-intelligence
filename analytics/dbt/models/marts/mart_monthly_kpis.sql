-- Pre-aggregated monthly KPIs (handy for the API and quick Power BI cards).
with spend as (
    select date_trunc('month', order_date)::date as month, data_source,
           sum(po_amount) as spend,
           sum(po_amount) filter (where is_smme) as smme_spend,
           sum(bbbee_recognised_amount) as bbbee_recognised_spend,
           count(*) as purchase_orders
    from {{ ref('fct_purchase_orders') }} group by 1, 2
),
pay as (
    select date_trunc('month', paid_date)::date as month, data_source,
           count(*) as invoices_paid,
           avg(days_to_pay) as avg_days_to_pay,
           avg(days_to_pay) filter (where is_smme) as avg_days_to_pay_smme,
           avg(days_to_pay) filter (where not is_smme) as avg_days_to_pay_large,
           avg(paid_within_terms::int) as pct_paid_within_terms
    from {{ ref('fct_invoices') }} where is_paid group by 1, 2
)
select
    coalesce(s.month, p.month) as month,
    coalesce(s.data_source, p.data_source) as data_source,
    coalesce(s.spend, 0) as spend,
    coalesce(s.smme_spend, 0) as smme_spend,
    round(coalesce(s.smme_spend, 0) / nullif(s.spend, 0), 4) as smme_share,
    coalesce(s.bbbee_recognised_spend, 0) as bbbee_recognised_spend,
    coalesce(s.purchase_orders, 0) as purchase_orders,
    coalesce(p.invoices_paid, 0) as invoices_paid,
    round(p.avg_days_to_pay, 1) as avg_days_to_pay,
    round(p.avg_days_to_pay_smme, 1) as avg_days_to_pay_smme,
    round(p.avg_days_to_pay_large, 1) as avg_days_to_pay_large,
    round(p.pct_paid_within_terms, 4) as pct_paid_within_terms
from spend s
full outer join pay p on p.month = s.month and p.data_source = s.data_source
