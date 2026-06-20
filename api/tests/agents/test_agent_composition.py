"""The composition point — F0-S4 review coverage.

``compose_and_execute_run`` is where the slice's headline wiring lives:
matter binding → guarded tools + matter prompt + privilege/tier onto
the model builder; no binding → blank workspace. The review found it
entirely untested (every endpoint test no-ops it) and found the
stranded-run regression (a composition failure left the run at
'running' forever, eating the flood brake). These tests drive the REAL
function through its injection seams — scripted model, test DB — no
monkeypatching.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.composition import MATTER_PROMPT, compose_and_execute_run, system_prompt_for
from app.agents.runner import SYSTEM_PROMPT
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.project import Project
from app.models.user import User
from app.security import hash_password
from tests.agents.fakes import (
    ScriptedToolCallingModel,
    final_message,
    tool_call_message,
)

pytestmark = pytest.mark.integration


@dataclass
class CapturingBuilder:
    """Stands in for build_gateway_chat_model; records the envelope kwargs."""

    model: BaseChatModel
    calls: list[dict[str, Any]] = field(default_factory=list)
    boom: Exception | None = None

    def __call__(self, **kwargs: Any) -> BaseChatModel:
        self.calls.append(kwargs)
        if self.boom is not None:
            raise self.boom
        return self.model


@dataclass
class _SkillRec:
    raw_yaml: str
    body: str


@dataclass
class _FakeSkillRegistry:
    """Minimal registry for the skills-activation wiring test (UX-B-3)."""

    records: dict[str, _SkillRec]

    def get(self, name: str) -> _SkillRec | None:
        return self.records.get(name)

    def names(self) -> list[str]:
        return sorted(self.records)


@dataclass
class CompositionEnv:
    factory: async_sessionmaker[AsyncSession]
    user_id: uuid.UUID
    project_id: uuid.UUID
    make_run: Callable[..., Awaitable[uuid.UUID]]


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def comp_env(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[CompositionEnv]:
    async with commit_factory() as db:
        user = User(
            email=f"agent-comp-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Agent Composition User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="Composition Matter",
            slug=f"comp-{uuid.uuid4().hex[:6]}",
            privileged=True,
            minimum_inference_tier=4,
        )
        db.add(project)
        await db.commit()
        user_id, project_id = user.id, project.id

    async def make_run(*, project_id_value: uuid.UUID | None) -> uuid.UUID:
        async with commit_factory() as db:
            thread = AgentThread(
                user_id=user_id, project_id=project_id_value, title="composition test"
            )
            db.add(thread)
            await db.flush()
            run = AgentRun(
                user_id=user_id,
                thread_id=thread.id,
                project_id=project_id_value,
                status="running",
                prompt="What is the liability cap?",
                model_alias="smart",
                max_steps=20,
            )
            db.add(run)
            await db.commit()
            return run.id

    yield CompositionEnv(
        factory=commit_factory,
        user_id=user_id,
        project_id=project_id,
        make_run=make_run,
    )

    async with commit_factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
        await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
        await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
        # The deployment-global ROPA register (ADR-F019) is shared across the
        # test DB, so the Privacy-matter test's rows must be cleaned by their
        # provenance BEFORE the project delete (which would only SET NULL the
        # source_project_id and orphan them into other tests' global view).
        from app.models.assessment import Assessment
        from app.models.ropa import ProcessingActivity, System

        # Assessments are deployment-global too (ADR-F019/F027) — clean by provenance
        # before the project delete (its SET NULL would orphan them into the shared
        # view and pollute test_assessment_tools' global list assertions).
        await db.execute(delete(Assessment).where(Assessment.source_project_id == project_id))
        await db.execute(
            delete(ProcessingActivity).where(ProcessingActivity.source_project_id == project_id)
        )
        await db.execute(delete(System).where(System.source_project_id == project_id))
        await db.execute(delete(Project).where(Project.id == project_id))
        await db.execute(delete(User).where(User.id == user_id))
        # Restore the shared seeded Commercial row: the tier-floor test
        # commits an UPDATE to it (commit_factory bypasses the per-test
        # rollback), which would otherwise pollute later tests (e.g.
        # test_practice_areas) in the full suite.
        from app.models.practice_area import PracticeArea

        await db.execute(
            PracticeArea.__table__.update()
            .where(PracticeArea.key == "commercial")
            .values(default_tier_floor=None)
        )
        await db.commit()


async def _run_row(env: CompositionEnv, run_id: uuid.UUID) -> AgentRun:
    async with env.factory() as db:
        return (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()


def test_system_prompt_assembly() -> None:
    assert system_prompt_for(None) == SYSTEM_PROMPT
    binding = MatterBinding(
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Acme MSA",
        privileged=False,
        minimum_inference_tier=None,
    )
    prompt = system_prompt_for(binding)
    assert prompt.startswith(SYSTEM_PROMPT)
    assert 'the matter "Acme MSA"' in prompt
    assert prompt.endswith(MATTER_PROMPT.format(name="Acme MSA"))


def test_system_prompt_appends_area_profile() -> None:
    """F1-S3: the area profile is appended after the matter addendum."""
    from app.agents.area_agent import AreaAgentSpec

    binding = MatterBinding(
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Acme MSA",
        privileged=False,
        minimum_inference_tier=None,
    )
    area = AreaAgentSpec(system_prompt_suffix="\n\nYou are the Commercial agent.")
    prompt = system_prompt_for(binding, area)
    assert 'the matter "Acme MSA"' in prompt
    assert prompt.endswith("You are the Commercial agent.")


async def test_bound_run_composes_matter_tools_and_privilege_envelope(
    comp_env: CompositionEnv,
) -> None:
    """The matter's tier floor + privilege reach the model builder, the
    scripted model can dispatch search_documents (so the tool WAS
    injected), and the run completes."""
    run_id = await comp_env.make_run(project_id_value=comp_env.project_id)
    builder = CapturingBuilder(
        model=ScriptedToolCallingModel(
            responses=[
                tool_call_message("search_documents", {"query": "liability"}),
                final_message("No documents attached; nothing to cite."),
            ]
        )
    )

    await compose_and_execute_run(
        run_id=run_id,
        model_builder=builder,
        session_factory_provider=lambda: comp_env.factory,
    )

    assert len(builder.calls) == 1
    envelope = builder.calls[0]
    assert envelope["project_minimum_inference_tier"] == 4
    assert envelope["privileged"] is True
    assert envelope["model_alias"] == "smart"

    run = await _run_row(comp_env, run_id)
    assert run.status == "completed"
    # The dispatch passed the guard chokepoint — the audit row proves the
    # injected tool really ran (matter has no documents; result is the
    # honest empty inventory).
    async with comp_env.factory() as db:
        rows = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "agent_run",
                        AuditLog.resource_id == str(run_id),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [r.details["tool"] for r in rows] == ["search_documents"]


async def test_area_filed_matter_combines_tier_floor_and_audits_area(
    comp_env: CompositionEnv,
) -> None:
    """F1-S3: a matter filed under an area with a tier floor sends the
    STRONGER of the matter floor (4) and the area floor (2) → 2, and the
    tool-call audit row carries the area id (per-area slicing). Sets the area
    floor explicitly (Commercial seeds no floor — see the migration)."""
    from app.models.practice_area import PracticeArea

    async with comp_env.factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        await db.execute(
            PracticeArea.__table__.update()
            .where(PracticeArea.id == area_id)
            .values(default_tier_floor=2)
        )
        await db.execute(
            Project.__table__.update()
            .where(Project.id == comp_env.project_id)
            .values(practice_area_id=area_id)
        )
        await db.commit()

    run_id = await comp_env.make_run(project_id_value=comp_env.project_id)
    builder = CapturingBuilder(
        model=ScriptedToolCallingModel(
            responses=[
                tool_call_message("search_documents", {"query": "cap"}),
                final_message("nothing to cite"),
            ]
        )
    )
    await compose_and_execute_run(
        run_id=run_id,
        model_builder=builder,
        session_factory_provider=lambda: comp_env.factory,
    )

    # min(matter floor 4, area floor 2) = 2.
    assert builder.calls[0]["project_minimum_inference_tier"] == 2

    async with comp_env.factory() as db:
        rows = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "agent_run",
                        AuditLog.resource_id == str(run_id),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert rows and all(r.practice_area_id == area_id for r in rows)


async def test_area_bound_skill_reaches_agent_system_prompt(
    comp_env: CompositionEnv,
) -> None:
    """UX-B-3 (ADR-F016): a skill bound to the matter's area, known to the
    injected registry, is exposed to the agent — its name lands in the
    SkillsMiddleware-augmented system prompt the model receives. Drives the
    REAL composition with the registry-backed backend; nothing is monkeypatched.
    Commercial carries default bindings (migration 0056), incl. ``nda-review``.
    """
    from app.models.practice_area import PracticeArea

    async with comp_env.factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        await db.execute(
            Project.__table__.update()
            .where(Project.id == comp_env.project_id)
            .values(practice_area_id=area_id)
        )
        await db.commit()

    run_id = await comp_env.make_run(project_id_value=comp_env.project_id)
    model = ScriptedToolCallingModel(responses=[final_message("done")])
    # The registry knows only nda-review; the area's other bound names
    # (msa-*, contract-qa) filter out — proving the subset filter (drift).
    registry = _FakeSkillRegistry(
        {
            "nda-review": _SkillRec(
                "name: nda-review\ndescription: Use when reviewing an NDA.", "# NDA"
            )
        }
    )
    await compose_and_execute_run(
        run_id=run_id,
        model_builder=CapturingBuilder(model=model),
        session_factory_provider=lambda: comp_env.factory,
        skill_registry_provider=lambda: registry,
    )

    assert model.seen_messages, "model was never called"
    prompt_text = "\n".join(
        str(getattr(m, "content", "")) for msgs in model.seen_messages for m in msgs
    )
    assert "nda-review" in prompt_text  # exposed via the backend
    assert "msa-review-saas" not in prompt_text  # not known to the registry → filtered


async def test_subagent_delegation_nests_steps_via_parent_step_id(
    comp_env: CompositionEnv,
) -> None:
    """UX-B-4 (ADR-F017): when the lead agent delegates via the deepagents
    ``task`` tool, the subagent's steps nest under that task step through
    ``parent_step_id`` — the delegation ancestry the runner records (F0-S7).

    Commercial carries the live ``document-researcher`` subagent (migration
    0057, applied to the test DB), so composing a matter under it builds the
    subagent for real. Driven by a scripted model: turn 1 calls ``task``, the
    subagent answers, the lead synthesises. No registry is injected — the
    subagent runs skill-less here (this probes ancestry, not skills) and the
    composition wiring strips its skill names, so deepagents never sees a bogus
    source. Deterministic; CI gate (the live qualification is separate)."""
    from app.models.agent_run import AgentRunStep
    from app.models.practice_area import PracticeArea
    from app.schemas.agent_runs import AgentRunStepKind

    async with comp_env.factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        await db.execute(
            Project.__table__.update()
            .where(Project.id == comp_env.project_id)
            .values(practice_area_id=area_id)
        )
        await db.commit()

    run_id = await comp_env.make_run(project_id_value=comp_env.project_id)
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "task",
                {
                    "description": "Investigate the liability cap across the matter's documents.",
                    "subagent_type": "document-researcher",
                },
            ),
            final_message(
                "Researcher findings: the cap is the fees paid in the preceding twelve "
                "months (Acme MSA, section 7)."
            ),
            final_message(
                "Based on the researcher's findings, the liability cap is 12 months' fees."
            ),
        ]
    )
    await compose_and_execute_run(
        run_id=run_id,
        model_builder=CapturingBuilder(model=model),
        session_factory_provider=lambda: comp_env.factory,
        # No registry → the subagent's declared skills are stripped (skill-less).
        skill_registry_provider=lambda: None,
    )

    run = await _run_row(comp_env, run_id)
    assert run.status == "completed", run.error

    async with comp_env.factory() as db:
        steps = (
            (
                await db.execute(
                    select(AgentRunStep)
                    .where(AgentRunStep.run_id == run_id)
                    .order_by(AgentRunStep.seq)
                )
            )
            .scalars()
            .all()
        )

    task_steps = [
        s for s in steps if s.kind == AgentRunStepKind.tool_call.value and s.name == "task"
    ]
    assert task_steps, (
        f"no `task` delegation step recorded; steps={[(s.kind, s.name) for s in steps]}"
    )
    task_ids = {s.id for s in task_steps}
    nested_under_task = [s for s in steps if s.parent_step_id in task_ids]
    assert nested_under_task, (
        "no step nested under the task delegation — parent_step_id ancestry missing; "
        f"parents={[(s.seq, s.parent_step_id) for s in steps]}"
    )


async def test_privacy_matter_grants_ropa_tools_and_validated_write_commits(
    comp_env: CompositionEnv,
) -> None:
    """PRIV-2 (ADR-F018): a matter filed under the Privacy area gets the ROPA
    tools (area-keyed selection at the composition point). A scripted model
    proposes a valid entry; the real loop dispatches the guarded, code-validated
    write and one processing-activity row is persisted to the matter."""
    from app.models.practice_area import PracticeArea
    from app.models.ropa import ProcessingActivity

    async with comp_env.factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "privacy"))
        ).scalar_one()
        await db.execute(
            Project.__table__.update()
            .where(Project.id == comp_env.project_id)
            .values(practice_area_id=area_id)
        )
        await db.commit()

    run_id = await comp_env.make_run(project_id_value=comp_env.project_id)
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "propose_processing_activity",
                {
                    "name": "Marketing emails",
                    "purpose": "Send opt-in newsletters",
                    "lawful_basis": "consent",
                    "controller_role": "controller",
                    "retention": "Until consent is withdrawn",
                },
            ),
            final_message("Recorded the marketing-emails processing activity."),
        ]
    )
    await compose_and_execute_run(
        run_id=run_id,
        model_builder=CapturingBuilder(model=model),
        session_factory_provider=lambda: comp_env.factory,
    )

    run = await _run_row(comp_env, run_id)
    assert run.status == "completed", run.error

    async with comp_env.factory() as db:
        rows = (
            (
                await db.execute(
                    select(ProcessingActivity).where(
                        # Deployment-global register (ADR-F019): the matter is
                        # provenance (source_project_id), not ownership.
                        ProcessingActivity.source_project_id == comp_env.project_id
                    )
                )
            )
            .scalars()
            .all()
        )
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "agent_run",
                        AuditLog.resource_id == str(run_id),
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].name == "Marketing emails"
    assert rows[0].lawful_basis == "consent"
    assert [r.details["tool"] for r in audit] == ["propose_processing_activity"]


async def test_privacy_matter_grants_assessment_tools_and_validated_write_commits(
    comp_env: CompositionEnv,
) -> None:
    """PRIV-A2 (ADR-F018/F027): the SAME Privacy matter also gets the assessment
    tools, granted at the composition point alongside the ROPA tools. A scripted
    model proposes a DPIA; the real loop dispatches the guarded, code-validated
    write and one assessment row is persisted to the matter (provenance only)."""
    from app.models.assessment import Assessment
    from app.models.practice_area import PracticeArea

    async with comp_env.factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "privacy"))
        ).scalar_one()
        await db.execute(
            Project.__table__.update()
            .where(Project.id == comp_env.project_id)
            .values(practice_area_id=area_id)
        )
        await db.commit()

    run_id = await comp_env.make_run(project_id_value=comp_env.project_id)
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "propose_assessment",
                {"type": "dpia", "title": "New analytics pipeline DPIA"},
            ),
            final_message("Opened the analytics-pipeline DPIA as a draft."),
        ]
    )
    await compose_and_execute_run(
        run_id=run_id,
        model_builder=CapturingBuilder(model=model),
        session_factory_provider=lambda: comp_env.factory,
    )

    run = await _run_row(comp_env, run_id)
    assert run.status == "completed", run.error

    async with comp_env.factory() as db:
        rows = (
            (
                await db.execute(
                    select(Assessment).where(Assessment.source_project_id == comp_env.project_id)
                )
            )
            .scalars()
            .all()
        )
        audit = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "agent_run",
                        AuditLog.resource_id == str(run_id),
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].type == "dpia"
    assert rows[0].title == "New analytics pipeline DPIA"
    assert rows[0].status == "draft"
    assert [r.details["tool"] for r in audit] == ["propose_assessment"]
    # The assessment row is cleaned by the comp_env fixture teardown (by provenance).


async def test_unbound_run_gets_no_matter_tools_and_no_envelope(
    comp_env: CompositionEnv,
) -> None:
    run_id = await comp_env.make_run(project_id_value=None)
    builder = CapturingBuilder(model=ScriptedToolCallingModel(responses=[final_message("done")]))

    await compose_and_execute_run(
        run_id=run_id,
        model_builder=builder,
        session_factory_provider=lambda: comp_env.factory,
    )

    envelope = builder.calls[0]
    assert envelope["project_minimum_inference_tier"] is None
    assert envelope["privileged"] is False
    run = await _run_row(comp_env, run_id)
    assert run.status == "completed"
    # No guarded dispatches happened (no tools to dispatch).
    async with comp_env.factory() as db:
        count = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "agent_run",
                        AuditLog.resource_id == str(run_id),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert count == []


async def test_archived_matter_executes_as_unbound(comp_env: CompositionEnv) -> None:
    """Binding facts are re-validated at execution time: archive the
    matter after the run row exists → no tools, no privilege envelope."""
    run_id = await comp_env.make_run(project_id_value=comp_env.project_id)
    async with comp_env.factory() as db:
        project = await db.get(Project, comp_env.project_id)
        assert project is not None
        project.archived_at = datetime.now(UTC)
        await db.commit()

    builder = CapturingBuilder(model=ScriptedToolCallingModel(responses=[final_message("ok")]))
    try:
        await compose_and_execute_run(
            run_id=run_id,
            model_builder=builder,
            session_factory_provider=lambda: comp_env.factory,
        )
    finally:
        async with comp_env.factory() as db:
            project = await db.get(Project, comp_env.project_id)
            assert project is not None
            project.archived_at = None
            await db.commit()

    envelope = builder.calls[0]
    assert envelope["project_minimum_inference_tier"] is None
    assert envelope["privileged"] is False
    assert (await _run_row(comp_env, run_id)).status == "completed"


async def test_follow_up_run_continues_the_thread(comp_env: CompositionEnv) -> None:
    """F0-S5 headline (ADR-F008): a second run on the SAME thread sees the
    first run's conversation — the checkpointer restores prior state and
    the new user message is appended, not a fresh context."""
    from langgraph.checkpoint.memory import InMemorySaver

    saver = InMemorySaver()
    thread_id: uuid.UUID
    async with comp_env.factory() as db:
        thread = AgentThread(user_id=comp_env.user_id, project_id=None, title="multi-turn")
        db.add(thread)
        await db.commit()
        thread_id = thread.id

    async def make_run_on_thread(prompt: str) -> uuid.UUID:
        async with comp_env.factory() as db:
            run = AgentRun(
                user_id=comp_env.user_id,
                thread_id=thread_id,
                project_id=None,
                status="running",
                prompt=prompt,
                model_alias="smart",
                max_steps=20,
            )
            db.add(run)
            await db.commit()
            return run.id

    first_model = ScriptedToolCallingModel(responses=[final_message("The cap is 12 months.")])
    run1 = await make_run_on_thread("What is the liability cap?")
    await compose_and_execute_run(
        run_id=run1,
        model_builder=CapturingBuilder(model=first_model),
        session_factory_provider=lambda: comp_env.factory,
        checkpointer_provider=lambda: saver,
    )
    assert (await _run_row(comp_env, run1)).status == "completed"

    second_model = ScriptedToolCallingModel(responses=[final_message("You asked about the cap.")])
    run2 = await make_run_on_thread("What did I just ask you?")
    await compose_and_execute_run(
        run_id=run2,
        model_builder=CapturingBuilder(model=second_model),
        session_factory_provider=lambda: comp_env.factory,
        checkpointer_provider=lambda: saver,
    )
    assert (await _run_row(comp_env, run2)).status == "completed"

    # The second model call carried the WHOLE conversation: both user
    # prompts and the first run's answer, in order.
    texts = [str(m.content) for m in second_model.seen_messages[0]]
    joined = "\n".join(texts)
    assert "What is the liability cap?" in joined
    assert "The cap is 12 months." in joined
    assert "What did I just ask you?" in joined
    assert joined.index("What is the liability cap?") < joined.index("What did I just ask you?")


async def test_runs_on_different_threads_share_nothing(comp_env: CompositionEnv) -> None:
    """Thread isolation (ADR-F008 / ADR-F004 runtime-verified isolation):
    a run on a DIFFERENT thread must not see another thread's history,
    even on the same checkpointer."""
    from langgraph.checkpoint.memory import InMemorySaver

    saver = InMemorySaver()

    async def run_on_new_thread(prompt: str, model: ScriptedToolCallingModel) -> None:
        async with comp_env.factory() as db:
            thread = AgentThread(user_id=comp_env.user_id, project_id=None, title=prompt)
            db.add(thread)
            await db.flush()
            run = AgentRun(
                user_id=comp_env.user_id,
                thread_id=thread.id,
                project_id=None,
                status="running",
                prompt=prompt,
                model_alias="smart",
                max_steps=20,
            )
            db.add(run)
            await db.commit()
            run_id = run.id
        await compose_and_execute_run(
            run_id=run_id,
            model_builder=CapturingBuilder(model=model),
            session_factory_provider=lambda: comp_env.factory,
            checkpointer_provider=lambda: saver,
        )

    model_a = ScriptedToolCallingModel(responses=[final_message("secret of thread A")])
    await run_on_new_thread("Thread A's private question", model_a)

    model_b = ScriptedToolCallingModel(responses=[final_message("fresh context")])
    await run_on_new_thread("Thread B's question", model_b)

    joined = "\n".join(str(m.content) for m in model_b.seen_messages[0])
    assert "Thread A" not in joined
    assert "secret of thread A" not in joined
    assert "Thread B's question" in joined


async def test_composition_failure_finalizes_run_as_failed(
    comp_env: CompositionEnv,
) -> None:
    """F0-S4 review (stranded-run regression): a model-builder failure
    must finalize the run — never strand it at 'running' where it eats
    the flood brake forever."""
    run_id = await comp_env.make_run(project_id_value=comp_env.project_id)
    builder = CapturingBuilder(
        model=ScriptedToolCallingModel(responses=[final_message("unreached")]),
        boom=RuntimeError("model construction exploded"),
    )

    await compose_and_execute_run(
        run_id=run_id,
        model_builder=builder,
        session_factory_provider=lambda: comp_env.factory,
    )

    run = await _run_row(comp_env, run_id)
    assert run.status == "failed"
    assert run.error is not None and "model construction exploded" in run.error
    assert "Traceback" not in run.error
    assert run.finished_at is not None
