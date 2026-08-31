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
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.schemas.intake import DRAFT_REPLY_BODY_MAX_CHARS, DRAFT_REPLY_SUBJECT_MAX_CHARS


class AgentRunStatus(StrEnum):
    """Lifecycle of a deep-agent run.

    Matches the CHECK constraint on ``agent_runs.status`` (widened by
    migration ``0093``). ``awaiting_input`` (HITL-1, ADR-F071) is a SETTLED
    state: the run paused on a stop-and-ask policy before a gated tool
    executed. HITL-2 resolves it — ``POST /agents/runs/{id}/resume`` spawns a
    follow-up run with the human's approve/reject decision, and a paused
    thread now also admits an ordinary follow-up (a new message dissolves the
    pause). Cancelling a paused run settles it ``cancelled``.
    """

    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"  # RESERVED — cancel endpoint is a later slice
    cap_exceeded = "cap_exceeded"
    awaiting_input = "awaiting_input"


class AgentRunStepKind(StrEnum):
    """The observable loop events a step row records.

    Matches the CHECK constraint on ``agent_run_steps.kind`` (widened by
    migration ``0093``). ``hitl_request`` (HITL-1, ADR-F071) records the
    stop-and-ask: the pending tool name(s) + a display-only args digest —
    the approved bytes remain the checkpointed tool call itself.
    """

    model_turn = "model_turn"
    tool_call = "tool_call"
    tool_result = "tool_result"
    hitl_request = "hitl_request"


class BudgetProfile(StrEnum):
    """Cost/effort envelope for an agent run (ADR-F053).

    Selects a tier of the four per-run brakes (token budget, fan-out quota,
    max steps, wall clock). ``balanced`` is the default (~4x the old caps);
    ``economy`` dials down to the conservative tier; ``generous`` raises it for
    deep work. The string values are persisted on ``agent_runs.budget_profile``
    and resolved to a concrete envelope in :mod:`app.agents.budget`.
    """

    economy = "economy"
    balanced = "balanced"
    generous = "generous"


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
    # F2 Slice O (ADR-F053): the run's cost/effort envelope. Resolves
    # server-side to (token_budget, fan_out_quota, max_steps, wall_clock).
    # SETUP-5a (ADR-F063): None = "resolve for me" — the endpoint walks
    # run-explicit > area default > deployment default > balanced and persists
    # the RESOLVED value. (The old always-concrete balanced default made a
    # client omission indistinguishable from an explicit balanced pick.)
    budget_profile: BudgetProfile | None = Field(default=None)
    # Per-run step ceiling. Normally driven by ``budget_profile`` (ADR-F053):
    # leave this None and the resolved profile's max_steps applies (economy 100 /
    # balanced 400 / generous 600). Set it to override the profile for one run
    # (advanced); the hard ceiling is 600 (the generous tier). The token budget
    # (ADR-F051) is the money guard and the wall clock bounds time.
    max_steps: int | None = Field(default=None, ge=1, le=600)
    # F0-S4: optional Matter binding — the run's agent gets the matter's
    # document tools and the gateway envelope carries the matter's
    # privilege/tier floor. Validated against ownership at the endpoint
    # (another user's project id → 404, never 403).
    project_id: uuid.UUID | None = None
    # F0-S5: continue this conversation (404 unowned; 409 when the
    # thread is busy or not continuable — ADR-F008).
    thread_id: uuid.UUID | None = None


def _no_control_chars(value: str) -> str:
    """Reject (never strip) control characters other than newline and tab.

    An approved reply's text goes out over SMTP: a bare CR, a NUL or an escape
    sequence in a subject line is header-injection surface, and in a body it is
    junk a human did not intend. "Reject, don't sanitize" (CLAUDE.md).
    """
    for ch in value:
        if ch in "\n\t":
            continue
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ValueError("must not contain control characters (except newline and tab)")
    return value


_CleanText = Annotated[str, AfterValidator(_no_control_chars)]


