"""Agent-run ORM models — F0-S2 (fork).

Data substrate for deep-agent runs (ADR-F002 "glass cockpit"): every run
of a practice-area deep agent is persisted as an :class:`AgentRun` with
its loop steps appended as :class:`AgentRunStep` rows *as they complete*.
The UI's capability rail and activity feed poll these settled records —
render-deterministic per ADR-F004 ("user-visible state derives from
settled state records, never from parsing LLM turns").

Two tables, migration ``0048_agent_runs.py``:

* :class:`AgentRun` — the run record (prompt, model alias, interim caps,
  terminal status, final answer).
* :class:`AgentRunStep` — one loop step (model turn, tool call, or tool
  result) with a bounded summary. Unique on ``(run_id, seq)`` so the
  poller's ordered read is deterministic.

``agent_runs.user_id`` is a non-null FK with ``ON DELETE CASCADE`` —
agent runs are hard per-user isolated, matching the autonomous layer
(see :mod:`app.models.autonomous`). Steps cascade from their run.

``summary`` carries a bounded digest (~2000 chars) of the step — tool
arguments and results are truncated before persisting and NEVER carry
raw secrets (CLAUDE.md security rules; the audit contract's
counts/types/IDs posture applies to anything beyond the user's own
work product). The CHECK constraints on ``status`` / ``kind`` are
enforced at the storage layer (migration 0048); the canonical
``StrEnum`` definitions live in :mod:`app.schemas.agent_runs`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentRun(Base):
    """One deep-agent run — the record the capability rail polls.

    ``status`` is the lifecycle (``running → completed | failed |
    cancelled | cap_exceeded``). ``cancelled`` is RESERVED for the
    cancel endpoint (later slice); no code sets it in F0-S2.

    Interim caps (full guarded_tool_call/R4-R6 integration is F1, see
    ADR-F002): ``max_steps`` bounds the number of persisted steps;
    exceeding it terminates the run at ``cap_exceeded``. The runner
    additionally enforces a wall-clock timeout (status ``failed``,
    ``error='timeout'``). ``cost_usd`` is NULL until the F1 cost-cap
    work aggregates gateway routing-log costs per run.

    ``purpose`` is the routing-log tag the run's gateway calls carry
    (``lq_ai_purpose``, default ``'agent_loop'``) so agent traffic is
    separable from interactive chat in cost/usage queries.
    """

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_agent_runs_user_id"),
        nullable=False,
    )
    # F0-S4: the Matter this run is bound to (NULL = blank workspace, no
    # document tools). SET NULL so deleting a project unbinds, never
    # destroys, run records. Migration 0049.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL", name="fk_agent_runs_project_id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'running'"))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_alias: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'smart'"))
    purpose: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'agent_loop'"))
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("20"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AgentRun id={self.id} user_id={self.user_id} "
            f"status={self.status!r} model_alias={self.model_alias!r}>"
        )


class AgentRunStep(Base):
    """One step of a deep-agent run, persisted as it completes.

    ``seq`` is the 1-based step order within the run; unique on
    ``(run_id, seq)`` so the polled activity feed renders
    deterministically. ``kind`` walks the loop's observable events:
    ``model_turn`` (one chat-model completion), ``tool_call`` (the
    model dispatched a tool), ``tool_result`` (the tool returned).
    ``name`` is the tool name (NULL for model turns). ``summary`` is a
    bounded digest (~2000 chars) — tool args/results are truncated and
    never carry raw secrets.
    """

    __tablename__ = "agent_run_steps"
    __table_args__ = (
        # Backs the poller's ordered (run_id, seq) read AND guarantees
        # the runner never double-writes a step index.
        UniqueConstraint("run_id", "seq", name="uq_agent_run_steps_run_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE", name="fk_agent_run_steps_run_id"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return (
            f"<AgentRunStep id={self.id} run_id={self.run_id} "
            f"seq={self.seq} kind={self.kind!r} name={self.name!r}>"
        )
