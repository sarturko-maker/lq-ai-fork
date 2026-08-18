"""ARQ worker function for the email-intake processing pipeline — INTAKE-1 (ADR-F086).

``POST /internal/intake/emails`` (``app.api.intake_emails``) enqueues this
job (via :func:`app.workers.queue.enqueue_intake_email_job`) onto the
shared ``arq:m3a6`` queue after landing an inbound envelope: idempotency
check, thread upsert, eager candidate-project creation, attachment ingest,
and the ``intake_messages`` row are all already committed by the time this
job runs.

STUB (this slice — INTAKE-1 is pure substrate, no agent, no LLM call
anywhere): the real body — composing the bound area agent, launching ONE
deep-agent run per inbound message (`enqueue_agent_run_job`, reusing
``intake_threads.agent_thread_id`` across follow-ups so the SAME agent
conversation continues), and wiring the run's `record_intake_outcome`
back onto ``intake_threads``/``projects.intake_state`` — is INTAKE-3
(`docs/fork/plans/INTAKE-INBOX-plan.md`). For now this only logs a
structured event and returns, so the substrate (envelope landing,
idempotency, eager project, attachment ingest) is independently verifiable
end-to-end with curl before any agent code exists.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Function name registered on the worker — must match the constant in
# :mod:`app.workers.queue` so the api-side enqueue helper targets the right
# function on the shared playbook queue.
INTAKE_EMAIL_JOB_NAME = "intake_email_job"


async def intake_email_job(ctx: dict[str, Any], thread_id_str: str) -> dict[str, Any]:
    """ARQ job — process one newly-landed inbound message on an intake thread.

    STUB (INTAKE-1): logs a structured event (thread id only — never email
    content) and returns. INTAKE-3 replaces this body with the real
    bound-area-agent run.
    """

    log.info(
        "intake_email_job: stub invocation (INTAKE-3 fills in the real run)",
        extra={"event": "intake_email_job_stub", "thread_id": thread_id_str},
    )
    return {"thread_id": thread_id_str, "status": "stub"}