def _no_control_chars_subject(value: str) -> str:
    """Stricter than :func:`_no_control_chars`, for a SUBJECT line (F7c).

    A subject is a single RFC-5322 line rendered in the outbound row the lawyer
    reads; a newline or bare CR would let a human-edited (or, on the sibling
    ``DraftEmailReplyInput`` path, agent-drafted) subject break onto a second visual
    line, and is defence-in-depth against header injection should a future slice ever
    pass the subject through to the bridge (today the bridge composes its own
    ``Re:`` subject and this value is display-only). Both are rejected even though a
    body may keep them; a tab is the one allowed whitespace, as elsewhere.
    """
    for ch in value:
        if ch == "\t":
            continue
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ValueError("subject must not contain control characters or line breaks")
    return value


_CleanSubject = Annotated[str, AfterValidator(_no_control_chars_subject)]


class EditedEmailReplyArgs(BaseModel):
    """The lawyer's edit of a pending ``draft_email_reply`` (INTAKE-4b, ADR-F087).

    The prose fields, and ONLY those. An omitted ``subject`` KEEPS the model's
    original argument (the runner merges over the pending action request), so
    "I only fixed the body" does not silently blank the subject line.

    **``to`` is deliberately not editable** (``extra="forbid"`` rejects it). The
    mail-bridge is reply-only by construction — it derives the recipients from the
    message being answered and is never handed an address, which is the property
    that stops anything the agent produces from mailing a third party (ADR-F086).
    A recipient editor would therefore be a control that does nothing; honouring one
    means widening the egress surface, which is its own decision, not a UI detail.

    Bounds are IMPORTED from :class:`~app.schemas.intake.DraftEmailReplyInput`'s own
    constants rather than restated, so the boundary and the tool can never drift
    apart. This is the API boundary; the tool re-validates the merged args against
    that schema when it executes (code disposes twice, ADR-F018).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    subject: _CleanSubject | None = Field(
        default=None, min_length=1, max_length=DRAFT_REPLY_SUBJECT_MAX_CHARS
    )
    body: _CleanText = Field(min_length=1, max_length=DRAFT_REPLY_BODY_MAX_CHARS)


class ResumeDecision(BaseModel):
    """The human's resolution of ONE paused ask (HITL-2, ADR-F071; ADR-F087).

    A SINGLE decision applied to the whole pending ask — the runner fans it across
    every gated tool call in the paused turn when it builds ``Command(resume=…)``.

    ``message`` is only meaningful for a ``reject``: it becomes the tool result the
    model sees, which is exactly why the UI's "Respond — tell the agent what to
    change" is a reject WITH a message rather than a fourth verb (ADR-F087). It is
    validated (reject-don't-sanitize), never sanitized, and never logged.

    ``edit`` (ADR-F087, amending F071's non-goal) carries the lawyer's rewritten
    ``draft_email_reply`` arguments and is accepted ONLY when the pending ask is
    that tool — the endpoint 422s otherwise, and the runner checks again against
    ``hitl.EDITABLE_TOOL_NAMES``.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["approve", "reject", "edit"]
    message: str | None = Field(default=None, max_length=2_000)
    edited_args: EditedEmailReplyArgs | None = None

    @model_validator(mode="after")
    def _fields_match_the_verb(self) -> ResumeDecision:
        if self.type == "edit" and self.edited_args is None:
            raise ValueError("edited_args is required for an 'edit' decision")
        if self.type != "edit" and self.edited_args is not None:
            raise ValueError("edited_args is only valid on an 'edit' decision")
        if self.type != "reject" and self.message is not None:
            raise ValueError("message is only valid on a 'reject' decision")
        return self


class AgentRunResume(BaseModel):
    """Request body for ``POST /agents/runs/{run_id}/resume`` (HITL-2)."""

    model_config = ConfigDict(extra="forbid")

    decision: ResumeDecision


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
    # F2 Slice O-2 (ADR-F053 addendum): a rough rolling-average USD estimate of the
    # run's spend (blended agent_loop per-token rate x total_tokens). An ESTIMATE,
    # surfaced as approximate in the UI; NULL on timeout/error or before settlement.
    cost_usd: Decimal | None = None
    # F2 Slice G (ADR-F051 follow-up): the run's cumulative model tokens, NULL until
    # settlement / when usage was not reported.
    total_tokens: int | None = None
    # F2 Slice O (ADR-F053): the cost/effort envelope the run was created with.
    # NULL for legacy rows created before the column existed (treated as balanced).
    budget_profile: BudgetProfile | None = None


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
