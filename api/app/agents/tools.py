"""Matter document tools — F0-S4 (fork): the first REAL agent tools.

A run bound to a Matter (``agent_runs.project_id``, migration 0049)
gets two tools over the matter's ingested documents:

* :func:`search_documents` — hybrid retrieval over every file attached to
  the matter (ADR-F049 Slice C1): FTS (``websearch_to_tsquery`` over
  ``document_chunks.content_tsv``) fused with pgvector cosine over the
  local-embedder column (``embedding_local``). The query is embedded via the
  configured provider (local in-process door by default); if the embedder is
  unavailable or the matter has no vectors yet it degrades to FTS-only.
* :func:`read_document` — the full ``documents.normalized_content``
  (the canonical PyMuPDF text stream) for one file, by filename,
  bounded to ``_READ_LIMIT`` chars with an honest truncation notice.

Matter membership is the UNION of upstream's two file↔project
affordances — the ``project_files`` join (the attach endpoint) and the
upload-time ``files.project_id`` column (``POST /files`` with a
``project_id`` form field sets only the column, no join row; verified
live in F0-S4). Either one makes a document the matter's. Defense in
depth on every query: ``files.owner_id == run.user_id`` re-asserted +
``deleted_at IS NULL`` (the chats-path posture). Matter and user
identifiers are B-class parameters (ADR-F004) — closure-injected at
:func:`build_matter_tools`, never model-visible; the model-facing
signatures carry only content arguments.

Every dispatch passes the :mod:`app.agents.guard` chokepoint FIRST
(ADR-F002) — the only way to obtain these tools is guarded.

Tool results return document text verbatim: the gateway's anonymization
middleware does not pseudonymize ``tool``-role messages (same M2-D2
posture as the chat path's document-context blocks — the model needs
intact source quotes for citation grounding). The matter's privilege /
tier floor travels on the run's gateway envelope instead
(:func:`app.agents.factory.build_gateway_chat_model`).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.selectable import Select

from app import storage
from app.agents.factory import DEFAULT_MAX_INPUT_TOKENS
from app.agents.guard import GuardContext, guarded_dispatch
from app.config import get_settings
from app.knowledge.embedding_provider import get_embedding_provider
from app.knowledge.rerank_provider import get_rerank_provider
from app.knowledge.retrieval import matter_search_reranked
from app.models.document import Document
from app.models.file import File
from app.models.project import ProjectFile
from app.pipeline.readers._base import OOXML_DOCX_MIME, guard_ooxml, ooxml_subtype
from app.schemas.matter_memory import EstimateReadCostInput

logger = logging.getLogger(__name__)

# Top-k passages per search; chunks are paragraph-sized so 8 keeps the
# tool result well inside the model's working context.
_SEARCH_LIMIT = 8
# Hybrid fusion weight for matter document search (ADR-F049 Slice C1):
# score = (1-alpha)*vector + alpha*fts. Tuned on Track-B; <1 to engage the vector
# side. When the query can't be embedded we fall back to alpha=1.0 (FTS-only).
_HYBRID_ALPHA = 0.5
_SNIPPET_LIMIT = 1500
# read_document cap (~10k tokens) — long documents truncate with an
# honest notice steering the model back to search_documents.
_READ_LIMIT = 40_000

# F2 Phase-3 Slice E (ADR-F049): pre-flight read-cost estimate.
# A tokenizer-agnostic ~4-chars/token estimate; legal text tokenises slightly denser,
# so this slightly UNDERSTATES — good enough to choose a consumption mode, not a
# billing-grade number (the honest limit recorded in the strategy research).
_CHARS_PER_TOKEN = 4
# Compaction trims context at ~0.85 x the window (factory.DEFAULT_MAX_INPUT_TOKENS);
# that floor is the budget a turn's reads compete inside.
_COMPACTION_FRACTION = 0.85
# A coarse standing-overhead reserve (base prompt + injected memory tiers + headroom
# for reasoning and output) subtracted from the floor to give a turn-START remaining
# budget. This is an ESTIMATE: live per-turn token accounting is the deferred R4 slice
# (guard.py R4 is still a no-op), so the tool never claims a live count.
_BUDGET_RESERVE_TOKENS = 40_000


def _read_tokens(character_count: int | None) -> int:
    """Estimated tokens to read one document in full (capped at the read limit).

    ``read_document`` truncates at ``_READ_LIMIT`` chars, so a document cannot cost
    more than ``_READ_LIMIT / _CHARS_PER_TOKEN`` tokens to read however large it is.
    """
    return min(character_count or 0, _READ_LIMIT) // _CHARS_PER_TOKEN


MATTER_TOOL_NAMES = frozenset(
    {"search_documents", "read_document", "get_document_metadata", "estimate_read_cost"}
)


@dataclass(frozen=True)
class MatterBinding:
    """The matter facts a run's tools and gateway envelope need."""

    project_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    privileged: bool
    minimum_inference_tier: int | None
    # F1-S3: the matter's practice area (None for unfiled/legacy matters) —
    # carried into the guard context for per-area audit slicing.
    practice_area_id: uuid.UUID | None = None


