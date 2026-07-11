import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

logger = logging.getLogger(__name__)


async def link_user_on_login(session: AsyncSession, *, cognito_sub: str, email: str) -> User | None:
    """Resolve a provisioned user row from its Cognito sub on login.

    Matches strictly by cognito_sub. Returns None if the user is not provisioned —
    we do NOT auto-create users, because dropping an unknown login into an existing
    practice would expose that practice's PHI. The caller rejects a None result.

    We deliberately do NOT fall back to email-matching and rebind the sub:
    cognito_sub is set to its real value when the row is seeded, so a sub miss + an
    email hit means a *different* Cognito account is claiming that email, and
    silently moving the sub would hand one user another's PHI (account takeover).
    Such attempts are refused and logged for investigation.
    """
    user = await session.scalar(select(User).where(User.cognito_sub == cognito_sub))
    if user is None:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            logger.warning(
                "login sub mismatch: email bound to a different cognito_sub; refusing",
                extra={"context": {"user_id": str(existing.id)}},
            )
        return None

    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user
