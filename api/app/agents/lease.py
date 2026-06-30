"""Run lease + heartbeat + fenced settlement — F1-S1 (fork, ADR-F009).

Agent runs execute at-most-once on the arq worker. This module is the
single home of the lease protocol all parties speak:

* the WORKER claims a run before executing (:func:`claim_run`) — a new
  ``lease_token`` per claim is the fencing value;
* the RUNNER proves liveness by touching ``heartbeat_at`` (throttled,
  from inside the stream loop — :func:`heartbeat_run`) and learns it has
  been settled elsewhere when the fenced write hits nothing;
* terminal writes go through :func:`settle_run` — one conditional
  UPDATE with ``WHERE status='running'`` (terminal-status monotonicity:
  the first terminal writer wins) and, when the caller holds a lease,
  ``AND lease_token = :mine`` (a zombie's late write is rejected by
  rowcount, never by hope).

Every comparison uses the DATABASE clock (``now()``) — one clock
authority; app-server skew can't shrink or stretch the staleness
windows the sweep reads.

All functions open fresh short-lived sessions from the injected factory
(the runner's posture since F0-S5: a long run never pins a pool
connection) and retry once, mirroring ``_persist_step``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.agent_runs import AgentRunStatus

logger = logging.getLogger(__name__)


class RunSettledElsewhere(Exception):
    """The run row was settled by another actor (sweep / cancel endpoint).

    Raised by the runner when its fenced heartbeat stops landing — the
    loop must hard-stop: its terminal write would be rejected anyway,
    and every further gateway call is spend on a run the user already
    sees as settled.
    """


@dataclass(frozen=True)
class RunLease:
    """One worker's claim on one run — the fencing facts."""

    run_id: uuid.UUID
    token: uuid.UUID
    claimed_by: str


async def claim_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    *,
    claimed_by: str,
) -> RunLease | None:
    """Atomically claim a ``running`` run for execution.

    Returns the lease, or ``None`` when the run is not claimable — it
    was settled while queued (cancel endpoint / sweep's unclaimed-grace
    rule) or another claim exists. ``claimed_by IS NULL`` is the
    at-most-once belt over arq's ``max_tries=1`` braces: even a manual
    re-enqueue under a fresh job id cannot double-execute a run.
    """
    token = uuid.uuid4()
    for attempt in (1, 2):
        try:
            async with session_factory() as db:
                result: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
                    text(
                        "UPDATE agent_runs SET claimed_by = :who, claimed_at = now(), "
                        "lease_token = :token, heartbeat_at = now() "
                        "WHERE id = :run_id AND status = :running AND claimed_by IS NULL"
                    ),
                    {
                        "who": claimed_by,
                        "token": token,
                        "run_id": run_id,
                        "running": AgentRunStatus.running.value,
                    },
                )
                await db.commit()
                if result.rowcount != 1:
                    return None
            return RunLease(run_id=run_id, token=token, claimed_by=claimed_by)
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(2.0)
    return None  # pragma: no cover — loop always returns/raises


async def heartbeat_run(
    session_factory: async_sessionmaker[AsyncSession],
    lease: RunLease,
) -> bool:
    """Fenced liveness write. ``False`` = the run was settled elsewhere.

    Best-effort on transport errors (a transient DB blip must not kill a
    healthy run — the write is retried on the next beat; the sweep
    threshold is 8 missed beats deep): only a SUCCESSFUL write that hits
    zero rows is a settlement signal.
    """
    try:
        async with session_factory() as db:
            result: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
                text(
                    "UPDATE agent_runs SET heartbeat_at = now() "
                    "WHERE id = :run_id AND status = :running AND lease_token = :token"
                ),
                {
                    "run_id": lease.run_id,
                    "running": AgentRunStatus.running.value,
                    "token": lease.token,
                },
            )
            await db.commit()
            return result.rowcount == 1
    except Exception:
        logger.warning(
            "agent run heartbeat write failed (transient; next beat retries)",
            extra={"event": "agent_run_heartbeat_failed", "run_id": str(lease.run_id)},
        )
        return True


async def settle_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    *,
    status: AgentRunStatus,
    final_answer: str | None = None,
    error: str | None = None,
    total_tokens: int | None = None,
    lease_token: uuid.UUID | None = None,
) -> bool:
    """The one terminal write. ``True`` when THIS call settled the run.

    ``WHERE status='running'`` enforces terminal-status monotonicity for
    every caller; ``lease_token`` additionally fences a worker-side
    settle so a zombie can never overwrite its successor's state.
    Fresh-session, retry-once (the F0-S2 ``_finalize`` posture: the
    driving session can be poisoned when a cancellation lands mid-commit).
    A double failure is logged, not raised — the orphan sweep is the
    backstop that finally settles the row.
    """
    params: dict[str, object] = {
        "run_id": run_id,
        "running": AgentRunStatus.running.value,
        "status": status.value,
        "final_answer": final_answer,
        "error": error,
        # F2 Slice G (ADR-F051 follow-up): the run's cumulative model tokens, NULL when
        # not reported / settled off the normal path. The single terminal write owns it.
        "total_tokens": total_tokens,
    }
    fence_sql = ""
    if lease_token is not None:
        fence_sql = " AND lease_token = :token"
        params["token"] = lease_token
    for attempt in (1, 2):
        try:
            async with session_factory() as db:
                result: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
                    text(
                        "UPDATE agent_runs SET status = :status, "
                        "final_answer = :final_answer, error = :error, "
                        "total_tokens = :total_tokens, finished_at = now() "
                        "WHERE id = :run_id AND status = :running" + fence_sql
                    ),
                    params,
                )
                await db.commit()
                settled = result.rowcount == 1
                if not settled:
                    logger.info(
                        "agent run terminal write skipped — settled elsewhere",
                        extra={
                            "event": "agent_run_settle_skipped",
                            "run_id": str(run_id),
                            "intended_status": status.value,
                        },
                    )
                return settled
        except Exception:
            if attempt == 2:
                logger.exception(
                    "agent run terminal write failed twice; sweep will settle",
                    extra={"event": "agent_run_settle_failed", "run_id": str(run_id)},
                )
                return False
            await asyncio.sleep(2.0)
    return False  # pragma: no cover — loop always returns
