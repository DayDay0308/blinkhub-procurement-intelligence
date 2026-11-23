"""Risk engine: rule catalogue, flag bookkeeping, PO delivery dates, synthetic labels.

Revision ID: 0003
Revises: 0002
"""

from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0003_risk_engine.sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "DROP SCHEMA IF EXISTS synthetic CASCADE; DELETE FROM risk.flags; DELETE FROM risk.rules; "
        "ALTER TABLE risk.flags DROP COLUMN IF EXISTS last_seen_at, DROP COLUMN IF EXISTS resolved_by; "
        "ALTER TABLE p2p.purchase_orders DROP COLUMN IF EXISTS expected_delivery_date;"
    )
