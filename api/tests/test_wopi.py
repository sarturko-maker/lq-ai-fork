"""Tests for the WOPI host + editor-session mint (libreoffice-editor Slice 2/3, ADR-F047).

Layers:

* **Pure unit** — the WOPI token round-trip (`create_wopi_token`/`decode_wopi_token`)
  and the lock state machines (`decide_lock`, `decide_putfile_lock`); no DB, no app.
* **Integration** — CheckFileInfo / GetFile / the Lock family over the bare WOPI
  router, authenticated by a minted `access_token` query param; plus the
  owner-scoped editor-session mint endpoint. The 404/401 split and per-file /
  per-user scoping are exercised here.
* **PutFile save-back (Slice 3)** — the snapshot-then-mutate matrix: snapshot the
  agent redline on the first human save (provenance flip), no-op on identical
  bytes, no re-snapshot on later saves (incl. the retry-after-commit-failure
  guard), the lock precondition (409 + echo), OOXML/`.docx` validation (400), the
  size cap (413), and the `X-COOL-WOPI-Timestamp` save-race backstop (1010).

Storage is the in-memory `FakeS3Client` (no live MinIO); the DB is the per-test
SAVEPOINT-rolled-back session from `conftest.py`.
"""

from __future__ import annotations

import hashlib
import time
import uuid
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.agent_run import AgentRun, AgentThread
from app.models.editor_lock import EditorLock
from app.models.file import File as FileModel
from app.models.user import User
from app.schemas.wopi import LockAction, decide_lock, decide_putfile_lock
from app.security import create_access_token, create_wopi_token, decode_wopi_token, hash_password
from tests.test_storage_streaming import FakeS3Client

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def fake_s3() -> FakeS3Client:
    return FakeS3Client()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, fake_s3: FakeS3Client) -> AsyncIterator[AsyncClient]:
    @asynccontextmanager
    async def _ctx() -> AsyncIterator[FakeS3Client]:
        yield fake_s3

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    with patch("app.storage.s3_client", _ctx):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.pop(get_db, None)


async def _make_user(db_session: AsyncSession, *, display_name: str | None = "Jane Lawyer") -> User:
    user = User(
        email=f"wopi-{uuid.uuid4().hex[:8]}@example.com",
        display_name=display_name,
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session)


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, display_name="Other Person")


async def _seed_file(
    db_session: AsyncSession,
    owner: User,
    *,
    filename: str = "deal (redlined).docx",
    content: bytes = b"PK\x03\x04 fake docx bytes",
) -> FileModel:
    digest = hashlib.sha256(content).hexdigest()
    row = FileModel(
        owner_id=owner.id,
        filename=filename,
        mime_type=DOCX_MIME,
        size_bytes=len(content),
        hash_sha256=digest,
        storage_path=str(uuid.uuid4()),
    )
    db_session.add(row)
    await db_session.flush()
    return row


def _bearer_for(user: User) -> str:
    return create_access_token(user.id, user.email, is_admin=user.is_admin)


# ---------------------------------------------------------------------------
# Token unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_wopi_token_round_trip() -> None:
    uid, fid = uuid.uuid4(), uuid.uuid4()
    token = create_wopi_token(uid, fid, name="Jane Lawyer")
    claims = decode_wopi_token(token)
    assert claims is not None
    assert claims.user_id == uid
    assert claims.file_id == fid
    assert claims.name == "Jane Lawyer"
    assert claims.expires_at > datetime.now(tz=UTC)


@pytest.mark.unit
def test_wopi_decode_rejects_access_token() -> None:
    """An access token must never validate as a WOPI token (typ discriminator)."""
    access = create_access_token(uuid.uuid4(), "x@example.com", is_admin=False)
    assert decode_wopi_token(access) is None


@pytest.mark.unit
def test_wopi_decode_rejects_expired() -> None:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": str(uuid.uuid4()),
        "fid": str(uuid.uuid4()),
        "name": "Jane",
        "iat": now - 100,
        "exp": now - 10,  # already expired
        "typ": "wopi",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    assert decode_wopi_token(token) is None


@pytest.mark.unit
def test_wopi_decode_rejects_garbage_and_missing_claims() -> None:
    settings = get_settings()
    assert decode_wopi_token("not.a.jwt") is None
    # Missing the `fid` claim.
    bad = jwt.encode(
        {"sub": str(uuid.uuid4()), "name": "x", "iat": 1, "exp": 9999999999, "typ": "wopi"},
        settings.jwt_secret,
        algorithm="HS256",
    )
    assert decode_wopi_token(bad) is None


# ---------------------------------------------------------------------------
# Lock state machine unit tests (pure)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_decide_lock_lock_on_unlocked_sets() -> None:
    out = decide_lock("LOCK", x_wopi_lock="L1", x_wopi_oldlock=None, current_lock=None)
    assert out.status == 200
    assert out.action is LockAction.SET
    assert out.lock_to_persist == "L1"
    assert out.response_lock is None  # success on LOCK omits the header


