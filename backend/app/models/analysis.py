import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKey
from app.models.enums import appeal_level, denial_category, probability_band


class Analysis(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "analyses"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    denial_category: Mapped[str | None] = mapped_column(denial_category, nullable=True)
    is_appealable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    appealability_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_probability: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    probability_band: Mapped[str | None] = mapped_column(
        probability_band, nullable=True
    )
    reasoning_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_appeal_level: Mapped[str | None] = mapped_column(
        appeal_level, nullable=True
    )
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
