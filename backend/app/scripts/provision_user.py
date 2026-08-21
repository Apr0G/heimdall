"""Provision a user from the command line: Cognito invite + `users` row, via the
same service the admin UI uses (app/services/provisioning.py). Cognito emails the
temporary password; it is never printed or logged.

Either attach to an existing practice (PROVISION_PRACTICE_ID) or create a new one
(PROVISION_PRACTICE_NAME) — exactly one. Re-running for an existing invitee
re-sends the invite with a fresh temporary password (they last 7 days).

Run as a one-off in-VPC ECS task (the DB is private) via the provision-user
workflow:
  PROVISION_EMAIL=dr@practice.com PROVISION_ROLE=doctor \\
    PROVISION_PRACTICE_ID=<uuid> [PROVISION_FULL_NAME="Dr. Jane Doe"] \\
    python -m app.scripts.provision_user
"""

import asyncio
import os
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.provisioning import ProvisioningError, invite_user


async def main() -> None:
    if not (settings.cognito_user_pool_id and settings.database_url):
        raise SystemExit("COGNITO_USER_POOL_ID and DATABASE_URL must be set")
    practice_id = os.environ.get("PROVISION_PRACTICE_ID") or None

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            try:
                result = await invite_user(
                    session,
                    email=os.environ.get("PROVISION_EMAIL", ""),
                    role=os.environ.get("PROVISION_ROLE", "doctor"),
                    full_name=os.environ.get("PROVISION_FULL_NAME") or None,
                    practice_id=uuid.UUID(practice_id) if practice_id else None,
                    practice_name=os.environ.get("PROVISION_PRACTICE_NAME") or None,
                )
            except (ProvisioningError, ValueError) as exc:
                raise SystemExit(str(exc)) from exc
            await session.commit()
    finally:
        await engine.dispose()

    print(
        "cognito: created user + sent invite"
        if result.created_cognito
        else "cognito: user existed; invite re-sent"
    )
    if result.created_practice:
        print(f"db: created practice id={result.practice.id}")
    print(
        f"db: {'created' if result.created_user else 'existing'} user id={result.user.id} "
        f"role={result.user.role} practice_id={result.practice.id}"
    )
    print("done — the user will receive an email with a temporary password (valid 7 days)")


if __name__ == "__main__":
    asyncio.run(main())
