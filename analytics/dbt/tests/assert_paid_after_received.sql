-- An invoice cannot be paid before it was received.
select invoice_id, received_date, paid_date
from {{ ref('fct_invoices') }}
where paid_date < received_date
