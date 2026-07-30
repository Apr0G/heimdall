"""Print recent cases with their document/pipeline state.

A no-psql way to inspect what the pipeline produced while testing. Run with the
backend venv active, from the repo root:

    python scripts/show_cases.py --practice-id <uuid>

TENANCY AND PHI. This script previously ran an unscoped
``select(Case).limit(15)`` and printed ``claim_number`` and ``payer_name`` to
stdout. Claim numbers are §164.514(b)(2)(i)(H) account identifiers, and
``DATABASE_URL`` resolves from the repo-root ``.env.local`` — which points at
RDS. So one command dumped the 15 most recent REAL claim numbers across ALL
tenants into terminal history and scrollback, i.e. straight out of the boundary
and into an agent transcript.

It now requires an explicit ``--practice-id``, prints a case-id prefix instead of
the claim number, and refuses to run against a non-local database unless
``ALLOW_REMOTE_DB=1`` is set deliberately.
"""

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import Analysis, Case, Document, Extraction  # noqa: E402

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres", ""}


def _assert_local_database() -> None:
    """Refuse to read a non-local database unless explicitly allowed.

    The failure mode this prevents is silent: nothing about running a dev helper
    signals that it is about to read production PHI.
    """
    if os.environ.get("ALLOW_REMOTE_DB") == "1":
        print(
            "WARNING: ALLOW_REMOTE_DB=1 — reading a non-local database.",
            file=sys.stderr,
        )
        return
    host = (urlsplit(settings.database_url).hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        raise SystemExit(
            f"Refusing to run: DATABASE_URL points at a non-local host ({host!r}). "
            "This prints tenant data. Set ALLOW_REMOTE_DB=1 only if you really "
            "intend to read that database."
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--practice-id",
        required=True,
        type=uuid.UUID,
        help="Practice to inspect. Required — there is no global view (hard rule 3).",
    )
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    _assert_local_database()

    async with AsyncSessionLocal() as session:
        cases = (
            await session.scalars(
                select(Case)
                .where(Case.practice_id == args.practice_id)
                .order_by(Case.created_at.desc())
                .limit(args.limit)
            )
        ).all()
        if not cases:
            print(f"No cases for practice {args.practice_id}.")
        for case in cases:
            docs = (
                await session.scalars(select(Document).where(Document.case_id == case.id))
            ).all()
            has_extraction = await session.scalar(
                select(Extraction.id).where(Extraction.case_id == case.id).limit(1)
            )
            has_analysis = await session.scalar(
                select(Analysis.id).where(Analysis.case_id == case.id).limit(1)
            )
            # Deliberately NOT claim_number: it is an account identifier. The case
            # id prefix is an internal random UUID and identifies the row just as
            # well for debugging. payer_name is not a patient identifier, so it
            # stays — it is usually the field you are actually debugging.
            print(f"\ncase {str(case.id)[:8]} | status={case.status} " f"| payer={case.payer_name}")
            if case.error_message:
                print(f"   error: {case.error_message}")
            for doc in sorted(docs, key=lambda d: d.doc_type):
                print(f"   doc {doc.doc_type:9} ocr={doc.ocr_status}")
            print(
                f"   extraction={'yes' if has_extraction else 'no'} "
                f"analysis={'yes' if has_analysis else 'no'}"
            )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
