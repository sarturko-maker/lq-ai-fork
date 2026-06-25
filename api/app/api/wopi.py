"""WOPI host — the in-app Word editor's protocol surface (Slice 2/3, ADR-F047).

Collabora Online opens a matter's ``.docx`` by calling these endpoints over the
WOPI protocol: ``CheckFileInfo`` (metadata), ``GetFile`` (bytes), the **Lock
family** (LOCK / GET_LOCK / REFRESH_LOCK / UNLOCK / UNLOCK_AND_RELOCK), and
**PutFile** (Slice 3 — the lawyer's edited bytes save back). The session is now
**editable** (``UserCanWrite=true``); the cockpit launch UI + reskin land in
Slice 4.

Save-back (Slice 3, ADR-F047) is **snapshot-then-mutate**: the agent's untouched
redline (``created_by_run_id`` set) is copied to a NEW immutable ``File`` row on
the FIRST human save (preserving it as a prior version, key == row id per ADR
0005), then the live row is mutated in place so the editor's one ``WOPISrc``
keeps serving the latest bytes. Later saves just mutate in place. The bytes are
untrusted browser input → ``guard_ooxml`` + a ``.docx`` subtype check + a size
cap gate every PutFile.

**Auth (ADR-F047).** This router is mounted WITHOUT the ``ActiveUser`` gate (same
posture as ``word_addin.public_router``): WOPI clients authenticate with a
host-minted ``access_token`` (a signed editor-session JWT) carried as a query
param on every call (Collabora also sends it as an ``Authorization: Bearer``
header — we accept either, preferring the query param). Three-layer scoping:

1. The token is minted only by ``POST /files/{id}/editor-session`` behind the
   ``ActiveUser`` gate + ``_load_visible_file`` (cross-user → 404).
2. The token's ``fid`` claim must equal the URL ``{file_id}`` — a token minted
   for one file cannot open another, even for the same user.
3. Every handler re-runs ``_load_visible_file(db, file_id, claims.user_id)`` →
   404 (never 403; no existence leak).

A malformed / expired / wrong-type / ``fid``-mismatch token → **401**; a valid
token whose file is not visible → **404**. The host makes NO model calls and
never reaches the gateway (ADR-F010 trivially intact).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.files import _load_visible_file
from app.audit import audit_action
from app.config import get_settings
from app.db.session import get_db
from app.errors import PayloadTooLarge, Unauthorized, ValidationError
from app.models.editor_lock import EditorLock
from app.models.file import File as FileModel
from app.pipeline.readers._base import (
    OOXML_DOCX_MIME,
    ParserError,
    ParserUnsupported,
    guard_ooxml,
    ooxml_subtype,
)
from app.schemas.wopi import (
    LOCK_OVERRIDES,
    LOCK_TTL_SECONDS,
    CheckFileInfoResponse,
    LockAction,
    decide_lock,
    decide_putfile_lock,
)
from app.security import WopiTokenClaims, decode_wopi_token
from app.storage import copy_object, delete_object, stream_download, upload_bytes

router = APIRouter(prefix="/wopi", tags=["wopi"])
log = logging.getLogger(__name__)

# Max attempts for the lock upsert. A concurrent LOCK on an as-yet-unlocked file
# can lose the INSERT race (duplicate PK); we re-resolve and re-decide so the
# loser gets the correct WOPI answer (a refresh if it holds the same lock, else
# a 409) instead of a 500. Two attempts suffice (after the first conflict the row
# exists, so the retry takes the UPDATE/conflict path, never INSERT again).
_LOCK_MAX_ATTEMPTS = 3


def _base_file_name(filename: str) -> str:
    """WOPI BaseFileName: the bare filename, never a path.

    Defensive — WOPI requires no path component (the CVE-2025-27791 sink) — so we
    strip any separator the stored name might carry, treating both ``/`` and
    ``\\`` as separators. Falls back to the raw name if stripping leaves nothing.
    """
    bare = PurePosixPath(filename.replace("\\", "/")).name
    return bare or filename


def _iso(dt: datetime) -> str:
    """Canonical UTC ISO-8601 string — the one timestamp format we emit/compare.

    CheckFileInfo's ``LastModifiedTime`` and PutFile's response use this, and the
    ``X-COOL-WOPI-Timestamp`` save-race check string-compares against it, so it
    must round-trip identically.
    """
    return dt.astimezone(UTC).isoformat()


def _snapshot_filename(filename: str) -> str:
    """Name for the preserved agent redline: ``<stem> (agent draft)<ext>``.

    The live row keeps the original filename (the editor's BaseFileName stays
    stable); the snapshot gets a distinguishable name in the matter's Documents
    tab. Provenance is carried by ``created_by_run_id`` on the snapshot row — the
    marker is just human-readable disambiguation.
    """
    bare = _base_file_name(filename)
    suffix = PurePosixPath(bare).suffix
    stem = bare[: -len(suffix)] if suffix else bare
    return f"{stem} (agent draft){suffix}"


async def _read_capped_body(request: Request, max_bytes: int) -> bytes:
    """Buffer the request body, raising 413 the instant it exceeds ``max_bytes``.

    PutFile bodies are validated as a whole (``guard_ooxml`` opens the zip), so
    the bytes must be materialized — but bounded, so a hostile oversize body
    can't exhaust memory. Mirrors the upload handler's streamed size enforcement.
    """
    buffer = bytearray()
    async for chunk in request.stream():
        if not chunk:
            continue
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise PayloadTooLarge(
                message=f"Edited document exceeds the {max_bytes // (1024 * 1024)} MB limit.",
                details={"limit_bytes": max_bytes},
            )
    return bytes(buffer)


# Default MIME for the .docx bytes GetFile streams. WOPI clients key the editor
# off CheckFileInfo's BaseFileName extension, not this, so the generic
# octet-stream is the safe default (mirrors files.DEFAULT_MIME).
_DEFAULT_MIME = "application/octet-stream"


def _extract_token(access_token: str | None, authorization: str | None) -> str | None:
    """The WOPI access token: prefer the query param, fall back to Bearer."""
    if access_token:
        return access_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[len("bearer ") :].strip() or None
    return None


async def _authorize_wopi(
    file_id: uuid.UUID,
    access_token: str | None,
    authorization: str | None,
    db: AsyncSession,
) -> tuple[WopiTokenClaims, FileModel]:
    """Validate the access token and load the (owner-scoped) file.

    Raises :class:`Unauthorized` (401) for any token failure including a
    ``fid``-claim that does not match the URL; :class:`app.errors.NotFound`
    (404, via ``_load_visible_file``) when the token's user cannot see the file.
    """
    token = _extract_token(access_token, authorization)
    if token is None:
        raise Unauthorized("Missing WOPI access token.")
    claims = decode_wopi_token(token)
    if claims is None:
        raise Unauthorized("Invalid or expired WOPI access token.")
    if claims.file_id != file_id:
        # Token scoped to a different file — no cross-file replay.
        raise Unauthorized("WOPI access token is not valid for this file.")
    file_row = await _load_visible_file(db, file_id, claims.user_id)
    return claims, file_row


@router.get(
    "/files/{file_id}",
    response_model=CheckFileInfoResponse,
    response_model_exclude_none=True,
    summary="WOPI CheckFileInfo — file metadata + session capabilities.",
)
async def check_file_info(
    file_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    access_token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> CheckFileInfoResponse:
    """Return the WOPI ``CheckFileInfo`` body for ``file_id``.

    ``OwnerId``/``UserId`` are emitted as ``uuid.hex`` because WOPI requires them
    to be alphanumeric (the hyphenated UUID form is invalid). ``Version`` is the
    content hash so it changes on every save-back (Slice 3) and matches the
    ``X-WOPI-ItemVersion`` header GetFile/PutFile return. ``LastModifiedTime`` is
    ``updated_at or created_at``: ``updated_at`` is stamped only by an in-place
    save-back, so it is the true last-modified time of the current bytes (and is
    what the ``X-COOL-WOPI-Timestamp`` save-race check compares against).
    """
    claims, file_row = await _authorize_wopi(file_id, access_token, authorization, db)
    settings = get_settings()

    return CheckFileInfoResponse(
        BaseFileName=_base_file_name(file_row.filename),
        OwnerId=file_row.owner_id.hex,
        Size=file_row.size_bytes,
        UserId=claims.user_id.hex,
        Version=file_row.hash_sha256,
        UserFriendlyName=claims.name,
        LastModifiedTime=_iso(file_row.updated_at or file_row.created_at),
        PostMessageOrigin=settings.collabora_post_message_origin or None,
    )


@router.get(
    "/files/{file_id}/contents",
    summary="WOPI GetFile — stream the original .docx bytes.",
    response_class=StreamingResponse,
)
async def get_file_contents(
    file_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    access_token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Stream the stored bytes back to Collabora.

    ``X-WOPI-ItemVersion`` echoes CheckFileInfo's ``Version`` (the content hash)
    so the client can detect an out-of-band change.
    """
    _claims, file_row = await _authorize_wopi(file_id, access_token, authorization, db)

    headers = {
        "X-WOPI-ItemVersion": file_row.hash_sha256,
        "Content-Length": str(file_row.size_bytes),
        "X-Content-Type-Options": "nosniff",
    }

    async def _generator() -> AsyncIterator[bytes]:
        async with stream_download(storage_path=file_row.storage_path) as chunks:
            async for chunk in chunks:
                yield chunk

    return StreamingResponse(
        _generator(),
        media_type=file_row.mime_type or _DEFAULT_MIME,
        headers=headers,
    )


