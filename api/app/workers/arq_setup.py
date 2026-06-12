"""Shared playbook ``arq`` worker — background jobs for Easy Playbook
generation (M3-A6) and Tabular Review execution (M3-C2).

Sister worker to :mod:`app.workers.document_pipeline` (the ``ingest-worker``
container). Both processes share the same Redis instance for coordination
but consume from **disjoint queues** so a backlog of one workload does not
delay the other.

Why a separate queue
--------------------

Long-running jobs — both Easy Playbook generation (PRD §3.7 NFR up to
10 minutes for a 10-document corpus) and Tabular Review execution (up
to 200 docs x 10 cols = 2000 cells over hours per Phase C prep doc
Decision C-3) — landing on the default ``arq:queue`` would compete
with document-ingest jobs and either side could starve the other
depending on queue depth. Worse, each worker would receive jobs whose
function name it does not register and reject them.

The worker therefore declares ``queue_name = M3_PLAYBOOK_QUEUE_NAME``
and the API-side enqueue helpers build their pool with
``default_queue_name=M3_PLAYBOOK_QUEUE_NAME`` so the playbook +
tabular pipelines never mix with the ingest pipeline.

Why share the queue between Easy Playbook + Tabular
---------------------------------------------------

Per Decision C-3: two arq containers per deployment would double the
operational surface for no isolation win — both workloads are bursty
in different shapes (Easy Playbook = 1-10 docs over ~10 min; Tabular =
up to 2000 cells over hours), but neither saturates a worker long
enough to deserve isolation. If we see queue contention in production,
splitting is a follow-on PR; the queue string stays ``arq:m3a6`` for
on-the-wire compatibility (rename is constant-name-only).

Registered functions:

* ``noop_job`` — lightweight "is the worker consuming?" health probe.
* :func:`app.workers.easy_playbook_worker.easy_playbook_generation_job`
  (M3-A6) — Easy Playbook generation pipeline.
* :func:`app.workers.tabular_worker.tabular_execution_job`
  (M3-C2) — Tabular Review execution pipeline.
* :func:`app.workers.autonomous_worker.autonomous_session_job`
  (M4-A2) — Autonomous Session execution pipeline.
* :func:`app.workers.agent_run_worker.agent_run_job`
  (F1-S1, ADR-F009) — deep-agent run execution, at-most-once
  (per-function ``max_tries=1``; lease claim before composing).

Registered cron jobs:

* :func:`app.workers.autonomous_worker.autonomous_idle_watchdog`
  (M4-A4-ii) — Idle-halt watchdog; runs at the top of every minute
  (``second=0``). Reaps sessions that have gone idle via a two-tick
  ``running → paused → halted`` lifecycle.
* :func:`app.workers.autonomous_worker.autonomous_schedule_dispatcher`
  (M4-B3) — Schedule dispatcher; runs at the top of every minute
  (``second=0``). Spawns one session per due schedule
  (``enabled AND deleted_at IS NULL AND next_run_at <= now()``) and
  advances ``next_run_at`` from the schedule's ``cron_expr``.
* :func:`app.workers.agent_run_worker.agent_run_orphan_sweep`
  (F1-S1) — every minute at ``second=30``; settles orphaned agent runs
  as FAILED (also runs once at startup).
* :func:`app.workers.agent_run_worker.checkpoint_gc_job`
  (F1-S1) — daily 04:30; deletes checkpoint lineages whose
  conversation row is gone.

Discovered by the ``arq`` CLI via::

    arq app.workers.arq_setup.WorkerSettings

See ``docker-compose.yml`` (``arq-worker`` service).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, ClassVar

from app.agents.checkpointer import close_agent_checkpointer, init_agent_checkpointer
from app.config import get_settings
from app.db.session import dispose_engine
from app.workers.agent_run_worker import (
    AGENT_RUN_JOB_TIMEOUT_SECONDS,
    agent_run_job,
    agent_run_orphan_sweep,
    checkpoint_gc_job,
)
from app.workers.autonomous_worker import (
    autonomous_idle_watchdog,
    autonomous_schedule_dispatcher,
    autonomous_session_job,
)
from app.workers.easy_playbook_worker import easy_playbook_generation_job
from app.workers.tabular_worker import tabular_execution_job

log = logging.getLogger(__name__)


M3_PLAYBOOK_QUEUE_NAME = "arq:m3a6"
"""Dedicated arq queue for shared playbook + tabular background work.
Disjoint from the ingest-worker's default ``arq:queue`` so a backlog
on either side does not affect the other.

