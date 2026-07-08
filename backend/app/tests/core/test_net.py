from starlette.requests import Request

from app.core.net import client_ip
from app.core.rate_limit import rate_key


def _request(headers: dict | None = None, client=("10.0.0.9", 5555)) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": client})


def test_no_forwarded_header_uses_direct_peer():
    assert client_ip(_request()) == "10.0.0.9"


def test_forwarded_single_ip():
    assert client_ip(_request({"x-forwarded-for": "203.0.113.7"})) == "203.0.113.7"


def test_forwarded_takes_rightmost_not_spoofed_leftmost():
    # Client prepended a fake IP; the ALB appended the real one on the right.
    req = _request({"x-forwarded-for": "1.2.3.4, 203.0.113.7"})
    assert client_ip(req) == "203.0.113.7"


def test_forwarded_strips_whitespace():
    assert client_ip(_request({"x-forwarded-for": "  203.0.113.7  "})) == "203.0.113.7"


def test_rate_key_ip_uses_real_client_not_alb():
    # No bearer token -> IP keying. Two different real clients behind the SAME ALB
    # must land in different buckets (else one shared bucket = global lockout).
    a = rate_key(_request({"x-forwarded-for": "spoof, 203.0.113.7"}))
    b = rate_key(_request({"x-forwarded-for": "spoof, 203.0.113.8"}))
    assert a == "ip:203.0.113.7"
    assert b == "ip:203.0.113.8"
    assert a != b
