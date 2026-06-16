from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Practice, User


async def upsert_user_on_login(
    session: AsyncSession, *, cognito_sub: str, email: str
) -> User:
    """Find-or-create the user row for a successful login.

    Match order: by cognito_sub, then by email (links a pre-seeded row to its
    real sub on first login), else create. New users default to the first
    practice (single-practice MVP). Caller commits.
    """
    user = await session.scalar(select(User).where(User.cognito_sub == cognito_sub))

    if user is None:
        user = await session.scalar(select(User).where(User.email == email))
        if user is not None:
            user.cognito_sub = cognito_sub

    if user is None:
        practice = await session.scalar(
            select(Practice).order_by(Practice.created_at).limit(1)
        )
        if practice is None:
            practice = Practice(name="Default Practice")
            session.add(practice)
            await session.flush()
        user = User(
            practice_id=practice.id,
            email=email,
            cognito_sub=cognito_sub,
            role="doctor",
        )
        session.add(user)

    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user
