"""Seed the dev database with one practice and two test users.

Idempotent: re-running matches existing rows (practice by name, users by email)
and updates them instead of creating duplicates. Cognito subs are read from env
vars — set them after creating the users in Cognito; until then a clearly-fake
placeholder sub is stored and overwritten on the next run.

Synthetic data only. Run with the backend venv active, from the repo root:
    python scripts/seed_dev.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Make the backend `app` package importable regardless of the current directory.
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


from app.models import Practice, User  # noqa: E402

SEED_USERS = [
    {
        "email": os.getenv("SEED_USER1_EMAIL", "doctor@heimdall.test"),
        "cognito_sub": os.getenv("SEED_USER1_COGNITO_SUB", "seed-pending-doctor"),
        "full_name": os.getenv("SEED_USER1_NAME", "Test Doctor One"),
        "role": os.getenv("SEED_USER1_ROLE", "doctor"),
    },
    {
        "email": os.getenv("SEED_USER2_EMAIL", "manager@heimdall.test"),
        "cognito_sub": os.getenv("SEED_USER2_COGNITO_SUB", "seed-pending-manager"),
        "full_name": os.getenv("SEED_USER2_NAME", "Test Manager One"),
        "role": os.getenv("SEED_USER2_ROLE", "office_manager"),
    },
]


async def seed() -> None:
    _assert_local_database()
    practice_name = os.getenv("SEED_PRACTICE_NAME", "Test Family Practice")

    async with AsyncSessionLocal() as session:
        practice = (
            await session.execute(select(Practice).where(Practice.name == practice_name))
        ).scalar_one_or_none()
        if practice is None:
            practice = Practice(
                name=practice_name,
                npi=os.getenv("SEED_PRACTICE_NPI", "0000000000"),
                tax_id=os.getenv("SEED_PRACTICE_TAX_ID", "00-0000000"),
                address_line1="1 Test Way",
                city="Testville",
                state="NY",
                zip="00000",
            )
            session.add(practice)
            await session.flush()
            practice_action = "created"
        else:
            practice_action = "exists"

        user_actions: list[tuple[str, str]] = []
        for u in SEED_USERS:
            existing = (
                await session.execute(select(User).where(User.email == u["email"]))
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    User(
                        practice_id=practice.id,
                        email=u["email"],
                        cognito_sub=u["cognito_sub"],
                        full_name=u["full_name"],
                        role=u["role"],
                    )
                )
                user_actions.append((u["email"], "created"))
            elif existing.practice_id != practice.id:
                # Never move a user between practices or overwrite a real
                # Cognito identity from a seed script — that's a tenancy rebind.
                user_actions.append((u["email"], "skipped: belongs to another practice"))
            elif existing.cognito_sub.startswith("seed-pending"):
                if u["cognito_sub"].startswith("seed-pending"):
                    user_actions.append((u["email"], "exists (cognito_sub still pending)"))
                else:
                    # The env now names the real Cognito user: bind it, or login
                    # can never resolve this row (it matches on cognito_sub).
                    existing.cognito_sub = u["cognito_sub"]
                    user_actions.append((u["email"], "updated (cognito_sub set)"))
            else:
                user_actions.append((u["email"], "exists (real cognito_sub kept)"))

        await session.commit()
        practice_id = practice.id

    print(f"practice '{practice_name}': {practice_action} (id={practice_id})")
    for email, action in user_actions:
        print(f"user {email}: {action}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
