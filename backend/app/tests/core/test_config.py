"""The production startup guard lives on Settings but is CALLED from the API
startup (main.py), not as a validator — so one-off admin tasks (alembic migrate,
export, dispose, provision) that run APP_ENV=production without Redis still boot.
This pins both halves, and that every setting whose absence silently weakens a
control (not just Redis) is refused."""

import pytest

from app.core.config import Settings

_PRODUCTION = dict(
    app_env="production",
    redis_url="rediss://cache:6379",
    redis_auth_token="tok",
    bedrock_model_id="us.anthropic.claude-sonnet-4-6",
    phi_hash_pepper="test-only-pepper",
    db_ssl_ca_bundle="/app/rds-ca.pem",
)


def _settings(**over) -> Settings:
    base = dict(_PRODUCTION)
    base.update(over)
    return Settings(**base)


def test_fully_configured_production_is_ok():
    _settings().require_production_settings()  # no raise


@pytest.mark.parametrize(
    ("over", "message"),
    [
        (dict(redis_url="", redis_auth_token=""), "REDIS_URL"),
        (dict(bedrock_model_id=""), "BEDROCK_MODEL_ID"),
        # A bare model id is a single-region call, not the inference profile
        # the hard rule requires.
        (dict(bedrock_model_id="anthropic.claude-sonnet-4-6"), "BEDROCK_MODEL_ID"),
        (dict(phi_hash_pepper="   "), "PHI_HASH_PEPPER"),
        (dict(db_ssl_ca_bundle=""), "DB_SSL_CA_BUNDLE"),
    ],
    ids=["redis", "model-empty", "model-not-a-profile", "pepper", "ca-bundle"],
)
def test_production_missing_a_control_setting_raises_when_checked(over, message):
    with pytest.raises(RuntimeError, match=message):
        _settings(**over).require_production_settings()


def test_non_production_never_requires_any_of_them():
    empty = dict(
        redis_url="",
        redis_auth_token="",
        bedrock_model_id="",
        phi_hash_pepper="",
        db_ssl_ca_bundle="",
    )
    _settings(app_env="development", **empty).require_production_settings()  # no raise
    _settings(app_env="test", **empty).require_production_settings()  # no raise


def test_constructing_settings_without_them_does_not_raise():
    # Critical: building Settings (as a migrate/export task does) must NOT fail —
    # only the explicit API-startup check does.
    _settings(redis_url="", redis_auth_token="", phi_hash_pepper="", db_ssl_ca_bundle="")
