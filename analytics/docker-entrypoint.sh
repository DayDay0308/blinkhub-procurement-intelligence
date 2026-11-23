#!/bin/sh
set -e
# Build the marts once at start-up so Power BI has data immediately,
# then serve the Dagster UI (schedules run from its daemon).
echo "Building analytics marts with dbt..."
(cd dbt && dbt build --profiles-dir . --quiet) || echo "dbt build failed - see the Dagster UI to re-run"
exec dagster dev -h 0.0.0.0 -p 3000
