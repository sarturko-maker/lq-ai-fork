"""LQ.AI backend API entrypoint.

Task A4 — Backend minimal scaffold. The full surface from
`docs/api/backend-openapi.yaml` is registered here so OpenAPI clients see
the contract; every endpoint except `/health` and `/ready` returns 501
with a structured "not implemented" body until its implementing task
(B1, C3, etc.) lands. See `app.api._stub.not_implemented`.

Lifespan:
- on startup: build the Postgres engine, Redis client, and gateway client
  lazily (their first call wires them up), and ensure the configured S3
  bucket exists so file uploads in C4 don't trip on missing-bucket.
- on shutdown: dispose / aclose all four.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.admin_bootstrap import (
    ensure_first_run_admin,
    ensure_first_run_branding,
    ensure_first_run_operator,
)
from app.agents.checkpointer import close_agent_checkpointer, init_agent_checkpointer
from app.agents.store import close_agent_store, init_agent_store
from app.agents.stream import RedisStreamBridge, RunStreamBroker
from app.api import api_router
from app.cache import check_redis, close_redis, get_redis
from app.clients.gateway import close_gateway_client, get_gateway_client
from app.config import assert_boot_secrets_configured, get_settings
from app.db.session import check_db, dispose_engine, get_session_factory
from app.errors import LQAIError
from app.security.rate_limit import RateLimiter, RedisRateLimitBackend
from app.skills import install_sighup_reload, install_skill_registry, resolve_skill_dirs
from app.storage import check_storage, ensure_bucket

SERVICE_NAME = "lq-ai-api"
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open process-global clients on startup; close them on shutdown.

    Bucket creation is best-effort: if storage is unavailable at startup
    the readiness probe will reflect that and operators can retry. We do
    not fail the process — the service should come up and report degraded
    so liveness probes still pass and operators can diagnose.
    """
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    log.info("Starting %s v%s", SERVICE_NAME, __version__)

    # ADR-F059 — a misconfigured signing SECRET is fatal (unlike a missing
    # runtime dependency, which the lifespan below deliberately degrades on):
    # refuse to boot a non-dev process on the shipped default JWT_SECRET.
    assert_boot_secrets_configured(settings)

    try:
        await ensure_bucket()
    except Exception as exc:
        # The bucket check must not crash the process — surface degradation
        # via /ready. The skills bootstrap below is the deliberate exception:
        # it raises on a missing/unreadable skills dir (uniform fail-fast
        # across api + worker, maintainer-ruled; see the bootstrap docstring).
        log.warning("ensure_bucket failed at startup: %s (continuing)", exc)

    # Skill registry (Task C1). The bootstrap is shared with the arq
    # worker's on_startup (app/skills/bootstrap.py) because the autonomous
    # executor resolves skill_refs via app.state in whichever process it
    # runs. The SIGHUP atomic-swap reload stays api-only policy, so it is
    # wired here on the returned holder, not inside the shared helper.
    skills_dir, effective_community_dir = resolve_skill_dirs(settings)
    skill_registry_holder = install_skill_registry(
        app, settings, resolved_dirs=(skills_dir, effective_community_dir)
    )
    install_sighup_reload(
        skill_registry_holder,
        skills_dir,
        community_skills_dir=effective_community_dir,
    )

    # First-run admin bootstrap (Task B2). If the DB is unreachable at
    # startup we log and continue — the readiness probe will reflect the
    # outage and the operator can recover, and the bootstrap will retry on
    # the next restart. We deliberately do NOT crash the process here.
    try:
        factory = get_session_factory()
        async with factory() as session:
            generated = await ensure_first_run_admin(session)
        if generated is not None:
            # The password is intentionally surfaced in the container log,
            # exactly once, on the actual creation event. Quickstart docs
            # tell operators to grep for the prefix below.
            log.warning(
                "First-run admin password (record it now and rotate on first login): %s",
                generated,
            )
    except Exception as exc:
        log.warning("first-run admin bootstrap failed: %s (continuing)", exc)

    # First-run operator bootstrap (SETUP-3a, ADR-F061). No-op unless
    # FIRST_RUN_OPERATOR_EMAIL is configured; same degrade-not-crash posture as
    # the admin bootstrap above.
    try:
        factory = get_session_factory()
        async with factory() as session:
            generated_op = await ensure_first_run_operator(session)
        if generated_op is not None:
            log.warning(
                "First-run operator password (record it now and rotate on first login): %s",
                generated_op,
            )
    except Exception as exc:
        log.warning("first-run operator bootstrap failed: %s (continuing)", exc)

    # First-run branding seed (BRAND-1a, ADR-F068). No-op unless a BRAND_*
    # setting is configured AND the branding table is still empty (admin edits
    # always win afterwards); same degrade-not-crash posture as above.
    try:
        factory = get_session_factory()
        async with factory() as session:
            seeded_branding = await ensure_first_run_branding(session)
        if seeded_branding:
            log.info("First-run branding: seeded from BRAND_* environment.")
    except Exception as exc:
        log.warning("first-run branding bootstrap failed: %s (continuing)", exc)

    # Durable agent state (F0-S5, ADR-F008). Init failure is degraded
    # service (no multi-turn persistence), never a crash — the function
    # logs and leaves the saver unset; see app/agents/checkpointer.py.
    await init_agent_checkpointer()

    # Native memory substrate (F2 N0, ADR-F049): the langgraph Store behind the
    # /memories CompositeBackend. Same degrade-not-crash posture as the
    # checkpointer — init failure leaves the store unset and the memory backend
    # falls back to the non-persistent default; see app/agents/store.py.
    await init_agent_store()

    # SSE v2 run-stream broker (F0-S7, ADR-F006): process-local pub/sub
    # between the runner and the stream endpoint. Composition root —
    # endpoints reach it through get_stream_broker (app/api/agent_runs).
    broker = RunStreamBroker()
    app.state.agent_stream_broker = broker

    # F025: cross-process stream bridge. Agent runs execute in the arq worker,
    # which publishes their live parts onto Redis pub/sub; this bridge relays
    # them into the process-local broker so the SSE endpoint serves them
    # unchanged. Constructed lazily-connecting (get_redis builds a client whose
    # TCP connect happens on first command) — if Redis is down the endpoint's
    # attach fails soft and the stream serves the DB-tail.
    app.state.agent_stream_bridge = RedisStreamBridge(get_redis(), broker)

    # ADR-F059 — auth-surface rate limiter on the shared redis client. Wired
    # once here (composition root); routes reach it via get_rate_limiter, which
    # reads app.state. A Redis fault fails OPEN inside the limiter (never 500s
    # an auth endpoint), so building it lazily-connecting is safe.
    app.state.rate_limiter = RateLimiter(RedisRateLimitBackend(get_redis()), settings)

    try:
        yield
    finally:
        log.info("Shutting down %s", SERVICE_NAME)
        # Close clients in reverse order of dependency. Failures here are
        # logged but never propagate — shutdown is best-effort.
        for closer_name, closer in (
            ("run-stream bridge", app.state.agent_stream_bridge.aclose),
            ("agent checkpointer", close_agent_checkpointer),
            ("agent memory store", close_agent_store),
            ("gateway client", close_gateway_client),
            ("redis", close_redis),
            ("db engine", dispose_engine),
        ):
            try:
                await closer()
            except Exception as exc:
                log.warning("Error closing %s: %s", closer_name, exc)


