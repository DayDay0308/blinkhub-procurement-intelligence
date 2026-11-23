"""Dagster orchestration for the BlinkHub analytics layer.

Every dbt model becomes a Dagster asset, with lineage from the app's tables (sources)
through staging to the marts Power BI reads. A daily schedule rebuilds and tests everything
at 03:00, after the worker's 02:00 risk scan, so the morning dashboards include last night's
flags. If a dbt test fails, the run fails and is visible in the Dagster UI.
"""

from pathlib import Path

from dagster import Definitions, ScheduleDefinition, define_asset_job
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

DBT_DIR = Path(__file__).resolve().parents[1] / "dbt"

dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR)
dbt_project.prepare_if_dev()  # parses the project into target/manifest.json during development


@dbt_assets(manifest=dbt_project.manifest_path)
def procurement_intelligence(context, dbt: DbtCliResource):
    """Build and test the staging views and analytics marts."""
    yield from dbt.cli(["build"], context=context).stream()


daily_refresh = define_asset_job("daily_refresh", selection="*")

defs = Definitions(
    assets=[procurement_intelligence],
    jobs=[daily_refresh],
    schedules=[
        ScheduleDefinition(
            job=daily_refresh,
            cron_schedule="0 3 * * *",
            execution_timezone="Africa/Johannesburg",
            name="daily_refresh_0300",
        )
    ],
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)