def build_matter_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
) -> list[Callable[..., Any]]:
    """Build the matter's guarded document tools for one run.

    The closures carry the B-class scope (matter + owner); the guard
    context grants exactly this tool set (search_documents + read_document +
    get_document_metadata + estimate_read_cost — R6's grant set).

    ``max_input_tokens`` is the run's context window (default the production
    window) — it sets the turn-start remaining-budget estimate the
    ``estimate_read_cost`` tool reports (F2 Slice E, ADR-F049).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=MATTER_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )
    # Turn-start remaining budget = compaction floor minus a coarse standing reserve.
    # An estimate for choosing a consumption mode, NOT live accounting (deferred R4).
    budget_floor = int(max_input_tokens * _COMPACTION_FRACTION)
    remaining_budget = max(0, budget_floor - _BUDGET_RESERVE_TOKENS)

    async def search_documents(query: str) -> str:
        """Search this matter's documents for passages matching a query.

        Full-text search over every document attached to the matter.
        Returns the best-matching passages with their document name and
        page numbers — quote from these to ground your answer. Pass an
        empty query to list the matter's documents instead.
        """
        return await guarded_dispatch(
            "search_documents", lambda db: _search(db, binding, query), ctx
        )

    async def read_document(name: str) -> str:
        """Read the full text of one of this matter's documents.

        ``name`` is the document's filename exactly as shown by
        search_documents. Long documents are truncated — use
        search_documents to locate specific passages instead of
        re-reading.
        """
        return await guarded_dispatch("read_document", lambda db: _read(db, binding, name), ctx)

    async def get_document_metadata(name: str) -> str:
        """Read a document's authorship metadata — who sent/authored it (ADR-F048).

        ``name`` is the document's filename exactly as shown by search_documents. For an
        EMAIL you get its From / To / Cc / Date / Subject headers (the sender is who sent
        the message); for a Word .docx you get the document's core-properties author and
        last-modified-by. Use this to work out who is who on the matter — then record them
        with record_matter_participant (which side they are on). These strings are
        provided by the document and can be forged: treat them as a clue to identity, not
        proof, and check in with the user if you are not sure.
        """
        return await guarded_dispatch(
            "get_document_metadata", lambda db: _document_metadata(db, binding, name), ctx
        )

    async def estimate_read_cost(filenames: list[str] | None = None) -> str:
        """Estimate the token cost of reading documents BEFORE you read or delegate.

        Pass the candidate filenames exactly as shown by search_documents, or omit
        them / pass an empty list to estimate the whole matter. Returns how many
        documents matched, the estimated tokens to read them in full, your remaining
        budget for this turn (an estimate), and which consumption mode fits. Use it to
        choose: read a set in full when it fits well within the remaining budget; fan
        out a subagent per document only when it would NOT fit and the work splits into
        independent reads; otherwise retrieve passages with search_documents.
        """
        return await guarded_dispatch(
            "estimate_read_cost",
            lambda db: _estimate_read_cost(db, binding, filenames, remaining_budget),
            ctx,
        )

    return [search_documents, read_document, get_document_metadata, estimate_read_cost]


async def _embed_query(query: str) -> list[float] | None:
    """Embed a search query via the configured provider; ``None`` on failure.

    ADR-F049 Slice C1: the local door (in-process) is the default; ``is_query=True``
    so an asymmetric model adds its retrieval prefix. Any provider error degrades
    to FTS-only (mirrors the chat RAG path) — retrieval must never hard-fail on the
    embedder.
    """
    try:
        vectors = await get_embedding_provider().embed([query], is_query=True)
    except Exception as exc:
        logger.warning(
            "matter search: query-embedding failed; FTS-only fallback",
            extra={"event": "matter_search_embed_failed", "error": str(exc)},
        )
        return None
    return vectors[0] if vectors else None


async def _search(db: AsyncSession, binding: MatterBinding, query: str) -> str:
    """Retrieve over the matter's chunks; empty query → document inventory.

    Routes through :func:`app.knowledge.retrieval.matter_search_reranked` — the one
    matter retriever the Track-B eval also runs (ADR-F049 Slice A). Slice C1 embeds
    the query (local door by default) and fuses FTS + vectors (``embedding_local``);
    if the embedder is unavailable or the matter has no vectors yet, the fusion
    degrades to the FTS-only fast path (``alpha=1.0``). Slice D: when
    ``rerank_enabled`` a local cross-encoder reorders the wider candidate set
    (``reranker=None`` ⇒ byte-identical to the plain hybrid path).
    """
    if not query.strip():
        return await _inventory(db, binding, header="Documents attached to this matter:")

    settings = get_settings()
    query_embedding = await _embed_query(query)
    hits = await matter_search_reranked(
        db,
        project_id=binding.project_id,
        user_id=binding.user_id,
        query=query,
        query_embedding=query_embedding,
        top_k=_SEARCH_LIMIT,
        alpha=_HYBRID_ALPHA if query_embedding is not None else 1.0,
        reranker=get_rerank_provider() if settings.rerank_enabled else None,
        rerank_candidates=settings.rerank_candidates,
    )

    if not hits:
        inventory = await _inventory(
            db, binding, header="Documents attached to this matter (none matched):"
        )
        return (
            f'No passages matched "{query}". Try different terms, or read a '
            f"document in full.\n\n{inventory}"
        )

    blocks: list[str] = []
    for hit in hits:
        pages = _page_range(hit.page_start, hit.page_end)
        snippet = hit.content
        if len(snippet) > _SNIPPET_LIMIT:
            snippet = snippet[: _SNIPPET_LIMIT - 1] + "…"
        blocks.append(f"[{hit.file_name}{pages}]\n{snippet}")
    return f"Top {len(hits)} matching passage(s) from this matter's documents:\n\n" + "\n\n".join(
        blocks
    )


async def _read(db: AsyncSession, binding: MatterBinding, name: str) -> str:
    """Full normalized text of one matter document, resolved by filename."""
    wanted = name.strip()
    if not wanted:
        return await _inventory(
            db,
            binding,
            header="Pass a document name. Documents attached to this matter:",
        )

    stmt = (
        _matter_files_query(
            binding,
            File.filename,
            Document.id,
            Document.normalized_content,
            Document.page_count,
        )
        .where(func.lower(File.filename) == wanted.lower())
        # Duplicates: prefer a READABLE copy (ingested Document) over an
        # unreadable one, then the most recently added — by attach time
        # when a join row exists, else upload time (column-only members
        # have no attached_at; F0-S4 review).
        .order_by(
            Document.id.is_(None),
            func.coalesce(ProjectFile.attached_at, File.created_at).desc(),
        )
    )
    rows = (await db.execute(stmt)).all()

    if not rows:
        inventory = await _inventory(db, binding, header="Documents attached to this matter:")
        return f'No document named "{wanted}" in this matter.\n\n{inventory}'

    row = rows[0]
    note = (
        f"Note: {len(rows)} files in this matter share this name; reading the "
        "most recently added readable copy.\n\n"
        if len(rows) > 1
        else ""
    )

    if row.id is None or not (row.normalized_content or "").strip():
        return (
            f'"{row.filename}" has no extractable text yet (ingestion pending '
            "or failed). Try again shortly or pick another document."
        )

    content = row.normalized_content
    pages = f" ({row.page_count} pages)" if row.page_count else ""
    if len(content) > _READ_LIMIT:
        omitted = len(content) - _READ_LIMIT
        return (
            f"{note}[{row.filename}{pages} — first {_READ_LIMIT:,} characters; "
            f"{omitted:,} more truncated. Use search_documents to locate "
            f"specific passages.]\n\n{content[:_READ_LIMIT]}"
        )
    return f"{note}[{row.filename}{pages} — full text]\n\n{content}"


def _rejection_text(exc: ValidationError, tool: str) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no body echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(input)"
        problems.append(f"- {loc}: {err['msg']}")
    return f"{tool} was rejected — nothing was read. Fix the following and retry:\n" + "\n".join(
        problems
    )


async def _estimate_read_cost(
    db: AsyncSession,
    binding: MatterBinding,
    filenames: list[str] | None,
    remaining_budget: int,
) -> str:
    """Estimate the tokens to read a candidate set in full, vs the remaining budget.

    Reject-not-crash: a malformed / over-long list is rejected back to the model. Names
    are matched parameterized over the matter scope (the security boundary in
    :func:`_matter_files_query`) — never built into SQL. An empty list ⇒ the whole
    matter. The estimate is ``Σ min(character_count, _READ_LIMIT) / _CHARS_PER_TOKEN``;
    the budget and modes follow the strategy research (read-in-full when it fits ≤ ½ of
    the remaining budget; fan out only when it would not fit and the work is independent).
    """
    try:
        proposal = EstimateReadCostInput(filenames=filenames or [])
    except ValidationError as exc:
        return _rejection_text(exc, "estimate_read_cost")

    wanted = [n.strip() for n in proposal.filenames if n.strip()]
    # Count READABLE documents (distinct Document.id) — an un-ingested matter file has
    # no Document row, so it is not a candidate to read and adds nothing to the cost.
    # NOTE: Postgres LEAST() SKIPS NULL args (LEAST(NULL, 40000) == 40000), so an
    # un-ingested file's NULL character_count would phantom-count as the read cap —
    # coalesce(..., 0) first so a NULL contributes 0, not _READ_LIMIT.
    stmt = _matter_files_query(
        binding,
        func.count(func.distinct(Document.id)),
        func.coalesce(
            func.sum(func.least(func.coalesce(Document.character_count, 0), _READ_LIMIT)), 0
        ),
    )
    if wanted:
        stmt = stmt.where(func.lower(File.filename).in_([w.lower() for w in wanted]))
    row = (await db.execute(stmt)).one()
    n_docs = int(row[0] or 0)
    est_tokens = int(row[1] or 0) // _CHARS_PER_TOKEN

    if n_docs == 0:
        if wanted:
            return (
                "None of those filenames matched documents in this matter. Check the "
                "names with search_documents (an empty query lists them)."
            )
        return "This matter has no documents to read."

    half = remaining_budget // 2
    if est_tokens <= half:
        mode = (
            "This fits comfortably — read them in full with read_document and reason "
            "over the whole text."
        )
    elif est_tokens <= remaining_budget:
        mode = (
            "This is large for one context — read only the few most relevant in full, "
            "or retrieve passages with search_documents."
        )
    else:
        mode = (
            "This is too large to read whole. If the work splits into independent "
            "per-document reads, fan out a subagent per document; otherwise retrieve "
            "passages with search_documents and read only the very top few in full."
        )
    scope = f"{n_docs} document(s)" if wanted else f"the whole matter ({n_docs} document(s))"
    return (
        f"Estimated cost to read {scope} in full: ~{est_tokens:,} tokens. "
        f"Remaining budget this turn: ~{remaining_budget:,} tokens (a turn-start "
        f"estimate, not a live count). {mode}"
    )


# Email header keys (lowercased label) as stored in Document.structured_content by the
# email reader (app.pipeline.readers._message.assemble_email) → the human label to render.
_EMAIL_HEADERS: tuple[tuple[str, str], ...] = (
    ("from", "From"),
    ("to", "To"),
    ("cc", "Cc"),
    ("date", "Date"),
    ("subject", "Subject"),
)


async def _document_metadata(db: AsyncSession, binding: MatterBinding, name: str) -> str:
    """Structured authorship metadata for one matter document, by filename (ADR-F048 S2).

    Email → the stored From/To/Cc/Date/Subject from ``structured_content`` (no re-parse).
    Word ``.docx`` → the core-properties author / last-modified-by from the document bytes
    (via the shared, safety-gated :func:`load_matter_docx_bytes`). The strings are
    UNTRUSTED, forgeable model input — a clue to who a participant is
    (record_matter_participant), never authoritative identity. Matter-scoped + 404-conflated.
    """
    wanted = name.strip()
    if not wanted:
        return await _inventory(
            db, binding, header="Pass a document name. Documents attached to this matter:"
        )
    stmt = (
        _matter_files_query(
            binding,
            File.filename,
            File.mime_type,
            Document.id,
            Document.structured_content,
        )
        .where(func.lower(File.filename) == wanted.lower())
        .order_by(
            Document.id.is_(None),
            func.coalesce(ProjectFile.attached_at, File.created_at).desc(),
        )
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        inventory = await _inventory(db, binding, header="Documents attached to this matter:")
        return f'No document named "{wanted}" in this matter.\n\n{inventory}'

    row = rows[0]
    structured = row.structured_content
    if isinstance(structured, dict) and structured.get("format") == "email":
        return _render_email_metadata(row.filename, structured)
    if row.mime_type == OOXML_DOCX_MIME:
        loaded = await load_matter_docx_bytes(db, binding, wanted)
        if isinstance(loaded, str):
            return loaded
        _docx_row, data = loaded
        return _render_docx_metadata(row.filename, data)
    return (
        f'"{row.filename}" has no structured authorship metadata (it is {row.mime_type}). '
        "For tracked-change authorship read the document, or use the negotiation / "
        "hand-back tools."
    )


def _render_email_metadata(filename: str, structured: dict[str, Any]) -> str:
    """Render an email's stored headers (From/To/Cc/Date/Subject) — the sender is who sent it."""
    messages = structured.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return f'"{filename}" is an email but carries no parsed headers.'
    lines = [
        f'EMAIL METADATA for "{filename}" — message headers (UNTRUSTED, forgeable model '
        "input: use to identify who a participant might be, then record_matter_participant; "
        "never treat as proof of identity). The sender (From) is who sent the message.",
    ]
    multi = len(messages) > 1
    for i, msg in enumerate(messages, start=1):
        if not isinstance(msg, dict):
            continue
        if multi:
            lines.append(f"\nMessage {i}:")
        for key, label in _EMAIL_HEADERS:
            value = msg.get(key)
            if value:
                lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _render_docx_metadata(filename: str, data: bytes) -> str:
    """Render a .docx's core-properties author / last-modified-by from its bytes."""
    try:
        from io import BytesIO

        import docx

        core = docx.Document(BytesIO(data)).core_properties
        author = (core.author or "").strip()
        last_modified_by = (core.last_modified_by or "").strip()
    except Exception:
        logger.warning(
            "docx core-properties read failed",
            extra={"event": "matter_docx_props_failed"},
        )
        return f'"{filename}" core properties could not be read.'
    lines = [
        f'DOCUMENT METADATA for "{filename}" — Word core properties (UNTRUSTED, forgeable '
        "model input: the document-level author/editor, NOT the per-change tracked-change "
        "authors; use to identify who a participant might be, then record_matter_participant).",
    ]
    if author:
        lines.append(f"- Author (created by): {author}")
    if last_modified_by:
        lines.append(f"- Last modified by: {last_modified_by}")
    if not author and not last_modified_by:
        lines.append("- No author is recorded in the document's core properties.")
    return "\n".join(lines)


