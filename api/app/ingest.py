"""Packaged file-ingest service — INTAKE-1 (ADR-F086).

``ingest_bytes()`` is the shared "bytes in, ``File`` row out" primitive:
validate → sha256 → storage_path → ``app.storage.upload_bytes`` → ``files``
row → ``enqueue_ingest_job`` (non-fatal). It was extracted from
``app.api.files.upload_file`` (Task C4's HTTP upload handler, which still
owns multipart-specific concerns: streaming the request body, the
``project_id`` form field, and the audit-log write) so a second caller —
the email-intake bridge endpoint (``app.api.intake_emails``), which already
holds fully-decoded attachment bytes with no HTTP request to stream from —
can reuse the exact same validation, storage, and enqueue semantics instead
of re-implementing them.

Dependency injection: both ``session`` (the caller's transaction — this
function only ``add``s + flushes, it never commits, so callers can batch
several ingests plus their own writes into one atomic commit) and
``settings`` are passed in explicitly. No module-level singleton, no
``get_settings()``/``get_db()`` call inside this module.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import PayloadTooLarge, ValidationError
from app.models.file import File
from app.storage import delete_object, upload_bytes

log = logging.getLogger(__name__)

# Default MIME for bytes that arrive with no declared content type. Same
# fallback the IETF recommends for "we have no idea what kind of bytes
# these are" — canonical home for the constant; app.api.files re-exports it
# so the HTTP route's docstrings/behavior stay unchanged.
DEFAULT_MIME = "application/octet-stream"


async def ingest_bytes(
    *,
    session: AsyncSession,
    settings: Settings,
    owner_id: uuid.UUID,
    project_id: uuid.UUID | None,
    filename: str,
    content_type: str | None,
    data: bytes,
    created_by_run_id: uuid.UUID | None = None,
) -> File:
    """Validate, store, and record ``data`` as a new ``files`` row.

    Mirrors the exact size/type rules ``upload_file`` enforces:

    * ``filename`` must be non-empty after stripping (:class:`ValidationError`,
      400) — the same check the multipart route applies before touching
      storage.
    * ``len(data)`` must not exceed ``settings.lq_ai_max_upload_size_mb``
      (:class:`PayloadTooLarge`, 413) — the same cap ``stream_upload``
      enforces, checked up front here since the caller already holds the
      full bytes (no streaming abort dance needed).
    * ``content_type`` falls back to :data:`DEFAULT_MIME` when falsy, same
      as the multipart route's ``file.content_type or DEFAULT_MIME``.

    On success: uploads the bytes to storage at a freshly-minted UUID key,
    inserts (and flushes — NOT commits) the ``files`` row at
    ``ingestion_status='pending'``, and enqueues the C5 document-pipeline
    job. The enqueue is best-effort/non-fatal (log a warning, row stays
    ``pending`` for the worker's startup sweep to pick up) — identical
    posture to the original inline code.

    On a flush-time :class:`~sqlalchemy.exc.IntegrityError` (e.g. ``owner_id``
    no longer references an existing user), the just-uploaded object is
    deleted from storage before re-raising so a failed ingest never leaves
    an orphaned blob behind.

    Does not call ``session.commit()`` — the caller decides the transaction
    boundary (the HTTP route commits once after its own audit-log write;
    the intake bridge endpoint batches several attachments plus the
    thread/message rows into one commit).
    """

    clean_filename = (filename or "").strip()
    if not clean_filename:
        raise ValidationError(
            "filename must not be empty.",
        )

    max_size_bytes = settings.lq_ai_max_upload_size_mb * 1024 * 1024
    if len(data) > max_size_bytes:
        raise PayloadTooLarge(
            message=(f"File exceeds the {max_size_bytes // (1024 * 1024)} MB per-file limit."),
            details={"limit_bytes": max_size_bytes, "received_bytes": len(data)},
        )

    mime_type = content_type or DEFAULT_MIME
    file_id = uuid.uuid4()
    storage_path = str(file_id)
    sha256_hex = hashlib.sha256(data).hexdigest()

    log.info(
        "ingest_bytes start",
        extra={
            "event": "ingest_bytes_start",
            "owner_id": str(owner_id),
            "file_id": str(file_id),
            "upload_filename": clean_filename,
            "mime_type": mime_type,
            "project_id": str(project_id) if project_id else None,
            "size_bytes": len(data),
        },
    )

    await upload_bytes(storage_path=storage_path, body=data, content_type=mime_type)

    row = File(
        id=file_id,
        owner_id=owner_id,
        project_id=project_id,
        filename=clean_filename,
        mime_type=mime_type,
        size_bytes=len(data),
        hash_sha256=sha256_hex,
        storage_path=storage_path,
        ingestion_status="pending",
        created_by_run_id=created_by_run_id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        try:
            await delete_object(storage_path=storage_path)
        except Exception:
            log.warning(
                "ingest_bytes: failed to clean up storage object after row-insert failure",
                extra={"event": "ingest_bytes_cleanup_failed", "storage_path": storage_path},
            )
        raise
    await session.refresh(row)

    log.info(
        "ingest_bytes complete",
        extra={
            "event": "ingest_bytes_complete",
            "owner_id": str(owner_id),
            "file_id": str(file_id),
            "size_bytes": len(data),
            "sha256": sha256_hex,
        },
    )

    # Enqueue the C5 ingest job. Failures are non-fatal — the row stays
    # `pending` and the worker's startup sweep picks it up. Lazy import so
    # environments without arq installed (or that monkeypatch the queue)
    # don't pay an import cost just from importing this module.
    try:
        from app.workers.queue import enqueue_ingest_job

        await enqueue_ingest_job(file_id)
    except Exception as exc:
        log.warning(
            "ingest_bytes: enqueue_ingest_job raised; row remains pending",
            extra={
                "event": "ingest_bytes_enqueue_raised",
                "file_id": str(file_id),
                "error": str(exc),
            },
        )

    return row
