"""create the least-privilege heimdall_app runtime role

Revision ID: 0007_app_role
Revises: 0006_pipeline_run_id
Create Date: 2026-07-11

The app runtime connects as heimdall_app (this role), NOT the table owner
(heimdall_admin). heimdall_app does normal DML on the app tables but gets only
SELECT+INSERT on audit_logs and is not the owner — so it cannot UPDATE/DELETE
audit rows, TRUNCATE the table, or DROP the append-only trigger. The audit trail
is then tamper-resistant even if the app's DB credential is compromised
(HIPAA §164.312(b)).

Migrations keep running as the owner (heimdall_admin) via a dedicated migrate task
definition. The role password is injected as APP_DB_PASSWORD (from Secrets
Manager) so it never lives in this file or in the app's environment.
"""

import os
import re

from alembic import op

revision = "0007_app_role"
down_revision = "0006_pipeline_run_id"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"


def _app_password() -> str:
    pw = os.environ.get("APP_DB_PASSWORD", "")
    if not pw:
        raise RuntimeError(
            "APP_DB_PASSWORD is not set — the migrate task must inject the "
            "heimdall_app password so this migration can create the role."
        )
    # random_password uses special=false, so the password is alphanumeric. Reject
    # anything else rather than risk a SQL-literal escaping issue in the DDL below.
    if not re.fullmatch(r"[A-Za-z0-9]+", pw):
        raise RuntimeError("APP_DB_PASSWORD must be alphanumeric.")
    return pw


def upgrade() -> None:
    pw = _app_password()
    # Create-or-update the login role (idempotent).
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            ALTER ROLE {APP_ROLE} WITH LOGIN PASSWORD '{pw}';
          ELSE
            CREATE ROLE {APP_ROLE} WITH LOGIN PASSWORD '{pw}';
          END IF;
        END $$;
        """)
    # Connect + schema usage.
    op.execute(
        f"DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {APP_ROLE}', "
        "current_database()); END $$;"
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    # Full DML on existing tables/sequences...
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    # ...except audit_logs, which the app may only append to (never mutate). TRUNCATE
    # was never granted, and the role is not the owner, so it cannot drop the trigger.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {APP_ROLE}")
    # ...and the same DML on tables future migrations create (run as heimdall_admin).
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )


def downgrade() -> None:
    # Best-effort: only succeeds when nothing is connected as the role.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"
    )
    op.execute(f"DROP OWNED BY {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
