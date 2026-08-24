"""NCCI reference tables: PTP edits, MUE values, load bookkeeping

Revision ID: 0012_ncci_tables
Revises: 0011_dr_hardening
Create Date: 2026-08-24

CMS NCCI reference data for the pre-check feature (and the appeal-side CO-97
modifier-indicator lookup). Pure reference data — no PHI, no tenant column.

Two deliberate deviations from the house conventions, both because these are
bulk-replaced reference tables rather than application rows:

* Natural composite primary keys instead of UUIDs. The PK is the CMS identity
  of the row ((column1, column2, effective_date) / (hcpcs, effective_quarter)),
  a surrogate UUID would only add 16 bytes x ~2.6M rows plus an index nobody
  queries.
* No created_at/updated_at. Rows are replaced wholesale each quarterly load;
  per-row timestamps would claim a provenance the load process doesn't have.
  ncci_loads carries the provenance instead.

The app role gets an explicit DELETE grant on the two data tables: the loader
runs as heimdall_app (one-off ECS task on the app task definition) and replaces
the data in place, and 0007's default privileges stop at SELECT + INSERT.
ncci_loads is append-only history — no DELETE there.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012_ncci_tables"
down_revision = "0011_dr_hardening"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"


def upgrade() -> None:
    op.create_table(
        "ncci_ptp_edits",
        sa.Column("column1", sa.Text(), nullable=False),
        sa.Column("column2", sa.Text(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        # NULL = edit still active. A retroactively withdrawn edit arrives with
        # deletion_date == effective_date (and modifier indicator 9): with the
        # active window treated as [effective_date, deletion_date), that row
        # matches no date of service — exactly CMS's "as if it never existed".
        sa.Column("deletion_date", sa.Date(), nullable=True),
        sa.Column("modifier_indicator", sa.SmallInteger(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("column1", "column2", "effective_date", name="pk_ncci_ptp_edits"),
    )
    # The PK index serves column1-prefix lookups; pair lookups also probe by
    # column2 (a claim's codes appear on either side of an edit).
    op.create_index("ix_ncci_ptp_edits_column2", "ncci_ptp_edits", ["column2"])

    op.create_table(
        "ncci_mue",
        sa.Column("hcpcs", sa.Text(), nullable=False),
        sa.Column("mue_value", sa.Integer(), nullable=False),
        sa.Column("mai", sa.SmallInteger(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        # e.g. "2026Q3". MUE files are current-state snapshots with no in-band
        # history, so the quarter lives in the PK and each load adds a quarter
        # rather than overwriting the past.
        sa.Column("effective_quarter", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("hcpcs", "effective_quarter", name="pk_ncci_mue"),
    )

    op.create_table(
        "ncci_loads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("kind", sa.Text(), nullable=False),  # 'ptp' | 'mue'
        sa.Column("quarter", sa.Text(), nullable=False),  # e.g. "2026Q3"
        sa.Column("version_tag", sa.Text(), nullable=False),  # e.g. "v322r0"
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column(
            "loaded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("kind IN ('ptp', 'mue')", name="ck_ncci_loads_kind"),
        sa.UniqueConstraint("kind", "quarter", "version_tag", name="uq_ncci_loads_version"),
    )

    # Loader replaces data in place as heimdall_app; 0007 defaults grant only
    # SELECT + INSERT on new tables. Schema-qualified per 0011.
    op.execute(f"GRANT DELETE ON public.ncci_ptp_edits TO {APP_ROLE}")
    op.execute(f"GRANT DELETE ON public.ncci_mue TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("ncci_loads")
    op.drop_table("ncci_mue")
    op.drop_index("ix_ncci_ptp_edits_column2", table_name="ncci_ptp_edits")
    op.drop_table("ncci_ptp_edits")
