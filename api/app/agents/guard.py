"""Guarded-dispatch chokepoint for agent-run tools — F0-S4 (fork).

The minimal cut of the ``guarded_tool_call`` pattern (ADR-F002), pulled
forward from F1 so the first REAL agent tools (the matter document
tools, :mod:`app.agents.tools`) never ship unguarded. Every dispatch of
a guarded tool passes :func:`guarded_dispatch` — one chokepoint, three
brakes, one audit row:

* **R6 (grant)** — the tool name must be in the run's granted set. In
  F0-S4 the grant set equals the injected matter tools; F1 swaps in
  per-practice-area grant configuration through this same check.
* **R5 (halt)** — the run's ``status`` is re-checked at the DB before
  the tool body executes; anything other than ``'running'`` denies the
  dispatch. Since F1-S1 the check IS a fenced heartbeat touch (one
  UPDATE: lands only while running, and proves liveness at tool-
  boundary cadence — ADR-F009). Deny is still model-visible-error
  advisory per dispatch; the HARD stop is the runner's heartbeat
  detecting the settled row (RunSettledElsewhere) or arq Job.abort.
* **R4 (cost)** — still an honest no-op *at the tool dispatch*: the
  matter tools are local Postgres reads with zero marginal inference
  cost, so there is nothing to cap here. The real per-run cost is the
  gateway MODEL calls, so the token budget that R4 always pointed at
  now lives where that cost is incurred — the runner loop, beside
  ``max_steps`` (F2 Slice F, ADR-F051: sum each turn's
  ``usage_metadata.total_tokens``, halt at ``run_token_budget``).

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
from typing import Any

from sqlalchemy import CursorResult, func, select, update as sa_update
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
    # F1-S3: the matter's practice area, for per-area audit slicing (ADR-F002).
    # B-class like project_id — never model-visible.
    practice_area_id: uuid.UUID | None = None


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
    boundary as the dispatch. One honest exception: a wall-clock
    cancellation landing INSIDE ``op`` (``asyncio.CancelledError`` is a
    BaseException) propagates without an outcome row — the runner's
    ``tool_call`` step row and the run's terminal ``error='timeout'``
    record that dispatch; a cancellation-safe audit write needs the
    arq migration's job model.
    """
    async with ctx.session_factory() as db:
        if tool not in ctx.granted:
            await _audit(db, ctx, tool=tool, outcome="tool_not_granted")
            await db.commit()
            raise AgentToolNotGranted(f"tool '{tool}' is not granted for this run")

        # R5 + liveness in one statement (F1-S1, ADR-F009): the UPDATE
        # only lands while the run is still 'running' — so a hit IS the
        # status check, and the touched heartbeat is a second liveness
        # source at tool-DISPATCH cadence beside the runner's throttled
        # per-event beat. Committed IMMEDIATELY (before the tool body):
        # the touch must be visible to the sweep while the body runs,
        # must survive a tool-error rollback, and must not hold the
        # agent_runs row lock under a slow tool (cancel/sweep would
        # block behind it — review fix). Honest limit: a single tool
        # body longer than agent_run_orphan_after_seconds can still be
        # false-orphaned — fenced-safe per ADR-F009 (the zombie halts,
        # the run reports failed; the sweep also fires an abort).
        touched: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
            sa_update(AgentRun)
            .where(AgentRun.id == ctx.run_id, AgentRun.status == AgentRunStatus.running.value)
            .values(heartbeat_at=func.now())
        )
        if touched.rowcount != 1:
            run_status = (
                await db.execute(select(AgentRun.status).where(AgentRun.id == ctx.run_id))
            ).scalar_one_or_none()
            await _audit(db, ctx, tool=tool, outcome="run_halted")
            await db.commit()
            raise AgentRunHalted(f"run is '{run_status}' — tool dispatch denied")
        await db.commit()

        # R4: no-op HERE — local DB reads, zero marginal inference cost.
        # The per-run TOKEN budget (the real cost is the gateway model calls)
        # is enforced in the runner loop beside max_steps (ADR-F051).

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
    and let the result stand. The rollback below is what makes that
    true: ``audit_action`` flushes, and a failed flush leaves the
    session pending-rollback — without the rollback, the caller's
    ``commit()`` would raise and mask the result after all (F0-S4
    review). Rolling back is safe here: the tool's reads are already
    materialized into the result string.
    """
    try:
        await audit_action(
            db,
            user_id=ctx.user_id,
            action=_AUDIT_ACTION,
            resource_type=_RESOURCE_TYPE,
            resource_id=str(ctx.run_id),
            project_id=ctx.project_id,
            practice_area_id=ctx.practice_area_id,
            details={"tool": tool, **details},
        )
    except Exception:
        logger.exception(
            "agent tool-call audit write failed",
            extra={
                "event": "agent_tool_audit_failed",
                "run_id": str(ctx.run_id),
                "tool": tool,
            },
        )
        try:
            await db.rollback()
        except Exception:
            logger.exception(
                "rollback after failed audit write also failed",
                extra={
                    "event": "agent_tool_audit_rollback_failed",
                    "run_id": str(ctx.run_id),
                },
            )
