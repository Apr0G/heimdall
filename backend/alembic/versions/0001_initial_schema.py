"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-13

Creates the full Heimdall schema: uuid-ossp extension, all native enums, the
ten tables with FKs (ON DELETE RESTRICT), indexes, the updated_at trigger, and
the append-only guard on audit_logs.
"""

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)

# Enum values are frozen at this migration (do not edit; create a new migration
# to change an enum). Order is the creation order.
ENUMS: dict[str, tuple[str, ...]] = {
    "user_role": ("doctor", "office_manager", "admin"),
    "case_status": ("draft", "processing", "ready", "submitted", "resolved", "error"),
    "plan_type": (
        "commercial",
        "medicare",
        "medicare_advantage",
        "medicaid",
        "medicaid_mco",
        "tricare",
        "other",
        "unknown",
    ),
    "doc_type": (
        "denial",
        "claim",
        "clinical",
        "prior_auth",
        "prior_treatment",
        "other",
    ),
    "ocr_status": ("not_needed", "pending", "completed", "failed"),
    "denial_category": (
        "medical_necessity",
        "prior_auth",
        "coding_error",
        "bundling",
        "timely_filing",
        "non_covered",
        "missing_info",
        "wrong_payer",
        "other",
    ),
    "probability_band": ("low", "moderate", "high"),
    "appeal_level": (
        "level_1_internal",
        "peer_to_peer",
        "level_2_internal",
        "external_review",
    ),
    "letter_status": ("draft", "finalized", "downloaded", "archived"),
    "model_run_purpose": ("extraction", "analysis", "letter_draft", "classification"),
    "model_run_status": ("success", "error"),
    "outcome_action": ("appealed", "not_appealed", "pending"),
    "outcome_result": ("overturned", "upheld", "partial", "pending", "withdrawn"),
    "outcome_source": ("user_reported", "imported"),
}


def _enum(name: str) -> postgresql.ENUM:
    # create_type=False: the types are created/dropped explicitly below, so
    # column DDL only references them.
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _id() -> sa.Column:
    return sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()"))


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def upgrade() -> None:
    bind = op.get_bind()

    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)

    # --- practices ---
    op.create_table(
        "practices",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("npi", sa.Text()),
        sa.Column("tax_id", sa.Text()),
        sa.Column("address_line1", sa.Text()),
        sa.Column("address_line2", sa.Text()),
        sa.Column("city", sa.Text()),
        sa.Column("state", sa.Text()),
        sa.Column("zip", sa.Text()),
        sa.Column("baa_signed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("baa_version", sa.Text()),
        _created_at(),
        _updated_at(),
    )

    # --- users ---
    op.create_table(
        "users",
        _id(),
        sa.Column(
            "practice_id",
            UUID,
            sa.ForeignKey("practices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("cognito_sub", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text()),
        sa.Column(
            "role",
            _enum("user_role"),
            nullable=False,
            server_default=sa.text("'doctor'"),
        ),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True)),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("cognito_sub", name="uq_users_cognito_sub"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # --- cases ---
    op.create_table(
        "cases",
        _id(),
        sa.Column(
            "practice_id",
            UUID,
            sa.ForeignKey("practices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("case_status"),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("payer_name", sa.Text()),
        sa.Column(
            "plan_type",
            _enum("plan_type"),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("claim_number", sa.Text()),
        sa.Column("member_id_hash", sa.Text()),
        sa.Column("patient_initials", sa.Text()),
        sa.Column("date_of_service", sa.Date()),
        sa.Column("denial_date", sa.Date()),
        sa.Column("appeal_deadline", sa.Date()),
        sa.Column("billed_amount_cents", sa.BigInteger()),
        sa.Column("denied_amount_cents", sa.BigInteger()),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'USD'")),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_cases_practice_status", "cases", ["practice_id", "status"])
    op.create_index("ix_cases_appeal_deadline", "cases", ["appeal_deadline"])

    # --- model_runs (referenced by extractions/analyses/appeal_letters) ---
    op.create_table(
        "model_runs",
        _id(),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="RESTRICT")),
        sa.Column("purpose", _enum("model_run_purpose"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default=sa.text("'bedrock'")),
        sa.Column("model_id", sa.Text()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("raw_request_s3_key", sa.Text()),
        sa.Column("raw_response_s3_key", sa.Text()),
        sa.Column("status", _enum("model_run_status"), nullable=False),
        sa.Column("error_message", sa.Text()),
        _created_at(),
    )

    # --- documents ---
    op.create_table(
        "documents",
        _id(),
        sa.Column(
            "case_id",
            UUID,
            sa.ForeignKey("cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("doc_type", _enum("doc_type"), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text()),
        sa.Column("content_hash", sa.Text()),
        sa.Column("mime_type", sa.Text()),
        sa.Column("file_size_bytes", sa.BigInteger()),
        sa.Column(
            "ocr_status",
            _enum("ocr_status"),
            nullable=False,
            server_default=sa.text("'not_needed'"),
        ),
        sa.Column("ocr_completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "uploaded_by",
            UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("s3_key", name="uq_documents_s3_key"),
    )

    # --- extractions ---
    array_default = sa.text("'{}'::text[]")
    op.create_table(
        "extractions",
        _id(),
        sa.Column(
            "case_id",
            UUID,
            sa.ForeignKey("cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            UUID,
            sa.ForeignKey("documents.id", ondelete="RESTRICT"),
        ),
        sa.Column("payer_name", sa.Text()),
        sa.Column("plan_type", _enum("plan_type")),
        sa.Column("claim_number", sa.Text()),
        sa.Column(
            "carc_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=array_default,
        ),
        sa.Column(
            "rarc_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=array_default,
        ),
        sa.Column(
            "group_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=array_default,
        ),
        sa.Column(
            "cpt_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=array_default,
        ),
        sa.Column(
            "icd10_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=array_default,
        ),
        sa.Column(
            "modifiers",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=array_default,
        ),
        sa.Column(
            "pos_codes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=array_default,
        ),
        sa.Column("denial_date", sa.Date()),
        sa.Column("date_of_service", sa.Date()),
        sa.Column("billed_amount_cents", sa.BigInteger()),
        sa.Column("denied_amount_cents", sa.BigInteger()),
        sa.Column("extracted_json", postgresql.JSONB()),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("model_run_id", UUID, sa.ForeignKey("model_runs.id", ondelete="RESTRICT")),
        _created_at(),
    )

    # --- analyses ---
    op.create_table(
        "analyses",
        _id(),
        sa.Column(
            "case_id",
            UUID,
            sa.ForeignKey("cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("denial_category", _enum("denial_category")),
        sa.Column("is_appealable", sa.Boolean(), nullable=False),
        sa.Column("appealability_reason", sa.Text()),
        sa.Column("success_probability", sa.Numeric(4, 3)),
        sa.Column("probability_band", _enum("probability_band")),
        sa.Column("reasoning_text", sa.Text()),
        sa.Column("recommended_appeal_level", _enum("appeal_level")),
        sa.Column("model_run_id", UUID, sa.ForeignKey("model_runs.id", ondelete="RESTRICT")),
        _created_at(),
    )

    # --- appeal_letters ---
    op.create_table(
        "appeal_letters",
        _id(),
        sa.Column(
            "case_id",
            UUID,
            sa.ForeignKey("cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("appeal_type", _enum("appeal_level")),
        sa.Column(
            "status",
            _enum("letter_status"),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("model_run_id", UUID, sa.ForeignKey("model_runs.id", ondelete="RESTRICT")),
        sa.Column("finalized_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("downloaded_at", sa.TIMESTAMP(timezone=True)),
        _created_at(),
        sa.UniqueConstraint("case_id", "version", name="uq_appeal_letters_case_version"),
    )

    # --- outcomes ---
    op.create_table(
        "outcomes",
        _id(),
        sa.Column(
            "case_id",
            UUID,
            sa.ForeignKey("cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action_taken", _enum("outcome_action")),
        sa.Column("result", _enum("outcome_result")),
        sa.Column("amount_recovered_cents", sa.BigInteger()),
        sa.Column("resolution_date", sa.Date()),
        sa.Column("reported_by", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column(
            "reported_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("source", _enum("outcome_source")),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("case_id", name="uq_outcomes_case_id"),
    )

    # --- audit_logs (append-only) ---
    op.create_table(
        "audit_logs",
        _id(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("practice_id", UUID, sa.ForeignKey("practices.id", ondelete="RESTRICT")),
        sa.Column("action", sa.Text()),
        sa.Column("resource_type", sa.Text()),
        sa.Column("resource_id", UUID),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute("CREATE INDEX ix_audit_logs_practice_ts ON audit_logs (practice_id, timestamp DESC)")
    op.execute("CREATE INDEX ix_audit_logs_user_ts ON audit_logs (user_id, timestamp DESC)")

    # updated_at triggers on the mutable tables
    for table in ("practices", "users", "cases"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )

    # Append-only enforcement for audit_logs. We connect as the table owner, so
    # GRANT-level revocation would not bind; a trigger is the reliable guard.
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_logs_block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only; % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute(
        "CREATE TRIGGER trg_audit_logs_no_update BEFORE UPDATE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_audit_logs_no_delete BEFORE DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation()"
    )


def downgrade() -> None:
    # This drops EVERY PHI table plus audit_logs — a more complete destruction
    # than wipe-test-data, which at least demands a typed phrase and now a live
    # row count. It is not reachable from any workflow (migrate-db.yml runs the
    # baked `alembic upgrade head` and passes no --overrides), so this guard is
    # about the asymmetry, not a live path: the destructive operation should not
    # be the one with no confirmation.
    if os.environ.get("ALEMBIC_ALLOW_INITIAL_DOWNGRADE") != "DESTROY-ALL-DATA":
        raise RuntimeError(
            "Refusing to downgrade the initial revision: this DROPs every PHI "
            "table and the append-only audit_logs. Set "
            "ALEMBIC_ALLOW_INITIAL_DOWNGRADE=DESTROY-ALL-DATA to proceed, and "
            "take a snapshot first."
        )

    bind = op.get_bind()

    # Drop tables in reverse dependency order (triggers/indexes drop with them).
    for table in (
        "audit_logs",
        "outcomes",
        "appeal_letters",
        "analyses",
        "extractions",
        "documents",
        "model_runs",
        "cases",
        "users",
        "practices",
    ):
        op.drop_table(table)

    op.execute("DROP FUNCTION IF EXISTS audit_logs_block_mutation()")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    for name in reversed(list(ENUMS)):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
