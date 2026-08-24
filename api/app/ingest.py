"""Packaged file-ingest primitives — INTAKE-1 (ADR-F086).

Two functions, two callers:

* :func:`register_ingested_file` — "bytes are ALREADY durably in object
  storage at ``storage_path``; record that as a ``files`` row and enqueue
  the C5 pipeline job." Shared by ``app.api.files.upload_file`` (which
  streams the multipart body straight to storage via
  ``app.storage.stream_upload`` — unchanged, still never buffers the whole
  file per the C4 invariant) and :func:`ingest_bytes` below.
* :func:`ingest_bytes` — "here are ``bytes`` I already hold in memory
  (e.g. a base64-decoded email attachment, bounded to 25 MB by the intake
  envelope schema); validate, write them to storage, then call
  :func:`register_ingested_file`." Used by the email-intake bridge endpoint
  (``app.api.intake_emails``), which has no HTTP request to stream from.

Dependency injection: ``session`` and ``settings`` are passed in explicitly
to both functions — no module-level singleton, no ``get_settings()``/
``get_db()`` call inside this module. Neither function calls
``session.commit()`` — the caller decides the transaction boundary.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

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


async def register_ingested_file(
    *,
    session: AsyncSession,
    owner_id: uuid.UUID,
    project_id: uuid.UUID | None,
    filename: str,
    content_type: str,
    size: int,
    sha256: str,
    storage_path: str,
    created_by_run_id: uuid.UUID | None = None,
) -> File:
    """Insert the ``files`` row for bytes ALREADY written to storage.

    ``storage_path`` is the bare file UUID as a string (ADR 0005) — the
    row's ``id`` is derived from it (``uuid.UUID(storage_path)``) rather
    than taking a separate ``file_id`` parameter, so caller and callee can
    never disagree on the key.

    Flushes only (never commits) — the caller owns the transaction
    boundary AND its own cleanup-on-failure: this function performs no
    storage cleanup itself on a flush-time
    :class:`~sqlalchemy.exc.IntegrityError`, because callers that upload
    several files in one request (the intake bridge's attachment loop) need
    to track and clean up MULTIPLE storage paths on a LATER failure, not
    just the one this call just wrote — a cleanup helper baked in here
    could only ever undo its own single write.

    Enqueues the C5 document-pipeline job before returning (non-fatal: a
    failure here logs a warning and leaves the row ``pending`` for the
    worker's own startup sweep to pick up — same posture the inline C4 code
    always had).
    """

    file_id = uuid.UUID(storage_path)
    row = File(
        id=file_id,
        owner_id=owner_id,
        project_id=project_id,
        filename=filename,
        mime_type=content_type,
        size_bytes=size,
        hash_sha256=sha256,
        storage_path=storage_path,
        ingestion_status="pending",
        created_by_run_id=created_by_run_id,
    )
    session.add(row)
    await session.flush()

    log.info(
        "register_ingested_file: files row created",
        extra={
            "event": "register_ingested_file_complete",
            "owner_id": str(owner_id),
            "file_id": str(file_id),
            "size_bytes": size,
        },
    )

    # Lazy import so environments without arq installed (or that
    # monkeypatch the queue) don't pay an import cost on every ingest.
    try:
        from app.workers.queue import enqueue_ingest_job

        await enqueue_ingest_job(file_id)
    except Exception as exc:
        log.warning(
            "register_ingested_file: enqueue_ingest_job raised; row remains pending",
            extra={
                "event": "register_ingested_file_enqueue_raised",
                "file_id": str(file_id),
                "error": str(exc),
            },
        )

    return row


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
    """Validate, store, and record ``data`` (bytes already held in memory)
    as a new ``files`` row.

    For callers with a fully-buffered payload — the intake bridge's email
    attachments, boundary-capped at 25 MB decoded by
    :mod:`app.schemas.intake` — NOT for the HTTP multipart upload route,
    which streams via ``app.storage.stream_upload`` directly and never
    calls this function (C4 invariant: never buffer the whole file; see
    ``app.storage``'s module docstring).

    * ``filename`` must be non-empty after stripping (:class:`ValidationError`,
      400).
    * ``len(data)`` must not exceed ``settings.lq_ai_max_upload_size_mb``
      (:class:`PayloadTooLarge`, 413) — checked up front since the caller
      already holds the full bytes.
    * ``content_type`` falls back to :data:`DEFAULT_MIME` when falsy.

    On success: uploads the bytes to storage at a freshly-minted UUID key,
    then delegates to :func:`register_ingested_file` for the row + enqueue.
    If registration fails after the upload (e.g. a flush-time
    IntegrityError), this call best-effort deletes its OWN just-uploaded
    object before re-raising — the caller can only clean up storage paths
    it learned from successful returns, so this one is invisible to it.
    Cleanup of EARLIER successful uploads when a LATER step in a
    multi-attachment request fails remains the caller's job (see
    ``app.api.intake_emails._cleanup_uploaded``).
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

    # Counts/IDs only — never the filename (sender-controlled on the
    # intake path; ADR-F086 security posture).
    log.info(
        "ingest_bytes start",
        extra={
            "event": "ingest_bytes_start",
            "owner_id": str(owner_id),
            "file_id": str(file_id),
            "mime_type": mime_type,
            "project_id": str(project_id) if project_id else None,
            "size_bytes": len(data),
        },
    )

    await upload_bytes(storage_path=storage_path, body=data, content_type=mime_type)

    try:
        row = await register_ingested_file(
            session=session,
            owner_id=owner_id,
            project_id=project_id,
            filename=clean_filename,
            content_type=mime_type,
            size=len(data),
            sha256=sha256_hex,
            storage_path=storage_path,
            created_by_run_id=created_by_run_id,
        )
        await session.refresh(row)
    except Exception:
        # THIS call's own object would otherwise orphan: a multi-attachment
        # caller (the intake bridge) can only clean up storage paths it was
        # TOLD about via successful returns — it never learns this one.
        # Two complementary layers: this call cleans its OWN object on its
        # own failure; the caller cleans PRIOR successful uploads when a
        # later step fails (see app.api.intake_emails._cleanup_uploaded).
        try:
            await delete_object(storage_path=storage_path)
        except Exception:
            log.warning(
                "ingest_bytes: failed to clean up storage object after registration failure",
                extra={"event": "ingest_bytes_cleanup_failed", "storage_path": storage_path},
            )
        raise

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

    return row
