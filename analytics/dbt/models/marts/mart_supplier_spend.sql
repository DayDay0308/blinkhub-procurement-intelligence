-- Supplier ranking with Pareto (ABC) classes: A = suppliers making up the first 80% of spend.
with s as (
    select supplier_id, data_source, sum(po_amount) as spend, count(*) as purchase_orders
    from {{ ref('fct_purchase_orders') }} group by 1, 2
),
ranked as (
    select s.*,
           rank() over (partition by data_source order by spend desc) as spend_rank,
           spend / sum(spend) over (partition by data_source) as spend_share,
           sum(spend) over (partition by data_source order by spend desc
                            rows between unbounded preceding and current row)
             / sum(spend) over (partition by data_source) as cumulative_share
    from s
)
select r.*,
       case when cumulative_share - spend_share < 0.80 then 'A'
            when cumulative_share - spend_share < 0.95 then 'B' else 'C' end as abc_class
from ranked r
