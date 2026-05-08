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

    # ----- File upload limits (Task C4) -----
    # Per-request cap on uploaded-file size. Documented in `.env.example`
    # as ``LQ_AI_MAX_UPLOAD_SIZE_MB``. The handler streams the body and
    # raises 413 (PayloadTooLarge) the instant the running byte count
    # exceeds the limit; we never load the full body into memory just to
    # check the size. Operators raising this should ensure their reverse
    # proxy / ingress (nginx/Traefik) raises its own ``client_max_body_size``
    # in step.
    lq_ai_max_upload_size_mb: int = Field(
        default=100,
        description=(
            "Per-request cap on uploaded-file size in MB. M1 default: 100. "
            "Streamed enforcement; never loads the body into memory to "
            "measure. Operators raising this must also raise their "
            "ingress's body-size limit."
        ),
    )

    # ----- Document pipeline (Task C5) -----
    # Concurrency: how many ingest jobs the arq worker runs in parallel.
    # 2 is the conservative default for M1 — both Docling and PyMuPDF are
    # CPU-bound and we don't want to starve the host. Operators with
    # multi-core dedicated hosts should bump this.
    lq_ai_ingest_worker_concurrency: int = Field(
        default=2,
        description=(
            "Concurrency of the document-pipeline arq worker. Each job runs "
            "Docling + PyMuPDF (CPU-bound); 2 is conservative."
        ),
    )

    # Docling can take a while on multi-page PDFs (legal contracts run
    # 20-100 pages routinely). 5 minutes per file is a generous default;
    # operators with structurally larger documents should raise.
    lq_ai_docling_timeout_seconds: int = Field(
        default=300,
        description=(
            "Per-job timeout for the document pipeline (Docling + PyMuPDF + "
            "chunking + persistence). Default 300 seconds."
        ),
    )

    # When False, skip the Docling pass entirely and run PyMuPDF only.
    # Useful for environments where Docling can't be installed (e.g.
    # constrained Python builds or CI runners without HuggingFace
    # network access).
    lq_ai_docling_enabled: bool = Field(
        default=True,
        description=(
            "When True (default), run Docling for structured-content "
            "extraction. When False, skip Docling and use PyMuPDF only "
            "for offsets and content."
        ),
    )

    # Chunker target / overlap. The defaults are tuned for ~500-token
    # chunks at the typical English-prose char/token ratio.
    lq_ai_chunk_target_chars: int = Field(
        default=2_000,
        description=(
            "Target chunk size in characters. The chunker snaps the actual "
            "boundary to a sentence terminator within a 200-char lookback "
            "when possible."
        ),
    )
    lq_ai_chunk_overlap_chars: int = Field(
        default=200,
        description=(
            "Characters of overlap between consecutive chunks. Aids "
            "boundary-spanning citations during retrieval."
        ),
    )

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

    # ----- First-run admin (per Task B2) -----
    # Email used for the auto-created first-run admin. Operators can override
    # this via environment before the first `docker compose up` to control
    # which address the bootstrapped admin uses. The email is never changed
    # after first-run by the bootstrap (only by manual operator action).
    first_run_admin_email: str = Field(
        default="admin@lq.ai",
        description=(
            "Email for the auto-created first-run admin user. Set before "
            "first deployment; ignored on subsequent restarts."
        ),
    )

    # Minimum length for user-set passwords (the change-password endpoint
    # rejects shorter inputs). 12 is a reasonable floor for an admin tool;
    # individual operators may raise but should not lower it.
    password_min_length: int = Field(
        default=12,
        description="Minimum length for user-set passwords. Default: 12 characters.",
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

    # ----- Skill registry (per Task C1 / ADR 0004) -----
    # Filesystem path the skill loader walks at startup (and re-walks on
    # SIGHUP). Defaults to the repo's `skills/` directory; in tests and
    # operator-side overlays this is overridden to a fixture or merged
    # directory. Resolved against the process working directory if
    # relative — the API container's WORKDIR is `/app`, so a relative
    # default is anchored there.
    skills_dir: str = Field(
        default="../skills",
        description=(
            "Filesystem directory the skill loader walks at startup and "
            "on SIGHUP. Default is the repo's `skills/` folder."
        ),
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
