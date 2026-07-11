from datetime import datetime

from sqlalchemy import TIMESTAMP, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Practice(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "practices"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    npi: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line1: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    zip: Mapped[str | None] = mapped_column(Text, nullable=True)
    baa_signed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    baa_version: Mapped[str | None] = mapped_column(Text, nullable=True)
