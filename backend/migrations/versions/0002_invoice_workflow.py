"""Invoice workflow: match exceptions + notifications.

Revision ID: 0002
Revises: 0001
"""

from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0002_invoice_workflow.sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "DROP TABLE IF EXISTS core.notifications; "
        "ALTER TABLE p2p.invoices DROP COLUMN IF EXISTS match_exceptions;"
    )
