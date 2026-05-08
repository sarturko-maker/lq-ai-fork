"""HTTP API routers for the backend.

Each module under `app.api` corresponds to one tag-group in
`docs/api/backend-openapi.yaml`. In Task A4 (this scaffold), every endpoint
is registered but returns HTTP 501 with a structured "not implemented" body
that names the M1 task implementing it. Subsequent tasks (B1, B5, C3, C4,
C7, etc.) replace each 501 with a real handler.
"""

from fastapi import APIRouter

from app.api import (
    admin,
    auth,
    chats,
    files,
    knowledge_bases,
    organization_profile,
    projects,
    saved_prompts,
    skills,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(chats.router)
api_router.include_router(skills.router)
api_router.include_router(files.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(organization_profile.router)
api_router.include_router(saved_prompts.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
