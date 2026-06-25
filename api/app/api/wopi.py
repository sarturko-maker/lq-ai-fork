"""WOPI host — the in-app Word editor's protocol surface (Slice 2, ADR-F047).

Collabora Online opens a matter's ``.docx`` by calling these endpoints over the
WOPI protocol. This slice is the **read** half: ``CheckFileInfo`` (metadata),
``GetFile`` (bytes), and the **Lock family** (LOCK / GET_LOCK / REFRESH_LOCK /
UNLOCK / UNLOCK_AND_RELOCK). The session is **read-only** (``UserCanWrite=false``)
so the lawyer can faithfully SEE the agent's redline — editing + byte save-back
(PutFile) land in Slice 3, the cockpit launch UI + reskin in Slice 4.

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

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.files import _load_visible_file
from app.config import get_settings
from app.db.session import get_db
from app.errors import Unauthorized
from app.models.editor_lock import EditorLock
from app.models.file import File as FileModel
from app.schemas.wopi import (
    LOCK_OVERRIDES,
    LOCK_TTL_SECONDS,
    CheckFileInfoResponse,
    LockAction,
    decide_lock,
)
from app.security import WopiTokenClaims, decode_wopi_token
from app.storage import stream_download

router = APIRouter(prefix="/wopi", tags=["wopi"])

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
    ``X-WOPI-ItemVersion`` header GetFile returns. ``LastModifiedTime`` is
    ``File.created_at``: the ``files`` table has no ``updated_at`` column, and a
    Slice-3 save-back persists a NEW ``File`` row, so ``created_at`` is the
    last-modified time of this file version.
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
        LastModifiedTime=file_row.created_at.astimezone(UTC).isoformat(),
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

    The lock family is handled via the pure :func:`decide_lock` state machine;
    everything else this slice does not implement (PUT → PutFile is Slice 3;
    PUT_RELATIVE is disabled via ``UserCanNotWriteRelative``) → ``501``.
    """
    await _authorize_wopi(file_id, access_token, authorization, db)

    override = (x_wopi_override or "").upper()
    if override not in LOCK_OVERRIDES:
        # PUT (PutFile, Slice 3), PUT_RELATIVE/RENAME_FILE (disabled), or unknown.
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
