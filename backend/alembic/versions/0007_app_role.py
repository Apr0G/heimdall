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

import sqlalchemy as sa

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
    #
    # The password never appears in DDL text in ONLINE mode. It was never
    # injectable (the regex above constrains it to alphanumerics), but an
    # inlined literal is logged verbatim by Postgres if the statement errors.
    # Offline `--sql` mode would inline it via literal_binds, so env.py refuses
    # to run offline at all.
    #
    # set_config() is an ordinary function call, so the value travels as a real
    # protocol-level bind parameter — unlike anything inside a `DO $$ ... $$`
    # body, which the server receives as one opaque string with no placeholders.
    # is_local=true scopes it to this transaction, so it is gone at commit.
    op.execute(sa.text("SELECT set_config('heimdall.app_pw', :pw, true)").bindparams(pw=pw))
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L',
                           '{APP_ROLE}', current_setting('heimdall.app_pw'));
          ELSE
            EXECUTE format('CREATE ROLE %I WITH LOGIN PASSWORD %L',
                           '{APP_ROLE}', current_setting('heimdall.app_pw'));
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
    # Schema-qualified, matching the grants above — an unqualified name resolves
    # against search_path, which is not guaranteed to be `public` for every caller.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON public.audit_logs FROM {APP_ROLE}")
    # ...and on tables future migrations create (run as heimdall_admin).
    #
    # SELECT + INSERT only by default. Postgres has no per-table exclusion for
    # ALTER DEFAULT PRIVILEGES, so a blanket UPDATE/DELETE grant would silently
    # re-grant them on audit_logs if that table were ever rebuilt — quietly
    # undoing the revoke above. Defaulting to append-only and granting the extra
    # DML per table means the failure mode is a permission error on a new table,
    # not a silent loss of the append-only guarantee on the audit trail.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public " f"GRANT SELECT, INSERT ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )


def downgrade() -> None:
    # Best-effort: only succeeds when nothing is connected as the role. Every
    # statement is wrapped in an existence check — DROP OWNED BY has no IF EXISTS
    # and ALTER DEFAULT PRIVILEGES errors on a missing role, so a downgrade on a
    # database where the role was never created used to abort partway.
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            EXECUTE format(
              'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
              'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM %I', '{APP_ROLE}');
            EXECUTE format(
              'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
              'REVOKE USAGE, SELECT ON SEQUENCES FROM %I', '{APP_ROLE}');
            EXECUTE format('DROP OWNED BY %I', '{APP_ROLE}');
            EXECUTE format('DROP ROLE %I', '{APP_ROLE}');
          END IF;
        END $$;
        """)
