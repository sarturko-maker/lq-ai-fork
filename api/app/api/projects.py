"""Projects endpoints — A4 scaffold.

Real CRUD lands in Task C7 (Project service). Skill / file attachment
endpoints live alongside the rest of the project surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api._stub import not_implemented

router = APIRouter(prefix="/projects", tags=["projects"])

_C7 = "C7 — Project service"


@router.get("")
async def list_projects(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C7, endpoint="GET /api/v1/projects")


@router.post("")
async def create_project(request: Request) -> JSONResponse:
    return not_implemented(request, next_task=_C7, endpoint="POST /api/v1/projects")


@router.get("/{project_id}")
async def get_project(request: Request, project_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C7, endpoint="GET /api/v1/projects/{project_id}")


@router.patch("/{project_id}")
async def update_project(request: Request, project_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C7, endpoint="PATCH /api/v1/projects/{project_id}")


@router.delete("/{project_id}")
async def delete_project(request: Request, project_id: str) -> JSONResponse:
    return not_implemented(request, next_task=_C7, endpoint="DELETE /api/v1/projects/{project_id}")


@router.post("/{project_id}/skills")
async def attach_skill(request: Request, project_id: str) -> JSONResponse:
    return not_implemented(
        request,
        next_task=_C7,
        endpoint="POST /api/v1/projects/{project_id}/skills",
    )


@router.post("/{project_id}/files")
async def attach_file(request: Request, project_id: str) -> JSONResponse:
    return not_implemented(
        request,
        next_task=_C7,
        endpoint="POST /api/v1/projects/{project_id}/files",
    )
