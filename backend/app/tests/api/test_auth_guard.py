from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_missing_bearer_returns_401_not_403():
    # A missing Authorization header must be 401 (+ WWW-Authenticate) so the
    # frontend routes it to the sign-in flow — not HTTPBearer's default 403.
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_malformed_bearer_returns_401():
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
