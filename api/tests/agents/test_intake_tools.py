"""INTAKE-3 intake-tool tests (ADR-F086).

Drives the two intake tools through the real test DB:

* the grant set (two tools; DISJOINT from every matter + domain grant — confinement),
* ``record_intake_outcome``: the two outcomes and their thread/matter effects
  (dealt_with CLOSES the matter via archived_at; needs_human leaves it open, and
  neither ever writes ``projects.intake_state`` — that is provenance, ADR-F086 A1),
  reject-not-truncate validation, idempotent overwrite, and the guard receipt +
  audit carrying counts/IDs only — never the label or the note,
* ``draft_email_reply``: records a ``direction='out'`` row and SENDS NOTHING;
  attachment ids outside the matter are refused (no existence disclosure),
* the R7 safe-fail hook: a settled run whose thread never got an outcome parks the
  thread for the lawyer with the FIXED fork-authored note; a concluded thread and a
  non-intake run are untouched.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.commercial_tools import COMMERCIAL_TOOL_NAMES
from app.agents.intake_tools import (
    INTAKE_TOOL_NAMES,
    NO_OUTCOME_NOTE,
    _draft_email_reply,
    _record_intake_outcome,
    build_intake_tools,
    requeue_pending_intake_message,
    safe_fail_intake_thread,
)
from app.agents.matter_fact_tools import MATTER_FACT_TOOL_NAMES
from app.agents.matter_memory_tools import MATTER_MEMORY_TOOL_NAMES
from app.agents.matter_roster_tools import MATTER_ROSTER_TOOL_NAMES
from app.agents.tools import MATTER_TOOL_NAMES, MatterBinding
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.file import File
from app.models.intake import IntakeMailbox, IntakeMessage, IntakeThread
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration


@dataclass
class SeededIntake:
    user_id: uuid.UUID
    project_id: uuid.UUID
    mailbox_id: uuid.UUID
    thread_id: uuid.UUID
    message_id: uuid.UUID
    file_id: uuid.UUID


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_intake(
    factory: async_sessionmaker[AsyncSession], *, intake_state: str | None = "candidate"
) -> SeededIntake:
    async with factory() as db:
        area_id = (
            await db.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        user = User(
            email=f"intake-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Intake Queue Owner",
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
            name="Intake — NDA review",
            slug=f"intake-{uuid.uuid4().hex[:6]}",
            intake_state=intake_state,
        )
        db.add(project)
        await db.flush()
        file = File(
            owner_id=user.id,
            project_id=project.id,
            filename="Mutual-NDA.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=1234,
            hash_sha256=uuid.uuid4().hex,
            storage_path=str(uuid.uuid4()),
            ingestion_status="ready",
        )
        db.add(file)
        mailbox = IntakeMailbox(
            provider="agentmail",
            inbox_id=f"inbox-{uuid.uuid4().hex[:8]}",
            address="legal-intake@example.com",
            practice_area_id=area_id,
            owner_user_id=user.id,
        )
        db.add(mailbox)
        await db.flush()
        thread = IntakeThread(
            mailbox_id=mailbox.id,
            provider_thread_id=f"thr-{uuid.uuid4().hex[:8]}",
            project_id=project.id,
            subject="Please review the attached NDA",
            status="processing",
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
            subject="Please review the attached NDA",
            body_text="Hi, please review the attached mutual NDA.",
            attachment_filenames=["Mutual-NDA.docx"],
            provider_timestamp=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        )
        db.add(message)
        await db.commit()
        return SeededIntake(
            user_id=user.id,
            project_id=project.id,
            mailbox_id=mailbox.id,
            thread_id=thread.id,
            message_id=message.id,
            file_id=file.id,
        )


@pytest_asyncio.fixture
async def seeded(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SeededIntake]:
    row = await _seed_intake(commit_factory)
    try:
        yield row
    finally:
        async with commit_factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == row.user_id))
            # intake_messages CASCADE with the thread; the thread CASCADEs with the mailbox.
            await db.execute(delete(IntakeMailbox).where(IntakeMailbox.id == row.mailbox_id))
            await db.execute(delete(AgentRun).where(AgentRun.user_id == row.user_id))
            await db.execute(delete(AgentThread).where(AgentThread.user_id == row.user_id))
            await db.execute(delete(File).where(File.owner_id == row.user_id))
            await db.execute(delete(Project).where(Project.owner_id == row.user_id))
            await db.execute(delete(User).where(User.id == row.user_id))
            await db.commit()


def _binding(row: SeededIntake) -> MatterBinding:
    return MatterBinding(
        project_id=row.project_id,
        user_id=row.user_id,
        name="Intake — NDA review",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )


async def _make_run(
    factory: async_sessionmaker[AsyncSession],
    row: SeededIntake,
    *,
    status: str = "running",
    is_intake_run: bool = True,
) -> uuid.UUID:
    """One agent run on this matter.

    ``is_intake_run`` binds the new conversation to the intake thread's
    ``agent_thread_id`` — the identity every intake hook keys on (S2/S5). ``False``
    models a lawyer's ORDINARY cockpit chat on the same matter.
    """
    async with factory() as db:
        thread = AgentThread(user_id=row.user_id, project_id=row.project_id, title="Legal intake")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=row.user_id,
            thread_id=thread.id,
            project_id=row.project_id,
            status=status,
            prompt="intake",
            max_steps=8,
        )
        db.add(run)
        if is_intake_run:
            intake_thread = await db.get(IntakeThread, row.thread_id)
            assert intake_thread is not None
            intake_thread.agent_thread_id = thread.id
        await db.commit()
        return run.id


# --------------------------------------------------------------------------- #
# Grant set / confinement
# --------------------------------------------------------------------------- #


def test_build_grants_exactly_the_two_intake_tools() -> None:
    tools = build_intake_tools(
        async_sessionmaker(),
        run_id=uuid.uuid4(),
        binding=MatterBinding(
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="m",
            privileged=False,
            minimum_inference_tier=None,
            practice_area_id=None,
        ),
    )
    assert [t.__name__ for t in tools] == ["record_intake_outcome", "draft_email_reply"]
    assert sorted(INTAKE_TOOL_NAMES) == ["draft_email_reply", "record_intake_outcome"]


def test_grant_set_disjoint_from_every_other_grant() -> None:
    for other in (
        MATTER_TOOL_NAMES,
        MATTER_MEMORY_TOOL_NAMES,
        MATTER_FACT_TOOL_NAMES,
        MATTER_ROSTER_TOOL_NAMES,
        COMMERCIAL_TOOL_NAMES,
    ):
        assert INTAKE_TOOL_NAMES.isdisjoint(other)


# --------------------------------------------------------------------------- #
# record_intake_outcome
# --------------------------------------------------------------------------- #


async def test_dealt_with_files_the_thread_and_closes_the_matter(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    async with commit_factory() as db:
        out = await _record_intake_outcome(
            db,
            _binding(seeded),
            outcome="dealt_with",
            label="marketing",
            note="Vendor marketing email; nothing needed.",
        )
        await db.commit()
    assert "dealt_with" in out
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        project = await db.get(Project, seeded.project_id)
        assert thread is not None and project is not None
        assert thread.outcome == "dealt_with"
        assert thread.status == "handled"
        assert thread.label == "marketing"
        assert thread.outcome_note == "Vendor marketing email; nothing needed."
        assert project.archived_at is not None
        # intake_state is PROVENANCE, never a lifecycle the agent drives (ADR-F086 A1).
        assert project.intake_state == "candidate"


async def test_needs_human_keeps_the_matter_open(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            outcome="needs_human",
            label="NDA review",
            note="Redline drafted.",
        )
        await db.commit()
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        project = await db.get(Project, seeded.project_id)
        assert thread is not None and project is not None
        assert thread.outcome == "needs_human"
        assert thread.status == "awaiting_human"
        assert project.archived_at is None
        assert project.intake_state == "candidate"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"outcome": "filed", "label": "x", "note": "y"},
        {"outcome": "candidate_matter", "label": "x", "note": "y"},  # retired (ADR-F086 A1)
        {"outcome": "dealt_with", "label": "", "note": "y"},
        {"outcome": "dealt_with", "label": "x", "note": ""},
        {"outcome": "dealt_with", "label": "x" * 201, "note": "y"},
        {"outcome": "dealt_with", "label": "x", "note": "y" * 2001},
        {"outcome": "dealt_with", "label": "x\x00y", "note": "y"},
    ],
)
async def test_invalid_proposals_are_rejected_and_write_nothing(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake, kwargs: dict[str, str]
) -> None:
    async with commit_factory() as db:
        out = await _record_intake_outcome(db, _binding(seeded), **kwargs)
        await db.commit()
    assert out.startswith("Rejected")
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.outcome is None
        assert thread.status == "processing"


async def test_second_call_overwrites_last_wins(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    async with commit_factory() as db:
        await _record_intake_outcome(
            db, _binding(seeded), outcome="dealt_with", label="spam", note="Noise."
        )
        await db.commit()
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            outcome="needs_human",
            note="On reflection the lawyer should see this.",
            label="unclear",
        )
        await db.commit()
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        project = await db.get(Project, seeded.project_id)
        assert thread is not None and project is not None
        assert thread.outcome == "needs_human"
        assert thread.status == "awaiting_human"
        # B4: last-wins must win WHOLE — the earlier dealt_with closed the matter, so
        # changing to needs_human has to re-open it or the thread and the matter
        # disagree about whether this is live work.
        assert project.archived_at is None


async def test_non_intake_matter_records_nothing(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A binding whose project has no intake thread is refused honestly."""
    async with commit_factory() as db:
        user = User(
            email=f"plain-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Plain",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(owner_id=user.id, name="Plain", slug=f"plain-{uuid.uuid4().hex[:6]}")
        db.add(project)
        await db.commit()
        user_id, project_id = user.id, project.id
    try:
        async with commit_factory() as db:
            out = await _record_intake_outcome(
                db,
                MatterBinding(
                    project_id=project_id,
                    user_id=user_id,
                    name="Plain",
                    privileged=False,
                    minimum_inference_tier=None,
                    practice_area_id=None,
                ),
                outcome="dealt_with",
                label="x",
                note="y",
            )
        assert "not an intake thread" in out
    finally:
        async with commit_factory() as db:
            await db.execute(delete(Project).where(Project.owner_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


async def test_guarded_dispatch_audits_counts_only_never_the_note(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    run_id = await _make_run(commit_factory, seeded)
    tools = build_intake_tools(commit_factory, run_id=run_id, binding=_binding(seeded))
    record = next(t for t in tools if t.__name__ == "record_intake_outcome")
    secret_note = "the counterparty offered a side letter nobody should see in an audit row"
    out = await record("needs_human", "NDA review", secret_note)
    assert "recorded" in out
    async with commit_factory() as db:
        rows = (
            (await db.execute(select(AuditLog).where(AuditLog.user_id == seeded.user_id)))
            .scalars()
            .all()
        )
        assert rows, "the guard must leave an audit row"
        blob = " ".join(str(r.details) for r in rows)
        assert secret_note not in blob
        assert "NDA review" not in blob


# --------------------------------------------------------------------------- #
# draft_email_reply
# --------------------------------------------------------------------------- #


async def test_draft_reply_records_an_out_message_and_sends_nothing(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=run_id,
            to=["counterparty@example.net"],
            subject="Re: Please review the attached NDA",
            body="Thanks — we have it and will come back to you this week.",
            attachment_file_ids=[str(seeded.file_id)],
        )
        await db.commit()
    assert "NOT sent" in out
    assert "INTAKE-4" in out
    async with commit_factory() as db:
        drafts = (
            (
                await db.execute(
                    select(IntakeMessage).where(
                        IntakeMessage.thread_id == seeded.thread_id,
                        IntakeMessage.direction == "out",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(drafts) == 1
        draft = drafts[0]
        assert draft.run_id == run_id
        assert draft.to_addrs == ["counterparty@example.net"]
        assert draft.subject == "Re: Please review the attached NDA"
        assert draft.attachment_filenames == ["Mutual-NDA.docx"]
        assert draft.provider_message_id.startswith("draft:")


async def test_draft_reply_refuses_a_file_outside_this_matter(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=uuid.uuid4(),
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="See attached.",
            attachment_file_ids=[str(uuid.uuid4())],
        )
        await db.commit()
    assert "not documents in this matter" in out
    async with commit_factory() as db:
        count = (
            await db.execute(
                select(IntakeMessage).where(
                    IntakeMessage.thread_id == seeded.thread_id, IntakeMessage.direction == "out"
                )
            )
        ).scalars()
        assert list(count) == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"to": [], "subject": "s", "body": "b"},
        {"to": ["a@b.c"], "subject": "", "body": "b"},
        {"to": ["a@b.c"], "subject": "s", "body": ""},
        {"to": ["a@b.c"], "subject": "s" * 999, "body": "b"},
        {"to": ["a@b.c"] * 21, "subject": "s", "body": "b"},
        {"to": ["a@b.c"], "subject": "s", "body": "b\x00d"},
    ],
)
async def test_invalid_drafts_are_rejected_and_write_nothing(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake, kwargs: dict[str, str]
) -> None:
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db, _binding(seeded), run_id=uuid.uuid4(), attachment_file_ids=[], **kwargs
        )
        await db.commit()
    assert out.startswith("Rejected")
    async with commit_factory() as db:
        rows = (
            await db.execute(
                select(IntakeMessage).where(
                    IntakeMessage.thread_id == seeded.thread_id, IntakeMessage.direction == "out"
                )
            )
        ).scalars()
        assert list(rows) == []


# --------------------------------------------------------------------------- #
# R7 safe-fail hook
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["failed", "cancelled", "completed", "awaiting_input"])
async def test_safe_fail_parks_a_thread_that_never_concluded(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake, status: str
) -> None:
    run_id = await _make_run(commit_factory, seeded, status=status)
    assert await safe_fail_intake_thread(commit_factory, run_id) is True
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.status == "awaiting_human"
        assert thread.outcome_note == NO_OUTCOME_NOTE
        assert thread.outcome is None


async def test_safe_fail_leaves_a_concluded_thread_alone(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    async with commit_factory() as db:
        await _record_intake_outcome(
            db, _binding(seeded), outcome="dealt_with", label="spam", note="Noise."
        )
        await db.commit()
    run_id = await _make_run(commit_factory, seeded, status="completed")
    assert await safe_fail_intake_thread(commit_factory, run_id) is False
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.status == "handled"
        assert thread.outcome_note == "Noise."


async def test_safe_fail_is_a_noop_for_a_still_running_run(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    run_id = await _make_run(commit_factory, seeded, status="running")
    assert await safe_fail_intake_thread(commit_factory, run_id) is False


async def test_safe_fail_is_a_noop_for_a_non_intake_run(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert await safe_fail_intake_thread(commit_factory, uuid.uuid4()) is False


async def test_safe_fail_ignores_an_ordinary_cockpit_run_on_the_same_matter(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """S5: an intake-born matter is an ORDINARY matter the lawyer chats about. A
    settled cockpit run must never park a thread that is still being worked."""
    run_id = await _make_run(commit_factory, seeded, status="completed", is_intake_run=False)
    assert await safe_fail_intake_thread(commit_factory, run_id) is False
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.status == "processing"
        assert thread.outcome_note is None


# --------------------------------------------------------------------------- #
# B3 re-enqueue hook
# --------------------------------------------------------------------------- #


async def _add_inbound(factory: async_sessionmaker[AsyncSession], thread_id: uuid.UUID) -> str:
    provider_message_id = f"msg-{uuid.uuid4().hex[:8]}"
    async with factory() as db:
        db.add(
            IntakeMessage(
                thread_id=thread_id,
                provider_message_id=provider_message_id,
                direction="in",
                from_addr="counterparty@example.net",
                to_addrs=["legal-intake@example.com"],
                body_text="Any update?",
            )
        )
        await db.commit()
    return provider_message_id


async def test_requeue_hands_a_deferred_message_back_to_the_queue(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """B3: nothing else would ever re-enqueue a deferred follow-up — the landing
    endpoint's arq job id is keyed per MESSAGE, so it had already burned its enqueue."""
    run_id = await _make_run(commit_factory, seeded, status="completed")
    # The seeded inbound message is already claimed by the settled run.
    async with commit_factory() as db:
        message = await db.get(IntakeMessage, seeded.message_id)
        assert message is not None
        message.run_id = run_id
        await db.commit()
    pending_id = await _add_inbound(commit_factory, seeded.thread_id)

    calls: list[tuple[uuid.UUID, str]] = []

    async def fake_enqueue(thread_id: uuid.UUID, provider_message_id: str) -> bool:
        calls.append((thread_id, provider_message_id))
        return True

    assert await requeue_pending_intake_message(commit_factory, run_id, enqueue=fake_enqueue)
    assert calls == [(seeded.thread_id, pending_id)]


async def test_requeue_is_a_noop_with_nothing_pending(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    run_id = await _make_run(commit_factory, seeded, status="completed")
    async with commit_factory() as db:
        message = await db.get(IntakeMessage, seeded.message_id)
        assert message is not None
        message.run_id = run_id
        await db.commit()

    async def fail_enqueue(thread_id: uuid.UUID, provider_message_id: str) -> bool:
        raise AssertionError("must not enqueue when nothing is pending")

    assert (
        await requeue_pending_intake_message(commit_factory, run_id, enqueue=fail_enqueue) is False
    )


async def test_requeue_ignores_an_ordinary_cockpit_run(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    run_id = await _make_run(commit_factory, seeded, status="completed", is_intake_run=False)

    async def fail_enqueue(thread_id: uuid.UUID, provider_message_id: str) -> bool:
        raise AssertionError("a cockpit run is not the thread's intake run")

    assert (
        await requeue_pending_intake_message(commit_factory, run_id, enqueue=fail_enqueue) is False
    )
