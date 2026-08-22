"""Suite-wide settings isolation.

`core/config.py` loads the repo-root dotenv files, so a developer tuning
TRUSTED_PROXY_HOPS, RATE_LIMIT_*, IDLE_TIMEOUT_MINUTES or REDIS_URL locally
would otherwise see failures that look like code regressions (LOW-19). Pin the
values the tests assume, and keep the login-throttle store in-memory so the
suite never writes to a shared Redis (LOW-20).
"""

import pytest
from limits import parse
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter

from app.core import rate_limit
from app.core.config import settings


@pytest.fixture(scope="session", autouse=True)
def _pinned_settings():
    pinned = {
        "app_env": "test",
        "trusted_proxy_hops": 1,
        "rate_limit_general": "150/minute",
        "rate_limit_auth": "10/15minutes",
        "rate_limit_public": "15/minute",
        "rate_limit_ai": "15/minute;50/day",
        "idle_timeout_minutes": 15,
        "redis_url": "",
        "redis_auth_token": "",
    }
    previous = {k: getattr(settings, k) for k in pinned}
    for k, v in pinned.items():
        object.__setattr__(settings, k, v)
    # Fresh in-process login-throttle store for the whole suite.
    rate_limit._login_storage = storage_from_string("memory://")
    rate_limit._login_strategy = MovingWindowRateLimiter(rate_limit._login_storage)
    rate_limit._login_limit = parse(settings.rate_limit_auth)
    yield
    for k, v in previous.items():
        object.__setattr__(settings, k, v)
