"""Worker-side tests for the Playbook EXECUTION pipeline — CLEAN-3a (HS-6).

:func:`app.workers.playbook_worker.playbook_execution_job` dispatches to
:func:`app.playbooks.executor.run_playbook_execution` (which has its own
coverage via :mod:`tests.playbooks.test_executor`). These tests mock the
executor at the worker's import site so the worker's *orchestration* — session
handling, missing-row guard, error settling, and arq registration — is tested
without re-running the LangGraph workflow.

Mirrors :mod:`tests.test_easy_playbook_worker` (the session-factory patch that
binds the worker's own session to the test's rollback-isolated ``db_session``)
and :mod:`tests.tabular.test_worker` (the registration/wiring pins).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.models.document import Document
from app.models.file import File as FileModel
from app.models.playbook import Playbook, PlaybookExecution, PlaybookPosition
from app.models.user import User
from app.playbooks.executor import PlaybookExecutorError
from app.security import hash_password
from app.workers import arq_setup, queue
from app.workers.playbook_worker import PLAYBOOK_EXECUTION_JOB_NAME, playbook_execution_job


@pytest_asyncio.fixture
async def patch_session_factory(db_session: AsyncSession) -> AsyncIterator[None]:
    """Make ``get_session_factory()`` return a factory bound to the test session.

    The worker opens its own session via ``async with factory() as session``; we
    patch the factory to yield ``db_session`` so the test's transaction-rollback
    isolation covers the worker's writes too (mirrors the easy-playbook test).
    """

    class _FakeAsyncContext:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *_exc: Any) -> None:
            return None  # conftest handles rollback at teardown

    class _FakeFactory:
        def __call__(self) -> _FakeAsyncContext:
            return _FakeAsyncContext()

    real_factory = get_session_factory()
    with patch(
        "app.workers.playbook_worker.get_session_factory",
        return_value=_FakeFactory(),
    ):
        yield
    _ = real_factory


async def _make_user(db: AsyncSession) -> User:
    u = User(
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("pw"),
        is_admin=False,
        role="member",
        mfa_enabled=False,
        must_change_password=False,
    )
    db.add(u)
    await db.flush()
    return u


async def _make_document(db: AsyncSession, *, owner: User) -> Document:
    f = FileModel(
        owner_id=owner.id,
        filename=f"contract-{uuid.uuid4().hex[:6]}.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        hash_sha256="c" * 64,
        storage_path=f"playbook-worker-fixture/{uuid.uuid4()}",
        ingestion_status="ready",
    )
    db.add(f)
    await db.flush()
    doc = Document(
        file_id=f.id,
        parser="pymupdf-only",
        parser_version="pymupdf=1.27",
        page_count=1,
        character_count=100,
        normalized_content="x" * 100,
        was_ocrd=False,
    )
    db.add(doc)
    await db.flush()
    return doc


async def _make_playbook(db: AsyncSession, *, author: User) -> Playbook:
    pb = Playbook(name="Test", contract_type="NDA", created_by=author.id)
    db.add(pb)
    await db.flush()
    db.add(
        PlaybookPosition(
            playbook_id=pb.id,
            issue="Confidentiality",
            standard_language="standard",
            severity_if_missing="high",
            detection_keywords=["test"],
        )
    )
    await db.flush()
    return pb


async def _make_execution(db: AsyncSession, *, owner: User) -> PlaybookExecution:
    doc = await _make_document(db, owner=owner)
    playbook = await _make_playbook(db, author=owner)
    row = PlaybookExecution(
        playbook_id=playbook.id,
        target_document_id=doc.id,
        user_id=owner.id,
        status="pending",
    )
    db.add(row)
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# Registration / wiring (the contract between api-side enqueue and the worker)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_playbook_execution_job_name_is_stable_and_matched() -> None:
    """The arq function name is the api↔worker contract; the queue constant and
    the worker constant must agree, and pinning it makes a rename deliberate."""

    assert PLAYBOOK_EXECUTION_JOB_NAME == "playbook_execution_job"
    assert queue.PLAYBOOK_EXECUTION_JOB_NAME == PLAYBOOK_EXECUTION_JOB_NAME


@pytest.mark.unit
def test_worker_registers_playbook_execution_job() -> None:
    """``WorkerSettings.functions`` must include the job or arq would reject
    playbook-execution jobs whose function name it doesn't register."""

    assert playbook_execution_job in arq_setup.WorkerSettings.functions


