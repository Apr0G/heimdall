"""Verify each stored document against its content_hash — integrity check (§164.312(c)).

Re-reads every uploaded PDF from S3, re-computes SHA-256, and compares it to the
``documents.content_hash`` recorded at ingest. Reports a summary and exits non-zero
if any document has been altered (tampering or corruption) so a scheduled run alerts.

One-off in-VPC ECS task (the DB is private)::

    python -m app.scripts.check_document_integrity
"""

import asyncio
import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Document
from app.services import s3


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        documents = (await session.scalars(select(Document))).all()
    await engine.dispose()

    checked = matched = mismatched = skipped = 0
    altered: list[str] = []
    for doc in documents:
        if not doc.content_hash:
            skipped += 1  # ingested before hashing, or hash never computed
            continue
        try:
            data = await asyncio.to_thread(s3.get_bytes, doc.s3_key)
        except Exception:  # noqa: BLE001 — a missing/unreadable object is skipped, not fatal
            skipped += 1
            continue
        checked += 1
        if hashlib.sha256(data).hexdigest() == doc.content_hash:
            matched += 1
        else:
            mismatched += 1
            altered.append(str(doc.id))

    print(
        f"document integrity: checked={checked} matched={matched} "
        f"mismatched={mismatched} skipped={skipped}"
    )
    if altered:
        # Document ids are internal UUIDs, not PHI.
        print("ALTERED document ids:", ", ".join(altered))
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
