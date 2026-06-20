"""Assessment register read API — PRIV-A3 (fork, ADR-F018/F019/F027).

Read-only endpoints over the Privacy module's **deployment-global** assessment
record — the PIA / DPIA / LIA / TIA assessments (``app.models.assessment``) and
the risk findings within them, the assessment-track sibling of the ROPA register
read API (``app.api.ropa``). Mounted under the same ``/ropa`` prefix and the same
shared-read posture (ADR-F019 — LQ.AI is single-tenant; the assessment record is
the company's standing accountability record, not a per-user artifact): the gate
is just "active (authenticated) firm user", enforced at the ``include_router``
site (``dependencies=_active``); a 404 means a genuinely missing assessment id,
not an existence-hiding authz refusal.

Writes are NOT here — the Privacy Deep Agent is the only writer, through the
guarded, code-validated tools (``app.agents.assessment_tools``); the user reads
and owns ("system proposes, user owns", ADR-0013 D4).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.db.session import get_db
from app.models.assessment import Assessment
from app.models.ropa import ProcessingActivity
from app.schemas.assessment import AssessmentRead

# Mounted under the ROPA register prefix (the assessment record is part of the
# privacy register surface) but tagged separately for the OpenAPI grouping.
router = APIRouter(prefix="/ropa", tags=["assessments"])

_Db = Annotated[AsyncSession, Depends(get_db)]


def _read_options() -> list[Any]:
    """Eager-load options shared by the list and detail reads.

    Loads the risks and the **live** linked activities (a retired activity has
    left the register — the same live-only criterion the agent's
    ``list_assessments`` and the ROPA reads apply, ADR-F023). Assessments do not
    soft-retire (deferred in PRIV-A1), so the lead rows are always live.
    """
    return [
        selectinload(Assessment.risks),
        selectinload(Assessment.processing_activities),
        with_loader_criteria(ProcessingActivity, ProcessingActivity.retired_at.is_(None)),
    ]


@router.get("/assessments", response_model=list[AssessmentRead])
async def list_assessments(db: _Db) -> list[Assessment]:
    """The company assessment register — every PIA/DPIA/LIA/TIA (with risks).

    Ordered oldest-first (created_at then title), matching the agent's
    ``list_assessments`` and the ROPA list endpoints.
    """
    rows = (
        (
            await db.execute(
                select(Assessment)
                .options(*_read_options())
                .order_by(Assessment.created_at.asc(), Assessment.title.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get("/assessments/{assessment_id}", response_model=AssessmentRead)
async def get_assessment(assessment_id: uuid.UUID, db: _Db) -> Assessment:
    """One privacy assessment + its risks and the activities it covers."""
    row = (
        await db.execute(
            select(Assessment).options(*_read_options()).where(Assessment.id == assessment_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assessment not found")
    return row