Queue string stays ``arq:m3a6`` (the original M3-A6 name) for
on-the-wire compatibility — only the Python constant was renamed to
better describe its current workload (Easy Playbook + Tabular share
this queue per Phase C prep doc Decision C-3). The
:data:`M3A6_QUEUE_NAME` alias below stays exported for one release so
in-flight code / external integrations keep working."""

M3A6_QUEUE_NAME = M3_PLAYBOOK_QUEUE_NAME
"""Backward-compat alias for the renamed :data:`M3_PLAYBOOK_QUEUE_NAME`.
Will be removed in a future release; new code should use
:data:`M3_PLAYBOOK_QUEUE_NAME`."""


# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------


async def noop_job(ctx: dict[str, Any]) -> str:
    """Smoke-test job: returns ``"ok"``.

    Kept indefinitely after Phase 5 lands the real easy-playbook
    function — it's a tiny, dependency-free hook that the smoke test
    (and any future health probe) can enqueue to verify the worker is
    consuming from the M3-A6 queue.
    """

    log.info(
        "arq_setup.noop_job: executed",
        extra={"event": "arq_m3a6_noop"},
    )
    return "ok"


# ---------------------------------------------------------------------------
# Worker startup / shutdown
# ---------------------------------------------------------------------------


async def on_startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook — install the skill registry, then log boot.

    The autonomous executor resolves ``skill_ref`` session targets via
    ``app.state.skill_registry`` (see
    :func:`app.autonomous.prompts._registry_from_app_state`) in whichever
    process runs the job. ``autonomous_session_job`` runs HERE, so this
    worker must install the registry exactly like the FastAPI lifespan
    does — historically only the api did, and every worker-side
    ``skill_ref`` session (scheduled, watch, Run-now) died at analysis
    with "skill registry not initialised".

    Fail-loudly posture (deliberate): if the skills directory is
    missing/unreadable or ``load_registry`` raises, the exception
    propagates and the worker process exits at startup. An operator sees
    a crash-looping container immediately instead of discovering the
    first scheduled 9 AM tick failed hours later.
    """

    # Deferred imports: app.main builds the full FastAPI app (router
    # tree, middleware). Importing it at module top would make every
    # `arq ...WorkerSettings` CLI discovery and unit-test import pay
    # that cost, and mirrors the deferred-import precedent in
    # app.autonomous.prompts._registry_from_app_state.
    from app.main import app
    from app.skills.bootstrap import install_skill_registry

    # No try/except: propagation is the contract (see docstring).
    holder = install_skill_registry(app, get_settings())
    skill_count = len(holder.current().names())
    log.info(
        "arq-worker startup: skill registry installed (%d skills)",
        skill_count,
        extra={
            "event": "arq_worker_skill_registry_installed",
            "skill_count": skill_count,
        },
    )

    # F1-S1 (ADR-F009): agent runs execute HERE — the worker needs the
    # langgraph checkpointer exactly like the api lifespan. Init failure
    # degrades (runs execute single-shot; follow-ups refused), never
    # crashes the worker — the api's posture, mirrored.
    await init_agent_checkpointer()

    # Startup orphan sweep: settle any 'running' rows left behind by a
    # dead worker (or by the pre-S1 BackgroundTasks model) before this
    # worker takes new jobs — the ingest worker's startup-sweep
    # precedent, with settle-FAILED instead of re-enqueue (ADR-F009).
    try:
        result = await agent_run_orphan_sweep(ctx)
        if result.get("swept"):
            log.warning(
                "arq-worker startup: orphan sweep settled %s run(s)", result["swept"]
            )
    except Exception:
        log.exception("arq-worker startup: orphan sweep failed (cron retries)")

    log.info(
        "arq-worker startup: playbook queue=%s ready",
        M3_PLAYBOOK_QUEUE_NAME,
        # Event name kept stable for log-query consumers; the queue
        # value uses the renamed constant (same string either way).
        extra={"event": "arq_m3a6_startup", "queue": M3_PLAYBOOK_QUEUE_NAME},
    )


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook — close the checkpointer, dispose the engine.

    Mirrors :mod:`app.workers.document_pipeline.on_shutdown`. Both
    closers are idempotent and best-effort; in-flight agent runs were
    already settled by :func:`agent_run_job`'s ``BaseException`` path
    (arq cancels running tasks before this hook fires).
    """

    log.info("arq-worker shutdown: closing checkpointer + disposing DB engine")
    try:
        await close_agent_checkpointer()
    except Exception as exc:  # pragma: no cover - shutdown best-effort
        log.warning("arq-worker shutdown: checkpointer close failed: %s", exc)
    try:
        await dispose_engine()
    except Exception as exc:  # pragma: no cover - shutdown best-effort
        log.warning("arq-worker shutdown: dispose_engine failed: %s", exc)


# ---------------------------------------------------------------------------
# arq WorkerSettings — discovered by ``arq <module>.WorkerSettings``
# ---------------------------------------------------------------------------


def _build_redis_settings() -> Any:
    """Build arq's ``RedisSettings`` from the configured ``REDIS_URL``.

    Lazy import so the module imports cleanly in environments where
    ``arq`` is not installed (matches the pattern in
    :mod:`app.workers.document_pipeline`).
    """

    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(get_settings().redis_url)


def _build_cron_jobs() -> list[Any]:
    """Build the arq cron_jobs list. Lazy import keeps arq optional at module load.

    Mirrors the pattern in :mod:`app.workers.document_pipeline._build_cron_jobs`.
    """

    from arq import cron

    return [
        # Every minute at second=0: reap idle autonomous sessions via
        # the two-tick running→paused→halted lifecycle (M4-A4-ii).
        cron(autonomous_idle_watchdog, second=0),
        # Every minute at second=0: spawn sessions for due schedules and
        # advance next_run_at from each schedule's cron_expr (M4-B3).
        cron(autonomous_schedule_dispatcher, second=0),
        # Every minute at second=30 (offset from the watchdogs): settle
        # orphaned agent runs as FAILED — F1-S1, ADR-F009.
        cron(agent_run_orphan_sweep, second=30),
        # Daily at 04:30 (offset from the 03:00 user hard-delete on the
        # ingest worker): delete checkpoint lineages whose thread row is
        # gone — F1-S1 retention.
        cron(checkpoint_gc_job, hour=4, minute=30),
    ]


class WorkerSettings:
    """arq worker configuration discovered by the arq CLI.

    See https://arq-docs.helpmanual.io/#workersettings for the schema.
    """

    functions: ClassVar[list[Any]] = [
        noop_job,
        easy_playbook_generation_job,
        tabular_execution_job,
        autonomous_session_job,
        # agent_run_job is appended by _populate_class_attrs wrapped in
        # arq's func() so it carries per-function max_tries=1 + its own
        # timeout (at-most-once, ADR-F009) without touching the legacy
        # jobs' defaults.
    ]
    queue_name: ClassVar[str] = M3_PLAYBOOK_QUEUE_NAME
    # F1-S1: lets the cancel endpoint deliver arq Job.abort() into a
    # running agent_run_job (asyncio cancellation). Inert for every job
    # nobody calls .abort() on.
    allow_abort_jobs: ClassVar[bool] = True
    # PRD §3.7 NFR caps generation at 10 min for a 10-doc corpus on the
    # default judge model. A 5-doc corpus is ~5 min, so the prior
    # default-300s ceiling cut runs off mid-assembly. 900s = NFR + 50%
    # headroom; a future tuning pass can lower it if cluster sizes
    # plateau lower than the worst case.
    job_timeout: ClassVar[int] = 900
    on_startup = on_startup
    on_shutdown = on_shutdown


def _populate_class_attrs() -> None:
    """Populate runtime-resolved class attrs (``redis_settings``, ``cron_jobs``).

    arq reads class attributes directly. We populate the attributes
    that need runtime values lazily so the module import succeeds even
    when arq is absent.

    Mirrors the pattern in :mod:`app.workers.document_pipeline._populate_class_attrs`.
    """

    # arq is a runtime dep but the import is deferred so this module loads
    # cleanly in environments where arq is absent (matching the pattern in
    # :mod:`app.workers.document_pipeline`).
    with contextlib.suppress(
        ImportError
    ):  # pragma: no cover - arq missing in some envs
        from arq.worker import func as arq_func

        WorkerSettings.redis_settings = _build_redis_settings()  # type: ignore[attr-defined]
        WorkerSettings.cron_jobs = _build_cron_jobs()  # type: ignore[attr-defined]
        if not any(
            getattr(f, "name", None) == "agent_run_job"
            for f in WorkerSettings.functions
        ):
            WorkerSettings.functions.append(
                # At-most-once (ADR-F009): max_tries=1 — verified at arq
                # 0.26.3 that job_try is checked BEFORE the body runs, so
                # post-crash redelivery settles without re-executing.
                arq_func(
                    agent_run_job,
                    max_tries=1,
                    timeout=AGENT_RUN_JOB_TIMEOUT_SECONDS,
                )
            )


_populate_class_attrs()
