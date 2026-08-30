"""Provider-agnostic inbound-email envelope + intake response shapes — INTAKE-1 (ADR-F086).

The mail-bridge (a future, separate microservice — INTAKE-2) is the ONLY
holder of mailbox credentials; it normalizes whatever a provider (AgentMail
in v1) sends into this envelope and POSTs it to
``POST /api/v1/internal/intake/emails``. Email content is untrusted model
input (CLAUDE.md; ADR-F086 security posture #1): every field here is
boundary-validated and REJECTED (422) rather than sanitized when it
exceeds its bound — an oversized or malformed envelope never reaches the
DB or an agent prompt.

Boundary bounds enforced here (ADR-F086 security posture + the INTAKE-1
slice spec):

* at most 10 attachments per message, each capped at 25 MB decoded, AND
  the SUM of every attachment's decoded size capped at 50 MB per envelope
  (a request with several attachments each just under the per-item cap
  could otherwise add up to hundreds of MB);
* the message body text capped at 512k chars; ``to``/``cc`` entries capped
  at 320 chars each (RFC 5321) and 50 entries per list;
* ``headers`` is filtered to a small allowlist (loop/authenticity signals
  only — ``Auto-Submitted``, ``Precedence``, ``In-Reply-To``,
  ``References``) rather than carried through as an arbitrary untrusted
  dict; every other header the bridge might forward is silently dropped
  (not "sanitized" — simply outside the accepted shape);
* NUL (``\\x00``) bytes are rejected (422), never stripped, in every
  free-text field that lands in a Postgres TEXT column or gets logged —
  asyncpg raises a client-side ``ValueError`` writing an embedded NUL,
  which without this boundary check would surface as an unhandled 500 deep
  inside a later INSERT instead of a clean 422 here.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    StringConstraints,
    field_validator,
    model_validator,
)

AuthState = Literal["pass", "fail", "unknown"]

# Boundary caps (ADR-F086 security posture; INTAKE-1 slice spec).
MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_DECODED_BYTES = 25 * 1024 * 1024  # 25 MB decoded, per attachment
MAX_AGGREGATE_ATTACHMENT_DECODED_BYTES = 50 * 1024 * 1024  # 50 MB decoded, whole envelope
MAX_BODY_TEXT_CHARS = 512_000
_ADDR_MAX_CHARS = 320  # RFC 5321 4.5.3.1.3 maximum reverse-path/forward-path length
# Encoded-length ceiling on content_b64 BEFORE we even attempt to decode —
# base64 inflates by ~4/3; this is a generous outer bound (cheap length
# check) ahead of the exact decoded-byte check in _decode_and_bound below.
_MAX_ATTACHMENT_B64_CHARS = (MAX_ATTACHMENT_DECODED_BYTES * 4 // 3) + 1024

# Only these headers carry loop-prevention / sender-authenticity signal
# (ADR-F086 security posture #2/#3). Everything else the bridge forwards is
# dropped at this boundary — the doctrine (INTAKE-3) never sees, and the
# agent prompt never fences, header names/values outside this set.
ALLOWED_HEADER_KEYS = frozenset({"Auto-Submitted", "Precedence", "In-Reply-To", "References"})
_HEADER_VALUE_MAX_CHARS = 500
# INTAKE-4a (ADR-F088): ``References`` is the ONE header that grows without bound
# — every hop appends the message it answered — and it is the one the layer-2
# resolver reads. At 500 chars a thread of ~8 exchanges already overflows, and
# because senders APPEND, a head-first trim throws away the newest ids, i.e.
# exactly the ones most likely to be ours. So this header gets its own, larger
# cap (matching the ``intake_messages.references_header`` CHECK and
# ``stamping.MAX_PARSED_HEADER_CHARS``) and is trimmed from the HEAD, keeping the
# tail. A trim can bisect the oldest ``<id>`` token; the parser requires both
# angle brackets, so a bisected token is simply not a token.
_REFERENCES_VALUE_MAX_CHARS = 2_000
_TAIL_TRUNCATED_HEADERS = frozenset({"References"})


def _reject_nul_bytes(value: str) -> str:
    """Reject (never strip) an embedded NUL byte — "reject, don't sanitize".

    Postgres TEXT columns cannot store ``\\x00``; asyncpg raises a
    client-side ``ValueError`` the moment such a value is bound to a query,
    which would otherwise surface as an unhandled 500 on whichever INSERT
    happens to be the first to touch the offending field.
    """

    if "\x00" in value:
        raise ValueError("must not contain NUL (\\x00) bytes")
    return value


#: Bidirectional formatting characters (INTAKE-5a.1, N9). They are not "control
#: characters" by Unicode's category, but they do the same job on a rendered line:
#: LRE/RLE/PDF/LRO/RLO (U+202A-U+202E) and the isolates LRI/RLI/FSI/PDI
#: (U+2066-U+2069) re-order the glyphs AROUND them, so a bullet can display text in
#: an order the stored string does not have ("Trojan Source" applied to a summary the
#: lawyer acts on). A one-line plain-text summary never needs one.
_BIDI_CONTROLS = frozenset(range(0x202A, 0x202F)) | frozenset(range(0x2066, 0x206A))


def _reject_control_chars(value: str) -> str:
    """Reject (never strip) ANY control or bidi-formatting character — ADR-F086.

    Stricter than :func:`_reject_nul_bytes`, and deliberately so: this guards the
    agent-written ``intake_threads.summary`` bullets and matter title, which are
    model text ABOUT untrusted mail rendered straight into the lawyer's Inbox (and,
    for the title, into the matter list). Such a value is one short plain-text line,
    so a newline, a tab, an ANSI escape, a line/paragraph separator or a bidi
    override is never legitimate content — it is someone trying to make the rendered
    line read as something it is not. C0 (``\x00``-``\x1f``), DEL, C1
    (``\x80``-``\x9f``), U+2028/U+2029 and :data:`_BIDI_CONTROLS` are all refused;
    the model is told which character class it must fix and retries.
    """

    for ch in value:
        code = ord(ch)
        if (
            code < 0x20
            or code == 0x7F
            or 0x80 <= code <= 0x9F
            or code in (0x2028, 0x2029)
            or code in _BIDI_CONTROLS
        ):
            raise ValueError("must not contain control characters or line breaks")
    return value


# A free-text field that must never carry an embedded NUL byte. Stacks with
# whatever length/emptiness Field(...) constraints the field itself adds.
_NulFreeStr = Annotated[str, AfterValidator(_reject_nul_bytes)]
# A single line of plain text — no NULs, no control characters at all.
_PlainLineStr = Annotated[str, AfterValidator(_reject_control_chars)]
_NulFreeAddr = Annotated[
    str, StringConstraints(max_length=_ADDR_MAX_CHARS), AfterValidator(_reject_nul_bytes)
]


class InboundEmailThread(BaseModel):
    """The provider-thread identity a message belongs to."""

    model_config = ConfigDict(extra="forbid")

    provider_thread_id: str = Field(..., min_length=1, max_length=500)
    # Empty subject lines are real email traffic, not an error — the
    # intake router derives a fallback candidate-matter name for them.
    subject: _NulFreeStr = Field(default="", max_length=998)


class InboundEmailAttachment(BaseModel):
    """One base64-encoded attachment on an inbound message.

    ``content_b64`` is decoded exactly ONCE, in :meth:`_decode_and_bound`
    below — the result is cached on a private attribute and exposed via
    :attr:`decoded_bytes` so callers (the ingest flow) never pay for a
    second decode.
    """

    model_config = ConfigDict(extra="forbid")

    filename: _NulFreeStr = Field(..., min_length=1, max_length=500)
    content_type: str = Field(default="application/octet-stream", max_length=200)
    content_b64: str = Field(..., min_length=1, max_length=_MAX_ATTACHMENT_B64_CHARS)

    _decoded: bytes = PrivateAttr(default=b"")

    @model_validator(mode="after")
    def _decode_and_bound(self) -> InboundEmailAttachment:
        try:
            decoded = base64.b64decode(self.content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                f"attachment {self.filename!r}: content_b64 is not valid base64"
            ) from exc
        if len(decoded) > MAX_ATTACHMENT_DECODED_BYTES:
            raise ValueError(
                f"attachment {self.filename!r} exceeds the "
                f"{MAX_ATTACHMENT_DECODED_BYTES} byte decoded limit"
            )
        self._decoded = decoded
        return self

    @property
    def decoded_bytes(self) -> bytes:
        """The base64-decoded attachment bytes (decoded once, at validation time)."""

        return self._decoded


class InboundEmailMessage(BaseModel):
    """The single inbound message this envelope carries."""

    model_config = ConfigDict(extra="forbid")

    provider_message_id: str = Field(..., min_length=1, max_length=500)
    from_addr: _NulFreeStr = Field(..., min_length=1, max_length=_ADDR_MAX_CHARS)
    to: list[_NulFreeAddr] = Field(default_factory=list, max_length=50)
    cc: list[_NulFreeAddr] = Field(default_factory=list, max_length=50)
    # Provider-claimed send time. Validated (a malformed value 422s) but NOT
    # trusted for the DB's `last_inbound_at` — the intake router stamps that
    # from the server's own clock (one clock source; defense against a
    # forged/skewed provider timestamp).
    timestamp: datetime
    text: _NulFreeStr = Field(default="", max_length=MAX_BODY_TEXT_CHARS)
    headers: dict[str, str] = Field(default_factory=dict)
    auth_state: AuthState = "unknown"
    attachments: list[InboundEmailAttachment] = Field(
        default_factory=list, max_length=MAX_ATTACHMENTS
    )

    @field_validator("headers", mode="before")
    @classmethod
    def _bound_headers(cls, value: object) -> dict[str, str]:
        """Filter to the allowlisted header keys; cap each value's length;
        reject (never strip) an embedded NUL in a value that survives the
        filter.

        The filtering itself is NOT a rejection boundary (unlike
        attachments/text) — the bridge may legitimately forward a broader
        header set than we act on; we simply never carry more than the
        allowlisted subset past this point. A NUL byte inside an
        allowlisted value IS rejected, same as every other free-text field.
        """

        if not isinstance(value, dict):
            return {}
        filtered: dict[str, str] = {}
        for k, v in value.items():
            if k not in ALLOWED_HEADER_KEYS:
                continue
            raw = str(v)
            if k in _TAIL_TRUNCATED_HEADERS:
                # Keep the NEWEST ids (senders append), not the oldest.
                text = raw[-_REFERENCES_VALUE_MAX_CHARS:]
            else:
                text = raw[:_HEADER_VALUE_MAX_CHARS]
            if "\x00" in text:
                raise ValueError(f"header {k!r} value must not contain NUL (\\x00) bytes")
            filtered[str(k)] = text
        return filtered

    @model_validator(mode="after")
    def _bound_aggregate_attachment_bytes(self) -> InboundEmailMessage:
        """Reject when the SUM of every attachment's decoded size exceeds
        the aggregate cap — the per-attachment 25 MB cap alone still admits
        a request whose several attachments add up to hundreds of MB."""

        total = sum(len(a.decoded_bytes) for a in self.attachments)
        if total > MAX_AGGREGATE_ATTACHMENT_DECODED_BYTES:
            raise ValueError(
                "attachments exceed the "
                f"{MAX_AGGREGATE_ATTACHMENT_DECODED_BYTES} byte aggregate decoded limit "
                f"(got {total})"
            )
        return self


class InboundEmailEnvelope(BaseModel):
    """The full provider-agnostic envelope POSTed by the mail-bridge."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1, max_length=50)
    inbox_id: str = Field(..., min_length=1, max_length=500)
    thread: InboundEmailThread
    message: InboundEmailMessage


