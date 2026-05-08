"""Helpers for the A4 endpoint scaffold.

Every endpoint in M1 is registered up front so that the OpenAPI surface
served at `/openapi.json` matches `docs/api/backend-openapi.yaml`. Until
the implementing task lands, each endpoint returns HTTP 501 with a
structured body that names the implementing task — making it obvious to
callers (humans, the web client, integration tests, the Word add-in)
that the surface exists but the body has not yet been wired.

The body shape is intentionally consistent so clients can branch on
`error.code == 'not_implemented'`.
"""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse


def not_implemented(
    request: Request,
    *,
    next_task: str,
    endpoint: str | None = None,
) -> JSONResponse:
    """Return the canonical 501 body for an unimplemented endpoint.

    `next_task` is a short label like "B1 — User model + auth endpoints"
    pointing the caller at `docs/M1-IMPLEMENTATION-ORDER.md`.

    `endpoint` defaults to the request method + path, but callers may pass
    a stable label (useful when the path contains a parameter).
    """
    method = request.method.upper()
    path = endpoint if endpoint is not None else request.url.path
    label = path if endpoint is not None else f"{method} {path}"
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": {
                "code": "not_implemented",
                "message": (
                    "Endpoint scaffold; full implementation lands in "
                    f"Task {next_task.split(' ')[0]}."
                ),
                "endpoint": label,
                "next_task": next_task,
            }
        },
    )
