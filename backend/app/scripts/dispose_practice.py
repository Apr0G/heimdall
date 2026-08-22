"""Destroy ONE practice's PHI — for BAA offboarding (contractual return/destruction).

Deletes, scoped to a single ``practice_id``:
  - the case-family DB rows (cases + outcomes/letters/analyses/extractions/documents/
    model_runs), in FK-safe order;
  - every S3 object under ``practices/<id>/`` (uploaded PDFs + extracted text) AND the
    ``model_runs/<run_id>/`` archives — including **all noncurrent versions and delete
    markers**, since the bucket is versioned (a plain delete would only hide them).

**Keeps** ``audit_logs`` (HIPAA activity record, no patient content) and the
practices/users rows (pinned by audit_logs; they hold workforce/business data, not
patient PHI).

Guarded: refuses to run unless ``DISPOSE_CONFIRM`` equals ``PRACTICE_ID`` (type the id
twice). Runs as a one-off in-VPC ECS task (the DB is private)::

    PRACTICE_ID=<uuid> DISPOSE_CONFIRM=<uuid> python -m app.scripts.dispose_practice
"""

import asyncio
import os
import uuid

import boto3
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.scripts import s3_purge

# Deleted in this order so ON DELETE RESTRICT FKs are satisfied (children that
# reference model_runs/documents first; model_runs before cases; cases last).
_DELETE_ORDER = [
    "outcomes",
    "appeal_letters",
    "analyses",
    "extractions",
    "documents",
    "model_runs",
]


async def main() -> None:
    pid = os.environ.get("PRACTICE_ID", "")
    if os.environ.get("DISPOSE_CONFIRM") != pid or not pid:
        raise SystemExit(
            "Refusing to run: set PRACTICE_ID and DISPOSE_CONFIRM to the same practice id."
        )
    try:
        uuid.UUID(pid)
    except ValueError as exc:
        raise SystemExit(f"PRACTICE_ID is not a valid UUID: {pid!r}") from exc

    engine = create_async_engine(settings.database_url)
    s3 = boto3.client("s3", region_name=settings.aws_region)
    bucket = settings.s3_bucket_name

    async with engine.connect() as conn:
        exists = await conn.scalar(text("SELECT 1 FROM practices WHERE id = :pid"), {"pid": pid})
        if not exists:
            raise SystemExit(f"No practice {pid} found — nothing to dispose.")
        case_count = await conn.scalar(
            text("SELECT count(*) FROM cases WHERE practice_id = :pid"), {"pid": pid}
        )
        # DISPOSE_CONFIRM is the same practice id the script already acts on, so
        # re-typing it proves intent about the id but nothing about the target's
        # actual state. Binding to the live case count means the operator must know
        # what they are destroying — and a stale dispatch against the wrong
        # environment aborts before any object is deleted.
        expected_raw = os.environ.get("DISPOSE_EXPECT_CASES", "")
        if not expected_raw.strip():
            raise SystemExit(
                f"Refusing to run without DISPOSE_EXPECT_CASES=<n>. This practice "
                f"currently has {case_count} case(s)."
            )
        try:
            expected = int(expected_raw)
        except ValueError as exc:
            raise SystemExit(
                f"DISPOSE_EXPECT_CASES must be an integer, got {expected_raw!r}"
            ) from exc
        if expected != case_count:
            raise SystemExit(
                f"ABORTED: practice {pid} has {case_count} case(s), but you "
                f"confirmed {expected}. Nothing was deleted."
            )
        # model_runs live under model_runs/<run_id>/ (not the practices/ prefix), so
        # collect their ids to purge those archives explicitly.
        run_ids = (
            (
                await conn.execute(
                    text(
                        "SELECT id FROM model_runs WHERE case_id IN "
                        "(SELECT id FROM cases WHERE practice_id = :pid)"
                    ),
                    {"pid": pid},
                )
            )
            .scalars()
            .all()
        )

    # S3 first (rows carry no S3 pointers we still need after this).
    s3_deleted = s3_purge.delete_all_versions(s3, bucket, f"practices/{pid}/")
    # Uploads that never reached create_case have no documents row and live only
    # under the practice's tmp prefix (1-day lifecycle, but the attestation must
    # not depend on a lifecycle rule firing).
    s3_deleted += s3_purge.delete_all_versions(s3, bucket, f"tmp-uploads/{pid}/")
    for run_id in run_ids:
        s3_deleted += s3_purge.delete_all_versions(s3, bucket, f"model_runs/{run_id}/")

    # Verify before dropping the rows — they are the only index of these keys, so
    # an incomplete purge stops being fixable the moment they are gone. This is a
    # contractual destruction under a BAA; the attestation must be true.
    s3_purge.assert_prefix_empty(s3, bucket, f"practices/{pid}/")
    s3_purge.assert_prefix_empty(s3, bucket, f"tmp-uploads/{pid}/")
    for run_id in run_ids:
        s3_purge.assert_prefix_empty(s3, bucket, f"model_runs/{run_id}/")

    async with engine.begin() as conn:
        for table in _DELETE_ORDER:
            # Table names are a hardcoded constant; practice_id is bound, not
            # interpolated — no SQL-injection surface.
            await conn.execute(
                text(  # nosemgrep
                    f"DELETE FROM {table} WHERE case_id IN "
                    "(SELECT id FROM cases WHERE practice_id = :pid)"
                ),
                {"pid": pid},
            )
        await conn.execute(text("DELETE FROM cases WHERE practice_id = :pid"), {"pid": pid})

    await engine.dispose()
    print(
        f"Disposed practice {pid}: {case_count} cases, {len(run_ids)} model runs, "
        f"{s3_deleted} S3 object versions. Kept audit_logs + practice/user rows."
    )


if __name__ == "__main__":
    asyncio.run(main())
