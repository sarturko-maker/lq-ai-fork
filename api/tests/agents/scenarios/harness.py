"""The rig: seed a Commercial matter, drive the real agent, read receipts.

:func:`seed_commercial_matter` plants a user + a Commercial-bound matter
+ one searchable document (file → document → chunks) in the test DB.
:func:`run_scenario` creates a run row, drives the PRODUCTION composition
point against the live gateway, then reads back the settled run + step
rows into a :class:`Receipt`. The only injected seams are the test DB
session factory and a null checkpointer (each scenario is single-turn on
its own fresh thread) — the model, the gateway http client, and the
gateway URL/key all flow from settings exactly as in production.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.composition import compose_and_execute_run
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.audit import AuditLog
from app.models.document import Document, DocumentChunk
from app.models.file import File
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.user import User
from app.schemas.agent_runs import AgentRunStepKind
from app.security import hash_password
from app.skills.registry import SkillRegistry
from tests.agents.scenarios.scenarios import (
    FixtureDocument,
    Scenario,
    ScenarioChecks,
    build_fixture_document,
    evaluate,
)

# The run's step cap — generous enough for a search→read→answer chain,
# tight enough that a runaway loop terminates as cap_exceeded (a finding).
_MAX_STEPS = 16
# Bound the answer excerpt that lands in the report (observations only).
_ANSWER_EXCERPT = 800


@dataclass
class SeededMatter:
    """A planted Commercial matter and its teardown handle."""

    factory: async_sessionmaker[AsyncSession]
    user_id: uuid.UUID
    project_id: uuid.UUID
    practice_area_id: uuid.UUID
    cleanup: Callable[[], Awaitable[None]]


async def seed_matter(
    factory: async_sessionmaker[AsyncSession],
    *,
    area_key: str,
    doc: FixtureDocument,
    matter_name: str,
) -> SeededMatter:
    """Plant a user + an ``area_key``-bound matter + ONE searchable document.

    Area-agnostic (UX-B-2): pass the area key, the area's fixture document, and
    a matter name. ``seed_commercial_matter`` is the UX-B-1 wrapper;
    :func:`seed_multi_doc_matter` plants several documents (UX-B-4).
    """
    return await seed_multi_doc_matter(
        factory, area_key=area_key, docs=[doc], matter_name=matter_name
    )


async def seed_multi_doc_matter(
    factory: async_sessionmaker[AsyncSession],
    *,
    area_key: str,
    docs: list[FixtureDocument],
    matter_name: str,
) -> SeededMatter:
    """Plant a user + an ``area_key``-bound matter + SEVERAL searchable documents.

    UX-B-4: a single-document matter gives the agent no reason to fan out;
    several documents are what make delegation to a subagent the better path.
    The matter floor is tier 4 (MiniMax-M3's tier) and the default areas seed no
    area floor, so the effective gateway floor stays 4 and M3 qualifies.
    """
    async with factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == area_key))
        ).scalar_one()

        user = User(
            email=f"ux-b2-{uuid.uuid4().hex[:8]}@example.com",
            display_name="UX-B Scenario User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()

        project = Project(
            owner_id=user.id,
            name=matter_name,
            slug=f"{area_key}-{uuid.uuid4().hex[:6]}",
            privileged=True,
            minimum_inference_tier=4,
            practice_area_id=area_id,
        )
        db.add(project)
        await db.flush()

        for doc in docs:
            file = File(
                owner_id=user.id,
                project_id=project.id,
                filename=doc.filename,
                mime_type="text/plain",
                size_bytes=len(doc.normalized_content.encode("utf-8")),
                hash_sha256=uuid.uuid4().hex,
                storage_path=str(uuid.uuid4()),
                ingestion_status="ready",
            )
            db.add(file)
            await db.flush()

            document = Document(
                file_id=file.id,
                parser="harness-fixture",
                page_count=doc.page_count,
                character_count=len(doc.normalized_content),
                normalized_content=doc.normalized_content,
            )
            db.add(document)
            await db.flush()

            for chunk in doc.chunks:
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        char_offset_start=chunk.char_offset_start,
                        char_offset_end=chunk.char_offset_end,
                    )
                )
        await db.commit()
        user_id, project_id = user.id, project.id

    async def cleanup() -> None:
        async with factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            # Steps + runs first (FK), then threads, then the matter's
            # file→document→chunk cascade drops with the file.
            run_ids = (
                (await db.execute(select(AgentRun.id).where(AgentRun.user_id == user_id)))
                .scalars()
                .all()
            )
            if run_ids:
                await db.execute(delete(AgentRunStep).where(AgentRunStep.run_id.in_(run_ids)))
            await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
            await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
            await db.execute(delete(File).where(File.owner_id == user_id))
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()

    return SeededMatter(
        factory=factory,
        user_id=user_id,
        project_id=project_id,
        practice_area_id=area_id,
        cleanup=cleanup,
    )


async def seed_commercial_matter(
    factory: async_sessionmaker[AsyncSession],
) -> SeededMatter:
    """UX-B-1 wrapper: a Commercial matter with the Acme MSA fixture."""
    return await seed_matter(
        factory,
        area_key="commercial",
        doc=build_fixture_document(),
        matter_name="Acme — Master Services Agreement",
    )


@dataclass
class Receipt:
    """The honest record of one scenario run — observations only."""

    scenario: Scenario
    status: str
    tools_called: list[str]
    step_count: int
    model_turns: int
    final_answer: str | None
    error: str | None
    latency_s: float
    checks: ScenarioChecks
    # The settled run's id — lets a caller re-read the masked step rows
    # (evals.runner.fetch_steps) for Track-A judging (F2 E1). Not in to_dict()
    # (a run id is not a report observation; the report carries counts/shapes).
    run_id: uuid.UUID
    # UX-B-4 delegation observations (ADR-F017): how many `task` delegations the
    # lead agent issued, whether ANY step nested under a parent (subagent ran),
    # and a compact parent-seq → child-seqs ancestry summary.
    task_calls: int = 0
    delegated: bool = False
    ancestry: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        answer = self.final_answer or ""
        excerpt = answer[:_ANSWER_EXCERPT] + ("…" if len(answer) > _ANSWER_EXCERPT else "")
        return {
            "id": self.scenario.id,
            "title": self.scenario.title,
            "note": self.scenario.note,
            "prompt": self.scenario.prompt,
            "status": self.status,
            "latency_s": round(self.latency_s, 1),
            "step_count": self.step_count,
            "model_turns": self.model_turns,
            "tools_called": self.tools_called,
            "task_calls": self.task_calls,
            "delegated": self.delegated,
            "ancestry": self.ancestry,
            "expect_tools": list(self.scenario.expect_tools),
            "forbid_tools": list(self.scenario.forbid_tools),
            "shape_matched": self.checks.shape_matched,
            "checks": {
                "expected_tools_present": self.checks.expected_tools_present,
                "forbidden_tools_absent": self.checks.forbidden_tools_absent,
                "must_include_ok": self.checks.must_include_ok,
                "should_not_ok": self.checks.should_not_ok,
                "within_step_bound": self.checks.within_step_bound,
                "clarify_ok": self.checks.clarify_ok,
                "refusal_ok": self.checks.refusal_ok,
            },
            "error": self.error,
            "final_answer_excerpt": excerpt,
        }


async def run_scenario(
    scenario: Scenario,
    seeded: SeededMatter,
    *,
    skill_registry: SkillRegistry | None = None,
    max_steps: int = _MAX_STEPS,
    model_alias: str | None = None,
) -> Receipt:
    """Drive one scenario through the production loop; read back receipts.

    UX-B-3: pass ``skill_registry`` (a real registry loaded from ``/skills``)
    to activate the matter's area-bound skills — the composition point builds
    the registry-backed backend over the area's bound subset. ``None`` (the
    default) leaves skills off, exactly as the production default provider
    resolves when no registry is installed in-process (the UX-B-1/2 baseline).

    UX-B-4: ``max_steps`` overrides the hard run cap — a delegating run
    (parent search → task → subagent search/read → report → parent answer)
    needs more headroom than a single-turn fetch.

    ``model_alias`` selects which gateway alias the run targets. The fork is
    model-agnostic (any LLM is injected via the gateway, not a MiniMax app),
    so the harness must be able to point at a candidate provider when
    qualifying it (ADR-F015). Resolution: explicit arg → ``LQ_AI_SCENARIO_MODEL``
    env → ``"smart"`` (the operator-configured, currently-qualified default).
    """
    resolved_alias = model_alias or os.environ.get("LQ_AI_SCENARIO_MODEL", "smart")
    factory = seeded.factory
    async with factory() as db:
        thread = AgentThread(
            user_id=seeded.user_id, project_id=seeded.project_id, title=scenario.title
        )
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=seeded.user_id,
            thread_id=thread.id,
            project_id=seeded.project_id,
            status="running",
            prompt=scenario.prompt,
            model_alias=resolved_alias,
            max_steps=max_steps,
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    started = time.monotonic()
    await compose_and_execute_run(
        run_id=run_id,
        session_factory_provider=lambda: factory,
        # Single-turn, fresh thread per scenario — no checkpoint needed,
        # and this keeps the harness off any Postgres checkpointer that
        # would point at the dev DB rather than the test DB.
        checkpointer_provider=lambda: None,
        # UX-B-3: inject the loaded registry (or None → skills off, the
        # production default in a registry-less process).
        skill_registry_provider=lambda: skill_registry,
    )
    latency = time.monotonic() - started

    async with factory() as db:
        run_row = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
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

    tools_called = [s.name for s in steps if s.kind == AgentRunStepKind.tool_call.value and s.name]
    model_turns = sum(1 for s in steps if s.kind == AgentRunStepKind.model_turn.value)
    answer = run_row.final_answer or ""
    checks = evaluate(
        scenario,
        tools_called=tools_called,
        step_count=len(steps),
        answer=answer,
    )
    # UX-B-4 delegation observations (ADR-F017). A `task` tool_call is a
    # delegation; the subagent's own steps nest under it via parent_step_id
    # (runner._innermost_tool_parent, F0-S7). Summarise parent seq → child seqs.
    task_calls = sum(
        1 for s in steps if s.kind == AgentRunStepKind.tool_call.value and s.name == "task"
    )
    seq_by_id = {s.id: s.seq for s in steps}
    children: dict[int, list[int]] = {}
    for s in steps:
        if s.parent_step_id is not None and s.parent_step_id in seq_by_id:
            children.setdefault(seq_by_id[s.parent_step_id], []).append(s.seq)
    ancestry = [
        {"parent_seq": parent_seq, "child_seqs": sorted(child_seqs)}
        for parent_seq, child_seqs in sorted(children.items())
    ]
    return Receipt(
        scenario=scenario,
        status=run_row.status,
        tools_called=tools_called,
        step_count=len(steps),
        model_turns=model_turns,
        final_answer=run_row.final_answer,
        error=run_row.error,
        latency_s=latency,
        checks=checks,
        run_id=run_id,
        task_calls=task_calls,
        delegated=bool(ancestry),
        ancestry=ancestry,
    )