def _matter_files_query(binding: MatterBinding, *columns: Any) -> Select[Any]:
    """SELECT ``columns`` over the matter's files (membership union +
    owner re-assertion — module docstring).

    ``columns`` are ORM-mapped attributes (``File.filename``, …) —
    typed ``Any`` because SQLAlchemy's public stubs have no common
    supertype covering ``InstrumentedAttribute`` columns here.
    """
    return (
        select(*columns)
        .select_from(File)
        .outerjoin(
            ProjectFile,
            and_(
                ProjectFile.file_id == File.id,
                ProjectFile.project_id == binding.project_id,
            ),
        )
        .outerjoin(Document, Document.file_id == File.id)
        .where(
            or_(
                ProjectFile.project_id.is_not(None),
                File.project_id == binding.project_id,
            ),
            File.owner_id == binding.user_id,
            File.deleted_at.is_(None),
        )
    )


def duplicate_groups_from_rows(rows: Sequence[Any]) -> dict[uuid.UUID, tuple[uuid.UUID, str]]:
    """Pure grouping: rows carrying ``id``/``filename``/``hash_sha256``/``created_at`` →
    map of each exact-duplicate file → (canonical file id, canonical filename).

    Duplicates are IDENTICAL bytes, detected deterministically from ``files.hash_sha256``
    (WORKSPACE-1, ADR-F082) — never agent-asserted, so a hostile document cannot forge a
    "this is a duplicate" claim. The canonical file of a duplicate set is the earliest-created
    one (id string as a stable tiebreaker); every other file in the set maps to it. Files with a
    unique hash are absent from the map. Pure so every surface that already holds the matter's
    row set (inventory, tier block, files endpoint) groups WITHOUT a second query; scoping is the
    CALLER's query (matter+owner, soft-delete-safe — the no-existence-leak boundary).
    """
    by_hash: dict[str, list[Any]] = {}
    for row in rows:
        by_hash.setdefault(row.hash_sha256, []).append(row)
    dup: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
    for group in by_hash.values():
        if len(group) < 2:
            continue
        canonical = min(group, key=lambda r: (r.created_at, str(r.id)))
        for row in group:
            if row.id != canonical.id:
                dup[row.id] = (canonical.id, canonical.filename)
    return dup


