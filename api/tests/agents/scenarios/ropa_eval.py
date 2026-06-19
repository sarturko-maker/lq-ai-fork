"""PRIV-7 — read-back + coverage scoring for ROPA-population scenario runs.

The scenario :class:`~tests.agents.scenarios.harness.Receipt` records only the
run's *shape* (tool names, step count, the final answer). For a ROPA-*population*
test the honest measure is the register the agent actually wrote — so this module
reads the deployment-global register back (filtered by ``source_project_id``,
ADR-F019 provenance), scores it against an Article 30(1) checklist, and cleans the
rows up so a live run never pollutes the dev register.

Everything here is pure or read-only except :func:`cleanup_register`, which deletes
ONLY the rows a run stamped with its own ``source_project_id``. The notice loader
and the scorer are deliberately generic — they are the reusable substrate for the
broader "populate records from a source" family (files, interviews, instructions),
of which notice→ROPA is the first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models.practice_area import PracticeAreaSkill
from app.models.ropa import (
    DataCategory,
    DataSubjectCategory,
    ProcessingActivity,
    System,
    Transfer,
    Vendor,
)
from tests.agents.scenarios.scenarios import FixtureDocument, build_document

# Bound the agent-written free-text we echo into the committed report. The values
# here are the AGENT's own structured output (never the source notice verbatim),
# but we still keep excerpts short — the report is an evidence artifact, not a copy.
_PURPOSE_EXCERPT = 160


# --- notice → FixtureDocument ------------------------------------------------


def load_notice_document(path: Path, *, filename: str) -> FixtureDocument:
    """Build a :class:`FixtureDocument` from a local plain-text notice file.

    The file is split into sections on top-level Markdown headings (``## ``);
    each section becomes one searchable chunk on its own page, so the agent's
    ``search_documents`` / ``read_document`` tools behave exactly as they do over
    a real ingested document. The text is read from a LOCAL (gitignored) path and
    is never committed — the caller supplies the path (default lives under
    ``scenarios/_local/``).
    """
    raw = path.read_text(encoding="utf-8")
    sections = _split_sections(raw)
    if not sections:
        raise ValueError(f"notice file produced no sections: {path}")
    return build_document(filename, sections)


def _split_sections(text: str) -> list[tuple[int, str]]:
    """Split notice text into ``(page, body)`` sections on ``## `` headings.

    Content before the first heading becomes the first section. Blank-only
    sections are dropped. Page numbers are 1-based and sequential (one per
    section) so citations point somewhere sensible.
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    bodies = [b for b in blocks if b]
    return [(i + 1, body) for i, body in enumerate(bodies)]


# --- register read-back ------------------------------------------------------


@dataclass
class ActivityView:
    """One processing activity plus its linked graph — observations only."""

    name: str
    purpose_excerpt: str
    lawful_basis: str
    controller_role: str
    retention: str
    special_category: bool
    art9_condition: str | None
    system_names: list[str]
    vendor_names: list[str]
    data_subject_categories: list[str]
    data_categories: list[str]
    transfers: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose_excerpt": self.purpose_excerpt,
            "lawful_basis": self.lawful_basis,
            "controller_role": self.controller_role,
            "retention": self.retention,
            "special_category": self.special_category,
            "art9_condition": self.art9_condition,
            "systems": self.system_names,
            "recipients": self.vendor_names,
            "data_subject_categories": self.data_subject_categories,
            "data_categories": self.data_categories,
            "transfers": self.transfers,
        }


@dataclass
class RegisterSnapshot:
    """The register a run produced, scoped to its ``source_project_id``."""

    activities: list[ActivityView] = field(default_factory=list)
    systems: list[dict[str, Any]] = field(default_factory=list)
    vendors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activities": [a.to_dict() for a in self.activities],
            "systems": self.systems,
            "vendors": self.vendors,
        }


