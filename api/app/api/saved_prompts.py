"""Saved-prompts endpoints — A4 scaffold.

Per-user saved prompt fragments. CRUD lands in Task D7 (Saved Prompts).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/saved-prompts", tags=["saved-prompts"])

_D7 = "D7 — Saved Prompts"


@router.get("")
async def list_prompts(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D7, endpoint="GET /api/v1/saved-prompts")


@router.post("")
async def create_prompt(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D7, endpoint="POST /api/v1/saved-prompts")


@router.get("/{prompt_id}")
async def get_prompt(request: Request, prompt_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_D7, endpoint="GET /api/v1/saved-prompts/{prompt_id}")


@router.patch("/{prompt_id}")
async def update_prompt(request: Request, prompt_id: str) -> JSONResponse:
    return not_implemented(
        request, next_task=_D7, endpoint="PATCH /api/v1/saved-prompts/{prompt_id}"
    )


@router.delete("/{prompt_id}")
async def delete_prompt(request: Request, prompt_id: str) -> JSONResponse:
    return not_implemented(
        request, next_task=_D7, endpoint="DELETE /api/v1/saved-prompts/{prompt_id}"
    )
