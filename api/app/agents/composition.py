"""Agent-run composition point — F0-S4, moved out of the api layer in F1-S1.

:func:`compose_and_execute_run` is the run's composition point: it loads
the run's matter binding (RE-validated against the owner and
``archived_at`` at execution time, not just at the 202 — F0-S4 rule),
assembles the guarded matter tools + matter-aware prompt + gateway
model, owns the gateway http client's lifecycle, and hands off to
:func:`app.agents.runner.execute_agent_run`.

F1-S1 (ADR-F009): execution lives in the arq worker
(:mod:`app.workers.agent_run_worker`), which claims the run's lease and
passes it here; every terminal write downstream is fenced by that
lease. The api layer keeps NO execution path. ``broker`` stays for the
in-process case (tests; a future Redis pub/sub publisher) — ``None``
degrades to settled-rows-only and the SSE endpoint's DB-tail serves
subscribers ("lossiness only costs animation", ADR-F004).

``model_builder`` / ``session_factory_provider`` /
``checkpointer_provider`` are injection seams: tests drive the REAL
composition with a scripted model, the test DB, and an in-memory
checkpointer — no gateway, no monkeypatching (CLAUDE.md DI rules).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.area_agent import AreaAgentSpec, combine_tier_floors, render_area_agent
from app.agents.checkpointer import get_agent_checkpointer
from app.agents.factory import build_gateway_chat_model, build_gateway_http_client
from app.agents.lease import RunLease, settle_run
from app.agents.runner import SYSTEM_PROMPT, execute_agent_run
from app.agents.skill_backend import SkillWiring, build_area_skill_wiring
from app.agents.stream import RunStreamBroker
from app.agents.tools import MatterBinding, build_matter_tools
from app.db.session import get_session_factory
from app.models.agent_run import AgentRun
from app.models.practice_area import PracticeArea, PracticeAreaSkill
from app.models.project import Project
from app.schemas.agent_runs import AgentRunStatus
from app.skills.registry import MutableSkillRegistry, SkillRegistry

logger = logging.getLogger(__name__)


def _skill_registry_from_app_state() -> SkillRegistry | None:
    """Current :class:`SkillRegistry` snapshot from ``app.state``, or None.

    Mirrors :func:`app.autonomous.prompts._registry_from_app_state`: both
    production startups install a :class:`MutableSkillRegistry` holder at
    ``app.state.skill_registry`` — the FastAPI lifespan and the arq worker's
    ``on_startup`` (runs execute in the worker, so the snapshot resolves
    there). Tests inject a fake via ``skill_registry_provider``; the import
    of :mod:`app.main` is deferred to avoid the startup import cycle.
    """
    from app.main import app

    holder: MutableSkillRegistry | None = getattr(app.state, "skill_registry", None)
    return holder.current() if holder is not None else None


# Appended to SYSTEM_PROMPT for matter-bound runs. Transparency rule:
# every agent instruction is readable in source (CLAUDE.md).
MATTER_PROMPT = (
    '\n\nThis run is bound to the matter "{name}". Ground your answer in '
    "the matter's documents: search_documents finds passages (an empty "
    "query lists the documents); read_document fetches one document's "
    "full text. Cite the document name and page for anything you take "
    "from them, and say so plainly when the documents don't answer the "
    "question."
)


def system_prompt_for(binding: MatterBinding | None, area: AreaAgentSpec | None = None) -> str:
    """The run's full system prompt — base + matter addendum + area profile.

    The area profile (F1-S3) is appended last so the practice area's voice
    grounds the matter work; an unconfigured/absent area adds nothing.
    """
    prompt = SYSTEM_PROMPT
    if binding is not None:
        prompt += MATTER_PROMPT.format(name=binding.name)
    if area is not None:
        prompt += area.system_prompt_suffix
    return prompt


async def compose_and_execute_run(
    *,
    run_id: uuid.UUID,
    lease: RunLease | None = None,
    broker: RunStreamBroker | None = None,
    model_builder: Callable[..., BaseChatModel] = build_gateway_chat_model,
    session_factory_provider: Callable[[], async_sessionmaker[AsyncSession]] = get_session_factory,
    checkpointer_provider: Callable[[], BaseCheckpointSaver | None] = get_agent_checkpointer,
    skill_registry_provider: Callable[[], SkillRegistry | None] = _skill_registry_from_app_state,
) -> None:
    """Compose one run's dependencies and execute it end to end.

    Any failure here settles the run as ``'failed'`` — a run must never
    strand at ``'running'`` (the flood brake counts those forever and
    three of them lock the user out — F0-S4 review). The settle is
    fenced when a lease is held and never overwrites an already-settled
    run (terminal-status monotonicity, ADR-F009).

    ``asyncio.CancelledError`` (arq abort / worker shutdown) is NOT
    handled here — it propagates to the worker wrapper, which settles
    the row and re-raises so arq's abort bookkeeping sees it.
    """
    session_factory = session_factory_provider()
    publisher = broker.publisher(run_id) if broker is not None else None
    try:
        binding: MatterBinding | None = None
        area_spec: AreaAgentSpec | None = None
        registry: SkillRegistry | None = None
        is_follow_up = False
        async with session_factory() as db:
            run = await db.get(AgentRun, run_id)
            if run is None:  # deleted underneath us (user cascade)
                if publisher is not None:
                    publisher.close()
                return
            model_alias, purpose = run.model_alias, run.purpose
            thread_id = run.thread_id
            is_follow_up = (
                await db.execute(
                    select(AgentRun.id)
                    .where(AgentRun.thread_id == thread_id, AgentRun.id != run_id)
                    .limit(1)
                )
            ).scalar_one_or_none() is not None
            if run.project_id is not None:
                project = (
                    await db.execute(
                        select(Project).where(
                            Project.id == run.project_id,
                            Project.owner_id == run.user_id,
                            Project.archived_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                if project is not None:
                    binding = MatterBinding(
                        project_id=project.id,
                        user_id=run.user_id,
                        name=project.name,
                        privileged=project.privileged,
                        minimum_inference_tier=project.minimum_inference_tier,
                        practice_area_id=project.practice_area_id,
                    )
                    # F1-S3: the matter's practice area IS the agent identity
                    # (ADR-F002). Render its profile/tier/subagents from
                    # config (ADR-F004 — one renderer, no per-area branches).
                    # UX-B-3 (ADR-F016): the area's bound skills (the
                    # practice_area_skills rows) go live, filtered to the
                    # registry's current set (drift). render_area_agent returns
                    # the resolved names; the backend below is built over them.
                    if project.practice_area_id is not None:
                        area = await db.get(PracticeArea, project.practice_area_id)
                        if area is not None:
                            registry = skill_registry_provider()
                            bound_skill_names = (
                                (
                                    await db.execute(
                                        select(PracticeAreaSkill.skill_name).where(
                                            PracticeAreaSkill.practice_area_id == area.id
                                        )
                                    )
                                )
                                .scalars()
                                .all()
                            )
                            area_spec = render_area_agent(
                                profile_md=area.profile_md,
                                default_tier_floor=area.default_tier_floor,
                                agent_config=area.agent_config,
                                bound_skill_names=bound_skill_names,
                                known_skill_names=registry.names() if registry is not None else [],
                            )

        checkpointer = checkpointer_provider()
        if checkpointer is None and is_follow_up:
            # Honest refusal (review fix): admission promised continuation
            # (has_checkpoint passed API-side), but THIS process cannot
            # read the conversation — executing would silently answer
            # with zero history while the UI presents a continuation.
            # The api's degraded mode refuses follow-ups the same way.
            await settle_run(
                session_factory,
                run_id,
                status=AgentRunStatus.failed,
                error="persistence degraded: checkpointer unavailable in worker",
                lease_token=lease.token if lease is not None else None,
            )
            if publisher is not None:
                publisher.close()
            return

        tools = (
            build_matter_tools(session_factory, run_id=run_id, binding=binding)
            if binding is not None
            else []
        )

        # F1-S3: the gateway tier floor is the strongest (lowest) of the
        # matter floor and the area's default floor — the gateway combiner
        # is min() over its sources, so combining API-side keeps the single
        # envelope field and needs no gateway change (plan §Goal 1).
        matter_floor = binding.minimum_inference_tier if binding is not None else None
        area_floor = area_spec.tier_floor if area_spec is not None else None
        effective_tier_floor = combine_tier_floors(matter_floor, area_floor)

        # UX-B-3/UX-B-4 (ADR-F016/F017): the area's bound skills become live via
        # a read-only MULTI-SOURCE backend — least privilege over the (unguarded)
        # builtin read_file the model uses to read a SKILL.md. The main agent
        # sees ONLY the area subset (source /skills); each skill-bearing subagent
        # sees ONLY its own (⊆ area) subset under its own source (deepagents'
        # isolated per-subagent skills). The wiring also rewrites each subagent
        # spec's `skills` (names → its virtual source path). When nothing
        # resolves (skills off — no registry — or no bound skill) the backend is
        # None and subagent `skills` are stripped, so the qualified default graph
        # is unchanged and no stored name can reach deepagents as a bogus source.
        if area_spec is not None:
            wiring = build_area_skill_wiring(
                registry,
                area_skill_names=area_spec.skills,
                subagents=area_spec.subagents,
            )
        else:
            wiring = SkillWiring(backend=None, main_sources=None, subagents=[])

        http_client = build_gateway_http_client()
        try:
            model = model_builder(
                model_alias=model_alias,
                purpose=purpose,
                http_async_client=http_client,
                project_minimum_inference_tier=effective_tier_floor,
                privileged=binding.privileged if binding is not None else False,
            )
            await execute_agent_run(
                run_id,
                session_factory,
                tools=tools,
                model=model,
                system_prompt=system_prompt_for(binding, area_spec),
                subagents=wiring.subagents or None,
                skills=wiring.main_sources,
                backend=wiring.backend,
                checkpointer=checkpointer,
                thread_id=thread_id,
                publisher=publisher,
                lease=lease,
            )
        finally:
            await http_client.aclose()
    except Exception as exc:
        logger.exception(
            "agent run composition failed",
            extra={"event": "agent_run_composition_failed", "run_id": str(run_id)},
        )
        error = f"{type(exc).__name__}: {exc}"[:500]
        # settle_run never overwrites a settled run, so a cleanup error
        # after a successful execution cannot flip 'completed'.
        settled = await settle_run(
            session_factory,
            run_id,
            status=AgentRunStatus.failed,
            error=error,
            lease_token=lease.token if lease is not None else None,
        )
        if publisher is not None and settled:
            # No-op if the runner already closed the stream — this only
            # fires for failures BEFORE execute_agent_run took over.
            publisher.run_finished(status=AgentRunStatus.failed.value, error=error)
        elif publisher is not None:
            # Our settle was fenced out (cancel/sweep won): end the
            # channel on the DB truth, never on a state we didn't write.
            publisher.close()
