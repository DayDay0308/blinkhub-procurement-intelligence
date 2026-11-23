-- One row per supplier, with readable labels and the data-source marker that lets every
-- report separate the real case-study sample from the synthetic demonstration year.
select
    id                                              as supplier_id,
    supplier_code,
    legal_name                                      as supplier_name,
    supplier_type::text                             as supplier_type,
    supplier_type = 'SMME'                          as is_smme,
    enterprise_size::text                           as enterprise_size,
    province::text                                  as province_code,
    case province::text
        when 'GAUTENG' then 'Gauteng'
        when 'LIMPOPO' then 'Limpopo'
        when 'KWAZULU_NATAL' then 'KwaZulu-Natal'
        when 'MPUMALANGA' then 'Mpumalanga'
        when 'NORTH_WEST' then 'North West'
        when 'FREE_STATE' then 'Free State'
        when 'EASTERN_CAPE' then 'Eastern Cape'
        when 'WESTERN_CAPE' then 'Western Cape'
        when 'NORTHERN_CAPE' then 'Northern Cape'
    end                                             as province,
    bbbee_level,
    black_owned_pct,
    black_women_owned_pct,
    coalesce(black_owned_pct >= 51, false)          as is_black_owned,          -- B-BBEE: 51%+
    coalesce(black_women_owned_pct >= 30, false)    as is_black_women_owned,    -- B-BBEE: 30%+
    status::text                                    as status,
    created_at,
    case when supplier_code like 'SYN-%' then 'SYNTHETIC' else 'CASE_STUDY' end as data_source
from {{ source('core', 'suppliers') }}