async def _resolve_current_lock(
    db: AsyncSession, file_id: uuid.UUID, now: datetime
) -> tuple[EditorLock | None, str | None]:
    """Load the file's lock row and its *effective* value (None if expired)."""
    row = (
        await db.execute(select(EditorLock).where(EditorLock.file_id == file_id))
    ).scalar_one_or_none()
    if row is None or row.expires_at <= now:
        return row, None
    return row, row.lock_value


@router.post(
    "/files/{file_id}",
    summary="WOPI lock family (LOCK / GET_LOCK / REFRESH_LOCK / UNLOCK).",
)
async def wopi_file_operation(
    file_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    access_token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_wopi_override: Annotated[str | None, Header()] = None,
    x_wopi_lock: Annotated[str | None, Header()] = None,
    x_wopi_oldlock: Annotated[str | None, Header()] = None,
) -> Response:
    """Dispatch a WOPI POST operation on ``X-WOPI-Override``.

    The lock family is handled via the pure :func:`decide_lock` state machine.
    PutFile is a separate route (``POST .../contents``); the only overrides that
    reach this bare-path handler outside the lock family are PUT_RELATIVE /
    RENAME_FILE (disabled via ``UserCanNotWriteRelative``) or unknown → ``501``.
    """
    await _authorize_wopi(file_id, access_token, authorization, db)

    override = (x_wopi_override or "").upper()
    if override not in LOCK_OVERRIDES:
        # PUT_RELATIVE / RENAME_FILE (disabled), or an unknown override.
        return Response(status_code=501)

    # Resolve → decide → persist, retrying if a concurrent LOCK won the INSERT
    # race. On the retry the row exists, so the loser re-decides correctly (a
    # refresh if it holds the same lock, otherwise a 409) — never a 500.
    outcome = None
    last_exc: IntegrityError | None = None
    for _attempt in range(_LOCK_MAX_ATTEMPTS):
        now = datetime.now(UTC)
        row, current_lock = await _resolve_current_lock(db, file_id, now)
        outcome = decide_lock(
            override,
            x_wopi_lock=x_wopi_lock,
            x_wopi_oldlock=x_wopi_oldlock,
            current_lock=current_lock,
        )
        try:
            if outcome.action is LockAction.SET:
                assert outcome.lock_to_persist is not None  # SET always carries a value
                expires_at = now + timedelta(seconds=LOCK_TTL_SECONDS)
                if row is None:
                    db.add(
                        EditorLock(
                            file_id=file_id,
                            lock_value=outcome.lock_to_persist,
                            expires_at=expires_at,
                        )
                    )
                else:
                    row.lock_value = outcome.lock_to_persist
                    row.expires_at = expires_at
                await db.commit()
            elif outcome.action is LockAction.CLEAR:
                if row is not None:
                    await db.delete(row)
                    await db.commit()
            break
        except IntegrityError as exc:
            # A concurrent request inserted the lock row first; re-resolve.
            last_exc = exc
            await db.rollback()
            continue
    else:  # pragma: no cover - retries exhausted only under sustained contention
        assert last_exc is not None
        raise last_exc

    assert outcome is not None
    headers: dict[str, str] = {}
    if outcome.response_lock is not None:
        headers["X-WOPI-Lock"] = outcome.response_lock
    if outcome.failure_reason is not None:
        headers["X-WOPI-LockFailureReason"] = outcome.failure_reason
    return Response(status_code=outcome.status, headers=headers)


