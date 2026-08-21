"""Admin user management — invite, re-send invite, deactivate, reactivate.

Same posture as the admin overview: `require_role("admin")` on every route, an
audit row per action, and a deliberate cross-practice read (the user list) that
exposes account metadata only — emails, roles, practice names — never case or
patient data. Cognito side effects run first, so a Cognito failure leaves the
database untouched.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.admin import require_admin
from app.core.net import client_ip
from app.db.session import get_db
from app.models import Practice, User
from app.schemas.admin import (
    AdminInviteRequest,
    AdminInviteResponse,
    AdminPracticeItem,
    AdminUserItem,
    AdminUsersResponse,
)
from app.services.audit import log_audit, safe_ip
from app.services.cognito import (
    CognitoError,
    InvalidCredentialsError,
    admin_invite,
    admin_set_enabled,
)
from app.services.provisioning import ProvisioningError, invite_user

router = APIRouter(prefix="/api/admin", tags=["admin"])

_COGNITO_DOWN = HTTPException(
    status_code=status.HTTP_502_BAD_GATEWAY, detail="Authentication service is unavailable"
)


def _item(user: User, practice_name: str) -> AdminUserItem:
    return AdminUserItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        practice_id=user.practice_id,
        practice_name=practice_name,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        invite_pending=user.last_login_at is None,
    )


async def _audit(session: AsyncSession, request: Request, admin: User, action: str, target: User):
    await log_audit(
        session,
        action=action,
        resource_type="user",
        resource_id=target.id,
        user_id=admin.id,
        practice_id=target.practice_id,
        ip=safe_ip(client_ip(request)),
        user_agent=request.headers.get("user-agent"),
        metadata={"email": target.email, "role": target.role},
    )


async def _get_target(session: AsyncSession, user_id: UUID) -> tuple[User, Practice]:
    row = (
        await session.execute(
            select(User, Practice)
            .join(Practice, Practice.id == User.practice_id)
            .where(User.id == user_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return row[0], row[1]


@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUsersResponse:
    rows = (
        await session.execute(
            select(User, Practice.name)
            .join(Practice, Practice.id == User.practice_id)
            .order_by(Practice.name, User.email)
        )
    ).all()
    practices = (await session.execute(select(Practice).order_by(Practice.name))).scalars().all()
    return AdminUsersResponse(
        users=[_item(u, name) for u, name in rows],
        practices=[AdminPracticeItem(id=p.id, name=p.name) for p in practices],
    )


@router.post("/users", response_model=AdminInviteResponse, status_code=status.HTTP_201_CREATED)
async def invite(
    body: AdminInviteRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminInviteResponse:
    """Create the Cognito account (Cognito emails the temporary password) and the
    users row. Re-inviting an existing, not-yet-signed-in user re-sends the email."""
    try:
        result = await invite_user(
            session,
            email=body.email,
            role=body.role,
            full_name=body.full_name,
            practice_id=body.practice_id,
            practice_name=body.practice_name,
        )
    except ProvisioningError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except InvalidCredentialsError:
        # Cognito refused RESEND: the person already set a real password.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user has already activated their account; they can use Forgot password.",
        ) from None
    except CognitoError as exc:
        raise _COGNITO_DOWN from exc
    await _audit(
        session,
        request,
        current_user,
        "user_invited" if result.created_user else "user_invite_resent",
        result.user,
    )
    await session.commit()
    return AdminInviteResponse(
        user=_item(result.user, result.practice.name),
        created_user=result.created_user,
        created_practice=result.created_practice,
        invite_resent=not result.created_cognito,
    )


@router.post("/users/{user_id}/resend-invite", response_model=AdminUserItem)
async def resend_invite(
    user_id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserItem:
    target, practice = await _get_target(session, user_id)
    if target.last_login_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user has already signed in; they can use Forgot password.",
        )
    try:
        await run_in_threadpool(admin_invite, target.email)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user has already activated their account; they can use Forgot password.",
        ) from None
    except CognitoError as exc:
        raise _COGNITO_DOWN from exc
    await _audit(session, request, current_user, "user_invite_resent", target)
    await session.commit()
    return _item(target, practice.name)


@router.post("/users/{user_id}/deactivate", response_model=AdminUserItem)
async def deactivate(
    user_id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserItem:
    """Kill switch: the app refuses the user's requests immediately (is_active is
    checked on every call), every open session is revoked, and Cognito is disabled
    so they can't sign in again until reactivated."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You can't deactivate your own account."
        )
    target, practice = await _get_target(session, user_id)
    try:
        await run_in_threadpool(admin_set_enabled, target.email, False)
    except (InvalidCredentialsError, CognitoError) as exc:
        raise _COGNITO_DOWN from exc
    now = datetime.now(UTC)
    target.is_active = False
    target.deactivated_at = now
    target.sessions_revoked_at = now
    target.session_keep_jti = None
    await _audit(session, request, current_user, "user_deactivated", target)
    await session.commit()
    return _item(target, practice.name)


@router.post("/users/{user_id}/reactivate", response_model=AdminUserItem)
async def reactivate(
    user_id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserItem:
    target, practice = await _get_target(session, user_id)
    try:
        await run_in_threadpool(admin_set_enabled, target.email, True)
    except (InvalidCredentialsError, CognitoError) as exc:
        raise _COGNITO_DOWN from exc
    target.is_active = True
    target.deactivated_at = None
    # sessions_revoked_at deliberately stays: old sessions remain dead; they sign in fresh.
    await _audit(session, request, current_user, "user_reactivated", target)
    await session.commit()
    return _item(target, practice.name)
