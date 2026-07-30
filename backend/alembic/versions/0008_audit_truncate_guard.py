"""audit_logs TRUNCATE guard, users.is_active kill switch, denial categories, FK indexes

Revision ID: 0008_audit_truncate_guard
Revises: 0007_app_role
Create Date: 2026-07-30

Five unrelated-but-small schema changes from the 2026-07-28 codebase audit, batched
into one revision so the deploy takes a single migration window:

1. TRUNCATE guard on audit_logs (MED-03). The 0001 triggers are FOR EACH ROW, and
   Postgres row triggers do not fire on TRUNCATE — so the append-only guarantee had
   a hole that neither layer covered (the grant layer is inert while the app still
   connects as the table owner). A STATEMENT-level BEFORE TRUNCATE trigger is
   owner-effective, so it binds regardless of which role is connected.
2. users.is_active (MED-10). Cognito access tokens cannot be revoked, so a
   compromised session was live for its full 60-minute lifetime with no admin lever.
   The auth dependency now checks this column on every request, which turns
   deactivation into a sub-request-latency kill switch. The users row cannot simply
   be deleted because audit_logs.user_id is ON DELETE RESTRICT.
3. denial_category gains contractual_adjustment and patient_responsibility (LOW-14).
   CO-45 and PR-* previously collapsed into "other", hiding the two never-appeal
   classes from the corpus labels.
4. Eight unindexed foreign keys (LOW-07). All are ON DELETE RESTRICT, so a parent
   delete sequential-scans the child table across every tenant — dispose_practice is
   the operation most likely to time out on this.
5. Least-privilege tidy-up on the app role (LOW-03/LOW-04).
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_audit_truncate_guard"
down_revision = "0007_app_role"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"

# (index name, table, column) for the eight FKs that had no supporting index.
# cases.practice_id and both audit_logs FKs are already served by composite indexes
# whose leading column matches, so they are intentionally absent here.
_FK_INDEXES = [
    ("ix_users_practice_id", "users", "practice_id"),
    ("ix_cases_created_by", "cases", "created_by"),
    ("ix_documents_uploaded_by", "documents", "uploaded_by"),
    ("ix_extractions_source_document_id", "extractions", "source_document_id"),
    ("ix_extractions_model_run_id", "extractions", "model_run_id"),
    ("ix_analyses_model_run_id", "analyses", "model_run_id"),
    ("ix_appeal_letters_model_run_id", "appeal_letters", "model_run_id"),
    ("ix_outcomes_reported_by", "outcomes", "reported_by"),
]


def upgrade() -> None:
    # 1. Statement-level TRUNCATE guard. Reuses the 0001 function unchanged — it
    # raises with TG_OP, which reads 'TRUNCATE' here just as it reads UPDATE/DELETE.
    op.execute(
        "CREATE TRIGGER trg_audit_logs_no_truncate BEFORE TRUNCATE ON public.audit_logs "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_block_mutation()"
    )

    # 2. Kill switch. Defaults true so every existing row stays usable.
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("deactivated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Sliding activity stamp for the server-side idle timeout (MED-11). Null on
    # existing rows means "never seen", which _idle_deadline_exceeded treats as not
    # expired — so nobody is logged out by the deploy itself.
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 3. New denial categories. ADD VALUE IF NOT EXISTS is transaction-safe on PG 12+
    # provided the new label is not *used* in the same transaction, which it is not.
    for value in ("contractual_adjustment", "patient_responsibility"):
        op.execute(f"ALTER TYPE denial_category ADD VALUE IF NOT EXISTS '{value}'")

    # 4. FK indexes.
    for name, table, column in _FK_INDEXES:
        op.create_index(name, table, [column])

    # 4b. model_runs.case_id NOT NULL (LOW-13). A row with no case has no path to a
    # practice, so every tenancy filter in the app misses it — while the row still
    # holds S3 keys to raw document text. All three call sites always passed a real
    # id, so this should be a no-op. It fails LOUDLY rather than deleting or
    # reparenting anything: a model_runs row is a billing and training record, and
    # silently destroying one to make a migration pass is the wrong trade.
    op.execute("""
        DO $$
        DECLARE orphans bigint;
        BEGIN
            SELECT count(*) INTO orphans FROM model_runs WHERE case_id IS NULL;
            IF orphans > 0 THEN
                RAISE EXCEPTION 'model_runs has % row(s) with a NULL case_id. These '
                    'have no tenant path and must be triaged by hand before this '
                    'migration can set the column NOT NULL.', orphans;
            END IF;
        END $$;
        """)
    op.alter_column("model_runs", "case_id", nullable=False)

    # 5. Re-assert the audit_logs revoke schema-qualified (LOW-03), add TRUNCATE on
    # the new-in-this-revision surface, and drop the app role's pointless write
    # access to alembic_version (LOW-04) — only the migrate task, which connects as
    # the owner, ever writes it.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON public.audit_logs FROM {APP_ROLE}")
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON public.alembic_version FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"GRANT UPDATE, DELETE ON public.alembic_version TO {APP_ROLE}")

    op.alter_column("model_runs", "case_id", nullable=True)

    for name, table, _ in reversed(_FK_INDEXES):
        op.drop_index(name, table_name=table)

    # Postgres cannot remove an enum label, so 3 is deliberately not reversed. A
    # downgrade leaves the two labels in place and unused, which is harmless.

    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "deactivated_at")
    op.drop_column("users", "is_active")

    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON public.audit_logs")
