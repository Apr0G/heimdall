"""Real signature verification tests for `verify_access_token` (HIGH-08).

The only negative auth test used to send `Authorization: Bearer not-a-jwt`. That
string has no dots, so it died in `jwt.get_unverified_header` — before `_get_jwks`
and before `jwt.decode` were ever reached. Nothing in the repo touched
verification at all, which meant:

  * adding `"verify_signature": False` to the options dict at `core/auth.py` is a
    ONE-WORD edit that keeps every test green while granting a full session to any
    attacker-forged token;
  * deleting the `token_use != "access"` check turns an ID token into a session
    token, silently;
  * deleting the `client_id` check accepts tokens minted for a different app
    client.

These tests mint real RS256 tokens from a locally generated keypair and patch the
JWKS cache, so they need no network and no Cognito.
"""

import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwk as jose_jwk
from jose import jwt

import app.core.auth as auth_module
from app.core.config import settings

pytestmark = pytest.mark.asyncio

_CLIENT_ID = "test-client-id"


def _stringify(jwk_dict: dict, kid: str) -> dict:
    """python-jose emits some JWK members as bytes; normalise and tag the kid."""
    out = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in jwk_dict.items()}
    out["kid"] = kid
    return out


def _keypair() -> tuple[dict, dict]:
    """(private JWK, public JWK) sharing one kid. Generated locally — these tests
    never touch Cognito or the network."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    constructed = jose_jwk.construct(pem, algorithm="RS256")
    kid = str(uuid.uuid4())
    return (
        _stringify(constructed.to_dict(), kid),
        _stringify(constructed.public_key().to_dict(), kid),
    )


@pytest.fixture(scope="module")
def signing_key():
    return _keypair()


@pytest.fixture(scope="module")
def other_key():
    """A DIFFERENT keypair — an attacker's, reusing a legitimate `kid`."""
    return _keypair()


@pytest.fixture(autouse=True)
def _cognito_env(monkeypatch, signing_key):
    """Serve the public JWK from the module cache so no network call happens."""
    _, public_jwk = signing_key
    monkeypatch.setattr(auth_module, "_jwks_by_kid", {public_jwk["kid"]: public_jwk})
    monkeypatch.setattr(settings, "cognito_client_id", _CLIENT_ID)
    yield
    auth_module._jwks_by_kid = None


def _claims(**overrides) -> dict:
    now = int(time.time())
    base = {
        "sub": str(uuid.uuid4()),
        "iss": auth_module._ISSUER,
        "token_use": "access",
        "client_id": _CLIENT_ID,
        "iat": now,
        "exp": now + 3600,
    }
    base.update(overrides)
    return base


def _token(key: tuple[dict, dict], **overrides) -> str:
    private_jwk, public_jwk = key
    return jwt.encode(
        _claims(**overrides),
        private_jwk,
        algorithm="RS256",
        headers={"kid": public_jwk["kid"]},
    )


# --- the happy path ----------------------------------------------------------


async def test_valid_token_is_accepted(signing_key):
    claims = await auth_module.verify_access_token(_token(signing_key))
    assert claims["token_use"] == "access"
    assert claims["client_id"] == _CLIENT_ID


# --- the four checks that had no test at all ---------------------------------


async def test_token_signed_by_a_different_key_is_rejected(signing_key, other_key):
    """THE test. Forge a token, sign it with your own key, reuse the real `kid`.
    If `verify_signature` is ever disabled this is the assertion that fails."""
    _, real_public = signing_key
    attacker_private, _ = other_key
    forged = jwt.encode(
        _claims(),
        attacker_private,
        algorithm="RS256",
        headers={"kid": real_public["kid"]},
    )
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(forged)
    assert exc.value.status_code == 401


async def test_id_token_is_rejected(signing_key):
    """token_use='id' must not be usable as a session token."""
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(_token(signing_key, token_use="id"))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Wrong token type"


async def test_token_for_another_client_is_rejected(signing_key):
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(_token(signing_key, client_id="some-other-client"))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token not issued for this client"


async def test_expired_token_is_rejected(signing_key):
    now = int(time.time())
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(_token(signing_key, iat=now - 7200, exp=now - 3600))
    assert exc.value.status_code == 401


async def test_wrong_issuer_is_rejected(signing_key):
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(
            _token(signing_key, iss="https://cognito-idp.us-east-1.amazonaws.com/evil-pool")
        )
    assert exc.value.status_code == 401


async def test_none_algorithm_is_rejected(signing_key):
    """The classic JWT downgrade: an unsigned token claiming alg=none."""
    unsigned = jwt.encode(_claims(), key="", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(unsigned)
    assert exc.value.status_code == 401


async def test_hmac_signed_token_is_rejected(signing_key):
    """Algorithm confusion: sign with HS256 using the public key as the shared
    secret. `algorithms=["RS256"]` is what stops this."""
    _, public_jwk = signing_key
    confused = jwt.encode(
        _claims(),
        "shared-secret",
        algorithm="HS256",
        headers={"kid": public_jwk["kid"]},
    )
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(confused)
    assert exc.value.status_code == 401


async def test_unknown_kid_is_rejected(monkeypatch, signing_key):
    """An unknown kid triggers one JWKS refresh; if it still misses, 401."""
    private_jwk, _ = signing_key

    async def _no_refresh(force_refresh: bool = False) -> dict:
        return {}

    monkeypatch.setattr(auth_module, "_get_jwks", _no_refresh)
    token = jwt.encode(_claims(), private_jwk, algorithm="RS256", headers={"kid": "unknown-kid"})
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(token)
    assert exc.value.status_code == 401


async def test_malformed_token_is_rejected():
    """The pre-existing case — kept, but it is no longer the only one."""
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token("not-a-jwt")
    assert exc.value.status_code == 401


async def test_tampered_payload_is_rejected(signing_key):
    """Flip a claim in the payload without re-signing."""
    import base64
    import json

    token = _token(signing_key)
    header, payload, signature = token.split(".")
    decoded = json.loads(base64.urlsafe_b64decode(payload + "=="))
    decoded["sub"] = "attacker-controlled-sub"
    tampered_payload = base64.urlsafe_b64encode(json.dumps(decoded).encode()).rstrip(b"=").decode()
    with pytest.raises(HTTPException) as exc:
        await auth_module.verify_access_token(f"{header}.{tampered_payload}.{signature}")
    assert exc.value.status_code == 401
