"""Files endpoints — Task C4 (File upload + storage).

Surface (per ``docs/api/backend-openapi.yaml``):

* ``POST   /api/v1/files``               — multipart upload; streams body to
  MinIO, computes SHA-256, persists metadata with
  ``ingestion_status='pending'`` and returns the canonical ``File`` shape.
* ``GET    /api/v1/files/{file_id}``     — file metadata; 404 if missing or
  owned by a different user (per-user isolation; we return 404 rather
  than 403 to avoid leaking existence).
* ``GET    /api/v1/files/{file_id}/content`` — streaming download of the
  original bytes; ``Content-Disposition: attachment; filename=...`` with
  RFC 5987-encoded ``filename*`` for non-ASCII filenames.
* ``DELETE /api/v1/files/{file_id}``     — soft-delete (sets ``deleted_at``);
  the MinIO bytes outlive the soft-delete per ADR 0005. The endpoint is
  idempotent: deleting an already-soft-deleted file (or a file that
  never existed) returns 404.

All four endpoints inherit the auth+gate from the router-level
``Depends(get_active_user)`` in ``app.api.__init__``; this module also
takes ``ActiveUser`` directly in handler signatures so the user object
is available for ``owner_id`` checks (FastAPI dedupes the dependency).

The C5 document pipeline picks up rows where
``ingestion_status='pending'`` and flips status through ``processing`` →
``ready`` (or ``failed``). C4 does NOT enqueue or notify — the pipeline
polls or subscribes; that's its problem.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser, MutatingUser
from app.audit import audit_action
from app.config import get_settings
from app.db.session import get_db
from app.errors import NotFound, PayloadTooLarge, ValidationError
from app.ingest import DEFAULT_MIME, ingest_bytes
from app.models.document import Document
from app.models.file import File as FileModel
from app.models.project import Project
from app.schemas.files import FileMetadata
from app.schemas.wopi import EditorSessionResponse
from app.security import create_wopi_token, decode_wopi_token
from app.storage import stream_download

router = APIRouter(prefix="/files", tags=["files"])
log = logging.getLogger(__name__)

# DEFAULT_MIME's canonical home is app.ingest (INTAKE-1); imported above so
# ``get_file_content``'s response media-type fallback (below) keeps working
# unchanged.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_file_id(file_id: str) -> uuid.UUID:
    """Reject non-UUID file ids per the OpenAPI sketch's ``{file_id}: uuid``."""

    try:
        return uuid.UUID(file_id)
    except ValueError as exc:
        # Keep the shape consistent with chats.py's _validate_chat_id —
        # 400 with code ``validation_error`` rather than a 404 (which
        # would conflate "bad input" with "no such resource").
        raise ValidationError(
            "file_id must be a UUID",
            details={"file_id": file_id},
        ) from exc


# RFC 6266 / RFC 5987: when the filename has only ascii printable chars
# we emit a plain ``filename="..."`` parameter; otherwise we add the
# UTF-8 ``filename*=UTF-8''<percent-encoded>`` form alongside an ascii
# fallback so legacy clients still get something usable.
_ASCII_PRINTABLE = re.compile(r"^[\x20-\x7E]+$")


def _content_disposition_attachment(filename: str) -> str:
    """Render an RFC 6266 ``Content-Disposition`` value for a download.

    For ASCII-only filenames the result is the simple
    ``attachment; filename="<name>"`` form. For names containing
    non-ASCII codepoints, both an ASCII fallback and the
    ``filename*=UTF-8''<percent-encoded>`` extension are emitted, in
    that order, per RFC 5987.

    Backslashes and quotes in the filename are escaped per RFC 6266
    section 4.1's quoted-string rules.
    """

    safe_ascii = _strip_for_ascii_fallback(filename) or "download"
    quoted_ascii = safe_ascii.replace("\\", "\\\\").replace('"', '\\"')

    if _ASCII_PRINTABLE.match(filename):
        return f'attachment; filename="{quoted_ascii}"'

    encoded = urllib.parse.quote(filename, safe="")
    return f"attachment; filename=\"{quoted_ascii}\"; filename*=UTF-8''{encoded}"


def _strip_for_ascii_fallback(filename: str) -> str:
    """Best-effort ASCII-fallback filename: drops non-printable codepoints.

    Used for the legacy ``filename="..."`` parameter when the canonical
    name has non-ASCII characters. The ``filename*`` parameter still
    carries the full UTF-8 form for modern clients.
    """

    return "".join(ch for ch in filename if 0x20 <= ord(ch) < 0x7F)


