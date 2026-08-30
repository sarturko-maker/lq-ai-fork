"""enqueue/abort queue helpers — F1-S1 (ADR-F009).

Pins the None-collision → False mapping (verified arq 0.26.3 behavior:
``enqueue_job`` silently returns ``None`` when a job/result key with the
same id exists) and the best-effort posture of abort. The pool is
replaced at the module seam (no live Redis in unit tests); the arq
transport itself is exercised by live verification.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest

from app.workers import queue as queue_module
from app.workers.queue import (
    AGENT_RUN_JOB_NAME,
    abort_agent_run_job,
    agent_run_job_id,
    enqueue_agent_run_job,
    enqueue_intake_email_job,
    intake_email_job_id,
)

pytestmark = pytest.mark.unit


class _FakePool:
    def __init__(self, *, result: Any = object(), boom: Exception | None = None) -> None:
        self._result = result
        self._boom = boom
        self.calls: list[tuple[Any, ...]] = []
        self.kwargs: list[dict[str, Any]] = []

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(args)
        self.kwargs.append(kwargs)
        if self._boom is not None:
            raise self._boom
        return self._result


def _pool_getter(pool: _FakePool) -> Any:
    async def _get() -> _FakePool:
        return pool

    return _get


async def test_enqueue_uses_the_deterministic_job_id() -> None:
    run_id = uuid.uuid4()
    pool = _FakePool()
    with patch.object(queue_module, "_get_m3a6_pool", new=_pool_getter(pool)):
        assert await enqueue_agent_run_job(run_id) is True
    assert pool.calls == [(AGENT_RUN_JOB_NAME, str(run_id))]
    assert pool.kwargs == [{"_job_id": agent_run_job_id(run_id)}]
    assert agent_run_job_id(run_id) == f"agent-run:{run_id}"


async def test_enqueue_collision_none_maps_to_false() -> None:
    """arq's silent job-id-collision return must read as NOT QUEUED —
    the caller settles the run failed (never a silent zombie)."""
    pool = _FakePool(result=None)
    with patch.object(queue_module, "_get_m3a6_pool", new=_pool_getter(pool)):
        assert await enqueue_agent_run_job(uuid.uuid4()) is False


async def test_enqueue_transport_failure_maps_to_false() -> None:
    pool = _FakePool(boom=ConnectionError("redis down"))
    with patch.object(queue_module, "_get_m3a6_pool", new=_pool_getter(pool)):
        assert await enqueue_agent_run_job(uuid.uuid4()) is False


async def test_abort_is_best_effort_on_transport_failure() -> None:
    """The cancel endpoint already settled the row — abort must never
    raise back into the request."""

    async def _exploding_pool() -> Any:
        raise ConnectionError("redis down")

    with patch.object(queue_module, "_get_m3a6_pool", new=_exploding_pool):
        await abort_agent_run_job(uuid.uuid4())  # must not raise


# --------------------------------------------------------------------------- #
# INTAKE-4b (ADR-F087): the intake job id is REUSED, so a refusal must surface
# --------------------------------------------------------------------------- #


class _JobIdPool:
    """A pool that models arq's real job-key semantics.

    ``enqueue_job`` returns ``None`` while the id is still known — queued,
    running, or holding an ``arq:result:<id>`` key — and a real job object once
    it is free again. :meth:`finish` is the moment a job completes with
    ``keep_result=0``: the id becomes reusable immediately.
    """

    def __init__(self) -> None:
        self.known: set[str] = set()
        self.kwargs: list[dict[str, Any]] = []

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> Any:
        self.kwargs.append(kwargs)
        job_id = kwargs["_job_id"]
        if job_id in self.known:
            return None
        self.known.add(job_id)
        return object()

    def finish(self, job_id: str) -> None:
        self.known.discard(job_id)


async def test_intake_enqueue_reports_a_refused_job_id() -> None:
    """Enqueue twice in a row: the second is REFUSED and must read as False.

    It used to return True regardless, which is what made requeue-on-settle a
    silent no-op — the hook believed it had handed the message back.
    """
    thread_id = uuid.uuid4()
    pool = _JobIdPool()
    with patch.object(queue_module, "_get_m3a6_pool", new=_pool_getter(pool)):  # type: ignore[arg-type]
        assert await enqueue_intake_email_job(thread_id, provider_message_id="<m1@x>") is True
        assert await enqueue_intake_email_job(thread_id, provider_message_id="<m1@x>") is False
    assert pool.kwargs[0] == {"_job_id": intake_email_job_id(thread_id, "<m1@x>")}


async def test_intake_enqueue_works_again_once_the_job_finished() -> None:
    """What ``keep_result=0`` buys: the id is reusable the moment the job is
    done, so the requeue hook can re-run the SAME (thread, message) that an
    earlier attempt deferred. With arq's default the id stayed refused for an
    hour and the message starved (ADR-F087)."""
    thread_id = uuid.uuid4()
    job_id = intake_email_job_id(thread_id, "<m1@x>")
    pool = _JobIdPool()
    with patch.object(queue_module, "_get_m3a6_pool", new=_pool_getter(pool)):  # type: ignore[arg-type]
        assert await enqueue_intake_email_job(thread_id, provider_message_id="<m1@x>") is True
        pool.finish(job_id)  # the job ran (returned "deferred") and kept no result
        assert await enqueue_intake_email_job(thread_id, provider_message_id="<m1@x>") is True


async def test_a_different_message_is_never_deduped_against_another() -> None:
    thread_id = uuid.uuid4()
    pool = _JobIdPool()
    with patch.object(queue_module, "_get_m3a6_pool", new=_pool_getter(pool)):  # type: ignore[arg-type]
        assert await enqueue_intake_email_job(thread_id, provider_message_id="<m1@x>") is True
        assert await enqueue_intake_email_job(thread_id, provider_message_id="<m2@x>") is True
    assert intake_email_job_id(thread_id, "<m1@x>") != intake_email_job_id(thread_id, "<m2@x>")


async def test_intake_enqueue_transport_failure_maps_to_false() -> None:
    pool = _FakePool(boom=ConnectionError("redis down"))
    with patch.object(queue_module, "_get_m3a6_pool", new=_pool_getter(pool)):
        assert await enqueue_intake_email_job(uuid.uuid4(), provider_message_id="<m@x>") is False
