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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models import Practice, User
from app.services.cognito import admin_find_sub, admin_invite

ROLES = ("doctor", "office_manager", "admin")

# A users row whose Cognito identity was deleted mid-authenticator-reset and
# never re-created carries this prefix on cognito_sub; it is the ONE case where
# an invite may rebind an existing email to a new sub.
RESET_PENDING_PREFIX = "reset-pending:"


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
    practice_name = (practice_name or "").strip() or None
    full_name = (full_name or "").strip() or None
    if not email or "@" not in email:
        raise ProvisioningError("A valid email is required")
    if role not in ROLES:
        raise ProvisioningError(f"Role must be one of {', '.join(ROLES)}")
    if bool(practice_id) == bool(practice_name):
        raise ProvisioningError("Choose an existing practice or name a new one — not both")

    # Refuse BEFORE any Cognito side effect. Inviting first meant a request we
    # then refuse (email bound to a different identity) had already created an
    # orphan Cognito account and emailed a temporary password — side effects
    # that survive the DB rollback. So the identity comparison is done against
    # a read-only lookup; the invite call only happens once it is known to be
    # safe. A reset-pending row is the one case where a rebind is the point.
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None and not existing.cognito_sub.startswith(RESET_PENDING_PREFIX):
        current_sub = await run_in_threadpool(admin_find_sub, email)
        if current_sub != existing.cognito_sub:
            raise _rebind_refused()

    sub, created_cognito = await run_in_threadpool(admin_invite, email)

    if existing is not None:
        if existing.cognito_sub != sub:
            if not existing.cognito_sub.startswith(RESET_PENDING_PREFIX):
                # Identity replaced between the lookup and the invite — refuse
                # rather than rebind, same rule as above.
                raise _rebind_refused()
            existing.cognito_sub = sub  # recovery from an interrupted authenticator reset
        practice = await session.get(Practice, existing.practice_id)
        return InviteResult(existing, practice, False, False, created_cognito)

    if practice_id:
        practice = await session.get(Practice, practice_id)
        if practice is None:
            raise ProvisioningError("That practice doesn't exist")

    # A savepoint around everything this invite inserts: a concurrent invite
    # for the same email can land first, and the unique violation on
    # users.email would otherwise poison the whole transaction (an unhandled
    # 500, with a half-created practice in it). On conflict the savepoint is
    # rolled back and the row the other caller created becomes ours — the
    # same idempotent re-send outcome a sequential second invite gets.
    try:
        async with session.begin_nested():
            created_practice = False
            if not practice_id:
                practice = Practice(name=practice_name)
                session.add(practice)
                await session.flush()
                created_practice = True
            user = User(
                practice_id=practice.id,
                email=email,
                cognito_sub=sub,
                role=role,
                full_name=full_name,
            )
            session.add(user)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is None:
            raise
        if existing.cognito_sub != sub:
            raise _rebind_refused() from None
        practice = await session.get(Practice, existing.practice_id)
        return InviteResult(existing, practice, False, False, created_cognito)
    return InviteResult(user, practice, True, created_practice, created_cognito)


def _rebind_refused() -> ProvisioningError:
    return ProvisioningError(
        "This email is already bound to a different sign-in identity; refusing to rebind"
    )
