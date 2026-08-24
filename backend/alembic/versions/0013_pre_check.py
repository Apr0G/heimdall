"""Pre-check case type: case_type discriminator, risk_reports, pre_check_review purpose

Revision ID: 0013_pre_check
Revises: 0012_ncci_tables
Create Date: 2026-08-24

The pre-check feature's application schema:

* ``case_type`` enum + NOT NULL DEFAULT 'appeal' column on cases (PG11+ fast
  default — no table rewrite; every existing row is an appeal).
* ``pre_check_review`` added to model_run_purpose. ADD VALUE IF NOT EXISTS is
  transaction-safe on PG 12+ provided the new label is not *used* in the same
  transaction, which it is not (0008 pattern).
* ``risk_reports`` — the pre-check analog of analyses: one row per pipeline
  run, findings as JSONB (validated at write by schemas/precheck.py).
* DELETE grant on risk_reports for the app role: dispose_practice.py and
  wipe_test_data.py connect with the app DB credentials, and 0007's default
  privileges stop at SELECT + INSERT — without this, a practice disposal fails
  AFTER the S3 purge has already destroyed the objects, stalling a BAA
  destruction attestation mid-way.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013_pre_check"
down_revision = "0012_ncci_tables"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"


def upgrade() -> None:
    op.execute("CREATE TYPE case_type AS ENUM ('appeal', 'pre_check')")
    op.add_column(
        "cases",
        sa.Column(
            "case_type",
            postgresql.ENUM(name="case_type", create_type=False),
            nullable=False,
            server_default=sa.text("'appeal'"),
        ),
    )
    op.create_index(
        "ix_cases_practice_type_status", "cases", ["practice_id", "case_type", "status"]
    )

    op.execute("ALTER TYPE model_run_purpose ADD VALUE IF NOT EXISTS 'pre_check_review'")

    op.create_table(
        "risk_reports",
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
            "overall_risk_band",
            postgresql.ENUM(name="probability_band", create_type=False),
            nullable=True,
        ),
        sa.Column("findings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("deterministic_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("model_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ncci_version_tag", sa.Text(), nullable=True),
        sa.Column(
            "model_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_runs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_risk_reports_case_created",
        "risk_reports",
        ["case_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_risk_reports_model_run_id", "risk_reports", ["model_run_id"])

    # Disposal/wipe run with the app DB credentials (see module docstring).
    op.execute(f"GRANT DELETE ON public.risk_reports TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_index("ix_risk_reports_model_run_id", table_name="risk_reports")
    op.drop_index("ix_risk_reports_case_created", table_name="risk_reports")
    op.drop_table("risk_reports")
    # model_run_purpose keeps 'pre_check_review' — enum member removal requires a
    # type rebuild and the value is harmless when unused.
    op.drop_index("ix_cases_practice_type_status", table_name="cases")
    op.drop_column("cases", "case_type")
    op.execute("DROP TYPE case_type")
