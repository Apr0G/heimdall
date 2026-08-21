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
from app.models import DeactivationRequest, Practice, User
from app.schemas.admin import (
    AdminDeactivationRequestItem,
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
    await _deactivate(session, request, current_user, target)
    await session.commit()
    return _item(target, practice.name)


async def _deactivate(session: AsyncSession, request: Request, admin: User, target: User) -> None:
    """Cognito first (a failure changes nothing), then the app-side kill switch +
    session revocation + audit. Does NOT commit. Shared by the manual button and
    request approval; any open deactivation request is marked approved."""
    try:
        await run_in_threadpool(admin_set_enabled, target.email, False)
    except (InvalidCredentialsError, CognitoError) as exc:
        raise _COGNITO_DOWN from exc
    now = datetime.now(UTC)
    target.is_active = False
    target.deactivated_at = now
    target.sessions_revoked_at = now
    target.session_keep_jti = None
    pending = await session.scalar(
        select(DeactivationRequest).where(
            DeactivationRequest.user_id == target.id, DeactivationRequest.status == "pending"
        )
    )
    if pending is not None:
        pending.status = "approved"
        pending.resolved_by = admin.id
        pending.resolved_at = now
    await _audit(session, request, admin, "user_deactivated", target)


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


# --- Deactivation requests ----------------------------------------------------


def _request_item(req: DeactivationRequest, user: User, practice_name: str):
    return AdminDeactivationRequestItem(
        id=req.id,
        user=_item(user, practice_name),
        reason=req.reason,
        status=req.status,
        created_at=req.created_at,
    )


async def _get_request(session: AsyncSession, request_id: UUID):
    row = (
        await session.execute(
            select(DeactivationRequest, User, Practice.name)
            .join(User, User.id == DeactivationRequest.user_id)
            .join(Practice, Practice.id == User.practice_id)
            .where(DeactivationRequest.id == request_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if row[0].status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This request was already resolved."
        )
    return row


@router.get("/deactivation-requests", response_model=list[AdminDeactivationRequestItem])
async def list_deactivation_requests(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> list[AdminDeactivationRequestItem]:
    rows = (
        await session.execute(
            select(DeactivationRequest, User, Practice.name)
            .join(User, User.id == DeactivationRequest.user_id)
            .join(Practice, Practice.id == User.practice_id)
            .where(DeactivationRequest.status == "pending")
            .order_by(DeactivationRequest.created_at)
        )
    ).all()
    return [_request_item(r, u, name) for r, u, name in rows]


@router.post("/deactivation-requests/{request_id}/approve", response_model=AdminUserItem)
async def approve_deactivation(
    request_id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserItem:
    req, target, practice_name = await _get_request(session, request_id)
    if target.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You can't deactivate your own account."
        )
    await _deactivate(session, request, current_user, target)  # marks the request approved
    await session.commit()
    return _item(target, practice_name)


@router.post("/deactivation-requests/{request_id}/deny", response_model=AdminUserItem)
async def deny_deactivation(
    request_id: UUID,
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserItem:
    req, target, practice_name = await _get_request(session, request_id)
    req.status = "denied"
    req.resolved_by = current_user.id
    req.resolved_at = datetime.now(UTC)
    await _audit(session, request, current_user, "deactivation_request_denied", target)
    await session.commit()
    return _item(target, practice_name)
