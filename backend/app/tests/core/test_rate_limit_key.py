"""The limiter must key on the same token the authenticator reads.

Heimdall authenticates browsers with the `hd_session` httpOnly cookie; nothing in
the frontend ever sets an Authorization header. A limiter that only looked at the
header therefore fell through to per-IP keying for every real request, which broke
the AI spend cap (any IP rotation mints a fresh daily allowance) and multi-user
availability (one office NAT shares one bucket) at the same time.
"""

from jose import jwt
from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.auth import AUTH_COOKIE
from app.core.rate_limit import ip_key, rate_key

_SUB = "11111111-2222-3333-4444-555555555555"


def _token(sub: str = _SUB) -> str:
    """An unsigned-but-well-formed JWT. rate_key reads claims WITHOUT verifying,
    so no key material is needed here."""
    return jwt.encode({"sub": sub, "token_use": "access"}, "test-secret", algorithm="HS256")


def _request(*, cookie: str | None = None, header: str | None = None) -> Request:
    raw: list[tuple[bytes, bytes]] = [(b"host", b"api.heimdall.test")]
    if cookie:
        raw.append((b"cookie", f"{AUTH_COOKIE}={cookie}".encode()))
    if header:
        raw.append((b"authorization", header.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/cases",
            "headers": Headers(raw=raw).raw,
            "client": ("203.0.113.7", 1234),
            "query_string": b"",
        }
    )


def test_session_cookie_yields_a_per_user_key():
    assert rate_key(_request(cookie=_token())) == f"user:{_SUB}"


def test_bearer_header_still_yields_a_per_user_key():
    """API clients that do send a header keep working."""
    assert rate_key(_request(header=f"Bearer {_token()}")) == f"user:{_SUB}"


def test_cookie_takes_precedence_over_header():
    """Same precedence as core/auth.py:get_current_user — if the limiter and the
    authenticator disagree about which token is authoritative, the limiter is
    bucketing a different identity than the one being authorised."""
    other = "99999999-8888-7777-6666-555555555555"
    request = _request(cookie=_token(_SUB), header=f"Bearer {_token(other)}")
    assert rate_key(request) == f"user:{_SUB}"


def test_two_users_get_separate_buckets():
    a = rate_key(_request(cookie=_token("aaaaaaaa-0000-0000-0000-000000000000")))
    b = rate_key(_request(cookie=_token("bbbbbbbb-0000-0000-0000-000000000000")))
    assert a != b


def test_unauthenticated_falls_back_to_ip():
    request = _request()
    assert rate_key(request) == ip_key(request)
    assert rate_key(request).startswith("ip:")


def test_malformed_token_falls_back_to_ip():
    request = _request(cookie="not-a-jwt")
    assert rate_key(request).startswith("ip:")


def test_public_key_never_trusts_a_token():
    """ip_key is used by login/leads, where an unauthenticated caller could forge a
    `sub` to mint a fresh bucket per request and evade the limit entirely."""
    assert ip_key(_request(cookie=_token())).startswith("ip:")
