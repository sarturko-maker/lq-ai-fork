"""ROPA register read API — PRIV-3 (fork, ADR-F018/F019).

Read-only endpoints over the Privacy module's **deployment-global** inventory
graph (Systems ↔ Processing Activities). The register is the company's standing
record (LQ.AI is single-tenant — the in-house team's one client is its own
organization; ADR-F019), so it is intentionally **shared across the firm's
users**: the cross-user→404 rule that protects private matters does NOT apply
here. The gate is just "active (authenticated) firm user", enforced at the
``include_router`` site (``dependencies=_active``); a 404 means a genuinely
missing record id, not an existence-hiding authz refusal.

Writes are NOT here — the Privacy Deep Agent is the only writer, through the
guarded, code-validated tools (``app.agents.ropa_tools``); the user reads and
owns ("system proposes, user owns", ADR-0013 D4).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.ropa import ProcessingActivity, System
from app.schemas.ropa import ProcessingActivityRead, SystemRead

router = APIRouter(prefix="/ropa", tags=["ropa"])

_Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/processing-activities", response_model=list[ProcessingActivityRead])
async def list_processing_activities(db: _Db) -> list[ProcessingActivity]:
    """The company ROPA register — all processing activities (with linked systems)."""
    rows = (
        (
            await db.execute(
                select(ProcessingActivity)
                .options(selectinload(ProcessingActivity.systems))
                .order_by(ProcessingActivity.created_at.asc(), ProcessingActivity.name.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get("/processing-activities/{activity_id}", response_model=ProcessingActivityRead)
async def get_processing_activity(activity_id: uuid.UUID, db: _Db) -> ProcessingActivity:
    """One processing activity + the systems it uses."""
    row = (
        await db.execute(
            select(ProcessingActivity)
            .options(selectinload(ProcessingActivity.systems))
            .where(ProcessingActivity.id == activity_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="processing activity not found"
        )
    return row


@router.get("/systems", response_model=list[SystemRead])
async def list_systems(db: _Db) -> list[System]:
    """The company system inventory — all systems (with linked processing activities)."""
    rows = (
        (
            await db.execute(
                select(System)
                .options(selectinload(System.processing_activities))
                .order_by(System.created_at.asc(), System.name.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get("/systems/{system_id}", response_model=SystemRead)
async def get_system(system_id: uuid.UUID, db: _Db) -> System:
    """One system + the processing activities that use it."""
    row = (
        await db.execute(
            select(System)
            .options(selectinload(System.processing_activities))
            .where(System.id == system_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="system not found")
    return row
