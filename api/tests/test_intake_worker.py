"""Unit tests for the INTAKE-1 (ADR-F086) worker registration + stub job.

Mirrors ``tests/test_arq_smoke.py``'s pattern: the drift-guard asserts
``intake_email_job`` is actually discoverable by the arq CLI (registered in
``WorkerSettings.functions``), and a direct-invocation test pins the stub's
contract (logs + returns, never raises) so INTAKE-3 has a clean baseline to
replace.
"""

from __future__ import annotations

import pytest

from app.workers.arq_setup import WorkerSettings
from app.workers.intake_worker import INTAKE_EMAIL_JOB_NAME, intake_email_job
from app.workers.queue import INTAKE_EMAIL_JOB_NAME as QUEUE_SIDE_JOB_NAME


@pytest.mark.unit
def test_intake_email_job_registered_on_worker_settings() -> None:
    """Drift-guard: the worker actually consumes the job the api enqueues.

    A discrepancy here means ``POST /internal/intake/emails`` would enqueue
    a job name the arq-worker container never registered — jobs pile up on
    the queue and are silently never executed.
    """

    assert intake_email_job in WorkerSettings.functions


@pytest.mark.unit
def test_job_name_constants_match_across_api_and_worker() -> None:
    """The api-side enqueue helper and the worker-side function name must
    agree byte-for-byte, or the worker rejects every enqueued job."""

    assert INTAKE_EMAIL_JOB_NAME == QUEUE_SIDE_JOB_NAME == "intake_email_job"


@pytest.mark.unit
async def test_intake_email_job_stub_logs_and_returns() -> None:
    result = await intake_email_job({}, "11111111-1111-1111-1111-111111111111")
    assert result == {
        "thread_id": "11111111-1111-1111-1111-111111111111",
        "status": "stub",
    }