async def duplicate_of_map(
    db: AsyncSession, binding: MatterBinding
) -> dict[uuid.UUID, tuple[uuid.UUID, str]]:
    """Query-then-group convenience over :func:`duplicate_groups_from_rows` for callers that do
    NOT already hold the matter's file rows. Scope is this matter, owner-re-asserted and
    soft-delete-safe (``_matter_files_query``), so an identical hash held in another matter or
    tenant is never revealed (no existence leak — the 404 discipline)."""
    rows = (
        await db.execute(
            _matter_files_query(binding, File.id, File.filename, File.hash_sha256, File.created_at)
        )
    ).all()
    return duplicate_groups_from_rows(rows)


async def resolve_matter_file_by_name(
    db: AsyncSession, binding: MatterBinding, name: str
) -> Row[Any] | None:
    """Resolve a matter file by filename with the SAME rule the read path uses.

    Mirrors ``_read`` exactly (review finding, PR #271): case-INSENSITIVE match, prefer a
    READABLE copy (ingested ``Document``) over an unreadable one on a name collision, then the
    most recently added — attach time when a join row exists, else upload time. Anything looser
    binds a summary to a file the agent never read (the resolver picking a newer un-ingested
    re-upload while ``read_document`` served the older ingested copy). Owner+matter scoped,
    soft-delete-safe; parameterised — the name never builds SQL. ``None`` when no live matter
    file has that name. Used by ``record_document_summary`` (WORKSPACE-1).
    """
    rows = (
        await db.execute(
            _matter_files_query(binding, File.id, File.filename)
            .where(func.lower(File.filename) == name.strip().lower())
            .order_by(
                Document.id.is_(None),
                func.coalesce(ProjectFile.attached_at, File.created_at).desc(),
            )
        )
    ).all()
    return rows[0] if rows else None


