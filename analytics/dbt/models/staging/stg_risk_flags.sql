select
    f.id                    as flag_id,
    f.rule_code,
    r.name                  as rule_name,
    f.entity_type,
    f.entity_id,
    f.supplier_id,
    f.score,
    f.severity::text        as severity,
    f.status::text          as flag_status,
    f.explanation ->> 'reason' as reason,
    f.detected_at::date     as detected_date,
    f.resolved_at::date     as resolved_date
from {{ source('risk', 'flags') }} f
join {{ source('risk', 'rules') }} r on r.code = f.rule_code