# ---------------------------------------------------------------------------
# Response shapes — counts/IDs only, never email content (ADR-F086 posture).
# ---------------------------------------------------------------------------


class IntakeEmailIngestResponse(BaseModel):
    """Response for ``POST /internal/intake/emails`` — counts/IDs only.

    Never echoes subject, body text, sender, or attachment content —
    matching the audit-contract posture elsewhere in this codebase (counts/
    types/IDs, never raw values).
    """

    duplicate: bool
    thread_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    files_ingested: int = 0


# ---------------------------------------------------------------------------
# INTAKE-3 (ADR-F086) — the agent's intake tool-call boundaries.
#
# Code-validated writes (ADR-F018 shape): the model PROPOSES, code DISPOSES
# against these schemas BEFORE anything is written; a failure is rejected back
# to the model with the reason (reject, never truncate/sanitize). Only A-class
# content args appear here — run_id / project_id / thread are B-class and set
# by the tool from the run's binding, never model-visible.
# ---------------------------------------------------------------------------

# The closed outcome vocabulary (ADR-F086: "the run concludes via a tool call with
# a closed outcome field — never free prose"). Mirrors app.models.intake._THREAD_OUTCOMES
# and the migration-0099 CHECK; keep the three in sync. TWO values only (ADR-F086
# Amendment A1): every intake thread IS a matter, so "keep it as a candidate" is not a
# decision anyone makes — the thread either needed nothing (``dealt_with``, matter
# closed) or it needs the lawyer (``needs_human``, matter stays open).
IntakeOutcome = Literal["dealt_with", "needs_human"]

