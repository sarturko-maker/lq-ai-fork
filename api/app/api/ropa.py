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
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import ropa_export
from app.db.session import get_db
from app.models.ropa import ProcessingActivity, System, Transfer, Vendor
from app.schemas.ropa import ProcessingActivityRead, SystemRead, VendorRead

router = APIRouter(prefix="/ropa", tags=["ropa"])

_Db = Annotated[AsyncSession, Depends(get_db)]


class ExportFormat(StrEnum):
    """Article 30 export formats (PRIV-4a). An off-enum value is a 422 at the boundary."""

    JSON = "json"
    CSV = "csv"
    XLSX = "xlsx"


@router.get("/processing-activities", response_model=list[ProcessingActivityRead])
async def list_processing_activities(db: _Db) -> list[ProcessingActivity]:
    """The company ROPA register — all processing activities (with linked systems)."""
    rows = (
        (
            await db.execute(
                select(ProcessingActivity)
                .options(
                    selectinload(ProcessingActivity.systems),
                    selectinload(ProcessingActivity.vendors),
                    selectinload(ProcessingActivity.transfers).selectinload(Transfer.vendor),
                )
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
            .options(
                selectinload(ProcessingActivity.systems),
                selectinload(ProcessingActivity.vendors),
                selectinload(ProcessingActivity.transfers).selectinload(Transfer.vendor),
            )
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


@router.get("/vendors", response_model=list[VendorRead])
async def list_vendors(db: _Db) -> list[Vendor]:
    """The company vendor/recipient register — all vendors (with linked activities)."""
    rows = (
        (
            await db.execute(
                select(Vendor)
                .options(selectinload(Vendor.processing_activities))
                .order_by(Vendor.created_at.asc(), Vendor.name.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get("/vendors/{vendor_id}", response_model=VendorRead)
async def get_vendor(vendor_id: uuid.UUID, db: _Db) -> Vendor:
    """One vendor/recipient + the processing activities that disclose to it."""
    row = (
        await db.execute(
            select(Vendor)
            .options(selectinload(Vendor.processing_activities))
            .where(Vendor.id == vendor_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vendor not found")
    return row


@router.get("/export")
async def export_article_30(db: _Db, format: ExportFormat = ExportFormat.JSON) -> Response:
    """Export the company ROPA as an Article 30 deliverable (JSON / CSV / XLSX).

    Read-and-render over the deployment-global register (ADR-F019): every
    processing activity with its lawful basis / retention / special-category,
    joined across the M:N to its linked systems and recipients (vendors) and its
    child third-country transfers, plus the system and vendor inventories.
    Shared-read posture (``_active`` at the mount) — the register is the
    company's standing record, not a per-user artifact. The export is HONEST
    about the Article 30(1) fields the domain does not yet capture (see the
    coverage note; the data-subject/data-category taxonomy arrives with PRIV-6).
    """
    activities = (
        (
            await db.execute(
                select(ProcessingActivity)
                .options(
                    selectinload(ProcessingActivity.systems),
                    selectinload(ProcessingActivity.vendors),
                    selectinload(ProcessingActivity.transfers).selectinload(Transfer.vendor),
                )
                .order_by(ProcessingActivity.created_at.asc(), ProcessingActivity.name.asc())
            )
        )
        .scalars()
        .all()
    )
    systems = (
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
    vendors = (
        (
            await db.execute(
                select(Vendor)
                .options(selectinload(Vendor.processing_activities))
                .order_by(Vendor.created_at.asc(), Vendor.name.asc())
            )
        )
        .scalars()
        .all()
    )

    export = ropa_export.build_export(
        [ProcessingActivityRead.model_validate(a) for a in activities],
        [SystemRead.model_validate(s) for s in systems],
        [VendorRead.model_validate(v) for v in vendors],
        generated_at=datetime.now(UTC),
    )

    stamp = export.generated_at.date().isoformat()
    if format is ExportFormat.JSON:
        return Response(
            content=export.model_dump_json(),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="article-30-ropa-{stamp}.json"'},
        )
    if format is ExportFormat.CSV:
        return Response(
            content=ropa_export.to_csv(export),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="article-30-ropa-{stamp}.csv"'},
        )
    return Response(
        content=ropa_export.to_xlsx(export),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="article-30-ropa-{stamp}.xlsx"'},
    )
