"""Files endpoints — A4 scaffold.

Upload / metadata / download land in Task C4 (File upload + storage).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/files", tags=["files"])

_C4 = "C4 — File upload + storage"


@router.post("")
async def upload_file(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C4, endpoint="POST /api/v1/files")


@router.get("/{file_id}")
async def get_file(request: Request, file_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C4, endpoint="GET /api/v1/files/{file_id}")


@router.delete("/{file_id}")
async def delete_file(request: Request, file_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C4, endpoint="DELETE /api/v1/files/{file_id}")


@router.get("/{file_id}/content")
async def get_file_content(request: Request, file_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C4, endpoint="GET /api/v1/files/{file_id}/content")
