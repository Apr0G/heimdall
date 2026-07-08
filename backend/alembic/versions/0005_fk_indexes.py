"""add indexes on hot case_id foreign keys

Revision ID: 0005_fk_indexes
Revises: 0004_case_submitted_at
Create Date: 2026-07-08

Postgres does not auto-index foreign keys. The dashboard's per-case "latest row"
lookups (DISTINCT ON (case_id) ORDER BY created_at DESC over extractions/analyses,
and the case-detail _latest queries) were sequential scans whose cost grows with
the global row count across all tenants, hit constantly by the ReadyNotifier poll.

Composite (case_id, created_at DESC) serves the latest-per-case pattern directly;
documents/model_runs get a plain case_id index. appeal_letters (case_id, version)
and outcomes (case_id) are already covered by their unique constraints, so they
are intentionally omitted. Tables are small (MVP), so a plain non-concurrent
CREATE INDEX is fine — the brief write lock is negligible.
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_fk_indexes"
down_revision = "0004_case_submitted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_extractions_case_created",
        "extractions",
        ["case_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_analyses_case_created",
        "analyses",
        ["case_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_documents_case_id", "documents", ["case_id"])
    op.create_index("ix_model_runs_case_id", "model_runs", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_model_runs_case_id", table_name="model_runs")
    op.drop_index("ix_documents_case_id", table_name="documents")
    op.drop_index("ix_analyses_case_created", table_name="analyses")
    op.drop_index("ix_extractions_case_created", table_name="extractions")
