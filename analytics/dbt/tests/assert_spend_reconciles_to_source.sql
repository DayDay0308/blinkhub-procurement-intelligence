-- Every rand of non-cancelled PO value in the app must appear in the spend fact.
-- Returns a row (= test failure) if the totals differ by more than one cent.
select src.total as source_total, fct.total as fact_total
from (select sum(total_amount) as total from {{ source('p2p', 'purchase_orders') }}
      where status <> 'CANCELLED') src
cross join (select sum(po_amount) as total from {{ ref('fct_purchase_orders') }}) fct
where abs(src.total - fct.total) > 0.01
