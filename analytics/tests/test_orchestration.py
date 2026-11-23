"""Load the Dagster definitions and materialize every asset against the database."""

from dagster import materialize

from orchestration.definitions import defs, procurement_intelligence


def test_definitions_load_with_schedule():
    assert defs.get_schedule_def("daily_refresh_0300").cron_schedule == "0 3 * * *"
    keys = {k.path[-1] for k in procurement_intelligence.keys}
    assert {"fct_purchase_orders", "fct_invoices", "dim_supplier", "mart_monthly_kpis"} <= keys


def test_materialize_all_assets_runs_dbt_build():
    result = materialize([procurement_intelligence], resources=defs.resources)
    assert result.success
