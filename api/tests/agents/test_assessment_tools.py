"""Assessment agent tools — PRIV-A2: the code-validated write path over REAL rows.

Real Postgres, real ``Assessment`` / ``Risk`` inserts, real audit rows: the
``build_assessment_tools`` closures are exercised exactly as the runner dispatches
them. The load-bearing assertions mirror ``test_ropa_tools`` for the new track:

* propose → validate → COMMIT: a valid proposal writes exactly one row;
* propose → reject → RETRY: an invalid proposal is refused, NOTHING is written,
  the reason comes back as the tool result — never a silent write/fix (ADR-F018);
* the HEADLINE cross-row invariant (ADR-F027): a DPIA — or any ``high``-rated
  assessment — cannot be ``completed`` unless ≥1 risk carries a documented
  mitigation (both directions);
* the M:N link tool — links an assessment to a ROPA activity, rejects unknown ids
  and retired activities, is idempotent;
* deployment-global scope (ADR-F019) — rows carry ``source_project_id`` as
  provenance, not ownership;
* the guard chokepoint — every dispatch leaves one ``agent_run.tool_call`` audit
  row carrying counts/types/IDs, never the proposal's values;
* the model-facing surface — A-class content args only, no B-class leakage;
* the end-to-end loop — a scripted model drives add_risk -> complete (the parent
  is seeded out-of-band so the fake can echo the id back; the model-driven
  propose path is covered by the composition test).

Like the ROPA tool tests these COMMIT (the tools open their own sessions from the
factory), so they seed via a commit-capable factory and tear down explicitly by
``source_project_id``.
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

from app.agents.assessment_tools import ASSESSMENT_TOOL_NAMES, build_assessment_tools
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.assessment import Assessment, Risk
from app.models.audit import AuditLog
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.ropa import ProcessingActivity
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration


@dataclass
class AssessmentEnv:
    factory: async_sessionmaker[AsyncSession]
    user_id: uuid.UUID
    run_id: uuid.UUID
    project_id: uuid.UUID
    practice_area_id: uuid.UUID
    propose: Callable[..., Awaitable[str]]
    add_risk: Callable[..., Awaitable[str]]
    complete: Callable[..., Awaitable[str]]
    link: Callable[..., Awaitable[str]]
    list_assessments: Callable[..., Awaitable[str]]
    built_tool_names: frozenset[str]


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def env(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AssessmentEnv]:
    """One Privacy matter + a running run, with the assessment tools built over it."""
    async with commit_factory() as db:
        privacy_area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "privacy"))
        ).scalar_one()

        user = User(
            email=f"assess-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Assessment User",
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

        thread = AgentThread(user_id=user.id, project_id=project.id, title="assessment tools tests")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user.id,
            thread_id=thread.id,
            project_id=project.id,
            status="running",
            prompt="Run the DPIA.",
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
        tools = build_assessment_tools(commit_factory, run_id=run.id, binding=binding)
        by_name = {t.__name__: t for t in tools}
        env = AssessmentEnv(
            factory=commit_factory,
            user_id=user.id,
            run_id=run.id,
            project_id=project.id,
            practice_area_id=privacy_area_id,
            propose=by_name["propose_assessment"],
            add_risk=by_name["add_risk"],
            complete=by_name["complete_assessment"],
            link=by_name["link_assessment_to_activity"],
            list_assessments=by_name["list_assessments"],
            built_tool_names=frozenset(t.__name__ for t in tools),
        )

    yield env

    async with commit_factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == env.user_id))
        # Risks + link rows cascade with their parent assessment; delete assessments
        # by provenance, then any activity this test created (its link rows cascade).
        await db.execute(delete(Assessment).where(Assessment.source_project_id == env.project_id))
        await db.execute(
            delete(ProcessingActivity).where(ProcessingActivity.source_project_id == env.project_id)
        )
        await db.execute(delete(AgentRun).where(AgentRun.user_id == env.user_id))
        await db.execute(delete(AgentThread).where(AgentThread.user_id == env.user_id))
        await db.execute(delete(Project).where(Project.id == env.project_id))
        await db.execute(delete(User).where(User.id == env.user_id))
        await db.commit()


async def _assessments(env: AssessmentEnv) -> list[Assessment]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(Assessment)
                .where(Assessment.source_project_id == env.project_id)
                .order_by(Assessment.created_at.asc())
            )
        ).scalars()
        return list(rows)


async def _risks(env: AssessmentEnv, assessment_id: uuid.UUID) -> list[Risk]:
    async with env.factory() as db:
        rows = (await db.execute(select(Risk).where(Risk.assessment_id == assessment_id))).scalars()
        return list(rows)


async def _audit_rows(env: AssessmentEnv) -> list[AuditLog]:
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


async def _make_activity(env: AssessmentEnv, *, retired: bool = False) -> ProcessingActivity:
    from datetime import UTC, datetime

    async with env.factory() as db:
        activity = ProcessingActivity(
            source_project_id=env.project_id,
            name="Marketing analytics",
            purpose="Analyse campaign performance.",
            lawful_basis="legitimate_interests",
            controller_role="controller",
            retention="2 years",
            special_category=False,
            retired_at=datetime.now(UTC) if retired else None,
        )
        db.add(activity)
        await db.commit()
        return activity


# ---------------------------------------------------------------------------
# propose_assessment — validate then commit
# ---------------------------------------------------------------------------


async def test_valid_draft_proposal_commits_one_row(env: AssessmentEnv) -> None:
    result = await env.propose(type="dpia", title="Analytics pipeline DPIA")
    assert "Recorded DPIA assessment" in result
    assert "Analytics pipeline DPIA" in result

    rows = await _assessments(env)
    assert len(rows) == 1
    row = rows[0]
    assert row.source_project_id == env.project_id  # provenance, not ownership
    assert row.type == "dpia"
    assert row.title == "Analytics pipeline DPIA"
    assert row.status == "draft"
    assert row.risk_rating is None


async def test_off_enum_type_is_rejected_and_nothing_written(env: AssessmentEnv) -> None:
    result = await env.propose(type="vibes_assessment", title="X")
    assert "rejected" in result.lower()
    assert "type" in result
    assert await _assessments(env) == []


async def test_blank_title_is_rejected_and_nothing_written(env: AssessmentEnv) -> None:
    result = await env.propose(type="pia", title="   ")
    assert "rejected" in result.lower()
    assert "title" in result
    assert await _assessments(env) == []


async def test_completed_without_rating_is_rejected(env: AssessmentEnv) -> None:
    # Within-row half of the headline rule, at the schema boundary.
    result = await env.propose(type="pia", title="Closed too soon", status="completed")
    assert "rejected" in result.lower()
    assert "risk_rating" in result
    assert await _assessments(env) == []


async def test_create_completed_low_risk_pia_commits(env: AssessmentEnv) -> None:
    # A low-risk, non-DPIA assessment may be created already-completed in one shot
    # (the cross-row rule does not bite a low/medium non-DPIA).
    result = await env.propose(
        type="pia", title="Low-risk screening", status="completed", risk_rating="low"
    )
    assert "Recorded PIA assessment" in result
    rows = await _assessments(env)
    assert len(rows) == 1 and rows[0].status == "completed" and rows[0].risk_rating == "low"


async def test_create_completed_dpia_is_rejected(env: AssessmentEnv) -> None:
    # A DPIA created already-completed has no documented risk → refused (ADR-F027).
    result = await env.propose(
        type="dpia", title="Premature DPIA", status="completed", risk_rating="high"
    )
    assert "cannot be created already-completed" in result.lower()
    assert await _assessments(env) == []


# ---------------------------------------------------------------------------
# add_risk
# ---------------------------------------------------------------------------


async def test_valid_risk_commits(env: AssessmentEnv) -> None:
    await env.propose(type="dpia", title="DPIA")
    assessment = (await _assessments(env))[0]
    result = await env.add_risk(
        assessment_id=str(assessment.id),
        description="Re-identification of pseudonymised analytics records.",
        likelihood="medium",
        impact="high",
        mitigation="Hash user_id at ingest; drop raw IPs after 24h.",
        owner="Data Eng",
    )
    assert "Added a medium/high" in result
    risks = await _risks(env, assessment.id)
    assert len(risks) == 1
    assert risks[0].impact == "high"
    assert risks[0].mitigation == "Hash user_id at ingest; drop raw IPs after 24h."


async def test_off_enum_likelihood_is_rejected_and_nothing_written(env: AssessmentEnv) -> None:
    await env.propose(type="dpia", title="DPIA")
    assessment = (await _assessments(env))[0]
    result = await env.add_risk(
        assessment_id=str(assessment.id),
        description="A risk",
        likelihood="catastrophic",
        impact="high",
    )
    assert "rejected" in result.lower()
    assert "likelihood" in result
    assert await _risks(env, assessment.id) == []


async def test_add_risk_unknown_assessment_is_refused(env: AssessmentEnv) -> None:
    result = await env.add_risk(
        assessment_id=str(uuid.uuid4()),
        description="A risk",
        likelihood="low",
        impact="low",
    )
    assert "refused" in result.lower()
    assert "no assessment" in result


async def test_add_risk_non_uuid_is_refused(env: AssessmentEnv) -> None:
    result = await env.add_risk(
        assessment_id="not-a-uuid", description="A risk", likelihood="low", impact="low"
    )
    assert "refused" in result.lower()


# ---------------------------------------------------------------------------
# complete_assessment — the HEADLINE cross-row invariant (ADR-F027)
# ---------------------------------------------------------------------------


async def test_complete_low_risk_pia_without_any_risk_succeeds(env: AssessmentEnv) -> None:
    await env.propose(type="pia", title="PIA")
    assessment = (await _assessments(env))[0]
    result = await env.complete(assessment_id=str(assessment.id), risk_rating="low")
    assert "Completed PIA assessment" in result
    rows = await _assessments(env)
    assert rows[0].status == "completed" and rows[0].risk_rating == "low"


async def test_complete_dpia_without_mitigated_risk_is_refused(env: AssessmentEnv) -> None:
    # HEADLINE (forward): a DPIA cannot be completed with no documented mitigation —
    # even with an unmitigated risk on file, and even rated low.
    await env.propose(type="dpia", title="DPIA")
    assessment = (await _assessments(env))[0]
    await env.add_risk(
        assessment_id=str(assessment.id),
        description="Unmitigated exposure risk.",
        likelihood="high",
        impact="high",
    )
    result = await env.complete(assessment_id=str(assessment.id), risk_rating="low")
    assert "refused" in result.lower()
    assert "mitigation" in result.lower()
    # Not completed — still a draft.
    assert (await _assessments(env))[0].status == "draft"


async def test_complete_dpia_with_mitigated_risk_succeeds(env: AssessmentEnv) -> None:
    # HEADLINE (satisfied): add a risk carrying a non-blank mitigation, then complete.
    await env.propose(type="dpia", title="DPIA")
    assessment = (await _assessments(env))[0]
    await env.add_risk(
        assessment_id=str(assessment.id),
        description="Re-identification risk.",
        likelihood="medium",
        impact="high",
        mitigation="Pseudonymise at ingest; 30-day retention; DPO review at 6 months.",
    )
    result = await env.complete(assessment_id=str(assessment.id), risk_rating="high")
    assert "Completed DPIA assessment" in result
    rows = await _assessments(env)
    assert rows[0].status == "completed" and rows[0].risk_rating == "high"


async def test_complete_high_rating_without_mitigation_is_refused(env: AssessmentEnv) -> None:
    # HEADLINE also bites a non-DPIA rated high.
    await env.propose(type="pia", title="High-risk PIA")
    assessment = (await _assessments(env))[0]
    await env.add_risk(
        assessment_id=str(assessment.id),
        description="Serious risk, no mitigation yet.",
        likelihood="high",
        impact="high",
    )
    result = await env.complete(assessment_id=str(assessment.id), risk_rating="high")
    assert "refused" in result.lower()
    assert (await _assessments(env))[0].status == "draft"


async def test_complete_without_rating_anywhere_is_refused(env: AssessmentEnv) -> None:
    await env.propose(type="pia", title="PIA")
    assessment = (await _assessments(env))[0]
    result = await env.complete(assessment_id=str(assessment.id))
    assert "refused" in result.lower()
    assert "risk_rating" in result
    assert (await _assessments(env))[0].status == "draft"


async def test_complete_uses_existing_rating_when_not_passed(env: AssessmentEnv) -> None:
    # A rating set on the draft is honoured at completion without re-passing it.
    await env.propose(type="pia", title="PIA", status="in_progress", risk_rating="medium")
    assessment = (await _assessments(env))[0]
    result = await env.complete(assessment_id=str(assessment.id))
    assert "Completed PIA assessment" in result
    assert (await _assessments(env))[0].risk_rating == "medium"


async def test_complete_unknown_is_refused(env: AssessmentEnv) -> None:
    result = await env.complete(assessment_id=str(uuid.uuid4()), risk_rating="low")
    assert "refused" in result.lower()
    assert "no assessment" in result


async def test_complete_already_completed_is_noop(env: AssessmentEnv) -> None:
    await env.propose(type="pia", title="PIA", status="completed", risk_rating="low")
    assessment = (await _assessments(env))[0]
    again = await env.complete(assessment_id=str(assessment.id))
    assert "already completed" in again.lower()
    assert (await _assessments(env))[0].status == "completed"


async def test_complete_off_enum_rating_is_refused(env: AssessmentEnv) -> None:
    await env.propose(type="pia", title="PIA")
    assessment = (await _assessments(env))[0]
    result = await env.complete(assessment_id=str(assessment.id), risk_rating="extreme")
    assert "refused" in result.lower()
    assert (await _assessments(env))[0].status == "draft"


async def test_complete_high_risk_via_stored_rating_refused_then_succeeds(
    env: AssessmentEnv,
) -> None:
    # The cross-row guard must bite when the rating comes from the PERSISTED row
    # (no risk_rating arg passed) — pins the effective_rating stored-rating leg, so
    # a regression that fed only the call-arg into the guard would be caught.
    await env.propose(type="pia", title="High PIA", status="in_progress", risk_rating="high")
    assessment = (await _assessments(env))[0]
    await env.add_risk(
        assessment_id=str(assessment.id),
        description="Unmitigated high exposure.",
        likelihood="high",
        impact="high",
    )
    refused = await env.complete(assessment_id=str(assessment.id))  # no risk_rating arg
    assert "refused" in refused.lower()
    assert "mitigation" in refused.lower()
    assert (await _assessments(env))[0].status == "in_progress"

    # Satisfy the rule via a mitigated risk; complete with no arg uses the stored high.
    await env.add_risk(
        assessment_id=str(assessment.id),
        description="Same risk, now mitigated.",
        likelihood="high",
        impact="high",
        mitigation="Tenant-scoped row-level security on the export query.",
    )
    ok = await env.complete(assessment_id=str(assessment.id))
    assert "Completed PIA assessment" in ok
    rows = await _assessments(env)
    assert rows[0].status == "completed" and rows[0].risk_rating == "high"


async def test_create_completed_high_risk_non_dpia_is_rejected(env: AssessmentEnv) -> None:
    # The high-rating arm of the cross-row guard on the CREATE path (not just DPIA).
    result = await env.propose(type="pia", title="High PIA", status="completed", risk_rating="high")
    assert "cannot be created already-completed" in result.lower()
    assert await _assessments(env) == []


async def test_re_rating_completed_assessment_re_runs_the_cross_row_guard(
    env: AssessmentEnv,
) -> None:
    # Re-completing an already-completed assessment WITH a new rating is NOT a no-op:
    # it re-runs the cross-row guard, so a low PIA cannot be silently relabelled high
    # without a documented mitigation.
    await env.propose(type="pia", title="Low then high", status="completed", risk_rating="low")
    assessment = (await _assessments(env))[0]
    await env.add_risk(
        assessment_id=str(assessment.id),
        description="Unmitigated high risk surfaced after sign-off.",
        likelihood="high",
        impact="high",
    )
    refused = await env.complete(assessment_id=str(assessment.id), risk_rating="high")
    assert "refused" in refused.lower()
    rows = await _assessments(env)
    assert rows[0].status == "completed" and rows[0].risk_rating == "low"  # unchanged

    # With a mitigated risk the re-rate goes through.
    await env.add_risk(
        assessment_id=str(assessment.id),
        description="Now mitigated.",
        likelihood="high",
        impact="high",
        mitigation="Access restricted to the support role; DPO review scheduled.",
    )
    ok = await env.complete(assessment_id=str(assessment.id), risk_rating="high")
    assert "Completed PIA assessment" in ok
    assert (await _assessments(env))[0].risk_rating == "high"


# ---------------------------------------------------------------------------
# link_assessment_to_activity
# ---------------------------------------------------------------------------


async def test_link_assessment_to_activity(env: AssessmentEnv) -> None:
    await env.propose(type="dpia", title="DPIA")
    assessment = (await _assessments(env))[0]
    activity = await _make_activity(env)

    result = await env.link(
        assessment_id=str(assessment.id), processing_activity_id=str(activity.id)
    )
    assert "Linked DPIA assessment" in result

    from sqlalchemy.orm import selectinload

    async with env.factory() as db:
        loaded = (
            await db.execute(
                select(Assessment)
                .options(selectinload(Assessment.processing_activities))
                .where(Assessment.id == assessment.id)
            )
        ).scalar_one()
        assert [a.id for a in loaded.processing_activities] == [activity.id]

    # Idempotent.
    again = await env.link(
        assessment_id=str(assessment.id), processing_activity_id=str(activity.id)
    )
    assert "already linked" in again


async def test_link_unknown_ids_is_refused(env: AssessmentEnv) -> None:
    result = await env.link(
        assessment_id=str(uuid.uuid4()), processing_activity_id=str(uuid.uuid4())
    )
    assert "refused" in result.lower()
    assert "no assessment" in result
    assert "no processing activity" in result


async def test_link_retired_activity_is_refused(env: AssessmentEnv) -> None:
    await env.propose(type="dpia", title="DPIA")
    assessment = (await _assessments(env))[0]
    activity = await _make_activity(env, retired=True)
    result = await env.link(
        assessment_id=str(assessment.id), processing_activity_id=str(activity.id)
    )
    assert "refused" in result.lower()
    assert "retired" in result.lower()


async def test_link_non_uuid_is_refused(env: AssessmentEnv) -> None:
    result = await env.link(assessment_id="nope", processing_activity_id="also-nope")
    assert "refused" in result.lower()


# ---------------------------------------------------------------------------
# list_assessments
# ---------------------------------------------------------------------------


async def test_list_is_empty_then_reflects_proposals(env: AssessmentEnv) -> None:
    empty = await env.list_assessments()
    assert "no privacy assessments yet" in empty

    await env.propose(type="dpia", title="Analytics DPIA")
    assessment = (await _assessments(env))[0]
    await env.add_risk(
        assessment_id=str(assessment.id),
        description="A risk",
        likelihood="low",
        impact="medium",
        mitigation="A mitigation",
    )
    listed = await env.list_assessments()
    assert "Company privacy register — 1 assessment" in listed
    assert "Analytics DPIA" in listed
    assert "DPIA" in listed
    assert "1 risk" in listed
    assert "status: draft" in listed


async def test_list_covers_count_excludes_retired_activity(env: AssessmentEnv) -> None:
    await env.propose(type="dpia", title="DPIA")
    assessment = (await _assessments(env))[0]
    activity = await _make_activity(env)
    await env.link(assessment_id=str(assessment.id), processing_activity_id=str(activity.id))
    assert "covers 1 activity" in await env.list_assessments()

    # Retire the activity directly — the coverage count must drop to 0 (parity with
    # the ROPA reads; the link row survives but the activity left the register).
    from datetime import UTC, datetime

    async with env.factory() as db:
        await db.execute(
            ProcessingActivity.__table__.update()
            .where(ProcessingActivity.id == activity.id)
            .values(retired_at=datetime.now(UTC))
        )
        await db.commit()
    assert "covers 0 activities" in await env.list_assessments()


# ---------------------------------------------------------------------------
# The guard chokepoint + the model-facing surface
# ---------------------------------------------------------------------------


async def test_each_dispatch_writes_one_audit_row_without_values(env: AssessmentEnv) -> None:
    await env.propose(type="dpia", title="Secret-named DPIA about Acme")
    await env.list_assessments()

    rows = await _audit_rows(env)
    assert len(rows) == 2
    assert {r.details["tool"] for r in rows} == {"propose_assessment", "list_assessments"}
    for row in rows:
        assert row.action == "agent_run.tool_call"
        assert row.user_id == env.user_id
        assert row.practice_area_id == env.practice_area_id
        assert row.details["outcome"] == "success"
        # Counts/types/IDs only — never the proposal's title text.
        assert "Acme" not in str(row.details)


async def test_rejected_proposal_still_audits_the_dispatch(env: AssessmentEnv) -> None:
    await env.propose(type="nonsense", title="X")
    rows = await _audit_rows(env)
    assert len(rows) == 1
    assert rows[0].details["tool"] == "propose_assessment"
    assert rows[0].details["outcome"] == "success"
    assert await _assessments(env) == []


def test_tool_names_cover_the_built_tools(env: AssessmentEnv) -> None:
    expected = {
        "propose_assessment",
        "add_risk",
        "complete_assessment",
        "link_assessment_to_activity",
        "list_assessments",
    }
    assert expected == ASSESSMENT_TOOL_NAMES
    # The R6 grant set must match the closures build_assessment_tools returns — else
    # a tool is silently R6-denied (dead) or a stale name advertises a dead capability.
    assert env.built_tool_names == ASSESSMENT_TOOL_NAMES


async def test_tools_expose_model_facing_schema(env: AssessmentEnv) -> None:
    """A-class content args only (ADR-F004) — no project_id / user_id leak."""
    assert list(inspect.signature(env.propose).parameters) == [
        "type",
        "title",
        "summary",
        "status",
        "risk_rating",
        "conditions",
    ]
    assert list(inspect.signature(env.add_risk).parameters) == [
        "assessment_id",
        "description",
        "likelihood",
        "impact",
        "mitigation",
        "owner",
        "status",
    ]
    assert list(inspect.signature(env.complete).parameters) == ["assessment_id", "risk_rating"]
    assert list(inspect.signature(env.link).parameters) == [
        "assessment_id",
        "processing_activity_id",
    ]
    assert list(inspect.signature(env.list_assessments).parameters) == []
    for tool in (env.propose, env.add_risk, env.complete, env.link, env.list_assessments):
        assert inspect.iscoroutinefunction(tool)


# ---------------------------------------------------------------------------
# End to end: the REAL deepagents loop drives propose → add_risk → complete
# ---------------------------------------------------------------------------


async def test_real_loop_builds_and_completes_a_dpia(env: AssessmentEnv) -> None:
    """A scripted model proposes a DPIA, adds a mitigated risk, then completes it —
    the run finishes with exactly one completed, high-rated DPIA persisted."""
    from app.agents.runner import execute_agent_run
    from tests.agents.fakes import (
        ScriptedToolCallingModel,
        final_message,
        tool_call_message,
    )

    # The model must add_risk before it knows the assessment id, so script it to
    # propose, list (to read the id back), then add_risk + complete. To keep the
    # fake deterministic we resolve the id out-of-band after the propose step.
    await env.propose(type="dpia", title="Pipeline DPIA")
    assessment = (await _assessments(env))[0]

    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "add_risk",
                {
                    "assessment_id": str(assessment.id),
                    "description": "Re-identification of analytics records.",
                    "likelihood": "medium",
                    "impact": "high",
                    "mitigation": "Pseudonymise user_id at ingest; 30-day retention.",
                },
            ),
            tool_call_message(
                "complete_assessment",
                {"assessment_id": str(assessment.id), "risk_rating": "high"},
            ),
            final_message("Completed the pipeline DPIA at high residual risk."),
        ]
    )

    await execute_agent_run(
        env.run_id,
        env.factory,
        tools=[env.propose, env.add_risk, env.complete, env.list_assessments],
        model=model,
    )

    async with env.factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == env.run_id))).scalar_one()
    assert run.status == "completed"

    rows = await _assessments(env)
    assert len(rows) == 1
    assert rows[0].status == "completed"
    assert rows[0].risk_rating == "high"
    assert len(await _risks(env, rows[0].id)) == 1
