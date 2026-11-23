-- Grain: one purchase order. "Spend" in this project = committed PO value.
with received as (
    select po_id, sum(amount_received) as received_amount, max(received_date) as last_received_date
    from {{ ref('stg_goods_receipts') }} group by 1
),
invoiced as (
    select po_id, sum(invoice_amount) as invoiced_amount
    from {{ ref('stg_invoices') }} where invoice_status <> 'REJECTED' and po_id is not null group by 1
)
select
    po.po_id,
    po.po_number,
    po.supplier_id,
    po.department_id,
    po.category_id,
    to_char(po.order_date, 'YYYYMMDD')::int          as order_date_key,
    po.order_date,
    po.expected_delivery_date,
    po.po_status,
    po.po_amount,
    round(po.po_amount * s.bbbee_recognition, 2)     as bbbee_recognised_amount,
    s.is_smme,
    s.is_black_owned,
    s.is_black_women_owned,
    s.province,
    s.data_source,
    coalesce(r.received_amount, 0)                   as received_amount,
    coalesce(i.invoiced_amount, 0)                   as invoiced_amount,
    r.last_received_date
from {{ ref('stg_purchase_orders') }} po
join {{ ref('dim_supplier') }} s on s.supplier_id = po.supplier_id
left join received r on r.po_id = po.po_id
left join invoiced i on i.po_id = po.po_id
