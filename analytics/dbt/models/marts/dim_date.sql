-- Calendar dimension. fiscal_year follows the South African government year (April-March).
select
    to_char(d, 'YYYYMMDD')::int                     as date_key,
    d::date                                         as date,
    extract(year from d)::int                       as year,
    extract(quarter from d)::int                    as quarter,
    extract(month from d)::int                      as month,
    to_char(d, 'Mon')                               as month_short,
    to_char(d, 'YYYY-MM')                           as year_month,
    extract(isodow from d)::int                     as day_of_week,
    extract(isodow from d) >= 6                     as is_weekend,
    case when extract(month from d) >= 4 then extract(year from d)::int + 1
         else extract(year from d)::int end         as fiscal_year,
    'FY' || case when extract(month from d) >= 4 then extract(year from d)::int + 1
                 else extract(year from d)::int end as fiscal_year_label
from generate_series(date '2024-01-01', date '2028-12-31', interval '1 day') as d
