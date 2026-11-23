select id as category_id, code as category_code, name as category_name
from {{ source('core', 'categories') }}
