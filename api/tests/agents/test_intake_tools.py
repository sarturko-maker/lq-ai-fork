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
    async with commit_factory() as db:
        out = await _draft_email_reply(
            db,
            _binding(seeded),
            run_id=run_id,
            to=["counterparty@example.net"],
            subject="Re: Please review the attached NDA",
            body="Thanks — we have it and will come back to you this week.",
            attachment_file_ids=[],
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
    # Keyed on the thread's newest INBOUND message; idempotency key = the row id;
    # the bridge gets the TAG, never an address.
    assert call["idempotency_key"] == str(row.id)
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
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
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
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
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
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
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
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
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
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="See attached.",
            attachment_file_ids=[str(seeded.file_id)],
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
            to=["counterparty@example.net"],
            subject="Re: NDA",
            body="Noted.",
            attachment_file_ids=[],
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
