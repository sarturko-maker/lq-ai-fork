"""arq queue helpers — enqueue document-ingest jobs from the API process.

Per ADR 0006 §5: the API's upload handler enqueues an ingest job
after the file row is committed. This module is the API-side helper
for that path. The worker process consumes the queue (see
:mod:`app.workers.document_pipeline`).

Design notes
------------

* The arq queue connection is built from the same ``REDIS_URL`` the
  rest of the API uses (via ``get_settings()``). It's cached as a
  module-global so the API process pools the connection across
  requests rather than reconnecting per upload.
* Enqueue failures are non-fatal for the upload: the upload handler
  catches and logs at WARNING. A row stuck at ``pending`` will be
  swept up by the worker's startup re-enqueue (see
  :mod:`app.workers.document_pipeline`).
* The job name (``ingest_file_job``) is the function the worker
  invokes; the function lives on the worker side. We enqueue by
  string name to avoid pulling worker-only deps into the API
  process.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

log = logging.getLogger(__name__)

# Job-function name on the worker side. Must match the function name
# in :mod:`app.workers.document_pipeline`.
INGEST_JOB_NAME = "ingest_file_job"

EMBED_JOB_NAME = "embed_chunks_for_file_job"
"""C6 — embedding-on-write job for ``document_chunks`` of a single
file. Triggered on KB attachment (when the file has chunks with NULL
embeddings) and from the ingest-completion hook."""

EXPORT_USER_DATA_JOB_NAME = "export_user_data_job"
"""D6 — GDPR Article 20 export job. Triggered by the API when a user
calls ``POST /api/v1/users/me/export``; the worker assembles the ZIP
and writes it to MinIO under ``exports/<user_id>/<job_id>.zip``."""

_pool: Any = None


async def _get_pool() -> Any:
    """Return a cached arq Redis pool, building it on first use.

    arq is imported lazily so the API process imports cleanly even
    when arq isn't installed (it's a runtime dep but we want the
    import path to fail loudly in tests where arq is mocked rather
    than failing at module import).
    """

    global _pool
    if _pool is not None:
        return _pool

    from arq import create_pool
    from arq.connections import RedisSettings

    from app.config import get_settings

    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    _pool = await create_pool(redis_settings)
    return _pool


async def close_pool() -> None:
    """Close the cached arq Redis pool. Idempotent."""

    global _pool
    if _pool is None:
        return
    try:
        await _pool.aclose()
    except Exception as exc:  # pragma: no cover - shutdown best-effort
        log.warning("close_pool: arq pool close failed: %s", exc)
    finally:
        _pool = None


async def enqueue_ingest_job(file_id: uuid.UUID) -> bool:
    """Enqueue an ingest job for ``file_id``; return True on success.

    Failures are caught and logged — the caller (upload handler)
    treats failure as non-fatal. The row stays at ``pending`` and
    will be re-enqueued by the worker's startup sweep.
    """

    try:
        pool = await _get_pool()
        await pool.enqueue_job(INGEST_JOB_NAME, str(file_id))
        log.info(
            "enqueue_ingest_job: enqueued",
            extra={"event": "ingest_enqueue", "file_id": str(file_id)},
        )
        return True
    except Exception as exc:
        log.warning(
            "enqueue_ingest_job: failed; row stays pending",
            extra={
                "event": "ingest_enqueue_failed",
                "file_id": str(file_id),
                "error": str(exc),
            },
        )
        return False


async def enqueue_embed_job(file_id: uuid.UUID) -> bool:
    """Enqueue an embed-chunks job for ``file_id``; return True on success.

    Triggered from the KB attach handler when a newly-attached file has
    chunks with NULL embeddings. Failures are non-fatal — the lazy
    embed-on-read path in the query handler covers the gap.
    """

    try:
        pool = await _get_pool()
        await pool.enqueue_job(EMBED_JOB_NAME, str(file_id))
        log.info(
            "enqueue_embed_job: enqueued",
            extra={"event": "embed_enqueue", "file_id": str(file_id)},
        )
        return True
    except Exception as exc:
        log.warning(
            "enqueue_embed_job: failed; embed-on-read will cover at query time",
            extra={
                "event": "embed_enqueue_failed",
                "file_id": str(file_id),
                "error": str(exc),
            },
        )
        return False


async def enqueue_user_export_job(job_id: uuid.UUID) -> bool:
    """Enqueue a D6 GDPR export job; return True on success.

    Failures here surface to the API endpoint which keeps the job row
    at ``status='queued'`` and returns 202 to the caller (the user can
    retry). The status-poll endpoint will report queued indefinitely
    until the worker picks it up — operators monitoring the
    ``user_export_jobs`` table for stale rows can re-enqueue manually.
    """

    try:
        pool = await _get_pool()
        await pool.enqueue_job(EXPORT_USER_DATA_JOB_NAME, str(job_id))
        log.info(
            "enqueue_user_export_job: enqueued",
            extra={"event": "user_export_enqueue", "job_id": str(job_id)},
        )
        return True
    except Exception as exc:
        log.warning(
            "enqueue_user_export_job: failed; job stays queued",
            extra={
                "event": "user_export_enqueue_failed",
                "job_id": str(job_id),
                "error": str(exc),
            },
        )
        return False
