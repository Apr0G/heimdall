"""Revoke INSERT on alembic_version from the app role

Revision ID: 0015_revoke_version_insert
Revises: 0014_risk_proposed_edits
Create Date: 2026-08-25

0007's blanket ``GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES`` reached
``alembic_version``; 0008's LOW-04 fix revoked only UPDATE/DELETE/TRUNCATE, so
INSERT survived. A compromised app credential could insert a spurious second
row into ``alembic_version`` and wedge the migration machinery (Alembic assumes
a single head row). Migrations run as the owner (heimdall_admin), not the app
role, so the app role never needs any write here. Keep SELECT for diagnostics.
"""

from alembic import op

revision = "0015_revoke_version_insert"
down_revision = "0014_risk_proposed_edits"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"


def upgrade() -> None:
    op.execute(f"REVOKE INSERT ON public.alembic_version FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"GRANT INSERT ON public.alembic_version TO {APP_ROLE}")
