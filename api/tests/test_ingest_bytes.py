"""Unit/integration tests for ``app.ingest.ingest_bytes()`` — INTAKE-1 (ADR-F086).

Covers the packaged ingest primitive extracted from ``app.api.files.upload_file``:

* Happy path — validates, stores, and records a ``files`` row; only
  flushes (never commits), so the caller controls the transaction.
* Filename validation (empty/whitespace → ``ValidationError``).
* Content-type fallback to :data:`app.ingest.DEFAULT_MIME`.
* Size cap (``PayloadTooLarge``, same ``limit_bytes``/``received_bytes``
  shape the HTTP route's 413 uses).
* Enqueue failure is non-fatal.
* A flush-time ``IntegrityError`` (bad FK) cleans up the just-uploaded
  storage object before re-raising.

``test_files_endpoints.py`` covers the HTTP-route-level behavior
(``upload_file`` calling through to this function) and pins that the
existing upload test suite passes unchanged.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import PayloadTooLarge, ValidationError
from app.ingest import DEFAULT_MIME, ingest_bytes
from app.models.file import File
from app.models.user import User
from app.security import hash_password
from tests.test_storage_streaming import FakeS3Client


@pytest_asyncio.fixture
async def fake_s3() -> FakeS3Client:
    return FakeS3Client()


@pytest_asyncio.fixture(autouse=True)
async def _patch_s3(fake_s3: FakeS3Client) -> AsyncIterator[None]:
    @asynccontextmanager
    async def _ctx() -> AsyncIterator[FakeS3Client]:
        yield fake_s3

    with patch("app.storage.s3_client", _ctx):
        yield


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        email=f"ingest-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Ingest Test Owner",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.integration
async def test_ingest_bytes_happy_path(
    db_session: AsyncSession, owner: User, fake_s3: FakeS3Client
) -> None:
    settings = get_settings()
    payload = b"hello world" * 100

    row = await ingest_bytes(
        session=db_session,
        settings=settings,
        owner_id=owner.id,
        project_id=None,
        filename="contract.pdf",
        content_type="application/pdf",
        data=payload,
    )

    assert row.filename == "contract.pdf"
    assert row.mime_type == "application/pdf"
    assert row.size_bytes == len(payload)
    assert row.hash_sha256 == hashlib.sha256(payload).hexdigest()
    assert row.storage_path == str(row.id)
    assert row.ingestion_status == "pending"
    assert row.owner_id == owner.id
    assert row.project_id is None
    assert fake_s3.objects[str(row.id)] == payload

    # ingest_bytes only flushes, never commits — the row is visible within
    # this still-open transaction, and the caller owns the commit boundary.
    persisted = (await db_session.execute(select(File).where(File.id == row.id))).scalar_one()
    assert persisted.filename == "contract.pdf"


@pytest.mark.integration
async def test_ingest_bytes_strips_filename_and_rejects_blank(
    db_session: AsyncSession, owner: User, fake_s3: FakeS3Client
) -> None:
    settings = get_settings()

    row = await ingest_bytes(
        session=db_session,
        settings=settings,
        owner_id=owner.id,
        project_id=None,
        filename="  padded.txt  ",
        content_type="text/plain",
        data=b"x",
    )
    assert row.filename == "padded.txt"

    with pytest.raises(ValidationError):
        await ingest_bytes(
            session=db_session,
            settings=settings,
            owner_id=owner.id,
            project_id=None,
            filename="   ",
            content_type="text/plain",
            data=b"x",
        )


@pytest.mark.integration
async def test_ingest_bytes_defaults_missing_content_type(
    db_session: AsyncSession, owner: User
) -> None:
    settings = get_settings()
    row = await ingest_bytes(
        session=db_session,
        settings=settings,
        owner_id=owner.id,
        project_id=None,
        filename="blob.bin",
        content_type=None,
        data=b"x",
    )
    assert row.mime_type == DEFAULT_MIME


@pytest.mark.integration
async def test_ingest_bytes_oversized_raises_payload_too_large(
    db_session: AsyncSession, owner: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LQ_AI_MAX_UPLOAD_SIZE_MB", "1")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        oversized = b"X" * (2 * 1024 * 1024)
        with pytest.raises(PayloadTooLarge) as exc:
            await ingest_bytes(
                session=db_session,
                settings=settings,
                owner_id=owner.id,
                project_id=None,
                filename="big.bin",
                content_type="application/octet-stream",
                data=oversized,
            )
        assert exc.value.details["limit_bytes"] == 1 * 1024 * 1024
        assert exc.value.details["received_bytes"] == len(oversized)
    finally:
        get_settings.cache_clear()


@pytest.mark.integration
async def test_ingest_bytes_enqueue_failure_is_non_fatal(
    db_session: AsyncSession, owner: User
) -> None:
    settings = get_settings()
    with patch(
        "app.workers.queue.enqueue_ingest_job",
        side_effect=RuntimeError("redis is down"),
    ):
        row = await ingest_bytes(
            session=db_session,
            settings=settings,
            owner_id=owner.id,
            project_id=None,
            filename="ok.txt",
            content_type="text/plain",
            data=b"still works",
        )
    assert row.ingestion_status == "pending"


@pytest.mark.integration
async def test_ingest_bytes_cleans_up_storage_on_integrity_error(
    db_session: AsyncSession, fake_s3: FakeS3Client
) -> None:
    """A bad owner_id (FK violation at flush) deletes the just-uploaded object."""

    settings = get_settings()
    bogus_owner_id = uuid.uuid4()  # no such row in `users`

    with pytest.raises(IntegrityError):
        await ingest_bytes(
            session=db_session,
            settings=settings,
            owner_id=bogus_owner_id,
            project_id=None,
            filename="orphan.txt",
            content_type="text/plain",
            data=b"never persisted",
        )

    assert fake_s3.objects == {}


@pytest.mark.integration
async def test_ingest_bytes_threads_project_id_and_created_by_run_id(
    db_session: AsyncSession, owner: User
) -> None:
    settings = get_settings()
    row = await ingest_bytes(
        session=db_session,
        settings=settings,
        owner_id=owner.id,
        project_id=None,
        filename="no-run.txt",
        content_type="text/plain",
        data=b"x",
        created_by_run_id=None,
    )
    assert row.project_id is None
    assert row.created_by_run_id is None
