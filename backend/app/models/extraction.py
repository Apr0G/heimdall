import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKey
from app.models.enums import plan_type


def _str_array() -> Mapped[list[str]]:
    return mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))


class Extraction(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "extractions"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    payer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_type: Mapped[str | None] = mapped_column(plan_type, nullable=True)
    claim_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    carc_codes: Mapped[list[str]] = _str_array()
    rarc_codes: Mapped[list[str]] = _str_array()
    group_codes: Mapped[list[str]] = _str_array()
    cpt_codes: Mapped[list[str]] = _str_array()
    icd10_codes: Mapped[list[str]] = _str_array()
    modifiers: Mapped[list[str]] = _str_array()
    pos_codes: Mapped[list[str]] = _str_array()
    denial_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_of_service: Mapped[date | None] = mapped_column(Date, nullable=True)
    billed_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    denied_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    extracted_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