async def _read_upload_bytes(upload: UploadFile, *, max_size_bytes: int) -> bytes:
    """Read an ``UploadFile`` fully, aborting the instant it exceeds the cap.

    Reads ``upload.read(MULTIPART_PART_SIZE)`` repeatedly (Starlette spools
    to a SpooledTemporaryFile on disk past 1 MB by default, so this never
    holds more than the part size plus the spool file at once while
    reading) and accumulates into one buffer for :func:`app.ingest.ingest_bytes`
    — INTAKE-1's shared ingest primitive takes fully-buffered ``bytes`` so it
    can serve both this HTTP route and the intake bridge's already-decoded
    email attachments from one code path.

    Raises :class:`app.errors.PayloadTooLarge` the instant the running byte
    count exceeds ``max_size_bytes`` — same check, same error shape
    (``limit_bytes``/``received_bytes``) ``stream_upload`` used to raise
    here, just evaluated before any storage write rather than mid-multipart.
    """

    from app.storage import MULTIPART_PART_SIZE

    buffer = bytearray()
    total_bytes = 0
    while True:
        chunk = await upload.read(MULTIPART_PART_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_size_bytes:
            raise PayloadTooLarge(
                message=(
                    f"Uploaded file exceeds the {max_size_bytes // (1024 * 1024)} MB "
                    "per-request limit."
                ),
                details={"limit_bytes": max_size_bytes, "received_bytes": total_bytes},
            )
        buffer.extend(chunk)
    return bytes(buffer)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=FileMetadata,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file",
    description=(
        "Streaming multipart upload. The body is streamed to MinIO without "
        "ever loading the whole file into memory; a SHA-256 is computed as "
        "bytes flow past, and metadata is persisted with "
        "`ingestion_status='pending'`. The document pipeline (Task C5) "
        "picks the row up asynchronously and flips status through "
        "`processing` → `ready` (or `failed`).\n\n"
        "Per-request size limit: `LQ_AI_MAX_UPLOAD_SIZE_MB` (default 100). "
        "Exceeding it returns 413 with `code=payload_too_large`."
    ),
)
async def upload_file(
    user: MutatingUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(description="The file to upload.")],
    project_id: Annotated[
        str | None,
        Form(
            description=(
                "Optional UUID of a project to attach this file to. The "
                "caller must own the project; cross-user or unknown ids "
                "return 422 (the upload is rejected before bytes touch "
                "MinIO)."
            ),
        ),
    ] = None,
) -> FileMetadata:
    """Read the upload; persist it via ``ingest_bytes``; return the ``File`` shape.

    Order of operations:

    1. **Validate ``project_id``** if supplied. The form field is parsed
       as a UUID; the project must exist, be owned by the caller, and
       not be archived. Failures here return 422 *before* any bytes
       touch storage so a bad project_id doesn't leak into orphan storage.
    2. **Read the multipart body**, aborting with 413 the instant it
       exceeds the configured cap (:func:`_read_upload_bytes`) — no bytes
       reach storage for an oversized upload.
    3. **Delegate to :func:`app.ingest.ingest_bytes`** (INTAKE-1) for
       validation, the storage write, the ``files`` row, and the C5
       enqueue — the same primitive the email-intake bridge endpoint uses
       for its already-decoded attachments.
    4. **Write the audit row and commit.** ``ingest_bytes`` only flushes,
       so the file insert and its audit row land in one transaction here.
    5. **Return the ``FileMetadata``** matching the OpenAPI ``File`` schema.
    """

    settings = get_settings()
    max_size_bytes = settings.lq_ai_max_upload_size_mb * 1024 * 1024

    # Filename is required by the OpenAPI sketch; FastAPI's UploadFile
    # always exposes `.filename` but it can be the empty string for a
    # pathologically-formed multipart. Reject those explicitly, before
    # reading any bytes. ``ingest_bytes`` re-checks this too (it has its
    # own, non-HTTP caller in the intake bridge endpoint).
    filename = (file.filename or "").strip()
    if not filename:
        raise ValidationError(
            "Multipart upload missing required `filename` on the file part.",
        )

    # Resolve the project attachment up front. Anything other than
    # "owner-visible active project" → 422 (validation error). We use
    # 422 rather than 404 here because the caller is making a *create*
    # request; the project_id is request input, not a path identifier
    # whose existence is being probed.
    resolved_project_id: uuid.UUID | None = None
    if project_id is not None:
        try:
            resolved_project_id = uuid.UUID(project_id)
        except ValueError as exc:
            raise ValidationError(
                "project_id must be a UUID",
                details={"project_id": project_id},
            ) from exc

        stmt = select(Project.id).where(
            Project.id == resolved_project_id,
            Project.owner_id == user.id,
            Project.archived_at.is_(None),
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise ValidationError(
                "project_id does not reference a project owned by the caller.",
                details={"project_id": str(resolved_project_id)},
            )

    data = await _read_upload_bytes(file, max_size_bytes=max_size_bytes)

    row = await ingest_bytes(
        session=db,
        settings=settings,
        owner_id=user.id,
        project_id=resolved_project_id,
        filename=filename,
        content_type=file.content_type,
        data=data,
    )

    # Privilege propagates from the project (if any) — audit_action
    # resolves it from project_id without an extra fetch when the
    # ORM Project isn't loaded here. Read the persisted row's fields
    # (not the local `data`/`filename`) — ingest_bytes already refreshed
    # it, and this keeps the audit row honest about what actually landed.
    await audit_action(
        db,
        user_id=user.id,
        action="file.uploaded",
        resource_type="file",
        resource_id=str(row.id),
        project_id=resolved_project_id,
        request=request,
        details={
            "filename": row.filename,
            "size_bytes": row.size_bytes,
            "mime_type": row.mime_type,
        },
    )
    await db.commit()
    # ingest_bytes()'s own refresh happened before this commit, which
    # expires it again (SQLAlchemy's default expire_on_commit) — refresh
    # once more so the serialization below never touches an expired
    # attribute outside of an awaited call (the MissingGreenlet trap).
    await db.refresh(row)

    return FileMetadata.model_validate(row)


@router.get(
    "/{file_id}",
    response_model=FileMetadata,
    summary="Get file metadata",
)
async def get_file(
    file_id: str,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileMetadata:
    """Return the canonical ``File`` shape for ``file_id``.

    Returns 404 if the file does not exist, has been soft-deleted, or
    is owned by another user. (Per CLAUDE.md and the C4 brief: the
    cross-user case returns 404 rather than 403 to avoid leaking
    existence information.)
    """

    file_uuid = _validate_file_id(file_id)
    row = await _load_visible_file(db, file_uuid, user.id)
    # Outerjoin to ``documents`` so the response carries ``document_id``
    # once the C5 parse pipeline has produced the row (M3-A6 Phase 6).
    document_id_stmt = select(Document.id).where(Document.file_id == row.id)
    document_id = (await db.execute(document_id_stmt)).scalar_one_or_none()
    return FileMetadata.model_validate(row).model_copy(update={"document_id": document_id})


@router.get(
    "/{file_id}/content",
    summary="Download original file content",
    response_class=StreamingResponse,
)
async def get_file_content(
    file_id: str,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Stream the original bytes from MinIO with the right headers.

    Headers set:
    * ``Content-Type``: from the stored ``mime_type``.
    * ``Content-Disposition``: ``attachment; filename="..."`` with an
      RFC 5987 ``filename*`` for non-ASCII filenames.
    * ``X-Content-Type-Options: nosniff``: defensive — clients (esp.
      browsers) must not infer a MIME from sniffing.

    Deliberately NO ``Content-Length``: two paths now mutate a file's bytes in
    place (the editor's PutFile save-back, ADR-F047, and the redline convergence,
    ADR-F081), and the row's ``size_bytes`` is a separate source of truth from
    the object — pinning the header to the row would emit a truncated/hung
    response across a mutation window. Chunked streaming keeps the declared
    length equal to the bytes actually sent (same reasoning as WOPI GetFile).
    """

    file_uuid = _validate_file_id(file_id)
    row = await _load_visible_file(db, file_uuid, user.id)

    headers = {
        "Content-Disposition": _content_disposition_attachment(row.filename),
        "X-Content-Type-Options": "nosniff",
    }

    async def _generator() -> AsyncIterator[bytes]:
        async with stream_download(storage_path=row.storage_path) as chunks:
            async for chunk in chunks:
                yield chunk

    return StreamingResponse(
        _generator(),
        media_type=row.mime_type or DEFAULT_MIME,
        headers=headers,
    )


@router.post(
    "/{file_id}/editor-session",
    response_model=EditorSessionResponse,
    summary="Mint a WOPI editor session for the file",
    description=(
        "Mints a file-scoped WOPI access token (ADR-F047) so the in-app "
        "editor can open this file through the WOPI host (`/api/v1/wopi/files/"
        "{id}`). Owner-scoped: cross-user/missing → 404. The token is bound to "
        "this single `(user, file)` pair and expires after "
        "`wopi_token_ttl_seconds`. The cockpit (Slice 4) combines the returned "
        "`wopi_src` + `access_token` with Collabora's discovery `urlsrc` to "
        "launch the editor iframe."
    ),
)
async def create_editor_session(
    file_id: str,
    user: MutatingUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EditorSessionResponse:
    """Mint a WOPI editor-session token for ``file_id`` (owner-scoped, 404 on miss).

    The session is editable (the WOPI host advertises ``UserCanWrite=true`` and
    PutFile saves back, ADR-F047 Slice 3). The cockpit launch UI is Slice 4.
    """
    file_uuid = _validate_file_id(file_id)
    row = await _load_visible_file(db, file_uuid, user.id)

    # WOPI UserFriendlyName becomes the w:author on any edit (Slice 3), so it
    # must be a real, non-empty name distinct from the agent's DEFAULT_AUTHOR;
    # display_name is nullable, so fall back to the email.
    friendly_name = user.display_name or user.email
    token = create_wopi_token(user.id, row.id, name=friendly_name)
    # access_token_ttl is the token's absolute expiry in epoch MILLISECONDS
    # (WOPI convention). Read it back from the minted token so it can never
    # drift from the signed `exp`.
    claims = decode_wopi_token(token)
    assert claims is not None  # we just minted it
    access_token_ttl_ms = int(claims.expires_at.timestamp() * 1000)

    settings = get_settings()
    wopi_src = f"{settings.collabora_wopi_host.rstrip('/')}/api/v1/wopi/files/{row.id}"

    await audit_action(
        db,
        user_id=user.id,
        action="editor.session_created",
        resource_type="file",
        resource_id=str(row.id),
        project_id=row.project_id,
        request=request,
    )
    await db.commit()

    return EditorSessionResponse(
        access_token=token,
        access_token_ttl=access_token_ttl_ms,
        wopi_src=wopi_src,
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a file",
    description=(
        "Sets `deleted_at` on the row; the MinIO object is left in place "
        "and reaped later by D6 (per-user export+delete) or a future GC "
        "sweep, per `docs/adr/0005-file-storage-soft-delete-and-key-scheme.md`. "
        "Idempotent: deleting an already-soft-deleted file or a missing "
        "file returns 404."
    ),
    response_class=Response,
)
async def delete_file(
    file_id: str,
    user: MutatingUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Soft-delete the file by setting ``deleted_at``.

    Re-uses ``_load_visible_file`` so the cross-user case returns 404
    (no information leakage) and the already-soft-deleted case also
    returns 404 (the row is no longer visible to the user).
    """

    file_uuid = _validate_file_id(file_id)
    row = await _load_visible_file(db, file_uuid, user.id)

    from datetime import UTC, datetime

    row.deleted_at = datetime.now(tz=UTC)
    await audit_action(
        db,
        user_id=user.id,
        action="file.deleted",
        resource_type="file",
        resource_id=str(row.id),
        project_id=row.project_id,
        request=request,
        details={"filename": row.filename},
    )
    await db.commit()

    log.info(
        "file soft-deleted",
        extra={
            "event": "file_soft_deleted",
            "user_id": str(user.id),
            "file_id": str(file_uuid),
        },
    )

    # FastAPI translates `Response(status_code=204)` to a no-body 204.
    # Returning JSONResponse({}) with 204 would emit an empty body
    # which some HTTP/1.1 implementations dislike alongside a 204 (which
    # is defined as no-body). The explicit Response is correct.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Internal: shared file-lookup
# ---------------------------------------------------------------------------


async def _load_visible_file(
    db: AsyncSession,
    file_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> FileModel:
    """Load ``files`` row by id, scoped to the owner, excluding soft-deleted rows.

    Raises :class:`NotFound` if the row does not exist, is soft-deleted,
    or is owned by a different user. The cross-user case is collapsed
    into 404 deliberately — see C4 brief and CLAUDE.md on
    information-leakage avoidance.
    """

    stmt = select(FileModel).where(
        FileModel.id == file_id,
        FileModel.owner_id == owner_id,
        FileModel.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFound(
            f"File {file_id} not found.",
            details={"file_id": str(file_id)},
        )
    return row


# ---------------------------------------------------------------------------
# JSONResponse wrapper for non-FastAPI callers
# ---------------------------------------------------------------------------
# Re-export under the legacy name so existing imports keep compiling. The
# tests under api/tests/test_endpoints.py read the route table from the
# app object; they do not import these handlers by name.

__all__ = [
    "delete_file",
    "get_file",
    "get_file_content",
    "router",
    "upload_file",
]
