"""Skills endpoints — A4 scaffold.

Skill listing and detail land in Task C1 (Skill Service: filesystem
loading). The fork endpoint lands later in C1 / C2 once the user/team
scopes are wired through the database.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/skills", tags=["skills"])

_C1 = "C1 — Skill Service: filesystem loading"


@router.get("")
async def list_skills(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C1, endpoint="GET /api/v1/skills")


@router.get("/{skill_name}")
async def get_skill(request: Request, skill_name: str) -> JSONResponse:
    return not_implemented(request, next_task=_C1, endpoint="GET /api/v1/skills/{skill_name}")


@router.post("/{skill_name}/fork")
async def fork_skill(request: Request, skill_name: str) -> JSONResponse:
    return not_implemented(request, next_task=_C1, endpoint="POST /api/v1/skills/{skill_name}/fork")
