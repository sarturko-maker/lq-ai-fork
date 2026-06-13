"""Pydantic schemas + shared enums for agent runs — F0-S2 (fork).

Wire shapes and the canonical ``StrEnum`` definitions for deep-agent run
records (ADR-F002 "glass cockpit"). The ORM models live in
:mod:`app.models.agent_run`; this module is the request/response surface
plus the single source of truth for the enums so models, the runner
(:mod:`app.agents.runner`), and the API share one definition.

The enums are ``StrEnum`` so members serialize to the plain strings the
CHECK constraints in migration ``0048_agent_runs.py`` enforce —
``AgentRunStatus.running == "running"`` etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AgentRunStatus(StrEnum):
    """Lifecycle of a deep-agent run.

    Matches the CHECK constraint on ``agent_runs.status``.
    ``cancelled`` is RESERVED for the cancel endpoint (later slice);
    nothing sets it in F0-S2.
    """

    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"  # RESERVED — cancel endpoint is a later slice
    cap_exceeded = "cap_exceeded"


class AgentRunStepKind(StrEnum):
    """The observable loop events a step row records.

    Matches the CHECK constraint on ``agent_run_steps.kind``.
    """

    model_turn = "model_turn"
    tool_call = "tool_call"
    tool_result = "tool_result"


class AgentRunCreate(BaseModel):
    """Request body for ``POST /agents/runs``.

    ``model_alias`` is a gateway alias (``smart``/``fast``/``budget``) —
    never a provider model id; routing, tier floors, and the routing log
    apply per request (CLAUDE.md: every LLM call goes through the
    gateway). ``max_steps`` is the interim step cap (full R4/R5/R6
    brakes are F1 scope, ADR-F002).

    F0-S5 (ADR-F008): ``thread_id`` continues an existing conversation —
    the run inherits the THREAD's Matter binding, so ``project_id`` must
    be omitted when ``thread_id`` is set (422 otherwise). Without
    ``thread_id`` a new thread is created (optionally Matter-bound via
    ``project_id``).
    """

    prompt: str = Field(min_length=1, max_length=32_768)
    model_alias: str = Field(default="smart", min_length=1, max_length=64)
    max_steps: int = Field(default=20, ge=1, le=100)
    # F0-S4: optional Matter binding — the run's agent gets the matter's
    # document tools and the gateway envelope carries the matter's
    # privilege/tier floor. Validated against ownership at the endpoint
    # (another user's project id → 404, never 403).
    project_id: uuid.UUID | None = None
    # F0-S5: continue this conversation (404 unowned; 409 when the
    # thread is busy or not continuable — ADR-F008).
    thread_id: uuid.UUID | None = None


class AgentRunRead(BaseModel):
    """ORM-read view of an :class:`~app.models.agent_run.AgentRun`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    thread_id: uuid.UUID
    project_id: uuid.UUID | None = None
    status: AgentRunStatus
    prompt: str
    final_answer: str | None = None
    model_alias: str
    purpose: str
    max_steps: int
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    cost_usd: Decimal | None = None


class AgentRunStepRead(BaseModel):
    """ORM-read view of an :class:`~app.models.agent_run.AgentRunStep`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    seq: int
    kind: AgentRunStepKind
    name: str | None = None
    summary: str
    # Innermost ancestor tool dispatch (F0-S7): NULL = root loop;
    # set = this step ran inside that tool_call row's subagent /
    # tool-wrapped graph. The UI groups, the eval gate measures, on it.
    parent_step_id: uuid.UUID | None = None
    created_at: datetime


class AgentRunDetailResponse(BaseModel):
    """Run detail plus its steps in ``seq`` order.

    The capability rail / activity feed polls this — steps are settled
    state records, never parsed LLM turns (ADR-F004).
    """

    run: AgentRunRead
    steps: list[AgentRunStepRead]


class AgentRunListResponse(BaseModel):
    """Paginated list of :class:`AgentRunRead` items (newest first).

    Mirrors ``AutonomousSessionListResponse`` — total_count / limit /
    offset envelope for consistent pagination conventions across the API.
    """

    runs: list[AgentRunRead]
    total_count: int
    limit: int
    offset: int


class AgentThreadRead(BaseModel):
    """ORM-read view of an :class:`~app.models.agent_run.AgentThread`.

    ``last_run_status`` is computed by the endpoint (the newest run's
    status) so the conversation list can badge threads without a second
    round trip; it is None only for a thread whose runs were all deleted
    underneath it (not a state the API produces itself).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    title: str
    created_at: datetime
    last_run_at: datetime
    last_run_status: AgentRunStatus | None = None


class AgentThreadListResponse(BaseModel):
    """Paginated conversation list (newest activity first)."""

    threads: list[AgentThreadRead]
    total_count: int
    limit: int
    offset: int


class MatterActivityRead(BaseModel):
    """One matter (project) with its agent-conversation rollup — F1-S2.

    The cockpit's matters list renders these instead of N+1
    ``ProjectResponse`` reads (which serialize attachments the list
    never shows). ``last_run_status`` is the newest run's status across
    ALL of the matter's threads; ``last_run_at`` / ``thread_count`` are
    aggregates over the caller's threads bound to the matter. All three
    are None/0 for a matter with no conversations yet. Settled rows
    only — never stream state (ADR-F004).
    """

    project_id: uuid.UUID
    name: str
    slug: str
    privileged: bool
    created_at: datetime
    thread_count: int = 0
    last_run_at: datetime | None = None
    last_run_status: AgentRunStatus | None = None
    # F1-S3: which practice area this matter files under (ADR-F002). None
    # for unfiled/legacy matters; the cockpit groups its area cards by
    # ``practice_area_key``.
    practice_area_id: uuid.UUID | None = None
    practice_area_key: str | None = None


class UnfiledThreadsSummary(BaseModel):
    """Rollup for the cockpit's "unfiled conversations" bucket — the
    caller's threads with no Matter binding (``project_id`` NULL; legacy
    data — every post-S8 composer run is matter-bound per ADR-F002).
    Surfaced rather than hidden: losing them loses data visibility and
    F2 memory scoping needs their story (MILESTONES § F1)."""

    thread_count: int = 0
    last_run_at: datetime | None = None
    last_run_status: AgentRunStatus | None = None


class MatterActivityResponse(BaseModel):
    """``GET /agents/matters`` — the cockpit's one-call matters surface:
    every active matter with activity rollups, plus the unfiled-bucket
    summary (computed server-side so client pagination can never
    under-report it)."""

    matters: list[MatterActivityRead]
    unfiled: UnfiledThreadsSummary


class AgentRunWithSteps(BaseModel):
    """One conversation turn: the run plus its steps in ``seq`` order."""

    run: AgentRunRead
    steps: list[AgentRunStepRead]


class AgentThreadDetailResponse(BaseModel):
    """Thread detail: the conversation's runs (oldest first) with steps.

    The multi-turn UI polls this while a run is live — same settled-rows
    contract as :class:`AgentRunDetailResponse` (ADR-F004).
    ``continuable`` tells the composer whether a follow-up would be
    accepted (latest run ``completed`` AND checkpoint state exists —
    ADR-F008); the POST endpoint re-checks, this flag is advisory UI
    state, not authorization.
    """

    thread: AgentThreadRead
    runs: list[AgentRunWithSteps]
    continuable: bool
