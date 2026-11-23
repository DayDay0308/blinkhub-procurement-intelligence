-- Grain: one risk flag. Value at risk = the invoice amount when the flag is on an invoice.
select
    f.flag_id,
    f.rule_code,
    f.rule_name,
    f.severity,
    f.flag_status,
    f.flag_status in ('OPEN', 'UNDER_REVIEW', 'ESCALATED') as is_open,
    f.score,
    f.entity_type,
    f.entity_id,
    f.supplier_id,
    f.reason,
    to_char(f.detected_date, 'YYYYMMDD')::int              as detected_date_key,
    f.detected_date,
    f.resolved_date,
    i.invoice_amount                                       as value_at_risk
from {{ ref('stg_risk_flags') }} f
left join {{ ref('stg_invoices') }} i on f.entity_type = 'INVOICE' and i.invoice_id = f.entity_id
