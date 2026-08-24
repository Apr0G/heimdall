import uuid
from datetime import date, datetime

from sqlalchemy import TIMESTAMP, BigInteger, Date, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.models.enums import case_status, case_type, plan_type


class Case(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "cases"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(case_status, nullable=False, server_default=text("'draft'"))
    # 'appeal' (denial + claim + clinical → appeal letter) or 'pre_check'
    # (draft claim + clinical → risk report). Discriminates pipelines, document
    # requirements, and which endpoints apply.
    case_type: Mapped[str] = mapped_column(
        case_type, nullable=False, server_default=text("'appeal'")
    )
    payer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_type: Mapped[str] = mapped_column(
        plan_type, nullable=False, server_default=text("'unknown'")
    )
    claim_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    member_id_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_initials: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_service: Mapped[date | None] = mapped_column(Date, nullable=True)
    denial_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    appeal_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    billed_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    denied_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'USD'"))
    # Populated when the pipeline fails (status='error'). Never contains PHI.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the doctor marked the appeal submitted; drives the "report your
    # outcome" reminder (Phase 11). Null until the case is submitted.
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Claim token for the background pipeline: each launch stamps a fresh UUID and
    # every phase aborts if it no longer matches — so only one runner owns the case.
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_cases_practice_status", "practice_id", "status"),
        # The case list filters practice + case_type (+ optional status).
        Index("ix_cases_practice_type_status", "practice_id", "case_type", "status"),
        Index("ix_cases_appeal_deadline", "appeal_deadline"),
        Index("ix_cases_created_by", "created_by"),
    )
