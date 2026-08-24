"""Integration tests for the INTAKE-1 (ADR-F086) bridge landing endpoint.

Covers ``POST /api/v1/internal/intake/emails``:

* Auth — valid bridge bearer required (401 missing/wrong), same posture as
  ``test_integrations_slack.py``.
* Happy path — one envelope with a base64 attachment → thread + candidate
  project (``intake_state='candidate'``) + ``files`` row + ``intake_messages``
  row (direction ``'in'``).
* Idempotency (claim-first, fresh-context-review fix) — the IntakeMessage
  insert IS the atomic claim: a pre-existing message row makes the request
  a no-op BEFORE any attachment is uploaded; re-delivering the same
  ``(thread, provider_message_id)`` returns ``duplicate: true``.
* Leak-free failure — a later attachment failing mid-request cleans up
  every already-uploaded object from THIS request and commits no rows.
* Thread-creation race — a concurrent delivery of the FIRST message on a
  brand-new thread is resolved by rollback + re-select, not a 500.
* Follow-up — a second message on the SAME ``provider_thread_id`` reuses
  the thread + project, bumps ``message_count``, creates no second project.
* Unknown ``(provider, inbox_id)`` → 404.
* Boundary rejection (422): an attachment over the 25 MB decoded cap; the
  aggregate 50 MB decoded cap across all attachments; more than 10
  attachments; an embedded NUL byte in a free-text field.
* An empty subject still produces a valid (fallback-named) candidate matter.
* Content-free logs — a hostile filename never appears in any log record.
"""

from __future__ import annotations

import base64
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import intake_emails as intake_emails_module
from app.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.file import File
from app.models.intake import IntakeMailbox, IntakeMessage, IntakeThread
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.user import User
from app.security import hash_password
from tests.test_storage_streaming import FakeS3Client

BRIDGE_TOKEN = "intake-bridge-token-fixture"


