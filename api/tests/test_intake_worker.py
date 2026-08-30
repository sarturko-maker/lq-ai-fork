"""INTAKE-3 (ADR-F086) intake-worker tests — registration + the real job body.

The arq drift-guard (the worker actually consumes the job the api enqueues) stays
from INTAKE-1; the stub tests are replaced by the real core:
:func:`app.workers.intake_worker.process_intake_thread`, driven directly against the
test DB with an injected enqueue (CLAUDE.md DI rules — no monkeypatching, and no
Redis in a unit run).

Covered: the happy path (thread ``processing``, one run on the mailbox OWNER with the
binding's lean budget/steps, the message stamped, the agent conversation stored back);
follow-ups CONTINUING the same agent conversation; the deferral when a run is in
flight; the no-ops (missing thread / nothing pending); the enqueue-failure contract;
a follow-up arriving after the matter was filed; and the invariant that no email
content reaches the conversation's title.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.intake_tools import requeue_pending_intake_message
from app.agents.run_service import is_conversation_in_flight, newest_live_run
from app.config import get_settings
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.intake import IntakeMailbox, IntakeMessage, IntakeThread
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.user import User
from app.security import hash_password
from app.workers.arq_setup import WorkerSettings
from app.workers.intake_worker import (
    DEFAULT_INTAKE_MAX_STEPS,
    INTAKE_EMAIL_JOB_NAME,
    INTAKE_THREAD_TITLE,
    OWNER_MISMATCH_NOTE,
    intake_email_job,
    process_intake_thread,
)
from app.workers.queue import INTAKE_EMAIL_JOB_NAME as QUEUE_SIDE_JOB_NAME


@pytest.mark.unit
def test_intake_email_job_registered_on_worker_settings() -> None:
    """Drift-guard: the worker actually consumes the job the api enqueues.

    A discrepancy here means ``POST /internal/intake/emails`` would enqueue
    a job name the arq-worker container never registered — jobs pile up on
    the queue and are silently never executed.
    """

    assert intake_email_job in WorkerSettings.functions


@pytest.mark.unit
def test_job_name_constants_match_across_api_and_worker() -> None:
    """The api-side enqueue helper and the worker-side function name must
    agree byte-for-byte, or the worker rejects every enqueued job."""

    assert INTAKE_EMAIL_JOB_NAME == QUEUE_SIDE_JOB_NAME == "intake_email_job"


# --------------------------------------------------------------------------- #
# The real job body
# --------------------------------------------------------------------------- #


@dataclass
class Seeded:
    user_id: uuid.UUID
    project_id: uuid.UUID
    mailbox_id: uuid.UUID
    thread_id: uuid.UUID
    message_id: uuid.UUID


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed(
    factory: async_sessionmaker[AsyncSession],
    *,
    budget_profile: str | None = None,
    max_steps: int | None = None,
) -> Seeded:
    async with factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        user = User(
            email=f"iw-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Intake Owner",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            practice_area_id=area_id,
            name="Intake — NDA",
            slug=f"iw-{uuid.uuid4().hex[:6]}",
            intake_state="candidate",
        )
        db.add(project)
        mailbox = IntakeMailbox(
            provider="agentmail",
            inbox_id=f"inbox-{uuid.uuid4().hex[:8]}",
            address="legal-intake@example.com",
            practice_area_id=area_id,
            owner_user_id=user.id,
            default_budget_profile=budget_profile,
            max_steps=max_steps,
        )
        db.add(mailbox)
        await db.flush()
        thread = IntakeThread(
            mailbox_id=mailbox.id,
            provider_thread_id=f"thr-{uuid.uuid4().hex[:8]}",
            project_id=project.id,
            subject="Confidential — please review the attached NDA",
            status="received",
            auth_state="pass",
            message_count=1,
        )
        db.add(thread)
        await db.flush()
        message = IntakeMessage(
            thread_id=thread.id,
            provider_message_id=f"msg-{uuid.uuid4().hex[:8]}",
            direction="in",
            from_addr="counterparty@example.net",
            to_addrs=["legal-intake@example.com"],
            subject="Confidential — please review the attached NDA",
            body_text="Please review the attached mutual NDA.",
            attachment_filenames=["Mutual-NDA.docx"],
            provider_timestamp=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        )
        db.add(message)
        await db.commit()
        return Seeded(
            user_id=user.id,
            project_id=project.id,
            mailbox_id=mailbox.id,
            thread_id=thread.id,
            message_id=message.id,
        )


@pytest_asyncio.fixture
async def seeded(commit_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[Seeded]:
    row = await _seed(commit_factory)
    try:
        yield row
    finally:
        await _cleanup(commit_factory, row)


async def _cleanup(factory: async_sessionmaker[AsyncSession], row: Seeded) -> None:
    async with factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == row.user_id))
        await db.execute(delete(IntakeMailbox).where(IntakeMailbox.id == row.mailbox_id))
        await db.execute(delete(AgentRun).where(AgentRun.user_id == row.user_id))
        await db.execute(delete(AgentThread).where(AgentThread.user_id == row.user_id))
        await db.execute(delete(Project).where(Project.owner_id == row.user_id))
        await db.execute(delete(User).where(User.id == row.user_id))
        await db.commit()


async def _ok(_run_id: uuid.UUID) -> bool:
    return True


async def _fails(_run_id: uuid.UUID) -> bool:
    return False


@pytest.mark.integration
async def test_happy_path_starts_one_run_owned_by_the_mailbox_owner(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    out = await process_intake_thread(commit_factory, get_settings(), seeded.thread_id, enqueue=_ok)
    assert out["status"] == "started"
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        message = await db.get(IntakeMessage, seeded.message_id)
        run = await db.get(AgentRun, uuid.UUID(out["run_id"]))
        assert thread is not None and message is not None and run is not None
        assert thread.status == "processing"
        assert thread.agent_thread_id == run.thread_id
        assert message.run_id == run.id
        # The mailbox binding decides ownership, budget and step ceiling.
        assert run.user_id == seeded.user_id
        assert run.project_id == seeded.project_id
        assert run.budget_profile == "economy"
        assert run.max_steps == DEFAULT_INTAKE_MAX_STEPS
        assert run.status == "running"
        # The prompt carries the fenced email (under this run's own nonce label —
        # B1); the TITLE never does.
        assert "----- BEGIN INTAKE EMAIL " in run.prompt
        assert "----- END INTAKE EMAIL " in run.prompt
        agent_thread = await db.get(AgentThread, run.thread_id)
        assert agent_thread is not None
        assert agent_thread.title == INTAKE_THREAD_TITLE
        assert "NDA" not in agent_thread.title


@pytest.mark.integration
async def test_mailbox_binding_overrides_budget_and_steps(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    row = await _seed(commit_factory, budget_profile="balanced", max_steps=7)
    try:
        out = await process_intake_thread(
            commit_factory, get_settings(), row.thread_id, enqueue=_ok
        )
        assert out["status"] == "started"
        async with commit_factory() as db:
            run = await db.get(AgentRun, uuid.UUID(out["run_id"]))
            assert run is not None
            assert run.budget_profile == "balanced"
            assert run.max_steps == 7
    finally:
        await _cleanup(commit_factory, row)


@pytest.mark.integration
async def test_follow_up_continues_the_same_agent_conversation(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    first = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    # Settle the first run, then land a follow-up message on the same thread.
    async with commit_factory() as db:
        run = await db.get(AgentRun, uuid.UUID(first["run_id"]))
        assert run is not None
        run.status = "completed"
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        thread.message_count = 2
        db.add(
            IntakeMessage(
                thread_id=seeded.thread_id,
                provider_message_id=f"msg-{uuid.uuid4().hex[:8]}",
                direction="in",
                from_addr="counterparty@example.net",
                to_addrs=["legal-intake@example.com"],
                subject="Re: NDA",
                body_text="Any update?",
            )
        )
        await db.commit()

    second = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    assert second["status"] == "started"
    assert second["run_id"] != first["run_id"]
    async with commit_factory() as db:
        run_a = await db.get(AgentRun, uuid.UUID(first["run_id"]))
        run_b = await db.get(AgentRun, uuid.UUID(second["run_id"]))
        assert run_a is not None and run_b is not None
        # The SAME agent conversation — that is what carries conversation memory.
        assert run_a.thread_id == run_b.thread_id
        assert "message 2 on this thread" in run_b.prompt


@pytest.mark.integration
async def test_in_flight_run_defers_instead_of_double_running(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    first = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    assert first["status"] == "started"
    async with commit_factory() as db:
        db.add(
            IntakeMessage(
                thread_id=seeded.thread_id,
                provider_message_id=f"msg-{uuid.uuid4().hex[:8]}",
                direction="in",
                from_addr="counterparty@example.net",
                to_addrs=["legal-intake@example.com"],
                body_text="Adding one more thing.",
            )
        )
        await db.commit()
    out = await process_intake_thread(commit_factory, get_settings(), seeded.thread_id, enqueue=_ok)
    assert out["status"] == "deferred"
    async with commit_factory() as db:
        runs = (
            (await db.execute(select(AgentRun).where(AgentRun.user_id == seeded.user_id)))
            .scalars()
            .all()
        )
        assert len(runs) == 1


@pytest.mark.integration
async def test_no_pending_message_is_a_noop(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    first = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    assert first["status"] == "started"
    async with commit_factory() as db:
        run = await db.get(AgentRun, uuid.UUID(first["run_id"]))
        assert run is not None
        run.status = "completed"
        await db.commit()
    out = await process_intake_thread(commit_factory, get_settings(), seeded.thread_id, enqueue=_ok)
    assert out == {
        "status": "noop",
        "reason": "no_pending_message",
        "thread_id": str(seeded.thread_id),
    }


@pytest.mark.integration
async def test_missing_thread_is_a_noop(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    ghost = uuid.uuid4()
    out = await process_intake_thread(commit_factory, get_settings(), ghost, enqueue=_ok)
    assert out == {"status": "noop", "reason": "thread_missing", "thread_id": str(ghost)}


@pytest.mark.integration
async def test_enqueue_failure_errors_the_thread_and_leaves_the_message_for_retry(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    out = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_fails
    )
    assert out["status"] == "error"
    assert out["reason"] == "enqueue_failed"
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        message = await db.get(IntakeMessage, seeded.message_id)
        assert thread is not None and message is not None
        assert thread.status == "error"
        # Unclaimed, so a re-enqueue can retry this email cleanly.
        assert message.run_id is None
        run = (
            (await db.execute(select(AgentRun).where(AgentRun.user_id == seeded.user_id)))
            .scalars()
            .one()
        )
        assert run.status == "failed"


@pytest.mark.integration
async def test_follow_up_after_the_matter_was_filed_parks_the_thread(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    """A 'dealt_with' outcome archives the matter; a later message must not spend a
    run against a matter composition would refuse to bind."""
    async with commit_factory() as db:
        project = await db.get(Project, seeded.project_id)
        assert project is not None
        # A closed matter is archived_at; intake_state stays 'candidate' (provenance —
        # ADR-F086 A1: the agent path never writes it).
        project.archived_at = datetime.now(tz=UTC)
        await db.commit()
    out = await process_intake_thread(commit_factory, get_settings(), seeded.thread_id, enqueue=_ok)
    assert out["status"] == "filed"
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.status == "awaiting_human"
        assert thread.outcome_note is not None
        runs = (
            (await db.execute(select(AgentRun).where(AgentRun.user_id == seeded.user_id)))
            .scalars()
            .all()
        )
        assert runs == []


@pytest.mark.integration
async def test_owner_mismatch_errors_the_thread(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    """S3: the matter's owner can be changed out of band, and the mailbox owner is who
    every intake run is composed AS — a mismatch must refuse loudly, not compose a run
    for a user who does not own the matter."""
    async with commit_factory() as db:
        other = User(
            email=f"other-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Someone Else",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(other)
        await db.flush()
        project = await db.get(Project, seeded.project_id)
        assert project is not None
        project.owner_id = other.id
        await db.commit()
        other_id = other.id
    try:
        out = await process_intake_thread(
            commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
        )
        assert out["status"] == "error"
        assert out["reason"] == "owner_mismatch"
        async with commit_factory() as db:
            thread = await db.get(IntakeThread, seeded.thread_id)
            assert thread is not None
            assert thread.status == "error"
            assert thread.outcome_note == OWNER_MISMATCH_NOTE
            runs = (
                (await db.execute(select(AgentRun).where(AgentRun.project_id == seeded.project_id)))
                .scalars()
                .all()
            )
            assert runs == []
    finally:
        async with commit_factory() as db:
            project = await db.get(Project, seeded.project_id)
            if project is not None:
                project.owner_id = seeded.user_id
            await db.commit()
            await db.execute(delete(User).where(User.id == other_id))
            await db.commit()


@pytest.mark.integration
async def test_unknown_budget_profile_degrades_to_the_default(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """S4: the column has no DB CHECK; an out-of-band value must not raise (an
    exception escapes to arq and the job retries forever on the same bad row)."""
    row = await _seed(commit_factory, budget_profile="lavish")
    try:
        out = await process_intake_thread(
            commit_factory, get_settings(), row.thread_id, enqueue=_ok
        )
        assert out["status"] == "started"
        async with commit_factory() as db:
            run = await db.get(AgentRun, uuid.UUID(out["run_id"]))
            assert run is not None
            assert run.budget_profile == "economy"
    finally:
        await _cleanup(commit_factory, row)


@pytest.mark.integration
async def test_deferred_message_is_picked_up_after_the_run_settles(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    """B3 end-to-end: defer -> settle -> the re-enqueue hook hands the message back ->
    the next job starts run 2 on the SAME agent conversation."""
    first = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    assert first["status"] == "started"

    async with commit_factory() as db:
        db.add(
            IntakeMessage(
                thread_id=seeded.thread_id,
                provider_message_id=f"msg-{uuid.uuid4().hex[:8]}",
                direction="in",
                from_addr="counterparty@example.net",
                to_addrs=["legal-intake@example.com"],
                body_text="One more thing.",
            )
        )
        await db.commit()

    # While run 1 is in flight the follow-up is deliberately left unclaimed.
    assert (
        await process_intake_thread(commit_factory, get_settings(), seeded.thread_id, enqueue=_ok)
    )["status"] == "deferred"

    # Settling run 1 frees the thread; the run job's exit hook re-enqueues.
    async with commit_factory() as db:
        run = await db.get(AgentRun, uuid.UUID(first["run_id"]))
        assert run is not None
        run.status = "completed"
        await db.commit()

    calls: list[tuple[uuid.UUID, str]] = []

    async def fake_enqueue(thread_id: uuid.UUID, provider_message_id: str) -> bool:
        calls.append((thread_id, provider_message_id))
        return True

    assert await requeue_pending_intake_message(
        commit_factory, uuid.UUID(first["run_id"]), enqueue=fake_enqueue
    )
    assert [c[0] for c in calls] == [seeded.thread_id]

    second = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    assert second["status"] == "started"
    assert second["run_id"] != first["run_id"]
    async with commit_factory() as db:
        run_a = await db.get(AgentRun, uuid.UUID(first["run_id"]))
        run_b = await db.get(AgentRun, uuid.UUID(second["run_id"]))
        assert run_a is not None and run_b is not None
        assert run_a.thread_id == run_b.thread_id


# --------------------------------------------------------------------------- #
# In-flight = the conversation's NEWEST live run (ADR-F087, INTAKE-4b live test)
# --------------------------------------------------------------------------- #


async def _add_run(
    factory: async_sessionmaker[AsyncSession],
    row: Seeded,
    agent_thread_id: uuid.UUID,
    *,
    status: str,
) -> uuid.UUID:
    """One more run on an EXISTING conversation, newer than the ones before it."""
    async with factory() as db:
        run = AgentRun(
            user_id=row.user_id,
            thread_id=agent_thread_id,
            project_id=row.project_id,
            status=status,
            prompt=f"[resume: {status}]",
            max_steps=8,
            started_at=datetime.now(tz=UTC) + timedelta(seconds=5),
        )
        db.add(run)
        await db.commit()
        return run.id


async def _pause_and_add_follow_up(
    factory: async_sessionmaker[AsyncSession], row: Seeded, run_id: uuid.UUID
) -> uuid.UUID:
    """Park the run at ``awaiting_input`` (a HITL pause — the row is never mutated
    again) and drop an unclaimed follow-up on the thread. Returns the conversation."""
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        run.status = "awaiting_input"
        agent_thread_id = run.thread_id
        db.add(
            IntakeMessage(
                thread_id=row.thread_id,
                provider_message_id=f"msg-{uuid.uuid4().hex[:8]}",
                direction="in",
                from_addr="counterparty@example.net",
                to_addrs=["legal-intake@example.com"],
                body_text="One more thing, while you were waiting for the lawyer.",
            )
        )
        await db.commit()
        return agent_thread_id


@pytest.mark.integration
async def test_a_paused_run_alone_still_holds_the_conversation(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    """The lawyer owns the next move: nothing may start beside a live ask."""
    first = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    await _pause_and_add_follow_up(commit_factory, seeded, uuid.UUID(first["run_id"]))

    out = await process_intake_thread(commit_factory, get_settings(), seeded.thread_id, enqueue=_ok)
    assert out["status"] == "deferred"


@pytest.mark.integration
async def test_a_completed_resume_frees_the_conversation_the_pause_never_will(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    """THE live bug (ADR-F087). HITL-2 never mutates the paused row, so it sits at
    ``awaiting_input`` forever — and the old "does ANY run sit at running/
    awaiting_input" check therefore deferred every sibling FOREVER, even after the
    resume run had done the work and completed. The rule is the NEWEST live run."""
    first = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    agent_thread_id = await _pause_and_add_follow_up(
        commit_factory, seeded, uuid.UUID(first["run_id"])
    )
    await _add_run(commit_factory, seeded, agent_thread_id, status="completed")

    out = await process_intake_thread(commit_factory, get_settings(), seeded.thread_id, enqueue=_ok)
    assert out["status"] == "started"
    assert out["run_id"] != first["run_id"]
    async with commit_factory() as db:
        started = await db.get(AgentRun, uuid.UUID(out["run_id"]))
        assert started is not None
        # Same conversation — the paused run's ask is history, not a fork.
        assert started.thread_id == agent_thread_id


@pytest.mark.integration
async def test_a_failed_resume_leaves_the_ask_live_and_the_conversation_busy(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    """A resume that died BEFORE driving the graph (enqueue failure, worker restart)
    never consumed the interrupt: the ask is still answerable, so the conversation is
    still busy. `failed`/`cancelled` are excluded from "newest live run" for exactly
    this reason — the same rule the resume endpoint's stale guard applies."""
    first = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    agent_thread_id = await _pause_and_add_follow_up(
        commit_factory, seeded, uuid.UUID(first["run_id"])
    )
    for dead in ("failed", "cancelled"):
        await _add_run(commit_factory, seeded, agent_thread_id, status=dead)
        out = await process_intake_thread(
            commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
        )
        assert out["status"] == "deferred", dead


