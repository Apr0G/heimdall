"""Seed a second tenant for isolation testing: a Practice + a User row linked to
an already-created Cognito account (pass its sub). Idempotent on the email.

Run as a one-off in-VPC ECS task (the DB is private):
  TENANT_PRACTICE_NAME="Practice B" TENANT_EMAIL="doctor-b@heimdall.test" \
    TENANT_COGNITO_SUB="<the cognito sub>" python -m app.scripts.seed_tenant
"""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models import Practice, User


async def main() -> None:
    name = os.environ.get("TENANT_PRACTICE_NAME")
    email = os.environ.get("TENANT_EMAIL")
    sub = os.environ.get("TENANT_COGNITO_SUB")
    if not (name and email and sub):
        raise SystemExit("Set TENANT_PRACTICE_NAME, TENANT_EMAIL, and TENANT_COGNITO_SUB")

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        if await session.scalar(select(User).where(User.email == email)) is not None:
            print(f"User {email} already exists; nothing to do.")
        else:
            practice = Practice(name=name)
            session.add(practice)
            await session.flush()
            session.add(User(practice_id=practice.id, email=email, cognito_sub=sub, role="doctor"))
            await session.commit()
            print(f"Seeded practice '{name}' + user {email}.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
