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
    """

    prompt: str = Field(min_length=1, max_length=32_768)
    model_alias: str = Field(default="smart", min_length=1, max_length=64)
    max_steps: int = Field(default=20, ge=1, le=100)


class AgentRunRead(BaseModel):
    """ORM-read view of an :class:`~app.models.agent_run.AgentRun`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
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
