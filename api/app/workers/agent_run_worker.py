"""Agent-run arq worker functions — F1-S1 (fork, ADR-F009).

Three responsibilities, one fragility family:

* :func:`agent_run_job` — execute one deep-agent run AT-MOST-ONCE.
  Registered with ``max_tries=1`` (arq 0.26.3 checks ``job_try``
  BEFORE the body runs, so post-crash redelivery settles arq-side
  without re-running the graph) and claims the run's lease before
  composing — the claim is the at-most-once belt over arq's braces.
* :func:`agent_run_orphan_sweep` — startup + every-minute cron that
  settles dead ``running`` rows as FAILED with an ``orphaned:`` error
  prefix. NEVER re-enqueues; resume is a user action (ADR-F009 — safe
  auto-resume needs the F1-S5 idempotency ledger).
* :func:`checkpoint_gc_job` — daily cron deleting checkpoint lineages
  whose ``agent_threads`` row is gone (user-cascade deletes, failed
  best-effort endpoint deletes). Uses the library's
  ``adelete_thread()`` API; only the DISCOVERY query reads the
  library-owned table directly (read-only, guarded for absence).

Core/wrapper split mirrors :mod:`app.workers.autonomous_worker`'s
``_run_idle_sweep`` pattern: the core functions take their dependencies
as arguments so tests drive them directly against the conftest test DB
(CLAUDE.md DI rules — no monkeypatching); the thin arq wrappers wire in
the process globals.

All timestamps compare on the DATABASE clock (``now()``) — the sweep
must never trust an app-server clock (see app/agents/lease.py).
"""

from __future__ import annotations

import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.checkpointer import get_agent_checkpointer
from app.agents.lease import claim_run, settle_run
from app.audit import audit_action
from app.config import get_settings
from app.db.session import get_session_factory
from app.schemas.agent_runs import AgentRunStatus

logger = logging.getLogger(__name__)

AGENT_RUN_JOB_NAME = "agent_run_job"
"""Function name the api-side enqueue helper targets — must match
:data:`app.workers.queue.AGENT_RUN_JOB_NAME`."""

# Runner wall clock (300s) + composition/finalize slack. Per-function
# override on the shared worker (its default job_timeout=900 serves the
# legacy playbook/tabular jobs).
AGENT_RUN_JOB_TIMEOUT_SECONDS = 420

# One tag per worker boot: host:pid:boot-uuid. The uuid component is
# what makes the tag unique across PID recycling / container restarts —
# the lease token (a fresh uuid per CLAIM) is the actual fencing value;
# this tag surfaces in LOGS, the DB column, and audit details only —
# never in user-facing error strings (internal identity, review fix).
_WORKER_BOOT_TAG = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


