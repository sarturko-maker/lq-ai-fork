"""Knowledge-base endpoints — A4 scaffold.

KB CRUD and hybrid (vector + FTS) search land in Task C6 (Knowledge
Service: hybrid retrieval), which builds on C5's document pipeline.

Note: the OpenAPI sketch (`docs/api/backend-openapi.yaml`) currently
defines `GET /api/v1/knowledge-bases`, `POST /api/v1/knowledge-bases`,
and `POST /api/v1/knowledge-bases/{kb_id}/search` — but no per-KB
GET / PATCH / DELETE. We register only what the sketch declares; the
remaining CRUD endpoints will be added when the sketch is updated in C6.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])

_C6 = "C6 — Knowledge Service: hybrid retrieval"


@router.get("")
async def list_kbs(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C6, endpoint="GET /api/v1/knowledge-bases")


@router.post("")
async def create_kb(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C6, endpoint="POST /api/v1/knowledge-bases")


@router.post("/{kb_id}/search")
async def search_kb(request: Request, kb_id: str) -> JSONResponse:
    return not_implemented(
        request,
        next_task=_C6,
        endpoint="POST /api/v1/knowledge-bases/{kb_id}/search",
    )
