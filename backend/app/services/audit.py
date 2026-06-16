import ipaddress
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


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