@pytest.mark.unit
def test_enqueue_helper_exists() -> None:
    """The api-side enqueue helper the endpoint calls must exist and be async."""

    import inspect

    assert inspect.iscoroutinefunction(queue.enqueue_playbook_execution_job)


# ---------------------------------------------------------------------------
# Orchestration behaviour (executor mocked)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_worker_happy_path_dispatches_to_executor(
    db_session: AsyncSession, patch_session_factory: None
) -> None:
    """Delegates to run_playbook_execution with the row's id and reports done."""

    owner = await _make_user(db_session)
    execution = await _make_execution(db_session, owner=owner)
    await db_session.commit()

    exec_mock = AsyncMock(return_value=None)
    with patch("app.workers.playbook_worker.run_playbook_execution", new=exec_mock):
        result = await playbook_execution_job({}, str(execution.id))

    assert result["status"] == "completed"
    exec_mock.assert_awaited_once()
    assert exec_mock.await_args.kwargs["execution_id"] == execution.id


@pytest.mark.integration
async def test_worker_missing_row_returns_early(
    db_session: AsyncSession, patch_session_factory: None
) -> None:
    """A job for a non-existent row returns 'missing' and never calls the executor."""

    exec_mock = AsyncMock()
    with patch("app.workers.playbook_worker.run_playbook_execution", new=exec_mock):
        result = await playbook_execution_job({}, str(uuid.uuid4()))

    assert result["status"] == "missing"
    exec_mock.assert_not_awaited()


@pytest.mark.integration
async def test_worker_reports_executor_refusal(
    db_session: AsyncSession, patch_session_factory: None
) -> None:
    """PlaybookExecutorError (the executor already committed 'error') is caught,
    logged, and reported — not re-raised as an unhandled job failure."""

    owner = await _make_user(db_session)
    execution = await _make_execution(db_session, owner=owner)
    await db_session.commit()

    with patch(
        "app.workers.playbook_worker.run_playbook_execution",
        new=AsyncMock(side_effect=PlaybookExecutorError("unable to start")),
    ):
        result = await playbook_execution_job({}, str(execution.id))

    assert result["status"] == "error"
    assert "unable to start" in result["error"]


@pytest.mark.integration
async def test_worker_baseexception_backstop_settles_error(
    db_session: AsyncSession, patch_session_factory: None
) -> None:
    """If the executor raises something it didn't self-settle, the worker writes
    'error' (NOT 'failed' — the PlaybookExecution CHECK constraint) itself so the
    row doesn't hang at 'running'."""

    owner = await _make_user(db_session)
    execution = await _make_execution(db_session, owner=owner)
    await db_session.commit()

    with patch(
        "app.workers.playbook_worker.run_playbook_execution",
        new=AsyncMock(side_effect=RuntimeError("graph blew up")),
    ):
        result = await playbook_execution_job({}, str(execution.id))

    assert result["status"] == "error"
    assert "graph blew up" in result["error"]

    await db_session.refresh(execution)
    assert execution.status == "error"
    assert execution.completed_at is not None
    assert execution.error is not None
    assert "RuntimeError" in execution.error
    assert "graph blew up" in execution.error


@pytest.mark.integration
async def test_worker_reraises_true_baseexception_after_settling(
    db_session: AsyncSession, patch_session_factory: None
) -> None:
    """A true BaseException (e.g. arq job_timeout → CancelledError, which is NOT
    an Exception subclass) is re-raised after the row is settled to 'error', so
    arq's shutdown machinery still sees the cancel. Guards the load-bearing
    ``if not isinstance(exc, Exception): raise`` branch."""

    owner = await _make_user(db_session)
    execution = await _make_execution(db_session, owner=owner)
    await db_session.commit()

    with (
        patch(
            "app.workers.playbook_worker.run_playbook_execution",
            new=AsyncMock(side_effect=asyncio.CancelledError()),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await playbook_execution_job({}, str(execution.id))

    # Row was settled to a terminal state BEFORE the re-raise.
    await db_session.refresh(execution)
    assert execution.status == "error"
    assert execution.completed_at is not None