# Defense cap on a .docx we'll buffer into memory (parse / redline). The upload
# cap is larger; a deal contract or policy is well under this.
_MAX_DOCX_BYTES = 25 * 1024 * 1024

# Shared projection for the .docx read/write tools (ADR-F066): fetch_matter_docx
# and resolve_working_docx must return interchangeable rows — _render_redline
# consumes either — so the row shape is defined exactly once. parent_file_id /
# is_snapshot let the redline persist step decide create-vs-converge (ADR-F081)
# without a second query at render time.
_DOCX_COLUMNS = (
    File.id.label("file_id"),
    File.filename,
    File.mime_type,
    File.storage_path,
    File.parent_file_id,
    File.is_snapshot,
    Document.id.label("document_id"),
    Document.normalized_content,
)


async def fetch_matter_docx(
    db: AsyncSession, binding: MatterBinding, document_name: str
) -> Row[Any] | None:
    """Resolve one matter document by filename (owner + matter scoped).

    Mirrors ``read_document``'s resolution: prefer an ingested (readable) copy,
    then the most recently added. Returns ``None`` when no such document exists
    in this matter (cross-user is the same 404-conflated absence — ADR-F035).

    Generic (any area): shared by the Commercial redline/negotiation read+write
    tools and the area-agnostic ``review_edited_document`` re-read (ADR-F047 S5).
    """
    wanted = document_name.strip()
    stmt = (
        _matter_files_query(binding, *_DOCX_COLUMNS)
        .where(func.lower(File.filename) == wanted.lower())
        .order_by(
            Document.id.is_(None),
            func.coalesce(ProjectFile.attached_at, File.created_at).desc(),
        )
    )
    rows = (await db.execute(stmt)).all()
    return rows[0] if rows else None


