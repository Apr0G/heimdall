"""Wipe ALL case data across EVERY practice — empties the dashboard.

Deletes every row in the case-family tables and the corresponding S3 objects
(uploaded documents, extracted text, model-run payloads), **including all
noncurrent versions and delete markers** — the bucket is versioned, so a plain
keyed delete would only hide them. **Keeps** users, practices, and the append-only
``audit_logs`` (HIPAA record of activity).

The name understates the reach: nothing here is scoped to synthetic data or to one
tenant. If this is ever pointed at a database that has held real PHI, it destroys
every practice's documents.

Guarded: refuses to run unless ``WIPE_CONFIRM=WIPE`` **and** ``WIPE_EXPECT_CASES``
equals the live case count. The second guard is the one that matters — the first
is a constant hardcoded into the workflow's container override, so it proves
intent about the workflow rather than about the target.

**Requires the ``heimdall-dispose`` task role**, not the app role. Deleting from a
versioned bucket needs ``s3:DeleteObjectVersion`` + ``s3:ListBucketVersions``; the
app role holds only ``s3:DeleteObject``, which writes a delete marker and destroys
nothing. Running this under the app role fails at the S3 purge — by design, since
`assert_prefix_empty` then stops it before the TRUNCATE rather than emptying the
database while the documents survive.

Runs as a one-off ECS task inside the VPC (the DB is private):
``python -m app.scripts.wipe_test_data``
"""

import asyncio
import os

import boto3
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.scripts import s3_purge

# Every case-family table. TRUNCATE ... CASCADE resolves the ON DELETE RESTRICT
# FKs; audit_logs is intentionally absent (it references users/practices, not
# cases, so CASCADE never reaches it).
CASE_TABLES = [
    "extractions",
    "analyses",
    "appeal_letters",
    "outcomes",
    "documents",
    "model_runs",
    "cases",
]


async def main() -> None:
    if os.environ.get("WIPE_CONFIRM") != "WIPE":
        raise SystemExit("Refusing to run without WIPE_CONFIRM=WIPE")

    # WIPE_CONFIRM is a CONSTANT, and the workflow hardcodes it into the container
    # override — so on that path it proves nothing about intent. WIPE_EXPECT_CASES
    # binds the confirmation to the TARGET instead: the operator must already know
    # how much data is about to be destroyed, and a stale or blind dispatch (wrong
    # database, or many more rows than expected) aborts before touching anything.
    expected_raw = os.environ.get("WIPE_EXPECT_CASES", "")
    if not expected_raw.strip():
        raise SystemExit(
            "Refusing to run without WIPE_EXPECT_CASES=<n> — the number of cases "
            "you expect to destroy. Check the dashboard first."
        )
    try:
        expected_cases = int(expected_raw)
    except ValueError as exc:
        raise SystemExit(f"WIPE_EXPECT_CASES must be an integer, got {expected_raw!r}") from exc

    engine = create_async_engine(settings.database_url)
    s3 = boto3.client("s3", region_name=settings.aws_region)
    bucket = settings.s3_bucket_name

    async with engine.connect() as conn:
        actual_cases = await conn.scalar(text("SELECT count(*) FROM cases"))
    if actual_cases != expected_cases:
        raise SystemExit(
            f"ABORTED: this database has {actual_cases} case(s), but you confirmed "
            f"{expected_cases}. Nothing was deleted. Re-check which database you are "
            "pointed at before re-running."
        )

    # Collect the S3 keys before we drop the rows that reference them.
    async with engine.connect() as conn:
        doc_keys = (await conn.execute(text("SELECT s3_key FROM documents"))).scalars().all()
        run_keys = (
            await conn.execute(
                text("SELECT raw_request_s3_key, raw_response_s3_key FROM model_runs")
            )
        ).all()

    keys: set[str] = set()
    for k in doc_keys:
        keys.add(k)
        keys.add(f"{k}.extracted.txt")  # extracted-text sibling
    for req, resp in run_keys:
        if req:
            keys.add(req)
        if resp:
            keys.add(resp)

    key_list = [k for k in keys if k]

    # Purge the two prefixes wholesale, by VersionId. This is both the correct
    # delete for a versioned bucket AND more complete than walking the key list:
    # it also collects orphans whose rows were already gone, which the row-driven
    # delete could never have found.
    deleted = s3_purge.delete_all_versions(s3, bucket, "practices/")
    deleted += s3_purge.delete_all_versions(s3, bucket, "model_runs/")
    # Belt and braces for any referenced key outside those prefixes (e.g. a
    # document still sitting under tmp-uploads/ because the case never advanced).
    deleted += s3_purge.delete_all_versions_of_keys(s3, bucket, set(key_list))

    # Verify BEFORE truncating. The rows are the only index of these keys, so an
    # incomplete purge becomes unrecoverable the instant the tables are empty —
    # and the script would still print a destruction count that never happened.
    s3_purge.assert_prefix_empty(s3, bucket, "practices/")
    s3_purge.assert_prefix_empty(s3, bucket, "model_runs/")

    async with engine.begin() as conn:
        # CASE_TABLES is a hardcoded module constant, never user input, so
        # interpolating it into the TRUNCATE is not a SQL-injection vector.
        await conn.execute(
            text(f"TRUNCATE TABLE {', '.join(CASE_TABLES)} RESTART IDENTITY CASCADE")  # nosemgrep
        )

    await engine.dispose()
    print(
        f"Wiped {deleted} S3 object versions ({len(key_list)} keys referenced by rows) "
        f"and truncated {len(CASE_TABLES)} tables."
    )


if __name__ == "__main__":
    asyncio.run(main())
