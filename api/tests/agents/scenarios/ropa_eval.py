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

import uuid
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
    processing_activity_systems,
    processing_activity_vendors,
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
    # Soft-retire (PRIV-8a, ADR-F023): True once the activity has been retired.
    # Defaulted so the pure-helper unit tests (which build live activities) and the
    # population read-back are unaffected; the maintenance scenario reads it back.
    retired: bool = False

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
            "retired": self.retired,
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

    The read is deliberately RAW — it does NOT apply the live-only filter the API
    uses (``app.api.ropa._live_only``); every row, retired or live, is returned
    with a ``retired`` flag (PRIV-8b). That lets a maintenance test see both what
    the live register shows and what was soft-retired underneath; deriving the
    *live* view (a retired row is invisible) is :func:`evaluate_swap`'s job.
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
            {
                "name": s.name,
                "system_type": s.system_type,
                "ai_usage": s.ai_usage,
                "retired": s.retired_at is not None,
            }
            for s in systems
        ],
        vendors=[
            {
                "name": v.name,
                "vendor_role": v.vendor_role,
                "dpa_status": v.dpa_status,
                "country": v.country,
                "retired": v.retired_at is not None,
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
                        "retired": t.retired_at is not None,
                    }
                    for t in a.transfers
                ],
                retired=a.retired_at is not None,
            )
        )
    return snapshot


def _excerpt(value: str, limit: int) -> str:
    return value[:limit] + ("…" if len(value) > limit else "")


# --- register seeding (PRIV-8b: an update needs something to update) ---------


@dataclass
class SeededRegister:
    """The pre-existing register a maintenance/update scenario operates on.

    Carries the ids a caller needs to target the seeded rows directly (e.g. the
    ORM-simulated swap in the eval round-trip); the names are the function's own
    arguments, so callers already have them.
    """

    activity_id: uuid.UUID
    vendor_id: uuid.UUID
    system_id: uuid.UUID


async def seed_ropa_register(
    factory: async_sessionmaker[AsyncSession],
    *,
    source_project_id: Any,
    activity_name: str = "Product analytics",
    old_tool_name: str = "Mixpanel",
) -> SeededRegister:
    """Plant a small, coherent pre-existing register for an *update* scenario.

    The population test starts from an empty register and asks the agent to build
    it; an update test needs a register to *change*. This plants one processing
    activity with a recipient vendor and an analytics system (both named for the
    old tool) linked to it — the shape behind the maintainer's literal test
    ("we moved off Mixpanel, we use Hotjar now"). Every row is stamped with
    ``source_project_id`` (ADR-F019 provenance) so :func:`snapshot_register` reads
    it back and :func:`cleanup_register` removes it; the join rows and any later
    transfers cascade from the activity.
    """
    async with factory() as db:
        activity = ProcessingActivity(
            source_project_id=source_project_id,
            name=activity_name,
            purpose="Understand product usage to improve the service.",
            lawful_basis="legitimate_interests",
            controller_role="controller",
            retention="26 months from collection",
            special_category=False,
            art9_condition=None,
        )
        vendor = Vendor(
            source_project_id=source_project_id,
            name=old_tool_name,
            vendor_role="processor",
            dpa_status="in_place",
            country="United States",
        )
        system = System(
            source_project_id=source_project_id,
            name=old_tool_name,
            system_type="analytics",
            ai_usage=False,
        )
        db.add_all([activity, vendor, system])
        await db.flush()
        await db.execute(
            processing_activity_vendors.insert().values(
                processing_activity_id=activity.id, vendor_id=vendor.id
            )
        )
        await db.execute(
            processing_activity_systems.insert().values(
                processing_activity_id=activity.id, system_id=system.id
            )
        )
        await db.commit()
        return SeededRegister(
            activity_id=activity.id,
            vendor_id=vendor.id,
            system_id=system.id,
        )


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

    linkage_axes = (
        "has_system",
        "has_recipient",
        "has_data_subject_category",
        "has_data_category",
    )
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