async def snapshot_register(
    factory: async_sessionmaker[AsyncSession], source_project_id: Any
) -> RegisterSnapshot:
    """Read back everything a run stamped with ``source_project_id`` (ADR-F019).

    Activities are loaded with their systems / vendors / transfers / category
    links eager-loaded; systems and vendors are loaded by provenance too (a run
    may create an orphan system it never linked — that is itself a finding).
    """
    async with factory() as db:
        activities = (
            (
                await db.execute(
                    select(ProcessingActivity)
                    .where(ProcessingActivity.source_project_id == source_project_id)
                    .options(
                        selectinload(ProcessingActivity.systems),
                        selectinload(ProcessingActivity.vendors),
                        selectinload(ProcessingActivity.data_subject_categories),
                        selectinload(ProcessingActivity.data_categories),
                        selectinload(ProcessingActivity.transfers).selectinload(Transfer.vendor),
                    )
                    .order_by(ProcessingActivity.name)
                )
            )
            .scalars()
            .all()
        )
        systems = (
            (
                await db.execute(
                    select(System)
                    .where(System.source_project_id == source_project_id)
                    .order_by(System.name)
                )
            )
            .scalars()
            .all()
        )
        vendors = (
            (
                await db.execute(
                    select(Vendor)
                    .where(Vendor.source_project_id == source_project_id)
                    .order_by(Vendor.name)
                )
            )
            .scalars()
            .all()
        )

    snapshot = RegisterSnapshot(
        systems=[
            {"name": s.name, "system_type": s.system_type, "ai_usage": s.ai_usage} for s in systems
        ],
        vendors=[
            {
                "name": v.name,
                "vendor_role": v.vendor_role,
                "dpa_status": v.dpa_status,
                "country": v.country,
            }
            for v in vendors
        ],
    )
    for a in activities:
        snapshot.activities.append(
            ActivityView(
                name=a.name,
                purpose_excerpt=_excerpt(a.purpose, _PURPOSE_EXCERPT),
                lawful_basis=a.lawful_basis,
                controller_role=a.controller_role,
                retention=_excerpt(a.retention, _PURPOSE_EXCERPT),
                special_category=a.special_category,
                art9_condition=a.art9_condition,
                system_names=[s.name for s in a.systems],
                vendor_names=[v.name for v in a.vendors],
                data_subject_categories=[c.name for c in a.data_subject_categories],
                data_categories=[c.name for c in a.data_categories],
                transfers=[
                    {
                        "destination": t.destination,
                        "restricted": t.restricted,
                        "mechanism": t.mechanism,
                        "recipient": t.vendor.name if t.vendor is not None else None,
                    }
                    for t in a.transfers
                ],
            )
        )
    return snapshot


def _excerpt(value: str, limit: int) -> str:
    return value[:limit] + ("…" if len(value) > limit else "")


# --- coverage scoring (pure) -------------------------------------------------


def score_coverage(snapshot: RegisterSnapshot) -> dict[str, Any]:
    """Score a snapshot against an Article 30(1) coverage checklist (pure).

    The required fields (purpose / lawful basis / role / retention) are present by
    construction — the write path rejects a row that lacks them — so the
    *interesting* signal is the relational completeness each activity reached:
    at least one system, recipient, data-subject category and data category, and
    whether transfers were recorded. Returns a JSON-serialisable dict.
    """
    distinct_ds = sorted({c for a in snapshot.activities for c in a.data_subject_categories})
    distinct_dc = sorted({c for a in snapshot.activities for c in a.data_categories})
    total_transfers = sum(len(a.transfers) for a in snapshot.activities)
    restricted = sum(1 for a in snapshot.activities for t in a.transfers if t["restricted"])

    per_activity: list[dict[str, Any]] = []
    for a in snapshot.activities:
        per_activity.append(
            {
                "name": a.name,
                "has_system": bool(a.system_names),
                "has_recipient": bool(a.vendor_names),
                "has_data_subject_category": bool(a.data_subject_categories),
                "has_data_category": bool(a.data_categories),
                "has_transfer": bool(a.transfers),
                "special_category_handled": (a.special_category and a.art9_condition is not None)
                or (not a.special_category and a.art9_condition is None),
            }
        )

    linkage_axes = ("has_system", "has_recipient", "has_data_subject_category", "has_data_category")
    fully_linked = sum(1 for p in per_activity if all(p[axis] for axis in linkage_axes))
    axis_fractions = {
        axis: (
            round(sum(1 for p in per_activity if p[axis]) / len(per_activity), 2)
            if per_activity
            else 0.0
        )
        for axis in linkage_axes
    }

    return {
        "counts": {
            "activities": len(snapshot.activities),
            "systems": len(snapshot.systems),
            "vendors": len(snapshot.vendors),
            "transfers": total_transfers,
            "restricted_transfers": restricted,
            "distinct_data_subject_categories": len(distinct_ds),
            "distinct_data_categories": len(distinct_dc),
        },
        "distinct_data_subject_categories": distinct_ds,
        "distinct_data_categories": distinct_dc,
        "activities_fully_linked": fully_linked,
        "linkage_axis_fractions": axis_fractions,
        "per_activity": per_activity,
        "integrity_ok": all(p["special_category_handled"] for p in per_activity),
    }


