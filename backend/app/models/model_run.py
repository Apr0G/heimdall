import uuid

from sqlalchemy import ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKey
from app.models.enums import model_run_purpose, model_run_status


class ModelRun(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "model_runs"

    # Non-null since 0008: a model_runs row holds S3 keys to raw document text, so a
    # row with no case has no practice_id path and is unreachable by every tenancy
    # filter in the app. All three call sites always passed a real id; the column
    # was nullable only by oversight.
    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(model_run_purpose, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'bedrock'"))
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_request_s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_s3_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(model_run_status, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_model_runs_case_id", "case_id"),)
