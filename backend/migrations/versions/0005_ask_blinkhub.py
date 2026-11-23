"""Ask BlinkHub: read-only `ask` views and the blinkhub_ask role.

Revision ID: 0005
Revises: 0004
"""

import os
from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0005_ask_blinkhub.sql"


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(SQL.read_text())
    password = os.getenv("ASK_DB_PASSWORD", "ask-local-dev-password").replace("'", "''")
    conn.exec_driver_sql(f"ALTER ROLE blinkhub_ask PASSWORD '{password}'")


def downgrade() -> None:
    # The role is cluster-wide and may serve other databases, so it is kept.
    op.get_bind().exec_driver_sql("DROP SCHEMA IF EXISTS ask CASCADE;")
