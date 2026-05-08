"""LQ.AI Inference Gateway entrypoint.

This is the M1-Task-A1 scaffold: a minimal FastAPI service that returns 503 from
its health endpoints and 501 from inference endpoints. Implementation lands in
Tasks A3, B3, B4 per docs/M1-IMPLEMENTATION-ORDER.md.
"""

from __future__ import annotations

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app import __version__

SERVICE_NAME = "lq-ai-gateway"

app = FastAPI(
    title="LQ.AI Inference Gateway",
    version=__version__,
    description=(
        "OpenAI-compatible inference gateway and security boundary for the "
        "LQ.AI platform. The gateway annotates every routed request with "
        "its derived Inference Tier (1-5) per PRD §3.13 / §1.5.2 and refuses "
        "requests below a declared minimum. M1 implementation lands progressively "
        "per docs/M1-IMPLEMENTATION-ORDER.md; until then, all endpoints return "
        "501 or 503 with a structured 'not implemented' body."
    ),
)


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness probe — returns 200 as soon as the process is serving requests.

    Per K8s liveness convention: this answers "is the process alive?" and is
    independent of whether the gateway config has loaded or providers are
    reachable. Used by docker-compose healthchecks and orchestration platforms.
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
    """Readiness probe — returns 200 when gateway can serve real inference traffic.

    Per K8s readiness convention: returns 503 until Task A3 lands gateway.yaml
    loading and validation, after which it returns 200 once the config parses
    and at least one provider is reachable.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_ready",
            "service": SERVICE_NAME,
            "version": __version__,
            "reason": "scaffold_only",
            "next_task": "A3 — Inference Gateway minimal scaffold (gateway.yaml load + validation)",
        },
    )
