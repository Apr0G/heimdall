"""deactivation_requests hardening: resolved_by index, qualified grant, audit triggers ALWAYS

Revision ID: 0011_dr_hardening
Revises: 0010_deactivation_requests
Create Date: 2026-08-21

Three small follow-ups from the 2026-08-21 codebase audit:

1. resolved_by is an ON DELETE RESTRICT FK with no supporting index — the exact
   class of defect 0008 eliminated (a parent delete sequential-scans the child).
2. 0010 granted UPDATE with an unqualified table name; re-issue it
   schema-qualified, as 0007/0008 require, so a non-default search_path cannot
   resolve it against the wrong object.
3. The audit_logs append-only triggers were created ENABLE ORIGIN (the
   default), which `session_replication_role = replica` silently disables —
   a path open to the owner/rds_superuser. ENABLE ALWAYS closes it; the app
   role was never able to set that GUC, so this hardens the owner path only.
4. model_runs.input_truncated — whether a prompt section was length-capped
   before the call. Previously only an in-band marker the model could see.
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_dr_hardening"
down_revision = "0010_deactivation_requests"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"

_AUDIT_TRIGGERS = (
    "trg_audit_logs_no_update",
    "trg_audit_logs_no_delete",
    "trg_audit_logs_no_truncate",
)


def upgrade() -> None:
    op.add_column(
        "model_runs",
        sa.Column("input_truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "ix_deactivation_requests_resolved_by", "deactivation_requests", ["resolved_by"]
    )
    op.execute(f"GRANT UPDATE ON public.deactivation_requests TO {APP_ROLE}")
    for trigger in _AUDIT_TRIGGERS:
        op.execute(f"ALTER TABLE public.audit_logs ENABLE ALWAYS TRIGGER {trigger}")


def downgrade() -> None:
    op.drop_column("model_runs", "input_truncated")
    for trigger in _AUDIT_TRIGGERS:
        op.execute(f"ALTER TABLE public.audit_logs ENABLE TRIGGER {trigger}")
    op.drop_index("ix_deactivation_requests_resolved_by", table_name="deactivation_requests")
