"""Verify each stored document against its content_hash — integrity check (§164.312(c)).

Re-reads every uploaded PDF from S3, re-computes SHA-256, and compares it to the
``documents.content_hash`` recorded at ingest. Reports a summary and exits non-zero
if any document has been altered (tampering or corruption) so a scheduled run alerts.

One-off in-VPC ECS task (the DB is private)::

    python -m app.scripts.check_document_integrity
"""

import asyncio
import hashlib
from collections import Counter

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Document
from app.services import s3

# Error codes meaning "this object genuinely is not there" — benign, and distinct
# from "I was not allowed to look", which is the condition an attacker would
# manufacture to silence this check.
_BENIGN_MISSING = {"404", "NoSuchKey", "NotFound"}


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        documents = (await session.scalars(select(Document))).all()
    await engine.dispose()

    checked = matched = mismatched = 0
    unhashed = 0
    altered: list[str] = []
    skip_reasons: Counter = Counter()
    unreadable = 0

    for doc in documents:
        if not doc.content_hash:
            unhashed += 1  # ingested before hashing, or hash never computed
            continue
        try:
            data = await asyncio.to_thread(s3.get_bytes, doc.s3_key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            skip_reasons[code] += 1
            if code not in _BENIGN_MISSING:
                unreadable += 1
            continue
        except Exception as exc:  # noqa: BLE001 — record the kind, keep going
            skip_reasons[type(exc).__name__] += 1
            unreadable += 1
            continue
        checked += 1
        if hashlib.sha256(data).hexdigest() == doc.content_hash:
            matched += 1
        else:
            mismatched += 1
            altered.append(str(doc.id))

    skipped = unhashed + sum(skip_reasons.values())
    print(
        f"document integrity: checked={checked} matched={matched} "
        f"mismatched={mismatched} skipped={skipped} (unhashed={unhashed}, "
        f"unreadable={unreadable})"
    )
    if skip_reasons:
        # Error codes only — no keys, no PHI.
        print("skip reasons:", dict(skip_reasons))

    if altered:
        # Document ids are internal UUIDs, not PHI.
        print("ALTERED document ids:", ", ".join(altered))
        raise SystemExit(1)

    # A check that verified nothing is not a passing check. Previously the only
    # exit(1) was inside `if altered`, which is populated ONLY by a successful read
    # with a mismatch — so a KMS key-policy change or a revoked s3:GetObject made
    # every document skip and the job report "checked=0 mismatched=0" and exit 0,
    # green forever. An attacker who can modify bucket objects could suppress the
    # alert simply by breaking read access.
    if unreadable:
        raise SystemExit(
            f"FAILED: {unreadable} document(s) could not be read (not merely absent). "
            "This check cannot attest to integrity it was unable to verify — "
            "investigate S3/KMS permissions."
        )
    if documents and checked == 0:
        raise SystemExit(
            f"FAILED: {len(documents)} document(s) exist but none was verified. "
            "A check that verified nothing must not report success."
        )


if __name__ == "__main__":
    asyncio.run(main())