app = FastAPI(
    title="LQ.AI Backend API",
    version=__version__,
    description=(
        "Backend API for the LQ.AI platform. The full surface is specified "
        "in docs/api/backend-openapi.yaml. M1 implementation lands progressively "
        "per docs/M1-IMPLEMENTATION-ORDER.md; until then, all endpoints under "
        "/api/v1 return 501 with a structured 'not implemented' body that names "
        "the implementing task."
    ),
    lifespan=lifespan,
)

# CORS — configurable allowed origins for cross-origin browser clients.
# Production deployments typically front web + api at the same origin via
# a reverse proxy and leave LQ_AI_CORS_ORIGINS unset (no CORS needed).
# Local Compose dev needs CORS because web (:3000) and api (:8000) live
# at different origins; the operator's .env sets the value.
_settings = get_settings()
_cors_origins = [o.strip() for o in (_settings.lq_ai_cors_origins or "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        # Date: the agents UI derives "server now" from it so staleness
        # cutoffs survive client clock skew (F0-S7; same-origin deploys
        # never needed the exposure).
        expose_headers=["X-LQ-AI-Routed-Inference-Tier", "X-LQ-AI-Routed-Provider", "Date"],
        max_age=600,
    )

app.include_router(api_router)

# M-Obs.1 — Prometheus /metrics + OpenTelemetry (PRD §5.4). OTel is
# off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (PRD §5.7 "no telemetry
# by default"). Wired AFTER the router is included so the FastAPI
# auto-instrumentor walks the full route tree.
from app.observability import install_observability  # noqa: E402

install_observability(app, service_name=SERVICE_NAME, service_version=__version__)


@app.exception_handler(LQAIError)
async def _lqai_error_handler(_request: Request, exc: LQAIError) -> JSONResponse:
    """Translate :class:`LQAIError` to the canonical structured error body.

    Renders ``{"detail": {"code": ..., "message": ..., "details": ...}}``
    with the exception's effective HTTP status. Documented in
    ``docs/api/backend-openapi.yaml`` as the ``Error`` schema and in
    :doc:`docs/adr/0003-error-handling.md`.

    The handler does not log here; subclasses or call sites that need
    operator-visible logging do so before raising. This keeps the
    handler a pure shape translator.
    """
    return JSONResponse(
        status_code=exc.effective_http_status,
        content=exc.to_envelope(),
    )


@app.get("/health", tags=["meta"])
async def health() -> JSONResponse:
    """Liveness probe — returns 200 as soon as the process is serving requests.

    Per K8s liveness convention: this answers "is the process alive?" and is
    independent of whether downstream dependencies are reachable. Used by
    docker-compose healthchecks and orchestration platforms.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "alive",
            "service": SERVICE_NAME,
            "version": __version__,
        },
    )


async def _check_gateway() -> bool:
    return await get_gateway_client().health_check()


@app.get("/ready", tags=["meta"])
async def ready() -> JSONResponse:
    """Readiness probe — returns 200 when DB + Redis + MinIO + gateway are reachable.

    Per K8s readiness convention: this answers "can I serve user requests?"
    Returns 200 with per-dependency `ok: true` when everything is up.
    Returns 503 with per-dependency status (and `ok: false` for failed
    deps) when any dependency is unreachable. Liveness (`/health`) stays
    200 in either case so orchestrators don't kill the pod for a transient
    dependency outage.
    """
    db_ok, redis_ok, storage_ok, gateway_ok = await asyncio.gather(
        check_db(),
        check_redis(),
        check_storage(),
        _check_gateway(),
        return_exceptions=False,
    )
    deps: dict[str, dict[str, bool]] = {
        "database": {"ok": db_ok},
        "redis": {"ok": redis_ok},
        "storage": {"ok": storage_ok},
        "gateway": {"ok": gateway_ok},
    }
    all_ok = all(d["ok"] for d in deps.values())
    failed = [name for name, d in deps.items() if not d["ok"]]
    body: dict[str, object] = {
        "status": "ready" if all_ok else "not_ready",
        "service": SERVICE_NAME,
        "version": __version__,
        "dependencies": deps,
    }
    if not all_ok:
        body["failed"] = failed

    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body,
    )