# --- test-only skill binding -------------------------------------------------


async def bind_area_skill(
    factory: async_sessionmaker[AsyncSession], practice_area_id: Any, skill_name: str
) -> None:
    """Bind a skill to a practice area in the (throwaway) test DB — test-only.

    Mirrors what a default-binding migration does (the 0056 pattern), so a
    scenario can activate a not-yet-shipped skill (e.g. ``ropa-population``)
    without a migration. The composition point exposes the area's bound subset
    intersected with the loaded registry, so the skill must also exist in the
    registry the run is given.

    Idempotent: the practice-area row is shared across parametrized tests in the
    session-scoped test DB, so re-binding the same (area, skill) is a no-op rather
    than a PK violation. Pair with :func:`unbind_area_skill` in a test's teardown
    to leave the shared area as it was found.
    """
    async with factory() as db:
        await db.execute(
            pg_insert(PracticeAreaSkill)
            .values(practice_area_id=practice_area_id, skill_name=skill_name)
            .on_conflict_do_nothing()
        )
        await db.commit()


async def unbind_area_skill(
    factory: async_sessionmaker[AsyncSession], practice_area_id: Any, skill_name: str
) -> None:
    """Remove a test-only skill binding (teardown for :func:`bind_area_skill`)."""
    async with factory() as db:
        await db.execute(
            delete(PracticeAreaSkill).where(
                PracticeAreaSkill.practice_area_id == practice_area_id,
                PracticeAreaSkill.skill_name == skill_name,
            )
        )
        await db.commit()


# --- dev-DB hygiene ----------------------------------------------------------


async def cleanup_register(
    factory: async_sessionmaker[AsyncSession], source_project_id: Any
) -> None:
    """Delete ONLY the register rows a run stamped with ``source_project_id``.

    The register is deployment-global with ``source_project_id`` ON DELETE SET
    NULL (provenance, not ownership), so the harness's project teardown would
    orphan these rows rather than remove them. Call this BEFORE
    ``SeededMatter.cleanup`` (which deletes the project and nulls the provenance).
    Deleting an activity cascades its transfers + all its link rows; categories
    created by this run (same provenance) are removed too — a category whose name
    pre-existed was reused under a different provenance and is left untouched.
    """
    async with factory() as db:
        await db.execute(
            delete(ProcessingActivity).where(
                ProcessingActivity.source_project_id == source_project_id
            )
        )
        await db.execute(delete(System).where(System.source_project_id == source_project_id))
        await db.execute(delete(Vendor).where(Vendor.source_project_id == source_project_id))
        await db.execute(
            delete(DataSubjectCategory).where(
                DataSubjectCategory.source_project_id == source_project_id
            )
        )
        await db.execute(
            delete(DataCategory).where(DataCategory.source_project_id == source_project_id)
        )
        await db.commit()
