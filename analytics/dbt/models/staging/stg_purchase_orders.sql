select
    id                       as po_id,
    po_number,
    supplier_id,
    department_id,
    category_id,
    total_amount             as po_amount,
    status::text             as po_status,
    created_at::date         as order_date,
    approved_at,
    expected_delivery_date,
    created_by,
    approved_by
from {{ source('p2p', 'purchase_orders') }}
where status <> 'CANCELLED'
