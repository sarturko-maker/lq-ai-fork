"""LQ.AI backend API entrypoint.

This is the M1-Task-A1 scaffold: a minimal FastAPI service that returns 503 from
its health endpoints. Implementation lands in subsequent tasks per
docs/M1-IMPLEMENTATION-ORDER.md.
"""

from __future__ import annotations

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app import __version__

SERVICE_NAME = "lq-ai-api"

app = FastAPI(
    title="LQ.AI Backend API",
    version=__version__,
    description=(
        "Backend API for the LQ.AI platform. The full surface is specified "
        "in docs/api/backend-openapi.yaml. M1 implementation lands progressively "
        "per docs/M1-IMPLEMENTATION-ORDER.md; until then, all endpoints return 501 "
        "or 503 with a structured 'not implemented' body."
    ),
)


@app.get("/health")
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


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe — returns 200 when the service can serve real traffic.

    Per K8s readiness convention: this answers "can I serve user requests?"
    Returns 503 with a structured "not ready" body until Task A4 (Backend
    minimal scaffold) wires up Postgres, Redis, and MinIO connections.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_ready",
            "service": SERVICE_NAME,
            "version": __version__,
            "reason": "scaffold_only",
            "next_task": "A4 — Backend minimal scaffold (DB/Redis/MinIO connections)",
        },
    )