INTAKE_LABEL_MAX_CHARS = 200
INTAKE_NOTE_MAX_CHARS = 2_000
DRAFT_REPLY_SUBJECT_MAX_CHARS = 998  # RFC 5322 line limit, as for a thread subject
DRAFT_REPLY_BODY_MAX_CHARS = 50_000
DRAFT_REPLY_MAX_RECIPIENTS = 20
DRAFT_REPLY_MAX_ATTACHMENTS = 10

# INTAKE-5a (ADR-F086, plan ruling 7): the thread summary's shape. Small on
# purpose — the point of the Inbox is that a fresh reader takes in the whole
# thread at a glance, so five short bullets is the budget, not a target.
# INTAKE-5a.1 (maintainer UAT ruling): the matter's NAME, written by the agent —
# the essence of the thread ("Contoso hosting renewal — pricing before notice
# deadline"), not the email subject the eager row was opened with. 80 chars is a
# name, not a sentence, and it sits under the 200-char ``projects.name`` CHECK
# with room to spare. Single-line plain text, same rejection as a summary title:
# it renders beside the matter reference in the Inbox, the cockpit and the agent's
# own prompt, so a line break or a bidi override there would forge a second line.
INTAKE_MATTER_TITLE_MAX_CHARS = 80

INTAKE_SUMMARY_MAX_ITEMS = 5
INTAKE_SUMMARY_TITLE_MAX_CHARS = 40
INTAKE_SUMMARY_TEXT_MAX_CHARS = 300


