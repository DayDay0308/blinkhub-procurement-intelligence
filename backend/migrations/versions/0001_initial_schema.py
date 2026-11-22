"""Initial schema: core, compliance, p2p, sourcing, risk, audit.

Revision ID: 0001
Revises:
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

SQL = Path(__file__).resolve().parents[1] / "sql" / "0001_initial_schema.sql"


def upgrade() -> None:
    # exec_driver_sql sends the file as-is (no bind-parameter parsing of '::' casts).
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "DROP SCHEMA IF EXISTS audit, risk, sourcing, p2p, compliance, core CASCADE;"
    )
