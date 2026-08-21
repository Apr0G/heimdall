import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.models.enums import user_role


class User(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "users"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cognito_sub: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(user_role, nullable=False, server_default=text("'doctor'"))
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Session kill switch. Cognito access tokens are not revocable, so without this
    # a compromised session stays live for its full 60-minute lifetime. Checked in
    # get_current_user on every request; the row cannot be deleted instead because
    # audit_logs.user_id is ON DELETE RESTRICT.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    deactivated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Sliding activity stamp for the SERVER-SIDE idle timeout. The browser's
    # setTimeout is a UX affordance — a closed tab cancels it and leaves the
    # session valid for the token's full remaining life.
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # App-side session revocation (Cognito can't revoke issued access tokens and we
    # verify them locally). Tokens with iat before sessions_revoked_at are refused,
    # except the one whose jti equals session_keep_jti — the session that changed
    # the password keeps working; everything else is signed out.
    sessions_revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    session_keep_jti: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_users_practice_id", "practice_id"),)