# Depth cap on the lineage walk — a real chain is a handful of rounds; this only
# stops a bad-data parent cycle from spinning the resolver forever (ADR-F066).
_LINEAGE_MAX_DEPTH = 20


async def resolve_working_docx(
    db: AsyncSession, binding: MatterBinding, document_name: str
) -> Row[Any] | None:
    """Resolve a named document to its newest WORKING version (R-1, ADR-F066).

    Starts from the exact-name row (:func:`fetch_matter_docx`, unchanged) and
    collects its ``files.parent_file_id`` descendant tree — skipping editor
    snapshots, which are immutable prior versions — then returns the newest
    non-snapshot LEAF: the agent's latest output, or the human-edited live row.
    Newest is by ``coalesce(updated_at, created_at)`` compared across the WHOLE
    tree, not per-hop among siblings, so a lineage that diverged (``start_fresh``
    or an explicitly named branch) still resolves to wherever the latest work
    actually happened. Every generation is fetched under the full matter scope
    (:func:`_matter_files_query`), so a lineage row can never pull in a document
    from outside the binding's matter. Returns the named row itself when nothing
    derives from it; ``None`` when the name doesn't resolve (the same
    404-conflated absence as :func:`fetch_matter_docx`).
    """
    root = await fetch_matter_docx(db, binding, document_name)
    if root is None:
        return None
    # Breadth-first over the non-snapshot descendants: one matter-scoped query
    # per generation, depth-capped against bad-data parent cycles.
    touched: dict[uuid.UUID, datetime] = {}  # descendant id → last activity
    inner: set[uuid.UUID] = set()  # ids with a non-snapshot child (not leaves)
    seen: set[uuid.UUID] = {root.file_id}
    frontier: list[uuid.UUID] = [root.file_id]
    for _ in range(_LINEAGE_MAX_DEPTH):
        stmt = _matter_files_query(
            binding,
            File.id,
            File.parent_file_id,
            func.coalesce(File.updated_at, File.created_at).label("touched_at"),
        ).where(
            File.parent_file_id.in_(frontier),
            File.is_snapshot.is_(False),
        )
        rows = (await db.execute(stmt)).all()
        frontier = []
        for row in rows:
            inner.add(row.parent_file_id)
            if row.id in seen:  # Document-outerjoin duplicate or cycle
                continue
            seen.add(row.id)
            touched[row.id] = row.touched_at
            frontier.append(row.id)
        if not frontier:
            break
    if not touched:
        return root  # nothing non-snapshot derives from the named row
    # Leaves = descendants nothing derives from. A bad-data cycle can leave no
    # leaf at all — degrade to the newest descendant. Equal timestamps (same
    # transaction) tie-break on id hex, arbitrary but deterministic.
    leaves = set(touched) - inner
    winner = max(leaves or set(touched), key=lambda fid: (touched[fid], fid.hex))
    stmt = (
        _matter_files_query(binding, *_DOCX_COLUMNS)
        .where(File.id == winner)
        .order_by(Document.id.is_(None))  # same file twice (re-ingested) → readable copy
        .limit(1)
    )
    final = (await db.execute(stmt)).first()
    return final if final is not None else root


