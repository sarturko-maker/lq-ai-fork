"""InHouse AI backend API entrypoint.

This is the M1-Task-A1 scaffold: a minimal FastAPI service that returns 503 from
its health endpoints. Implementation lands in subsequent tasks per
docs/M1-IMPLEMENTATION-ORDER.md.
"""

from __future__ import annotations

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app import __version__

SERVICE_NAME = "inhouse-ai-api"

app = FastAPI(
    title="InHouse AI Backend API",
    version=__version__,
    description=(
        "Backend API for the InHouse AI platform. The full surface is specified "
        "in docs/api/backend-openapi.yaml. M1 implementation lands progressively "
        "per docs/M1-IMPLEMENTATION-ORDER.md; until then, all endpoints return 501 "
        "or 503 with a structured 'not implemented' body."
    ),
)


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness probe.

    Returns 503 until Task A4 (Backend minimal scaffold) wires up dependencies.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_implemented",
            "service": SERVICE_NAME,
            "version": __version__,
            "next_task": "A4 — Backend minimal scaffold",
        },
    )


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe (checks downstream dependencies).

    Returns 503 until Task A4 wires up Postgres / Redis / MinIO connections.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_implemented",
            "service": SERVICE_NAME,
            "version": __version__,
            "next_task": "A4 — Backend minimal scaffold (DB/Redis/MinIO connections)",
        },
    )