def evaluate_swap(
    snapshot: RegisterSnapshot,
    *,
    activity_name: str,
    old_name: str,
    new_name: str,
) -> dict[str, Any]:
    """Score a vendor/system swap on one activity — pure, observations only (PRIV-8b).

    The maintainer's literal test: "we moved off Mixpanel, we use Hotjar now." A
    *coherent* swap leaves the **live** register showing the new tool linked to the
    activity and the old tool gone from it — while the old row is kept on record
    (soft-retired), so the change is auditable (ADR-F023). This scores exactly that
    across both the recipient (vendor) and system axes.

    The "live" view mirrors what the API serves (``_live_only`` / reads-exclude-
    retired): a row is visible on the activity iff it is still *linked* AND *not
    retired*. So a swap done by retiring the old tool, by unlinking it, or by both
    all count as coherent — what is rejected is leaving the old tool live AND linked
    alongside the new one (the "register lists both" failure ADR-F023 names).

    Two further fidelity guards: (a) a retired *activity* is itself hidden from the
    live register (the API hides retired leads), so retiring the whole activity —
    the mistake the ``ropa-maintenance`` skill warns against (retire the *tool*, not
    the activity) — is NOT coherent, even if the new tool is otherwise linked; and
    (b) vendor/system names are not unique, so a non-deterministic model can create a
    duplicate — when keying by name we prefer a live (non-retired) row so a retired
    duplicate never masks a live one, and we surface any ``duplicate_names``.
    """
    activity = next((a for a in snapshot.activities if a.name == activity_name), None)
    activity_retired = activity is not None and activity.retired

    def _by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            cur = out.get(r["name"])
            if cur is None or (cur["retired"] and not r["retired"]):
                out[r["name"]] = r
        return out

    def _dupes(rows: list[dict[str, Any]]) -> list[str]:
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["name"]] = counts.get(r["name"], 0) + 1
        return [n for n, c in counts.items() if c > 1]

    vendors_by_name = _by_name(snapshot.vendors)
    systems_by_name = _by_name(snapshot.systems)
    duplicate_names = sorted(set(_dupes(snapshot.vendors) + _dupes(snapshot.systems)))

    def _axis(linked_names: list[str], registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
        old_row = registry.get(old_name)
        new_row = registry.get(new_name)
        new_linked = new_name in linked_names
        old_linked = old_name in linked_names
        new_retired = bool(new_row and new_row["retired"])
        old_retired = bool(old_row and old_row["retired"])
        new_live_visible = new_linked and new_row is not None and not new_retired
        old_live_visible = old_linked and old_row is not None and not old_retired
        return {
            "new_present": new_row is not None,
            "old_present": old_row is not None,
            "new_linked": new_linked,
            "old_linked": old_linked,
            "new_retired": new_retired,
            "old_retired": old_retired,
            "new_live_visible": new_live_visible,
            "old_live_visible": old_live_visible,
            "coherent": new_live_visible and not old_live_visible,
            "both_visible": new_live_visible and old_live_visible,
        }

    recipient = _axis(activity.vendor_names if activity else [], vendors_by_name)
    system = _axis(activity.system_names if activity else [], systems_by_name)
    return {
        "activity": activity_name,
        "found_activity": activity is not None,
        # A retired activity is hidden from the live register, so retiring the whole
        # activity (instead of the tool) is not a coherent swap — it makes the record
        # vanish. Surfaced + gated into `coherent`.
        "activity_retired": activity_retired,
        "old": old_name,
        "new": new_name,
        "recipient": recipient,
        "system": system,
        # Headline: the LIVE register shows the new tool and not the old, on both axes,
        # and the activity itself is still live.
        "coherent": activity is not None
        and not activity_retired
        and recipient["coherent"]
        and system["coherent"],
        # The exact ADR-F023 failure mode — the register still lists BOTH (live + linked).
        "lists_both": recipient["both_visible"] or system["both_visible"],
        # Audit property: the old tool was soft-retired (kept on record), not destroyed.
        "old_soft_retired": recipient["old_retired"] or system["old_retired"],
        "old_still_on_record": recipient["old_present"] or system["old_present"],
        # Fidelity flag: same-named duplicate rows make the by-name view ambiguous.
        "duplicate_names": duplicate_names,
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
