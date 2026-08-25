"""The production-Redis guard lives on Settings but is CALLED from the API
startup (main.py), not as a validator — so one-off admin tasks (alembic migrate,
export, dispose, provision) that run APP_ENV=production without Redis still boot.
This pins both halves."""

import pytest

from app.core.config import Settings


def _settings(**over) -> Settings:
    base = dict(app_env="production", redis_url="", redis_auth_token="")
    base.update(over)
    return Settings(**base)


def test_production_without_redis_raises_when_checked():
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        _settings().require_redis_in_production()


def test_production_with_redis_is_ok():
    _settings(
        redis_url="rediss://cache:6379", redis_auth_token="tok"
    ).require_redis_in_production()  # no raise


def test_non_production_never_requires_redis():
    _settings(app_env="development").require_redis_in_production()  # no raise
    _settings(app_env="test").require_redis_in_production()  # no raise


def test_constructing_settings_without_redis_does_not_raise():
    # Critical: building Settings (as a migrate/export task does) must NOT fail —
    # only the explicit API-startup check does.
    _settings()  # no raise