class IntakeSummaryItem(BaseModel):
    """One bullet of the agent's account of an intake thread (ADR-F086, ruling 7).

    ``title`` is the two-or-three-word lead the UI renders in bold ("What they
    want", "Where it stands"); ``text`` is the sentence under it. Both are plain
    single-line text: control characters and line breaks are REJECTED, not
    stripped, because these strings are model output about untrusted mail and the
    UI renders them as text (never HTML) in a tight list where an injected newline
    would forge a bullet the agent did not write.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: _PlainLineStr = Field(min_length=1, max_length=INTAKE_SUMMARY_TITLE_MAX_CHARS)
    text: _PlainLineStr = Field(min_length=1, max_length=INTAKE_SUMMARY_TEXT_MAX_CHARS)


class RecordIntakeOutcomeInput(BaseModel):
    """Validate one ``record_intake_outcome`` call — the run's structural conclusion.

    ``label`` is a short free-form tag of the agent's own choosing (Ruling 5: no fixed
    taxonomy — nothing branches on it); ``note`` is the one-glance explanation the
    lawyer reads in the intake list. ``matter_title`` (INTAKE-5a.1) is the NAME of
    the matter this thread is — the agent's one-line statement of what the thread
    turned out to be, which replaces the email subject the eager row was opened
    with UNLESS a human has renamed it (``projects.name_source``). ``summary``
    (INTAKE-5a, ruling 7) is the agent's
    ≤5-bullet account of the THREAD SO FAR, required on every call and written in
    full each time — it is what the Inbox opens on instead of the email chain. All
    three are model text: bounded here, stored on the thread, and never written into
    an audit row or a log line.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    outcome: IntakeOutcome
    label: _NulFreeStr = Field(min_length=1, max_length=INTAKE_LABEL_MAX_CHARS)
    note: _NulFreeStr = Field(min_length=1, max_length=INTAKE_NOTE_MAX_CHARS)
    matter_title: _PlainLineStr = Field(min_length=1, max_length=INTAKE_MATTER_TITLE_MAX_CHARS)
    summary: list[IntakeSummaryItem] = Field(min_length=1, max_length=INTAKE_SUMMARY_MAX_ITEMS)


