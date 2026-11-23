select * from {{ ref('mart_monthly_kpis') }} where smme_share < 0 or smme_share > 1
