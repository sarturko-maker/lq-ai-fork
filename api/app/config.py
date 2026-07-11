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

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
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

    # ----- Embeddings (matter/agent retrieval — ADR-F049 Slice C1) -----
    # Two doors behind one configurable provider (app.knowledge.embedding_provider):
    # 'local' = in-process fastembed/ONNX ($0, no gateway, dev-friendly DEFAULT);
    # 'gateway' = the Inference Gateway's /v1/embeddings (single-egress option).
    # Both emit `embedding_dim`-length vectors that fit document_chunks.embedding_local.
    # (Unprefixed env names per the database_url / jwt_secret precedent.)
    embedding_provider: Literal["local", "gateway"] = Field(
        default="local",
        description=(
            "Matter-document embedding door: 'local' (in-process fastembed, default, "
            "$0) or 'gateway' (Inference Gateway /v1/embeddings)."
        ),
    )
    embedding_model: str = Field(
        default="BAAI/bge-base-en-v1.5",
        description="fastembed model id for the local (Door A) embedder. 768-dim, MIT.",
    )
    embedding_dim: int = Field(
        default=768,
        description=(
            "Embedding dimensionality. Must match document_chunks.embedding_local "
            "vector(N) (mig 0078) and, for the gateway door, the requested OpenAI "
            "`dimensions` reduction. Coupled to embedding_model."
        ),
    )
    embedding_cache_dir: str | None = Field(
        default=None,
        description=(
            "fastembed model cache dir for the local door. None = fastembed default "
            "(warmed into the image at build so first use does not download)."
        ),
    )

    # ----- Cross-encoder rerank (matter/agent retrieval — ADR-F049 Slice D) -----
    # A local fastembed TextCrossEncoder reorders the hybrid candidate set by scoring
    # (query, passage) pairs jointly (precision complement to the bi-encoder fusion).
    # Door A only today (no gateway /rerank endpoint); reuses fastembed (no new dep).
    # DEFAULT ON per the Track-B B3 gate (ADR-F015 finding, N=30): rerank lifts top-rank
    # (within-doc p@1 +15.5%, MAP +11%) and the at-scale cross-doc case (+20-36%) with
    # zero recall harm, ~1 GB memory peak in real runs. (The dev box can't batch-eval the
    # embedder + cross-encoder together, so hybrid+rerank-at-scale is a deferred finding;
    # the measured FTS+rerank arm is a conservative lower bound on the hybrid pool.)
    rerank_enabled: bool = Field(
        default=True,
        description=(
            "Enable cross-encoder rerank of matter document search results. Default ON "
            "per the Track-B B3 gate (ADR-F049 Slice D)."
        ),
    )
    rerank_model: str = Field(
        default="Xenova/ms-marco-MiniLM-L-6-v2",
        description=(
            "fastembed TextCrossEncoder model id for the local reranker. MS-MARCO "
            "MiniLM (~5 MB) by default; BAAI/bge-reranker-base is the quality alt."
        ),
    )
    rerank_cache_dir: str | None = Field(
        default=None,
        description=(
            "fastembed cache dir for the reranker model. None = fastembed default "
            "(warmed into the image at build via RERANK_CACHE_DIR so first use does "
            "not download)."
        ),
    )
    rerank_candidates: int = Field(
        default=30,
        description=(
            "How many hybrid candidates to fetch and rerank before truncating to the "
            "tool's top-k. Wider = more for the cross-encoder to reorder, more CPU."
        ),
    )

    # ----- Fan-out safety quota (strategy + safety — ADR-F049 Slice E) -----
    # A per-run CEILING on subagent (`task`) dispatches, enforced by a fork
    # middleware (app.agents.fan_out_middleware) over the deepagents builtin `task`
    # tool (which bypasses the guarded_dispatch chokepoint). This is a SAFETY brake
    # (the antidote to the ADR-F015 over-exploration), NOT a taste limit — the
    # retrieval-strategy doctrine teaches WHEN to fan out; this bounds the blast
    # radius if the model misjudges. Over the ceiling, the run is not killed: the
    # `task` call is denied with a model-visible refusal so the agent can adapt
    # (consolidate findings / read remaining documents directly). NOTE: this is the
    # step/breadth brake; the complementary per-run TOKEN budget (R4 realised) now
    # lives in `run_token_budget` / the runner loop (ADR-F051, below).
    fan_out_quota: int = Field(
        default=32,
        description=(
            "Maximum subagent (`task`) dispatches per run before fan-out is denied "
            "with a model-visible refusal. A configurable safety ceiling (ADR-F049 "
            "Slice E), not a taste limit. This is the BALANCED (default) tier of the "
            "budget profiles (ADR-F053); economy/generous scale it in app.agents.budget. "
            "<= 0 disables the brake."
        ),
    )

    # ----- Per-run token budget (R4 realised — ADR-F051) -----
    # The HARD cost stop the Slice-E estimate/quota deferred to: the runner sums each
    # model turn's usage_metadata.total_tokens (lead + subagents) and halts the run
    # (cap_exceeded, error=token_budget_exceeded) once the cumulative total crosses this
    # ceiling. This is the token brake the guarded-tool R4 slot always pointed at
    # (tool dispatches themselves stay free local reads — R4-at-the-tool is still a
    # no-op by design); the cost lives in the gateway model calls, so the brake lives in
    # the runner loop beside max_steps. The default is a CONSERVATIVE, uncalibrated
    # runaway backstop (~10x the 200k window) — generous enough not to clip a legitimate
    # multi-turn / bounded-fan-out run, low enough to bound a pathological loop; precise
    # calibration awaits per-run token telemetry (a deferred observability follow-up).
    # <= 0 disables the brake.
    run_token_budget: int = Field(
        default=8_000_000,
        description=(
            "Maximum cumulative model tokens (input+output, lead + subagents) per agent "
            "run before it is halted as cap_exceeded (ADR-F051). A conservative runaway "
            "backstop, not a tight cap. The BALANCED (default) tier of the budget "
            "profiles (ADR-F053); economy/generous scale it in app.agents.budget. "
            "<= 0 disables the brake."
        ),
    )

    # ----- Per-run step + wall-clock tiers (balanced default — ADR-F053) -----
    # The other two halves of the BALANCED budget envelope (with the token budget +
    # fan-out quota above). The economy/generous tiers scale these in
    # app.agents.budget; the per-run `budget_profile` (default balanced) selects the
    # tier. Both are env-tunable so an operator can shift the default tier without a
    # code change.
    run_max_steps: int = Field(
        default=400,
        ge=1,
        description=(
            "Default settled-step ceiling per agent run (balanced tier, ADR-F053). The "
            "request may override per-run via AgentRunCreate.max_steps (advanced)."
        ),
    )
    run_wall_clock_seconds: float = Field(
        default=3600.0,
        gt=0,
        description=(
            "Default in-run wall-clock timeout in seconds (balanced tier, ADR-F053). "
            "The arq job timeout (AGENT_RUN_JOB_TIMEOUT_SECONDS) MUST exceed the largest "
            "profile's wall clock so the runner's clean cap fires before arq hard-cancels."
        ),
    )

    # ----- Deployment default budget profile (SETUP-5a, ADR-F063) -----
    # The deployment-wide default budget_profile for new agent runs, applied
    # when the request omits one AND the run's practice area carries no
    # default_budget_profile. Resolution order (ADR-F063, at run create):
    # run-explicit > area default > this setting > balanced. Distinct from the
    # RUN_* balanced-tier knobs above, which shape what "balanced" MEANS —
    # this picks which TIER applies by default. Operator-owned env (F061).
    run_default_budget_profile: str | None = Field(
        default=None,
        description=(
            "Deployment default budget_profile (economy/balanced/generous) for new "
            "agent runs (ADR-F063). Unset ⇒ balanced. Overridden by an area's "
            "default_budget_profile and by an explicit per-run choice."
        ),
    )

    @field_validator("run_default_budget_profile", mode="before")
    @classmethod
    def _normalize_run_default_budget_profile(cls, value: object) -> object:
        """Normalize "" → None and reject unknown profiles at boot (fail loud).

        The prod compose forwards the knob as ``${RUN_DEFAULT_BUDGET_PROFILE:-}``,
        so an UNSET key reaches pydantic as EMPTY STRING, never None (the
        SETUP-3b `${VAR:-}` trap — same normalization as bootstrap.hosted's
        truthiness gate). Anything else outside the three profiles is a
        misconfiguration; refusing to boot beats silently running every run on
        an unintended tier.
        """
        if value is None or value == "":
            return None
        if value not in ("economy", "balanced", "generous"):
            raise ValueError(
                "RUN_DEFAULT_BUDGET_PROFILE must be one of: economy, balanced, generous "
                "(or unset for the balanced default)"
            )
        return value

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

    # M-Sec.1 — session timeouts per PRD §5.1. Both are configurable;
    # defaults match the PRD's stated floor (8h absolute, 30m idle).
    # The refresh handler enforces both; access tokens themselves use
    # ``jwt_access_token_ttl_seconds``. Setting either timeout shorter
    # than the access-token TTL effectively means "the access token
    # outlives the session" — operators tuning the absolute below
    # ``jwt_access_token_ttl_seconds`` should also shorten the access
    # token to match (or accept the implicit drift).
    session_absolute_timeout_seconds: int = Field(
        default=28800,  # 8h
        description=(
            "Absolute session timeout in seconds. Copied verbatim "
            "across refresh-token rotations; the refresh endpoint "
            "401s when exceeded. PRD §5.1 default: 8 hours."
        ),
    )
    session_idle_timeout_seconds: int = Field(
        default=1800,  # 30m
        description=(
            "Idle session timeout in seconds. Refreshing the access "
            "token resets the clock; the refresh endpoint 401s when "
            "exceeded. PRD §5.1 default: 30 minutes."
        ),
    )

    # ----- Autonomous (M4) -----
    # Global fallback cap on per-session cost for autonomous sessions
    # whose spawning trigger (watch or schedule) did not specify
    # ``max_cost_usd``. Mirrors the gateway.yaml default. R4 (the
    # economic brake) trips when projected cost would exceed this cap.
    autonomous_default_max_cost_usd: Decimal = Field(
        default=Decimal("5.00"),
        description=(
            "Global default per-session cost cap (USD) for autonomous sessions "
            "spawned by a watch or schedule that did not set max_cost_usd. "
            "Mirrors the gateway.yaml default. R4 (economic brake) trips when "
            "projected cost would exceed this cap."
        ),
        validation_alias=AliasChoices("LQ_AI_AUTONOMOUS_DEFAULT_MAX_COST_USD"),
    )

    # Default model the analysis node passes to the gateway when neither
    # the spawning trigger (watch/schedule ``params["model"]``) nor the
    # target skill/playbook pinned one. Mirrors the gateway.yaml deployment
    # default. Operators may override via the env var; the value must be a
    # model identifier the gateway recognises in its routing table.
    autonomous_default_model: str = Field(
        default="claude-opus-4-7",
        description=(
            "Fallback chat-completion model used by the autonomous "
            "analysis node when ``params['model']`` is not set on the "
            "session. Must be a model id the gateway can route."
        ),
        validation_alias=AliasChoices("LQ_AI_AUTONOMOUS_DEFAULT_MODEL"),
    )

    # M-Sec.1 — MFA-mandatory deployment flag per PRD §5.1. When True,
    # the backend treats any authenticated user without MFA enrolled
    # as not-fully-authenticated for normal endpoints — they can only
    # call the MFA enrollment flow (and a small whitelist of safe
    # endpoints like ``/users/me`` and ``/auth/logout``). Operators
    # handling client-confidential data are expected to enable this.
    mfa_mandatory: bool = Field(
        default=False,
        description=(
            "Require MFA enrollment for every user. When True, "
            "non-enrolled users are gated to the MFA-setup endpoints "
            "until they enroll."
        ),
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

    # ----- First-run operator (SETUP-3a, ADR-F061 D3) -----
    # The platform operator's in-app account. Unlike the admin (which always
    # bootstraps at a default email), the operator is minted ONLY when this is
    # set — no default, so a self-host deployment that has no separate operator
    # simply never gets one. Bootstrap is idempotent (skips if an operator
    # already exists) and mints role='operator', is_admin=true (so the operator
    # also passes org-admin surfaces), must_change_password=true. Operator
    # accounts are the ONLY holders of the gateway-proxy surfaces (aliases,
    # provider-keys, gateway config, tier-policy PATCH) and can never be minted
    # through the org-admin role endpoint (escalation guard, ADR-F061 D3).
    first_run_operator_email: str | None = Field(
        default=None,
        description=(
            "Email for the auto-created first-run operator (platform) account. "
            "Unset ⇒ no operator is bootstrapped. Ignored once an operator exists."
        ),
    )

    # ----- First-run branding seed (BRAND-1a, ADR-F068) -----
    # Optional white-label seed applied by ensure_first_run_branding: inserted
    # ONCE, only when the deployment_branding table is empty AND at least one
    # BRAND_* value is set — an admin's in-app edits always win afterwards.
    # Bare env names (no env_prefix), per the FIRST_RUN_ADMIN_EMAIL precedent.
    # The accents are validated at use (hex #RRGGBB); an invalid value is
    # warned about and skipped rather than crashing the boot (the lifespan's
    # degrade-not-crash posture).
    brand_product_name: str = Field(
        default="",
        description=(
            "Product name seeded into the branding singleton at first boot "
            "(max 80 chars, no control characters). Empty ⇒ default brand."
        ),
    )
    brand_accent_light: str | None = Field(
        default=None,
        description=(
            "Light-theme accent (#RRGGBB) seeded at first boot; fans out to the "
            "brandable token family server-side (ADR-F068). Unset ⇒ default blue."
        ),
    )
    brand_accent_dark: str | None = Field(
        default=None,
        description=(
            "Dark-theme accent (#RRGGBB) seeded at first boot; fans out to the "
            "brandable token family server-side (ADR-F068). Unset ⇒ default blue."
        ),
    )

    # ----- Public base URL for emailed links (SETUP-3a, ADR-F061 D6) -----
    # The browser-facing origin used to build invite / password-reset links
    # (e.g. https://acme.lq-ai.example.com). Distinct from collabora_wopi_host
    # (in-network) and from CORS origins. Unset ⇒ links fall back to path-only
    # strings and the invite-create response returns the accept URL so an admin
    # can hand it over out-of-band. (Bare env name per the database_url /
    # jwt_secret precedent — no env_prefix.)
    public_base_url: str | None = Field(
        default=None,
        description=(
            "Browser-facing base URL for emailed invite/reset links (e.g. "
            "https://tenant.example.com). Unset ⇒ path-only fallback links."
        ),
    )

    # ----- Lifecycle token TTLs (SETUP-3a, ADR-F061 D7) -----
    invite_token_ttl_seconds: int = Field(
        default=604800,  # 7 days
        gt=0,
        description="Invite-token TTL in seconds. Default: 7 days (ADR-F061 D7).",
    )
    password_reset_token_ttl_seconds: int = Field(
        default=3600,  # 1 hour
        gt=0,
        description="Password-reset-token TTL in seconds. Default: 1 hour (ADR-F061 D7).",
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

    # ----- In-app Word editor / Collabora over WOPI (ADR-F047, libreoffice-editor) -----
    # The absolute URL the Collabora container uses to reach this api as the
    # WOPI host (the WOPISrc callback origin). It must be the in-Compose-network
    # address, NOT the browser origin, and must be present in the collabora
    # service's `aliasgroup1` allow-list. Default matches Slice-1's
    # `aliasgroup1: http://api:8000`.
    collabora_wopi_host: str = Field(
        default="http://api:8000",
        description=(
            "Origin Collabora reaches the WOPI host (api) at; the WOPISrc callback "
            "base. In-network address, not the browser origin. Must match the "
            "collabora service aliasgroup1 allow-list."
        ),
    )
    # Editor-session (WOPI access) token TTL. Kept at 10h deliberately (SAAS-2,
    # ADR-F059 §6-item-4): shortening it was considered for internet exposure but
    # DECLINED because the web editor has no token-renewal path (the token is
    # form-POSTed into the Collabora iframe once per load — DocumentEditorPanel),
    # so a short TTL would silently 401 a long legal editing session mid-work
    # (saves fail, the 30-min WOPI lock lapses). The token's actual exposure is
    # closed instead by: the api access-log scrub (observability.py) + the Caddy
    # edge redaction, the Caddy edge-DENY of /api/v1/wopi/* (Collabora reaches
    # the WOPI host over the compose-internal api:8000, never the public edge),
    # and the browser-side form-POST (the token never enters a URL/history). A
    # configurable short TTL with client renewal is a follow-up (editor slice).
    # Surfaced to the client as `access_token_ttl` (epoch ms) at mint time.
    wopi_token_ttl_seconds: int = Field(
        default=36000,
        description="Editor-session (WOPI) token TTL in seconds. Default: 10 hours.",
    )
    # The browser origin Collabora may postMessage to (CheckFileInfo
    # PostMessageOrigin). Consumed by the Slice-4 reskin; harmless to advertise
    # now. Default matches the dev web origin.
    collabora_post_message_origin: str = Field(
        default="http://localhost:3000",
        description="Browser origin Collabora may postMessage to (CheckFileInfo PostMessageOrigin).",
    )

    # ----- GDPR Article 17 grace period (per Task D6 / PRD §5.3) -----
    # When a user calls /users/me/delete, deletion_scheduled_at is set to
    # now() + this many days. The hard-delete worker scans daily and only
    # touches users whose schedule has elapsed. 30 days is the GDPR-typical
    # default; operators with stricter retention policies may shorten it,
    # and tests use 0 to exercise the cascade path immediately.
    gdpr_grace_period_days: int = Field(
        default=30,
        ge=0,
        description=(
            "Days between a user's account-deletion request and hard "
            "deletion. 0 hard-deletes on the next worker tick; the GDPR-"
            "typical default is 30."
        ),
    )

    # ----- Agent-run durability (F1-S1, ADR-F009) -----
    # Liveness/sweep thresholds for deep-agent runs on the arq worker. The
    # runner heartbeats (throttled) from inside its stream loop and at the
    # guarded_tool_call chokepoint; the sweep settles stale runs as FAILED
    # (never re-enqueues). A false-orphan is fenced-safe but rude, so the
    # CLAIMED-run orphan threshold is sized at 8 missed beats.
    #
    # The claim grace bounds how long an UNCLAIMED 'running' run may sit before
    # the sweep settles it FAILED — a backstop for a worker that died between
    # enqueue and claim (the api already settles enqueue FAILURES at POST). It
    # also feeds the SSE stale-run threshold (api/agent_runs.py), so its value is
    # NOT isolated to the sweep.
    # KNOWN LIMITATION (CLEAN-2 / HS-4 follow-up): a claimed agent run can hold a
    # worker slot for up to AGENT_RUN_JOB_TIMEOUT_SECONDS (5520s), well above this
    # 1200s grace. On a single worker now bounded to
    # lq_ai_agent_worker_concurrency slots, a run queued behind a saturated worker
    # can exceed the grace and be falsely FAILED even though it was legitimately
    # waiting. The scaling answer is more worker REPLICAS (not a deeper
    # single-worker backlog); a real fix (distinguish "queued behind full slots"
    # from "lost enqueue", or track the job timeout, minding the SSE coupling) is
    # its own durability slice.
    agent_run_heartbeat_seconds: float = Field(
        default=15.0,
        gt=0,
        description="Min seconds between heartbeat writes from a live agent run.",
    )
    agent_run_orphan_after_seconds: float = Field(
        default=120.0,
        gt=0,
        description=(
            "A claimed 'running' run whose heartbeat is older than this is "
            "settled FAILED by the orphan sweep."
        ),
    )
    agent_run_claim_grace_seconds: float = Field(
        default=1200.0,
        gt=0,
        description=(
            "An unclaimed 'running' run older than this is settled FAILED "
            "by the orphan sweep (lost enqueue / worker died before claim / "
            "pre-F1-S1 legacy rows). Ideally exceeds the queue's worst-case "
            "pickup delay; note a claimed agent run can occupy a slot up to "
            "AGENT_RUN_JOB_TIMEOUT_SECONDS (5520s) — see the KNOWN LIMITATION "
            "above (CLEAN-2/HS-4). Also feeds the SSE stale-run threshold."
        ),
    )

    # Concurrency cap for the shared deep-agent / playbook / tabular / autonomous
    # arq worker (arq_setup.WorkerSettings). arq defaults to 10 concurrent jobs;
    # each agent run drives in-process retrieval (ONNX embedder + cross-encoder,
    # loaded once per process but spiking CPU/memory per concurrent embed) and can
    # fan out subagents, so 10 unbounded jobs can OOM a modestly-sized worker pod
    # (HS-4). Bound it — mirrors the ingest worker's lq_ai_ingest_worker_concurrency.
    # 4 is conservative for a few-GB pod; horizontal scale is by worker replicas,
    # each honouring this cap.
    lq_ai_agent_worker_concurrency: int = Field(
        default=4,
        gt=0,
        description=(
            "Max concurrent jobs for the deep-agent/playbook/tabular arq worker "
            "(arq_setup.WorkerSettings.max_jobs). Replaces arq's unbounded default "
            "of 10; each agent run loads in-process ONNX retrieval models. 4 is "
            "conservative — raise on larger worker pods."
        ),
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

    # Optional override for the community skills directory. When unset (the
    # default), the loader auto-discovers the community submodule at
    # ``<skills_dir>/community/skills/`` (i.e., ``skills/community/skills/``
    # relative to the repo root). Set this to a different path if you mount
    # the community corpus at a custom location. An empty string or a path
    # that does not exist disables community skill loading silently.
    community_skills_dir: str | None = Field(
        default=None,
        description=(
            "Override for the community skills directory. Defaults to "
            "`skills/community/skills/` relative to the repo root. "
            "Set to an empty string to disable community skill loading."
        ),
    )

    # ----- Profile manifests (ADR-F067 D4, B-7a) -----
    # Filesystem path the profile loader walks at API startup. Defaults to the
    # repo's `profiles/` directory (sibling to `skills/`); resolved against the
    # process working directory if relative — the API container's WORKDIR is
    # `/app`, so `../profiles` anchors at `/profiles` (the Dockerfile COPY target
    # and the dev bind mount). Fail-loud: a missing dir or a malformed manifest
    # aborts boot (see app/profiles/bootstrap.py). Tests point this at a fixture.
    profiles_dir: str = Field(
        default="../profiles",
        description=(
            "Filesystem directory the profile-manifest loader walks at startup. "
            "Default is the repo's `profiles/` folder."
        ),
    )

    # ----- M3-D1 slack-bridge integration -----
    # The slack-bridge runs the OAuth dance with Slack then POSTs the
    # resulting workspace record to
    # ``POST /api/v1/integrations/slack/workspaces``. Both secrets here
    # live on the api ONLY (NOT on the gateway): the gateway has no
    # role in the Slack OAuth surface, and keeping its secret surface
    # minimal is a load-bearing posture. Different from the gateway's
    # ``LQ_AI_GATEWAY_MASTER_KEY`` on purpose — Slack bot tokens enable
    # bot impersonation; provider keys enable inference routing.
    # Different blast radii → different keys.
    lq_ai_bridge_token: str = Field(
        default="",
        description=(
            "Shared bearer token the slack-bridge presents on POSTs to "
            "/api/v1/integrations/slack/workspaces. Constant-time matched."
        ),
    )
    lq_ai_bridge_master_key: str = Field(
        default="",
        description=(
            "urlsafe-base64 Fernet master key used to encrypt Slack bot "
            "tokens at rest (and any future bridge-issued secret)."
        ),
    )

    # ----- Operational -----
    log_level: LogLevel = Field(default="info", description="Log level for the api/ service.")
    lq_ai_dev_mode: bool = Field(
        default=False,
        description=(
            "When true, gates the non-dev boot secret assertion "
            "(assert_boot_secrets_configured) so the local harness runs on the "
            "shipped default JWT_SECRET. This is the ONLY behaviour it gates — "
            "do not hang unrelated relaxations on it without an ADR."
        ),
    )

    # ----- SMTP / email transport (M4-C1) -----
    # Optional best-effort email transport for autonomous notifications.
    # Email is enabled IFF ``smtp_host`` is set; with it unset the notify
    # handler's email step is a clean no-op (the durable in-app row is the
    # record regardless). No new dependency — the sender uses stdlib
    # ``smtplib`` run via ``asyncio.to_thread`` (CLAUDE.md SBOM posture).
    smtp_host: str | None = Field(
        default=None,
        description=(
            "SMTP server hostname for autonomous-notification email. "
            "Unset disables email transport (in-app notifications still work)."
        ),
    )
    smtp_port: int = Field(
        default=587,
        description="SMTP server port. Default 587 (STARTTLS submission).",
    )
    smtp_username: str | None = Field(
        default=None,
        description="SMTP auth username. Unset skips login (open relay / no auth).",
    )
    smtp_password: str | None = Field(
        default=None,
        description="SMTP auth password. Unset skips login.",
    )
    smtp_from: str | None = Field(
        default=None,
        description=(
            "From address for notification email. Falls back to ``smtp_username`` when unset."
        ),
    )
    smtp_use_tls: bool = Field(
        default=True,
        description="Issue STARTTLS after connecting. Default True.",
    )
    smtp_timeout: int = Field(
        default=10,
        description=(
            "Socket timeout (seconds) for the SMTP connection — applies to "
            "connect, STARTTLS, and send. Bounds the best-effort send so a "
            "hung/black-holing mail server can't tie up a worker thread."
        ),
    )

    # ----- CORS -----
    # Comma-separated list of origins allowed to call the api from the
    # browser. Production deployments typically front web + api at the
    # same origin via a reverse proxy and leave this UNSET (no CORS).
    # Local Compose dev needs http://localhost:3000 because web (:3000)
    # and api (:8000) live at different origins.
    lq_ai_cors_origins: str = Field(
        default="",
        description=(
            "Comma-separated allowed origins for CORS. Empty disables CORS. "
            "For local Compose dev set to http://localhost:3000."
        ),
    )

    # ----- Auth rate limiting (SAAS-2, ADR-F059 §6-item-1) -----
    # Per-IP + per-account fixed-window counters on the auth surface, enforced
    # on the EXISTING Redis client (no new dependency). Each bucket count is
    # env-tunable; the window is shared. Redis-unavailable => FAIL OPEN (a Redis
    # outage must never lock legitimate users out of authentication). The
    # defaults are "per minute" (window 60s).
    rate_limit_window_seconds: int = Field(
        default=60,
        description="Fixed-window length (seconds) for all auth rate-limit buckets.",
    )
    rate_limit_login_ip_per_window: int = Field(
        default=10,
        description="Max /auth/login attempts per window per source IP.",
    )
    rate_limit_login_account_per_window: int = Field(
        default=5,
        description="Max /auth/login attempts per window per submitted account (email).",
    )
    rate_limit_refresh_ip_per_window: int = Field(
        default=60,
        description="Max /auth/refresh attempts per window per source IP.",
    )
    rate_limit_mfa_verify_ip_per_window: int = Field(
        default=10,
        description="Max /auth/mfa/verify attempts per window per source IP (TOTP brute-force).",
    )
    rate_limit_mfa_verify_account_per_window: int = Field(
        default=5,
        description="Max /auth/mfa/verify attempts per window per account (from the mfa_token).",
    )
    rate_limit_change_password_account_per_window: int = Field(
        default=5,
        description="Max /auth/change-password attempts per window per authenticated account.",
    )
    rate_limit_mfa_manage_account_per_window: int = Field(
        default=10,
        description="Max /auth/mfa/{setup,enable,disable} attempts per window per account.",
    )
    rate_limit_bootstrap_status_ip_per_window: int = Field(
        default=30,
        description="Max /admin/bootstrap-status probes per window per source IP.",
    )
    # BRAND-1a (ADR-F068) — the unauthenticated branding surface (GET /branding
    # + GET /branding/logo share one per-IP bucket). Public-by-design data, but
    # unauth endpoints get a brake like bootstrap-status; the responses are
    # cacheable (max-age=300 / immutable) so a browser rarely re-hits.
    rate_limit_branding_ip_per_window: int = Field(
        default=30,
        description="Max /branding (+ /branding/logo) reads per window per source IP.",
    )
    # SETUP-3a (ADR-F061 D7) — unauthenticated lifecycle surfaces. The reset
    # request is doubly bucketed (per-IP AND per-submitted-email) so neither a
    # source-IP flood nor a single-victim spam gets through; both buckets are
    # incremented on every attempt whether or not the account exists (so the
    # 429 leaks no existence signal, matching the uniform 202). The redeem
    # bucket is shared by accept-invite + reset-confirm (per-IP only — the
    # token IS the identifier and must not be hashed into a key/log).
    rate_limit_password_reset_request_ip_per_window: int = Field(
        default=10,
        description="Max /auth/password-reset-request attempts per window per source IP.",
    )
    rate_limit_password_reset_request_email_per_window: int = Field(
        default=5,
        description="Max /auth/password-reset-request attempts per window per submitted email.",
    )
    rate_limit_token_redeem_ip_per_window: int = Field(
        default=10,
        description=(
            "Max /auth/accept-invite + /auth/password-reset redemptions per window "
            "per source IP (shared bucket)."
        ),
    )


# ADR-F059 — the intentionally-obvious dev default (see security/jwt.py); a
# non-dev process refuses to boot on it so a real deployment can never silently
# sign tokens with a public, well-known secret. Empty is included because an
# unset signing secret is equally catastrophic.
_INSECURE_JWT_SECRETS = frozenset({"dev-jwt-secret-change-me", ""})


def assert_boot_secrets_configured(settings: Settings) -> None:
    """Refuse to boot a non-dev process configured with an insecure JWT secret.

    Pure and unit-testable: raises :class:`RuntimeError` naming the offending
    setting (never echoing its value) when ``lq_ai_dev_mode`` is False and
    ``jwt_secret`` is the shipped default or empty. In dev mode
    (``LQ_AI_DEV_MODE=true``) the check is a no-op so the local harness runs on
    the obvious default. Called at the TOP of the api lifespan (:mod:`app.main`):
    unlike a missing runtime dependency — which the lifespan deliberately
    degrades on, not crashes — a misconfigured signing SECRET is fatal.
    """
    if settings.lq_ai_dev_mode:
        return
    if settings.jwt_secret in _INSECURE_JWT_SECRETS:
        raise RuntimeError(
            "JWT_SECRET is unset or still the shipped development default; set a "
            "strong JWT_SECRET (or LQ_AI_DEV_MODE=true for local development) "
            "before starting outside dev. Refusing to boot."
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance.

    Tests that need a different config call `get_settings.cache_clear()` after
    monkeypatching environment variables.
    """
    return Settings()
