"""Email legal-intake ORM models — INTAKE-1 (ADR-F086).

Three tables, additive-only, backing the "agent-monitored legal-intake inbox"
milestone (`docs/fork/plans/INTAKE-INBOX-plan.md`):

* :class:`IntakeMailbox` — the admin-owned binding of one mailbox (provider +
  inbox id) to one practice area and one owner user (the queue owner — owns
  every candidate matter/run and approves in v1). Soft-deleted
  ``slack_workspaces``-style so re-binding revives history rather than
  losing it. No policy JSONB, no triage model — doctrine lives in the
  intake skill (INTAKE-3), not in this table (Ruling 1/5 of the plan).
* :class:`IntakeThread` — the inbox backbone: one row per provider email
  thread, carrying the candidate-project binding, the agent-thread binding
  (once INTAKE-3 starts running the agent), a free-form agent-chosen
  ``label`` (display/grouping only — nothing branches on it), and the
  lifecycle ``status``.
* :class:`IntakeMessage` — idempotency + provenance for one inbound/outbound
  message on a thread. ``UNIQUE(thread_id, provider_message_id)`` is the
  idempotency anchor: duplicate webhook/websocket delivery is a no-op.

See migrations ``0098_intake_substrate.py`` (the three tables) and
``0099_intake_outcome_and_triage_skill.py`` (INTAKE-3: the thread outcome +
the inbound message's own content) and ``0102_intake_inbox_surface.py``
(INTAKE-5a: the thread summary + the two read indexes) for the DDL these
mirror.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# CHECK value sets — the SQL mirror of the migration's literal IN-lists. Keep
# the two in sync (same convention as MatterParticipant's _SIDES/_TRUST).
_THREAD_STATUSES = ("received", "processing", "awaiting_human", "replied", "handled", "error")
_AUTH_STATES = ("pass", "fail", "unknown")
_MESSAGE_DIRECTIONS = ("in", "out")
# INTAKE-3 (migration 0099): the closed outcome vocabulary the agent's
# ``record_intake_outcome`` tool writes. Nothing else may write this column.
# TWO values (ADR-F086 Amendment A1): every intake thread IS a matter, so there is
# no promotion step — ``dealt_with`` closes the matter, ``needs_human`` leaves it
# open for the lawyer.
_THREAD_OUTCOMES = ("dealt_with", "needs_human")


def _in_set(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class IntakeMailbox(Base):
    """One admin-bound intake mailbox (ADR-F086).

    ``provider`` + ``inbox_id`` identify the mailbox at the provider (v1:
    AgentMail); uniqueness is enforced on LIVE rows only (partial index,
    migration-side) so a soft-deleted binding can be re-created cleanly.
    ``owner_user_id`` is the queue owner — every candidate matter and run
    this mailbox produces is owned by them, and they give every approval
    (the plan's maintainer ruling: "there is no Team who can own intake
    with agents").
    """

    __tablename__ = "intake_mailboxes"
    __table_args__ = (
        CheckConstraint(
            "char_length(provider) BETWEEN 1 AND 50", name="chk_intake_mailboxes_provider_len"
        ),
        CheckConstraint(
            "char_length(inbox_id) BETWEEN 1 AND 500", name="chk_intake_mailboxes_inbox_id_len"
        ),
        CheckConstraint(
            "char_length(address) BETWEEN 1 AND 320", name="chk_intake_mailboxes_address_len"
        ),
        CheckConstraint(
            "max_steps IS NULL OR (max_steps BETWEEN 1 AND 600)",
            name="chk_intake_mailboxes_max_steps_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'agentmail'"))
    inbox_id: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    practice_area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "practice_areas.id", ondelete="RESTRICT", name="fk_intake_mailboxes_practice_area_id"
        ),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_intake_mailboxes_owner_user_id"),
        nullable=False,
    )
    # Lean-budget-by-default posture (Ruling 1: cost control is "run
    # briefly", never "don't run"). NULL = fall back to the platform default
    # at run-composition time (INTAKE-3); no CHECK here — the same
    # BudgetProfile vocabulary as `agent_runs.budget_profile` is validated
    # at the Pydantic boundary (schemas.intake_mailboxes), not the DB.
    default_budget_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<IntakeMailbox id={self.id} provider={self.provider!r} "
            f"inbox_id={self.inbox_id!r} active={self.active}>"
        )


class IntakeThread(Base):
    """One provider email thread — the inbox backbone (ADR-F086).

    ``project_id`` is the candidate matter this thread's documents and work
    product land in — created EAGERLY at first ingest (runs and files are
    project-scoped substrate, not policy) and ``SET NULL`` if the project is
    ever hard-deleted. ``agent_thread_id`` is reused across follow-up
    messages so the SAME agent conversation continues (INTAKE-3); NULL until
    the first agent run starts. ``label`` is a short free-form tag the agent
    chooses ("NDA review", "renewal notice"...) — display/grouping only,
    nothing branches on it (Ruling 5: no fixed taxonomy).
    """

    __tablename__ = "intake_threads"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_id", "provider_thread_id", name="uq_intake_threads_mailbox_provider_thread"
        ),
        CheckConstraint(_in_set("status", _THREAD_STATUSES), name="chk_intake_threads_status"),
        CheckConstraint(_in_set("auth_state", _AUTH_STATES), name="chk_intake_threads_auth_state"),
        CheckConstraint("char_length(subject) <= 998", name="chk_intake_threads_subject_len"),
        CheckConstraint(
            "label IS NULL OR char_length(label) BETWEEN 1 AND 200",
            name="chk_intake_threads_label_len",
        ),
        CheckConstraint(
            f"outcome IS NULL OR {_in_set('outcome', _THREAD_OUTCOMES)}",
            name="chk_intake_threads_outcome",
        ),
        # INTAKE-4a (ADR-F088): mirrors app.matters.reference.REFERENCE_PATTERN.
        CheckConstraint(
            "claimed_reference IS NULL OR (char_length(claimed_reference) <= 40 "
            "AND claimed_reference ~ '^[A-Z0-9]{2,6}-[A-Z0-9]{2,6}-[0-9]{4,}$')",
            name="chk_intake_threads_claimed_reference",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_mailboxes.id", ondelete="CASCADE", name="fk_intake_threads_mailbox_id"),
        nullable=False,
    )
    provider_thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL", name="fk_intake_threads_project_id"),
        nullable=True,
    )
    agent_thread_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "agent_threads.id", ondelete="SET NULL", name="fk_intake_threads_agent_thread_id"
        ),
        nullable=True,
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    # Free-form agent-chosen tag (Ruling 5) — display/grouping only.
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    # INTAKE-3 (ADR-F086, migration 0099): the run's STRUCTURAL conclusion — one of
    # _THREAD_OUTCOMES, written only by the agent's ``record_intake_outcome`` tool
    # (never free prose, never inferred from model text). NULL until a run concludes.
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # INTAKE-4a (ADR-F088, migration 0100): a matter reference an inbound sender
    # CLAIMED — in a subject tag or a plus-addressed recipient — that did NOT earn
    # an attach (the reference resolves to nothing here, or the sender is not on
    # that matter's roster). Untrusted, format-checked, never acted on by code:
    # it is rendered into the intake prompt (through the existing sanitisers) so
    # the agent can flag "someone says this belongs to X" for the lawyer. NULL
    # whenever a claim was honoured or none was made.
    claimed_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'received'"))
    last_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sender-authenticity caution (security posture #2): caps the doctrine's
    # action ladder at summarize + banners the UI when not 'pass'.
    auth_state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unknown'"))
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # INTAKE-5a (ADR-F086, migration 0102): the agent's account of THE THREAD SO FAR
    # — a JSON array of at most five ``{"title", "text"}`` objects, rewritten IN FULL
    # by every ``record_intake_outcome`` call so it always describes the whole chain
    # rather than the last message. This is what the lawyer's Inbox opens on; the raw
    # emails stay collapsed behind it (plan ruling 7). Model text about UNTRUSTED
    # mail: bounded at the Pydantic write boundary
    # (:class:`app.schemas.intake.IntakeSummaryItem` — ≤5 items, title ≤40 chars,
    # text ≤300 chars, no control characters), rendered as text and never as HTML,
    # and never written into a log line or an audit row. NULL until a run concludes.
    summary: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    # The run whose ``record_intake_outcome`` last wrote ``summary``; ``SET NULL`` on
    # run delete keeps the summary (it outlives the run record, like
    # ``files.summary_run_id``). Comparing it to the newest SETTLED run that
    # processed one of this thread's inbound messages is what makes the read API's
    # ``summary_stale`` flag computable — see ``app.api.intake_threads``.
    summary_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL", name="fk_intake_threads_summary_run_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<IntakeThread id={self.id} mailbox_id={self.mailbox_id} "
            f"status={self.status!r} messages={self.message_count}>"
        )


class IntakeMessage(Base):
    """One inbound/outbound message on an intake thread — idempotency anchor.

    ``UNIQUE(thread_id, provider_message_id)`` is what makes duplicate
    webhook/websocket delivery a no-op: the bridge (and dev websocket
    subscriber) can re-deliver the same provider message any number of
    times and only the first insert sticks.
    """

    __tablename__ = "intake_messages"
    __table_args__ = (
        UniqueConstraint(
            "thread_id", "provider_message_id", name="uq_intake_messages_thread_provider_message"
        ),
        CheckConstraint(
            _in_set("direction", _MESSAGE_DIRECTIONS), name="chk_intake_messages_direction"
        ),
        CheckConstraint(
            "from_addr IS NULL OR char_length(from_addr) BETWEEN 1 AND 320",
            name="chk_intake_messages_from_addr_len",
        ),
        CheckConstraint(
            "subject IS NULL OR char_length(subject) <= 998",
            name="chk_intake_messages_subject_len",
        ),
        CheckConstraint(
            "body_text IS NULL OR char_length(body_text) <= 512000",
            name="chk_intake_messages_body_text_len",
        ),
        CheckConstraint(
            "in_reply_to IS NULL OR char_length(in_reply_to) <= 500",
            name="chk_intake_messages_in_reply_to_len",
        ),
        CheckConstraint(
            "references_header IS NULL OR char_length(references_header) <= 2000",
            name="chk_intake_messages_references_len",
        ),
        CheckConstraint(
            "send_error IS NULL OR char_length(send_error) BETWEEN 1 AND 100",
            name="chk_intake_messages_send_error_len",
        ),
        Index("ix_intake_messages_provider_message_id", "provider_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_threads.id", ondelete="CASCADE", name="fk_intake_messages_thread_id"),
        nullable=False,
    )
    provider_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    # INTAKE-3 (migration 0099): the message's own content, persisted so the arq
    # job — whose payload is ONLY the thread id — can re-derive the email for the
    # agent's fenced prompt block (app.agents.intake_prompt). Every value here is
    # UNTRUSTED sender-controlled text: it is boundary-validated at
    # app.schemas.intake, fenced as DATA in the prompt, and never logged or
    # audited. For a ``direction='out'`` row these carry a DRAFT reply the agent
    # composed (draft_email_reply); delivery arrives in INTAKE-4.
    from_addr: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_addrs: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The names ingest_bytes() actually stored for this message's attachments —
    # what ``read_document`` will answer to, so the prompt can name real files.
    attachment_filenames: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # INTAKE-4a (ADR-F088, migration 0100): the two RFC 5322 threading headers,
    # forwarded by the bridge inside the envelope's allowlisted ``headers`` map.
    # Persisted so the layer-2 resolver can match a reply that arrives on a NEW
    # provider thread back to a message we already hold: the ids in here are
    # compared to ``provider_message_id`` values, never parsed for meaning.
    in_reply_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    references_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    # INTAKE-4b (ADR-F087, migration 0101): why the approved send of THIS outbound
    # row failed, as an error CLASS ONLY (``timeout``, ``http_502``, ``duplicate``,
    # ``not_configured``, …). Never a provider message, a body or an address — a
    # provider error string quotes the recipient and the subject, and the audit
    # contract (counts/types/IDs) applies to this column too. NULL on every inbound
    # row and on every reply that was actually delivered.
    send_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provider-CLAIMED send time (validated, never trusted for ordering — the
    # thread's last_inbound_at is stamped from the server clock).
    provider_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The agent run that processed this message (INTAKE-3); SET NULL on run
    # delete keeps the message row (audit-adjacent, like File.created_by_run_id).
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL", name="fk_intake_messages_run_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<IntakeMessage id={self.id} thread_id={self.thread_id} direction={self.direction!r}>"
        )
