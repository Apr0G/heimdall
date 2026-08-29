"""corrected_claims — a pre-check draft claim with chosen edits applied in place

Revision ID: 0016_corrected_claims
Revises: 0015_revoke_version_insert
Create Date: 2026-08-28

One row per apply; versioned per case like appeal_letters. The PDF lives in S3
(s3_key, under the practice prefix so disposal/purge and the lifecycle rule
cover it); the row keeps the per-edit outcome (codes and reason codes only).

Grants: 0007's default privileges give the app role SELECT/INSERT on new
tables. UPDATE is needed for downloaded_at; DELETE for dispose_practice.py /
wipe_test_data.py, which run with the app credentials.

Downgrade DESTROYS tenant data: it drops the rows whose ``s3_key`` is the only
index of the corrected-claim PDFs, orphaning every one of them in S3 (purge
them first, or they stay until the lifecycle rule). Gated by the same env var
as 0001; snapshot first.
"""

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016_corrected_claims"
down_revision = "0015_revoke_version_insert"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"


def upgrade() -> None:
    op.create_table(
        "corrected_claims",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "risk_report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("risk_reports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=True, unique=True),
        sa.Column("results", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("total_updated", sa.Boolean(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("downloaded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("case_id", "version", name="uq_corrected_claims_case_version"),
    )
    op.create_index("ix_corrected_claims_case_id", "corrected_claims", ["case_id"])
    op.create_index("ix_corrected_claims_risk_report_id", "corrected_claims", ["risk_report_id"])
    op.create_index("ix_corrected_claims_created_by", "corrected_claims", ["created_by"])
    op.execute(f"GRANT UPDATE, DELETE ON public.corrected_claims TO {APP_ROLE}")


def downgrade() -> None:
    # Same gate as 0001: the destructive direction must not be the one with no
    # confirmation. Not reachable from any workflow; guards a hand-run.
    if os.environ.get("ALEMBIC_ALLOW_INITIAL_DOWNGRADE") != "DESTROY-ALL-DATA":
        raise RuntimeError(
            "Refusing to downgrade 0016: this DROPs corrected_claims (tenant PHI) and "
            "orphans every corrected-claim PDF in S3 — s3_key is their only index. "
            "Purge them, take a snapshot, then set "
            "ALEMBIC_ALLOW_INITIAL_DOWNGRADE=DESTROY-ALL-DATA to proceed."
        )
    op.drop_index("ix_corrected_claims_created_by", table_name="corrected_claims")
    op.drop_index("ix_corrected_claims_risk_report_id", table_name="corrected_claims")
    op.drop_index("ix_corrected_claims_case_id", table_name="corrected_claims")
    op.drop_table("corrected_claims")
