"""The lawyer's Inbox — intake thread read API (INTAKE-5a, ADR-F086).

Two owner-fenced reads, and nothing else. After INTAKE-4 the machine works
end-to-end but the only way to find out what it did was to open a conversation you
already knew about; these are the front door
(``docs/fork/plans/INTAKE-5-plan.md``):

* ``GET /intake/threads`` — every email thread the caller can see, **attention
  first**: a live approval ask, then a failed send, then "the agent says a human is
  needed", then work in flight, then replied, then handled (plan ruling 3). The
  order is computed HERE, in SQL, so the UI cannot invent a second, disagreeing
  queue. One page = one query for the rows (three lateral joins carry the derived
  columns) plus one bounded query for the paused asks' digests — no N+1.
* ``GET /intake/threads/{id}`` — that thread with its emails, oldest first.

**The owner fence.** A thread is visible to the owner of the MATTER it landed in.
A thread whose project row was hard-deleted (``project_id`` is ``SET NULL``) falls
back to the mailbox's ``owner_user_id`` — the queue owner, who owns every matter
and run the mailbox produces anyway. Anyone else simply does not see the row: the
list omits it and the detail 404s (never 403 — no existence leaks, CLAUDE.md).

**What may leave this module.** Bodies, subjects and addresses go to the human who
owns them (plan ruling 9) and NOWHERE else: there is not one logging call in this
file, and none may be added — the audit contract (counts/types/IDs, never raw
values) governs this surface exactly as it governs the landing endpoint. Every
string returned is rendered as text by the client, never as HTML.

Nothing here mutates. Human attach (``POST /intake/threads/{id}/attach``) is
INTAKE-5b and carries ``MutatingUser`` + an audit row; this slice is read-only, so
the router mounts under the ordinary ``_active`` user gate.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections import defaultdict, deque
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, Row, case, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.agents.hitl import decisions_allowed_for_step, order_decisions, tool_names_for_step
from app.agents.intake_prompt import single_line_neutralised
from app.agents.run_service import IN_FLIGHT_RUN_STATUSES, NOT_LIVE_RUN_STATUSES
from app.api.dependencies import ActiveUser
from app.db.session import get_db
from app.models.agent_run import AgentRun, AgentRunStep
from app.models.file import File
from app.models.intake import IntakeMailbox, IntakeMessage, IntakeThread
from app.models.project import Project
from app.schemas.agent_runs import AgentRunStatus, AgentRunStepKind
from app.schemas.intake import (
    INTAKE_THREAD_LIST_LIMIT_DEFAULT,
    INTAKE_THREAD_LIST_LIMIT_MAX,
    INTAKE_THREAD_MESSAGE_MAX,
    IntakeLiveAskRead,
    IntakeMessageRead,
    IntakeSummaryItem,
    IntakeThreadDetailResponse,
    IntakeThreadListResponse,
    IntakeThreadProjectRead,
    IntakeThreadRead,
)

router = APIRouter(prefix="/intake", tags=["intake-threads"])

# Plan ruling 3, as a sort key. Lower sorts first. `handled` and anything the CHECK
# does not know about fall to the bottom together — a status we cannot rank is not
# an emergency, and inventing a rank for it would be a guess.
_ATTENTION_LIVE_ASK = 0
_ATTENTION_SEND_FAILED = 1
_ATTENTION_AWAITING_HUMAN = 2
_ATTENTION_WORKING = 3
_ATTENTION_REPLIED = 4
_ATTENTION_HANDLED = 5
#: What ``attention=true`` keeps: the three ranks a human is expected to act on.
_ATTENTION_CUTOFF = _ATTENTION_AWAITING_HUMAN

#: Thread statuses accepted by the ``status`` filter — the model's CHECK vocabulary.
#: An unknown value is a 422 at the boundary, not an empty page (reject, don't guess).
_THREAD_STATUS_FILTER = ("received", "processing", "awaiting_human", "replied", "handled", "error")

#: Hard ceiling on the cursor's OFFSET. An offset is a SKIP the database pays for
#: row by row, so an unbounded one is a free way to make the server do arbitrary
#: work. 10_000 is far past any real Inbox (200 pages at the max page size); past
#: it the answer is a 422, not a slow scan. Reject at the boundary, don't clamp —
#: a silently clamped cursor would return a page the client did not ask for.
_CURSOR_OFFSET_MAX = 10_000


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def _encode_cursor(offset: int) -> str:
    """Encode the next page's offset as an opaque wire cursor.

    Deliberately an OFFSET and not a keyset comparator, which is what the chat list
    uses. The Inbox's sort key leads with ``attention_rank``, a DERIVED value that
    changes the moment a run settles or a send fails — a keyset built on it would be
    exact about a boundary that is not stable anyway, at the price of a three-part
    mixed-direction comparator with NULL handling. Offset over a bounded page is the
    honest trade. The base64 keeps the wire shape opaque so this can become a keyset
    later without a client change.
    """
    body = json.dumps({"offset": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(body.encode("utf-8")).rstrip(b"=").decode("ascii")


def _decode_cursor(value: str) -> int:
    """Decode a wire cursor to its offset; 422 on anything malformed."""
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode(value + padding).decode("utf-8")
        decoded = json.loads(raw)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="cursor is malformed") from exc
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=422, detail="cursor is malformed")
    offset = decoded.get("offset")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise HTTPException(status_code=422, detail="cursor is malformed")
    if offset > _CURSOR_OFFSET_MAX:
        raise HTTPException(status_code=422, detail="cursor is out of range")
    return offset


# ---------------------------------------------------------------------------
# The page query
# ---------------------------------------------------------------------------


def _thread_page_select(user_id: uuid.UUID) -> tuple[Any, ColumnElement[int]]:
    """The owner-fenced thread SELECT plus its attention-rank expression.

    Four joins carry what the row model needs and one query cannot be talked out of:

    ``live``
        the conversation's newest LIVE run (:data:`NOT_LIVE_RUN_STATUSES` — the
        shared definition in ``run_service``, so this page and the resume endpoint
        can never disagree about what is live). A ``awaiting_input`` status here IS
        the "needs your decision" row.
    ``last_err``
        the newest outbound message that failed to send, for its error CLASS.
    ``settled``
        the newest SETTLED run that processed one of THIS thread's inbound messages
        — the other half of ``summary_stale`` (see :func:`_row_to_read`).
    ``summary_run``
        the run that wrote the summary, for its ``started_at``.

    The fence is the WHERE clause, not a post-filter: a thread the caller cannot see
    never leaves the database. The rank expression is returned UNLABELLED alongside
    the statement so ``attention=true`` can filter on the SAME expression the page is
    ordered by (a post-filter in Python would silently shrink pages and break the
    cursor) — unlabelled because a label is only addressable in the columns and
    ORDER BY clauses, never in a WHERE.
    """
    live = (
        select(AgentRun.id.label("run_id"), AgentRun.status.label("run_status"))
        .where(
            AgentRun.thread_id == IntakeThread.agent_thread_id,
            AgentRun.status.not_in(NOT_LIVE_RUN_STATUSES),
        )
        .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
        .limit(1)
        .lateral("live_run")
    )
    last_err = (
        select(IntakeMessage.send_error.label("send_error"))
        .where(
            IntakeMessage.thread_id == IntakeThread.id,
            IntakeMessage.direction == "out",
            IntakeMessage.send_error.is_not(None),
        )
        .order_by(IntakeMessage.created_at.desc(), IntakeMessage.id.desc())
        .limit(1)
        .lateral("last_send_error")
    )
    settled = (
        select(AgentRun.started_at.label("started_at"))
        .join(IntakeMessage, IntakeMessage.run_id == AgentRun.id)
        .where(
            IntakeMessage.thread_id == IntakeThread.id,
            IntakeMessage.direction == "in",
            AgentRun.status.not_in(IN_FLIGHT_RUN_STATUSES),
        )
        .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
        .limit(1)
        .lateral("newest_settled_run")
    )
    summary_run = aliased(AgentRun, name="summary_run")

    attention_rank = case(
        (live.c.run_status == AgentRunStatus.awaiting_input.value, _ATTENTION_LIVE_ASK),
        (IntakeThread.status == "error", _ATTENTION_SEND_FAILED),
        (IntakeThread.status == "awaiting_human", _ATTENTION_AWAITING_HUMAN),
        (IntakeThread.status.in_(("processing", "received")), _ATTENTION_WORKING),
        (IntakeThread.status == "replied", _ATTENTION_REPLIED),
        else_=_ATTENTION_HANDLED,
    )

    stmt = (
        select(
            IntakeThread,
            IntakeMailbox.address.label("mailbox_address"),
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            Project.reference.label("project_reference"),
            Project.archived_at.label("project_archived_at"),
            live.c.run_id,
            live.c.run_status,
            last_err.c.send_error,
            settled.c.started_at.label("newest_settled_started_at"),
            summary_run.started_at.label("summary_run_started_at"),
            attention_rank.label("attention_rank"),
        )
        .select_from(IntakeThread)
        .join(IntakeMailbox, IntakeMailbox.id == IntakeThread.mailbox_id)
        .outerjoin(Project, Project.id == IntakeThread.project_id)
        .outerjoin(summary_run, summary_run.id == IntakeThread.summary_run_id)
        .outerjoin(live, true())
        .outerjoin(last_err, true())
        .outerjoin(settled, true())
        .where(
            # The owner fence. `project_id` is NULL exactly when the matter row was
            # hard-deleted (SET NULL), and such an orphan belongs to the mailbox's
            # queue owner alone.
            (Project.owner_id == user_id)
            | (IntakeThread.project_id.is_(None) & (IntakeMailbox.owner_user_id == user_id))
        )
    )
    return stmt, attention_rank


def _row_to_read(row: Row[Any], live_asks: dict[uuid.UUID, IntakeLiveAskRead]) -> IntakeThreadRead:
    """Turn one page row into the wire model.

    ``summary_stale`` — the definition, in one sentence: **the newest SETTLED run
    that processed one of this thread's inbound emails started AFTER the run that
    wrote the summary.** In other words, a worker run has come and gone since the
    account you are reading was written, and it did not rewrite it — which is what
    ``safe_fail_intake_thread`` leaves behind when a run is cancelled, capped or
    crashes without concluding.

    Three deliberate consequences:

    * a thread with NO summary is never "stale" (there is nothing to be out of
      date — the UI opens such a thread on the email chain instead, plan ruling 7);
    * a **resume** run is not counted. It is a new ``agent_runs`` row with no inbound
      message stamped on it, so it cannot make an approve-then-send flow — where the
      outcome is recorded in the paused run, exactly as the doctrine asks — report a
      stale summary the moment the lawyer clicks Approve;
    * a summary whose run row was deleted (``summary_run_id`` SET NULL) reads as
      fresh. We cannot date it, and crying wolf about an account that may be perfect
      is worse than saying nothing.
    """
    thread: IntakeThread = row[0]
    summary_started = row.summary_run_started_at
    settled_started = row.newest_settled_started_at
    summary_stale = bool(
        thread.summary
        and summary_started is not None
        and settled_started is not None
        and settled_started > summary_started
    )
    project = None
    if row.project_id is not None:
        project = IntakeThreadProjectRead(
            id=row.project_id,
            name=row.project_name,
            reference=row.project_reference,
            archived=row.project_archived_at is not None,
        )
    return IntakeThreadRead(
        id=thread.id,
        mailbox_address=row.mailbox_address,
        subject=single_line_neutralised(thread.subject),
        status=thread.status,
        outcome=thread.outcome,
        label=thread.label,
        outcome_note=thread.outcome_note,
        auth_state=thread.auth_state,
        claimed_reference=thread.claimed_reference,
        summary=_summary_items(thread.summary),
        summary_stale=summary_stale,
        message_count=thread.message_count,
        last_inbound_at=thread.last_inbound_at,
        project=project,
        agent_thread_id=thread.agent_thread_id,
        live_ask=live_asks.get(row.run_id) if row.run_id is not None else None,
        last_send_error=row.send_error,
        attention_rank=row.attention_rank,
    )


def _summary_items(stored: list[Any] | None) -> list[IntakeSummaryItem]:
    """Re-validate the stored summary on the way OUT, dropping anything malformed.

    The column is JSONB with no DB CHECK — its shape is guarded at the Pydantic
    write boundary. Re-validating here means a row planted by out-of-band SQL (or
    left by a future migration) degrades to the bullets that do parse instead of
    500-ing the whole Inbox, and the length/control-character bounds are enforced on
    the read path too rather than trusted.
    """
    if not isinstance(stored, list):
        return []
    items: list[IntakeSummaryItem] = []
    for entry in stored:
        if not isinstance(entry, dict):
            continue
        try:
            items.append(IntakeSummaryItem.model_validate(entry))
        except ValueError:
            continue
    return items


async def _load_live_asks(
    db: AsyncSession, run_ids: list[uuid.UUID]
) -> dict[uuid.UUID, IntakeLiveAskRead]:
    """The paused ask for each of the page's ``awaiting_input`` runs — ONE query.

    Reads the SETTLED ``hitl_request`` step (ADR-F004: the durable row decides, never
    a re-read of the checkpoint), exactly as ``POST /agents/runs/{id}/resume`` does,
    and derives the verbs through the same :func:`decisions_allowed_for_step` gate so
    the Inbox can never offer a decision the resume endpoint would refuse.
    """
    if not run_ids:
        return {}
    rows = (
        await db.execute(
            select(AgentRunStep.run_id, AgentRunStep.name, AgentRunStep.summary)
            .where(
                AgentRunStep.run_id.in_(run_ids),
                AgentRunStep.kind == AgentRunStepKind.hitl_request.value,
            )
            .distinct(AgentRunStep.run_id)
            .order_by(AgentRunStep.run_id, AgentRunStep.seq.asc())
        )
    ).all()
    return {
        run_id: IntakeLiveAskRead(
            run_id=run_id,
            tool_names=tool_names_for_step(name, summary),
            allowed_decisions=order_decisions(decisions_allowed_for_step(name, summary)),
        )
        for run_id, name, summary in rows
    }


async def _read_page(db: AsyncSession, stmt: Any) -> list[IntakeThreadRead]:
    """Execute a thread SELECT and hydrate its rows (including the live asks)."""
    rows = (await db.execute(stmt)).all()
    paused = [
        row.run_id
        for row in rows
        if row.run_id is not None and row.run_status == AgentRunStatus.awaiting_input.value
    ]
    live_asks = await _load_live_asks(db, paused)
    return [_row_to_read(row, live_asks) for row in rows]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/threads",
    response_model=IntakeThreadListResponse,
    summary="The caller's intake email threads, attention first.",
)
async def list_intake_threads(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    project_id: Annotated[
        uuid.UUID | None,
        Query(description="Narrow to one matter's threads (the matter-level Inbox tab)."),
    ] = None,
    status: Annotated[str | None, Query(description="Narrow to one thread status.")] = None,
    attention: Annotated[
        bool,
        Query(description="Only threads a human is expected to act on (ranks 0, 1 and 2)."),
    ] = False,
    limit: Annotated[int, Query(ge=1, le=INTAKE_THREAD_LIST_LIMIT_MAX)] = (
        INTAKE_THREAD_LIST_LIMIT_DEFAULT
    ),
    cursor: Annotated[
        str | None, Query(description="Opaque cursor from a previous page's `next_cursor`.")
    ] = None,
) -> IntakeThreadListResponse:
    """GET /api/v1/intake/threads

    Attention-first (plan ruling 3): a live approval ask, then a failed send, then a
    thread the agent handed to a human, then one still being worked, then replied,
    then handled; ties newest-inbound-first. ``attention=true`` keeps the first
    three. A ``project_id`` the caller does not own matches nothing — an empty page,
    never a 404, so the filter cannot be used to probe for foreign matters.
    """
    if status is not None and status not in _THREAD_STATUS_FILTER:
        raise HTTPException(status_code=422, detail="unknown thread status")
    offset = _decode_cursor(cursor) if cursor else 0

    stmt, attention_rank = _thread_page_select(user.id)
    if project_id is not None:
        stmt = stmt.where(IntakeThread.project_id == project_id)
    if status is not None:
        stmt = stmt.where(IntakeThread.status == status)
    if attention:
        stmt = stmt.where(attention_rank <= _ATTENTION_CUTOFF)
    # Fetch one extra row to learn whether a next page exists without a COUNT.
    stmt = (
        stmt.order_by(
            attention_rank,
            IntakeThread.last_inbound_at.desc().nulls_last(),
            IntakeThread.id.desc(),
        )
        .limit(limit + 1)
        .offset(offset)
    )
    items = await _read_page(db, stmt)
    has_more = len(items) > limit
    items = items[:limit]
    # Never hand back a cursor the decoder would refuse: past `_CURSOR_OFFSET_MAX`
    # the walk ends here rather than issuing a link that 422s on use.
    next_offset = offset + limit
    return IntakeThreadListResponse(
        items=items,
        next_cursor=(
            _encode_cursor(next_offset) if has_more and next_offset <= _CURSOR_OFFSET_MAX else None
        ),
    )


@router.get(
    "/threads/{thread_id}",
    response_model=IntakeThreadDetailResponse,
    summary="One intake thread with its emails, oldest first.",
)
async def get_intake_thread(
    thread_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeThreadDetailResponse:
    """GET /api/v1/intake/threads/{thread_id}

    The thread row exactly as the list renders it, plus every email on it in
    ``provider_timestamp`` order, falling back to our insert time for rows without one
    (sent replies — the bridge returns no timestamp). The provider's claimed send time
    is untrusted for lifecycle decisions but is the right thing to READ a chain by; ties
    break on our own insert order. A thread the caller cannot see is a 404 — the same answer a
    non-existent id gets.

    A chain longer than ``INTAKE_THREAD_MESSAGE_MAX`` keeps its NEWEST messages: the
    query walks newest-first and the page is reversed in Python, so the reader still
    gets an oldest-first chain but the part that is missing is the old part, not the
    part they came to read. ``messages_truncated`` says so.
    """
    stmt, _rank = _thread_page_select(user.id)
    items = await _read_page(db, stmt.where(IntakeThread.id == thread_id))
    if not items:
        raise HTTPException(status_code=404, detail="intake thread not found")
    thread_read = items[0]

    # Newest-first in SQL (with one extra row to detect truncation), then reversed
    # here: the client is served oldest-first, but what falls off a long chain is
    # the OLD end, not the new one. `nulls_first` on the DESC leg is the exact
    # mirror of the oldest-first `nulls_last` this used to be, so an untruncated
    # chain comes back in precisely the order it always did.
    rows = (
        (
            await db.execute(
                select(IntakeMessage)
                .where(IntakeMessage.thread_id == thread_id)
                .order_by(
                    # Sent rows carry no provider timestamp (the bridge returns only the
                    # id), so the chain reads by the provider's time where we have it and
                    # by our own insert time where we don't — otherwise every reply would
                    # sort after every inbound email.
                    func.coalesce(
                        IntakeMessage.provider_timestamp, IntakeMessage.created_at
                    ).desc(),
                    IntakeMessage.created_at.desc(),
                    IntakeMessage.id.desc(),
                )
                .limit(INTAKE_THREAD_MESSAGE_MAX + 1)
            )
        )
        .scalars()
        .all()
    )
    truncated = len(rows) > INTAKE_THREAD_MESSAGE_MAX
    messages = list(reversed(rows[:INTAKE_THREAD_MESSAGE_MAX]))
    file_ids = await _resolve_attachment_file_ids(
        db, messages, project_id=thread_read.project.id if thread_read.project else None
    )
    return IntakeThreadDetailResponse(
        thread=thread_read,
        messages=[
            IntakeMessageRead(
                id=m.id,
                direction=m.direction,
                from_addr=m.from_addr,
                to_addrs=[str(a) for a in (m.to_addrs or [])],
                subject=m.subject,
                body_text=m.body_text,
                attachment_filenames=[str(f) for f in (m.attachment_filenames or [])],
                file_ids=file_ids.get(m.id, []),
                provider_timestamp=m.provider_timestamp,
                run_id=m.run_id,
                send_error=m.send_error,
            )
            for m in messages
        ],
        messages_truncated=truncated,
    )


async def _resolve_attachment_file_ids(
    db: AsyncSession, messages: list[IntakeMessage], *, project_id: uuid.UUID | None
) -> dict[uuid.UUID, list[uuid.UUID | None]]:
    """Best-effort ``attachment_filenames`` → ``files.id``, per message.

    **There is no stored link.** ``ingest_bytes`` writes a ``files`` row per
    attachment and the landing endpoint records only the STORED filenames on the
    message (``app.api.intake_emails``), so the join has to be reconstructed. The
    rule: within this thread's matter, take the live ``files`` rows whose
    ``filename`` is one of the names ON THIS PAGE (an ``IN`` over that set — the
    query never pulls the matter's whole file table, which on a data-room matter is
    thousands of rows this thread has no use for), oldest first, and hand them out
    to the messages in INGEST order (message ``created_at``) — the same order the
    rows were written in. That is exact whenever a filename appears once, and
    correct-by-construction for a filename that repeats across messages in the
    ordinary case; a repeat whose rows were re-ordered by a later human upload can
    mis-pair, so the UI treats an id as a convenience link to a document it also
    names, never as proof.

    Returns a list PARALLEL to each message's ``attachment_filenames`` (same length,
    same order), with ``None`` where nothing resolved. An orphaned thread (no matter)
    resolves nothing.
    """
    resolved: dict[uuid.UUID, list[uuid.UUID | None]] = {
        m.id: [None] * len(m.attachment_filenames or []) for m in messages
    }
    wanted = {str(name) for m in messages for name in (m.attachment_filenames or []) if str(name)}
    if project_id is None or not wanted:
        return resolved
    rows = (
        await db.execute(
            select(File.id, File.filename)
            .where(
                File.project_id == project_id,
                File.deleted_at.is_(None),
                File.filename.in_(wanted),
            )
            .order_by(File.created_at.asc(), File.id.asc())
        )
    ).all()
    by_name: dict[str, deque[uuid.UUID]] = defaultdict(deque)
    for file_id, filename in rows:
        by_name[filename].append(file_id)
    for message in sorted(messages, key=lambda m: (m.created_at, m.id)):
        slot = resolved[message.id]
        for index, filename in enumerate(message.attachment_filenames or []):
            queue = by_name.get(str(filename))
            if queue:
                slot[index] = queue.popleft()
    return resolved


__all__ = ["router"]