async def execute_run_job(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    *,
    claimed_by: str,
    compose: Callable[..., Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Claim → compose → execute one run, at-most-once (core).

    An unclaimable run (settled while queued by the cancel endpoint or
    the unclaimed-grace sweep; or a duplicate enqueue under a fresh job
    id) is an honest no-op.

    ``BaseException`` (arq ``Job.abort`` / worker-shutdown
    ``CancelledError`` — NOT ``Exception``) settles the row before
    re-raising so a graceful deploy is never a silent orphan factory;
    the fenced write no-ops when the cancel endpoint already won the
    row. Ordinary exceptions never reach arq: the composition point
    settles them as ``failed`` itself.
    """
    if compose is None:
        from app.agents.composition import compose_and_execute_run

        compose = compose_and_execute_run

    try:
        lease = await claim_run(session_factory, run_id, claimed_by=claimed_by)
    except Exception as exc:
        # Belt over claim_run's retry-once: surface a claim-time DB blip
        # to the user NOW (settle is status-conditional, monotonic-safe)
        # instead of after the claim-grace sweep minutes later.
        await settle_run(
            session_factory,
            run_id,
            status=AgentRunStatus.failed,
            error=f"claim failed: {type(exc).__name__}",
        )
        raise
    if lease is None:
        logger.info(
            "agent run not claimable (settled while queued, or already claimed)",
            extra={"event": "agent_run_unclaimable", "run_id": str(run_id)},
        )
        return {"run_id": str(run_id), "executed": False}
    try:
        await compose(run_id=run_id, lease=lease)
    except BaseException as exc:
        settled = await settle_run(
            session_factory,
            run_id,
            status=AgentRunStatus.failed,
            # Covers arq abort, worker SIGTERM shutdown, AND the arq
            # job timeout (420s) — all delivered as CancelledError.
            error=f"run interrupted: worker shutdown, abort, or job timeout ({type(exc).__name__})",
            lease_token=lease.token,
        )
        logger.warning(
            "agent run interrupted; row %s",
            "settled failed" if settled else "already settled elsewhere",
            extra={"event": "agent_run_interrupted", "run_id": str(run_id)},
        )
        raise
    return {"run_id": str(run_id), "executed": True}


async def agent_run_job(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    """arq wrapper around :func:`execute_run_job` (process globals)."""
    return await execute_run_job(
        get_session_factory(), uuid.UUID(run_id), claimed_by=_WORKER_BOOT_TAG
    )


async def run_orphan_sweep(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    orphan_after_seconds: float,
    claim_grace_seconds: float,
    abort_job: Callable[[uuid.UUID], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Settle dead ``running`` runs as FAILED (core; ADR-F009).

    Two rules, each one conditional UPDATE (atomic — concurrent sweeps
    race safely on rowcount; no SKIP LOCKED ceremony needed), predicate
    checked against the DB clock inside the UPDATE itself:

    * CLAIMED row whose ``heartbeat_at`` is stale → the worker died (or
      an event drought outlasted the threshold — fenced-safe, see
      ADR-F009). ``abort_job`` is then fired per settled run: a
      false-orphaned ZOMBIE is still executing and its checkpoint/step
      writes are not lease-fenced — the abort kills it within delivery
      latency instead of the 300s wall clock (review fix).
    * UNCLAIMED row older than the claim grace → the enqueue was lost
      after acceptance, the worker died between dequeue and claim, or
      the row predates F1-S1 (BackgroundTasks rows have no live runner
      by construction). The grace is sized ABOVE the shared queue's
      worst-case pickup delay (legacy jobs run up to 900s) so a
      legitimately queued run is never falsely failed.

    Settles are COMMITTED before any audit write: the audit rows ride a
    second transaction with per-row rollback-on-failure (the guard's
    F0-S4 lesson), so a poisoned audit insert can never roll back a
    settle — "audit failure never masks the settle" holds structurally.
    The user-visible error is a constant string; the worker identity
    (``claimed_by``) stays on the row + log/audit surfaces only.
    """
    swept: list[tuple[uuid.UUID, uuid.UUID, str, str | None]] = []
    async with session_factory() as db:
        stale = await db.execute(
            text(
                "UPDATE agent_runs SET status = :failed, finished_at = now(), "
                "error = 'orphaned: worker heartbeat stale' "
                "WHERE status = :running AND claimed_at IS NOT NULL "
                "AND heartbeat_at < now() - make_interval(secs => :orphan_after) "
                "RETURNING id, user_id, claimed_by"
            ),
            {
                "failed": AgentRunStatus.failed.value,
                "running": AgentRunStatus.running.value,
                "orphan_after": orphan_after_seconds,
            },
        )
        swept.extend(
            (row[0], row[1], "stale_heartbeat", row[2]) for row in stale.fetchall()
        )
        unclaimed = await db.execute(
            text(
                "UPDATE agent_runs SET status = :failed, finished_at = now(), "
                "error = 'orphaned: never claimed by a worker' "
                "WHERE status = :running AND claimed_at IS NULL "
                "AND started_at < now() - make_interval(secs => :claim_grace) "
                "RETURNING id, user_id, claimed_by"
            ),
            {
                "failed": AgentRunStatus.failed.value,
                "running": AgentRunStatus.running.value,
                "claim_grace": claim_grace_seconds,
            },
        )
        swept.extend(
            (row[0], row[1], "never_claimed", row[2]) for row in unclaimed.fetchall()
        )
        # The settles are durable BEFORE anything else can fail.
        await db.commit()

    if not swept:
        return {"swept": 0}

    # Audit pass — separate transaction; a failed insert rolls back ONLY
    # itself (guard.py:_audit posture) and never the settles above.
    async with session_factory() as db:
        for swept_run_id, user_id, reason, claimed_by in swept:
            try:
                await audit_action(
                    db,
                    user_id=user_id,
                    action="agent_run.orphan_settled",
                    resource_type="agent_run",
                    resource_id=str(swept_run_id),
                    details={"reason": reason, "claimed_by": claimed_by},
                )
                await db.commit()
            except Exception:
                logger.exception(
                    "orphan-settle audit write failed (settle stands)",
                    extra={
                        "event": "agent_run_sweep_audit_failed",
                        "run_id": str(swept_run_id),
                    },
                )
                try:
                    await db.rollback()
                except Exception:
                    logger.exception("rollback after failed sweep audit also failed")

    # Kill surviving zombies: a stale-heartbeat run may still be
    # EXECUTING (false orphan / long event drought) — best-effort abort.
    if abort_job is not None:
        for swept_run_id, _, reason, _ in swept:
            if reason == "stale_heartbeat":
                try:
                    await abort_job(swept_run_id)
                except Exception:
                    logger.exception(
                        "post-sweep abort failed (zombie bounded by wall clock)",
                        extra={
                            "event": "agent_run_sweep_abort_failed",
                            "run_id": str(swept_run_id),
                        },
                    )

    logger.warning(
        "orphan sweep settled %d agent run(s) as failed",
        len(swept),
        extra={
            "event": "agent_run_orphans_swept",
            "count": len(swept),
            "run_ids": [str(r[0]) for r in swept],
            "claimed_by": [r[3] for r in swept],
        },
    )
    return {"swept": len(swept)}


async def agent_run_orphan_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """arq cron/startup wrapper around :func:`run_orphan_sweep`."""
    from app.workers.queue import abort_agent_run_job

    settings = get_settings()
    return await run_orphan_sweep(
        get_session_factory(),
        orphan_after_seconds=settings.agent_run_orphan_after_seconds,
        claim_grace_seconds=settings.agent_run_claim_grace_seconds,
        abort_job=abort_agent_run_job,
    )


async def run_checkpoint_gc(
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: Any,
    *,
    batch_limit: int = 500,
) -> dict[str, Any]:
    """Delete checkpoint lineages whose conversation row is gone (core).

    The langgraph checkpointer's tables are library-owned (not alembic)
    and carry no FK to ``agent_threads`` — a user-cascade delete leaves
    the lineage orphaned (pre-S1 carry-over). Discovery reads the
    library table read-only (guarded: it may not exist when the saver
    never initialized); deletion goes through the library's own
    ``adelete_thread()``. Age-based pruning INSIDE live threads is
    deliberately out of scope (needs measured bloat + a retention
    policy call — see the F1-S1 plan's non-goals).
    """
    if checkpointer is None:
        logger.info("checkpoint GC skipped: checkpointer not initialized")
        return {"deleted_threads": 0, "skipped": True}
    async with session_factory() as db:
        exists = (
            await db.execute(text("SELECT to_regclass('checkpoints')"))
        ).scalar_one()
        if exists is None:
            return {"deleted_threads": 0, "skipped": True}
        rows = await db.execute(
            text(
                "SELECT DISTINCT c.thread_id FROM checkpoints c "
                "WHERE NOT EXISTS (SELECT 1 FROM agent_threads t "
                "WHERE t.id::text = c.thread_id) LIMIT :batch_limit"
            ),
            {"batch_limit": batch_limit},
        )
        orphaned = [row[0] for row in rows.fetchall()]
    deleted = 0
    for thread_id in orphaned:
        try:
            await checkpointer.adelete_thread(thread_id)
            deleted += 1
        except Exception:
            logger.exception(
                "checkpoint GC failed for thread lineage (next pass retries)",
                extra={"event": "checkpoint_gc_failed", "thread_id": thread_id},
            )
    if deleted:
        logger.info(
            "checkpoint GC deleted %d orphaned lineage(s)",
            deleted,
            extra={"event": "checkpoint_gc_done", "deleted": deleted},
        )
    return {"deleted_threads": deleted, "skipped": False}


async def checkpoint_gc_job(ctx: dict[str, Any]) -> dict[str, Any]:
    """arq daily-cron wrapper around :func:`run_checkpoint_gc`."""
    return await run_checkpoint_gc(get_session_factory(), get_agent_checkpointer())