@pytest.mark.unit
def test_decide_lock_lock_same_value_refreshes() -> None:
    out = decide_lock("LOCK", x_wopi_lock="L1", x_wopi_oldlock=None, current_lock="L1")
    assert out.status == 200
    assert out.action is LockAction.SET
    assert out.lock_to_persist == "L1"


@pytest.mark.unit
def test_decide_lock_lock_conflict_echoes_current() -> None:
    out = decide_lock("LOCK", x_wopi_lock="L2", x_wopi_oldlock=None, current_lock="L1")
    assert out.status == 409
    assert out.action is LockAction.NONE
    assert out.response_lock == "L1"


@pytest.mark.unit
def test_decide_lock_lock_missing_header_is_400() -> None:
    for empty in (None, ""):
        out = decide_lock("LOCK", x_wopi_lock=empty, x_wopi_oldlock=None, current_lock=None)
        assert out.status == 400
        assert out.action is LockAction.NONE


@pytest.mark.unit
def test_decide_lock_get_lock_empty_when_unlocked() -> None:
    out = decide_lock("GET_LOCK", x_wopi_lock=None, x_wopi_oldlock=None, current_lock=None)
    assert out.status == 200
    assert out.action is LockAction.NONE
    assert out.response_lock == ""  # explicit "no lock" signal


@pytest.mark.unit
def test_decide_lock_get_lock_returns_current() -> None:
    out = decide_lock("GET_LOCK", x_wopi_lock=None, x_wopi_oldlock=None, current_lock="L1")
    assert out.status == 200
    assert out.response_lock == "L1"


@pytest.mark.unit
def test_decide_lock_refresh_match_and_mismatch() -> None:
    ok = decide_lock("REFRESH_LOCK", x_wopi_lock="L1", x_wopi_oldlock=None, current_lock="L1")
    assert ok.status == 200
    assert ok.action is LockAction.SET
    assert ok.lock_to_persist == "L1"

    bad = decide_lock("REFRESH_LOCK", x_wopi_lock="L2", x_wopi_oldlock=None, current_lock="L1")
    assert bad.status == 409
    assert bad.response_lock == "L1"

    unlocked = decide_lock("REFRESH_LOCK", x_wopi_lock="L1", x_wopi_oldlock=None, current_lock=None)
    assert unlocked.status == 409
    assert unlocked.response_lock == ""  # empty when unlocked


@pytest.mark.unit
def test_decide_lock_unlock_match_clears_and_mismatch_conflicts() -> None:
    ok = decide_lock("UNLOCK", x_wopi_lock="L1", x_wopi_oldlock=None, current_lock="L1")
    assert ok.status == 200
    assert ok.action is LockAction.CLEAR
    assert ok.response_lock is None

    bad = decide_lock("UNLOCK", x_wopi_lock="L2", x_wopi_oldlock=None, current_lock="L1")
    assert bad.status == 409
    assert bad.response_lock == "L1"

    unlocked = decide_lock("UNLOCK", x_wopi_lock="L1", x_wopi_oldlock=None, current_lock=None)
    assert unlocked.status == 409
    assert unlocked.response_lock == ""


@pytest.mark.unit
def test_decide_lock_unlock_and_relock() -> None:
    ok = decide_lock("LOCK", x_wopi_lock="NEW", x_wopi_oldlock="OLD", current_lock="OLD")
    assert ok.status == 200
    assert ok.action is LockAction.SET
    assert ok.lock_to_persist == "NEW"

    bad = decide_lock("LOCK", x_wopi_lock="NEW", x_wopi_oldlock="WRONG", current_lock="OLD")
    assert bad.status == 409
    assert bad.response_lock == "OLD"


@pytest.mark.unit
def test_decide_lock_rejects_non_lock_override() -> None:
    with pytest.raises(ValueError):
        decide_lock("PUT", x_wopi_lock=None, x_wopi_oldlock=None, current_lock=None)


# ---------------------------------------------------------------------------
# CheckFileInfo integration
# ---------------------------------------------------------------------------


def _wopi_url(file_id: uuid.UUID, token: str, suffix: str = "") -> str:
    return f"/api/v1/wopi/files/{file_id}{suffix}?access_token={token}"


