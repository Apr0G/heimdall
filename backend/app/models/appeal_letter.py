import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKey
from app.models.enums import appeal_level, letter_status


class AppealLetter(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "appeal_letters"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    appeal_type: Mapped[str | None] = mapped_column(appeal_level, nullable=True)
    status: Mapped[str] = mapped_column(
        letter_status, nullable=False, server_default=text("'draft'")
    )
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    finalized_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_appeal_letters_case_version"),
        Index("ix_appeal_letters_model_run_id", "model_run_id"),
    )
