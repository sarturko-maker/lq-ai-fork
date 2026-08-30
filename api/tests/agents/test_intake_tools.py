"""INTAKE-3 intake-tool tests (ADR-F086).

Drives the two intake tools through the real test DB:

* the grant set (two tools; DISJOINT from every matter + domain grant — confinement),
* ``record_intake_outcome``: the two outcomes and their thread/matter effects
  (dealt_with CLOSES the matter via archived_at; needs_human leaves it open, and
  neither ever writes ``projects.intake_state`` — that is provenance, ADR-F086 A1),
  reject-not-truncate validation, idempotent overwrite, and the guard receipt +
  audit carrying counts/IDs only — never the label or the note,
* ``draft_email_reply`` (INTAKE-4b, ADR-F087): records a ``direction='out'`` row
  and SENDS it through an injected fake bridge — the stamped subject, the
  provider id, the thread transition, and the failure semantics (one attempt, no
  retries; the reply is kept with an error CLASS and the thread goes to
  ``error``); attachments are refused before anything is written,
* the R7 safe-fail hook: a settled run whose thread never got an outcome parks the
  thread for the lawyer with the FIXED fork-authored note; a concluded thread and a
  non-intake run are untouched.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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
    _send_key,
    build_intake_tools,
    load_intake_thread_for_run,
    requeue_pending_intake_message,
    safe_fail_intake_thread,
)
from app.agents.matter_fact_tools import MATTER_FACT_TOOL_NAMES
from app.agents.matter_memory_tools import MATTER_MEMORY_TOOL_NAMES
from app.agents.matter_roster_tools import MATTER_ROSTER_TOOL_NAMES
from app.agents.tools import MATTER_TOOL_NAMES, MatterBinding
from app.clients.mail_bridge import BridgeSendError, SentReply
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


# INTAKE-5a (ADR-F086 ruling 7): a valid ``summary`` for the calls that are meant to
# succeed. Shape-checked by RecordIntakeOutcomeInput, so every write-path test has to
# carry one — that is the point: the arg is REQUIRED, there is no "outcome without an
# account of the thread".
# INTAKE-5a.1: the matter's NAME, written by the agent. Required on every call for
# the same reason the summary is — a matter still called "RE: FW: quick question" is
# a matter the lawyer cannot find.
_TITLE = "Contoso NDA — mutual, before diligence"

_SUMMARY: list[dict[str, str]] = [
    {"title": "What they want", "text": "The counterparty asks us to review their mutual NDA."},
    {"title": "Where it stands", "text": "Read and redlined; waiting on the lawyer."},
]


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
        intake_thread_id=uuid.uuid4(),
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
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        out = await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="dealt_with",
            label="marketing",
            note="Vendor marketing email; nothing needed.",
            matter_title=_TITLE,
            summary=_SUMMARY,
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
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="Redline drafted.",
            matter_title=_TITLE,
            summary=_SUMMARY,
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


# --------------------------------------------------------------------------- #
# INTAKE-5a.1 — the matter's NAME (migration 0103, projects.name_source)
# --------------------------------------------------------------------------- #


async def _set_name(
    factory: async_sessionmaker[AsyncSession],
    project_id: uuid.UUID,
    *,
    name: str,
    source: str,
    intake_state: str | None = "candidate",
) -> None:
    async with factory() as db:
        project = await db.get(Project, project_id)
        assert project is not None
        project.name = name
        project.name_source = source
        project.intake_state = intake_state
        await db.commit()


async def test_the_agent_names_the_matter_it_read(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """The eager row was named from the subject line; concluding renames it to what
    the thread turned out to be, and records that the AGENT did so."""
    await _set_name(
        commit_factory, seeded.project_id, name="RE: FW: quick question", source="subject"
    )
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="Redline drafted.",
            matter_title=_TITLE,
            summary=_SUMMARY,
        )
        await db.commit()
    async with commit_factory() as db:
        project = await db.get(Project, seeded.project_id)
        assert project is not None
        assert project.name == _TITLE
        assert project.name_source == "agent"


async def test_a_later_run_may_improve_its_own_title(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """An agent-written name is still the agent's: the thread turning out to be
    something else rewrites it."""
    await _set_name(commit_factory, seeded.project_id, name="Old reading", source="agent")
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="n",
            matter_title="Contoso hosting renewal — pricing before notice deadline",
            summary=_SUMMARY,
        )
        await db.commit()
    async with commit_factory() as db:
        project = await db.get(Project, seeded.project_id)
        assert project is not None
        assert project.name == "Contoso hosting renewal — pricing before notice deadline"
        assert project.name_source == "agent"


async def test_a_human_name_is_never_overwritten(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """ADR-F042 in its simplest form: the human writes last, permanently. The rest of
    the conclusion (outcome, label, note, summary) still lands."""
    await _set_name(commit_factory, seeded.project_id, name="Project Atlas", source="human")
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="n",
            matter_title=_TITLE,
            summary=_SUMMARY,
        )
        await db.commit()
    async with commit_factory() as db:
        project = await db.get(Project, seeded.project_id)
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert project is not None and thread is not None
        assert project.name == "Project Atlas"
        assert project.name_source == "human"
        assert thread.outcome == "needs_human"
        assert thread.summary == _SUMMARY


async def test_a_matter_not_born_from_email_is_never_renamed(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """Only an intake-BORN matter carries a subject line for a name. A thread filed
    onto the lawyer's own matter (INTAKE-5b) must never rename their file."""
    await _set_name(
        commit_factory, seeded.project_id, name="Atlas MSA", source="agent", intake_state=None
    )
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="n",
            matter_title=_TITLE,
            summary=_SUMMARY,
        )
        await db.commit()
    async with commit_factory() as db:
        project = await db.get(Project, seeded.project_id)
        assert project is not None
        assert project.name == "Atlas MSA"


