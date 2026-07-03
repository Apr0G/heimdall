import ipaddress
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.models import AuditLog, User


async def log_audit(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    user_id: UUID | None = None,
    practice_id: UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one audit row. Does NOT commit — the caller owns the transaction.

    Never pass PHI in `metadata`: account emails and IDs are fine, patient data
    and document text are not.
    """
    session.add(
        AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            practice_id=practice_id,
            ip_address=ip,
            user_agent=user_agent,
            event_metadata=metadata,
        )
    )


def safe_ip(host: str | None) -> str | None:
    """Return host only if it is a valid IP (the audit column is INET)."""
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        return None


async def log_read(
    session: AsyncSession,
    request: Request,
    user: User,
    action: str,
    resource_type: str,
    resource_id: UUID,
) -> None:
    """Append a PHI-access (read/export) audit row and commit it. Metadata only —
    never document content. Satisfies HIPAA §164.312(b) audit controls for reads."""
    await log_audit(
        session,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user.id,
        practice_id=user.practice_id,
        ip=safe_ip(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
