select id as grn_id, grn_number, po_id, received_date, amount_received
from {{ source('p2p', 'goods_receipts') }}
