"""corpus export bookkeeping: corpus_exports, corpus_records, corpus_export_events

Revision ID: 0018_corpus_exports
Revises: 0017_document_text_source
Create Date: 2026-09-28

The training-corpus export used to write a record carrying the production
cases.id and an HMAC of the claim number straight into its final, non-expiring
S3 prefix, labelled "best-effort". Under HIPAA Safe Harbor (45 CFR §164.514(b)(2))
a code derived from the individual's information must be removed, and
§164.514(c) allows a re-identification code only if it is NOT so derived and its
mechanism is never disclosed. These three tables are that mechanism:

  corpus_exports        one row per run (versions, counts, quarantine keys).
  corpus_records        random record_id -> case_id. The only link back to a
                        patient. Never leaves the database. DELETE is granted
                        so practice disposal can sever the link; UPDATE is not.
  corpus_export_events  append-only release record: exported / released /
                        rejected, with the reviewer, the corpus sha256 and the
                        attested checklist. A corpus is de-identified only once a
                        `released` event exists — that event IS the documented
                        "no actual knowledge" determination, §164.514(b)(2)(ii).

Cross-tenant by design (an export spans practices); none of the three holds PHI.
The 0007 default privileges give heimdall_app SELECT+INSERT on new tables, which
is exactly right for corpus_exports and corpus_export_events; corpus_records
additionally gets DELETE. The events table gets the same BEFORE UPDATE / DELETE
/ TRUNCATE guard as audit_logs so the release record is tamper-evident even for
the table owner.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018_corpus_exports"
down_revision = "0017_document_text_source"
branch_labels = None
depends_on = None

APP_ROLE = "heimdall_app"


def upgrade() -> None:
    op.execute("CREATE TYPE corpus_export_event AS ENUM ('exported', 'released', 'rejected')")

    op.create_table(
        "corpus_exports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("detector_versions", postgresql.JSONB(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("quarantine_key", sa.Text(), nullable=False),
        sa.Column("report_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "corpus_records",
        sa.Column("record_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "export_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("corpus_exports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "practice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("practices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_corpus_records_export_id", "corpus_records", ["export_id"])
    op.create_index("ix_corpus_records_case_id", "corpus_records", ["case_id"])
    op.create_index("ix_corpus_records_practice_id", "corpus_records", ["practice_id"])

    op.create_table(
        "corpus_export_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "export_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("corpus_exports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "event",
            postgresql.ENUM(
                "exported", "released", "rejected", name="corpus_export_event", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_corpus_export_events_export_id", "corpus_export_events", ["export_id"])

    # Append-only guard on the release record. Own function (the 0001 one names
    # audit_logs in its message); same shape — row triggers for UPDATE/DELETE and
    # a statement trigger for TRUNCATE, all owner-effective.
    op.execute("""
        CREATE OR REPLACE FUNCTION corpus_export_events_block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'corpus_export_events is append-only; % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute(
        "CREATE TRIGGER trg_corpus_export_events_no_update BEFORE UPDATE ON "
        "public.corpus_export_events FOR EACH ROW EXECUTE FUNCTION "
        "corpus_export_events_block_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_corpus_export_events_no_delete BEFORE DELETE ON "
        "public.corpus_export_events FOR EACH ROW EXECUTE FUNCTION "
        "corpus_export_events_block_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_corpus_export_events_no_truncate BEFORE TRUNCATE ON "
        "public.corpus_export_events FOR EACH STATEMENT EXECUTE FUNCTION "
        "corpus_export_events_block_mutation()"
    )

    # Grants. Default privileges (0007) already give SELECT+INSERT. The mapping
    # table must be deletable by the disposal / wipe scripts, which run as the
    # app role. Guarded: the role may not exist on a database that never ran 0007
    # (the integration suite does run it, so this is belt-and-braces).
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            EXECUTE 'GRANT DELETE ON public.corpus_records TO {APP_ROLE}';
            EXECUTE 'REVOKE UPDATE, TRUNCATE ON public.corpus_records FROM {APP_ROLE}';
            EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON public.corpus_exports FROM {APP_ROLE}';
            EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON public.corpus_export_events '
                    'FROM {APP_ROLE}';
          END IF;
        END $$;
        """)


def downgrade() -> None:
    for trg in ("no_update", "no_delete", "no_truncate"):
        op.execute(
            f"DROP TRIGGER IF EXISTS trg_corpus_export_events_{trg} ON public.corpus_export_events"
        )
    op.execute("DROP FUNCTION IF EXISTS corpus_export_events_block_mutation()")
    op.drop_index("ix_corpus_export_events_export_id", table_name="corpus_export_events")
    op.drop_table("corpus_export_events")
    op.drop_index("ix_corpus_records_practice_id", table_name="corpus_records")
    op.drop_index("ix_corpus_records_case_id", table_name="corpus_records")
    op.drop_index("ix_corpus_records_export_id", table_name="corpus_records")
    op.drop_table("corpus_records")
    op.drop_table("corpus_exports")
    op.execute("DROP TYPE corpus_export_event")
