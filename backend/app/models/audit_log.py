import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class AuditLog(Base, UUIDPrimaryKey):
    """Append-only. UPDATE/DELETE are blocked by a DB trigger (see migration)."""

    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    practice_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="RESTRICT"),
        nullable=True,
    )
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "metadata" is reserved on the declarative Base, so the attribute is renamed.
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_audit_logs_practice_ts", "practice_id", text("timestamp DESC")),
        Index("ix_audit_logs_user_ts", "user_id", text("timestamp DESC")),
    )