@pytest.mark.integration
async def test_newest_live_run_is_one_rule_for_both_call_sites(
    commit_factory: async_sessionmaker[AsyncSession], seeded: Seeded
) -> None:
    """The unit behind both the worker's deferral and the resume endpoint's
    stale-resume guard. Two copies of this rule drifted once and starved a mailbox;
    pin the shared one."""
    first = await process_intake_thread(
        commit_factory, get_settings(), seeded.thread_id, enqueue=_ok
    )
    paused_id = uuid.UUID(first["run_id"])
    agent_thread_id = await _pause_and_add_follow_up(commit_factory, seeded, paused_id)

    async with commit_factory() as db:
        newest = await newest_live_run(db, agent_thread_id)
        assert newest is not None
        assert (newest.id, newest.status) == (paused_id, "awaiting_input")
        assert await is_conversation_in_flight(db, agent_thread_id) is True

    # A failed successor does not supersede the pause (it never consumed it).
    await _add_run(commit_factory, seeded, agent_thread_id, status="failed")
    async with commit_factory() as db:
        newest = await newest_live_run(db, agent_thread_id)
        assert newest is not None and newest.id == paused_id
        assert await is_conversation_in_flight(db, agent_thread_id) is True

    # A completed one does: the ask is resolved and the conversation is free.
    completed_id = await _add_run(commit_factory, seeded, agent_thread_id, status="completed")
    async with commit_factory() as db:
        newest = await newest_live_run(db, agent_thread_id)
        assert newest is not None and newest.id == completed_id
        assert await is_conversation_in_flight(db, agent_thread_id) is False

    # An unknown conversation is neither live nor in flight.
    async with commit_factory() as db:
        assert await newest_live_run(db, uuid.uuid4()) is None
        assert await is_conversation_in_flight(db, uuid.uuid4()) is False
