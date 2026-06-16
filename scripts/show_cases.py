"""Print recent cases with their document/pipeline state.

A no-psql way to inspect what the pipeline produced while testing. Run with the
backend venv active, from the repo root:

    python scripts/show_cases.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import Analysis, Case, Document, Extraction  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as session:
        cases = (
            await session.scalars(
                select(Case).order_by(Case.created_at.desc()).limit(15)
            )
        ).all()
        if not cases:
            print("No cases yet.")
        for case in cases:
            docs = (
                await session.scalars(
                    select(Document).where(Document.case_id == case.id)
                )
            ).all()
            has_extraction = await session.scalar(
                select(Extraction.id).where(Extraction.case_id == case.id).limit(1)
            )
            has_analysis = await session.scalar(
                select(Analysis.id).where(Analysis.case_id == case.id).limit(1)
            )
            print(
                f"\ncase {str(case.id)[:8]} | status={case.status} "
                f"| claim={case.claim_number} | payer={case.payer_name}"
            )
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
