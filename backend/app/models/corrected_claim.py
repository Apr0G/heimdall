import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKey


class CorrectedClaim(Base, UUIDPrimaryKey, CreatedAtMixin):
    """A pre-check draft claim with the doctor's chosen edits applied in place
    (services/claim_patch.py). The pre-check analog of ``appeal_letters``:
    versioned per case, the PDF itself lives in S3 next to the source documents
    and is served by presigned URL — the backend never streams it.
    """

    __tablename__ = "corrected_claims"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Which report's proposed_edits the selections index into.
    risk_report_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("risk_reports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Null when none of the selected edits could be applied — the row still
    # records the attempt and the per-edit reasons, but there is no file.
    s3_key: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    # Per selected edit: {index, kind, target, value, applied, reason}. Codes
    # and modifiers only — no patient data.
    results: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    # Null = no charge changed; false = a line was removed but Box 28 could not
    # be located unambiguously, so the user must fix the total by hand.
    total_updated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    downloaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_corrected_claims_case_version"),
        Index("ix_corrected_claims_case_id", "case_id"),
        Index("ix_corrected_claims_risk_report_id", "risk_report_id"),
        Index("ix_corrected_claims_created_by", "created_by"),
    )
