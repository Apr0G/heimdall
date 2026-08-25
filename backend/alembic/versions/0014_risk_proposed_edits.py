"""risk_reports.proposed_edits — diff-style changes alongside the findings

Revision ID: 0014_risk_proposed_edits
Revises: 0013_pre_check
Create Date: 2026-08-25

Pre-check reports now lead with concrete, apply-in-the-PM edits
({kind, target, instruction, source}) instead of prose-only suggestions.
Additive column with a server default, so existing rows read as [].
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014_risk_proposed_edits"
down_revision = "0013_pre_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risk_reports",
        sa.Column(
            "proposed_edits",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("risk_reports", "proposed_edits")
