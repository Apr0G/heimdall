"""deactivation_requests — a user asks to be deactivated; an admin decides

Revision ID: 0010_deactivation_requests
Revises: 0009_session_revocation
Create Date: 2026-08-21

Accounts belong to the practice, so there is no self-service delete or
deactivate. A user can REQUEST deactivation from Settings; an admin approves
(which runs the normal deactivation) or denies. One row per request, kept as a
record. The app role needs UPDATE to resolve a request (default privileges on
new tables are SELECT + INSERT only, by design — see 0007).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_deactivation_requests"
down_revision = "0009_session_revocation"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"


def upgrade() -> None:
    status = postgresql.ENUM("pending", "approved", "denied", name="deactivation_request_status")
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "deactivation_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "practice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="deactivation_request_status", create_type=False),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "resolved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_deactivation_requests_user_id", "deactivation_requests", ["user_id"])
    op.create_index(
        "ix_deactivation_requests_practice_id", "deactivation_requests", ["practice_id"]
    )
    # At most one OPEN request per user; resolved ones accumulate as history.
    op.create_index(
        "uq_deactivation_requests_pending",
        "deactivation_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.execute(
        "CREATE TRIGGER trg_deactivation_requests_set_updated_at BEFORE UPDATE ON "
        "deactivation_requests FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(f"GRANT UPDATE ON deactivation_requests TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("deactivation_requests")
    op.execute("DROP TYPE IF EXISTS deactivation_request_status")
