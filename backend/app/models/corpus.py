"""Training-corpus export bookkeeping — the §164.514(c) re-identification
mechanism and the release record.

Three tables, deliberately cross-tenant (an export spans practices) and
deliberately NOT PHI-bearing:

  corpus_exports        one row per export run: versions of every layer that
                        shaped the output, where the quarantine objects landed.
  corpus_records        record_id (random, minted at export) -> case_id. This is
                        the ONLY link between a corpus record and a patient.
                        §164.514(c)(1): the code is not derived from information
                        about the individual; (c)(2): the mechanism is never
                        disclosed — this table never leaves the database.
                        Deletable (practice disposal must sever the link);
                        never updated.
  corpus_export_events  append-only: exported / released / rejected, with the
                        reviewer identity, the corpus hash and the checklist the
                        reviewer attested to. A corpus is de-identified only once
                        a `released` event exists for it.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKey
from app.models.enums import corpus_export_event


class CorpusExport(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "corpus_exports"

    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    # {"presidio": {...}, "comprehend": {...}, "image_digest": ...} — whatever
    # shaped the redaction, so a later audit can say which detectors ran.
    detector_versions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quarantine_key: Mapped[str] = mapped_column(Text, nullable=False)
    report_key: Mapped[str] = mapped_column(Text, nullable=False)


class CorpusRecord(Base):
    __tablename__ = "corpus_records"

    # Random, minted by the export — NOT the case id, NOT derived from anything.
    record_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    export_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("corpus_exports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    practice_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_corpus_records_export_id", "export_id"),
        Index("ix_corpus_records_case_id", "case_id"),
        # Practice disposal deletes this practice's mapping rows.
        Index("ix_corpus_records_practice_id", "practice_id"),
    )


class CorpusExportEvent(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Append-only (DB trigger + no UPDATE/DELETE grant)."""

    __tablename__ = "corpus_export_events"

    export_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("corpus_exports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event: Mapped[str] = mapped_column(corpus_export_event, nullable=False)
    # GitHub actor for released/rejected; "export-task" for exported.
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reviewer checklist, counts, released keys. Never an identifier.
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (Index("ix_corpus_export_events_export_id", "export_id"),)
