"""ARQ worker function for the Playbook EXECUTION pipeline — CLEAN-3a (HS-6).

The ``POST /api/v1/playbooks/{id}/execute`` handler creates a
:class:`PlaybookExecution` row at ``status='pending'`` and enqueues this job
(via :func:`app.workers.queue.enqueue_playbook_execution_job`) onto the shared
playbook queue (``arq:m3a6``). This replaces the previous FastAPI
``BackgroundTasks`` kick-off so execution runs on the ``arq-worker`` process
rather than the api — the api stays multi-replica-clean (HS-6).

Distinct from :func:`app.workers.easy_playbook_worker.easy_playbook_generation_job`,
which GENERATES a draft playbook from a corpus; this EXECUTES an existing
playbook against one target document via the LangGraph executor.

The worker picks up the job, resolves a :class:`GatewayClient`, opens its own
session via the standard factory, and dispatches to
:func:`app.playbooks.executor.run_playbook_execution`. The executor manages the
lifecycle (``pending → running → completed | error``) internally; this
function's responsibility is the orchestration layer around it.

Durability note: unlike the deep-agent runner (F1-S1/ADR-F009) there is no
lease/heartbeat/orphan-sweep for ``PlaybookExecution`` yet — a worker killed
mid-run leaves the row at ``running`` with no reaper, exactly as the old
BackgroundTasks path did. Closing that gap (schema migration + sweep) is
CLEAN-3b.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import update

from app.db.session import get_session_factory
from app.models.playbook import PlaybookExecution
from app.playbooks.executor import PlaybookExecutorError, run_playbook_execution

if TYPE_CHECKING:
    from app.clients.gateway import GatewayClient

logger = logging.getLogger(__name__)


# Function name registered on the worker — must match the constant in
# :mod:`app.workers.queue` so the api-side enqueue helper targets the right
# function on the shared playbook queue.
PLAYBOOK_EXECUTION_JOB_NAME = "playbook_execution_job"


async def playbook_execution_job(ctx: dict[str, Any], execution_id_str: str) -> dict[str, Any]:
    """ARQ job — run the Playbook Execution pipeline for one execution row.

    Lifecycle (delegated to :func:`run_playbook_execution`):

    * On entry: ``pending → running``.
    * On success: ``running → completed`` (the compile node writes ``results``).
    * On in-graph exception: ``running → error`` (the executor persists it and
      does NOT re-raise).
    * On start refusal: the executor writes ``error`` and raises
      :class:`PlaybookExecutorError`.

    This wrapper additionally handles:

    * Missing row — graceful early return.
    * ``PlaybookExecutorError`` — the executor already committed ``error``; log
      and report (mirrors the old ``_run_in_background`` catch).
    * ``BaseException`` (arq ``job_timeout`` cancellation / ``SystemExit``) —
      the executor's ``except Exception`` does not catch these, so write the
      ``error`` terminal state ourselves then re-raise so arq's shutdown
      machinery still sees the cancel. Mirrors
      :func:`app.workers.tabular_worker.tabular_execution_job`.

    Note the status vocabulary is ``error`` (the ``PlaybookExecution`` CHECK
    constraint allows ``pending/running/completed/error``) — NOT ``failed`` as
    the tabular/agent-run rows use.

    Returns a small dict for arq's result-tracking. All real state lives on the
    execution row.
    """

    execution_id = uuid.UUID(execution_id_str)
    logger.info(
        "playbook_worker: job start",
        extra={"event": "playbook_worker_start", "execution_id": execution_id_str},
    )

    factory = get_session_factory()

    async with factory() as session:
        execution = await session.get(PlaybookExecution, execution_id)
        if execution is None:
            logger.warning(
                "playbook_worker: row not found; nothing to do",
                extra={"event": "playbook_worker_row_missing", "execution_id": execution_id_str},
            )
            return {"execution_id": execution_id_str, "status": "missing"}

        gateway = _gateway_from_ctx(ctx)
        try:
            await run_playbook_execution(
                session,
                execution_id=execution_id,
                gateway=gateway,
            )
        except PlaybookExecutorError as exc:
            # The executor already committed status='error' before raising;
            # log so the job doesn't surface as an unhandled exception.
            logger.warning(
                "playbook_worker: executor refused to start",
                extra={
                    "event": "playbook_worker_refused",
                    "execution_id": execution_id_str,
                    "reason": str(exc),
                },
            )
            return {"execution_id": execution_id_str, "status": "error", "error": str(exc)}
        except BaseException as exc:
            # The executor catches Exception subclasses internally but not
            # BaseException (CancelledError, SystemExit). On those paths, write
            # an 'error' terminal state ourselves so the row doesn't get stuck
            # at 'running' indefinitely.
            logger.exception(
                "playbook_worker: pipeline failed at orchestration layer",
                extra={
                    "event": "playbook_worker_orchestration_error",
                    "execution_id": execution_id_str,
                    "error_type": type(exc).__name__,
                },
            )
            await session.execute(
                update(PlaybookExecution)
                .where(PlaybookExecution.id == execution_id)
                .values(
                    status="error",
                    error=f"{type(exc).__name__}: {exc}"[:2000],
                    completed_at=datetime.now(UTC),
                )
            )
            await session.commit()
            # Re-raise BaseException subclasses after bookkeeping so arq's
            # shutdown machinery still sees the cancel.
            if not isinstance(exc, Exception):
                raise
            return {"execution_id": execution_id_str, "status": "error", "error": str(exc)}

        logger.info(
            "playbook_worker: job complete",
            extra={"event": "playbook_worker_complete", "execution_id": execution_id_str},
        )
        return {"execution_id": execution_id_str, "status": "completed"}


def _gateway_from_ctx(ctx: dict[str, Any]) -> GatewayClient:
    """Resolve a :class:`GatewayClient` from the arq worker ``ctx``.

    Mirrors :func:`app.workers.tabular_worker._gateway_from_ctx` — builds one on
    demand via the api's standard factory if the worker didn't pre-populate
    ``ctx['gateway']`` at startup.
    """

    # Lazy import — keeps the worker module importable in environments where the
    # gateway client isn't yet configured.
    from app.clients.gateway import GatewayClient, get_gateway_client

    existing = ctx.get("gateway")
    if isinstance(existing, GatewayClient):
        return existing
    return get_gateway_client()
