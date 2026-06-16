import uuid
from datetime import date, datetime

from sqlalchemy import TIMESTAMP, BigInteger, Date, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey
from app.models.enums import outcome_action, outcome_result, outcome_source


class Outcome(Base, UUIDPrimaryKey):
    __tablename__ = "outcomes"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    action_taken: Mapped[str | None] = mapped_column(outcome_action, nullable=True)
    result: Mapped[str | None] = mapped_column(outcome_result, nullable=True)
    amount_recovered_cents: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    resolution_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reported_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reported_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    source: Mapped[str | None] = mapped_column(outcome_source, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