async def download_matter_docx(storage_path: str) -> bytes | None:
    """Buffer a .docx's bytes from object storage (size-capped). ``None`` on cap/error."""
    chunks: list[bytes] = []
    total = 0
    try:
        async with storage.stream_download(storage_path=storage_path) as stream:
            async for chunk in stream:
                total += len(chunk)
                if total > _MAX_DOCX_BYTES:
                    logger.warning(
                        "matter docx exceeds cap",
                        extra={"event": "matter_docx_too_large", "bytes": total},
                    )
                    return None
                chunks.append(chunk)
    except Exception:
        logger.warning(
            "matter docx download failed",
            extra={"event": "matter_docx_download_failed"},
        )
        return None
    return b"".join(chunks)


async def load_matter_docx_bytes(
    db: AsyncSession, binding: MatterBinding, document_name: str
) -> tuple[Row[Any], bytes] | str:
    """Fetch a matter ``.docx`` (owner+matter scoped, 404-conflated) and return its
    safety-checked bytes, or a fix-and-retry STRING.

    Generic (any area): the Commercial negotiation read/respond tools and the
    area-agnostic ``review_edited_document`` re-read both load through here so the
    matter-scope + OOXML safety gate lives in one place (the redline path inlines
    the same steps in ``_render_redline``)."""
    row = await fetch_matter_docx(db, binding, document_name.strip())
    if row is None:
        return (
            f'No document named "{document_name}" in this matter. Use search_documents '
            "(empty query) to list the matter's documents."
        )
    if row.mime_type != OOXML_DOCX_MIME:
        return f'"{row.filename}" is not a Word .docx (it is {row.mime_type}).'
    data = await download_matter_docx(row.storage_path)
    if data is None:
        return f'"{row.filename}" could not be read from storage. Try again shortly.'
    if ooxml_subtype(data) != "docx":
        return f'"{row.filename}" is not a valid .docx.'
    try:
        guard_ooxml(data)
    except Exception:
        logger.warning(
            "matter docx failed OOXML safety checks",
            extra={"event": "matter_docx_unsafe_ooxml"},
        )
        return f'"{row.filename}" failed .docx safety checks and was not read.'
    return row, data


