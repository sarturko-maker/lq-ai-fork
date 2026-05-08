"""InHouse AI Inference Gateway entrypoint.

This is the M1-Task-A1 scaffold: a minimal FastAPI service that returns 503 from
its health endpoints and 501 from inference endpoints. Implementation lands in
Tasks A3, B3, B4 per docs/M1-IMPLEMENTATION-ORDER.md.
"""

from __future__ import annotations

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app import __version__

SERVICE_NAME = "inhouse-ai-gateway"

app = FastAPI(
    title="InHouse AI Inference Gateway",
    version=__version__,
    description=(
        "OpenAI-compatible inference gateway and security boundary for the "
        "InHouse AI platform. The gateway annotates every routed request with "
        "its derived Inference Tier (1-5) per PRD §3.13 / §1.5.2 and refuses "
        "requests below a declared minimum. M1 implementation lands progressively "
        "per docs/M1-IMPLEMENTATION-ORDER.md; until then, all endpoints return "
        "501 or 503 with a structured 'not implemented' body."
    ),
)


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness probe.

    Returns 503 until Task A3 (Inference Gateway minimal scaffold) wires up
    config loading and basic routing.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_implemented",
            "service": SERVICE_NAME,
            "version": __version__,
            "next_task": "A3 — Inference Gateway minimal scaffold",
        },
    )


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe (checks gateway.yaml load + provider reachability).

    Returns 503 until Task A3 implements config validation.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_implemented",
            "service": SERVICE_NAME,
            "version": __version__,
            "next_task": "A3 — Inference Gateway minimal scaffold (gateway.yaml load + validation)",
        },
    )
