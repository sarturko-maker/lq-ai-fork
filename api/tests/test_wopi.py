"""Tests for the WOPI host + editor-session mint (libreoffice-editor Slice 2, ADR-F047).

Three layers:

* **Pure unit** — the WOPI token round-trip (`create_wopi_token`/`decode_wopi_token`)
  and the lock state machine (`decide_lock`); no DB, no app.
* **Integration** — CheckFileInfo / GetFile / the Lock family over the bare WOPI
  router, authenticated by a minted `access_token` query param; plus the
  owner-scoped editor-session mint endpoint. The 404/401 split and per-file /
  per-user scoping are exercised here.

Storage is the in-memory `FakeS3Client` (no live MinIO); the DB is the per-test
SAVEPOINT-rolled-back session from `conftest.py`.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.editor_lock import EditorLock
from app.models.file import File as FileModel
from app.models.user import User
from app.schemas.wopi import LockAction, decide_lock
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
    # Read-only viewer this slice.
    assert body["UserCanWrite"] is False
    assert body["ReadOnly"] is True
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
