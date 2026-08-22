import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.models.enums import deactivation_request_status


class DeactivationRequest(Base, UUIDPrimaryKey, TimestampMixin):
    """A user's request to have their own account deactivated. Accounts belong
    to the practice, so the decision is an admin's; this is the ticket."""

    __tablename__ = "deactivation_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    practice_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("practices.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        deactivation_request_status, nullable=False, server_default=text("'pending'")
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Mirrors 0010/0011 so autogenerate never proposes dropping them — the
    # partial unique index is the only guard on "one open request per user".
    __table_args__ = (
        Index("ix_deactivation_requests_user_id", "user_id"),
        Index("ix_deactivation_requests_practice_id", "practice_id"),
        Index("ix_deactivation_requests_resolved_by", "resolved_by"),
        Index(
            "uq_deactivation_requests_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
