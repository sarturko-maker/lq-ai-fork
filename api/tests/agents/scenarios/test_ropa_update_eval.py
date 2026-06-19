"""PRIV-8b — CI-gated proof of the update/maintenance eval substrate (no provider).

The live mixpanel→hotjar scenario (``test_ropa_update_scenario.py``) needs a real
gateway, so it self-skips in CI. This file proves the *substrate* that scenario
relies on, deterministically and key-free:

  * :func:`seed_ropa_register` plants a coherent pre-existing register (a
    "Product analytics" activity with a Mixpanel vendor + system linked);
  * :func:`snapshot_register` reads it back and now surfaces each row's ``retired``
    state (PRIV-8a soft-retire);
  * :func:`evaluate_swap` scores a swap against the *live* register view.

We simulate the swap the agent would perform — add Hotjar, link it, unlink and
soft-retire Mixpanel — directly through the ORM, so the scorer and the read-back
are exercised without a model in the loop. If the live model issues the right tool
calls, the snapshot it produces is read by exactly this code.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.ropa import (
    System,
    Vendor,
    processing_activity_systems,
    processing_activity_vendors,
)
from tests.agents.scenarios.harness import seed_matter
from tests.agents.scenarios.ropa_eval import (
    ActivityView,
    RegisterSnapshot,
    cleanup_register,
    evaluate_swap,
    seed_ropa_register,
    snapshot_register,
)
from tests.agents.scenarios.scenarios import FixtureDocument, build_document

_ACTIVITY = "Product analytics"
_OLD = "Mixpanel"
_NEW = "Hotjar"


def _note() -> FixtureDocument:
    """A trivial synthetic matter document (the eval tests never read it)."""
    return build_document(
        "Internal-note.txt",
        [(1, "Internal note: we migrated product analytics from Mixpanel to Hotjar.")],
    )


# --- pure evaluate_swap (no DB) ----------------------------------------------


def _vendor(name: str, *, retired: bool = False) -> dict[str, object]:
    return {
        "name": name,
        "vendor_role": "processor",
        "dpa_status": "in_place",
        "country": "US",
        "retired": retired,
    }


def _system(name: str, *, retired: bool = False) -> dict[str, object]:
    return {
        "name": name,
        "system_type": "analytics",
        "ai_usage": False,
        "retired": retired,
    }


def _activity(*, systems: list[str], vendors: list[str], retired: bool = False) -> ActivityView:
    return ActivityView(
        name=_ACTIVITY,
        purpose_excerpt="purpose",
        lawful_basis="legitimate_interests",
        controller_role="controller",
        retention="26 months",
        special_category=False,
        art9_condition=None,
        system_names=systems,
        vendor_names=vendors,
        data_subject_categories=[],
        data_categories=[],
        transfers=[],
        retired=retired,
    )


def test_evaluate_swap_coherent_when_old_retired_and_unlinked_new_linked() -> None:
    snap = RegisterSnapshot(
        activities=[_activity(systems=[_NEW], vendors=[_NEW])],
        systems=[_system(_NEW), _system(_OLD, retired=True)],
        vendors=[_vendor(_NEW), _vendor(_OLD, retired=True)],
    )
    verdict = evaluate_swap(snap, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
    assert verdict["coherent"] is True
    assert verdict["lists_both"] is False
    assert verdict["old_soft_retired"] is True  # audit trail preserved
    assert verdict["old_still_on_record"] is True
    assert verdict["recipient"]["new_live_visible"] is True
    assert verdict["recipient"]["old_live_visible"] is False


def test_evaluate_swap_coherent_when_old_retired_but_link_lingers() -> None:
    # Retire alone (no unlink): the API hides a retired row even if the join lingers,
    # so the live view is still coherent — the scorer must mirror that.
    snap = RegisterSnapshot(
        activities=[_activity(systems=[_NEW, _OLD], vendors=[_NEW, _OLD])],
        systems=[_system(_NEW), _system(_OLD, retired=True)],
        vendors=[_vendor(_NEW), _vendor(_OLD, retired=True)],
    )
    verdict = evaluate_swap(snap, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
    assert verdict["coherent"] is True
    assert verdict["lists_both"] is False
    assert verdict["recipient"]["old_linked"] is True
    assert verdict["recipient"]["old_live_visible"] is False


def test_evaluate_swap_flags_lists_both_when_old_left_live_and_linked() -> None:
    # The failure ADR-F023 names: agent added Hotjar but never removed Mixpanel.
    snap = RegisterSnapshot(
        activities=[_activity(systems=[_NEW, _OLD], vendors=[_NEW, _OLD])],
        systems=[_system(_NEW), _system(_OLD)],
        vendors=[_vendor(_NEW), _vendor(_OLD)],
    )
    verdict = evaluate_swap(snap, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
    assert verdict["coherent"] is False
    assert verdict["lists_both"] is True


def test_evaluate_swap_not_coherent_when_new_added_but_not_linked() -> None:
    # Half-done: Hotjar created but never linked to the activity.
    snap = RegisterSnapshot(
        activities=[_activity(systems=[], vendors=[])],
        systems=[_system(_NEW), _system(_OLD, retired=True)],
        vendors=[_vendor(_NEW), _vendor(_OLD, retired=True)],
    )
    verdict = evaluate_swap(snap, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
    assert verdict["coherent"] is False
    assert verdict["recipient"]["new_live_visible"] is False


def test_evaluate_swap_missing_activity_is_not_coherent() -> None:
    snap = RegisterSnapshot(activities=[], systems=[], vendors=[])
    verdict = evaluate_swap(snap, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
    assert verdict["found_activity"] is False
    assert verdict["coherent"] is False


def test_evaluate_swap_retiring_the_whole_activity_is_not_coherent() -> None:
    # The mistake the skill warns against: retire the *activity*, not the tool. A
    # retired activity is hidden from the live register, so this is NOT a coherent
    # swap even though Hotjar is otherwise linked + live.
    snap = RegisterSnapshot(
        activities=[_activity(systems=[_NEW], vendors=[_NEW], retired=True)],
        systems=[_system(_NEW), _system(_OLD, retired=True)],
        vendors=[_vendor(_NEW), _vendor(_OLD, retired=True)],
    )
    verdict = evaluate_swap(snap, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
    assert verdict["activity_retired"] is True
    assert verdict["coherent"] is False


def test_evaluate_swap_flags_duplicate_names() -> None:
    # A non-deterministic model can create a duplicate row (e.g. a retried propose).
    # We prefer the live row for live-visibility and surface the ambiguity.
    snap = RegisterSnapshot(
        activities=[_activity(systems=[_NEW], vendors=[_NEW])],
        systems=[_system(_NEW)],
        vendors=[_vendor(_NEW, retired=True), _vendor(_NEW), _vendor(_OLD, retired=True)],
    )
    verdict = evaluate_swap(snap, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
    assert verdict["duplicate_names"] == [_NEW]
    # The live (non-retired) Hotjar is preferred, so the swap still reads coherent.
    assert verdict["recipient"]["new_live_visible"] is True
    assert verdict["coherent"] is True


# --- seed + snapshot round-trip (DB-backed, no provider) ---------------------


async def _simulate_swap(
    factory: async_sessionmaker[AsyncSession],
    *,
    activity_id: object,
    old_vendor_id: object,
    old_system_id: object,
    source_project_id: object,
) -> None:
    """Perform the swap directly via ORM — what the agent's tool calls would do."""
    async with factory() as db:
        hotjar_vendor = Vendor(
            source_project_id=source_project_id,
            name=_NEW,
            vendor_role="processor",
            dpa_status="in_place",
            country="Ireland",
        )
        hotjar_system = System(
            source_project_id=source_project_id,
            name=_NEW,
            system_type="analytics",
            ai_usage=False,
        )
        db.add_all([hotjar_vendor, hotjar_system])
        await db.flush()
        await db.execute(
            processing_activity_vendors.insert().values(
                processing_activity_id=activity_id, vendor_id=hotjar_vendor.id
            )
        )
        await db.execute(
            processing_activity_systems.insert().values(
                processing_activity_id=activity_id, system_id=hotjar_system.id
            )
        )
        # Unlink the old tool from the activity.
        await db.execute(
            delete(processing_activity_vendors).where(
                processing_activity_vendors.c.processing_activity_id == activity_id,
                processing_activity_vendors.c.vendor_id == old_vendor_id,
            )
        )
        await db.execute(
            delete(processing_activity_systems).where(
                processing_activity_systems.c.processing_activity_id == activity_id,
                processing_activity_systems.c.system_id == old_system_id,
            )
        )
        # Soft-retire it company-wide (never destroyed — auditable, ADR-F023).
        now = datetime.now(UTC)
        old_vendor = await db.get(Vendor, old_vendor_id)
        old_system = await db.get(System, old_system_id)
        assert old_vendor is not None and old_system is not None
        old_vendor.retired_at = now
        old_system.retired_at = now
        await db.commit()


