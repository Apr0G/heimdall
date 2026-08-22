"""Seed synthetic demo cases so the dashboard has data to show.

Creates cases spanning the deadline badge colors (red < 7d, yellow < 14d,
green otherwise), one resolved case with an outcome, and one submitted case left
unreported for 35 days (to exercise the Phase 11 outcome-reminder banner).
Idempotent by claim number. Synthetic data only. Run with the backend venv
active, from repo root:

    python scripts/seed_case.py
"""

import asyncio
import os
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal, engine  # noqa: E402

# --- local-database guard (audit 2026-08-21 LOW-16) ---------------------------
# Same refusal show_cases.py applies to its READ path; a WRITE path needs it
# more. RDS is private and these scripts aren't in the image, so this is
# belt-and-braces against a mis-pointed DATABASE_URL on a laptop that has a
# tunnel open.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres", ""}


def _assert_local_database() -> None:
    from urllib.parse import urlsplit

    from app.core.config import settings  # noqa: E402

    if os.environ.get("ALLOW_REMOTE_DB") == "1":
        print(
            "WARNING: ALLOW_REMOTE_DB=1 — writing to a non-local database.",
            file=sys.stderr,
        )
        return
    host = (urlsplit(settings.database_url).hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        raise SystemExit(
            f"Refusing to run: DATABASE_URL points at a non-local host ({host!r}). "
            "This script WRITES seed data. Set ALLOW_REMOTE_DB=1 only if you really mean it."
        )


from app.models import Analysis, Case, Extraction, Outcome, Practice, User  # noqa: E402

TODAY = date.today()

DEMO_CASES = [
    {
        "claim_number": "CLM-TEST-0001",
        "status": "ready",
        "patient_initials": "J.D.",
        "payer_name": "Aetna",
        "plan_type": "commercial",
        "date_of_service": TODAY - timedelta(days=40),
        "denial_date": TODAY - timedelta(days=2),
        "appeal_deadline": TODAY + timedelta(days=5),  # red (< 7 days)
        "billed_amount_cents": 60000,
        "denied_amount_cents": 45000,
        "carc_codes": ["CO-50"],
        "denial_category": "medical_necessity",
        "is_appealable": True,
        "probability_band": "moderate",
        "success_probability": "0.520",
        "outcome": None,
    },
    {
        "claim_number": "CLM-TEST-0002",
        "status": "processing",
        "patient_initials": "A.B.",
        "payer_name": "UnitedHealthcare",
        "plan_type": "commercial",
        "date_of_service": TODAY - timedelta(days=30),
        "denial_date": TODAY - timedelta(days=4),
        "appeal_deadline": TODAY + timedelta(days=10),  # yellow (< 14 days)
        "billed_amount_cents": 120000,
        "denied_amount_cents": 120000,
        "carc_codes": ["CO-197"],
        "denial_category": "prior_auth",
        "is_appealable": True,
        "probability_band": "high",
        "success_probability": "0.710",
        "outcome": None,
    },
    {
        "claim_number": "CLM-TEST-0003",
        "status": "resolved",
        "patient_initials": "M.K.",
        "payer_name": "Cigna",
        "plan_type": "medicare",
        "date_of_service": TODAY - timedelta(days=90),
        "denial_date": TODAY - timedelta(days=50),
        "appeal_deadline": TODAY + timedelta(days=45),  # green
        "billed_amount_cents": 80000,
        "denied_amount_cents": 80000,
        "carc_codes": ["CO-50"],
        "denial_category": "medical_necessity",
        "is_appealable": True,
        "probability_band": "high",
        "success_probability": "0.680",
        "outcome": {
            "action_taken": "appealed",
            "result": "overturned",
            "amount_recovered_cents": 80000,
            "source": "user_reported",
        },
    },
    {
        "claim_number": "CLM-TEST-0004",
        "status": "submitted",
        "patient_initials": "R.S.",
        "payer_name": "Humana",
        "plan_type": "commercial",
        "date_of_service": TODAY - timedelta(days=70),
        "denial_date": TODAY - timedelta(days=45),
        "appeal_deadline": TODAY + timedelta(days=15),  # green
        "submitted_at": datetime.now(UTC) - timedelta(days=35),  # overdue for outcome
        "billed_amount_cents": 95000,
        "denied_amount_cents": 95000,
        "carc_codes": ["CO-197"],
        "denial_category": "prior_auth",
        "is_appealable": True,
        "probability_band": "moderate",
        "success_probability": "0.580",
        "outcome": None,
    },
]


async def seed() -> None:
    _assert_local_database()
    async with AsyncSessionLocal() as session:
        # Explicit target only — "oldest practice" would be a real customer in
        # any shared database. SEED_PRACTICE_NAME matches seed_dev.py's default.
        practice_name = os.getenv("SEED_PRACTICE_NAME", "Test Family Practice")
        practice = await session.scalar(select(Practice).where(Practice.name == practice_name))
        user = (
            await session.scalar(
                select(User).where(User.practice_id == practice.id).order_by(User.created_at)
            )
            if practice is not None
            else None
        )
        if practice is None or user is None:
            print("No practice/user found — run scripts/seed_dev.py first.")
            return

        results: list[tuple[str, str]] = []
        for spec in DEMO_CASES:
            existing = await session.scalar(
                select(Case).where(
                    Case.practice_id == practice.id,
                    Case.claim_number == spec["claim_number"],
                )
            )
            if existing is not None:
                results.append((spec["claim_number"], "exists"))
                continue

            case = Case(
                practice_id=practice.id,
                created_by=user.id,
                status=spec["status"],
                payer_name=spec["payer_name"],
                plan_type=spec["plan_type"],
                claim_number=spec["claim_number"],
                patient_initials=spec["patient_initials"],
                date_of_service=spec["date_of_service"],
                denial_date=spec["denial_date"],
                appeal_deadline=spec["appeal_deadline"],
                billed_amount_cents=spec["billed_amount_cents"],
                denied_amount_cents=spec["denied_amount_cents"],
                submitted_at=spec.get("submitted_at"),
            )
            session.add(case)
            await session.flush()

            session.add(
                Extraction(
                    case_id=case.id,
                    payer_name=spec["payer_name"],
                    plan_type=spec["plan_type"],
                    claim_number=spec["claim_number"],
                    carc_codes=spec["carc_codes"],
                    billed_amount_cents=spec["billed_amount_cents"],
                    denied_amount_cents=spec["denied_amount_cents"],
                    confidence=Decimal("0.90"),
                )
            )
            session.add(
                Analysis(
                    case_id=case.id,
                    denial_category=spec["denial_category"],
                    is_appealable=spec["is_appealable"],
                    appealability_reason="Synthetic demo case.",
                    success_probability=Decimal(spec["success_probability"]),
                    probability_band=spec["probability_band"],
                    reasoning_text="AI-generated estimate (synthetic demo data).",
                    recommended_appeal_level="level_1_internal",
                )
            )
            if spec["outcome"] is not None:
                outcome = spec["outcome"]
                session.add(
                    Outcome(
                        case_id=case.id,
                        action_taken=outcome["action_taken"],
                        result=outcome["result"],
                        amount_recovered_cents=outcome["amount_recovered_cents"],
                        source=outcome["source"],
                        reported_by=user.id,
                        resolution_date=TODAY - timedelta(days=5),
                    )
                )
            results.append((spec["claim_number"], "created"))

        await session.commit()

    for claim_number, action in results:
        print(f"case {claim_number}: {action}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
