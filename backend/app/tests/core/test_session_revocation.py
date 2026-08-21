"""Boundary cases of the app-side session revocation check (core/auth.py)."""

from datetime import UTC, datetime

from app.core.auth import session_revoked

T = datetime(2026, 8, 21, 12, 0, 30, 500_000, tzinfo=UTC)  # revocation instant


def _claims(iat_dt: datetime, jti: str = "x") -> dict:
    return {"iat": int(iat_dt.timestamp()), "jti": jti}


def test_nothing_revoked():
    assert session_revoked(_claims(datetime(2020, 1, 1, tzinfo=UTC)), None, None) is False


def test_token_issued_well_before_revocation_is_refused():
    assert session_revoked(_claims(datetime(2026, 8, 21, 11, 0, tzinfo=UTC)), T, None) is True


def test_token_issued_after_revocation_is_fine():
    assert session_revoked(_claims(datetime(2026, 8, 21, 12, 0, 31, tzinfo=UTC)), T, None) is False


def test_same_second_as_revocation_survives():
    # iat has 1s resolution; a login in the same second must not be bounced.
    assert session_revoked(_claims(datetime(2026, 8, 21, 12, 0, 30, tzinfo=UTC)), T, None) is False


def test_kept_jti_survives_even_if_old():
    old = _claims(datetime(2026, 8, 21, 11, 0, tzinfo=UTC), jti="keep-me")
    assert session_revoked(old, T, "keep-me") is False
    assert session_revoked({**old, "jti": "other"}, T, "keep-me") is True


def test_missing_iat_fails_closed_once_revoked():
    assert session_revoked({"jti": "x"}, T, None) is True
    assert session_revoked({"jti": "x"}, None, None) is False
