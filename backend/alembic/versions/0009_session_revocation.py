"""users.sessions_revoked_at + session_keep_jti — app-side session revocation

Revision ID: 0009_session_revocation
Revises: 0008_audit_truncate_guard
Create Date: 2026-08-21

Cognito cannot revoke an issued access token, and this API verifies tokens
locally against the JWKS — so Cognito's GlobalSignOut alone does nothing to a
session that is already open here. A password change, a password reset, or an
admin deactivation must nevertheless end every other session, so:

* sessions_revoked_at — tokens issued (iat) before this instant are rejected by
  get_current_user. NULL = nothing revoked.
* session_keep_jti — the one token allowed to survive a revocation: the session
  that performed the password change, so the user isn't logged out of the tab
  they're sitting in. Reset/deactivation leave it NULL (nothing survives).
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_session_revocation"
down_revision = "0008_audit_truncate_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("sessions_revoked_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("session_keep_jti", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "session_keep_jti")
    op.drop_column("users", "sessions_revoked_at")
