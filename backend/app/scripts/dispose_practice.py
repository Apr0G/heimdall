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


def _delete_all_versions(s3, bucket: str, prefix: str) -> int:
    """Delete every version + delete-marker under a prefix (versioned bucket)."""
    victims: list[dict] = []
    paginator = s3.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for entry in page.get("Versions", []) + page.get("DeleteMarkers", []):
            victims.append({"Key": entry["Key"], "VersionId": entry["VersionId"]})
    for i in range(0, len(victims), 1000):  # delete_objects caps at 1000/call
        s3.delete_objects(Bucket=bucket, Delete={"Objects": victims[i : i + 1000], "Quiet": True})
    return len(victims)


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
    s3_deleted = _delete_all_versions(s3, bucket, f"practices/{pid}/")
    for run_id in run_ids:
        s3_deleted += _delete_all_versions(s3, bucket, f"model_runs/{run_id}/")

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
