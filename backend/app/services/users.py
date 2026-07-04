from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def link_user_on_login(session: AsyncSession, *, cognito_sub: str, email: str) -> User | None:
    """Link a pre-provisioned user row to its Cognito sub on first login.

    Match by cognito_sub, then by email (which links an admin-seeded row to its
    real sub on first login). Returns None if the user is not provisioned — we do
    NOT auto-create users, because dropping an unknown login into an existing
    practice would expose that practice's PHI. The caller rejects a None result.
    """
    user = await session.scalar(select(User).where(User.cognito_sub == cognito_sub))
    if user is None:
        user = await session.scalar(select(User).where(User.email == email))
        if user is not None:
            user.cognito_sub = cognito_sub

    if user is None:
        return None

    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user
