"""Provision a user: create (or re-invite) the Cognito account and upsert the app
`users` row in one step. Cognito generates the temporary password and emails the
invite itself — the password is never printed, logged, or returned here.

Either attach the user to an existing practice (PROVISION_PRACTICE_ID) or create a
new practice for them (PROVISION_PRACTICE_NAME) — exactly one of the two.

Idempotent on the email:
  * Cognito user already exists -> re-sends the invite (a fresh temporary password;
    this is also the fix for "my temporary password expired" — they last 7 days).
  * `users` row already exists  -> left untouched (role/practice are not rewritten).

Run as a one-off in-VPC ECS task (the DB is private) via the provision-user workflow:
  PROVISION_EMAIL=dr@practice.com PROVISION_ROLE=doctor \\
    PROVISION_PRACTICE_ID=<uuid> [PROVISION_FULL_NAME="Dr. Jane Doe"] \\
    python -m app.scripts.provision_user
"""

import asyncio
import os
import uuid

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Practice, User

ROLES = ("doctor", "office_manager", "admin")


def _cognito_invite(email: str) -> str:
    """Create the Cognito user with an emailed temporary password, or re-send the
    invite if they already exist. Returns the Cognito sub."""
    client = boto3.client("cognito-idp", region_name=settings.cognito_region)
    common = {
        "UserPoolId": settings.cognito_user_pool_id,
        "Username": email,
        "DesiredDeliveryMediums": ["EMAIL"],
    }
    try:
        resp = client.admin_create_user(
            **common,
            UserAttributes=[
                {"Name": "email", "Value": email},
                # Mark verified so Cognito will deliver to it and the user is never
                # asked to confirm an address an admin already vetted.
                {"Name": "email_verified", "Value": "true"},
            ],
        )
        print("cognito: created user + sent invite email")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "UsernameExistsException":
            raise
        # RESEND only works while the user is still FORCE_CHANGE_PASSWORD; a user
        # who already set a real password gets AdminSetUserPassword from an admin.
        resp = client.admin_create_user(**common, MessageAction="RESEND")
        print("cognito: user already existed; re-sent invite with a fresh temporary password")
    attrs = {a["Name"]: a["Value"] for a in resp["User"]["Attributes"]}
    return attrs["sub"]


async def _upsert_user(email: str, sub: str, role: str, full_name: str | None) -> None:
    practice_id = os.environ.get("PROVISION_PRACTICE_ID")
    practice_name = os.environ.get("PROVISION_PRACTICE_NAME")
    if bool(practice_id) == bool(practice_name):
        raise SystemExit("Set exactly one of PROVISION_PRACTICE_ID or PROVISION_PRACTICE_NAME")

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            existing = await session.scalar(select(User).where(User.email == email))
            if existing is not None:
                if existing.cognito_sub != sub:
                    # The same email is bound to a different Cognito identity — a
                    # silent rebind would hand one account another's PHI. Stop.
                    raise SystemExit(
                        "users row exists with a DIFFERENT cognito_sub; refusing to rebind"
                    )
                print(f"db: user row already exists (id={existing.id}); unchanged")
                return

            if practice_id:
                practice = await session.get(Practice, uuid.UUID(practice_id))
                if practice is None:
                    raise SystemExit("PROVISION_PRACTICE_ID does not match any practice")
            else:
                practice = Practice(name=practice_name)
                session.add(practice)
                await session.flush()
                print(f"db: created practice id={practice.id}")

            user = User(
                practice_id=practice.id,
                email=email,
                cognito_sub=sub,
                role=role,
                full_name=full_name,
            )
            session.add(user)
            await session.commit()
            print(f"db: created user id={user.id} role={role} practice_id={practice.id}")
    finally:
        await engine.dispose()


async def main() -> None:
    email = os.environ.get("PROVISION_EMAIL", "").strip().lower()
    role = os.environ.get("PROVISION_ROLE", "doctor")
    full_name = os.environ.get("PROVISION_FULL_NAME") or None
    if not email or "@" not in email:
        raise SystemExit("PROVISION_EMAIL is required")
    if role not in ROLES:
        raise SystemExit(f"PROVISION_ROLE must be one of {ROLES}")
    if not (settings.cognito_user_pool_id and settings.database_url):
        raise SystemExit("COGNITO_USER_POOL_ID and DATABASE_URL must be set")

    sub = _cognito_invite(email)
    await _upsert_user(email, sub, role, full_name)
    print("done — the user will receive an email with a temporary password (valid 7 days)")


if __name__ == "__main__":
    asyncio.run(main())
