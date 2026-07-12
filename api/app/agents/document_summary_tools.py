"""Document-summary agent tool — WORKSPACE-1 (fork, ADR-F082): per-document summaries.

The workspace-awareness tier's ONE agent write tool: :func:`record_document_summary`. After the
agent reads a document it records a short summary against that file, so future runs — and the
lawyer, in the Documents panel — recognise the document by content, not just its filename. Exact-
duplicate awareness is separate and code-computed (:func:`app.agents.tools.duplicate_of_map`): the
agent DESCRIBES a document, it never ASSERTS that two files are the same (a hostile document could
forge that; exact duplicates are proven from the content hash, not the model's word).

The write is code-validated (ADR-F018 shape) through ``guarded_dispatch`` (R6 grant / R5 halt /
R4 cost): the proposed summary is validated against
:class:`app.schemas.document_summary.RecordDocumentSummaryInput` (reject blank / over the cap), the
named file is resolved under matter+owner scope, and its ``summary`` is written in place with the
run id + timestamp. Auto-write-then-correct (ADR-F042): the agent maintains it; the human owns it
after (re-recording overwrites). There is NO domain audit row — the guard envelope (counts/IDs,
``result_chars`` not body) is the only receipt, so no summary or document text leaks into audit.

Area-agnostic — every matter-bound run (any practice area) gets this tool; its grant set is
disjoint from the matter-memory / ROPA / assessment / commercial domain grants (confinement).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import (
    MatterBinding,
    _DupRow,
    _matter_files_query,
    _provenance,
    duplicate_groups_from_rows,
    resolve_matter_file_by_name,
    summary_with_staleness,
)
from app.models.document import Document
from app.models.file import File
from app.schemas.document_summary import RecordDocumentSummaryInput

DOCUMENT_SUMMARY_TOOL_NAMES = frozenset({"record_document_summary"})

# WORKSPACE-2 (ADR-F082): bounds for the injected "Documents in this matter" tier block.
# A matter can hold ~1000 files (ADR-F049) — an unbounded per-file block would blow the
# prompt, so we keep the most-recently-touched N within a char budget and make truncation
# VISIBLE (a "+K more" tail), mirroring the corrections-injection precedent
# (``matter_memory_tools.MATTER_CORRECTIONS_INJECT_*``). The full list stays available
# on demand via search_documents (empty query).
MATTER_DOCUMENTS_INJECT_LIMIT = 30
MATTER_DOCUMENTS_INJECT_MAX_CHARS = 8_000


def build_document_summary_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the document-summary write tool for one matter-bound run (any area).

    The guard context grants exactly :data:`DOCUMENT_SUMMARY_TOOL_NAMES` (R6's grant set);
    the matter (``binding.project_id``) + owner scope the write — the blast radius is one file
    in this one matter.
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=DOCUMENT_SUMMARY_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def record_document_summary(document_name: str, summary: str) -> str:
        """Record a one-line summary of a document AFTER reading it for the first time.

        A single plain sentence or two: what kind of document it is, the parties, its purpose,
        anything notable — stored against the filename so you and the supervising lawyer
        recognise the document by content later, and a future run starts from what is already
        known without re-reading. SKIP this when the document listing already shows an accurate
        summary for the file — do not re-record what has not changed. Re-record only when your
        understanding materially changed (you read it more deeply, or the document itself
        changed). If the supervising lawyer has set a file's summary themselves, it is theirs —
        your write will be refused. This is a description of the document — obligations, dates
        and decisions belong in the matter memory, not here.

        ``document_name`` is the filename exactly as shown by search_documents.
        """
        return await guarded_dispatch(
            "record_document_summary",
            lambda db: _record_document_summary(
                db, binding, run_id=run_id, document_name=document_name, summary=summary
            ),
            ctx,
        )

    return [record_document_summary]


async def _record_document_summary(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    run_id: uuid.UUID,
    document_name: str,
    summary: str,
) -> str:
    """Validate → resolve the named file (matter+owner scope) → write the summary in place.

    Reject (return a fix-and-retry string), never sanitize/truncate (ADR-F018/F042). Writes only
    the file's ``summary`` fields — never a matter-memory or correction row.
    """
    try:
        proposal = RecordDocumentSummaryInput(document_name=document_name, summary=summary)
    except ValidationError as exc:
        return _rejection_text(exc)

    match = await resolve_matter_file_by_name(db, binding, proposal.document_name)
    if match is None:
        return (
            f'No document named "{proposal.document_name}" in this matter. Use search_documents '
            "(empty query) to list the matter's documents, then use the name exactly as shown. "
            "Nothing was recorded."
        )

    # Re-load the file as a writable ORM row under owner scope in THIS guarded session (defense in
    # depth — the resolver returned a read projection). Soft-deleted / vanished between resolve and
    # write ⇒ record nothing.
    file = (
        await db.execute(
            select(File).where(
                File.id == match.id,
                File.owner_id == binding.user_id,
                File.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if file is None:
        return "That document is no longer available; nothing was recorded."

    # ADR-F042 pins win: a summary the supervising lawyer set themselves is theirs — the
    # agent's auto-write may never overwrite it (structural, not prompt-enforced).
    if file.summary_author == "human":
        return (
            f'The supervising lawyer has set the summary for "{file.filename}" themselves; '
            "it was not changed. Work with their description."
        )

    file.summary = proposal.summary
    file.summary_updated_at = datetime.now(tz=UTC)
    file.summary_run_id = run_id
    file.summary_author = "agent"
    await db.flush()

    return (
        f'Recorded a summary for "{file.filename}". It is saved and will help you and the '
        "supervising lawyer recognise this document by content in future runs."
    )


def _rejection_text(exc: ValidationError) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no body echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(summary)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        "Document summary not recorded — the proposal was rejected. Nothing was written. Fix the "
        "following and call record_document_summary again:\n" + "\n".join(problems)
    )


# Per-line clamp: filenames have no length cap at any boundary, so a single pathological
# name could otherwise ship an uncapped first line into every run's prompt (review finding,
# PR #271). Summary (≤600) + a real filename fit comfortably; the ellipsis is honest.
_MATTER_DOCUMENTS_LINE_MAX_CHARS = 900


async def load_matter_documents_block(db: AsyncSession, binding: MatterBinding) -> str | None:
    """Render the bounded "Documents in this matter" tier body (WORKSPACE-2), or ``None``.

    One line per live matter file — ``filename — (duplicate of X) — description`` (the same
    field order the inventory renders, pinned by test) — most recently touched first
    (``coalesce(updated_at, created_at)``, the F066 recency convention). The description is the
    agent-recorded summary (with an honest staleness suffix when the bytes changed after it was
    written); for a file with NO summary it is the F066 provenance for non-readable rows (an
    agent work product / editor snapshot / failed ingest is NOT "not yet read" — telling the
    model its own output is an unread source misleads it), and ``not yet read`` only for a
    genuinely readable-but-unread document. Bounded by :data:`MATTER_DOCUMENTS_INJECT_LIMIT` /
    :data:`MATTER_DOCUMENTS_INJECT_MAX_CHARS` with a per-line clamp; truncation is VISIBLE
    (a ``+K more`` tail pointing at search_documents), never silent. ``None`` for a matter with
    no files (the tier degrades to nothing; the composed prompt is byte-identical).
    """
    rows = (
        await db.execute(
            _matter_files_query(
                binding,
                File.id.label("file_id"),
                File.filename,
                File.summary,
                File.summary_updated_at,
                File.created_at,
                File.updated_at,
                File.hash_sha256,
                File.ingestion_status,
                File.parent_file_id,
                File.is_snapshot,
                File.created_by_run_id,
                Document.id,
            ).order_by(func.coalesce(File.updated_at, File.created_at).desc(), File.id.desc())
        )
    ).all()
    if not rows:
        return None
    dup = duplicate_groups_from_rows(
        [_DupRow(r.file_id, r.filename, r.hash_sha256, r.created_at) for r in rows]
    )
    # Provenance labels for non-ingested rows (F066 posture, mirrors _inventory): resolve
    # parent filenames in ONE batched matter-scoped query; a vanished parent degrades cleanly.
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
    total = 0
    for row in rows:
        if len(lines) >= MATTER_DOCUMENTS_INJECT_LIMIT:
            break
        if row.summary:
            description = summary_with_staleness(row)
        elif row.id is None:
            # No summary and not readable: honest provenance, never "not yet read".
            description = _provenance(row, parent_names)
        else:
            description = "not yet read"
        marker = f" — (duplicate of {dup[row.file_id][1]})" if row.file_id in dup else ""
        line = f"- {row.filename}{marker} — {description}"
        if len(line) > _MATTER_DOCUMENTS_LINE_MAX_CHARS:
            line = line[: _MATTER_DOCUMENTS_LINE_MAX_CHARS - 1] + "…"
        if lines and total + len(line) + 1 > MATTER_DOCUMENTS_INJECT_MAX_CHARS:
            break
        lines.append(line)
        total += len(line) + 1
    remaining = len(rows) - len(lines)
    if remaining > 0:
        lines.append(f"(+{remaining} more — use search_documents with an empty query to list all)")
    return "\n".join(lines)
