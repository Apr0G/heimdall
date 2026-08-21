"""Inviting users: the Cognito account + the `users` row, as one operation.

Shared by the admin API and the provision_user script so the rules live once:
Cognito emails the temporary password (never surfaced here); a user is attached
to an existing practice OR a new practice is created for them; an email already
bound to a DIFFERENT Cognito identity is refused rather than rebound, because a
silent rebind would hand one person another's PHI.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models import Practice, User
from app.services.cognito import admin_invite

ROLES = ("doctor", "office_manager", "admin")


class ProvisioningError(Exception):
    """A caller mistake (bad practice, conflicting email) — safe to show to an admin."""


@dataclass
class InviteResult:
    user: User
    practice: Practice
    created_user: bool  # False = users row already existed (invite re-sent only)
    created_practice: bool
    created_cognito: bool  # False = Cognito user existed; invite was re-sent


async def invite_user(
    session: AsyncSession,
    *,
    email: str,
    role: str,
    full_name: str | None,
    practice_id: uuid.UUID | None,
    practice_name: str | None,
) -> InviteResult:
    """Idempotent on the email. Does NOT commit — the caller owns the transaction
    (so it can add its audit row to the same one)."""
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ProvisioningError("A valid email is required")
    if role not in ROLES:
        raise ProvisioningError(f"Role must be one of {', '.join(ROLES)}")
    if bool(practice_id) == bool(practice_name):
        raise ProvisioningError("Choose an existing practice or name a new one — not both")

    # Cognito first: if this fails nothing has been written.
    sub, created_cognito = await run_in_threadpool(admin_invite, email)

    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        if existing.cognito_sub != sub:
            raise ProvisioningError(
                "This email is already bound to a different sign-in identity; refusing to rebind"
            )
        practice = await session.get(Practice, existing.practice_id)
        return InviteResult(existing, practice, False, False, created_cognito)

    created_practice = False
    if practice_id:
        practice = await session.get(Practice, practice_id)
        if practice is None:
            raise ProvisioningError("That practice doesn't exist")
    else:
        practice = Practice(name=practice_name.strip())
        session.add(practice)
        await session.flush()
        created_practice = True

    user = User(
        practice_id=practice.id,
        email=email,
        cognito_sub=sub,
        role=role,
        full_name=(full_name or "").strip() or None,
    )
    session.add(user)
    await session.flush()
    return InviteResult(user, practice, True, created_practice, created_cognito)
