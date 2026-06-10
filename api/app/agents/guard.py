"""Guarded-dispatch chokepoint for agent-run tools — F0-S4 (fork).

The minimal cut of the ``guarded_tool_call`` pattern (ADR-F002), pulled
forward from F1 so the first REAL agent tools (the matter document
tools, :mod:`app.agents.tools`) never ship unguarded. Every dispatch of
a guarded tool passes :func:`guarded_dispatch` — one chokepoint, three
brakes, one audit row:

* **R6 (grant)** — the tool name must be in the run's granted set. In
  F0-S4 the grant set equals the injected matter tools; F1 swaps in
  per-practice-area grant configuration through this same check.
* **R5 (halt)** — the run's ``status`` is re-read from the DB before
  the tool body executes; anything other than ``'running'`` denies the
  dispatch. ADVISORY in F0-S4: deepagents' tool node converts the
  raised exception into a model-visible error and the loop continues
  until the wall clock — a hard stop needs the cancel endpoint +
  checkpointer interrupt (S5+). The chokepoint is still the right
  place for the check: when ``cancelled`` lands, no tool runs again.
* **R4 (cost)** — honest no-op: the matter document tools are local
  Postgres reads with zero marginal inference cost. Per-run budgets
  aggregating gateway routing-log costs are F1 (``cost_usd`` NULL
  until then, migration 0048).

Audit: one ``agent_run.tool_call`` row per dispatch via
:func:`app.audit.audit_action` — tool name, outcome, result size.
Counts/types/IDs only, never query text or document content (CLAUDE.md
audit contract). ``privilege_marked`` resolves from the bound project.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import audit_action
from app.models.agent_run import AgentRun
from app.schemas.agent_runs import AgentRunStatus

logger = logging.getLogger(__name__)

_AUDIT_ACTION = "agent_run.tool_call"
_RESOURCE_TYPE = "agent_run"


class AgentToolNotGranted(Exception):
    """R6: the tool is not in the run's granted set."""


class AgentRunHalted(Exception):
    """R5: the run is no longer ``'running'`` — dispatch denied."""


@dataclass(frozen=True)
class GuardContext:
    """Run-scoped facts every guarded dispatch needs.

    ``project_id``/``user_id`` are B-class parameters (ADR-F004):
    runtime-injected here, never model-visible — the model-facing tool
    signatures carry only A-class content arguments.
    """

    session_factory: async_sessionmaker[AsyncSession]
    run_id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None
    granted: frozenset[str]


async def guarded_dispatch(
    tool: str,
    op: Callable[[AsyncSession], Awaitable[str]],
    ctx: GuardContext,
) -> str:
    """Run ``op`` through the brakes; return its result text.

    Opens one fresh session per dispatch (the runner's loop session is
    never shared with tool bodies). Brake order R6 → R5 mirrors the
    autonomous chokepoint's cheap-check-first ordering; every outcome —
    granted or denied — leaves an audit row in the same transaction
    boundary as the dispatch.
    """
    async with ctx.session_factory() as db:
        if tool not in ctx.granted:
            await _audit(db, ctx, tool=tool, outcome="tool_not_granted")
            await db.commit()
            raise AgentToolNotGranted(f"tool '{tool}' is not granted for this run")

        run_status = (
            await db.execute(select(AgentRun.status).where(AgentRun.id == ctx.run_id))
        ).scalar_one_or_none()
        if run_status != AgentRunStatus.running.value:
            await _audit(db, ctx, tool=tool, outcome="run_halted")
            await db.commit()
            raise AgentRunHalted(f"run is '{run_status}' — tool dispatch denied")

        # R4: no-op — local DB reads, zero marginal inference cost.
        # Per-run budgets land with F1 (ADR-F002).

        try:
            result = await op(db)
        except Exception as exc:
            await db.rollback()  # op may have poisoned the transaction
            await _audit(db, ctx, tool=tool, outcome="error", error_type=type(exc).__name__)
            await db.commit()
            raise

        await _audit(db, ctx, tool=tool, outcome="success", result_chars=len(result))
        await db.commit()
        return result


async def _audit(db: AsyncSession, ctx: GuardContext, *, tool: str, **details: object) -> None:
    """One audit row per dispatch outcome; failures log, never mask.

    A lost audit row must not turn a successful tool result into a
    model-visible error (the dispatch already happened) — log loudly
    and let the result stand.
    """
    try:
        await audit_action(
            db,
            user_id=ctx.user_id,
            action=_AUDIT_ACTION,
            resource_type=_RESOURCE_TYPE,
            resource_id=str(ctx.run_id),
            project_id=ctx.project_id,
            details={"tool": tool, **details},
        )
    except Exception:
        logger.exception(
            "agent tool-call audit write failed",
            extra={"event": "agent_tool_audit_failed", "run_id": str(ctx.run_id), "tool": tool},
        )
