"""Client-IP resolution behind the load balancer.

The app runs behind the ECS Express ALB, so ``request.client.host`` is always the
ALB's private IP — useless for rate limiting (one shared bucket for everyone) and
wrong for audit records. The real client IP comes from ``X-Forwarded-For``.

AWS ALB *appends* the connecting client's IP to X-Forwarded-For, so the trusted,
non-spoofable value is the **rightmost** entry. A client can prepend arbitrary
values (``X-Forwarded-For: 1.2.3.4``) but the ALB always adds the true peer to the
right of them, so we count ``trusted_proxy_hops`` entries in from the right (1 = the
ALB alone). Left-most parsing would be trivially spoofable — do not "fix" this to
take ``[0]``.
"""

from starlette.requests import Request

from app.core.config import settings


def client_ip(request: Request) -> str | None:
    """The real client IP, resolved from X-Forwarded-For behind the ALB.

    Falls back to the direct peer (``request.client.host``) when there is no
    forwarded header — i.e. local dev / direct connections.
    """
    hops = settings.trusted_proxy_hops
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and hops >= 1:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else None
