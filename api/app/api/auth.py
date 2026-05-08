"""Auth endpoints — A4 scaffold.

Per ADR 0002 (Backend owns authentication) and `backend-openapi.yaml`,
the backend exposes login, logout, refresh, MFA setup, and MFA verify.
Real handlers land in Task B1 (login/logout/refresh) and Task D5 (MFA).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/auth", tags=["auth"])

_B1 = "B1 — User model + auth endpoints (backend)"
_D5 = "D5 — MFA enrollment + verification"


@router.post("/login")
async def login(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_B1, endpoint="POST /api/v1/auth/login")


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_B1, endpoint="POST /api/v1/auth/logout")


@router.post("/refresh")
async def refresh(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_B1, endpoint="POST /api/v1/auth/refresh")


@router.post("/mfa/setup")
async def mfa_setup(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D5, endpoint="POST /api/v1/auth/mfa/setup")


@router.post("/mfa/verify")
async def mfa_verify(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_D5, endpoint="POST /api/v1/auth/mfa/verify")
