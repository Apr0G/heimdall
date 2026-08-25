from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

# The repo root holds the single source of truth for local secrets (.env.local),
# shared by frontend and backend. This file lives at backend/app/core/config.py,
# so the repo root is three directory levels up from here.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application settings, read from environment / repo-root .env.local.

    Every field defaults to a safe empty/placeholder value so the process can
    always boot (e.g. /healthz works without a database). Real values come from
    .env.local. Anything that actually needs a credential (DB, Bedrock, Cognito)
    validates its own presence at call time, not at import time.
    """

    model_config = SettingsConfigDict(
        # Real env vars win over the file; .env.local wins over .env.
        env_file=(_REPO_ROOT / ".env", _REPO_ROOT / ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # AWS
    aws_region: str = "us-east-1"
    s3_bucket_name: str = ""
    leads_topic_arn: str = ""  # SNS topic for "get started" lead notifications

    # Database
    database_url: str = ""
    # Path to the AWS RDS CA bundle to enable verify-full DB TLS (cert + hostname
    # verification). Empty = require TLS but skip verification (current default;
    # RDS is private + force_ssl, so traffic is still encrypted). Set to
    # /app/rds-ca.pem — which the image ships — once a deploy is verified to connect.
    db_ssl_ca_bundle: str = ""

    # Auth (Cognito)
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    cognito_region: str = "us-east-1"

    # Bedrock (inference profile id, e.g. us.anthropic.claude-sonnet-4-6)
    bedrock_model_id: str = ""

    # App
    # Two security controls key off this (cookie `secure`, docs gating), so a
    # typo must fail at boot instead of silently taking the development branch.
    app_env: Literal["development", "test", "production"] = "development"
    frontend_url: str = "http://localhost:3000"
    log_level: str = "INFO"
    # Number of trusted proxies in front of the app (the ECS Express ALB = 1). The
    # real client IP is read this many entries in from the right of X-Forwarded-For.
    # Bump only if another trusted hop (e.g. a CDN) is added ahead of the ALB.
    trusted_proxy_hops: int = 1

    # Rate limiting (tunable without redeploy). redis_url empty -> in-memory
    # storage (single-process dev/test only); set a redis:// URL in production.
    redis_url: str = ""
    # ElastiCache AUTH token, injected from Secrets Manager. Kept separate from
    # REDIS_URL so the credential never sits in the task definition's plaintext
    # environment; `redis_dsn` splices it in at connect time.
    redis_auth_token: str = ""
    # Transactional email the API sends itself (authenticator-recovery codes).
    # Provider-switched: "ses" (default; sender must be a verified SES identity,
    # ses.tf) or "smtp2go" (HTTPS API; sender domain verified in SMTP2GO via
    # CNAMEs — added while the SES account is stuck in the sandbox, which
    # refuses mail to unverified recipients). The pool's own invite/reset emails
    # are configured on the Cognito side, not here. These emails carry auth
    # codes to practice staff — NEVER PHI; that rule is what makes a non-BAA
    # provider acceptable for them.
    mail_provider: Literal["ses", "smtp2go"] = "ses"
    smtp2go_api_key: str = ""
    mail_from: str = "Heimdall <no-reply@heimdallclaims.com>"
    mail_reply_to: str = "info@heimdallclaims.com"
    # Authenticator-recovery email codes: lifetime and attempts before a new code
    # must be requested.
    mfa_recovery_code_ttl_seconds: int = 600
    mfa_recovery_max_attempts: int = 5

    rate_limit_general: str = "150/minute"  # authed general API, per user
    rate_limit_auth: str = "10/15minutes"  # login, per IP
    rate_limit_public: str = "15/minute"  # unauthenticated public endpoints, per IP
    rate_limit_ai: str = "15/minute;50/day"  # Bedrock/Textract endpoints, per user

    # Secret pepper for keyed hashes of identifiers (member_id_hash, corpus
    # claim_ref). A bare SHA-256 of a structured, payer-prefixed identifier is
    # exhaustible offline, so it is not a de-identification control under
    # §164.514 — and §164.514(c) additionally requires a re-identification code
    # NOT derived from information about the individual. Empty is allowed so the
    # process still boots; the hashing helpers fail loudly rather than silently
    # falling back to an unkeyed digest.
    phi_hash_pepper: str = ""

    # Hard ceiling on pages sent to pypdf/Textract. A highly compressed 25 MB PDF
    # can hold tens of thousands of pages; extract_text() over all of them pins a
    # threadpool worker with no timeout, and Textract bills per page.
    max_document_pages: int = 150

    # Server-side idle timeout. The 15-minute browser timer is a UX affordance, not
    # a control — a closed tab leaves the session valid for the token's full life.
    # 0 disables the server-side check.
    idle_timeout_minutes: int = 15

    def require_redis_in_production(self) -> None:
        """Raise if production has no Redis DSN. The rate limiters fall back to
        `memory://` when redis_dsn() is empty (see core/rate_limit.py) — which
        silently makes the fail-closed AI spend cap and the login brute-force
        throttle per-container counters that reset on every deploy. A dropped
        REDIS_URL must be a loud failure for the SERVING API, not a quiet
        downgrade.

        Called from the API app startup (main.py) — NOT a Settings validator,
        because the one-off admin tasks (alembic migrate, export-corpus,
        dispose, provision) also run with APP_ENV=production but legitimately
        have no Redis, and must not be blocked from booting."""
        if self.app_env == "production" and not self.redis_dsn():
            raise RuntimeError(
                "REDIS_URL (and REDIS_AUTH_TOKEN) must be set in production — the "
                "in-memory rate-limit fallback is single-process only and defeats "
                "the AI spend cap and login throttle."
            )

    def redis_dsn(self) -> str:
        """`redis_url` with the AUTH token spliced in, or "" when unset.

        The token arrives as its own secret rather than baked into the URL, so it
        stays out of the task definition's plaintext environment (and therefore out
        of `aws ecs describe-task-definition` output and anything that logs it).
        """
        if not self.redis_url or not self.redis_auth_token:
            return self.redis_url
        scheme, _, remainder = self.redis_url.partition("://")
        if not remainder or "@" in remainder:
            return self.redis_url  # already carries credentials; leave it alone
        return f"{scheme}://:{quote(self.redis_auth_token, safe='')}@{remainder}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
