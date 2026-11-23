"""Dagster loads dbt models from dbt's manifest (dbt/target/manifest.json). That folder is
generated output and is git-ignored, so a fresh checkout (e.g. CI) doesn't have it.
Parse the project first, as the Docker image does at build time. No database is needed."""

import subprocess
from pathlib import Path

DBT_DIR = Path(__file__).resolve().parents[1] / "dbt"

if not (DBT_DIR / "target" / "manifest.json").exists():
    subprocess.run(["dbt", "parse", "--profiles-dir", ".", "--quiet"], cwd=DBT_DIR, check=True)
