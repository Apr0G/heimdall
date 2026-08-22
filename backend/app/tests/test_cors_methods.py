"""The CORS method allowlist must cover every method a router registers — a
missing one makes the browser preflight fail, so the route can never be called
cross-origin from the frontend (MED-02: DELETE was missing)."""

from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.main import app


def _cors_allow_methods() -> set[str]:
    for m in app.user_middleware:
        if m.cls is CORSMiddleware:
            return set(m.kwargs["allow_methods"])
    raise AssertionError("CORSMiddleware not configured")


def test_every_registered_method_is_cors_allowed():
    registered = {
        method
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in route.methods
    }
    assert registered - {"HEAD"} <= _cors_allow_methods()


def test_preflight_for_delete_is_accepted():
    from fastapi.testclient import TestClient

    from app.core.config import settings

    client = TestClient(app)
    resp = client.options(
        "/api/auth/deactivation-request",
        headers={
            "Origin": settings.frontend_url,
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert resp.status_code == 200
    assert "DELETE" in resp.headers.get("access-control-allow-methods", "")
