"""Pydantic schemas for the chats + messages surface (Task C3).

Wire shapes for ``/api/v1/chats`` and ``/api/v1/chats/{id}/messages``
matching ``Chat``, ``ChatCreate``, ``ChatUpdate``, ``Message``,
``MessageCreate``, and ``MessagePostResponse`` in
``docs/api/backend-openapi.yaml``. The ORM models live in
``app.models.chat``; this module is the request/response surface.

Notes
-----

* ``MessageCreate`` extends OpenAPI's existing shape with the
  C2-introduced ``skills`` and ``skill_inputs`` fields. C3 adds nothing
  to that shape — message persistence is a server-side concern, not a
  request-body concern.
* ``Cursor`` pagination uses an opaque base64-encoded ``(created_at,
  id)`` tuple. The cursor is symmetric: encoded server-side on the
  ``next_cursor`` of one page, decoded server-side on the request's
  ``cursor`` query param. We keep the format internal so the client
  cannot manufacture cursors that bypass per-user isolation (the
  handler validates the decoded ``id`` belongs to the caller).
* Cost is presented over the wire as ``cost_estimate`` (a USD float)
  for client friendliness. Internally it is stored as integer USD
  micros (``cost_estimate_micros``); :func:`micros_to_usd` and
  :func:`usd_to_micros` translate.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

# --- Constants ---------------------------------------------------------------

TITLE_MAX_LEN: int = 200
"""Hard cap on chat ``title``. Matches the DB CHECK constraint."""

CONTENT_MIN_LEN: int = 1
"""Minimum length of a ``MessageCreate`` content string."""

AUTO_RENAME_MAX_CHARS: int = 80
"""First-message auto-rename truncation length (per C3 brief)."""

LIST_LIMIT_DEFAULT: int = 20
"""Default page size for chat / message listing."""

LIST_LIMIT_MAX: int = 100
"""Maximum page size accepted by the listing endpoints."""


# --- Type aliases ------------------------------------------------------------

ChatTitle = Annotated[
    str,
    StringConstraints(min_length=1, max_length=TITLE_MAX_LEN, strip_whitespace=True),
]
"""1-200 chars, leading/trailing whitespace stripped."""


# --- Cost helpers ------------------------------------------------------------


def usd_to_micros(value: float | None) -> int | None:
    """Convert a USD float to integer micros (1e-6 USD).

    Returns ``None`` for ``None`` (the gateway leaves cost ``None`` when
    no rate is configured for the routed model). Handles edge cases:

    * ``0.0`` → ``0`` (round-trips as zero, not None — operators want
      to see "we routed this for free" distinctly from "we don't know").
    * Negative values → preserved as negative (operator can't reasonably
      get one, but if the gateway emits one we shouldn't lose the sign).
    * Very large floats → caller's responsibility; we round to the
      nearest integer micro and trust the BIGINT column to hold it.

    Uses :func:`round` (banker's rounding in Python 3.x) on the product
    so .5-cases round to even. The audit-log delta from one micro
    either way is well below "matters to a lawyer".
    """

    if value is None:
        return None
    return round(value * 1_000_000)


def micros_to_usd(value: int | None) -> float | None:
    """Convert integer micros back to a USD float.

    Inverse of :func:`usd_to_micros`. Returns ``None`` for ``None``.
    The float result has at most 6 decimal places of significance;
    formatting to fewer is the caller's concern.
    """

    if value is None:
        return None
    return value / 1_000_000


# --- Auto-rename helpers -----------------------------------------------------


def derive_chat_title(message_content: str) -> str:
    """Derive a chat title from the first user message.

    Strategy:

    * Take the first non-empty line (newlines and CRLF terminate).
    * Collapse runs of whitespace to single spaces.
    * Truncate to ``AUTO_RENAME_MAX_CHARS`` chars; append an ellipsis
      character (U+2026) if truncated.
    * Strip leading/trailing whitespace.
    * Fall back to ``"New chat"`` if the result is empty.

    Returns a string suitable for assignment to ``chats.title``.
    """

    if not message_content:
        return "New chat"

    # Take the first non-empty line.
    first_line = ""
    for line in message_content.splitlines():
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break
    if not first_line:
        return "New chat"

    # Collapse internal whitespace runs.
    collapsed = " ".join(first_line.split())
    if len(collapsed) <= AUTO_RENAME_MAX_CHARS:
        return collapsed
    # Truncate, leaving room for the ellipsis. The ellipsis itself is
    # one codepoint so the total is AUTO_RENAME_MAX_CHARS exactly.
    head = collapsed[: AUTO_RENAME_MAX_CHARS - 1].rstrip()
    return f"{head}…"


# --- Cursor pagination -------------------------------------------------------


class Cursor(BaseModel):
    """Opaque cursor for ``(created_at, id)`` keyset pagination.

    Encoded as URL-safe base64 of a JSON dict so the wire shape is
    opaque to the client. The handler decodes, validates the ``id``
    belongs to the caller, and uses ``(created_at, id)`` as the
    keyset comparator.
    """

    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    id: uuid.UUID

    def encode(self) -> str:
        """Return the URL-safe base64 string for the wire."""

        body = json.dumps(
            {"created_at": self.created_at.isoformat(), "id": str(self.id)},
            separators=(",", ":"),
        )
        return base64.urlsafe_b64encode(body.encode("utf-8")).rstrip(b"=").decode("ascii")

    @classmethod
    def decode(cls, value: str) -> Cursor:
        """Decode a wire cursor; raises ValueError on malformed input."""

        # Restore padding.
        padding = "=" * (-len(value) % 4)
        try:
            raw = base64.urlsafe_b64decode(value + padding).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("cursor is not valid base64") from exc
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("cursor body is not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise ValueError("cursor body must be a JSON object")
        return cls.model_validate(decoded)


# --- Request schemas ---------------------------------------------------------


class ChatCreateRequest(BaseModel):
    """``ChatCreate`` from backend-openapi.yaml.

    All fields are optional. ``title`` defaults to ``"New chat"``
    (DB-side); when omitted, the API auto-renames the chat from the
    first user message.
    """

    model_config = ConfigDict(extra="forbid")

    title: ChatTitle | None = None
    project_id: uuid.UUID | None = None


class ChatUpdateRequest(BaseModel):
    """``ChatUpdate`` from backend-openapi.yaml.

    PATCH applies only the fields the caller sets (``exclude_unset``
    pattern at the handler boundary). ``archived`` toggles
    ``archived_at`` on/off; ``title`` updates the chat title.
    """

    model_config = ConfigDict(extra="forbid")

    title: ChatTitle | None = None
    archived: bool | None = None


class MessageCreateRequest(BaseModel):
    """``MessageCreate`` from backend-openapi.yaml (B5 + C2 + C3).

    C3 does not add new fields here — message persistence is server
    side. The shape stays identical to the B5/C2 definition so any
    client that worked against the stateless pass-through continues to
    work after C3.
    """

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=CONTENT_MIN_LEN)
    model: str = Field(default="smart")
    """Model alias (per the OpenAPI sketch). Defaults to ``smart``."""

    skills: list[str] = Field(default_factory=list)
    """C2: skill names to attach. Forwarded to the gateway as
    ``lq_ai_skills``."""

    skill_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """C2: per-skill input bindings. Forwarded as ``lq_ai_skill_inputs``."""

    stream: bool = False
    """Whether to stream the response as SSE. ``False`` returns a single
    JSON body."""


# --- Response schemas --------------------------------------------------------


class ChatResponse(BaseModel):
    """``Chat`` schema from backend-openapi.yaml.

    Built from the ORM row plus the rolled-up ``message_count``
    (counted in the handler with a single COUNT(*) per chat — fine on
    the M1 footprint).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    project_id: uuid.UUID | None = None
    title: str
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageResponse(BaseModel):
    """``Message`` schema from backend-openapi.yaml.

    Cost is presented as a USD float for client friendliness; the DB
    stores integer micros and :func:`micros_to_usd` translates. The
    handler is expected to convert via :func:`message_to_response` —
    we do not use ``from_attributes=True`` here because the column
    name on the ORM row (``cost_estimate_micros``) differs from the
    wire field (``cost_estimate``).
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    chat_id: uuid.UUID
    role: Literal["user", "assistant", "system", "tool"]
    kind: Literal["user", "ai", "refusal", "system"] = "user"
    """Wave D.1 — distinguishes assistant rows that carry a model
    response (``ai``) from refusal rows (``refusal``) emitted by the
    gateway's tier-floor enforcement. Defaults to ``user`` to match the
    DB column server default; the override-tier-floor flow writes
    ``ai`` explicitly so the UI can tell a re-run apart from a refusal."""

    content: str
    applied_skills: list[str] = Field(default_factory=list)
    routed_inference_tier: int | None = None
    routed_provider: str | None = None
    routed_model: str | None = None
    requested_model: str | None = None
    """The originally-requested model alias or ``provider/model`` pair
    (ADR 0011 follow-on). Differs from ``routed_model`` when an alias
    was resolved; null on rows persisted before this column existed."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_estimate: float | None = None
    """USD float; derived from the integer micros column."""

    error_code: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


def message_to_response(row: Any) -> MessageResponse:
    """Build a :class:`MessageResponse` from an ORM ``Message`` row.

    Materializes ``cost_estimate`` from the DB's integer micros column.
    Centralizing the conversion keeps the handler free of cost-unit
    bookkeeping and makes the schema's ``extra="forbid"`` posture
    workable (we don't accept the micros column on the wire).
    """

    return MessageResponse(
        id=row.id,
        chat_id=row.chat_id,
        role=row.role,
        kind=row.kind,
        content=row.content,
        applied_skills=list(row.applied_skills or []),
        routed_inference_tier=row.routed_inference_tier,
        routed_provider=row.routed_provider,
        routed_model=row.routed_model,
        requested_model=row.requested_model,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        cost_estimate=micros_to_usd(row.cost_estimate_micros),
        error_code=row.error_code,
        citations=list(row.citations or []),
        created_at=row.created_at,
    )


class ChatListResponse(BaseModel):
    """Paginated ``GET /api/v1/chats`` response."""

    model_config = ConfigDict(extra="forbid")

    items: list[ChatResponse]
    next_cursor: str | None = None


class MessageListResponse(BaseModel):
    """Paginated ``GET /api/v1/chats/{id}/messages`` response."""

    model_config = ConfigDict(extra="forbid")

    items: list[MessageResponse]
    next_cursor: str | None = None


class MessagePostResponse(BaseModel):
    """Non-streaming ``POST /api/v1/chats/{id}/messages`` response."""

    model_config = ConfigDict(extra="forbid")

    message: MessageResponse
    citations: list[dict[str, Any]] = Field(default_factory=list)
    routed_inference_tier: int | None = None
    routed_provider: str | None = None
    cost_estimate: float | None = None
    applied_skills: list[str] = Field(default_factory=list)


# --- Internal: helpers exposed for tests -------------------------------------


def encode_cursor(created_at: datetime, id_: uuid.UUID) -> str:
    """Encode a ``(created_at, id)`` pair as the wire cursor."""

    return Cursor(created_at=created_at, id=id_).encode()


def decode_cursor(value: str) -> Cursor:
    """Decode a wire cursor; raises ValueError on malformed input."""

    return Cursor.decode(value)


__all__ = [
    "AUTO_RENAME_MAX_CHARS",
    "CONTENT_MIN_LEN",
    "LIST_LIMIT_DEFAULT",
    "LIST_LIMIT_MAX",
    "TITLE_MAX_LEN",
    "ChatCreateRequest",
    "ChatListResponse",
    "ChatResponse",
    "ChatTitle",
    "ChatUpdateRequest",
    "Cursor",
    "MessageCreateRequest",
    "MessageListResponse",
    "MessagePostResponse",
    "MessageResponse",
    "decode_cursor",
    "derive_chat_title",
    "encode_cursor",
    "message_to_response",
    "micros_to_usd",
    "usd_to_micros",
]