@pytest.mark.parametrize(
    ("send_status", "outcome"),
    [("replied", "dealt_with"), ("replied", "needs_human"), ("error", "needs_human")],
)
async def test_outcome_never_overwrites_a_settled_send_status(
    commit_factory: async_sessionmaker[AsyncSession],
    seeded: SeededIntake,
    send_status: str,
    outcome: str,
) -> None:
    """INTAKE-4b (ADR-F087): `replied` (a letter went out) and `error` (one was
    approved and did not go) are later, stronger facts than the outcome's own
    bookkeeping — and `error` is the ONLY place a failed delivery is visible to the
    lawyer. Recording the outcome out of order must not erase either."""
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        thread.status = send_status
        await db.commit()

    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        out = await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome=outcome,
            label="NDA review",
            note="n",
            matter_title=_TITLE,
            summary=_SUMMARY,
        )
        await db.commit()

    assert send_status in out  # the tool reports the status the thread actually has
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.status == send_status
        assert thread.outcome == outcome  # the outcome itself IS recorded
        assert thread.label == "NDA review"


def _bad(**overrides: object) -> dict[str, object]:
    """A valid proposal with one field spoiled — one failure per case."""
    base: dict[str, object] = {
        "outcome": "dealt_with",
        "label": "x",
        "note": "y",
        "matter_title": _TITLE,
        "summary": _SUMMARY,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "kwargs",
    [
        _bad(outcome="filed"),
        _bad(outcome="candidate_matter"),  # retired (ADR-F086 A1)
        _bad(label=""),
        _bad(note=""),
        _bad(label="x" * 201),
        _bad(note="y" * 2001),
        _bad(label="x\x00y"),
        # INTAKE-5a (ruling 7) — the summary's own bounds.
        _bad(summary=[]),  # zero bullets is not an account of anything
        _bad(summary=[{"title": "t", "text": "x"}] * 6),  # more than five
        _bad(summary=[{"title": "t" * 41, "text": "x"}]),  # title over 40
        _bad(summary=[{"title": "t", "text": "x" * 301}]),  # text over 300
        _bad(summary=[{"title": "t", "text": "line one\nline two"}]),  # control char
        _bad(summary=[{"title": "t\x1b[31m", "text": "x"}]),  # ANSI escape
        _bad(summary=[{"title": "t", "text": "x\x00y"}]),  # NUL
        # INTAKE-5a.1 — the matter title's own bounds. Single line, same control-char
        # rejection as a summary title: it renders beside the matter reference.
        _bad(matter_title=""),
        _bad(matter_title="t" * 81),
        _bad(matter_title="Contoso NDA\nsecond line"),
        _bad(matter_title="Contoso\u2028NDA"),
        _bad(matter_title="Contoso\x00NDA"),
        _bad(summary=[{"title": "", "text": "x"}]),  # empty title
        _bad(summary=[{"title": "t"}]),  # missing text
        _bad(summary=[{"title": "t", "text": "x", "extra": "z"}]),  # extra="forbid"
        _bad(summary=["not an object"]),
    ],
)
async def test_invalid_proposals_are_rejected_and_write_nothing(
    commit_factory: async_sessionmaker[AsyncSession],
    seeded: SeededIntake,
    kwargs: dict[str, object],
) -> None:
    async with commit_factory() as db:
        out = await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=uuid.uuid4(),
            intake_thread_id=seeded.thread_id,
            **kwargs,  # type: ignore[arg-type]
        )
        await db.commit()
    assert out.startswith("Rejected")
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.outcome is None
        assert thread.summary is None
        assert thread.summary_run_id is None
        assert thread.status == "processing"


async def test_summary_is_written_in_full_and_rewritten_wholesale(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """INTAKE-5a (ADR-F086 ruling 7): every call REPLACES the summary outright.

    The summary is "the thread so far", not a log. A second conclusion (a follow-up
    email, a rerun) must leave exactly the new bullets behind — a merge would produce
    an account of the thread that no run ever wrote — and must re-stamp
    ``summary_run_id`` so staleness stays computable.
    """
    first_run = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=first_run,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="Redline drafted.",
            matter_title=_TITLE,
            summary=_SUMMARY,
        )
        await db.commit()
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.summary == _SUMMARY
        assert thread.summary_run_id == first_run

    second_run = await _make_run(commit_factory, seeded)
    rewritten = [{"title": "Where it stands", "text": "They accepted the redline."}]
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=second_run,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="They came back.",
            matter_title=_TITLE,
            summary=rewritten,
        )
        await db.commit()
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        # Wholesale: exactly the new list, not the old one plus the new one.
        assert thread.summary == rewritten
        assert thread.summary_run_id == second_run


