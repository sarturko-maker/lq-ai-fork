"""LQ.AI Inference Gateway entrypoint.

A3 (this scaffold) loads ``gateway.yaml`` on startup and validates it via
Pydantic. If the config is missing or malformed the lifespan raises
:class:`~app.config_loader.ConfigLoadError` and the process exits non-zero —
the gateway is the security boundary, and silently coming up with an empty
config would mask operator misconfiguration.

Endpoint posture in A3:

* ``GET  /health``                — 200 (liveness; independent of config).
* ``GET  /ready``                 — 200 once config has loaded; 503 otherwise.
* ``POST /v1/chat/completions``   — 501 (B3 + B4 land real routing).
* ``POST /v1/embeddings``         — 501.
* ``GET  /v1/models``             — returns configured aliases.
* ``GET  /admin/v1/tier-config``  — returns loaded tier policy.
* Other ``/admin/v1/*`` endpoints — 501.

Configuration path resolution
-----------------------------

The lifespan reads the path from ``GATEWAY_CONFIG_PATH``. Defaults:

* If ``GATEWAY_CONFIG_PATH`` is set, use it (typical in containers; e.g.,
  ``/etc/gateway.yaml`` mounted from the operator's file).
* Otherwise fall back to ``./gateway.yaml`` relative to the process cwd
  (the repo-root file used during local ``uvicorn app.main:app`` runs).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app import __version__
from app.api import admin_router, inference_router
from app.config import GatewayConfig
from app.config_loader import ConfigLoadError, load_config

logger = logging.getLogger(__name__)

SERVICE_NAME = "lq-ai-gateway"

DEFAULT_CONFIG_PATH = Path("gateway.yaml")
"""Default path the gateway looks for its config when ``GATEWAY_CONFIG_PATH``
is unset. Resolved relative to the process cwd."""


def _resolve_config_path() -> Path:
    """Return the effective config path for this process."""

    override = os.environ.get("GATEWAY_CONFIG_PATH")
    if override:
        return Path(override)
    return DEFAULT_CONFIG_PATH


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load and validate ``gateway.yaml`` on startup.

    On success: stash the parsed :class:`GatewayConfig` on ``app.state.config``
    and serve. On failure: log and re-raise — uvicorn exits non-zero.
    """

    config_path = _resolve_config_path()
    logger.info("loading gateway config from %s", config_path)
    try:
        config = load_config(config_path)
    except ConfigLoadError:
        logger.exception("gateway config load failed; refusing to start")
        raise

    app.state.config = config
    logger.info(
        "gateway config loaded: %d providers, %d aliases",
        len(config.providers),
        len(config.model_aliases),
    )
    try:
        yield
    finally:
        # No teardown work in A3. Provider adapters (B3+) will close
        # httpx clients here.
        logger.info("gateway shutting down")


app = FastAPI(
    title="LQ.AI Inference Gateway",
    version=__version__,
    description=(
        "OpenAI-compatible inference gateway and security boundary for the "
        "LQ.AI platform. The gateway annotates every routed request with "
        "its derived Inference Tier (1-5) per PRD §3.13 / §1.5.2 and refuses "
        "requests below a declared minimum. M1 implementation lands progressively "
        "per docs/M1-IMPLEMENTATION-ORDER.md; A3 ships the scaffold (config "
        "loading + 501 stubs); B3/B4 land real routing."
    ),
    lifespan=lifespan,
)

app.include_router(inference_router)
app.include_router(admin_router)


def _config_loaded(app: FastAPI) -> GatewayConfig | None:
    """Return the loaded config if startup succeeded, else ``None``.

    During the small window before lifespan completes (or if startup raised),
    ``app.state.config`` is unset. ``/ready`` uses this to differentiate
    "loaded" from "not yet loaded".
    """

    return getattr(app.state, "config", None)


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness probe — returns 200 as soon as the process is serving requests.

    Per K8s liveness convention: this answers "is the process alive?" and is
    independent of whether the gateway config has loaded. Used by docker
    healthchecks and orchestration platforms.
    """

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "alive",
            "service": SERVICE_NAME,
            "version": __version__,
        },
    )


@app.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness probe — 200 once gateway config is loaded; 503 otherwise.

    Per K8s readiness convention: returns 503 until A3's config load
    completes. (If the config fails to load, the process exits — there is no
    "config failed but server still up" state in A3.)

    Reads config from ``request.app.state`` (not the module-level ``app``)
    so the endpoint is testable when mounted on a fresh ``FastAPI`` instance.

    Provider-reachability checks are layered on top of this in B3+; a future
    revision may downgrade to 503 if every configured provider is failing.
    """

    config = _config_loaded(request.app)
    if config is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "service": SERVICE_NAME,
                "version": __version__,
                "reason": "config_not_loaded",
            },
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ready",
            "service": SERVICE_NAME,
            "version": __version__,
            "providers": len(config.providers),
            "aliases": len(config.model_aliases),
        },
    )