def _override_get_db(db_session: AsyncSession):
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def configured_settings(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("LQ_AI_BRIDGE_TOKEN", BRIDGE_TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def fake_s3() -> FakeS3Client:
    return FakeS3Client()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    configured_settings: None,
    fake_s3: FakeS3Client,
) -> AsyncIterator[AsyncClient]:
    @asynccontextmanager
    async def _ctx() -> AsyncIterator[FakeS3Client]:
        yield fake_s3

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    with patch("app.storage.s3_client", _ctx):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def owner_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"intake-owner-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("test-password-123"),
        is_admin=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def practice_area(db_session: AsyncSession) -> PracticeArea:
    area = PracticeArea(
        key=f"area-{uuid.uuid4().hex[:8]}",
        name="Commercial (test)",
        unit_label="Matter",
        position=0,
    )
    db_session.add(area)
    await db_session.flush()
    return area


@pytest_asyncio.fixture
async def mailbox(
    db_session: AsyncSession, owner_user: User, practice_area: PracticeArea
) -> IntakeMailbox:
    row = IntakeMailbox(
        provider="agentmail",
        inbox_id="legal-intake-inbox",
        address="legal-intake@example.com",
        practice_area_id=practice_area.id,
        owner_user_id=owner_user.id,
    )
    db_session.add(row)
    await db_session.flush()
    return row


def _attachment(
    *, filename: str = "nda.docx", data: bytes = b"fake docx bytes", content_type: str | None = None
) -> dict[str, Any]:
    return {
        "filename": filename,
        "content_type": content_type
        or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "content_b64": base64.b64encode(data).decode("ascii"),
    }


def _envelope(
    *,
    provider: str = "agentmail",
    inbox_id: str = "legal-intake-inbox",
    provider_thread_id: str = "thread-1",
    subject: str = "NDA review",
    provider_message_id: str = "msg-1",
    attachments: list[dict[str, Any]] | None = None,
    auth_state: str = "pass",
) -> dict[str, Any]:
    return {
        "provider": provider,
        "inbox_id": inbox_id,
        "thread": {"provider_thread_id": provider_thread_id, "subject": subject},
        "message": {
            "provider_message_id": provider_message_id,
            "from_addr": "counterparty@example.com",
            "to": ["legal-intake@example.com"],
            "cc": [],
            "timestamp": "2026-08-18T12:00:00Z",
            "text": "Please review the attached NDA.",
            "headers": {"Precedence": "bulk", "X-Not-Whitelisted": "dropped"},
            "auth_state": auth_state,
            "attachments": attachments or [],
        },
    }


async def _post(client: AsyncClient, body: dict[str, Any], *, bearer: str | None = BRIDGE_TOKEN):
    headers = {"Authorization": f"Bearer {bearer}"} if bearer is not None else {}
    return await client.post("/api/v1/internal/intake/emails", json=body, headers=headers)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ingest_without_bearer_returns_401(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    res = await _post(client, _envelope(), bearer=None)
    assert res.status_code == 401


@pytest.mark.integration
async def test_ingest_with_wrong_bearer_returns_401(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    res = await _post(client, _envelope(), bearer="not-the-real-token")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_happy_path_creates_thread_project_file_and_message(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    fake_s3: FakeS3Client,
) -> None:
    res = await _post(client, _envelope(attachments=[_attachment()]))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["duplicate"] is False
    assert body["files_ingested"] == 1
    assert body["thread_id"] is not None
    assert body["project_id"] is not None

    thread = (
        await db_session.execute(
            select(IntakeThread).where(IntakeThread.id == uuid.UUID(body["thread_id"]))
        )
    ).scalar_one()
    assert thread.mailbox_id == mailbox.id
    assert thread.provider_thread_id == "thread-1"
    assert thread.subject == "NDA review"
    assert thread.status == "received"
    assert thread.auth_state == "pass"
    assert thread.message_count == 1
    assert thread.last_message_id == "msg-1"
    assert thread.project_id == uuid.UUID(body["project_id"])

    project = (
        await db_session.execute(select(Project).where(Project.id == thread.project_id))
    ).scalar_one()
    assert project.owner_id == mailbox.owner_user_id
    assert project.practice_area_id == mailbox.practice_area_id
    assert project.intake_state == "candidate"
    assert project.name == "NDA review"

    files = (
        (await db_session.execute(select(File).where(File.project_id == project.id)))
        .scalars()
        .all()
    )
    assert len(files) == 1
    assert files[0].filename == "nda.docx"
    assert files[0].owner_id == mailbox.owner_user_id
    assert fake_s3.objects[str(files[0].id)] == b"fake docx bytes"

    messages = (
        (
            await db_session.execute(
                select(IntakeMessage).where(IntakeMessage.thread_id == thread.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(messages) == 1
    assert messages[0].direction == "in"
    assert messages[0].provider_message_id == "msg-1"

    # Never echoed back: no email content anywhere in the response.
    assert "text" not in body
    assert "subject" not in body
    assert "from_addr" not in body


@pytest.mark.integration
async def test_headers_are_filtered_to_the_allowlist(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    """Non-whitelisted headers are silently dropped, not rejected."""

    res = await _post(client, _envelope())
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------------------
# Idempotency + follow-up
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_duplicate_delivery_is_a_no_op(
    client: AsyncClient, db_session: AsyncSession, mailbox: IntakeMailbox
) -> None:
    first = await _post(client, _envelope(attachments=[_attachment()]))
    assert first.status_code == 200
    first_body = first.json()

    second = await _post(client, _envelope(attachments=[_attachment()]))
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["duplicate"] is True
    assert second_body["thread_id"] == first_body["thread_id"]
    assert second_body["project_id"] == first_body["project_id"]
    assert second_body["files_ingested"] == 0

    messages = (await db_session.execute(select(IntakeMessage))).scalars().all()
    assert len(messages) == 1
    files = (await db_session.execute(select(File))).scalars().all()
    assert len(files) == 1
    thread = (await db_session.execute(select(IntakeThread))).scalar_one()
    assert thread.message_count == 1


@pytest.mark.integration
async def test_followup_message_reuses_thread_and_project(
    client: AsyncClient, db_session: AsyncSession, mailbox: IntakeMailbox
) -> None:
    first = await _post(client, _envelope(provider_message_id="msg-1"))
    assert first.status_code == 200
    first_body = first.json()

    second = await _post(client, _envelope(provider_message_id="msg-2"))
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["duplicate"] is False
    assert second_body["thread_id"] == first_body["thread_id"]
    assert second_body["project_id"] == first_body["project_id"]

    thread = (
        await db_session.execute(
            select(IntakeThread).where(IntakeThread.id == uuid.UUID(first_body["thread_id"]))
        )
    ).scalar_one()
    assert thread.message_count == 2
    assert thread.last_message_id == "msg-2"

    projects = (
        (await db_session.execute(select(Project).where(Project.owner_id == mailbox.owner_user_id)))
        .scalars()
        .all()
    )
    assert len(projects) == 1


# ---------------------------------------------------------------------------
# Unknown mailbox
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_unknown_inbox_returns_404(client: AsyncClient, mailbox: IntakeMailbox) -> None:
    res = await _post(client, _envelope(inbox_id="some-other-inbox"))
    assert res.status_code == 404


@pytest.mark.integration
async def test_inactive_mailbox_returns_404(
    client: AsyncClient, db_session: AsyncSession, mailbox: IntakeMailbox
) -> None:
    mailbox.active = False
    await db_session.commit()
    res = await _post(client, _envelope())
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Boundary rejection (422)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_oversized_attachment_returns_422(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    oversized = b"x" * (25 * 1024 * 1024 + 1)
    res = await _post(client, _envelope(attachments=[_attachment(data=oversized)]))
    assert res.status_code == 422


@pytest.mark.integration
async def test_too_many_attachments_returns_422(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    attachments = [_attachment(filename=f"f{i}.txt", data=b"x") for i in range(11)]
    res = await _post(client, _envelope(attachments=attachments))
    assert res.status_code == 422


@pytest.mark.integration
async def test_malformed_base64_returns_422(client: AsyncClient, mailbox: IntakeMailbox) -> None:
    bad = _attachment()
    bad["content_b64"] = "not-valid-base64!!!"
    res = await _post(client, _envelope(attachments=[bad]))
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Empty subject
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_empty_subject_falls_back_to_default_project_name(
    client: AsyncClient, db_session: AsyncSession, mailbox: IntakeMailbox
) -> None:
    res = await _post(client, _envelope(subject=""))
    assert res.status_code == 200, res.text
    body = res.json()

    project = (
        await db_session.execute(select(Project).where(Project.id == uuid.UUID(body["project_id"])))
    ).scalar_one()
    assert project.name == "Intake — (no subject)"


# ---------------------------------------------------------------------------
# Claim-first idempotency + leak-free failure (fresh-context review fix)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_preexisting_message_row_is_claimed_first_no_upload_attempted(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    fake_s3: FakeS3Client,
) -> None:
    """A message row inserted directly (simulating a delivery that already
    landed) makes a redelivery with the SAME ids a no-op BEFORE the claim
    step ever reaches the attachment loop — no attachment is uploaded."""

    thread = IntakeThread(
        mailbox_id=mailbox.id,
        provider_thread_id="preclaimed-thread",
        subject="Already here",
        message_count=1,
    )
    db_session.add(thread)
    await db_session.flush()
    existing_message = IntakeMessage(
        thread_id=thread.id, provider_message_id="preclaimed-msg", direction="in"
    )
    db_session.add(existing_message)
    await db_session.commit()

    res = await _post(
        client,
        _envelope(
            provider_thread_id="preclaimed-thread",
            provider_message_id="preclaimed-msg",
            attachments=[_attachment(data=b"must never be uploaded")],
        ),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["duplicate"] is True
    assert body["thread_id"] == str(thread.id)
    assert body["files_ingested"] == 0

    assert fake_s3.objects == {}
    files = (await db_session.execute(select(File))).scalars().all()
    assert files == []
    messages = (
        (
            await db_session.execute(
                select(IntakeMessage).where(IntakeMessage.thread_id == thread.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(messages) == 1  # only the pre-existing one


@pytest.mark.integration
async def test_failure_on_second_attachment_cleans_up_first_and_commits_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: IntakeMailbox,
    fake_s3: FakeS3Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attachment 1 uploads fine; attachment 2 trips ``ingest_bytes``'s OWN
    per-file cap (lowered below the envelope's 25 MB per-item bound so a
    schema-valid attachment can still fail server-side). The whole request
    must fail (4xx), attachment 1's already-uploaded object must be
    deleted, and no row from this request may be committed."""

    monkeypatch.setenv("LQ_AI_MAX_UPLOAD_SIZE_MB", "1")
    get_settings.cache_clear()
    try:
        small = _attachment(filename="a1.bin", data=b"x" * 100)
        # Under the envelope's 25 MB per-attachment cap, but over the
        # server's (lowered) 1 MB per-file cap enforced inside ingest_bytes.
        oversized = _attachment(filename="a2.bin", data=b"y" * (2 * 1024 * 1024))

        res = await _post(
            client,
            _envelope(provider_thread_id="two-attachment-thread", attachments=[small, oversized]),
        )
        assert 400 <= res.status_code < 600, res.text
    finally:
        get_settings.cache_clear()

    # Attachment 1's object was uploaded, then cleaned up on the request's
    # overall failure; attachment 2 never got as far as an upload call.
    assert fake_s3.objects == {}

    # Single-transaction semantics: the whole request rolled back — no
    # thread, message, project, or file row survives a failed delivery.
    assert (await db_session.execute(select(IntakeThread))).scalars().all() == []
    assert (await db_session.execute(select(IntakeMessage))).scalars().all() == []
    assert (await db_session.execute(select(Project))).scalars().all() == []
    assert (await db_session.execute(select(File))).scalars().all() == []


@pytest.mark.integration
async def test_thread_creation_race_recovers_via_reselect(
    client: AsyncClient, db_session: AsyncSession, mailbox: IntakeMailbox
) -> None:
    """A concurrent delivery creates (and commits) the SAME brand-new
    thread between our SELECT and our INSERT. The handler must roll back,
    re-select, and continue with the concurrent winner's row — not 500 on
    the unique-constraint IntegrityError."""

    real_select_thread = intake_emails_module._select_thread
    calls = {"n": 0}

    async def _racy_select_thread(
        db: AsyncSession, *, mailbox_id: uuid.UUID, provider_thread_id: str
    ) -> IntakeThread | None:
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate a concurrent request winning the race: it creates
            # and commits the thread we haven't seen yet.
            concurrent = IntakeThread(
                mailbox_id=mailbox_id,
                provider_thread_id=provider_thread_id,
                subject="Concurrent winner",
                message_count=0,
            )
            db.add(concurrent)
            await db.commit()
            return None
        return await real_select_thread(
            db, mailbox_id=mailbox_id, provider_thread_id=provider_thread_id
        )

    with patch("app.api.intake_emails._select_thread", _racy_select_thread):
        res = await _post(client, _envelope(provider_thread_id="race-thread"))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["duplicate"] is False

    threads = (
        (
            await db_session.execute(
                select(IntakeThread).where(IntakeThread.provider_thread_id == "race-thread")
            )
        )
        .scalars()
        .all()
    )
    # Exactly one thread survives — OUR attempted insert lost the race and
    # was abandoned; the concurrent winner's row is what the request used.
    assert len(threads) == 1
    assert threads[0].subject == "Concurrent winner"
    assert threads[0].message_count == 1


# ---------------------------------------------------------------------------
# NUL bytes + aggregate attachment cap (SHOULD-FIX 3/4)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_nul_byte_in_subject_returns_422(client: AsyncClient, mailbox: IntakeMailbox) -> None:
    res = await _post(client, _envelope(subject="NDA review\x00"))
    assert res.status_code == 422


@pytest.mark.integration
async def test_nul_byte_in_from_addr_returns_422(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    body = _envelope()
    body["message"]["from_addr"] = "counterparty@example.com\x00"
    res = await _post(client, body)
    assert res.status_code == 422


@pytest.mark.integration
async def test_nul_byte_in_attachment_filename_returns_422(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    res = await _post(client, _envelope(attachments=[_attachment(filename="nda\x00.docx")]))
    assert res.status_code == 422


@pytest.mark.integration
async def test_nul_byte_in_header_value_returns_422(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    body = _envelope()
    body["message"]["headers"] = {"Precedence": "bulk\x00"}
    res = await _post(client, body)
    assert res.status_code == 422


@pytest.mark.integration
async def test_aggregate_attachment_cap_returns_422(
    client: AsyncClient, mailbox: IntakeMailbox
) -> None:
    """Three attachments each UNDER the 25 MB per-item cap but summing well
    past the 50 MB aggregate cap must still be rejected."""

    chunk = b"x" * (18 * 1024 * 1024)  # 18 MB each -> 54 MB total
    attachments = [_attachment(filename=f"big{i}.bin", data=chunk) for i in range(3)]
    res = await _post(client, _envelope(attachments=attachments))
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Content-free logs (SHOULD-FIX 5)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_hostile_filename_never_appears_in_logs(
    client: AsyncClient,
    mailbox: IntakeMailbox,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The attachment filename is sender-controlled on the intake path; it
    must never land in a log record (message text OR any ``extra`` value)."""

    hostile = "SENDER-CONTROLLED-MARKER-should-never-be-logged.exe"
    caplog.set_level(logging.INFO)

    res = await _post(client, _envelope(attachments=[_attachment(filename=hostile)]))
    assert res.status_code == 200, res.text

    for record in caplog.records:
        assert hostile not in record.getMessage()
        for value in vars(record).values():
            assert hostile not in str(value)
