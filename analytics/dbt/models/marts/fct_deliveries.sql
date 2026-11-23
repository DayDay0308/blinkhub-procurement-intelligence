-- Grain: one goods receipt. Delivery-reliability measures.
select
    g.grn_id,
    g.grn_number,
    g.po_id,
    po.supplier_id,
    po.department_id,
    po.category_id,
    to_char(g.received_date, 'YYYYMMDD')::int                as received_date_key,
    g.received_date,
    po.expected_delivery_date,
    g.amount_received,
    greatest(0, g.received_date - po.expected_delivery_date) as days_late,
    g.received_date <= po.expected_delivery_date             as is_on_time
from {{ ref('stg_goods_receipts') }} g
join {{ ref('stg_purchase_orders') }} po on po.po_id = g.po_id
where po.expected_delivery_date is not null