async def test_summary_is_stripped_of_surrounding_whitespace(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """``str_strip_whitespace`` applies to the bullets too — a padded title is
    stored trimmed, not stored padded and trimmed by every reader."""
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="n",
            matter_title=_TITLE,
            summary=[{"title": "  What they want  ", "text": "  A review.  "}],
        )
        await db.commit()
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.summary == [{"title": "What they want", "text": "A review."}]


async def test_safe_fail_leaves_the_previous_summary_in_place(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """INTAKE-5a: a run that settles WITHOUT concluding parks the thread but must not
    blank the last run's account of it — replacing something true-as-of-last-time
    with nothing is strictly worse. The read API flags it stale instead."""
    outcome_run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=outcome_run_id,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            label="NDA review",
            note="Redline drafted.",
            matter_title=_TITLE,
            summary=_SUMMARY,
        )
        await db.commit()
    # A LATER run on the thread settles without an outcome.
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        thread.status = "processing"
        await db.commit()
    failed_run = await _make_run(commit_factory, seeded, status="failed")
    assert await safe_fail_intake_thread(commit_factory, failed_run) is True
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.status == "awaiting_human"
        assert thread.summary == _SUMMARY
        assert thread.summary_run_id == outcome_run_id


async def test_second_call_overwrites_last_wins(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="dealt_with",
            label="spam",
            note="Noise.",
            matter_title=_TITLE,
            summary=_SUMMARY,
        )
        await db.commit()
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            outcome="needs_human",
            note="On reflection the lawyer should see this.",
            label="unclear",
            matter_title=_TITLE,
            summary=[{"title": "Where it stands", "text": "Over to the lawyer after all."}],
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
                # An id that names no thread on THIS matter: the tool re-checks the
                # composition root's id against its own binding before acting.
                run_id=uuid.uuid4(),
                intake_thread_id=uuid.uuid4(),
                outcome="dealt_with",
                label="x",
                note="y",
                matter_title=_TITLE,
                summary=_SUMMARY,
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
    tools = build_intake_tools(
        commit_factory,
        run_id=run_id,
        binding=_binding(seeded),
        intake_thread_id=seeded.thread_id,
    )
    record = next(t for t in tools if t.__name__ == "record_intake_outcome")
    secret_note = "the counterparty offered a side letter nobody should see in an audit row"
    out = await record("needs_human", "NDA review", secret_note, _SUMMARY)
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


