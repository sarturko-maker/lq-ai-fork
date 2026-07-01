"""AI Compliance agent tools — AIC-1 (fork, ADR-F057): the code-validated write path.

Real Postgres, real ``AiSystem`` inserts, real audit rows: the
``build_compliance_tools`` closures are exercised exactly as the runner dispatches
them. The load-bearing assertions:

* propose → validate → COMMIT: a valid proposal writes exactly one row with the
  proposed FACTS, stamped with ``source_project_id`` (provenance, ADR-F019) and the
  NON-NULL ``practice_area_id`` (ADR-F057/F021), from the binding — never the model;
* propose → reject → RETRY: an invalid proposal is refused, NOTHING is written, the
  reason comes back as the tool result (ADR-F018);
* the presence gate — the register has no risk-tier/role column; the schema refuses
  an extra field the model might use to smuggle a tier;
* soft-retire hides a row from the live list but keeps it on record;
* the guard chokepoint — one ``agent_run.tool_call`` audit row per dispatch carrying
  counts/types/IDs, never the proposal's values;
* the DB CHECK mirror refuses an inconsistent row even bypassing the schema;
* the grant set matches the built tools.

Like the ROPA tool tests these COMMIT (the tools open their own sessions from the
factory), so they seed via a commit-capable factory and tear down by
``source_project_id``.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.ai_system_changes import AiSystemChangeLedger
from app.agents.compliance_tools import COMPLIANCE_TOOL_NAMES, build_compliance_tools
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.classification import RiskClassification
from app.models.compliance import AiSystem
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration

_VALID = {
    "name": "Applicant ranking model",
    "intended_purpose": "Score and rank job applicants for recruiter review.",
    "lifecycle_status": "in_service",
    "development_origin": "third_party",
    "is_gpai": False,
    "gpai_systemic": False,
    "notes": None,
}


@dataclass
class ComplianceEnv:
    factory: async_sessionmaker[AsyncSession]
    user_id: uuid.UUID
    run_id: uuid.UUID
    project_id: uuid.UUID
    practice_area_id: uuid.UUID
    propose: Callable[..., Awaitable[str]]
    retire: Callable[..., Awaitable[str]]
    list_systems: Callable[..., Awaitable[str]]
    classify: Callable[..., Awaitable[str]]
    built_tool_names: frozenset[str]
    ledger: AiSystemChangeLedger


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def compliance_env(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[ComplianceEnv]:
    """One AI Compliance matter + a running run, with the compliance tools built over it."""
    async with commit_factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "ai-compliance"))
        ).scalar_one()

        user = User(
            email=f"aic-{uuid.uuid4().hex[:8]}@example.com",
            display_name="AIC User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()

        project = Project(
            owner_id=user.id,
            name="Programme — EU AI Act",
            slug=f"aiact-{uuid.uuid4().hex[:6]}",
            practice_area_id=area_id,
        )
        db.add(project)
        await db.flush()

        thread = AgentThread(user_id=user.id, project_id=project.id, title="aic tools tests")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user.id,
            thread_id=thread.id,
            project_id=project.id,
            status="running",
            prompt="Maintain the AI-systems register.",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()

        binding = MatterBinding(
            project_id=project.id,
            user_id=user.id,
            name="Programme — EU AI Act",
            privileged=False,
            minimum_inference_tier=None,
            practice_area_id=area_id,
        )
        ledger = AiSystemChangeLedger()
        tools = build_compliance_tools(
            commit_factory, run_id=run.id, binding=binding, change_ledger=ledger
        )
        by_name = {t.__name__: t for t in tools}
        env = ComplianceEnv(
            factory=commit_factory,
            user_id=user.id,
            run_id=run.id,
            project_id=project.id,
            practice_area_id=area_id,
            propose=by_name["propose_ai_system"],
            retire=by_name["retire_ai_system"],
            list_systems=by_name["list_ai_systems"],
            classify=by_name["classify_ai_system"],
            built_tool_names=frozenset(t.__name__ for t in tools),
            ledger=ledger,
        )

    yield env

    async with commit_factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == env.user_id))
        # Classifications FK ai_systems (RESTRICT) — delete them before the register rows.
        await db.execute(
            delete(RiskClassification).where(RiskClassification.source_project_id == env.project_id)
        )
        await db.execute(delete(AiSystem).where(AiSystem.source_project_id == env.project_id))
        await db.execute(delete(AgentRun).where(AgentRun.user_id == env.user_id))
        await db.execute(delete(AgentThread).where(AgentThread.user_id == env.user_id))
        await db.execute(delete(Project).where(Project.id == env.project_id))
        await db.execute(delete(User).where(User.id == env.user_id))
        await db.commit()


async def _systems(env: ComplianceEnv) -> list[AiSystem]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(AiSystem)
                .where(AiSystem.source_project_id == env.project_id)
                .order_by(AiSystem.created_at.asc())
            )
        ).scalars()
        return list(rows)


async def _audit_rows(env: ComplianceEnv) -> list[AuditLog]:
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


async def test_valid_proposal_commits_one_row(compliance_env: ComplianceEnv) -> None:
    result = await compliance_env.propose(**_VALID)
    assert "Recorded AI system" in result
    assert "Applicant ranking model" in result

    rows = await _systems(compliance_env)
    assert len(rows) == 1
    row = rows[0]
    # Provenance (ADR-F019) + the durable scoping key (ADR-F057/F021) are stamped
    # from the binding, never from the model.
    assert row.source_project_id == compliance_env.project_id
    assert row.practice_area_id == compliance_env.practice_area_id
    assert row.name == "Applicant ranking model"
    assert row.lifecycle_status == "in_service"
    assert row.development_origin == "third_party"
    assert row.is_gpai is False
    assert row.retired_at is None
    # The presence gate — nothing tier-like is written (the register has no such column).
    assert not hasattr(row, "risk_tier")


async def test_valid_systemic_gpai_commits(compliance_env: ComplianceEnv) -> None:
    result = await compliance_env.propose(
        **{**_VALID, "name": "Foundation model", "is_gpai": True, "gpai_systemic": True}
    )
    assert "systemic-risk GPAI" in result
    rows = await _systems(compliance_env)
    assert len(rows) == 1
    assert rows[0].is_gpai is True and rows[0].gpai_systemic is True


async def test_off_enum_origin_rejected_and_nothing_written(compliance_env: ComplianceEnv) -> None:
    result = await compliance_env.propose(**{**_VALID, "development_origin": "vibes"})
    assert "rejected" in result.lower()
    assert "development_origin" in result
    assert await _systems(compliance_env) == []


async def test_systemic_without_gpai_rejected(compliance_env: ComplianceEnv) -> None:
    result = await compliance_env.propose(**{**_VALID, "is_gpai": False, "gpai_systemic": True})
    assert "rejected" in result.lower()
    assert "is_gpai" in result
    assert await _systems(compliance_env) == []


async def test_retire_hides_from_live_list_but_keeps_row(compliance_env: ComplianceEnv) -> None:
    await compliance_env.propose(**_VALID)
    sid = str((await _systems(compliance_env))[0].id)

    retired = await compliance_env.retire(sid, "decommissioned")
    assert "Retired" in retired

    # The row survives (soft-retire), with retired_at set.
    rows = await _systems(compliance_env)
    assert len(rows) == 1
    assert rows[0].retired_at is not None
    # The live list tool hides it and footnotes the hidden count.
    listing = await compliance_env.list_systems()
    assert "Applicant ranking model" not in listing
    assert "1 retired system hidden" in listing


async def test_list_shows_recorded_systems(compliance_env: ComplianceEnv) -> None:
    await compliance_env.propose(**_VALID)
    listing = await compliance_env.list_systems()
    assert "Applicant ranking model" in listing
    assert "in_service" in listing


async def test_ledger_records_create(compliance_env: ComplianceEnv) -> None:
    await compliance_env.propose(**_VALID)
    changes = compliance_env.ledger.drain()
    assert len(changes) == 1
    assert changes[0].kind == "ai_system"
    assert changes[0].verb == "create"


async def test_audit_row_carries_counts_types_ids_only(compliance_env: ComplianceEnv) -> None:
    await compliance_env.propose(**_VALID)
    rows = await _audit_rows(compliance_env)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.action == "agent_run.tool_call"
    assert audit.details["tool"] == "propose_ai_system"
    assert audit.details["outcome"] == "success"
    # The raw proposal values never reach the audit row (counts/types/IDs only).
    serialized = str(audit.details)
    assert "Applicant ranking model" not in serialized
    assert "Score and rank" not in serialized


async def test_grant_set_matches_built_tools(compliance_env: ComplianceEnv) -> None:
    assert compliance_env.built_tool_names == COMPLIANCE_TOOL_NAMES


async def test_db_check_refuses_inconsistent_row(compliance_env: ComplianceEnv) -> None:
    # Bypass the schema and insert a systemic-GPAI-without-GPAI row directly: the DB
    # CHECK mirror (defense-in-depth) refuses it even though no tool would.
    with pytest.raises(IntegrityError):
        async with compliance_env.factory() as db:
            db.add(
                AiSystem(
                    practice_area_id=compliance_env.practice_area_id,
                    source_project_id=compliance_env.project_id,
                    name="Inconsistent row",
                    intended_purpose="A systemic model that is somehow not a GPAI model.",
                    lifecycle_status="in_service",
                    development_origin="in_house",
                    is_gpai=False,
                    gpai_systemic=True,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            await db.commit()


# --- AIC-2: the classify_ai_system tool + verdict persistence (presence gate) ----


async def _classifications(env: ComplianceEnv) -> list[RiskClassification]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(RiskClassification)
                .where(RiskClassification.source_project_id == env.project_id)
                .order_by(RiskClassification.created_at.asc())
            )
        ).scalars()
        return list(rows)


async def _first_system_id(env: ComplianceEnv) -> str:
    await env.propose(**_VALID)
    return str((await _systems(env))[0].id)


async def test_classify_persists_sealed_high_risk_verdict(compliance_env: ComplianceEnv) -> None:
    sid = await _first_system_id(compliance_env)
    result = await compliance_env.classify(sid, annex_iii_area="employment")
    assert "HIGH" in result
    assert "engine's determination" in result

    rows = await _classifications(compliance_env)
    assert len(rows) == 1
    row = rows[0]
    assert row.tier == "high"
    assert row.route == "annex_iii"
    assert row.superseded_at is None
    assert row.verdict_hash
    assert row.ruleset_version.startswith("2024-1689+omnibus-2026-06-30")
    # Provenance + durable scoping key stamped from the binding, never the model.
    assert row.source_project_id == compliance_env.project_id
    assert row.practice_area_id == compliance_env.practice_area_id
    # The engine's input snapshot is stored; the tier is not one of its keys.
    assert "tier" not in row.facts
    assert row.facts["annex_iii_area"] == "employment"


async def test_reclassify_same_facts_is_idempotent(compliance_env: ComplianceEnv) -> None:
    sid = await _first_system_id(compliance_env)
    await compliance_env.classify(sid, annex_iii_area="employment")
    again = await compliance_env.classify(sid, annex_iii_area="employment")
    assert "unchanged" in again.lower()
    # Still exactly one row (no duplicate, no supersede).
    rows = await _classifications(compliance_env)
    assert len(rows) == 1
    assert rows[0].superseded_at is None


async def test_reclassify_changed_facts_supersedes(compliance_env: ComplianceEnv) -> None:
    sid = await _first_system_id(compliance_env)
    await compliance_env.classify(sid, annex_iii_area="employment")  # high
    # A valid Art 6(3) derogation drops it below high-risk → a different verdict.
    await compliance_env.classify(
        sid, annex_iii_area="employment", art6_3_derogation_condition="narrow_procedural_task"
    )
    rows = await _classifications(compliance_env)
    assert len(rows) == 2
    current = [r for r in rows if r.superseded_at is None]
    superseded = [r for r in rows if r.superseded_at is not None]
    assert len(current) == 1 and len(superseded) == 1
    assert current[0].tier == "minimal"
    assert current[0].draft_basis is True
    assert superseded[0].tier == "high"


async def test_classify_unknown_system_refused(compliance_env: ComplianceEnv) -> None:
    result = await compliance_env.classify(str(uuid.uuid4()), annex_iii_area="employment")
    assert "refused" in result.lower()
    assert await _classifications(compliance_env) == []


async def test_classify_rejects_incoherent_facts(compliance_env: ComplianceEnv) -> None:
    sid = await _first_system_id(compliance_env)
    # third-party conformity assessment without an Annex I component is incoherent.
    result = await compliance_env.classify(sid, requires_third_party_conformity_assessment=True)
    assert "rejected" in result.lower()
    assert await _classifications(compliance_env) == []


async def test_classify_tool_has_no_tier_parameter(compliance_env: ComplianceEnv) -> None:
    # The presence gate at the tool boundary: there is no way to pass a verdict in.
    params = set(inspect.signature(compliance_env.classify).parameters)
    assert "tier" not in params
    assert "risk_tier" not in params
    assert "route" not in params


async def test_classify_ledger_records_classify_verb(compliance_env: ComplianceEnv) -> None:
    sid = await _first_system_id(compliance_env)
    compliance_env.ledger.drain()  # discard the create from _first_system_id
    await compliance_env.classify(sid, annex_iii_area="employment")
    changes = compliance_env.ledger.drain()
    assert len(changes) == 1
    assert changes[0].kind == "ai_system"
    assert changes[0].verb == "classify"
    assert changes[0].id == sid


async def test_classify_audit_row_carries_ids_not_facts(compliance_env: ComplianceEnv) -> None:
    sid = await _first_system_id(compliance_env)
    await compliance_env.classify(sid, annex_iii_area="employment")
    rows = await _audit_rows(compliance_env)
    classify_rows = [r for r in rows if r.details.get("tool") == "classify_ai_system"]
    assert len(classify_rows) == 1
    audit = classify_rows[0]
    assert audit.details["outcome"] == "success"
    # The register name and intended purpose never reach the audit row.
    serialized = str(audit.details)
    assert "Applicant ranking model" not in serialized
    assert "Score and rank" not in serialized