async def test_seed_snapshot_and_simulated_swap_round_trip(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await seed_matter(
        commit_factory,
        area_key="privacy",
        doc=_note(),
        matter_name="PRIV-8b eval round-trip",
    )
    try:
        seed = await seed_ropa_register(commit_factory, source_project_id=seeded.project_id)

        before = await snapshot_register(commit_factory, seeded.project_id)
        v_before = {v["name"]: v for v in before.vendors}
        activity_before = next(a for a in before.activities if a.name == _ACTIVITY)
        # Seeded register: Mixpanel present, live, and linked to the activity.
        assert _OLD in v_before and v_before[_OLD]["retired"] is False
        assert _OLD in activity_before.vendor_names
        assert _OLD in activity_before.system_names
        pre = evaluate_swap(before, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
        assert pre["coherent"] is False  # nothing swapped yet
        assert pre["recipient"]["old_live_visible"] is True

        await _simulate_swap(
            commit_factory,
            activity_id=seed.activity_id,
            old_vendor_id=seed.vendor_id,
            old_system_id=seed.system_id,
            source_project_id=seeded.project_id,
        )

        after = await snapshot_register(commit_factory, seeded.project_id)
        v_after = {v["name"]: v for v in after.vendors}
        activity_after = next(a for a in after.activities if a.name == _ACTIVITY)
        # Hotjar is now linked; Mixpanel is unlinked but kept on record, soft-retired.
        assert _NEW in activity_after.vendor_names and _NEW in activity_after.system_names
        assert _OLD not in activity_after.vendor_names
        assert v_after[_OLD]["retired"] is True
        assert v_after[_NEW]["retired"] is False

        verdict = evaluate_swap(after, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
        assert verdict["coherent"] is True
        assert verdict["lists_both"] is False
        assert verdict["old_soft_retired"] is True
        assert verdict["old_still_on_record"] is True
    finally:
        await cleanup_register(commit_factory, seeded.project_id)
        await seeded.cleanup()
