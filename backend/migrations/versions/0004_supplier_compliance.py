"""Supplier compliance: upload metadata, rejection reasons, duplicate-file guard.

Revision ID: 0004
Revises: 0003
"""

from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"

SQL = Path(__file__).resolve().parents[1] / "sql" / "0004_supplier_compliance.sql"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SQL.read_text())


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "DROP INDEX IF EXISTS compliance.ux_documents_supplier_file; "
        "DROP INDEX IF EXISTS compliance.ix_documents_supplier_type; "
        "ALTER TABLE compliance.documents DROP CONSTRAINT IF EXISTS ck_rejected_has_reason, "
        "DROP CONSTRAINT IF EXISTS ck_verified_has_verifier, DROP COLUMN IF EXISTS uploaded_by, "
        "DROP COLUMN IF EXISTS original_filename, DROP COLUMN IF EXISTS content_type, "
        "DROP COLUMN IF EXISTS size_bytes, DROP COLUMN IF EXISTS rejection_reason;"
    )
