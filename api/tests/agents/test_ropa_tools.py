"""ROPA agent tools — PRIV-2/PRIV-3: the code-validated write path over REAL rows.

Real Postgres, real ``ProcessingActivity`` / ``System`` inserts, real audit rows:
the ``build_ropa_tools`` closures are exercised exactly as the runner dispatches
them. The load-bearing assertions:

* propose → validate → COMMIT (activity AND system): a valid proposal writes
  exactly one row with the proposed values;
* propose → reject → RETRY: an invalid proposal is refused, NOTHING is written,
  the validation reason comes back as the tool result — never a silent write,
  never a silent fix (ADR-F018);
* the M:N link tool — links an activity to a system, rejects unknown ids, is
  idempotent;
* deployment-global scope (ADR-F019) — rows carry ``source_project_id`` as
  provenance, not ownership; the register is not matter-filtered;
* the guard chokepoint — every dispatch leaves one ``agent_run.tool_call`` audit
  row carrying counts/types/IDs, never the proposal's values;
* the end-to-end loop — a scripted model proposes a valid then an invalid entry;
  the run completes with exactly the valid row persisted and the rejection
  surfaced back to the model.

Like the matter-tool tests these COMMIT (the tools open their own sessions from
the factory), so they seed via a commit-capable factory and tear down explicitly
by ``source_project_id``.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.ropa_tools import ROPA_TOOL_NAMES, build_ropa_tools
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.ropa import ProcessingActivity, System, Vendor
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration

_VALID = {
    "name": "Payroll processing",
    "purpose": "Pay employees and meet tax obligations",
    "lawful_basis": "legal_obligation",
    "controller_role": "controller",
    "retention": "7 years after the tax year ends",
    "special_category": False,
    "art9_condition": None,
}

_VALID_SYSTEM = {
    "name": "Production database",
    "system_type": "database",
    "hosting_location": "London, UK",
}

_VALID_VENDOR = {
    "name": "Acme Payroll Ltd",
    "vendor_role": "processor",
    "dpa_status": "in_place",
    "country": "UK",
}


@dataclass
class RopaEnv:
    factory: async_sessionmaker[AsyncSession]
    user_id: uuid.UUID
    run_id: uuid.UUID
    project_id: uuid.UUID
    practice_area_id: uuid.UUID
    propose: Callable[..., Awaitable[str]]
    propose_system: Callable[..., Awaitable[str]]
    propose_vendor: Callable[..., Awaitable[str]]
    link: Callable[..., Awaitable[str]]
    link_vendor: Callable[..., Awaitable[str]]
    list_activities: Callable[..., Awaitable[str]]
    list_systems: Callable[..., Awaitable[str]]
    list_vendors: Callable[..., Awaitable[str]]


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def ropa_env(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[RopaEnv]:
    """One Privacy matter + a running run, with the ROPA tools built over it."""
    async with commit_factory() as db:
        privacy_area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "privacy"))
        ).scalar_one()

        user = User(
            email=f"ropa-{uuid.uuid4().hex[:8]}@example.com",
            display_name="ROPA User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()

        project = Project(
            owner_id=user.id,
            name="Programme — GDPR",
            slug=f"gdpr-{uuid.uuid4().hex[:6]}",
            practice_area_id=privacy_area_id,
        )
        db.add(project)
        await db.flush()

        thread = AgentThread(user_id=user.id, project_id=project.id, title="ropa tools tests")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user.id,
            thread_id=thread.id,
            project_id=project.id,
            status="running",
            prompt="Maintain the ROPA.",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()

        binding = MatterBinding(
            project_id=project.id,
            user_id=user.id,
            name="Programme — GDPR",
            privileged=False,
            minimum_inference_tier=None,
            practice_area_id=privacy_area_id,
        )
        tools = build_ropa_tools(commit_factory, run_id=run.id, binding=binding)
        by_name = {t.__name__: t for t in tools}
        env = RopaEnv(
            factory=commit_factory,
            user_id=user.id,
            run_id=run.id,
            project_id=project.id,
            practice_area_id=privacy_area_id,
            propose=by_name["propose_processing_activity"],
            propose_system=by_name["propose_system"],
            propose_vendor=by_name["propose_vendor"],
            link=by_name["link_processing_activity_to_system"],
            link_vendor=by_name["link_vendor_to_activity"],
            list_activities=by_name["list_processing_activities"],
            list_systems=by_name["list_systems"],
            list_vendors=by_name["list_vendors"],
        )

    yield env

    async with commit_factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == env.user_id))
        # Join rows cascade when the activity/system is deleted.
        await db.execute(
            delete(ProcessingActivity).where(ProcessingActivity.source_project_id == env.project_id)
        )
        await db.execute(delete(System).where(System.source_project_id == env.project_id))
        await db.execute(delete(Vendor).where(Vendor.source_project_id == env.project_id))
        await db.execute(delete(AgentRun).where(AgentRun.user_id == env.user_id))
        await db.execute(delete(AgentThread).where(AgentThread.user_id == env.user_id))
        await db.execute(delete(Project).where(Project.id == env.project_id))
        await db.execute(delete(User).where(User.id == env.user_id))
        await db.commit()


async def _activities(env: RopaEnv) -> list[ProcessingActivity]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(ProcessingActivity)
                .where(ProcessingActivity.source_project_id == env.project_id)
                .order_by(ProcessingActivity.created_at.asc())
            )
        ).scalars()
        return list(rows)


async def _systems(env: RopaEnv) -> list[System]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(System)
                .where(System.source_project_id == env.project_id)
                .order_by(System.created_at.asc())
            )
        ).scalars()
        return list(rows)


async def _vendors(env: RopaEnv) -> list[Vendor]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(Vendor)
                .where(Vendor.source_project_id == env.project_id)
                .order_by(Vendor.created_at.asc())
            )
        ).scalars()
        return list(rows)


async def _audit_rows(env: RopaEnv) -> list[AuditLog]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.resource_type == "agent_run",
                    AuditLog.resource_id == str(env.run_id),
                )
                .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
            )
        ).scalars()
        return list(rows)


# ---------------------------------------------------------------------------
# propose_processing_activity — validate then commit
# ---------------------------------------------------------------------------


async def test_valid_proposal_commits_one_row(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose(**_VALID)
    assert "Recorded processing activity" in result
    assert "Payroll processing" in result

    rows = await _activities(ropa_env)
    assert len(rows) == 1
    row = rows[0]
    # Provenance, not ownership (ADR-F019).
    assert row.source_project_id == ropa_env.project_id
    assert row.name == "Payroll processing"
    assert row.lawful_basis == "legal_obligation"
    assert row.controller_role == "controller"
    assert row.retention == "7 years after the tax year ends"
    assert row.special_category is False
    assert row.art9_condition is None


async def test_valid_special_category_proposal_commits(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose(
        name="Occupational health records",
        purpose="Manage workplace health assessments",
        lawful_basis="legal_obligation",
        controller_role="controller",
        retention="Duration of employment plus 6 years",
        special_category=True,
        art9_condition="health_or_social_care",
    )
    assert "Recorded processing activity" in result
    rows = await _activities(ropa_env)
    assert len(rows) == 1
    assert rows[0].special_category is True
    assert rows[0].art9_condition == "health_or_social_care"


async def test_off_enum_lawful_basis_is_rejected_and_nothing_written(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose(**{**_VALID, "lawful_basis": "because_we_want_to"})
    assert "rejected" in result.lower()
    assert "lawful_basis" in result
    assert await _activities(ropa_env) == []


async def test_blank_retention_is_rejected_and_nothing_written(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose(**{**_VALID, "retention": "   "})
    assert "rejected" in result.lower()
    assert "retention" in result
    assert await _activities(ropa_env) == []


async def test_special_category_without_art9_is_rejected(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose(**{**_VALID, "special_category": True, "art9_condition": None})
    assert "rejected" in result.lower()
    assert "Article 9" in result
    assert await _activities(ropa_env) == []


async def test_art9_without_special_category_is_rejected(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose(
        **{**_VALID, "special_category": False, "art9_condition": "explicit_consent"}
    )
    assert "rejected" in result.lower()
    assert "art9_condition" in result
    assert await _activities(ropa_env) == []


# ---------------------------------------------------------------------------
# propose_system — the second code-validated entity (PRIV-3)
# ---------------------------------------------------------------------------


async def test_valid_system_proposal_commits(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose_system(**_VALID_SYSTEM)
    assert "Recorded system" in result
    assert "Production database" in result
    rows = await _systems(ropa_env)
    assert len(rows) == 1
    assert rows[0].name == "Production database"
    assert rows[0].system_type == "database"
    assert rows[0].hosting_location == "London, UK"
    assert rows[0].source_project_id == ropa_env.project_id


async def test_off_enum_system_type_is_rejected_and_nothing_written(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose_system(name="Mystery box", system_type="quantum_orb")
    assert "rejected" in result.lower()
    assert "system_type" in result
    assert await _systems(ropa_env) == []


# ---------------------------------------------------------------------------
# propose_vendor — the recipient entity (PRIV-5a)
# ---------------------------------------------------------------------------


async def test_valid_vendor_proposal_commits(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose_vendor(**_VALID_VENDOR)
    assert "Recorded vendor" in result
    assert "Acme Payroll Ltd" in result
    rows = await _vendors(ropa_env)
    assert len(rows) == 1
    assert rows[0].name == "Acme Payroll Ltd"
    assert rows[0].vendor_role == "processor"
    assert rows[0].dpa_status == "in_place"
    assert rows[0].country == "UK"
    assert rows[0].source_project_id == ropa_env.project_id


async def test_off_enum_vendor_role_is_rejected_and_nothing_written(ropa_env: RopaEnv) -> None:
    result = await ropa_env.propose_vendor(name="X", vendor_role="overlord", dpa_status="none")
    assert "rejected" in result.lower()
    assert "vendor_role" in result
    assert await _vendors(ropa_env) == []


# ---------------------------------------------------------------------------
# link_processing_activity_to_system — the M:N data-flow link
# ---------------------------------------------------------------------------


async def test_link_activity_to_system(ropa_env: RopaEnv) -> None:
    await ropa_env.propose(**_VALID)
    await ropa_env.propose_system(**_VALID_SYSTEM)
    activity = (await _activities(ropa_env))[0]
    system = (await _systems(ropa_env))[0]

    result = await ropa_env.link(processing_activity_id=str(activity.id), system_id=str(system.id))
    assert "Linked processing activity" in result

    # The link is visible through the relationship.
    from sqlalchemy.orm import selectinload

    async with ropa_env.factory() as db:
        loaded = (
            await db.execute(
                select(ProcessingActivity)
                .options(selectinload(ProcessingActivity.systems))
                .where(ProcessingActivity.id == activity.id)
            )
        ).scalar_one()
        assert [s.id for s in loaded.systems] == [system.id]

    # Idempotent.
    again = await ropa_env.link(processing_activity_id=str(activity.id), system_id=str(system.id))
    assert "already linked" in again


async def test_link_unknown_ids_is_rejected(ropa_env: RopaEnv) -> None:
    result = await ropa_env.link(
        processing_activity_id=str(uuid.uuid4()), system_id=str(uuid.uuid4())
    )
    assert "refused" in result.lower()
    assert "no processing activity" in result
    assert "no system" in result


async def test_link_non_uuid_is_rejected(ropa_env: RopaEnv) -> None:
    result = await ropa_env.link(processing_activity_id="not-a-uuid", system_id="also-not")
    assert "refused" in result.lower()


# ---------------------------------------------------------------------------
# link_vendor_to_activity — the recipient link (PRIV-5a)
# ---------------------------------------------------------------------------


async def test_link_activity_to_vendor(ropa_env: RopaEnv) -> None:
    await ropa_env.propose(**_VALID)
    await ropa_env.propose_vendor(**_VALID_VENDOR)
    activity = (await _activities(ropa_env))[0]
    vendor = (await _vendors(ropa_env))[0]

    result = await ropa_env.link_vendor(
        processing_activity_id=str(activity.id), vendor_id=str(vendor.id)
    )
    assert "Linked processing activity" in result

    from sqlalchemy.orm import selectinload

    async with ropa_env.factory() as db:
        loaded = (
            await db.execute(
                select(ProcessingActivity)
                .options(selectinload(ProcessingActivity.vendors))
                .where(ProcessingActivity.id == activity.id)
            )
        ).scalar_one()
        assert [v.id for v in loaded.vendors] == [vendor.id]

    # Idempotent.
    again = await ropa_env.link_vendor(
        processing_activity_id=str(activity.id), vendor_id=str(vendor.id)
    )
    assert "already discloses" in again


async def test_link_vendor_unknown_ids_is_rejected(ropa_env: RopaEnv) -> None:
    result = await ropa_env.link_vendor(
        processing_activity_id=str(uuid.uuid4()), vendor_id=str(uuid.uuid4())
    )
    assert "refused" in result.lower()
    assert "no processing activity" in result
    assert "no vendor" in result


# ---------------------------------------------------------------------------
# list tools
# ---------------------------------------------------------------------------


async def test_list_is_empty_then_reflects_proposals(ropa_env: RopaEnv) -> None:
    empty = await ropa_env.list_activities()
    assert "no processing activities yet" in empty

    await ropa_env.propose(**_VALID)
    listed = await ropa_env.list_activities()
    assert "1 processing activity" in listed
    assert "Payroll processing" in listed
    assert "legal_obligation" in listed
    assert "7 years after the tax year ends" in listed


async def test_list_systems_is_empty_then_reflects_proposals(ropa_env: RopaEnv) -> None:
    empty = await ropa_env.list_systems()
    assert "no systems yet" in empty

    await ropa_env.propose_system(**_VALID_SYSTEM)
    listed = await ropa_env.list_systems()
    assert "1 system" in listed
    assert "Production database" in listed
    assert "database" in listed


async def test_list_vendors_is_empty_then_reflects_proposals(ropa_env: RopaEnv) -> None:
    empty = await ropa_env.list_vendors()
    assert "no vendors" in empty

    await ropa_env.propose_vendor(**_VALID_VENDOR)
    listed = await ropa_env.list_vendors()
    assert "1 vendor" in listed
    assert "Acme Payroll Ltd" in listed
    assert "processor" in listed
    assert "in_place" in listed


# ---------------------------------------------------------------------------
# The guard chokepoint + the model-facing surface
# ---------------------------------------------------------------------------


async def test_each_dispatch_writes_one_audit_row_without_values(ropa_env: RopaEnv) -> None:
    await ropa_env.propose(**_VALID)
    await ropa_env.list_activities()

    rows = await _audit_rows(ropa_env)
    assert len(rows) == 2
    assert {r.details["tool"] for r in rows} == {
        "propose_processing_activity",
        "list_processing_activities",
    }
    for row in rows:
        assert row.action == "agent_run.tool_call"
        assert row.user_id == ropa_env.user_id
        assert row.practice_area_id == ropa_env.practice_area_id
        assert row.details["outcome"] == "success"
        # Counts/types/IDs only — never the proposal's purpose/retention text.
        serialized = str(row.details)
        assert "Payroll" not in serialized
        assert "tax year" not in serialized


async def test_rejected_proposal_still_audits_the_dispatch(ropa_env: RopaEnv) -> None:
    # A code-rejected write is a successful tool DISPATCH that returned a
    # rejection string — the dispatch is audited; no row is written.
    await ropa_env.propose(**{**_VALID, "lawful_basis": "nonsense"})
    rows = await _audit_rows(ropa_env)
    assert len(rows) == 1
    assert rows[0].details["tool"] == "propose_processing_activity"
    assert rows[0].details["outcome"] == "success"
    assert await _activities(ropa_env) == []


def test_tool_names_cover_the_built_tools(ropa_env: RopaEnv) -> None:
    assert {
        "propose_processing_activity",
        "propose_system",
        "propose_vendor",
        "link_processing_activity_to_system",
        "link_vendor_to_activity",
        "list_processing_activities",
        "list_systems",
        "list_vendors",
    } == ROPA_TOOL_NAMES


async def test_tools_expose_model_facing_schema(ropa_env: RopaEnv) -> None:
    """The model-visible surface: A-class content args only (ADR-F004) — no
    project_id / user_id leaks into any signature."""
    assert list(inspect.signature(ropa_env.propose).parameters) == [
        "name",
        "purpose",
        "lawful_basis",
        "controller_role",
        "retention",
        "special_category",
        "art9_condition",
    ]
    assert list(inspect.signature(ropa_env.propose_system).parameters) == [
        "name",
        "system_type",
        "description",
        "owner",
        "hosting_location",
        "retention",
        "security_measures",
        "ai_usage",
    ]
    assert list(inspect.signature(ropa_env.propose_vendor).parameters) == [
        "name",
        "vendor_role",
        "dpa_status",
        "description",
        "country",
    ]
    assert list(inspect.signature(ropa_env.link).parameters) == [
        "processing_activity_id",
        "system_id",
    ]
    assert list(inspect.signature(ropa_env.link_vendor).parameters) == [
        "processing_activity_id",
        "vendor_id",
    ]
    assert list(inspect.signature(ropa_env.list_activities).parameters) == []
    assert list(inspect.signature(ropa_env.list_systems).parameters) == []
    assert list(inspect.signature(ropa_env.list_vendors).parameters) == []
    for tool in (
        ropa_env.propose,
        ropa_env.propose_system,
        ropa_env.propose_vendor,
        ropa_env.link,
        ropa_env.link_vendor,
        ropa_env.list_activities,
        ropa_env.list_systems,
        ropa_env.list_vendors,
    ):
        assert inspect.iscoroutinefunction(tool)


# ---------------------------------------------------------------------------
# End to end: the REAL deepagents loop drives propose (valid then rejected)
# ---------------------------------------------------------------------------


async def test_real_loop_proposes_valid_then_rejects_invalid(ropa_env: RopaEnv) -> None:
    """A scripted model proposes a valid entry, then an invalid one; the run
    completes with exactly the valid row persisted and the rejection surfaced
    back to the model as a tool result."""
    from app.agents.runner import execute_agent_run
    from app.models.agent_run import AgentRunStep
    from tests.agents.fakes import (
        ScriptedToolCallingModel,
        final_message,
        tool_call_message,
    )

    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("propose_processing_activity", dict(_VALID)),
            tool_call_message(
                "propose_processing_activity",
                # special-category without an Article 9(2) condition → rejected
                {**_VALID, "name": "Health data", "special_category": True},
            ),
            final_message("Recorded payroll; the health-data entry was rejected pending Art 9."),
        ]
    )

    await execute_agent_run(
        ropa_env.run_id,
        ropa_env.factory,
        tools=[
            ropa_env.propose,
            ropa_env.propose_system,
            ropa_env.link,
            ropa_env.list_activities,
            ropa_env.list_systems,
        ],
        model=model,
    )

    async with ropa_env.factory() as db:
        run = (
            await db.execute(select(AgentRun).where(AgentRun.id == ropa_env.run_id))
        ).scalar_one()
        steps = (
            (
                await db.execute(
                    select(AgentRunStep)
                    .where(AgentRunStep.run_id == ropa_env.run_id)
                    .order_by(AgentRunStep.seq.asc())
                )
            )
            .scalars()
            .all()
        )

    assert run.status == "completed"

    # Exactly the valid row is persisted; the invalid proposal wrote nothing.
    rows = await _activities(ropa_env)
    assert len(rows) == 1
    assert rows[0].name == "Payroll processing"

    # Both proposals dispatched; one tool_result recorded the commit, the other
    # the rejection — the model saw both.
    results = [s.summary or "" for s in steps if s.kind == "tool_result"]
    assert any("Recorded processing activity" in r for r in results)
    assert any("rejected" in r.lower() for r in results)
