-- Market concentration per category: HHI (0-10,000) and the share of the top supplier.
with s as (
    select category_id, supplier_id, data_source, sum(po_amount) as spend
    from {{ ref('fct_purchase_orders') }} group by 1, 2, 3
),
c as (
    select category_id, data_source, sum(spend) as category_spend, count(*) as suppliers,
           round(sum(power(spend, 2)) / power(sum(spend), 2) * 10000) as hhi,
           max(spend) / sum(spend) as top_supplier_share
    from s group by 1, 2
)
select c.*,
       case when hhi > 2500 then 'Highly concentrated'
            when hhi > 1500 then 'Moderately concentrated' else 'Competitive' end as concentration_band
from c
