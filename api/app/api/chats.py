"""Chats and messages endpoints — A4 scaffold.

Real chat / message persistence + streaming lands in Task C3 (Chat service).
The citations subresource depends on C3 + C5 (document pipeline) being in
place; until then it returns 501.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/chats", tags=["chats"])

_C3 = "C3 — Chat service + message persistence"


@router.get("")
async def list_chats(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="GET /api/v1/chats")


@router.post("")
async def create_chat(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="POST /api/v1/chats")


@router.get("/{chat_id}")
async def get_chat(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="GET /api/v1/chats/{chat_id}")


@router.patch("/{chat_id}")
async def update_chat(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="PATCH /api/v1/chats/{chat_id}")


@router.delete("/{chat_id}")
async def delete_chat(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="DELETE /api/v1/chats/{chat_id}")


@router.get("/{chat_id}/messages")
async def list_messages(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="GET /api/v1/chats/{chat_id}/messages")


@router.post("/{chat_id}/messages")
async def send_message(request: Request, chat_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C3, endpoint="POST /api/v1/chats/{chat_id}/messages")


@router.get("/{chat_id}/messages/{message_id}/citations")
async def get_citations(request: Request, chat_id: str, message_id: str) -> JSONResponse:
    return not_implemented(
        request,
        next_task=_C3,
        endpoint="GET /api/v1/chats/{chat_id}/messages/{message_id}/citations",
    )
