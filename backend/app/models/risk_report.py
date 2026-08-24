import uuid

from sqlalchemy import ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKey
from app.models.enums import probability_band


class RiskReport(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Denial-risk report for a pre-check case — the pre-check analog of
    ``analyses``. One row per pipeline run; latest per case wins. Findings are
    the merged output of the deterministic NCCI engine and the documentation-
    review model call, schema-validated at write time (``schemas/precheck.py``).
    """

    __tablename__ = "risk_reports"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Reuses the probability_band enum as a severity scale; the column name
    # carries the semantics (high = high risk of denial — UI colors invert
    # relative to appeal success probability). Derived server-side from finding
    # severities, never taken from the model. Null only when there are no findings.
    overall_risk_band: Mapped[str | None] = mapped_column(probability_band, nullable=True)
    # List of finding objects: {check_id, severity, title, predicted_carc,
    # explanation, suggested_fix, source}. Contains claim/clinical detail —
    # treat as PHI-adjacent: fine in the DB (tenant-scoped), never in logs.
    findings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    deterministic_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    model_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Which NCCI load served the deterministic pass (e.g. "ptp 2026Q3-v322r0 /
    # mue 2026Q3"); null when no data was loaded and the pass was skipped.
    ncci_version_tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_risk_reports_case_created", "case_id", text("created_at DESC")),
        Index("ix_risk_reports_model_run_id", "model_run_id"),
    )
