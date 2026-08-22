from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.security_headers import BodySizeLimitMiddleware


async def _echo(request):
    body = await request.body()
    return PlainTextResponse(f"got {len(body)}")


def _client(max_bytes: int) -> TestClient:
    app = Starlette(routes=[Route("/echo", _echo, methods=["POST"])])
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=max_bytes)
    return TestClient(app)


def test_small_body_passes_and_is_intact():
    r = _client(1000).post("/echo", content=b"x" * 500)
    assert r.status_code == 200
    assert r.text == "got 500"  # body replayed intact to the app


def test_oversized_body_rejected_413():
    r = _client(1000).post("/echo", content=b"x" * 5000)
    assert r.status_code == 413


def test_empty_body_flows_through():
    r = _client(1000).post("/echo", content=b"")
    assert r.status_code == 200
    assert r.text == "got 0"


def test_oversize_rejection_carries_security_headers():
    # SecurityHeaders must wrap the body guard (LOW-07): a 413 is still a
    # response the browser caches and frames unless told otherwise.
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/leads",
        content=b"x" * (2 * 1024 * 1024),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert "no-store" in resp.headers.get("cache-control", "")