class _FakeBridge:
    """The mail-bridge send seam (ADR-F087) — records calls, never a network."""

    def __init__(self, *, error: str | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._error = error

    async def send_reply(
        self,
        *,
        reply_to_provider_message_id: str,
        idempotency_key: str,
        text: str,
        reply_to_tag: str | None = None,
    ) -> SentReply:
        self.calls.append(
            {
                "reply_to_provider_message_id": reply_to_provider_message_id,
                "idempotency_key": idempotency_key,
                "text": text,
                "reply_to_tag": reply_to_tag,
            }
        )
        if self._error is not None:
            raise BridgeSendError(self._error)
        return SentReply(
            provider_message_id="<reply-1@email.amazonses.com>",
            provider_thread_id="thr-provider",
        )


async def _outbound_rows(
    factory: async_sessionmaker[AsyncSession], thread_id: uuid.UUID
) -> list[IntakeMessage]:
    async with factory() as db:
        return list(
            (
                await db.execute(
                    select(IntakeMessage).where(
                        IntakeMessage.thread_id == thread_id, IntakeMessage.direction == "out"
                    )
                )
            )
            .scalars()
            .all()
        )


async def _set_reference(
    factory: async_sessionmaker[AsyncSession], project_id: uuid.UUID, reference: str
) -> None:
    async with factory() as db:
        project = await db.get(Project, project_id)
        assert project is not None
        project.reference = reference
        await db.commit()


async def test_approved_reply_is_stamped_sent_and_recorded(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """ADR-F087: the tool body runs only after a human approved it, and that IS
    the send — one bridge call, the provider id persisted (layer 2's anchor),
    the subject stamped with the reference, the thread ``replied``."""
    run_id = await _make_run(commit_factory, seeded)
    await _set_reference(commit_factory, seeded.project_id, "NWT-COM-0011")
    bridge = _FakeBridge()
    call_id = "call_approved_ask"
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            to=["counterparty@example.net"],
            subject="Re: Please review the attached NDA",
            body="Thanks — we have it and will come back to you this week.",
            attachment_file_ids=[],
            tool_call_id=call_id,
            bridge=bridge,
        )
        await db.commit()

    assert out.startswith("Sent.")
    assert "NWT-COM-0011" in out
    rows = await _outbound_rows(commit_factory, seeded.thread_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.run_id == run_id
    assert row.to_addrs == ["counterparty@example.net"]
    # The reference is stamped exactly once, and the recorded id is the
    # PROVIDER's — the one an inbound References header will name (ADR-F088).
    assert row.subject == "Re: Please review the attached NDA [NWT-COM-0011]"
    assert row.provider_message_id == "<reply-1@email.amazonses.com>"
    assert row.send_error is None
    assert len(bridge.calls) == 1
    call = bridge.calls[0]
    # Keyed on the thread's newest INBOUND message; the idempotency key is the
    # per-ASK key (ADR-F087 — deliberately NOT this row's id, which is minted fresh
    # on every execution); the bridge gets the matter TAG, never an address.
    assert call["idempotency_key"] == _send_key(seeded.thread_id, call_id)
    assert call["idempotency_key"] != str(row.id)
    assert call["reply_to_tag"] == "NWT-COM-0011"
    assert call["text"] == "Thanks — we have it and will come back to you this week."
    async with commit_factory() as db:
        inbound = await db.get(IntakeMessage, seeded.message_id)
        assert inbound is not None
        assert call["reply_to_provider_message_id"] == inbound.provider_message_id
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.status == "replied"


async def test_a_matter_without_a_reference_still_sends_unstamped(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """A missing reference is cosmetic — it must not block the send."""
    bridge = _FakeBridge()
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=await _make_run(commit_factory, seeded),
            intake_thread_id=seeded.thread_id,
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
            tool_call_id=uuid.uuid4().hex,
            bridge=bridge,
        )
        await db.commit()
    assert out.startswith("Sent.")
    assert bridge.calls[0]["reply_to_tag"] is None
    rows = await _outbound_rows(commit_factory, seeded.thread_id)
    assert rows[0].subject == "Re: NDA"


@pytest.mark.parametrize("reason", ["http_500", "timeout", "transport", "duplicate", "unexpected"])
async def test_a_failed_send_keeps_the_reply_and_errors_the_thread(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake, reason: str
) -> None:
    """No retries (ADR-F087). The approved text is kept, the failure is recorded
    as a CLASS only, the thread goes to ``error``, and the tool tells the model
    to conclude needs_human."""
    bridge = _FakeBridge(error=reason)
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=await _make_run(commit_factory, seeded),
            intake_thread_id=seeded.thread_id,
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
            tool_call_id=uuid.uuid4().hex,
            bridge=bridge,
        )
        await db.commit()

    assert out.startswith("NOT DELIVERED")
    assert "needs_human" in out
    assert len(bridge.calls) == 1  # exactly one attempt, ever
    rows = await _outbound_rows(commit_factory, seeded.thread_id)
    assert len(rows) == 1
    assert rows[0].send_error == reason
    assert rows[0].body_text == "Noted."
    assert rows[0].provider_message_id.startswith("draft:")
    async with commit_factory() as db:
        thread = await db.get(IntakeThread, seeded.thread_id)
        assert thread is not None
        assert thread.status == "error"


async def test_no_bridge_configured_is_an_honest_failure(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=await _make_run(commit_factory, seeded),
            intake_thread_id=seeded.thread_id,
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
            tool_call_id=uuid.uuid4().hex,
            bridge=None,
        )
        await db.commit()
    assert out.startswith("NOT DELIVERED")
    rows = await _outbound_rows(commit_factory, seeded.thread_id)
    assert rows[0].send_error == "not_configured"


async def test_a_thread_with_no_inbound_message_is_never_sent_into(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """The bridge is reply-only: with nothing to reply TO there is no send, and
    we must not fall back to anything that could originate a thread."""
    async with commit_factory() as db:
        await db.execute(delete(IntakeMessage).where(IntakeMessage.id == seeded.message_id))
        await db.commit()
    bridge = _FakeBridge()
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=await _make_run(commit_factory, seeded),
            intake_thread_id=seeded.thread_id,
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
            tool_call_id=uuid.uuid4().hex,
            bridge=bridge,
        )
        await db.commit()
    assert out.startswith("NOT DELIVERED")
    assert bridge.calls == []
    rows = await _outbound_rows(commit_factory, seeded.thread_id)
    assert rows[0].send_error == "no_inbound_message"


async def test_attachments_are_refused_before_anything_is_written(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """INTAKE-4b sends text only; recording "1 attachment" on a reply that goes
    out without it would make the row lie about what the counterparty got."""
    bridge = _FakeBridge()
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=await _make_run(commit_factory, seeded),
            intake_thread_id=seeded.thread_id,
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="See attached.",
            attachment_file_ids=[str(seeded.file_id)],
            tool_call_id=uuid.uuid4().hex,
            bridge=bridge,
        )
        await db.commit()
    assert "Attachments cannot be delivered yet" in out
    assert bridge.calls == []
    assert await _outbound_rows(commit_factory, seeded.thread_id) == []


async def test_a_non_intake_matter_sends_nothing(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    bridge = _FakeBridge()
    binding = MatterBinding(
        project_id=uuid.uuid4(),
        user_id=seeded.user_id,
        name="Not an intake matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=None,
    )
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            binding,
            run_id=uuid.uuid4(),
            intake_thread_id=seeded.thread_id,
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
            tool_call_id=uuid.uuid4().hex,
            bridge=bridge,
        )
        await db.commit()
    assert "not an intake thread" in out
    assert bridge.calls == []


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
            db,
            _binding(seeded),
            run_id=uuid.uuid4(),
            intake_thread_id=seeded.thread_id,
            attachment_file_ids=[],
            tool_call_id=uuid.uuid4().hex,
            **kwargs,
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
# Double-send safety (ADR-F087) — the re-execution hazard, not a retry
# --------------------------------------------------------------------------- #


def test_draft_email_reply_takes_an_injected_tool_call_id() -> None:
    """The whole double-send fix rests on this wiring: langchain injects the
    CHECKPOINTED tool-call id, and the model can neither see it in the schema nor
    set it. If a langchain/deepagents bump ever drops the injection, the key would
    silently become "" for every ask — so pin the contract here."""
    from langchain_core.tools import StructuredTool

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
        intake_thread_id=uuid.uuid4(),
    )
    draft = next(t for t in tools if t.__name__ == "draft_email_reply")
    schema = StructuredTool.from_function(
        coroutine=draft, name="draft_email_reply", description="d"
    ).args
    assert "tool_call_id" not in schema
    assert {"to", "subject", "body", "attachment_file_ids"} <= set(schema)


