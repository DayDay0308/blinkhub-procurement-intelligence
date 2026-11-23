-- Grain: one invoice. Payment-performance measures for Problem 4.
with grn as (select distinct po_id from {{ ref('stg_goods_receipts') }})
select
    i.invoice_id,
    i.invoice_number,
    i.supplier_id,
    i.po_id,
    po.department_id,
    po.category_id,
    to_char(i.received_date, 'YYYYMMDD')::int                    as received_date_key,
    i.invoice_date,
    i.received_date,
    i.due_date,
    i.paid_date,
    i.invoice_amount,
    i.invoice_status,
    i.invoice_status = 'PAID'                                    as is_paid,
    i.invoice_status not in ('PAID', 'REJECTED')                 as is_open,
    case when i.paid_at is not null
         then round(extract(epoch from i.paid_at - i.received_at) / 86400, 1) end as days_to_pay,
    case when i.invoice_status not in ('PAID', 'REJECTED')
         then current_date - i.received_date end                 as days_outstanding,
    case when i.paid_at is not null
         then i.paid_at - i.received_at <= make_interval(days => {{ var('payment_terms_days') }}) end
                                                                 as paid_within_terms,
    case
        when i.invoice_status in ('PAID', 'REJECTED') then 'Closed'
        when current_date - i.received_date <= 30 then '0-30 days'
        when current_date - i.received_date <= 60 then '31-60 days'
        when current_date - i.received_date <= 90 then '61-90 days'
        else '90+ days'
    end                                                          as ageing_bucket,
    i.po_id is not null                                          as has_po,
    g.po_id is not null                                          as has_goods_receipt,
    i.match_exception_count,
    i.channel,
    s.is_smme,
    s.data_source
from {{ ref('stg_invoices') }} i
join {{ ref('dim_supplier') }} s on s.supplier_id = i.supplier_id
left join {{ ref('stg_purchase_orders') }} po on po.po_id = i.po_id
left join grn g on g.po_id = i.po_id
