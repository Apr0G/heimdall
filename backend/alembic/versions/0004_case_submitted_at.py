"""add cases.submitted_at

Revision ID: 0004_case_submitted_at
Revises: 0003_analysis_extra_docs
Create Date: 2026-06-18

Records when an appeal was marked submitted so the dashboard can nag for an
outcome after 30 days (Phase 11 flywheel).
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_case_submitted_at"
down_revision = "0003_analysis_extra_docs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cases", "submitted_at")