async def test_re_executing_the_same_ask_sends_once_and_writes_one_row(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """A worker killed between a successful send and the checkpoint write settles
    the run ``failed``; a failed successor does NOT supersede the pause, so the card
    stays live and Approve can run this body again on the SAME checkpointed call.
    The counterparty must still receive exactly one letter."""
    run_id = await _make_run(commit_factory, seeded)
    bridge = _FakeBridge()
    call_id = "call_the_same_checkpointed_ask"

    async def approve() -> str:
        async with commit_factory() as db:
            out = await _draft_email_reply(
                db,
                _binding(seeded),
                run_id=run_id,
                intake_thread_id=seeded.thread_id,
                to=["counterparty@example.net"],
                subject="Re: NDA",
                body="Thanks — we have it.",
                attachment_file_ids=[],
                tool_call_id=call_id,
                bridge=bridge,
            )
            await db.commit()
            return out

    first, second = await approve(), await approve()

    assert first.startswith("Sent.")
    assert "already been sent" in second
    assert len(bridge.calls) == 1  # the bridge is not touched a second time
    rows = await _outbound_rows(commit_factory, seeded.thread_id)
    assert len(rows) == 1  # and no twin row was inserted
    assert rows[0].provider_message_id == "<reply-1@email.amazonses.com>"


async def test_the_idempotency_key_is_the_ask_not_the_row(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """The key must be derived from the CHECKPOINTED tool-call id: a freshly minted
    row id would present a NEW key on a second attempt and the bridge would accept
    it. Two executions of the same ask ⇒ the same key; a different ask ⇒ a different
    one (and both are within the bridge's 64-char cap)."""
    bridge = _FakeBridge(error="transport")  # fail, so the row stays undelivered

    async def approve(call_id: str) -> None:
        async with commit_factory() as db:
            await _draft_email_reply(
                db,
                _binding(seeded),
                run_id=await _make_run(commit_factory, seeded),
                intake_thread_id=seeded.thread_id,
                to=["counterparty@example.net"],
                subject="Re: NDA",
                body="Noted.",
                attachment_file_ids=[],
                tool_call_id=call_id,
                bridge=bridge,
            )
            await db.commit()

    await approve("call_a")
    await approve("call_a")
    await approve("call_b")

    keys = [c["idempotency_key"] for c in bridge.calls]
    assert keys[0] == keys[1] != keys[2]
    assert all(isinstance(k, str) and 1 <= len(k) <= 64 for k in keys)
    # The failed attempt reused its own row; only the second ask made a new one.
    rows = await _outbound_rows(commit_factory, seeded.thread_id)
    assert len(rows) == 2
    assert {r.send_error for r in rows} == {"transport"}


async def test_reply_targets_the_newest_inbound_the_agent_actually_read(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """A pause can last days. A follow-up that lands meanwhile is unread text whose
    sender the lawyer never approved replying to — and the bridge derives the
    recipient from whichever message we key the reply on."""
    run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        processed = await db.get(IntakeMessage, seeded.message_id)
        assert processed is not None
        processed.run_id = run_id
        db.add(
            IntakeMessage(
                thread_id=seeded.thread_id,
                provider_message_id="msg-arrived-during-the-pause",
                direction="in",
                from_addr="a-stranger@example.org",
                to_addrs=["legal-intake@example.com"],
                subject="Re: NDA",
                body_text="me too",
                provider_timestamp=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
            )
        )
        await db.commit()

    bridge = _FakeBridge()
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=run_id,
            intake_thread_id=seeded.thread_id,
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
            tool_call_id=uuid.uuid4().hex,
            bridge=bridge,
        )
        await db.commit()

    assert out.startswith("Sent.")
    async with commit_factory() as db:
        read = await db.get(IntakeMessage, seeded.message_id)
        assert read is not None
        assert bridge.calls[0]["reply_to_provider_message_id"] == read.provider_message_id


async def test_a_delivered_reply_blocks_a_second_one_until_new_mail_arrives(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """The DB-side guard, independent of the tool-call id: a reply already out since
    the newest inbound short-circuits before the bridge is touched."""
    bridge = _FakeBridge()

    async def approve() -> str:
        async with commit_factory() as db:
            out = await _draft_email_reply(
                db,
                _binding(seeded),
                run_id=await _make_run(commit_factory, seeded),
                intake_thread_id=seeded.thread_id,
                to=["counterparty@example.net"],
                subject="Re: NDA",
                body="Noted.",
                attachment_file_ids=[],
                tool_call_id=uuid.uuid4().hex,  # a DIFFERENT ask each time
                bridge=bridge,
            )
            await db.commit()
            return out

    assert (await approve()).startswith("Sent.")
    assert "already been sent" in await approve()
    assert len(bridge.calls) == 1


# --------------------------------------------------------------------------- #
# One conversation, MANY intake threads (ADR-F088 layer 2/3) — the binding
# --------------------------------------------------------------------------- #


@dataclass
class SeededConversation:
    """The live shape that crashed the first approval: three intake threads on ONE
    agent conversation — the one being worked plus two attached mid-run."""

    seeded: SeededIntake
    agent_thread_id: uuid.UUID
    run_id: uuid.UUID
    worked_thread_id: uuid.UUID
    pending_a_id: uuid.UUID
    pending_b_id: uuid.UUID


async def _seed_conversation(
    factory: async_sessionmaker[AsyncSession], row: SeededIntake
) -> SeededConversation:
    """The worked thread (processing, its inbound stamped with the run) + two siblings
    the resolver attached later, both still `received` with an unclaimed inbound."""
    run_id = await _make_run(factory, row)
    async with factory() as db:
        worked = await db.get(IntakeThread, row.thread_id)
        assert worked is not None
        agent_thread_id = worked.agent_thread_id
        assert agent_thread_id is not None
        worked.status = "processing"
        processed = await db.get(IntakeMessage, row.message_id)
        assert processed is not None
        processed.run_id = run_id  # the worker's binding, at run start

        siblings: list[uuid.UUID] = []
        # Explicit, distinct created_at: "the OLDEST pending inbound" is the contract,
        # and two rows written in one transaction share now() to the microsecond.
        for tag, landed_at in (
            ("a", datetime(2026, 8, 21, 9, 0, tzinfo=UTC)),
            ("b", datetime(2026, 8, 22, 9, 0, tzinfo=UTC)),
        ):
            sibling = IntakeThread(
                mailbox_id=row.mailbox_id,
                provider_thread_id=f"thr-{tag}-{uuid.uuid4().hex[:8]}",
                project_id=row.project_id,
                agent_thread_id=agent_thread_id,  # SAME conversation (ADR-F088)
                subject="Re: Please review the attached NDA",
                status="received",
                auth_state="pass",
                message_count=1,
            )
            db.add(sibling)
            await db.flush()
            db.add(
                IntakeMessage(
                    thread_id=sibling.id,
                    provider_message_id=f"msg-{tag}-{uuid.uuid4().hex[:8]}",
                    direction="in",
                    from_addr="counterparty@example.net",
                    to_addrs=["legal-intake@example.com"],
                    subject="Re: Please review the attached NDA",
                    body_text="a follow-up that landed while the run was in flight",
                    provider_timestamp=landed_at,
                    created_at=landed_at,
                )
            )
            siblings.append(sibling.id)
        await db.commit()
    return SeededConversation(
        seeded=row,
        agent_thread_id=agent_thread_id,
        run_id=run_id,
        worked_thread_id=row.thread_id,
        pending_a_id=siblings[0],
        pending_b_id=siblings[1],
    )


@pytest_asyncio.fixture
async def conversation(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> SeededConversation:
    return await _seed_conversation(commit_factory, seeded)


async def test_binding_picks_the_thread_this_run_was_started_for(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """Three threads share one agent conversation. The old query raised
    MultipleResultsFound here (the live INTAKE-4b approval died on exactly this);
    a LIMIT 1 would have picked the oldest row and been right by luck only."""
    async with commit_factory() as db:
        bound = await load_intake_thread_for_run(
            db,
            project_id=conversation.seeded.project_id,
            agent_thread_id=conversation.agent_thread_id,
            run_id=conversation.run_id,
        )
        assert bound is not None
        assert bound.id == conversation.worked_thread_id


async def test_binding_follows_the_conversation_lineage_for_a_resumed_run(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """A resume is a NEW agent_runs row with no messages of its own (HITL-2). It must
    still bind to the thread the paused run was working."""
    # A resume run is a NEW agent_runs row on the SAME conversation (HITL-2), so it
    # must be created on the existing agent thread — not a fresh one.
    async with commit_factory() as db:
        paused = await db.get(AgentRun, conversation.run_id)
        assert paused is not None
        paused.status = "awaiting_input"  # the pause the human is resolving
        resume = AgentRun(
            user_id=conversation.seeded.user_id,
            thread_id=conversation.agent_thread_id,
            project_id=conversation.seeded.project_id,
            status="running",
            prompt="[resume: approve]",
            max_steps=8,
        )
        db.add(resume)
        await db.commit()
        resume_run_id = resume.id
    assert resume_run_id != conversation.run_id
    async with commit_factory() as db:
        bound = await load_intake_thread_for_run(
            db,
            project_id=conversation.seeded.project_id,
            agent_thread_id=conversation.agent_thread_id,
            run_id=resume_run_id,
        )
        assert bound is not None
        assert bound.id == conversation.worked_thread_id


async def _make_resume(
    factory: async_sessionmaker[AsyncSession],
    conversation: SeededConversation,
    *,
    parent_run_id: uuid.UUID | None,
) -> uuid.UUID:
    """A resume run on the SAME conversation: no messages of its own, optionally
    carrying the parent link the resume endpoint now writes (fix D)."""
    async with factory() as db:
        resume = AgentRun(
            user_id=conversation.seeded.user_id,
            thread_id=conversation.agent_thread_id,
            project_id=conversation.seeded.project_id,
            status="running",
            prompt="[resume: approve]",
            max_steps=8,
            resumed_from_run_id=parent_run_id,
        )
        db.add(resume)
        await db.commit()
        return resume.id


async def _sibling_replied_more_recently(
    factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """The live shape (fix D): a SIBLING thread's inbound is the newest message on the
    conversation and was processed by its own run — so the layer-2 heuristic names
    that sibling, not the thread the paused run was working."""
    async with factory() as db:
        sibling_run = AgentRun(
            user_id=conversation.seeded.user_id,
            thread_id=conversation.agent_thread_id,
            project_id=conversation.seeded.project_id,
            status="completed",
            prompt="intake",
            max_steps=8,
        )
        db.add(sibling_run)
        await db.flush()
        newest = (
            (
                await db.execute(
                    select(IntakeMessage).where(
                        IntakeMessage.thread_id == conversation.pending_a_id
                    )
                )
            )
            .scalars()
            .first()
        )
        assert newest is not None
        newest.run_id = sibling_run.id
        newest.created_at = datetime.now(tz=UTC) + timedelta(hours=1)
        await db.commit()


async def test_a_resume_binds_to_the_thread_its_parent_was_working(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """P1, reproduced from dev (fix D): the sibling thread carries the conversation's
    NEWEST processed inbound, so the legacy lineage heuristic names it — and the
    approved reply was then refused against that sibling's delivered row. With the
    parent link the resume binds to the thread its paused run actually worked."""
    await _sibling_replied_more_recently(commit_factory, conversation)
    resume_run_id = await _make_resume(
        commit_factory, conversation, parent_run_id=conversation.run_id
    )
    async with commit_factory() as db:
        bound = await load_intake_thread_for_run(
            db,
            project_id=conversation.seeded.project_id,
            agent_thread_id=conversation.agent_thread_id,
            run_id=resume_run_id,
        )
        assert bound is not None
        assert bound.id == conversation.worked_thread_id
        assert bound.id != conversation.pending_a_id


async def test_a_resume_of_a_resume_follows_the_whole_chain(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """Send-back → redraft → approve builds a chain of resumes, none of which stamps a
    message. The walk climbs it to the run that did."""
    await _sibling_replied_more_recently(commit_factory, conversation)
    first = await _make_resume(commit_factory, conversation, parent_run_id=conversation.run_id)
    second = await _make_resume(commit_factory, conversation, parent_run_id=first)
    async with commit_factory() as db:
        bound = await load_intake_thread_for_run(
            db,
            project_id=conversation.seeded.project_id,
            agent_thread_id=conversation.agent_thread_id,
            run_id=second,
        )
        assert bound is not None
        assert bound.id == conversation.worked_thread_id


async def test_a_historic_resume_still_uses_the_legacy_lineage_heuristic(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """No backfill: a resume written before migration 0103 carries no parent link and
    falls through to layer 2 exactly as it always did — which is the behaviour this
    test pins, bug and all, so a future change to it is deliberate."""
    await _sibling_replied_more_recently(commit_factory, conversation)
    resume_run_id = await _make_resume(commit_factory, conversation, parent_run_id=None)
    async with commit_factory() as db:
        bound = await load_intake_thread_for_run(
            db,
            project_id=conversation.seeded.project_id,
            agent_thread_id=conversation.agent_thread_id,
            run_id=resume_run_id,
        )
        assert bound is not None
        assert bound.id == conversation.pending_a_id


async def test_binding_falls_back_to_the_single_working_thread(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """Nothing processed yet: the two `received` siblings are not candidates, so the
    one thread actually being worked is unambiguous."""
    async with commit_factory() as db:
        processed = await db.get(IntakeMessage, conversation.seeded.message_id)
        assert processed is not None
        processed.run_id = None
        await db.commit()
    async with commit_factory() as db:
        bound = await load_intake_thread_for_run(
            db,
            project_id=conversation.seeded.project_id,
            agent_thread_id=conversation.agent_thread_id,
            run_id=conversation.run_id,
        )
        assert bound is not None
        assert bound.id == conversation.worked_thread_id


async def test_binding_fails_closed_when_it_is_genuinely_ambiguous(
    commit_factory: async_sessionmaker[AsyncSession],
    conversation: SeededConversation,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two working threads and nothing processed is a BUG, not a state to guess
    through: log it with counts/ids and grant nothing (no tools, no doctrine, no
    thread flipped) — never MultipleResultsFound, never the wrong thread."""
    async with commit_factory() as db:
        processed = await db.get(IntakeMessage, conversation.seeded.message_id)
        assert processed is not None
        processed.run_id = None
        sibling = await db.get(IntakeThread, conversation.pending_a_id)
        assert sibling is not None
        sibling.status = "processing"
        await db.commit()
    with caplog.at_level(logging.ERROR, logger="app.agents.intake_tools"):
        async with commit_factory() as db:
            bound = await load_intake_thread_for_run(
                db,
                project_id=conversation.seeded.project_id,
                agent_thread_id=conversation.agent_thread_id,
                run_id=conversation.run_id,
            )
    assert bound is None
    assert any(r.__dict__.get("event") == "intake_thread_binding_ambiguous" for r in caplog.records)


async def test_requeue_hands_back_the_oldest_pending_sibling(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """The requeue-on-settle contract is per CONVERSATION now: a mail that landed
    mid-run is on a sibling thread, and settling this run is what frees it."""
    async with commit_factory() as db:
        run = await db.get(AgentRun, conversation.run_id)
        assert run is not None
        run.status = "completed"
        await db.commit()

    handed: list[tuple[uuid.UUID, str]] = []

    async def fake_enqueue(thread_id: uuid.UUID, provider_message_id: str) -> bool:
        handed.append((thread_id, provider_message_id))
        return True

    assert await requeue_pending_intake_message(
        commit_factory, conversation.run_id, enqueue=fake_enqueue
    )
    assert len(handed) == 1
    # The OLDEST pending inbound across the siblings — and its OWN thread id, which
    # is what the worker keys on (not the thread this run was working).
    assert handed[0][0] == conversation.pending_a_id
    async with commit_factory() as db:
        message = (
            await db.execute(
                select(IntakeMessage).where(IntakeMessage.thread_id == conversation.pending_a_id)
            )
        ).scalar_one()
        assert handed[0][1] == message.provider_message_id


async def test_safe_fail_parks_only_the_thread_the_run_was_working(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """The pending siblings have not been looked at by anyone — parking them would
    tell the lawyer they are waiting on a decision that was never asked for."""
    async with commit_factory() as db:
        run = await db.get(AgentRun, conversation.run_id)
        assert run is not None
        run.status = "failed"
        await db.commit()

    assert await safe_fail_intake_thread(commit_factory, conversation.run_id) is True
    async with commit_factory() as db:
        worked = await db.get(IntakeThread, conversation.worked_thread_id)
        assert worked is not None
        assert worked.status == "awaiting_human"
        assert worked.outcome_note == NO_OUTCOME_NOTE
        for sibling_id in (conversation.pending_a_id, conversation.pending_b_id):
            sibling = await db.get(IntakeThread, sibling_id)
            assert sibling is not None
            assert sibling.status == "received"
            assert sibling.outcome_note is None


async def test_the_tools_act_on_the_bound_thread_not_the_oldest_on_the_matter(
    commit_factory: async_sessionmaker[AsyncSession], conversation: SeededConversation
) -> None:
    """The send path must scope its "newest inbound processed" lookup and its
    delivered-row guard to the BOUND thread. Bind to a sibling and the reply must
    key on THAT thread's message, not the matter's oldest."""
    bridge = _FakeBridge()
    async with commit_factory() as db:
        sibling_message = (
            await db.execute(
                select(IntakeMessage).where(IntakeMessage.thread_id == conversation.pending_a_id)
            )
        ).scalar_one()
        sibling_message.run_id = conversation.run_id
        await db.commit()
        expected = sibling_message.provider_message_id

    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(conversation.seeded),
            run_id=conversation.run_id,
            intake_thread_id=conversation.pending_a_id,
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
            tool_call_id=uuid.uuid4().hex,
            bridge=bridge,
        )
        await db.commit()

    assert out.startswith("Sent.")
    assert bridge.calls[0]["reply_to_provider_message_id"] == expected
    rows = await _outbound_rows(commit_factory, conversation.pending_a_id)
    assert len(rows) == 1
    # The thread the run was NOT bound to is untouched.
    assert await _outbound_rows(commit_factory, conversation.worked_thread_id) == []
    async with commit_factory() as db:
        worked = await db.get(IntakeThread, conversation.worked_thread_id)
        assert worked is not None
        assert worked.status == "processing"


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
    outcome_run_id = await _make_run(commit_factory, seeded)
    async with commit_factory() as db:
        await _record_intake_outcome(
            db,
            _binding(seeded),
            run_id=outcome_run_id,
            intake_thread_id=seeded.thread_id,
            outcome="dealt_with",
            label="spam",
            note="Noise.",
            matter_title=_TITLE,
            summary=_SUMMARY,
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


async def test_requeue_reports_a_refused_enqueue_as_a_failure(
    commit_factory: async_sessionmaker[AsyncSession], seeded: SeededIntake
) -> None:
    """ADR-F087: a refused enqueue means the message is STILL waiting and nothing
    will pick it up — the landing endpoint already burned its own enqueue and this
    hook is the only other producer. It must read as False, not as a success with a
    `queued: false` field buried in an info line."""
    run_id = await _make_run(commit_factory, seeded, status="completed")
    async with commit_factory() as db:
        db.add(
            IntakeMessage(
                thread_id=seeded.thread_id,
                provider_message_id=f"msg-{uuid.uuid4().hex[:8]}",
                direction="in",
                from_addr="counterparty@example.net",
                to_addrs=["legal-intake@example.com"],
                body_text="Still waiting.",
            )
        )
        await db.commit()

    async def refused(thread_id: uuid.UUID, provider_message_id: str) -> bool:
        return False

    assert await requeue_pending_intake_message(commit_factory, run_id, enqueue=refused) is False
    # Nothing was consumed: every inbound is still unclaimed and re-enqueueable.
    async with commit_factory() as db:
        inbound = (
            (
                await db.execute(
                    select(IntakeMessage).where(
                        IntakeMessage.thread_id == seeded.thread_id,
                        IntakeMessage.direction == "in",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert inbound and all(m.run_id is None for m in inbound)


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


def test_summary_is_required_at_the_tool_schema() -> None:
    """INTAKE-5a (ruling 7): a proposal without ``summary`` never reaches the writer —
    the tool's own input schema refuses it, which is the boundary the model hits."""
    from pydantic import ValidationError

    from app.schemas.intake import RecordIntakeOutcomeInput

    with pytest.raises(ValidationError):
        RecordIntakeOutcomeInput(outcome="dealt_with", label="x", note="y")  # type: ignore[call-arg]
