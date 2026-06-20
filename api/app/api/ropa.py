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
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app import ropa_export, ropa_graph, ropa_summary
from app.db.session import get_db
from app.models.ropa import (
    DataCategory,
    DataSubjectCategory,
    ProcessingActivity,
    System,
    Transfer,
    Vendor,
)
from app.schemas.ropa import (
    DataCategoryRead,
    DataFlowGraph,
    DataSubjectCategoryRead,
    ProcessingActivityRead,
    ProgrammeSummary,
    SystemRead,
    VendorRead,
)

router = APIRouter(prefix="/ropa", tags=["ropa"])

_Db = Annotated[AsyncSession, Depends(get_db)]

# Soft-retire (PRIV-8a, ADR-F023): the four mutable register entities. Reads
# exclude retired rows by default so the live register is the "current" record;
# ``?include_retired=true`` on the list endpoints shows them for audit.
_RETIRABLE = (ProcessingActivity, System, Vendor, Transfer)


def _live_only(*, exclude: type | None = None) -> list[Any]:
    """``with_loader_criteria`` options that drop retired rows from EAGER-LOADED
    relationships (a retired system/vendor disappears from an activity; a retired
    activity from a system's reverse link; a transfer's retired recipient vendor
    becomes null). ``exclude`` skips one entity — used on the detail endpoints so
    the lead row still resolves by id even when itself retired.
    """
    return [
        with_loader_criteria(model, model.retired_at.is_(None))
        for model in _RETIRABLE
        if model is not exclude
    ]


def _hide_retired[M: (ProcessingActivity, System, Vendor)](
    stmt: Select[Any], model: type[M], *, include_retired: bool
) -> Select[Any]:
    """Apply the live-register filter to a list query unless ``include_retired``.

    One place for "exclude retired" so a new list endpoint can't forget it (the
    slice's load-bearing risk): filters the lead row (``.where``) and every
    eager-loaded relationship (``_live_only``; the lead is excluded there since the
    ``.where`` already covers it).
    """
    if include_retired:
        return stmt
    return stmt.where(model.retired_at.is_(None)).options(*_live_only(exclude=model))


class ExportFormat(StrEnum):
    """Article 30 export formats (PRIV-4a). An off-enum value is a 422 at the boundary."""

    JSON = "json"
    CSV = "csv"
    XLSX = "xlsx"


_INCLUDE_RETIRED = Query(
    False, description="Include soft-retired rows (ADR-F023); default false (live register only)."
)


@router.get("/processing-activities", response_model=list[ProcessingActivityRead])
async def list_processing_activities(
    db: _Db, include_retired: bool = _INCLUDE_RETIRED
) -> list[ProcessingActivity]:
    """The company ROPA register — all processing activities (with linked systems).

    Retired entries are hidden unless ``include_retired=true`` (PRIV-8a, ADR-F023).
    """
    stmt = (
        select(ProcessingActivity)
        .options(
            selectinload(ProcessingActivity.systems),
            selectinload(ProcessingActivity.vendors),
            selectinload(ProcessingActivity.transfers).selectinload(Transfer.vendor),
            selectinload(ProcessingActivity.data_subject_categories),
            selectinload(ProcessingActivity.data_categories),
            selectinload(ProcessingActivity.assessments),  # PRIV-A3 write-back marker
        )
        .order_by(ProcessingActivity.created_at.asc(), ProcessingActivity.name.asc())
    )
    stmt = _hide_retired(stmt, ProcessingActivity, include_retired=include_retired)
    rows = (await db.execute(stmt)).scalars().all()
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
                selectinload(ProcessingActivity.data_subject_categories),
                selectinload(ProcessingActivity.data_categories),
                selectinload(ProcessingActivity.assessments),  # PRIV-A3 write-back marker
                # The activity itself resolves even if retired (deep-link/audit), but
                # its linked records are shown live-only (PRIV-8a, ADR-F023).
                *_live_only(exclude=ProcessingActivity),
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
async def list_systems(db: _Db, include_retired: bool = _INCLUDE_RETIRED) -> list[System]:
    """The company system inventory — all systems (with linked processing activities).

    Retired systems are hidden unless ``include_retired=true`` (PRIV-8a, ADR-F023).
    """
    stmt = (
        select(System)
        .options(selectinload(System.processing_activities))
        .order_by(System.created_at.asc(), System.name.asc())
    )
    stmt = _hide_retired(stmt, System, include_retired=include_retired)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.get("/systems/{system_id}", response_model=SystemRead)
