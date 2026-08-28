"""documents.text_source — where a document's text came from

Revision ID: 0017_document_text_source
Revises: 0016_corrected_claims
Create Date: 2026-08-28

pdf_text (born-digital page text), ocr (Textract), form_fields (a fillable
AcroForm read through its field values). Nullable: rows extracted before this
revision stay null and are interpreted via ocr_status. Additive; no backfill.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017_document_text_source"
down_revision = "0016_corrected_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE text_source AS ENUM ('pdf_text', 'ocr', 'form_fields')")
    op.add_column(
        "documents",
        sa.Column(
            "text_source",
            postgresql.ENUM(
                "pdf_text", "ocr", "form_fields", name="text_source", create_type=False
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "text_source")
    op.execute("DROP TYPE text_source")