class DraftEmailReplyInput(BaseModel):
    """Validate one ``draft_email_reply`` call — a reply the human must approve.

    Since INTAKE-4b (ADR-F087) the tool's execution IS the send. That is not an
    auto-send path: the tool is interrupt-gated unconditionally
    (``app.agents.hitl.ALWAYS_INTERRUPT_TOOL_NAMES``), so a body validated here has
    already been approved — possibly edited — by the supervising lawyer by the time
    it executes, and delivery goes out through the mail-bridge (``POST /send``) with
    the approved bytes. These caps are therefore the size of what a counterparty can
    actually receive; :class:`~app.schemas.agent_runs.EditedEmailReplyArgs` imports
    them so the human-edit boundary cannot drift from the tool's own.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    to: list[_NulFreeAddr] = Field(min_length=1, max_length=DRAFT_REPLY_MAX_RECIPIENTS)
    subject: _NulFreeStr = Field(min_length=1, max_length=DRAFT_REPLY_SUBJECT_MAX_CHARS)
    body: _NulFreeStr = Field(min_length=1, max_length=DRAFT_REPLY_BODY_MAX_CHARS)
    # File ids must belong to THIS matter — enforced by the tool against the DB
    # (a foreign id is refused the way a cross-user read is: "not found").
    attachment_file_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=DRAFT_REPLY_MAX_ATTACHMENTS
    )


# ---------------------------------------------------------------------------
# INTAKE-5a (ADR-F086) — the lawyer's Inbox read model.
#
# Response shapes for ``GET /intake/threads`` and ``GET /intake/threads/{id}``.
# These DO carry email content (subject, addresses, bodies) — plan ruling 9: it is
# the owner's own post, shown to the owner behind the owner fence. What they never
# do is reach a log line or an audit row, and every string here is rendered as
# text, never HTML.
# ---------------------------------------------------------------------------

#: Page-size bounds for the thread list (bounded like every other list here).
INTAKE_THREAD_LIST_LIMIT_DEFAULT = 50
INTAKE_THREAD_LIST_LIMIT_MAX = 100
#: Hard ceiling on the messages returned with one thread. A thread is one email
#: conversation, so this is generous; a chain longer than this is truncated to its
#: NEWEST ``INTAKE_THREAD_MESSAGE_MAX`` messages — the ones a human opening the
#: thread came to read — and ``messages_truncated`` tells the reader the OLD end is
#: missing rather than silently showing a partial chain.
INTAKE_THREAD_MESSAGE_MAX = 200


class IntakeThreadProjectRead(BaseModel):
    """The matter an intake thread landed in (ADR-F086 Amendment A1: always one).

    ``None`` on the parent field only when the project row was hard-deleted
    (``project_id`` is ``SET NULL``); such a thread is visible to the MAILBOX
    owner alone.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    reference: str | None = None
    archived: bool = False


