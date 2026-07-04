"""Wipe all synthetic case data — empties the dashboard.

Deletes every row in the case-family tables and the corresponding S3 objects
(uploaded documents, extracted text, model-run payloads). **Keeps** users,
practices, and the append-only ``audit_logs`` (HIPAA record of activity).

Guarded: refuses to run unless ``WIPE_CONFIRM=WIPE``. Meant to run as a one-off
ECS task inside the VPC (the DB is private):  ``python -m app.scripts.wipe_test_data``
"""

import asyncio
import os

import boto3
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

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

    engine = create_async_engine(settings.database_url)
    s3 = boto3.client("s3", region_name=settings.aws_region)
    bucket = settings.s3_bucket_name

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
    for i in range(0, len(key_list), 1000):  # delete_objects caps at 1000/call
        batch = [{"Key": k} for k in key_list[i : i + 1000]]
        s3.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True})

    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {', '.join(CASE_TABLES)} RESTART IDENTITY CASCADE")
        )

    await engine.dispose()
    print(f"Wiped {len(key_list)} S3 objects and truncated {len(CASE_TABLES)} tables.")


if __name__ == "__main__":
    asyncio.run(main())