async def _inventory(db: AsyncSession, binding: MatterBinding, *, header: str) -> str:
    """One line per attached file — name, pages, read-cost estimate, ingest readiness.

    F2 Slice E (ADR-F049): the per-document ``~k tokens to read`` estimate (from the
    stored ``character_count``, capped at the read limit) is the cheapest, highest-
    leverage self-awareness signal — the agent sees the cost of reading each candidate
    BEFORE it reads, which is the precondition for choosing a consumption mode.
    """
    stmt = _matter_files_query(
        binding,
        File.id.label("file_id"),
        File.filename,
        File.ingestion_status,
        File.parent_file_id,
        File.is_snapshot,
        File.created_by_run_id,
        File.summary,
        File.summary_updated_at,
        File.updated_at,
        File.hash_sha256,
        File.created_at,
        Document.id,
        Document.page_count,
        Document.character_count,
    ).order_by(File.filename)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return f"{header}\n(no documents attached — answer from the prompt alone, honestly)"

    # WORKSPACE-1 (ADR-F082): exact-duplicate awareness, computed from the content hash
    # (never agent-asserted). Grouped from the rows already fetched — no second query. The
    # marker tells the agent when two files are the same bytes so it doesn't treat a
    # re-upload as a second document.
    dup_map = duplicate_groups_from_rows(
        [_DupRow(r.file_id, r.filename, r.hash_sha256, r.created_at) for r in rows]
    )

    # Provenance labels for non-ingested work products (ADR-F066): resolve the
    # parent filenames in ONE batched matter-scoped query (never per row). A
    # parent that is gone (hard delete → SET NULL; soft delete → out of matter
    # scope) drops out of the map and the label degrades gracefully.
    parent_ids = {r.parent_file_id for r in rows if r.id is None and r.parent_file_id is not None}
    parent_names: dict[uuid.UUID, str] = {}
    if parent_ids:
        parent_rows = (
            await db.execute(
                _matter_files_query(binding, File.id, File.filename).where(File.id.in_(parent_ids))
            )
        ).all()
        parent_names = {r.id: r.filename for r in parent_rows}

    lines: list[str] = []
    for row in rows:
        dup = dup_map.get(row.file_id)
        dup_marker = f" — (duplicate of {dup[1]})" if dup is not None else ""
        # WORKSPACE-1 (ADR-F082): the agent-recorded summary — shown for EVERY row that has
        # one (a summarised work product is still a described document), with an honest
        # staleness marker when the bytes were mutated after the summary was written
        # (editor save-back / redline convergence, ADR-F047/F081).
        summary_marker = f" — {summary_with_staleness(row)}" if row.summary else ""
        if row.id is None:
            lines.append(
                f"- {row.filename} {_provenance(row, parent_names)}{dup_marker}{summary_marker}"
            )
            continue
        bits: list[str] = []
        if row.page_count:
            bits.append(f"{row.page_count} pages")
        if row.character_count:
            bits.append(f"~{_read_tokens(row.character_count):,} tokens to read")
        suffix = f" ({'; '.join(bits)})" if bits else ""
        lines.append(f"- {row.filename}{suffix}{dup_marker}{summary_marker}")
    return f"{header}\n" + "\n".join(lines)


@dataclass(frozen=True)
class _DupRow:
    """The minimal row shape :func:`duplicate_groups_from_rows` groups on."""

    id: uuid.UUID
    filename: str
    hash_sha256: str
    created_at: Any


def summary_with_staleness(row: Any) -> str:
    """The recorded summary, suffixed honestly when the FILE changed after it was written.

    ``updated_at`` is set only by the in-place byte mutators (editor save-back, ADR-F047;
    redline convergence, ADR-F081) — when it postdates ``summary_updated_at`` the description
    no longer describes the current bytes, and presenting it bare would mislead both the agent
    and the lawyer (review finding, PR #271). Shared by the inventory, the WS-2 tier block and
    the files endpoint so the staleness rule lives in one place.
    """
    summary = (row.summary or "").strip()
    if is_summary_stale(row):
        return f"{summary} (summary may be stale — the document changed after it was written)"
    return summary


def is_summary_stale(row: Any) -> bool:
    """True when the file's bytes were mutated after the summary was recorded."""
    return bool(
        row.summary
        and row.updated_at is not None
        and (row.summary_updated_at is None or row.updated_at > row.summary_updated_at)
    )


def _provenance(row: Row[Any], parent_names: dict[uuid.UUID, str]) -> str:
    """Honest one-phrase provenance for a non-ingested inventory row (ADR-F066).

    Agent outputs and editor snapshots are deliberately never ingested (work
    product, not a search source) — rendering them as pending uploads misled the
    model into treating its own latest draft as an unprocessed original.
    """
    parent = parent_names.get(row.parent_file_id) if row.parent_file_id is not None else None
    if row.is_snapshot:
        return f"(editor snapshot of {parent})" if parent else "(editor snapshot)"
    if parent is not None:
        return f"(agent work product — derived from {parent})"
    if row.created_by_run_id is not None:
        return "(agent work product)"
    return f"(not ingested yet — status: {row.ingestion_status})"


def _page_range(start: int | None, end: int | None) -> str:
    if start is None:
        return ""
    if end is None or end == start:
        return f" — page {start}"
    return f" — pages {start}-{end}"
