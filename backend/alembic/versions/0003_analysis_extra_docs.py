"""add analyses.additional_documents_needed

Revision ID: 0003_analysis_extra_docs
Revises: 0002_add_case_error_message
Create Date: 2026-06-17

The analysis records which extra documents would strengthen the appeal (Phase
12 conditional uploads). The initial schema lacked the column.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_analysis_extra_docs"
down_revision = "0002_add_case_error_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column(
            "additional_documents_needed",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )


def downgrade() -> None:
    op.drop_column("analyses", "additional_documents_needed")
