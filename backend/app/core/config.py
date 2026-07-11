from functools import lru_cache
from pathlib import Path

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
    app_env: str = "development"
    frontend_url: str = "http://localhost:3000"
    log_level: str = "INFO"
    # Number of trusted proxies in front of the app (the ECS Express ALB = 1). The
    # real client IP is read this many entries in from the right of X-Forwarded-For.
    # Bump only if another trusted hop (e.g. a CDN) is added ahead of the ALB.
    trusted_proxy_hops: int = 1

    # Rate limiting (tunable without redeploy). redis_url empty -> in-memory
    # storage (single-process dev/test only); set a redis:// URL in production.
    redis_url: str = ""
    rate_limit_general: str = "150/minute"  # authed general API, per user
    rate_limit_auth: str = "10/15minutes"  # login, per IP
    rate_limit_public: str = "15/minute"  # unauthenticated public endpoints, per IP
    rate_limit_ai: str = "15/minute;50/day"  # Bedrock/Textract endpoints, per user


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
