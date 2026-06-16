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
    kms_key_alias: str = "alias/heimdall"

    # Database
    database_url: str = ""

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
