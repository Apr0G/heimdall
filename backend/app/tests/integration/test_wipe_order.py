"""wipe_test_data deletes in FK order under the app role — the H2 shape (audit
2026-08-25): the S3 purge is irreversible and runs FIRST, so a DELETE that
fails on an ON DELETE RESTRICT afterwards leaves rows pointing at nothing.
Nothing here exercises TRUNCATE (the app role never had it); it pins the order
against the migrated schema and runs the real DELETE loop inside a transaction
that is rolled back, so the shared database is untouched."""

from sqlalchemy import text

from app.scripts.wipe_test_data import CASE_TABLES


async def test_case_tables_delete_children_before_parents(sessions):
    async with sessions() as s:
        rows = (await s.execute(text("""
                    SELECT child.relname, parent.relname
                    FROM pg_constraint c
                    JOIN pg_class child ON child.oid = c.conrelid
                    JOIN pg_class parent ON parent.oid = c.confrelid
                    WHERE c.contype = 'f'
                    """))).all()
    order = {name: i for i, name in enumerate(CASE_TABLES)}
    for child, parent in rows:
        if child in order and parent in order and child != parent:
            assert order[child] < order[parent], f"{child} must be deleted before {parent}"
    # Every table that references a case-family table is itself in the list
    # (else its RESTRICT FK fails the wipe halfway) — audit_logs and
    # deactivation_requests reference users/practices only, by design.
    referencing = {child for child, parent in rows if parent in order}
    assert referencing <= set(CASE_TABLES), referencing - set(CASE_TABLES)


async def test_wipe_delete_loop_runs_clean_then_rolls_back(sessions, tenant):
    async with sessions() as s:
        for table in CASE_TABLES:
            await s.execute(text(f"DELETE FROM {table}"))  # nosemgrep
        await s.rollback()
