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
from app.models.compliance import AiSystem
from app.schemas.compliance import AiSystemRead

router = APIRouter(prefix="/compliance", tags=["ai-compliance"])

_Db = Annotated[AsyncSession, Depends(get_db)]

_INCLUDE_RETIRED = Query(
    False, description="Include soft-retired rows; default false (live register only)."
)


@router.get("/ai-systems", response_model=list[AiSystemRead])
async def list_ai_systems(db: _Db, include_retired: bool = _INCLUDE_RETIRED) -> list[AiSystem]:
    """The company AI-systems register — all systems (oldest first).

    Retired systems are hidden unless ``include_retired=true``.
    """
    stmt = select(AiSystem).order_by(AiSystem.created_at.asc(), AiSystem.name.asc())
    if not include_retired:
        stmt = stmt.where(AiSystem.retired_at.is_(None))
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.get("/ai-systems/{ai_system_id}", response_model=AiSystemRead)
async def get_ai_system(ai_system_id: uuid.UUID, db: _Db) -> AiSystem:
    """One AI system in the register (resolves even if retired, for deep-link/audit)."""
    row = (
        await db.execute(select(AiSystem).where(AiSystem.id == ai_system_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
    return row
