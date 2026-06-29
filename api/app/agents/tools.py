"""Matter document tools — F0-S4 (fork): the first REAL agent tools.

A run bound to a Matter (``agent_runs.project_id``, migration 0049)
gets two tools over the matter's ingested documents:

* :func:`search_documents` — lexical FTS (``websearch_to_tsquery`` over
  ``document_chunks.content_tsv``, the proven pattern from the tabular
  executor) across every file attached to the matter. Works with no
  embedding provider — the dev stack has none (vector search is a
  Backlog item).
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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.selectable import Select

from app import storage
from app.agents.guard import GuardContext, guarded_dispatch
from app.knowledge.retrieval import matter_hybrid_search
from app.models.document import Document
from app.models.file import File
from app.models.project import ProjectFile
from app.pipeline.readers._base import OOXML_DOCX_MIME, guard_ooxml, ooxml_subtype

logger = logging.getLogger(__name__)

# Top-k passages per search; chunks are paragraph-sized so 8 keeps the
# tool result well inside the model's working context.
_SEARCH_LIMIT = 8
_SNIPPET_LIMIT = 1500
# read_document cap (~10k tokens) — long documents truncate with an
# honest notice steering the model back to search_documents.
_READ_LIMIT = 40_000

MATTER_TOOL_NAMES = frozenset({"search_documents", "read_document", "get_document_metadata"})


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
) -> list[Callable[..., Any]]:
    """Build the matter's guarded document tools for one run.

    The closures carry the B-class scope (matter + owner); the guard
    context grants exactly this tool set (search_documents + read_document +
    get_document_metadata — R6's grant set).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=MATTER_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

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

    return [search_documents, read_document, get_document_metadata]


async def _search(db: AsyncSession, binding: MatterBinding, query: str) -> str:
    """Retrieve over the matter's chunks; empty query → document inventory.

    Routes through :func:`app.knowledge.retrieval.matter_hybrid_search` — the
    one matter retriever the Track-B eval also runs (ADR-F049, Slice A). With no
    embedder wired (``query_embedding=None``) it takes the FTS-only fast path:
    byte-identical to the pre-Slice-A behaviour. Slice C lights up the vector
    side by passing a real query embedding here.
    """
    if not query.strip():
        return await _inventory(db, binding, header="Documents attached to this matter:")

    hits = await matter_hybrid_search(
        db,
        project_id=binding.project_id,
        user_id=binding.user_id,
        query=query,
        query_embedding=None,
        top_k=_SEARCH_LIMIT,
        alpha=1.0,
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


# Defense cap on a .docx we'll buffer into memory (parse / redline). The upload
# cap is larger; a deal contract or policy is well under this.
_MAX_DOCX_BYTES = 25 * 1024 * 1024


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
        _matter_files_query(
            binding,
            File.id.label("file_id"),
            File.filename,
            File.mime_type,
            File.storage_path,
            Document.id.label("document_id"),
            Document.normalized_content,
        )
        .where(func.lower(File.filename) == wanted.lower())
        .order_by(
            Document.id.is_(None),
            func.coalesce(ProjectFile.attached_at, File.created_at).desc(),
        )
    )
    rows = (await db.execute(stmt)).all()
    return rows[0] if rows else None


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
    """One line per attached file — name, pages, ingest readiness."""
    stmt = _matter_files_query(
        binding, File.filename, File.ingestion_status, Document.id, Document.page_count
    ).order_by(File.filename)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return f"{header}\n(no documents attached — answer from the prompt alone, honestly)"

    lines: list[str] = []
    for row in rows:
        if row.id is None:
            lines.append(f"- {row.filename} (not ingested yet — status: {row.ingestion_status})")
        elif row.page_count:
            lines.append(f"- {row.filename} ({row.page_count} pages)")
        else:
            lines.append(f"- {row.filename}")
    return f"{header}\n" + "\n".join(lines)


def _page_range(start: int | None, end: int | None) -> str:
    if start is None:
        return ""
    if end is None or end == start:
        return f" — page {start}"
    return f" — pages {start}-{end}"