class IntakeLiveAskRead(BaseModel):
    """The conversation's live HITL ask, when there is one (plan ruling 2).

    Derived from :func:`app.agents.run_service.newest_live_run` — the ONE definition
    of "what is happening on this conversation right now" — plus the paused run's
    settled ``hitl_request`` step. The Inbox renders no approval card of its own: it
    shows "needs your decision" and deep-links into the conversation where
    ``HitlConfirmCard`` already works. ``allowed_decisions`` is the same gate the
    resume endpoint applies, so the two can never offer different verbs.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    tool_names: list[str] = Field(default_factory=list)
    allowed_decisions: list[str] = Field(default_factory=list)


class IntakeWaitingOnRead(BaseModel):
    """Why this thread has not been read yet (INTAKE-5a.1).

    A conversation runs ONE run at a time (``is_conversation_in_flight``), so a thread
    whose sibling is paused on the lawyer's approval is not "in progress" — it is
    waiting for them, and the Inbox used to say "Agent is reading the thread", which
    was not true. This names the sibling that holds the live ask so the row can say
    what is actually blocking it, and link to it.
    """

    model_config = ConfigDict(extra="forbid")

    thread_id: uuid.UUID
    #: Single-line neutralised, like every other subject on this surface.
    subject: str


class IntakeSummariseResponse(BaseModel):
    """``POST /intake/threads/{id}/summarise`` — IDs and a flag, never content."""

    model_config = ConfigDict(extra="forbid")

    thread_id: uuid.UUID
    queued: bool


class IntakeThreadRead(BaseModel):
    """One row of the lawyer's Inbox."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    mailbox_address: str
    #: Single-line neutralised (``app.agents.intake_prompt``): a sender-controlled
    #: subject with embedded line breaks or marker-shaped dash runs renders as one
    #: ordinary line, here as in the agent's prompt.
    subject: str
    status: str
    outcome: str | None = None
    label: str | None = None
    outcome_note: str | None = None
    auth_state: str
    claimed_reference: str | None = None
    summary: list[IntakeSummaryItem] = Field(default_factory=list)
    #: The agent's last run settled without rewriting the summary — see
    #: ``app.api.intake_threads`` for the exact definition.
    summary_stale: bool = False
    message_count: int
    last_inbound_at: datetime | None = None
    project: IntakeThreadProjectRead | None = None
    agent_thread_id: uuid.UUID | None = None
    live_ask: IntakeLiveAskRead | None = None
    #: The error CLASS of the newest outbound message that failed to send
    #: (``timeout``, ``http_502``, …) — never a provider message, body or address.
    last_send_error: str | None = None
    #: INTAKE-5a.1: set only when this thread is unread BECAUSE a sibling thread on the
    #: same conversation is paused on the lawyer's decision. ``None`` otherwise — and
    #: never set when the live ask is on THIS thread (that is what ``live_ask`` says).
    waiting_on: IntakeWaitingOnRead | None = None
    #: Server-computed queue position (plan ruling 3), ascending: 0 = a live ask,
    #: 1 = a failed send, 2 = waiting for a human, 3 = still working, 4 = replied,
    #: 5 = handled. ``attention=true`` returns ranks 0, 1 and 2 only. Computed here so the
    #: UI cannot invent a second, disagreeing order.
    attention_rank: int


class IntakeThreadListResponse(BaseModel):
    """One page of the Inbox, attention-first."""

    model_config = ConfigDict(extra="forbid")

    items: list[IntakeThreadRead] = Field(default_factory=list)
    #: Opaque; pass back as ``cursor``. ``None`` on the last page.
    next_cursor: str | None = None


class IntakeMessageRead(BaseModel):
    """One email on the thread (plan ruling 9 — shown to the owner, never logged)."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    direction: str
    from_addr: str | None = None
    to_addrs: list[str] = Field(default_factory=list)
    subject: str | None = None
    #: The message text as received/approved. Rendered as plain text with preserved
    #: line breaks — no HTML, no markdown, no link activation (plan ruling 9).
    body_text: str | None = None
    attachment_filenames: list[str] = Field(default_factory=list)
    #: Parallel to ``attachment_filenames`` (same length, same order): the ``files``
    #: row this attachment was ingested into, or ``None`` where it could not be
    #: resolved. There is no stored message→file link — see
    #: ``app.api.intake_threads`` for the resolution rule and its limits.
    file_ids: list[uuid.UUID | None] = Field(default_factory=list)
    provider_timestamp: datetime | None = None
    run_id: uuid.UUID | None = None
    send_error: str | None = None


class IntakeThreadDetailResponse(BaseModel):
    """One thread plus its emails, oldest first."""

    model_config = ConfigDict(extra="forbid")

    thread: IntakeThreadRead
    messages: list[IntakeMessageRead] = Field(default_factory=list)
    #: True when the chain was longer than ``INTAKE_THREAD_MESSAGE_MAX`` and the
    #: OLDEST messages were dropped — the reader is told, never silently shortchanged.
    messages_truncated: bool = False
