"""Practice-area endpoints — F1-S2 (fork, ADR-F002).

* ``GET /api/v1/practice-areas`` — bearer-authed read for every active
  user: the cockpit's left rail lists the areas with their honest
  configured / not-yet-configured state. Readable by everyone for the
  same reason the Organization Profile is (PRD §1.3 transparency —
  users are entitled to see how their workspace is organised).

Read-only in S2: rows are seeded by migration 0053 and curated by the
operator. The config/admin API (area profile, bound skills/playbooks/
MCPs, tier floor) is F1-S3 scope and will extend this module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser
from app.db.session import get_db
from app.models.practice_area import PracticeArea
from app.schemas.practice_areas import PracticeAreaListResponse, PracticeAreaRead

router = APIRouter(prefix="/practice-areas", tags=["practice-areas"])


@router.get(
    "",
    response_model=PracticeAreaListResponse,
    summary="List practice areas (cockpit left rail), position order.",
)
async def list_practice_areas(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PracticeAreaListResponse:
    """GET /api/v1/practice-areas

    Deployment-wide curated list (single-org model — NORTH-STAR
    invariant 4: no per-tenant scoping), ordered by ``position`` then
    ``key`` for deterministic rendering.
    """
    rows = (
        (
            await db.execute(
                select(PracticeArea).order_by(PracticeArea.position, PracticeArea.key)
            )
        )
        .scalars()
        .all()
    )
    return PracticeAreaListResponse(
        practice_areas=[PracticeAreaRead.model_validate(r) for r in rows]
    )
