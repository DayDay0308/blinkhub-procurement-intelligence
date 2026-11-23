select supplier_id, doc_type::text as doc_type, status::text as doc_status, issue_date, expiry_date
from {{ source('compliance', 'documents') }}
