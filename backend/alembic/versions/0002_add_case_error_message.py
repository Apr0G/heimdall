"""add cases.error_message

Revision ID: 0002_add_case_error_message
Revises: 0001_initial_schema
Create Date: 2026-06-14

The pipeline records failures on the case (status='error' + error_message),
per the "no silent failures" rule. The initial schema lacked the column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_add_case_error_message"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "error_message")