@router.post(
    "/files/{file_id}/contents",
    summary="WOPI PutFile — save the editor's edited .docx bytes back.",
)
async def put_file_contents(
    file_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    access_token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_wopi_override: Annotated[str | None, Header()] = None,
    x_wopi_lock: Annotated[str | None, Header()] = None,
    x_cool_wopi_timestamp: Annotated[str | None, Header()] = None,
    x_lool_wopi_timestamp: Annotated[str | None, Header()] = None,
) -> Response:
    """WOPI PutFile — persist the lawyer's edited bytes back to the file.

    Flow (ADR-F047 Slice 3), short-circuiting before any storage work on a refusal:

    1. **Authorize** (token → 401, file not visible → 404), same as the read half.
    2. **Lock precondition** (:func:`decide_putfile_lock`): a held lock that the
       request's ``X-WOPI-Lock`` doesn't match → 409 + the current lock echoed;
       unlocked or matching → proceed. The lock row is never mutated here.
    3. **Save-race backstop**: if ``X-COOL-WOPI-Timestamp`` (Collabora's last-seen
       ``LastModifiedTime``) no longer matches the stored one, the file changed in
       storage → 409 ``{"COOLStatusCode": 1010}`` so the editor warns, not clobbers.
    4. **Validate** the untrusted body: size cap → 413; ``guard_ooxml`` + a
       ``.docx`` subtype check → 400 (zip-bomb / XXE / wrong type rejected).
    5. **No-op autosave** (identical hash) → 200 without writing or snapshotting.
    6. **Snapshot-then-mutate**: if the live row is still the agent's untouched
       redline (``created_by_run_id`` set), copy its current bytes to a new
       immutable ``File`` row FIRST (data-safety: old bytes survive before the
       overwrite), flip the live row to human-authored; then overwrite the live
       object in place and bump ``hash``/``size``/``updated_at``. ``Version`` /
       ``X-WOPI-ItemVersion`` track the new content hash; the JSON body carries
       the new ``LastModifiedTime`` (the documented Collabora quirk).
    """
    claims, file_row = await _authorize_wopi(file_id, access_token, authorization, db)

    # On the /contents path PUT is the only operation (PutRelativeFile is on the
    # bare path and disabled). Reject any other explicit override.
    if x_wopi_override and x_wopi_override.upper() != "PUT":
        return Response(status_code=501)

    # 1) Lock precondition — refuse before reading the body on a conflict.
    now = datetime.now(UTC)
    _row, current_lock = await _resolve_current_lock(db, file_id, now)
    lock_outcome = decide_putfile_lock(x_wopi_lock=x_wopi_lock, current_lock=current_lock)
    if lock_outcome.status != 200:
        headers = (
            {"X-WOPI-Lock": lock_outcome.response_lock}
            if lock_outcome.response_lock is not None
            else {}
        )
        return Response(status_code=lock_outcome.status, headers=headers)

    # 2) Save-race backstop (Collabora sends the timestamp it last saw).
    current_ts = _iso(file_row.updated_at or file_row.created_at)
    seen_ts = x_cool_wopi_timestamp or x_lool_wopi_timestamp
    if seen_ts and seen_ts != current_ts:
        return JSONResponse(status_code=409, content={"COOLStatusCode": 1010})

    # 3) Read + validate the untrusted body.
    settings = get_settings()
    max_bytes = settings.lq_ai_max_upload_size_mb * 1024 * 1024
    body = await _read_capped_body(request, max_bytes)
    try:
        guard_ooxml(body)
    except ParserError as exc:
        raise ValidationError("Edited bytes are not a valid OOXML (.docx) document.") from exc
    except ParserUnsupported as exc:
        raise ValidationError("Edited document was rejected by the OOXML safety guard.") from exc
    if ooxml_subtype(body) != "docx":
        raise ValidationError("Editor save-back must be a .docx (WordprocessingML) document.")

    new_hash = hashlib.sha256(body).hexdigest()
    new_size = len(body)

    # 4) No-op autosave: identical bytes → don't snapshot or flip provenance.
    if new_hash == file_row.hash_sha256:
        return JSONResponse(
            status_code=200,
            content={"LastModifiedTime": current_ts},
            headers={"X-WOPI-ItemVersion": new_hash},
        )

    # 5) Snapshot-then-mutate. The agent's untouched redline is preserved on the
    # FIRST human save; later saves (created_by_run_id already NULL) mutate only.
    should_snapshot = file_row.created_by_run_id is not None
    snapshot_id: uuid.UUID | None = None
    if should_snapshot:
        snapshot_id = uuid.uuid4()
        # Copy FIRST — the old bytes must exist at the snapshot key before the
        # live object is overwritten, so a crash can never lose them.
        await copy_object(source_path=file_row.storage_path, dest_path=str(snapshot_id))

    saved_at = datetime.now(UTC)
    live_overwritten = False
    try:
        if should_snapshot:
            assert snapshot_id is not None
            db.add(
                FileModel(
                    id=snapshot_id,
                    owner_id=file_row.owner_id,
                    project_id=file_row.project_id,
                    filename=_snapshot_filename(file_row.filename),
                    mime_type=file_row.mime_type,
                    size_bytes=file_row.size_bytes,
                    hash_sha256=file_row.hash_sha256,
                    storage_path=str(snapshot_id),
                    ingestion_status=file_row.ingestion_status,
                    created_by_run_id=file_row.created_by_run_id,
                )
            )
            # The live row is now human-authored — its provenance moves to the snapshot.
            file_row.created_by_run_id = None
        file_row.hash_sha256 = new_hash
        file_row.size_bytes = new_size
        file_row.updated_at = saved_at
        await audit_action(
            db,
            user_id=claims.user_id,
            action="editor.file_saved",
            resource_type="file",
            resource_id=str(file_row.id),
            project_id=file_row.project_id,
            request=request,
            details={"size_bytes": new_size, "snapshotted": should_snapshot},
        )
        await db.flush()
        # Overwrite the live object only after the row writes are staged.
        await upload_bytes(
            storage_path=file_row.storage_path, body=body, content_type=OOXML_DOCX_MIME
        )
        live_overwritten = True
        await db.commit()
    except Exception:
        await db.rollback()
        # Only delete the snapshot orphan if the live object was NOT overwritten
        # (a pre-upload failure). If the overwrite already happened, the snapshot
        # is the sole copy of the agent's redline — KEEP it (orphan, GC-able)
        # rather than lose it; Collabora retries PutFile and converges.
        if snapshot_id is not None and not live_overwritten:
            try:
                await delete_object(storage_path=str(snapshot_id))
            except Exception:
                log.warning(
                    "Failed to clean up orphan editor snapshot after save failure",
                    extra={
                        "event": "editor_snapshot_cleanup_failed",
                        "snapshot_id": str(snapshot_id),
                    },
                )
        raise

    return JSONResponse(
        status_code=200,
        content={"LastModifiedTime": _iso(saved_at)},
        headers={"X-WOPI-ItemVersion": new_hash},
    )
