from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import get_current_user, verify_access_token
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, UserOut
from app.services.audit import log_audit, safe_ip
from app.services.cognito import CognitoError, InvalidCredentialsError, initiate_auth
from app.services.users import link_user_on_login

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.rate_limit_auth)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    ip = safe_ip(request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")

    try:
        auth = await run_in_threadpool(initiate_auth, body.email, body.password)
    except InvalidCredentialsError:
        await log_audit(
            session,
            action="login_failure",
            ip=ip,
            user_agent=user_agent,
            metadata={"email": body.email},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from None
    except CognitoError as exc:
        await log_audit(
            session,
            action="login_error",
            ip=ip,
            user_agent=user_agent,
            metadata={"email": body.email},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service is unavailable",
        ) from exc

    # Trust-but-verify: confirm the access token validates, and use its sub.
    claims = await verify_access_token(auth["AccessToken"])
    user = await link_user_on_login(session, cognito_sub=claims["sub"], email=body.email)
    if user is None:
        # Valid Cognito credentials but no provisioned app account — deny, never
        # auto-create (that would drop the login into an existing practice).
        await log_audit(
            session,
            action="login_denied",
            ip=ip,
            user_agent=user_agent,
            metadata={"email": body.email},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not provisioned. Contact your administrator.",
        )
    await log_audit(
        session,
        action="login_success",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        practice_id=user.practice_id,
        ip=ip,
        user_agent=user_agent,
        metadata={"email": body.email},
    )
    await session.commit()

    return LoginResponse(
        access_token=auth["AccessToken"],
        id_token=auth["IdToken"],
        refresh_token=auth["RefreshToken"],
        token_type=auth.get("TokenType", "Bearer"),
        expires_in=auth.get("ExpiresIn", 3600),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
