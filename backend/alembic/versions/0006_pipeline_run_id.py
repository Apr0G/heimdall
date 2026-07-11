"""add cases.pipeline_run_id (pipeline claim token)

Revision ID: 0006_pipeline_run_id
Revises: 0005_fk_indexes
Create Date: 2026-07-10

A claim token so only one background pipeline owns a case at a time. Each launch
(create / retry / reanalyze) stamps a fresh UUID; every pipeline phase checks the
token still matches and aborts if a newer run has superseded it. This prevents a
stall-detection retry from spawning a second concurrent pipeline (duplicate
Textract/Bedrock spend + letter-version unique collisions that flip the case to
error even though the other run succeeded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0006_pipeline_run_id"
down_revision = "0005_fk_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("pipeline_run_id", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "pipeline_run_id")
