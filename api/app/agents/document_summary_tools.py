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
    _matter_files_query,
    duplicate_of_map,
    resolve_matter_file_by_name,
)
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
        """Record a short summary of a document you have READ, against its name.

        Call this once you have read a document and understood what it is: a one or two sentence
        description of the document (what kind of document it is, the parties, its purpose, anything
        notable), stored against the filename. It helps you and the supervising lawyer recognise the
        document by content later, and lets a future run start from what is already known without
        re-reading. Keep it short and factual, well under the length limit; recording it again
        overwrites the previous summary. This is a description of the document — obligations,
        dates and decisions belong in the matter memory, not here.

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

    file.summary = proposal.summary
    file.summary_updated_at = datetime.now(tz=UTC)
    file.summary_run_id = run_id
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


async def load_matter_documents_block(db: AsyncSession, binding: MatterBinding) -> str | None:
    """Render the bounded "Documents in this matter" tier body (WORKSPACE-2), or ``None``.

    One line per live matter file — filename, the agent-recorded summary (or an honest
    ``not yet read``), and the code-computed exact-duplicate marker — most recently touched
    first (``coalesce(updated_at, created_at)``, the F066 recency convention). Bounded by
    :data:`MATTER_DOCUMENTS_INJECT_LIMIT` / :data:`MATTER_DOCUMENTS_INJECT_MAX_CHARS`;
    truncation is VISIBLE (a ``+K more`` tail pointing at search_documents), never silent —
    a capped list that reads as complete would mislead the agent about the workspace.
    ``None`` for a matter with no files (the tier degrades to nothing; the composed prompt
    is byte-identical to the pre-slice text).
    """
    rows = (
        await db.execute(
            _matter_files_query(
                binding, File.id, File.filename, File.summary, File.created_at, File.updated_at
            ).order_by(func.coalesce(File.updated_at, File.created_at).desc(), File.id.desc())
        )
    ).all()
    if not rows:
        return None
    dup = await duplicate_of_map(db, binding)
    lines: list[str] = []
    total = 0
    for row in rows:
        if len(lines) >= MATTER_DOCUMENTS_INJECT_LIMIT:
            break
        summary = (row.summary or "").strip() or "not yet read"
        marker = f" — (duplicate of {dup[row.id][1]})" if row.id in dup else ""
        line = f"- {row.filename} — {summary}{marker}"
        if lines and total + len(line) + 1 > MATTER_DOCUMENTS_INJECT_MAX_CHARS:
            break
        lines.append(line)
        total += len(line) + 1
    remaining = len(rows) - len(lines)
    if remaining > 0:
        lines.append(f"(+{remaining} more — use search_documents with an empty query to list all)")
    return "\n".join(lines)