@pytest.mark.integration
async def test_check_file_info_shape(client: AsyncClient, db_user: User, db_session) -> None:
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(db_user.id, f.id, name="Jane Lawyer")
    resp = await client.get(_wopi_url(f.id, token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["BaseFileName"] == "deal (redlined).docx"
    assert body["OwnerId"] == db_user.id.hex  # alphanumeric, no hyphens
    assert body["UserId"] == db_user.id.hex
    assert body["Size"] == f.size_bytes
    assert body["Version"] == f.hash_sha256
    assert body["UserFriendlyName"] == "Jane Lawyer"
    # Editable session (Slice 3 — PutFile save-back enabled).
    assert body["UserCanWrite"] is True
    assert body["ReadOnly"] is False
    assert body["SupportsUpdate"] is True
    assert body["SupportsLocks"] is True
    assert body["UserCanNotWriteRelative"] is True
    # No null properties on the wire.
    assert all(v is not None for v in body.values())


@pytest.mark.integration
async def test_check_file_info_basename_strips_path(
    client: AsyncClient, db_user: User, db_session
) -> None:
    """WOPI BaseFileName must be a bare filename — a stored path is stripped."""
    f = await _seed_file(db_session, db_user, filename="evil/../sub\\deal (redlined).docx")
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    resp = await client.get(_wopi_url(f.id, token))
    assert resp.status_code == 200
    assert resp.json()["BaseFileName"] == "deal (redlined).docx"


@pytest.mark.integration
async def test_check_file_info_missing_token_401(
    client: AsyncClient, db_user: User, db_session
) -> None:
    f = await _seed_file(db_session, db_user)
    resp = await client.get(f"/api/v1/wopi/files/{f.id}")
    assert resp.status_code == 401


@pytest.mark.integration
async def test_check_file_info_bad_token_401(
    client: AsyncClient, db_user: User, db_session
) -> None:
    f = await _seed_file(db_session, db_user)
    resp = await client.get(_wopi_url(f.id, "garbage.token"))
    assert resp.status_code == 401


@pytest.mark.integration
async def test_check_file_info_wrong_file_token_401(
    client: AsyncClient, db_user: User, db_session
) -> None:
    """A token minted for file B cannot open file A (fid claim mismatch)."""
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(db_user.id, uuid.uuid4(), name="Jane")
    resp = await client.get(_wopi_url(f.id, token))
    assert resp.status_code == 401


@pytest.mark.integration
async def test_check_file_info_cross_user_404(
    client: AsyncClient, db_user: User, other_user: User, db_session
) -> None:
    """A structurally-valid token whose user cannot see the file → 404, not 403."""
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(other_user.id, f.id, name="Other Person")
    resp = await client.get(_wopi_url(f.id, token))
    assert resp.status_code == 404


@pytest.mark.integration
async def test_check_file_info_accepts_bearer_header(
    client: AsyncClient, db_user: User, db_session
) -> None:
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    resp = await client.get(
        f"/api/v1/wopi/files/{f.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GetFile integration (round-trip via a real upload through the fake S3)
# ---------------------------------------------------------------------------


async def _upload(client: AsyncClient, user: User, *, payload: bytes) -> str:
    token = _bearer_for(user)
    files = {"file": ("deal.docx", payload, DOCX_MIME)}
    resp = await client.post(
        "/api/v1/files", files=files, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.integration
async def test_get_file_contents_round_trip(client: AsyncClient, db_user: User) -> None:
    payload = b"PK\x03\x04" + bytes(range(256)) * 4
    file_id = uuid.UUID(await _upload(client, db_user, payload=payload))
    token = create_wopi_token(db_user.id, file_id, name="Jane")

    resp = await client.get(_wopi_url(file_id, token, "/contents"))
    assert resp.status_code == 200
    assert resp.content == payload
    expected_hash = hashlib.sha256(payload).hexdigest()
    assert resp.headers["X-WOPI-ItemVersion"] == expected_hash


@pytest.mark.integration
async def test_get_file_contents_bad_token_401(client: AsyncClient, db_user: User) -> None:
    file_id = uuid.UUID(await _upload(client, db_user, payload=b"PK\x03\x04 x"))
    resp = await client.get(f"/api/v1/wopi/files/{file_id}/contents?access_token=nope")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Lock family integration
# ---------------------------------------------------------------------------


async def _lock_op(
    client: AsyncClient,
    file_id: uuid.UUID,
    token: str,
    override: str,
    *,
    lock: str | None = None,
    oldlock: str | None = None,
):
    headers = {"X-WOPI-Override": override}
    if lock is not None:
        headers["X-WOPI-Lock"] = lock
    if oldlock is not None:
        headers["X-WOPI-OldLock"] = oldlock
    return await client.post(_wopi_url(file_id, token), headers=headers)


@pytest.mark.integration
async def test_lock_lifecycle(client: AsyncClient, db_user: User, db_session) -> None:
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    # No lock yet.
    r = await _lock_op(client, f.id, token, "GET_LOCK")
    assert r.status_code == 200
    assert r.headers.get("X-WOPI-Lock") == ""

    # Acquire.
    r = await _lock_op(client, f.id, token, "LOCK", lock="LOCK-A")
    assert r.status_code == 200
    assert "X-WOPI-Lock" not in r.headers  # success on LOCK omits the header

    # Now visible.
    r = await _lock_op(client, f.id, token, "GET_LOCK")
    assert r.status_code == 200
    assert r.headers["X-WOPI-Lock"] == "LOCK-A"

    # Same value refreshes.
    r = await _lock_op(client, f.id, token, "LOCK", lock="LOCK-A")
    assert r.status_code == 200

    # Different value conflicts and echoes the current lock.
    r = await _lock_op(client, f.id, token, "LOCK", lock="LOCK-B")
    assert r.status_code == 409
    assert r.headers["X-WOPI-Lock"] == "LOCK-A"

    # Refresh + unlock with the wrong value conflicts.
    r = await _lock_op(client, f.id, token, "REFRESH_LOCK", lock="LOCK-A")
    assert r.status_code == 200
    r = await _lock_op(client, f.id, token, "UNLOCK", lock="WRONG")
    assert r.status_code == 409
    assert r.headers["X-WOPI-Lock"] == "LOCK-A"

    # Correct unlock releases.
    r = await _lock_op(client, f.id, token, "UNLOCK", lock="LOCK-A")
    assert r.status_code == 200
    r = await _lock_op(client, f.id, token, "GET_LOCK")
    assert r.headers["X-WOPI-Lock"] == ""


@pytest.mark.integration
async def test_unlock_and_relock(client: AsyncClient, db_user: User, db_session) -> None:
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    await _lock_op(client, f.id, token, "LOCK", lock="OLD")
    # Wrong old-lock conflicts.
    r = await _lock_op(client, f.id, token, "LOCK", lock="NEW", oldlock="WRONG")
    assert r.status_code == 409
    assert r.headers["X-WOPI-Lock"] == "OLD"
    # Correct old-lock swaps.
    r = await _lock_op(client, f.id, token, "LOCK", lock="NEW", oldlock="OLD")
    assert r.status_code == 200
    r = await _lock_op(client, f.id, token, "GET_LOCK")
    assert r.headers["X-WOPI-Lock"] == "NEW"


@pytest.mark.integration
async def test_lock_missing_header_400(client: AsyncClient, db_user: User, db_session) -> None:
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    r = await _lock_op(client, f.id, token, "LOCK")  # no X-WOPI-Lock
    assert r.status_code == 400


@pytest.mark.integration
async def test_expired_lock_treated_as_unlocked(
    client: AsyncClient, db_user: User, db_session
) -> None:
    f = await _seed_file(db_session, db_user)
    db_session.add(
        EditorLock(
            file_id=f.id,
            lock_value="STALE",
            expires_at=datetime.now(tz=UTC) - timedelta(minutes=5),
        )
    )
    await db_session.flush()
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    # Expired => GET_LOCK reports no lock.
    r = await _lock_op(client, f.id, token, "GET_LOCK")
    assert r.headers["X-WOPI-Lock"] == ""
    # And a fresh LOCK succeeds (overwrites the stale row).
    r = await _lock_op(client, f.id, token, "LOCK", lock="FRESH")
    assert r.status_code == 200
    r = await _lock_op(client, f.id, token, "GET_LOCK")
    assert r.headers["X-WOPI-Lock"] == "FRESH"


@pytest.mark.integration
async def test_put_and_unknown_override_501(client: AsyncClient, db_user: User, db_session) -> None:
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    for override in ("PUT", "PUT_RELATIVE", "RENAME_FILE", "WHATEVER", ""):
        r = await client.post(
            _wopi_url(f.id, token),
            headers=({"X-WOPI-Override": override} if override else {}),
        )
        assert r.status_code == 501, override


@pytest.mark.integration
async def test_lock_insert_race_resolves_to_conflict(
    client: AsyncClient, db_user: User, db_session, monkeypatch
) -> None:
    """A lost INSERT race re-resolves to the correct WOPI answer, never a 500.

    Simulate two concurrent LOCKs on an unlocked file: a lock already exists
    (the concurrent winner), but the handler's first read reports "unlocked", so
    its INSERT collides on the PK. The retry must re-read, see the winner's lock,
    and return 409 + the current lock — not a duplicate-key 500.
    """
    import app.api.wopi as wopi_mod

    f = await _seed_file(db_session, db_user)
    # The concurrent winner's lock — committed so it survives the handler's
    # rollback-after-IntegrityError.
    db_session.add(
        EditorLock(
            file_id=f.id,
            lock_value="WINNER",
            expires_at=datetime.now(tz=UTC) + timedelta(minutes=30),
        )
    )
    await db_session.commit()
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    real_resolve = wopi_mod._resolve_current_lock
    calls = {"n": 0}

    async def stale_then_real(db, file_id, now):
        calls["n"] += 1
        if calls["n"] == 1:
            return None, None  # stale read: didn't see the concurrent lock
        return await real_resolve(db, file_id, now)

    monkeypatch.setattr(wopi_mod, "_resolve_current_lock", stale_then_real)

    r = await _lock_op(client, f.id, token, "LOCK", lock="LOSER")
    assert r.status_code == 409
    assert r.headers["X-WOPI-Lock"] == "WINNER"
    assert calls["n"] >= 2  # proves the retry fired


@pytest.mark.integration
async def test_lock_op_bad_token_401(client: AsyncClient, db_user: User, db_session) -> None:
    f = await _seed_file(db_session, db_user)
    r = await client.post(
        f"/api/v1/wopi/files/{f.id}?access_token=nope",
        headers={"X-WOPI-Override": "GET_LOCK"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Editor-session mint endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_mint_editor_session(client: AsyncClient, db_user: User, db_session) -> None:
    f = await _seed_file(db_session, db_user)
    resp = await client.post(
        f"/api/v1/files/{f.id}/editor-session",
        headers={"Authorization": f"Bearer {_bearer_for(db_user)}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["wopi_src"] == f"http://api:8000/api/v1/wopi/files/{f.id}"
    claims = decode_wopi_token(body["access_token"])
    assert claims is not None
    assert claims.user_id == db_user.id
    assert claims.file_id == f.id
    assert claims.name == "Jane Lawyer"
    # access_token_ttl is epoch milliseconds in the future.
    assert body["access_token_ttl"] > int(time.time() * 1000)


@pytest.mark.integration
async def test_mint_editor_session_unauthenticated_401(
    client: AsyncClient, db_user: User, db_session
) -> None:
    f = await _seed_file(db_session, db_user)
    resp = await client.post(f"/api/v1/files/{f.id}/editor-session")
    assert resp.status_code == 401


@pytest.mark.integration
async def test_mint_editor_session_cross_user_404(
    client: AsyncClient, db_user: User, other_user: User, db_session
) -> None:
    f = await _seed_file(db_session, db_user)
    resp = await client.post(
        f"/api/v1/files/{f.id}/editor-session",
        headers={"Authorization": f"Bearer {_bearer_for(other_user)}"},
    )
    assert resp.status_code == 404


@pytest.mark.integration
async def test_mint_editor_session_missing_404(client: AsyncClient, db_user: User) -> None:
    resp = await client.post(
        f"/api/v1/files/{uuid.uuid4()}/editor-session",
        headers={"Authorization": f"Bearer {_bearer_for(db_user)}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PutFile (save-back) — Slice 3
# ---------------------------------------------------------------------------


def _make_ooxml(subtype: str = "docx", *, marker: bytes = b"") -> bytes:
    """A minimal, valid OOXML zip whose [Content_Types].xml types it as ``subtype``.

    Passes ``guard_ooxml`` (real zip, no DOCTYPE/ENTITY) and ``ooxml_subtype``
    (the main-part content type carries the family marker). ``marker`` varies the
    bytes so two valid docx blobs hash differently.
    """
    main = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    }[subtype]
    part = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml"}[subtype]
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Override PartName="/{part}" ContentType="{main}"/>'
        "</Types>"
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr(part, b"<root/>" + marker)
    return buf.getvalue()


async def _make_run(db_session: AsyncSession, owner: User) -> uuid.UUID:
    thread = AgentThread(user_id=owner.id, title="redline")
    db_session.add(thread)
    await db_session.flush()
    run = AgentRun(user_id=owner.id, thread_id=thread.id, prompt="redline")
    db_session.add(run)
    await db_session.flush()
    return run.id


async def _seed_editable(
    db_session: AsyncSession,
    fake_s3: FakeS3Client,
    owner: User,
    *,
    content: bytes,
    created_by_run_id: uuid.UUID | None = None,
    filename: str = "deal (redlined).docx",
) -> FileModel:
    """Seed a File row AND its bytes in the fake store (so copy/overwrite work)."""
    row = await _seed_file(db_session, owner, filename=filename, content=content)
    if created_by_run_id is not None:
        row.created_by_run_id = created_by_run_id
        await db_session.flush()
    fake_s3.objects[row.storage_path] = content
    fake_s3.content_types[row.storage_path] = DOCX_MIME
    return row


async def _seed_lock(db_session: AsyncSession, file_id: uuid.UUID, value: str) -> None:
    db_session.add(
        EditorLock(
            file_id=file_id,
            lock_value=value,
            expires_at=datetime.now(tz=UTC) + timedelta(minutes=30),
        )
    )
    await db_session.flush()


def _putfile(
    client: AsyncClient,
    file_id: uuid.UUID,
    token: str,
    body: bytes,
    *,
    lock: str | None = None,
    timestamp: str | None = None,
):
    headers = {"X-WOPI-Override": "PUT"}
    if lock is not None:
        headers["X-WOPI-Lock"] = lock
    if timestamp is not None:
        headers["X-COOL-WOPI-Timestamp"] = timestamp
    return client.post(_wopi_url(file_id, token, "/contents"), content=body, headers=headers)


# ----- pure unit: PutFile lock precondition -----


@pytest.mark.unit
def test_decide_putfile_lock_unlocked_and_match_proceed() -> None:
    assert decide_putfile_lock(x_wopi_lock=None, current_lock=None).status == 200
    assert decide_putfile_lock(x_wopi_lock="L1", current_lock=None).status == 200
    assert decide_putfile_lock(x_wopi_lock="L1", current_lock="L1").status == 200


@pytest.mark.unit
def test_decide_putfile_lock_mismatch_conflicts_and_echoes() -> None:
    out = decide_putfile_lock(x_wopi_lock="L2", current_lock="L1")
    assert out.status == 409
    assert out.response_lock == "L1"
    miss = decide_putfile_lock(x_wopi_lock=None, current_lock="L1")
    assert miss.status == 409
    assert miss.response_lock == "L1"


# ----- integration -----


@pytest.mark.integration
async def test_putfile_human_upload_mutates_in_place_no_snapshot(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    """A human-uploaded file (no run provenance) saves in place; no snapshot row."""
    original = _make_ooxml("docx", marker=b"v1")
    file_id = uuid.UUID(await _upload(client, db_user, payload=original))
    await _seed_lock(db_session, file_id, "LCK")
    token = create_wopi_token(db_user.id, file_id, name="Jane")

    edited = _make_ooxml("docx", marker=b"v2-edited")
    resp = await _putfile(client, file_id, token, edited, lock="LCK")
    assert resp.status_code == 200, resp.text
    new_hash = hashlib.sha256(edited).hexdigest()
    assert resp.headers["X-WOPI-ItemVersion"] == new_hash
    assert resp.json()["LastModifiedTime"]

    # GetFile now returns the edited bytes + the bumped version.
    got = await client.get(_wopi_url(file_id, token, "/contents"))
    assert got.content == edited
    assert got.headers["X-WOPI-ItemVersion"] == new_hash

    # Exactly one file row for the owner — no snapshot.
    rows = (
        (await db_session.execute(select(FileModel).where(FileModel.owner_id == db_user.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].updated_at is not None


@pytest.mark.integration
async def test_putfile_snapshots_agent_redline_on_first_save(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    """First human save of an agent redline preserves it as an immutable snapshot."""
    run_id = await _make_run(db_session, db_user)
    original = _make_ooxml("docx", marker=b"agent-redline")
    f = await _seed_editable(
        db_session, fake_s3, db_user, content=original, created_by_run_id=run_id
    )
    await _seed_lock(db_session, f.id, "LCK")
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    edited = _make_ooxml("docx", marker=b"human-edited")
    resp = await _putfile(client, f.id, token, edited, lock="LCK")
    assert resp.status_code == 200, resp.text

    # Live row: mutated in place, now human-authored.
    await db_session.refresh(f)
    assert f.hash_sha256 == hashlib.sha256(edited).hexdigest()
    assert f.created_by_run_id is None
    assert f.updated_at is not None
    assert fake_s3.objects[f.storage_path] == edited  # WOPI id serves latest

    # A NEW snapshot row preserves the agent's redline (provenance + old bytes).
    rows = (
        (
            await db_session.execute(
                select(FileModel).where(FileModel.owner_id == db_user.id, FileModel.id != f.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    snap = rows[0]
    assert snap.created_by_run_id == run_id
    assert snap.hash_sha256 == hashlib.sha256(original).hexdigest()
    assert "(agent draft)" in snap.filename
    assert fake_s3.objects[snap.storage_path] == original
    assert snap.storage_path == str(snap.id)  # key == row id (ADR 0005)


@pytest.mark.integration
async def test_putfile_second_save_does_not_snapshot_again(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    run_id = await _make_run(db_session, db_user)
    f = await _seed_editable(
        db_session,
        fake_s3,
        db_user,
        content=_make_ooxml("docx", marker=b"r0"),
        created_by_run_id=run_id,
    )
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    r1 = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"r1"))
    assert r1.status_code == 200
    r2 = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"r2"))
    assert r2.status_code == 200

    # Only ONE snapshot (from the first save); the second just mutated in place.
    others = (
        (
            await db_session.execute(
                select(FileModel).where(FileModel.owner_id == db_user.id, FileModel.id != f.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(others) == 1


@pytest.mark.integration
async def test_putfile_retry_after_commit_failure_does_not_resnapshot(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client, monkeypatch
) -> None:
    """Two-commit guard: a retry after a post-overwrite commit failure must NOT
    re-snapshot the edited bytes under the agent's provenance.

    Inject a failure at the (post-overwrite) audit step of the FIRST save: the
    snapshot+provenance-flip commit has already landed and the live object is
    already overwritten, but the save's own commit fails -> 500. The client's
    retry must see created_by_run_id=NULL and skip the snapshot entirely, so
    exactly ONE snapshot exists and it holds the AGENT bytes, not the human edit.
    """
    import app.api.wopi as wopi_mod
    from app.errors import InternalError

    run_id = await _make_run(db_session, db_user)
    original = _make_ooxml("docx", marker=b"agent-redline")
    f = await _seed_editable(
        db_session, fake_s3, db_user, content=original, created_by_run_id=run_id
    )
    # Capture locals up front: the handler's rollback (on the injected failure)
    # expires the `f` instance, so a later sync attribute access would lazy-load.
    f_id, storage_path = f.id, f.storage_path
    orig_hash = hashlib.sha256(original).hexdigest()
    token = create_wopi_token(db_user.id, f_id, name="Jane")

    real_audit = wopi_mod.audit_action
    calls = {"n": 0}

    async def flaky_audit(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise InternalError("simulated commit-time failure")
        return await real_audit(*a, **k)

    monkeypatch.setattr(wopi_mod, "audit_action", flaky_audit)

    edited = _make_ooxml("docx", marker=b"human-edited")
    edited_hash = hashlib.sha256(edited).hexdigest()
    r1 = await _putfile(client, f_id, token, edited)
    assert r1.status_code == 500
    # The overwrite happened before the (failed) commit; the edit is durable.
    assert fake_s3.objects[storage_path] == edited

    # Retry: provenance already flipped -> no second snapshot.
    r2 = await _putfile(client, f_id, token, edited)
    assert r2.status_code == 200

    snaps = (
        (await db_session.execute(select(FileModel).where(FileModel.created_by_run_id == run_id)))
        .scalars()
        .all()
    )
    assert len(snaps) == 1  # exactly one snapshot, from the first (committed) step
    assert snaps[0].hash_sha256 == orig_hash  # the AGENT bytes, not the human edit
    assert fake_s3.objects[snaps[0].storage_path] == original

    live = (await db_session.execute(select(FileModel).where(FileModel.id == f_id))).scalar_one()
    assert live.created_by_run_id is None
    assert live.hash_sha256 == edited_hash


@pytest.mark.integration
async def test_putfile_lock_mismatch_409(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    original = _make_ooxml("docx", marker=b"v1")
    f = await _seed_editable(db_session, fake_s3, db_user, content=original)
    await _seed_lock(db_session, f.id, "HELD")
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    resp = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"v2"), lock="WRONG")
    assert resp.status_code == 409
    assert resp.headers["X-WOPI-Lock"] == "HELD"
    # The stored bytes are untouched.
    assert fake_s3.objects[f.storage_path] == original


@pytest.mark.integration
async def test_putfile_unlocked_allowed(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    f = await _seed_editable(
        db_session, fake_s3, db_user, content=_make_ooxml("docx", marker=b"v1")
    )
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    resp = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"v2"))  # no lock
    assert resp.status_code == 200


@pytest.mark.integration
async def test_putfile_rejects_non_ooxml_400(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    f = await _seed_editable(
        db_session, fake_s3, db_user, content=_make_ooxml("docx", marker=b"v1")
    )
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    resp = await _putfile(client, f.id, token, b"this is not a zip at all")
    assert resp.status_code == 400


@pytest.mark.integration
async def test_putfile_rejects_non_docx_ooxml_400(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    """A valid OOXML zip that is a spreadsheet, not a document, is rejected."""
    f = await _seed_editable(
        db_session, fake_s3, db_user, content=_make_ooxml("docx", marker=b"v1")
    )
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    resp = await _putfile(client, f.id, token, _make_ooxml("xlsx", marker=b"sheet"))
    assert resp.status_code == 400


@pytest.mark.integration
async def test_putfile_oversize_413(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client, monkeypatch
) -> None:
    import app.api.wopi as wopi_mod

    f = await _seed_editable(
        db_session, fake_s3, db_user, content=_make_ooxml("docx", marker=b"v1")
    )
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    # Force the cap to 0 bytes so any non-empty body trips the 413.
    monkeypatch.setattr(
        wopi_mod, "get_settings", lambda: SimpleNamespace(lq_ai_max_upload_size_mb=0)
    )
    resp = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"v2"))
    assert resp.status_code == 413


@pytest.mark.integration
async def test_putfile_save_race_returns_1010(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    original = _make_ooxml("docx", marker=b"v1")
    f = await _seed_editable(db_session, fake_s3, db_user, content=original)
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    resp = await _putfile(
        client,
        f.id,
        token,
        _make_ooxml("docx", marker=b"v2"),
        timestamp="1999-01-01T00:00:00+00:00",  # stale: != current LastModifiedTime
    )
    assert resp.status_code == 409
    assert resp.json() == {"COOLStatusCode": 1010}
    assert fake_s3.objects[f.storage_path] == original  # not clobbered


@pytest.mark.integration
async def test_putfile_matching_timestamp_proceeds(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    f = await _seed_editable(
        db_session, fake_s3, db_user, content=_make_ooxml("docx", marker=b"v1")
    )
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    first = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"v2"))
    assert first.status_code == 200
    last_modified = first.json()["LastModifiedTime"]

    # The editor echoes back the timestamp it just received → no conflict.
    second = await _putfile(
        client, f.id, token, _make_ooxml("docx", marker=b"v3"), timestamp=last_modified
    )
    assert second.status_code == 200


@pytest.mark.integration
async def test_putfile_no_op_identical_bytes(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    """An autosave of identical bytes neither snapshots nor flips provenance."""
    run_id = await _make_run(db_session, db_user)
    original = _make_ooxml("docx", marker=b"same")
    f = await _seed_editable(
        db_session, fake_s3, db_user, content=original, created_by_run_id=run_id
    )
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    resp = await _putfile(client, f.id, token, original)  # identical
    assert resp.status_code == 200
    assert resp.headers["X-WOPI-ItemVersion"] == hashlib.sha256(original).hexdigest()

    await db_session.refresh(f)
    assert f.created_by_run_id == run_id  # provenance NOT flipped
    others = (
        (
            await db_session.execute(
                select(FileModel).where(FileModel.owner_id == db_user.id, FileModel.id != f.id)
            )
        )
        .scalars()
        .all()
    )
    assert others == []  # no snapshot


@pytest.mark.integration
async def test_putfile_bad_token_401(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    f = await _seed_editable(db_session, fake_s3, db_user, content=_make_ooxml("docx"))
    resp = await client.post(
        f"/api/v1/wopi/files/{f.id}/contents?access_token=nope",
        content=_make_ooxml("docx", marker=b"v2"),
        headers={"X-WOPI-Override": "PUT"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
async def test_putfile_cross_user_404(
    client: AsyncClient, db_user: User, other_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    f = await _seed_editable(db_session, fake_s3, db_user, content=_make_ooxml("docx"))
    token = create_wopi_token(other_user.id, f.id, name="Other Person")
    resp = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"v2"))
    assert resp.status_code == 404


@pytest.mark.integration
async def test_putfile_non_put_override_501(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    """An explicit non-PUT override on the /contents path is 501."""
    f = await _seed_editable(db_session, fake_s3, db_user, content=_make_ooxml("docx"))
    token = create_wopi_token(db_user.id, f.id, name="Jane")
    resp = await client.post(
        _wopi_url(f.id, token, "/contents"),
        content=_make_ooxml("docx", marker=b"v2"),
        headers={"X-WOPI-Override": "PUT_RELATIVE"},
    )
    assert resp.status_code == 501


# ---------------------------------------------------------------------------
# SETUP-5b §F (ADR-F064 D1) — write-path role re-check (demotion window)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_putfile_demoted_mid_session_401_reads_stay_open(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    """A user demoted to viewer mid-session cannot keep SAVING through an
    already-minted WOPI token (401 = session-invalid to Collabora), while the
    still-member save path is unchanged and reads stay open after demotion."""
    f = await _seed_editable(db_session, fake_s3, db_user, content=_make_ooxml("docx"))
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    # Still a member: the save succeeds through the new role re-check.
    edited = _make_ooxml("docx", marker=b"v2-member-save")
    ok = await _putfile(client, f.id, token, edited)
    assert ok.status_code == 200, ok.text

    # Demoted to viewer mid-session: the SAME (still-valid) token can no
    # longer write...
    db_user.role = "viewer"
    await db_session.flush()
    denied = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"v3"))
    assert denied.status_code == 401

    # ...but read ops stay role-free: GetFile still streams the last save.
    got = await client.get(_wopi_url(f.id, token, "/contents"))
    assert got.status_code == 200
    assert got.content == edited
    info = await client.get(_wopi_url(f.id, token))
    assert info.status_code == 200


@pytest.mark.integration
async def test_lock_op_demoted_mid_session_401(
    client: AsyncClient, db_user: User, db_session
) -> None:
    """The lock family is a write too: a mid-session demotion invalidates it."""
    f = await _seed_file(db_session, db_user)
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    r = await _lock_op(client, f.id, token, "LOCK", lock="L1")
    assert r.status_code == 200

    db_user.role = "viewer"
    await db_session.flush()
    r = await _lock_op(client, f.id, token, "REFRESH_LOCK", lock="L1")
    assert r.status_code == 401


@pytest.mark.integration
async def test_putfile_disabled_mid_session_401(
    client: AsyncClient, db_user: User, db_session, fake_s3: FakeS3Client
) -> None:
    """Liveness mirror of get_current_user: a disabled account's live WOPI
    token loses write access on the next save."""
    f = await _seed_editable(db_session, fake_s3, db_user, content=_make_ooxml("docx"))
    token = create_wopi_token(db_user.id, f.id, name="Jane")

    db_user.disabled_at = datetime.now(tz=UTC)
    await db_session.flush()
    denied = await _putfile(client, f.id, token, _make_ooxml("docx", marker=b"v2"))
    assert denied.status_code == 401