async def get_system(system_id: uuid.UUID, db: _Db) -> System:
    """One system + the processing activities that use it."""
    row = (
        await db.execute(
            select(System)
            .options(
                selectinload(System.processing_activities),
                *_live_only(exclude=System),
            )
            .where(System.id == system_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="system not found")
    return row


@router.get("/vendors", response_model=list[VendorRead])
async def list_vendors(db: _Db, include_retired: bool = _INCLUDE_RETIRED) -> list[Vendor]:
    """The company vendor/recipient register — all vendors (with linked activities).

    Retired vendors are hidden unless ``include_retired=true`` (PRIV-8a, ADR-F023).
    """
    stmt = (
        select(Vendor)
        .options(selectinload(Vendor.processing_activities))
        .order_by(Vendor.created_at.asc(), Vendor.name.asc())
    )
    stmt = _hide_retired(stmt, Vendor, include_retired=include_retired)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.get("/vendors/{vendor_id}", response_model=VendorRead)
async def get_vendor(vendor_id: uuid.UUID, db: _Db) -> Vendor:
    """One vendor/recipient + the processing activities that disclose to it."""
    row = (
        await db.execute(
            select(Vendor)
            .options(
                selectinload(Vendor.processing_activities),
                *_live_only(exclude=Vendor),
            )
            .where(Vendor.id == vendor_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vendor not found")
    return row


async def _all_categories[M: (DataSubjectCategory, DataCategory)](
    db: AsyncSession, model: type[M]
) -> list[M]:
    """The full ordered, activity-eager-loaded category vocabulary (PRIV-6a).

    Shared by the two list endpoints + the export so ordering/eager-loading stay
    in lockstep. Ordered created_at-then-name to match the agent's ``list_*``
    tools and the System/Vendor surfaces (one register order everywhere).
    """
    rows = (
        (
            await db.execute(
                select(model)
                .options(selectinload(model.processing_activities), *_live_only())
                .order_by(model.created_at.asc(), model.name.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.get("/data-subject-categories", response_model=list[DataSubjectCategoryRead])
async def list_data_subject_categories(db: _Db) -> list[DataSubjectCategory]:
    """The company ROPA vocabulary of data-subject categories (Article 30(1)(c))."""
    return await _all_categories(db, DataSubjectCategory)


@router.get("/data-categories", response_model=list[DataCategoryRead])
async def list_data_categories(db: _Db) -> list[DataCategory]:
    """The company ROPA vocabulary of personal-data categories (Article 30(1)(c))."""
    return await _all_categories(db, DataCategory)


async def _load_register(
    db: AsyncSession,
) -> tuple[
    list[ProcessingActivity],
    list[System],
    list[Vendor],
    list[DataSubjectCategory],
    list[DataCategory],
]:
    """Load the whole deployment-global register, eager-loaded for read-and-render.

    Shared by the Article 30 export and the programme summary so both render the
    same rows through one load path (ADR-F019 shared-read; ordering matches the
    list endpoints — created_at then name everywhere).
    """
    activities = (
        (
            await db.execute(
                select(ProcessingActivity)
                .options(
                    selectinload(ProcessingActivity.systems),
                    selectinload(ProcessingActivity.vendors),
                    selectinload(ProcessingActivity.transfers).selectinload(Transfer.vendor),
                    selectinload(ProcessingActivity.data_subject_categories),
                    selectinload(ProcessingActivity.data_categories),
                    # PRIV-A3 write-back projection — loaded so ProcessingActivityRead
                    # serializes ``assessments`` without an async lazy-load here too.
                    selectinload(ProcessingActivity.assessments),
                    *_live_only(exclude=ProcessingActivity),
                )
                .where(ProcessingActivity.retired_at.is_(None))
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
                .options(selectinload(System.processing_activities), *_live_only(exclude=System))
                .where(System.retired_at.is_(None))
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
                .options(selectinload(Vendor.processing_activities), *_live_only(exclude=Vendor))
                .where(Vendor.retired_at.is_(None))
                .order_by(Vendor.created_at.asc(), Vendor.name.asc())
            )
        )
        .scalars()
        .all()
    )
    data_subject_categories = await _all_categories(db, DataSubjectCategory)
    data_categories = await _all_categories(db, DataCategory)
    return (
        list(activities),
        list(systems),
        list(vendors),
        data_subject_categories,
        data_categories,
    )


@router.get("/programme-summary", response_model=ProgrammeSummary)
async def get_programme_summary(db: _Db) -> ProgrammeSummary:
    """The privacy-programme overview over the deployment-global ROPA register (PRIV-6b).

    Read-only aggregate (shared-read, ADR-F019): headline totals, breakdowns by
    lawful basis / controller role / DPA status, special-category & restricted-
    transfer counts, and honest "needs attention" gaps. Counts only — no
    free-text — so the payload carries even less than the register read endpoints.
    """
    activities, systems, vendors, _, _ = await _load_register(db)
    return ropa_summary.build_summary(
        [ProcessingActivityRead.model_validate(a) for a in activities],
        [SystemRead.model_validate(s) for s in systems],
        [VendorRead.model_validate(v) for v in vendors],
    )


@router.get("/data-flow", response_model=DataFlowGraph)
async def get_data_flow(db: _Db) -> DataFlowGraph:
    """The data-flow / lineage projection over the deployment-global ROPA register (PRIV-6c).

    Read-only node-link graph (shared-read, ADR-F019): systems feed the
    processing activities that use them, which in turn disclose to recipient
    vendors and transfer to third-country destinations (the Chapter V safeguard
    rides each transfer edge). Labels + categorical badges only — no free-text —
    so the payload carries no more than the register read endpoints already
    expose. Orphan systems/vendors appear as unconnected nodes.
    """
    activities, systems, vendors, _, _ = await _load_register(db)
    return ropa_graph.build_graph(
        [ProcessingActivityRead.model_validate(a) for a in activities],
        [SystemRead.model_validate(s) for s in systems],
        [VendorRead.model_validate(v) for v in vendors],
    )


@router.get("/export")
async def export_article_30(db: _Db, format: ExportFormat = ExportFormat.JSON) -> Response:
    """Export the company ROPA as an Article 30 deliverable (JSON / CSV / XLSX).

    Read-and-render over the deployment-global register (ADR-F019): every
    processing activity with its lawful basis / retention / special-category,
    joined across the M:N to its linked systems and recipients (vendors) and its
    child third-country transfers, plus the system and vendor inventories.
    Shared-read posture (``_active`` at the mount) — the register is the
    company's standing record, not a per-user artifact. As of PRIV-6a the export
    captures the full Article 30(1) content set, including the 30(1)(c)
    data-subject / personal-data taxonomy, so the coverage note is empty; the note
    mechanism is retained (still honest) for any future Article 30(1) gap.
    """
    activities, systems, vendors, data_subject_categories, data_categories = await _load_register(
        db
    )

    export = ropa_export.build_export(
        [ProcessingActivityRead.model_validate(a) for a in activities],
        [SystemRead.model_validate(s) for s in systems],
        [VendorRead.model_validate(v) for v in vendors],
        [DataSubjectCategoryRead.model_validate(c) for c in data_subject_categories],
        [DataCategoryRead.model_validate(c) for c in data_categories],
        generated_at=datetime.now(UTC),
    )

    stamp = export.generated_at.date().isoformat()
    if format is ExportFormat.JSON:
        return Response(
            # The Article 30 deliverable carries the Article 30(1) content set only.
            # The PRIV-A3 write-back marker (ProcessingActivityRead.assessments) is a
            # register-UI projection, NOT part of the regulatory record — exclude it
            # so the export's wire shape does not drift (the activity DTO is shared
            # with the register reads, which DO carry it). Regression: test_ropa_export.
            content=export.model_dump_json(
                exclude={"processing_activities": {"__all__": {"assessments"}}}
            ),
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
