"""The API-wide `default-src 'none'` CSP blanks the interactive docs (Swagger
UI / ReDoc load their own scripts), so outside production those three paths —
and only those, and only that header — are exempt (LOW-18). In production the
docs are not served at all and every path keeps the full header set."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

_CSP = "content-security-policy"
_DOCS = ("/docs", "/redoc", "/openapi.json")


def test_docs_paths_drop_only_the_csp_outside_production():
    client = TestClient(app)
    for path in _DOCS:
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert _CSP not in resp.headers, path
        # Every other header still applies to the docs pages.
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["cache-control"] == "no-store"


def test_api_paths_keep_the_csp():
    resp = TestClient(app).get("/healthz")
    assert resp.headers[_CSP] == "default-src 'none'; frame-ancestors 'none'"


def test_production_exempts_nothing(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    client = TestClient(app)
    for path in _DOCS:
        assert _CSP in client.get(path).headers, path
