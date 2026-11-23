select
    id                                   as invoice_id,
    invoice_number,
    supplier_id,
    po_id,
    amount                               as invoice_amount,
    vat_amount,
    invoice_date,
    received_at::date                    as received_date,
    received_at,
    due_date,
    paid_at::date                        as paid_date,
    paid_at,
    status::text                         as invoice_status,
    channel,
    coalesce(cardinality(match_exceptions), 0) as match_exception_count
from {{ source('p2p', 'invoices') }}
