"""The intake run's two tools — INTAKE-3 (fork, ADR-F086).

An intake run is an ORDINARY agent run on the bound practice-area agent (Ruling 1):
same composition root, same brakes, same memory tiers. Only two things are added, and
only for a run whose matter was born from an intake email (``projects.intake_state IS
NOT NULL`` — provenance, and the grant gate) — the same "structural grant, not area data" precedent as the matter-memory
tools, so no ``practice_area_tool_groups`` row exists or is needed:

* :func:`record_intake_outcome` — the run's STRUCTURAL conclusion. A closed outcome
  enum plus a short free-form label and a note. This is the ONE thing an intake run
  must do (ADR-F086: "recorded structurally … never free prose"), and it decides
  whether the thread's matter closes or stays open for the lawyer.

  Every intake thread IS a matter from message one (ADR-F086 Amendment A1), so there
  are TWO outcomes and no promotion step:

  ================  =====================  ====================================
  outcome           intake_threads.status  the matter
  ================  =====================  ====================================
  ``dealt_with``    ``handled``            closed (``archived_at``), label + note
  ``needs_human``   ``awaiting_human``     stays open for the lawyer
  ================  =====================  ====================================

  ``projects.intake_state`` is PROVENANCE ("born from email") and the grant gate for
  these tools — the agent path never writes it.

  INTAKE-5a (ADR-F086 ruling 7) makes the call carry a required ``summary``: the
  agent's one-to-five-bullet account of THE THREAD SO FAR, REWRITTEN IN FULL every
  time, which is what the lawyer's Inbox opens on instead of the email chain.

* :func:`draft_email_reply` — composes a reply, records it as a ``direction='out'``
  ``intake_messages`` row and, INTAKE-4b (ADR-F087), SENDS it. There is still no
  auto-send path: the tool is interrupt-gated UNCONDITIONALLY by
  :data:`app.agents.hitl.ALWAYS_INTERRUPT_TOOL_NAMES` — a structural gate, not a
  policy one, so no area config and no instruction inside a hostile email can
  unlock it — and its body runs only after a human approved (or edited) the exact
  call. "The tool executed" and "a lawyer said yes to these bytes" are one event,
  which is precisely why the send lives in the tool. Delivery goes through the
  injected mail-bridge client (api → bridge ``POST /send``); the api holds only
  the bridge token, never a mailbox credential (ADR-F086).

Both writes go through ``guarded_dispatch`` (R6 grant / R5 halt / R4 cost) with the
guard's auto-audit only: counts/IDs, never the label, the note or a body. The grant
set is DISJOINT from every matter/domain grant (confinement).

Zero model calls; pure DB writes.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import MatterBinding
from app.clients.mail_bridge import BridgeClient, BridgeSendError
from app.matters.stamping import tag_subject
from app.models.agent_run import AgentRun
from app.models.intake import IntakeMessage, IntakeThread
from app.models.project import Project
from app.schemas.intake import DraftEmailReplyInput, RecordIntakeOutcomeInput

logger = logging.getLogger(__name__)

INTAKE_TOOL_NAMES = frozenset({"record_intake_outcome", "draft_email_reply"})
# INTAKE-5a.1: the human-asked "Summarise now" pass gets the conclusion tool alone.
_SUMMARISE_TOOL_NAMES = frozenset({"record_intake_outcome"})

# outcome -> the thread status it settles on. The matter-side effect (closing the
# matter on 'dealt_with') is applied beside this map in _record_intake_outcome.
_OUTCOME_THREAD_STATUS: dict[str, str] = {
    "dealt_with": "handled",
    "needs_human": "awaiting_human",
}

# R7 — the safe-fail note. FORK-AUTHORED and fixed: a run that ended without
# concluding must never have model text put in its place.
NO_OUTCOME_NOTE = "run ended without a recorded outcome"

# INTAKE-4b (ADR-F087): the marker on an outbound row that has NOT been delivered.
# ``provider_message_id`` is NOT NULL (it is half the idempotency unique key), so an
# undelivered reply carries this prefix plus its per-ask send key until the provider
# assigns the real id. "Starts with this" is therefore exactly "never went out".
_DRAFT_ID_PREFIX = "draft:"

# INTAKE-4b: a thread nobody has started work on yet (the landing endpoint's initial
# state). Used only as the last-resort tie-break when no message on the conversation
# has been processed at all — see load_intake_thread_for_run.
_PENDING_THREAD_STATUSES = frozenset({"received"})

# Thread statuses a settled SEND put on the thread. ``record_intake_outcome`` must not
# overwrite them: "we replied" / "the send failed" is a stronger, later fact about the
# thread than the outcome's own bookkeeping, and losing `error` loses the only place a
# failed delivery is visible to the lawyer.
_SEND_TERMINAL_THREAD_STATUSES = frozenset({"replied", "error"})


def _send_key(thread_id: uuid.UUID, tool_call_id: str) -> str:
    """The idempotency key for ONE approved ask (INTAKE-4b, ADR-F087).

    Derived from the CHECKPOINTED tool-call id, which is the only identifier that is
    stable across everything that can make this tool run twice: the HITL middleware
    rebuilds an EDITED call with the same id, and a re-approval after a crashed run
    resumes the same checkpointed call. A freshly minted row id is not — that was the
    double-send hole.

    sha256 (not the raw id) for two reasons: provider tool-call ids have no length
    contract and the bridge caps the key at 64 chars, and hashing keeps a
    provider-supplied string out of another service's key space entirely. Salted with
    the thread id so the same id under two threads can never collide.
    """
    return hashlib.sha256(f"{thread_id}:{tool_call_id}".encode()).hexdigest()


def build_intake_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
    intake_thread_id: uuid.UUID,
    bridge: BridgeClient | None = None,
    summarise_only: bool = False,
) -> list[Callable[..., Any]]:
    """Build the intake tools for one run on an intake-born matter (one, or two).

    The guard context grants exactly :data:`INTAKE_TOOL_NAMES`; ``binding.project_id``
    scopes every write, so the blast radius is this one matter and the one
    intake thread bound to it.

    ``intake_thread_id`` is the ONE thread this run is working on, resolved ONCE at
    the composition root by :func:`load_intake_thread_for_run` and handed down. A
    conversation can carry several intake threads (ADR-F088 layer 2/3), so neither tool
    may re-derive "the thread" from the project — that was the crash and, once
    LIMIT-1'd, would have been the wrong thread.

    ``bridge`` (INTAKE-4b, ADR-F087) is the mail-bridge send seam, constructed at the
    composition root and injected here — never reached for as a global. ``None`` means
    the deployment has not configured a bridge: an approved reply is then kept as a
    draft with ``send_error='not_configured'`` and the tool says plainly that nothing
    was delivered.

    ``summarise_only`` (INTAKE-5a.1) is the human-asked "Summarise now" pass: the run
    exists to write an account of a thread that never got one. It gets
    ``record_intake_outcome`` and NOTHING ELSE — no reply tool is built, so the grant
    set is narrowed to match (R6 fails closed on a tool that is not in it), and the
    outcome it records leaves the thread's status exactly where it was.
    """
    granted = _SUMMARISE_TOOL_NAMES if summarise_only else INTAKE_TOOL_NAMES
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=granted,
        practice_area_id=binding.practice_area_id,
    )

    async def record_intake_outcome(
        outcome: str,
        label: str,
        note: str,
        matter_title: str,
        summary: list[dict[str, str]],
    ) -> str:
        """Conclude this intake thread — call this exactly once, last.

        `outcome` must be one of exactly two values:

        - "dealt_with" — nothing further is needed and nothing leaves the system
          (spam, marketing, an FYI, a notification, an automated message). The matter
          is CLOSED and filed with your label and note, so it does not clutter the
          lawyer's list. Use this ONLY when you are confident no lawyer needs to look.
        - "needs_human" — anything else: you prepared something, real work is
          starting, a decision or deadline is involved, or you are simply not sure.
          The matter stays OPEN and the thread waits for the supervising lawyer.
          This is the safe answer: when in doubt, choose it.

        `label` is a short tag of YOUR choosing for the lawyer's list ("NDA review",
        "renewal notice", "out of area — HR"). It is display only; nothing branches
        on it, and you are not picking from a fixed list.

        `note` is one short paragraph the lawyer reads at a glance: what this is,
        what you did, and what (if anything) you need from them.

        `matter_title` NAMES this matter. The matter was opened before anyone had
        read the email, so it is still called whatever the subject line said —
        which is often "RE: FW: quick question". Replace it with the essence of
        the matter in at most 80 characters, on one line, the way a lawyer would
        write it on a file: "Contoso hosting renewal — pricing before notice
        deadline", "Northwind MSA — indemnity cap open". No sender addresses, no
        "RE:"/"FW:", and do NOT repeat the matter reference — it is displayed
        beside the name already. The title usually settles after the first email;
        write it again only when the thread turns out to be about something
        different. If a human has renamed this matter, their name stands and
        yours is ignored — that is deliberate, not a failure.

        `summary` is THE THREAD SO FAR for someone who has never seen it: one to
        five bullets, each `{"title": "...", "text": "..."}`. The title is two or
        three words the lawyer's eye lands on ("What they want", "What we did",
        "Where it stands", "Open point", "Proposed next step") — at most 40
        characters; the text is one plain sentence under it — at most 300
        characters, one line, no line breaks. Rewrite ALL of it every time you
        conclude, describing the WHOLE chain including the latest message: it
        replaces the previous version outright, and the lawyer reads it instead of
        opening the emails. Put no email addresses in a title.
        """
        return await guarded_dispatch(
            "record_intake_outcome",
            lambda db: _record_intake_outcome(
                db,
                binding,
                run_id=run_id,
                intake_thread_id=intake_thread_id,
                outcome=outcome,
                label=label,
                note=note,
                matter_title=matter_title,
                summary=summary,
                summarise_only=summarise_only,
            ),
            ctx,
        )

    async def draft_email_reply(
        to: list[str],
        subject: str,
        body: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        attachment_file_ids: list[str] | None = None,
    ) -> str:
        """Propose a reply to this intake email. Nothing is sent until a lawyer approves.

        Use this when the right answer to the email is a reply: an answer to a
        question, an acknowledgement with what happens next, a request for the
        missing document, a handoff note for mail that belongs to another team.

        Write it as the company's legal team would write it: plain English, short,
        no legalese, no promises the lawyer has not made. `to` is the address(es)
        the reply should go to; `subject` is the reply's subject line; `body` is the
        full message text.

        This call ALWAYS stops for the supervising lawyer first. They read your
        draft and either approve it (optionally after editing your wording — what
        they approve is what goes out), or send it back with a note telling you what
        to change; when that happens, write a NEW draft with this tool that answers
        their note. Only after an approval is the reply delivered to the recipient,
        as a reply on the original email thread.

        `attachment_file_ids` is recorded but attachments CANNOT be delivered yet:
        call this with no attachment ids, and say in the body what the lawyer should
        attach if a document really has to travel with the reply.
        """
        # `tool_call_id` is INJECTED by langchain (InjectedToolCallId) — it is not in
        # the schema the model sees and the model cannot set it. It is the identity of
        # THIS ask: the HITL middleware rebuilds an edited call with the same id, and a
        # re-approval after a crash resumes the same checkpointed call, so it is the
        # only stable per-ask key there is (ADR-F087 double-send fix).
        return await guarded_dispatch(
            "draft_email_reply",
            lambda db: _draft_email_reply(
                db,
                binding,
                run_id=run_id,
                intake_thread_id=intake_thread_id,
                to=to,
                subject=subject,
                body=body,
                attachment_file_ids=attachment_file_ids or [],
                tool_call_id=tool_call_id,
                bridge=bridge,
            ),
            ctx,
        )

    if summarise_only:
        # Nothing this run does can reach a counterparty: the tool is not built, so
        # there is no interrupt to approve and no send path to reach.
        return [record_intake_outcome]
    return [record_intake_outcome, draft_email_reply]


async def load_intake_thread_for_run(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    agent_thread_id: uuid.UUID | None,
    run_id: uuid.UUID | None = None,
) -> IntakeThread | None:
    """The intake thread this RUN is working on, or ``None``.

    Under ADR-F086 Amendment A1 an intake-born matter is an ordinary matter: the
    lawyer opens it in the cockpit and chats about it like any other. Those chats run
    on their OWN agent conversation, so keying on the project alone (as the first cut
    did) would have let a cockpit turn be treated as the thread's intake run —
    arming the intake doctrine and tools, and letting a settled cockpit run flip a
    thread that is still processing (adversarial review S2/S5). The intake run is the
    one whose agent conversation IS the thread's ``agent_thread_id``; nothing else is.

    **ONE conversation now holds MANY intake threads** (INTAKE-4a, ADR-F088). The
    layer-2/3 resolver deliberately opens a NEW ``intake_threads`` row when a reply or
    a tagged mail arrives on a fresh provider thread, attaches it to the same matter,
    and gives it the SAME ``agent_thread_id`` so the conversation continues. "The
    thread on this conversation" therefore stopped being a single row, and the old
    ``scalar_one_or_none()`` here raised ``MultipleResultsFound`` — which killed the
    resume of the first live approval (three rows: one ``awaiting_human``, two still
    ``received``). A ``LIMIT 1`` would only have replaced a crash with a coin flip, so
    the run is bound to its thread EXPLICITLY, in four deterministic steps:

    0. **A human-asked summarise pass** (INTAKE-5a.1) names its thread on the row
       itself (``intake_threads.summarise_pass_run_id``): it claims no inbound
       message, so no later layer could find it.
    1. **This run's own work.** The worker stamps an inbound message's ``run_id`` at
       the moment it starts a run for it (``intake_worker``), so the message carrying
       this ``run_id`` names the thread the run was started for.
    1b. **The resume's parent chain** (INTAKE-5a.1 fix D, migration 0103). A resume is
       a NEW ``agent_runs`` row with no messages of its own, but it now records WHICH
       run it resumes (``agent_runs.resumed_from_run_id``, set by the resume endpoint;
       a resume of a resume chains, so the walk follows it up to
       :data:`_RESUME_CHAIN_MAX_HOPS`). The thread is then the one whose inbound
       message an ANCESTOR claimed — a fact, not an inference.

       This layer exists because layer 2 below got it WRONG in production, twice: on a
       conversation holding three intake threads, an approved reply on the paused
       thread bound to a SIBLING thread that had already replied, and the tool's
       delivered-row guard refused the send. The lawyer's approval was consumed and
       nothing went out.
    2. **The conversation's lineage — LEGACY heuristic, superseded by 1b.** The newest
       inbound processed by ANY run on this same agent conversation. It is right when
       the conversation holds ONE thread and a guess when it holds several, which is
       why it now runs only for runs that predate the parent link (no backfill).
    3. **The single working thread.** With nothing processed yet, take the one thread
       that is not still ``received``.

    Ambiguity beyond that is a bug, not a state to guess through: it logs an ERROR with
    counts and ids and returns ``None``, which fails CLOSED (no intake tools, no
    doctrine, no thread flipped) rather than acting on the wrong thread.
    """
    if agent_thread_id is None:
        return None
    candidates = await load_conversation_intake_threads(
        db, project_id=project_id, agent_thread_id=agent_thread_id
    )
    if run_id is not None:
        # Layer 0 (INTAKE-5a.1): a human-asked "Summarise now" pass names its thread
        # outright — it claims no inbound message, so nothing below could find it.
        for candidate in candidates:
            if candidate.summarise_pass_run_id == run_id:
                return candidate
    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    by_id = {thread.id: thread for thread in candidates}
    thread_ids = list(by_id)

    def _newest_processed(run_filter: Any) -> Any:
        return (
            select(IntakeMessage.thread_id)
            .where(
                IntakeMessage.thread_id.in_(thread_ids),
                IntakeMessage.direction == "in",
                run_filter,
            )
            .order_by(IntakeMessage.created_at.desc(), IntakeMessage.id.desc())
            .limit(1)
        )

    bound: uuid.UUID | None = None
    if run_id is not None:
        bound = (
            await db.execute(_newest_processed(IntakeMessage.run_id == run_id))
        ).scalar_one_or_none()
    if bound is None and run_id is not None:
        # Layer 1b: follow the resume's own parent link (fix D).
        ancestors = await _resume_ancestor_run_ids(db, run_id)
        if ancestors:
            bound = (
                await db.execute(_newest_processed(IntakeMessage.run_id.in_(ancestors)))
            ).scalar_one_or_none()
    if bound is None:
        bound = (
            await db.execute(
                _newest_processed(
                    IntakeMessage.run_id.in_(
                        select(AgentRun.id).where(AgentRun.thread_id == agent_thread_id)
                    )
                )
            )
        ).scalar_one_or_none()
    if bound is not None:
        return by_id[bound]

    working = [t for t in candidates if t.status not in _PENDING_THREAD_STATUSES]
    if len(working) == 1:
        return working[0]
    logger.error(
        "cannot bind this run to one intake thread on its conversation",
        extra={
            "event": "intake_thread_binding_ambiguous",
            "run_id": str(run_id) if run_id is not None else None,
            "agent_thread_id": str(agent_thread_id),
            "candidates": len(candidates),
            "working": len(working),
        },
    )
    return None


#: How far the resume chain is followed before the walk gives up (fix D). A human
#: approving, being sent back to, and re-approving a draft builds a chain one link at
#: a time; ten is far past any real sequence and makes a corrupted self-referential
#: link a bounded walk rather than a hang.
_RESUME_CHAIN_MAX_HOPS = 10


async def _resume_ancestor_run_ids(db: AsyncSession, run_id: uuid.UUID) -> list[uuid.UUID]:
    """The runs THIS run resumes, nearest ancestor first (INTAKE-5a.1 fix D).

    Empty for an ordinary run, for a historic resume written before migration 0103,
    and for a run row that is gone. ``db.get`` is a primary-key lookup served from the
    session's identity map when the caller already loaded the row (both callers do),
    so the common case costs no query at all.
    """
    ancestors: list[uuid.UUID] = []
    current = await db.get(AgentRun, run_id)
    for _ in range(_RESUME_CHAIN_MAX_HOPS):
        if current is None or current.resumed_from_run_id is None:
            break
        parent_id = current.resumed_from_run_id
        if parent_id in ancestors or parent_id == run_id:
            break  # a cycle is a bug, not a state to walk forever
        ancestors.append(parent_id)
        current = await db.get(AgentRun, parent_id)
    return ancestors


async def load_conversation_intake_threads(
    db: AsyncSession, *, project_id: uuid.UUID, agent_thread_id: uuid.UUID | None
) -> list[IntakeThread]:
    """EVERY intake thread on this agent conversation, oldest first (ADR-F088).

    The requeue-on-settle contract operates over all of them: a mail that arrives while
    a run is in flight lands on a SIBLING thread as often as on the one being worked,
    and settling that run is the moment the whole conversation is free again.
    """
    if agent_thread_id is None:
        return []
    return list(
        (
            await db.execute(
                select(IntakeThread)
                .where(
                    IntakeThread.project_id == project_id,
                    IntakeThread.agent_thread_id == agent_thread_id,
                )
                .order_by(IntakeThread.created_at.asc(), IntakeThread.id.asc())
            )
        )
        .scalars()
        .all()
    )


async def _load_bound_thread(
    db: AsyncSession, binding: MatterBinding, intake_thread_id: uuid.UUID
) -> IntakeThread | None:
    """The ONE intake thread this run was bound to, re-read in the tool's session.

    Matter-scoped as well as id-scoped: the id arrives from the composition root, but
    a tool never trusts an identifier it did not re-check against this run's matter
    (the same posture as every other matter-scoped read here).
    """
    return (
        await db.execute(
            select(IntakeThread).where(
                IntakeThread.id == intake_thread_id,
                IntakeThread.project_id == binding.project_id,
            )
        )
    ).scalar_one_or_none()


async def _record_intake_outcome(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    run_id: uuid.UUID,
    intake_thread_id: uuid.UUID,
    outcome: str,
    label: str,
    note: str,
    matter_title: str,
    summary: list[dict[str, str]],
    summarise_only: bool = False,
) -> str:
    """Validate → write the outcome + summary onto the thread → apply the project effect.

    ``summarise_only`` (INTAKE-5a.1) is the human-asked backfill pass. It writes the
    ACCOUNT of the thread — outcome, label, note, title, summary — and touches nothing
    else: the thread's status and the matter's open/closed state are facts a real run
    established, and a pass whose only purpose is to describe them must not restate
    them as decisions. Concretely, it can never downgrade a ``replied`` or ``handled``
    thread back to ``awaiting_human``, and it can never re-open (or close) the matter.
    """
    try:
        proposal = RecordIntakeOutcomeInput(
            outcome=outcome,  # type: ignore[arg-type]  # Pydantic validates the closed set
            label=label,
            note=note,
            matter_title=matter_title,
            summary=summary,  # type: ignore[arg-type]  # Pydantic validates the item shape
        )
    except ValidationError as exc:
        return _rejection_text(exc, tool="record_intake_outcome")

    thread = await _load_bound_thread(db, binding, intake_thread_id)
    if thread is None:
        # Not an intake run after all (or the thread was deleted underneath us).
        return (
            "This matter is not an intake thread, so there is no intake outcome to "
            "record. Nothing was recorded."
        )

    if thread.outcome is not None:
        # Idempotent: last write wins, but a second conclusion in one run is worth
        # knowing about (IDs only — never the label or the note).
        logger.info(
            "record_intake_outcome called again in the same run; overwriting",
            extra={
                "event": "intake_outcome_overwritten",
                "thread_id": str(thread.id),
                "previous_outcome": thread.outcome,
                "outcome": proposal.outcome,
            },
        )

    prior_outcome = thread.outcome
    thread.outcome = proposal.outcome
    thread.label = proposal.label
    thread.outcome_note = proposal.note
    # INTAKE-5a (ADR-F086 ruling 7): a FULL REWRITE, every call. The summary is
    # "the thread so far", not an append-only log, so merging an old list with a
    # new one would produce an account of the thread that no run ever wrote. The
    # safe-fail path (``safe_fail_intake_thread``) deliberately leaves whatever is
    # here in place and the read API flags it stale instead.
    thread.summary = [item.model_dump() for item in proposal.summary]
    thread.summary_run_id = run_id
    # INTAKE-4b (ADR-F087): a SEND already settled this thread — `replied` (a letter
    # went to the counterparty) or `error` (one was approved and did not go). Both are
    # later, stronger facts than the outcome's bookkeeping, and `error` is the only
    # place a failed delivery is visible to the lawyer, so the outcome records itself
    # WITHOUT touching the status. The doctrine asks for the outcome first, so this is
    # the out-of-order case, not the normal one.
    if summarise_only:
        # The lawyer asked for an account of a settled thread, not for a new decision
        # about it. Leaving the status alone is what makes `replied`/`handled` sticky
        # here — there is no "stronger status" comparison to get wrong.
        status_note = f"the thread stays {thread.status}"
    else:
        if thread.status not in _SEND_TERMINAL_THREAD_STATUSES:
            thread.status = _OUTCOME_THREAD_STATUS[proposal.outcome]
        status_note = f"the thread is now {thread.status}"

    # ONE owner-scoped load for every matter-side effect below (the name, the close,
    # the re-open) — the same row, in the same transaction, read once.
    project = (
        await db.execute(
            select(Project).where(
                Project.id == binding.project_id, Project.owner_id == binding.user_id
            )
        )
    ).scalar_one_or_none()

    # INTAKE-5a.1 (maintainer UAT ruling, migration 0103): the matter's NAME is the
    # agent's summary of what this thread IS, not the subject line the eager row was
    # opened with. Two fences, both structural:
    #
    # * ``intake_state == 'candidate'`` — only an intake-BORN matter is renamed. A
    #   thread later attached to an ordinary matter (INTAKE-5b) must never rename
    #   the lawyer's own file.
    # * ``name_source != 'human'`` — a person's name is final. This is ADR-F042's
    #   auto-write-then-correct in its simplest form: the agent writes, the human
    #   corrects, and the correction is permanent (pins win).
    if (
        project is not None
        and project.intake_state == "candidate"
        and project.name_source != "human"
        and project.name != proposal.matter_title
    ):
        project.name = proposal.matter_title
        project.name_source = "agent"

    if summarise_only:
        return (
            f"Summary recorded for this thread ({proposal.outcome}, label: "
            f"{proposal.label}). Nothing else changed: {status_note} and the matter's "
            "state is exactly as the earlier run left it."
        )

    project_note = "the matter stays open for the lawyer"
    # Last-wins must win WHOLE (adversarial review B4): an earlier dealt_with in this
    # same run closed the matter, so changing our mind has to re-open it or the thread
    # says "open" while the matter is archived. Scoped to undoing OUR OWN close — a
    # matter the human archived was never given a dealt_with outcome, so this branch
    # cannot reach it.
    if proposal.outcome != "dealt_with" and prior_outcome == "dealt_with" and project is not None:
        project.archived_at = None
    if proposal.outcome == "dealt_with":
        # Close the matter: the SAME soft archive DELETE /projects/{id} performs
        # (archived_at), and nothing else — ``intake_state`` is provenance, never a
        # lifecycle the agent drives (ADR-F086 Amendment A1). Archiving is also the
        # memory fence: a closed matter composes no binding on a later run.
        if project is not None and project.archived_at is None:
            project.archived_at = datetime.now(tz=UTC)
        project_note = "the matter is closed and filed away"

    return (
        f"Intake outcome recorded: {proposal.outcome} (label: {proposal.label}). "
        f"{status_note[0].upper()}{status_note[1:]} and {project_note}. "
        "This thread stays visible to the lawyer with your label and note."
    )


async def _draft_email_reply(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    run_id: uuid.UUID,
    intake_thread_id: uuid.UUID,
    to: list[str],
    subject: str,
    body: str,
    attachment_file_ids: list[str],
    tool_call_id: str,
    bridge: BridgeClient | None = None,
) -> str:
    """Validate → record the outbound row → SEND it (INTAKE-4b, ADR-F087).

    This body runs only AFTER a human approved (or edited) the call — the tool is
    interrupt-gated unconditionally (``hitl.ALWAYS_INTERRUPT_TOOL_NAMES``), so
    "the tool executed" and "a lawyer said yes to these exact bytes" are the same
    event. That is why the send lives here and not behind a second endpoint.

    Order matters: the row is inserted and COMMITTED before the bridge is called,
    so a crash mid-send leaves a record of what we tried rather than a delivered
    email nobody has. Exactly one attempt is ever made — no retries (ADR-F087).

    **Re-execution is the hazard this function is shaped around.** A worker killed
    (or wall-clock cancelled) between a successful send and the checkpoint write
    settles the run ``failed``; a failed successor does not supersede the pause
    (``agent_runs.py`` — deliberately, so a resume that never consumed the interrupt
    stays re-approvable), so the card is still live and Approve can run this body a
    SECOND time on the same checkpointed call. Three things make that safe, and none
    of them is a retry:

    * the idempotency key is derived from the CHECKPOINTED tool-call id
      (:func:`_send_key`), not from a freshly minted row id, so the second attempt
      presents the key the first one used and the bridge (and the provider) refuse it;
    * the outbound row is keyed by that same value while it is a draft, so a second
      execution REUSES it instead of inserting a twin;
    * and a delivered outbound row newer than the newest inbound short-circuits the
      whole thing before the bridge is touched at all.
    """
    try:
        proposal = DraftEmailReplyInput(
            to=to,
            subject=subject,
            body=body,
            attachment_file_ids=attachment_file_ids,  # type: ignore[arg-type]  # str → UUID
        )
    except ValidationError as exc:
        return _rejection_text(exc, tool="draft_email_reply")

    if proposal.attachment_file_ids:
        # INTAKE-4b: the send carries text only. Recording "3 attachments" on a
        # reply that goes out without them would make the row lie about what the
        # counterparty received, so this is refused BEFORE anything is written —
        # the model redrafts without them (and the docstring tells it not to try).
        return (
            "Attachments cannot be delivered yet, so nothing was sent. Call "
            "draft_email_reply again with no attachment_file_ids — say in the body "
            "what the lawyer should attach if a document has to travel with the reply."
        )

    thread = await _load_bound_thread(db, binding, intake_thread_id)
    if thread is None:
        return (
            "This matter is not an intake thread, so there is no email to reply to. "
            "Nothing was drafted."
        )

    # ADR-F088: the matter reference stamps the subject we record and becomes the
    # Reply-To plus-tag the bridge composes, so a reply to this reply comes home.
    # NULL only for a matter that predates the reference (or a sandbox) — the send
    # still happens, unstamped, rather than failing on a cosmetic.
    reference = (
        await db.execute(
            select(Project.reference).where(
                Project.id == binding.project_id, Project.owner_id == binding.user_id
            )
        )
    ).scalar_one_or_none()
    stamped_subject = tag_subject(proposal.subject, reference) if reference else proposal.subject

    # The message we are replying TO. The bridge is reply-only by construction (it
    # derives the recipients from THIS message), which is exactly why no address of
    # ours ever reaches it — and exactly why picking the right one matters. Prefer
    # the newest inbound the agent has actually processed (``run_id`` set): a pause
    # can last days, and a follow-up that landed meanwhile is unread text the lawyer
    # never saw and whose sender they never approved replying to. Fall back to the
    # newest inbound only when the thread has none processed at all.
    reply_to_message_id = (
        await db.execute(
            select(IntakeMessage.provider_message_id)
            .where(
                IntakeMessage.thread_id == thread.id,
                IntakeMessage.direction == "in",
                IntakeMessage.run_id.is_not(None),
            )
            .order_by(IntakeMessage.created_at.desc(), IntakeMessage.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    newest_inbound = (
        await db.execute(
            select(IntakeMessage.provider_message_id, IntakeMessage.created_at)
            .where(IntakeMessage.thread_id == thread.id, IntakeMessage.direction == "in")
            .order_by(IntakeMessage.created_at.desc(), IntakeMessage.id.desc())
            .limit(1)
        )
    ).first()
    if reply_to_message_id is None and newest_inbound is not None:
        reply_to_message_id = newest_inbound[0]

    # Guard 1 (ADR-F087): has a reply ALREADY gone out since the newest inbound? Then
    # this execution is a repeat — a re-approved card after a crash, or a second draft
    # nobody asked for — and the counterparty must not receive a second letter. Answer
    # from the DB; the bridge is never touched.
    delivered_since = (
        await db.execute(
            select(IntakeMessage.id)
            .where(
                IntakeMessage.thread_id == thread.id,
                IntakeMessage.direction == "out",
                IntakeMessage.send_error.is_(None),
                IntakeMessage.provider_message_id.not_like(f"{_DRAFT_ID_PREFIX}%"),
                *(
                    [IntakeMessage.created_at >= newest_inbound[1]]
                    if newest_inbound is not None
                    else []
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if delivered_since is not None:
        return (
            "A reply has already been sent on this email thread since the last message "
            "came in, so nothing was sent again. Do not draft another reply unless a "
            "new message arrives; tell the lawyer the reply already went out."
        )

    # Guard 2: the row for THIS ask. Keyed by the checkpointed tool-call id, so a
    # second execution of the same call updates the row it already made instead of
    # inserting a twin (and presents the same idempotency key below).
    send_key = _send_key(thread.id, tool_call_id)
    draft_id = f"{_DRAFT_ID_PREFIX}{send_key}"
    outbound = (
        await db.execute(
            select(IntakeMessage).where(
                IntakeMessage.thread_id == thread.id,
                IntakeMessage.provider_message_id == draft_id,
            )
        )
    ).scalar_one_or_none()
    if outbound is None:
        outbound = IntakeMessage(
            thread_id=thread.id,
            # A local, clearly-marked placeholder until the provider assigns the real
            # id (the unique key (thread_id, provider_message_id) needs a value). On a
            # successful send it is REPLACED by the provider's id — the one an inbound
            # References header will name, which is what layer 2 matches on (ADR-F088).
            provider_message_id=draft_id,
            direction="out",
            attachment_filenames=[],
        )
        db.add(outbound)
    outbound.run_id = run_id
    # What the agent said it was answering, recorded for the matter file. It is
    # NOT what addresses the send: the bridge derives the recipients from the
    # message being replied to and is never handed an address (ADR-F086), which
    # is also why `to` is not one of the human-editable fields (ADR-F087).
    outbound.to_addrs = list(proposal.to)
    outbound.subject = stamped_subject
    outbound.body_text = proposal.body
    outbound.send_error = None
    await db.flush()
    # Durable BEFORE the network call: a process that dies mid-send must leave the
    # attempt visible (the R7 safe-fail hook then parks the thread for the lawyer).
    await db.commit()

    failure: str | None = None
    if bridge is None:
        failure = "not_configured"
    elif reply_to_message_id is None:
        failure = "no_inbound_message"
    else:
        try:
            sent = await bridge.send_reply(
                reply_to_provider_message_id=reply_to_message_id,
                # Derived from the CHECKPOINTED tool-call id, never from this row's
                # freshly minted id: a re-execution of the same ask must present the
                # SAME key so the bridge and the provider can refuse it (ADR-F087).
                idempotency_key=send_key,
                text=proposal.body,
                reply_to_tag=reference,
            )
        except BridgeSendError as exc:
            failure = exc.reason
        else:
            outbound.provider_message_id = sent.provider_message_id
            thread.status = "replied"
            if sent.provider_thread_id != thread.provider_thread_id:
                # Never fatal, never a second source of truth: the reply belongs to
                # the thread we replied into, and a disagreement is worth seeing.
                logger.warning(
                    "sent reply landed on a different provider thread than expected",
                    extra={
                        "event": "intake_reply_thread_mismatch",
                        "thread_id": str(thread.id),
                        "run_id": str(run_id),
                    },
                )
            logger.info(
                "intake reply sent",
                extra={
                    "event": "intake_reply_sent",
                    "thread_id": str(thread.id),
                    "message_id": str(outbound.id),
                    "run_id": str(run_id),
                    "stamped": reference is not None,
                },
            )
            # Commit HERE, not at the dispatch boundary: guarded_dispatch's audit
            # helper rolls the session back if the audit write fails, and that would
            # discard the provider id of an email that has ALREADY been delivered —
            # taking layer-2 threading (ADR-F088) down with it.
            await db.commit()
            return (
                "Sent. The lawyer's approved reply has gone out on this email thread"
                + (f" stamped {reference}" if reference else "")
                + ", and it is recorded on the matter. Tell the lawyer plainly that "
                "the reply was sent, and conclude with record_intake_outcome if you "
                "have not already."
            )

    outbound.send_error = failure
    thread.status = "error"
    logger.warning(
        "intake reply was approved but not sent",
        extra={
            "event": "intake_reply_send_failed",
            "thread_id": str(thread.id),
            "message_id": str(outbound.id),
            "run_id": str(run_id),
            "reason": failure,
        },
    )
    # Same reason as the success path: the failure record must survive an audit-write
    # rollback, or the thread reports `processing` with no explanation.
    await db.commit()
    return (
        # Deliberately NOT "nothing left the building": a timeout or a duplicate-key
        # refusal cannot prove that. Treat delivery as unconfirmed and hand it to the
        # human, who can look in the mailbox — that is the only honest claim here.
        f"NOT DELIVERED — the send failed ({failure}) and was NOT retried, so assume "
        "the reply did not go out and say so; only the mailbox can confirm otherwise. "
        "The lawyer's approved text is saved on this matter. Record the outcome as "
        "needs_human with a note saying the reply is written but was not delivered, so "
        "the lawyer can check and send it themselves."
    )


async def safe_fail_intake_thread(
    session_factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID
) -> bool:
    """R7 — a settled intake run that recorded NO outcome leaves the thread waiting.

    Called once at the run job's exit for EVERY run (no-op for the overwhelming
    majority — a run with no intake thread returns immediately). Without it a run
    that failed, was cancelled, capped, or paused for HITL without concluding would
    leave its thread stuck at ``processing`` forever, invisible in the lawyer's
    "waiting for me" list. The note is a FIXED fork-authored string — never model
    text, never an exception message.

    ``summary`` is deliberately LEFT ALONE (INTAKE-5a): a run that did not conclude
    has no account of the thread to offer, and blanking the previous run's would
    replace something true-as-of-last-time with nothing. The read API compares
    ``summary_run_id`` against the newest settled run instead and shows the reader
    "the agent's last run did not finish", which is the honest form of the same fact.

    Returns whether it changed anything. Never raises: it must not mask the run's
    own outcome (the caller invokes it from a ``finally``).
    """
    try:
        async with session_factory() as db:
            run = await db.get(AgentRun, run_id)
            if run is None or run.project_id is None or run.status == "running":
                return False
            # S5: only the thread's OWN intake run may park it — a lawyer's cockpit
            # run on the same matter must never flip a thread that is still processing.
            thread = await load_intake_thread_for_run(
                db,
                project_id=run.project_id,
                agent_thread_id=run.thread_id,
                run_id=run_id,
            )
            if thread is None or thread.status != "processing":
                return False
            thread.status = "awaiting_human"
            if thread.outcome_note is None:
                thread.outcome_note = NO_OUTCOME_NOTE
            await db.commit()
            logger.info(
                "intake thread left waiting: run settled without an outcome",
                extra={
                    "event": "intake_thread_safe_failed",
                    "thread_id": str(thread.id),
                    "run_id": str(run_id),
                    "run_status": run.status,
                },
            )
            return True
    except Exception:
        logger.exception(
            "intake safe-fail hook failed (the run's own settle stands)",
            extra={"event": "intake_safe_fail_error", "run_id": str(run_id)},
        )
        return False


async def requeue_pending_intake_message(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    *,
    enqueue: Callable[[uuid.UUID, str], Awaitable[bool]] | None = None,
) -> bool:
    """B3 — hand the CONVERSATION's next unprocessed message back to the queue.

    A follow-up that landed while a run was in flight is deliberately left unclaimed
    by :func:`app.workers.intake_worker.process_intake_thread` (it returns
    ``deferred`` rather than forking the conversation). Nothing else would ever
    re-enqueue it: the only other producer is the landing endpoint, and its arq job id
    is keyed per MESSAGE, so the deferred message had already burned its enqueue. The
    result was a silently orphaned email (adversarial review B3). Settling the
    in-flight run is exactly the moment the thread is free again, so the run job's
    exit re-enqueues here.

    Called once per settled run, right after the safe-fail hook; a no-op for every
    non-intake run and for a conversation with nothing pending on any of its threads. Never raises — it must not
    mask the run's own outcome.
    """
    if enqueue is None:

        async def enqueue(thread_id: uuid.UUID, provider_message_id: str) -> bool:
            from app.workers.queue import enqueue_intake_email_job

            return await enqueue_intake_email_job(
                thread_id, provider_message_id=provider_message_id
            )

    try:
        async with session_factory() as db:
            run = await db.get(AgentRun, run_id)
            if run is None or run.project_id is None or run.status == "running":
                return False
            # ADR-F088: EVERY intake thread on this conversation, not just the one
            # this run worked. A mail that arrives mid-run is attached by the layer-2/3
            # resolver as a SIBLING thread and deferred there; settling this run is the
            # moment the whole conversation is free, so the oldest pending inbound
            # ACROSS the siblings is the one to hand back.
            threads = await load_conversation_intake_threads(
                db, project_id=run.project_id, agent_thread_id=run.thread_id
            )
            if not threads:
                return False
            pending = (
                await db.execute(
                    select(IntakeMessage)
                    .where(
                        IntakeMessage.thread_id.in_([t.id for t in threads]),
                        IntakeMessage.direction == "in",
                        IntakeMessage.run_id.is_(None),
                    )
                    .order_by(IntakeMessage.created_at.asc(), IntakeMessage.id.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if pending is None:
                return False
            thread_id, provider_message_id = pending.thread_id, pending.provider_message_id
        queued = await enqueue(thread_id, provider_message_id)
        if not queued:
            # A refused enqueue means this message is STILL pending and nothing
            # will pick it up: the landing endpoint already burned its own
            # enqueue, and this hook is the only other producer. That is an
            # orphaned email, so it is a WARNING with ids — never an info line
            # with `queued: false` buried in it (ADR-F087, found live).
            logger.warning(
                "intake re-enqueue was refused; the deferred message is still waiting",
                extra={
                    "event": "intake_requeue_refused",
                    "thread_id": str(thread_id),
                    "run_id": str(run_id),
                },
            )
            return False
        logger.info(
            "intake thread has a deferred message; re-enqueued after the run settled",
            extra={
                "event": "intake_deferred_message_requeued",
                "thread_id": str(thread_id),
                "run_id": str(run_id),
            },
        )
        return True
    except Exception:
        logger.exception(
            "intake re-enqueue hook failed (the message stays pending for a later run)",
            extra={"event": "intake_requeue_error", "run_id": str(run_id)},
        )
        return False


def _rejection_text(exc: ValidationError, *, tool: str) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no value echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(input)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        f"Rejected — nothing was recorded. Fix the following and call {tool} again:\n"
        + "\n".join(problems)
    )


__all__ = [
    "INTAKE_TOOL_NAMES",
    "NO_OUTCOME_NOTE",
    "build_intake_tools",
    "load_conversation_intake_threads",
    "load_intake_thread_for_run",
    "requeue_pending_intake_message",
    "safe_fail_intake_thread",
]
