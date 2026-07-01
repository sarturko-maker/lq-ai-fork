"""AI-systems register read API — AIC-1 (fork, ADR-F057/F018/F019).

Read-only endpoints over the AI Compliance module's **deployment-global** register
of the organisation's AI systems. The register is the company's standing record
(LQ.AI is single-tenant; ADR-F019), so it is intentionally **shared across the
firm's users**: the cross-user→404 rule that protects private matters does NOT
apply here. The gate is just "active (authenticated) firm user", enforced at the
``include_router`` site (``dependencies=_active``); a 404 means a genuinely missing
record id, not an existence-hiding authz refusal.

Writes are NOT here — the AI Compliance Deep Agent is the only writer, through the
guarded, code-validated tools (``app.agents.compliance_tools``); the user reads and
owns ("system proposes, user owns", ADR-0013 D4). The risk classification is a
legal determination owned by the deterministic engine (AIC-2, ADR-F057), not the
model — this register carries only the FACTS that feed it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.classification import RiskClassification
from app.models.compliance import AiSystem
from app.schemas.classification import ClassificationSummary, VerdictRead
from app.schemas.compliance import AiSystemRead

router = APIRouter(prefix="/compliance", tags=["ai-compliance"])

_Db = Annotated[AsyncSession, Depends(get_db)]

_INCLUDE_RETIRED = Query(
    False, description="Include soft-retired rows; default false (live register only)."
)


async def _current_verdicts(
    db: AsyncSession, ai_system_ids: list[uuid.UUID]
) -> dict[uuid.UUID, RiskClassification]:
    """Map each system id to its CURRENT (un-superseded) verdict, if any.

    One query for the whole page — the register badge without an N+1. The partial
    unique index guarantees at most one current row per system.
    """
    if not ai_system_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(RiskClassification).where(
                    RiskClassification.ai_system_id.in_(ai_system_ids),
                    RiskClassification.superseded_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.ai_system_id: row for row in rows}


def _with_badge(system: AiSystem, verdict: RiskClassification | None) -> AiSystemRead:
    read = AiSystemRead.model_validate(system)
    if verdict is not None:
        read.classification = ClassificationSummary.model_validate(verdict)
    return read


@router.get("/ai-systems", response_model=list[AiSystemRead])
async def list_ai_systems(db: _Db, include_retired: bool = _INCLUDE_RETIRED) -> list[AiSystemRead]:
    """The company AI-systems register — all systems (oldest first), with risk badges.

    Retired systems are hidden unless ``include_retired=true``. Each row carries its
    current risk verdict (``classification``) when the engine has classified it.
    """
    stmt = select(AiSystem).order_by(AiSystem.created_at.asc(), AiSystem.name.asc())
    if not include_retired:
        stmt = stmt.where(AiSystem.retired_at.is_(None))
    rows = list((await db.execute(stmt)).scalars().all())
    verdicts = await _current_verdicts(db, [row.id for row in rows])
    return [_with_badge(row, verdicts.get(row.id)) for row in rows]


@router.get("/ai-systems/{ai_system_id}", response_model=AiSystemRead)
async def get_ai_system(ai_system_id: uuid.UUID, db: _Db) -> AiSystemRead:
    """One AI system in the register (resolves even if retired, for deep-link/audit)."""
    row = (
        await db.execute(select(AiSystem).where(AiSystem.id == ai_system_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
    verdicts = await _current_verdicts(db, [row.id])
    return _with_badge(row, verdicts.get(row.id))


@router.get("/ai-systems/{ai_system_id}/classification", response_model=VerdictRead)
async def get_ai_system_classification(ai_system_id: uuid.UUID, db: _Db) -> RiskClassification:
    """The current sealed risk verdict for one system — tier, route, refs, full trace.

    404 when the system is not yet classified (or the id is unknown — the register is
    deployment-global, so a 404 is a genuinely missing verdict, not an authz refusal).
    """
    verdict = (
        await db.execute(
            select(RiskClassification).where(
                RiskClassification.ai_system_id == ai_system_id,
                RiskClassification.superseded_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if verdict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No current classification"
        )
    return verdict
