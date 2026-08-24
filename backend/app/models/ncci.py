"""CMS NCCI reference tables (no PHI, no tenant column — shared read-mostly data).

Loaded quarterly by ``app.scripts.load_ncci`` and read by ``services/ncci.py``.
Natural composite PKs and no timestamp mixins on the two data tables — they are
bulk-replaced snapshots of CMS files, and ``ncci_loads`` carries the provenance
(see the 0012 migration docstring for the convention deviation rationale).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Date,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NcciPtpEdit(Base):
    __tablename__ = "ncci_ptp_edits"

    column1: Mapped[str] = mapped_column(Text, primary_key=True)
    column2: Mapped[str] = mapped_column(Text, primary_key=True)
    effective_date: Mapped[date] = mapped_column(Date, primary_key=True)
    # NULL = still active. Active window is [effective_date, deletion_date):
    # a retroactive withdrawal (deletion == effective, indicator 9) matches no DOS.
    deletion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    modifier_indicator: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_ncci_ptp_edits_column2", "column2"),)


class NcciMue(Base):
    __tablename__ = "ncci_mue"

    hcpcs: Mapped[str] = mapped_column(Text, primary_key=True)
    effective_quarter: Mapped[str] = mapped_column(Text, primary_key=True)  # "2026Q3"
    mue_value: Mapped[int] = mapped_column(Integer, nullable=False)
    mai: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)


class NcciLoad(Base):
    __tablename__ = "ncci_loads"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # 'ptp' | 'mue'
    quarter: Mapped[str] = mapped_column(Text, nullable=False)
    version_tag: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("kind IN ('ptp', 'mue')", name="ck_ncci_loads_kind"),
        UniqueConstraint("kind", "quarter", "version_tag", name="uq_ncci_loads_version"),
    )
