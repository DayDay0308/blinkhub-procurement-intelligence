-- Supplier dimension with B-BBEE procurement recognition (Codes of Good Practice):
-- spend with a Level 1 supplier counts 135% towards the buyer's preferential procurement score.
with docs as (
    select supplier_id,
           max(expiry_date) filter (where doc_type = 'TAX_CLEARANCE')      as tax_clearance_expiry,
           max(expiry_date) filter (where doc_type = 'BBBEE_CERTIFICATE') as bbbee_certificate_expiry,
           bool_or(doc_type = 'TAX_CLEARANCE' and doc_status = 'VERIFIED'
                   and coalesce(expiry_date, 'infinity') >= current_date) as tax_clearance_valid
    from {{ ref('stg_documents') }}
    group by 1
)
select
    s.*,
    case when s.bbbee_level is null then 'Non-compliant'
         else 'Level ' || s.bbbee_level end                                    as bbbee_level_label,
    case s.bbbee_level when 1 then 1.35 when 2 then 1.25 when 3 then 1.10 when 4 then 1.00
                       when 5 then 0.80 when 6 then 0.60 when 7 then 0.50 when 8 then 0.10
                       else 0 end                                              as bbbee_recognition,
    coalesce(d.tax_clearance_valid, false)                                     as tax_clearance_valid,
    d.tax_clearance_expiry,
    d.bbbee_certificate_expiry
from {{ ref('stg_suppliers') }} s
left join docs d on d.supplier_id = s.supplier_id
