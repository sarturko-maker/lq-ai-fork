"""Application configuration via pydantic-settings.

All values are loaded from environment variables (or a `.env` file) and
validated by Pydantic. The variable names match the inventory in
`.env.example` so a deployment configured per the documented quickstart
flows directly into this object.

The settings object is cached via `lru_cache` so importing modules can
call `get_settings()` cheaply; tests that need a different configuration
clear the cache via `get_settings.cache_clear()` after monkeypatching env.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["debug", "info", "warning", "warn", "error", "critical"]


class Settings(BaseSettings):
    """Backend API configuration.

    Field grouping mirrors `.env.example`. Only fields the backend reads are
    declared here — provider keys and Mode-2 / Ollama variables are read by
    the gateway, not by `api/`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Postgres -----
    # SQLAlchemy async URL form, e.g. postgresql+asyncpg://user:pass@host:5432/db.
    # In Compose this is composed in docker-compose.yml; in local dev it is
    # typically taken straight from .env.
    database_url: str = Field(
        default="postgresql+asyncpg://lq_ai:lq_ai@localhost:5432/lq_ai",
        description="Async SQLAlchemy URL for Postgres.",
    )

    # ----- Redis -----
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL used for sessions, queues, and rate limits.",
    )

    # ----- MinIO / S3 -----
    s3_endpoint_url: str = Field(
        default="http://localhost:9000",
        description="S3-compatible endpoint URL (MinIO in Compose; S3 in prod).",
    )
    s3_access_key: str = Field(default="", description="S3 access key.")
    s3_secret_key: str = Field(default="", description="S3 secret key.")
    s3_bucket: str = Field(default="lq-ai-files", description="S3 bucket for uploaded files.")
    s3_region: str = Field(default="us-east-1", description="S3 region.")

    # ----- Inference Gateway -----
    lq_ai_gateway_url: str = Field(
        default="http://localhost:8001",
        description="Inference Gateway base URL.",
    )
    lq_ai_gateway_key: str = Field(
        default="",
        description="Shared secret for backend ↔ gateway. Required in prod.",
    )

    # ----- JWT (per ADR 0002 — backend owns auth) -----
    jwt_secret: str = Field(
        default="dev-jwt-secret-change-me",
        description="Signing secret for JWT access and refresh tokens.",
    )
    jwt_access_token_ttl_seconds: int = Field(
        default=900,
        description="Access-token TTL in seconds. Default: 15 minutes.",
    )
    jwt_refresh_token_ttl_seconds: int = Field(
        default=604800,
        description="Refresh-token TTL in seconds. Default: 7 days.",
    )

    # ----- Password hashing (per ADR 0002) -----
    # Default 12 rounds matches bcrypt's library default and the OWASP
    # password-storage recommendation. Operators may tune downward in CI
    # (where speed matters and threat-model is internal) or upward for
    # high-assurance deployments. The cost factor is per-hash; verifying
    # an existing hash respects whatever cost factor it was minted with.
    bcrypt_rounds: int = Field(
        default=12,
        description="Bcrypt cost factor for password hashing. Default 12.",
    )

    # ----- MFA challenge token (per ADR 0002 / PRD §5.1) -----
    # Issued by /auth/login when the user has mfa_enabled=true; redeemed
    # by /auth/mfa/verify (D5) within this window. Short-lived: 5 minutes
    # is enough for a user to fish their TOTP code out of an authenticator
    # app and submit it; longer windows widen the replay surface.
    mfa_token_ttl_seconds: int = Field(
        default=300,
        description="MFA challenge token TTL in seconds. Default: 5 minutes.",
    )

    # ----- Operational -----
    log_level: LogLevel = Field(default="info", description="Log level for the api/ service.")
    lq_ai_dev_mode: bool = Field(
        default=False,
        description="When true, relax some safety checks for local development.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance.

    Tests that need a different config call `get_settings.cache_clear()` after
    monkeypatching environment variables.
    """
    return Settings()
