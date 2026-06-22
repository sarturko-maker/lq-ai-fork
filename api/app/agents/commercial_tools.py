"""Commercial agent tools — C4 (ADR-F031/F035): the surgical-redline write path.

The Commercial Deep Agent's one domain tool so far is :func:`apply_redline` — the
**code-validated write** that turns the model's proposed narrow edits into a
native tracked-changes ``.docx`` via Adeu. The loop is the ADR-F018 shape the
ROPA/assessment tools use: the model PROPOSES, code DISPOSES against the
measurable surgical gate (:mod:`app.schemas.commercial`), Adeu renders the
survivors, and the **human owns** the accept (the redline is saved as a
downloadable matter document with tracked changes — the supervisor accepts/rejects
each change in Word). Reject, never silently fix.

**Matter-scoped (ADR-F035).** Unlike the deployment-global ROPA register
(ADR-F019), Commercial records are matter-scoped: the source document is fetched
under ``binding`` (owner + matter, 404-conflated cross-user) and the redlined
output is written back into the *same* matter. Cross-deal leakage is a security
boundary, not a style choice.

**Egress.** Adeu makes zero network calls; it is wrapped behind ``guarded_dispatch``
(R6 grant / R5 halt / R4 cost) like every agent action. The audit row carries
counts/types/IDs only — never ``target_text``/``new_text``/clause content.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import storage
from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.redline_service import ProposedEdit, RedlineService
from app.agents.tools import MatterBinding, _matter_files_query
from app.audit import audit_action
from app.models.document import Document
from app.models.file import File
from app.models.project import ProjectFile
from app.pipeline.readers._base import OOXML_DOCX_MIME, guard_ooxml, ooxml_subtype
from app.schemas.commercial import ApplyRedlineInput, evaluate_gate

logger = logging.getLogger(__name__)

# The stable key of the Commercial practice area (migration 0054). The
# composition point grants the Commercial tools only to a matter filed under this
# area — the first Commercial domain-tool grant branch (mirrors PRIVACY_AREA_KEY).
COMMERCIAL_AREA_KEY = "commercial"

COMMERCIAL_TOOL_NAMES = frozenset({"apply_redline"})

# Defense cap on the original .docx we'll load into memory + redline. The upload
# cap is larger; a deal contract is well under this.
_MAX_DOCX_BYTES = 25 * 1024 * 1024


def build_commercial_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
    redline_service: RedlineService,
) -> list[Callable[..., Any]]:
    """Build the Commercial matter's guarded tools for one run.

    ``redline_service`` is the injected Adeu adapter (provider-callable from
    ``composition.py``; tests pass a fake). The guard context grants exactly the
    Commercial tool names; the matter (``binding.project_id``) scopes both the
    source-document fetch and the redlined output (ADR-F035).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=COMMERCIAL_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def apply_redline(document_name: str, edits: list[dict[str, Any]]) -> str:
        """Redline one of this matter's ``.docx`` documents with tracked changes.

        Propose a batch of NARROW edits; each becomes native Word tracked changes
        the supervisor reviews and accepts/rejects. The redlined document is saved
        back into this matter for download.

        IMPORTANT — batch your edits: pass ALL the edits for a document in a
        SINGLE call. Each call redlines the *named* document afresh and saves a new
        redlined copy; calling again does NOT stack on your previous output (it
        re-redlines the original). So review the whole document first, then make one
        apply_redline call covering every change.

        Redline like a lawyer (this is enforced — over-broad edits are rejected):
        - **One narrow edit per discrete change.** Change the few words that need
          changing; never restate a whole sentence/clause to alter part of it.
        - **Balance a one-sided clause; don't rip-and-replace it.** Against a
          vendor-favoured cap, weave in protection through the right mechanism —
          carve high-risk heads of loss (confidentiality, data protection, IP,
          indemnified claims) OUT of the cap or under a super-cap; deem key losses
          direct; read the whole agreement. Bumping a number is the naive move.
        - **You supply the replacement language.** Never delete substantive text
          and leave a gap — put the redrafted wording in ``new_text``.
        - **Explain substantive changes.** A change to an obligation, amount,
          period, or defined term needs a ``rationale`` (it becomes a Word comment).

        Each edit is an object:
        - ``target_text`` (required): the EXACT existing text to change — must
          appear once in the document (quote a longer span if it's not unique).
        - ``new_text``: the replacement (omit/empty only for a non-substantive
          deletion).
        - ``rationale``: why the change protects the client (required for
          substantive edits; ≥15 words).
        - ``rewrite_justified``: set true only when a full-clause rewrite is
          genuinely necessary (and still give the reason in ``rationale``).
        """
        return await guarded_dispatch(
            "apply_redline",
            lambda db: _apply_redline(
                db,
                binding,
                document_name=document_name,
                edits=edits,
                service=redline_service,
            ),
            ctx,
        )

    return [apply_redline]


async def _apply_redline(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    document_name: str,
    edits: list[dict[str, Any]],
    service: RedlineService,
) -> str:
    """Validate → gate → decompose → dry-run → apply → persist (or reject)."""
    # 1. Per-edit, document-free gate (D2/D3) + shape (reject, don't sanitize).
    try:
        proposal = ApplyRedlineInput(document_name=document_name, edits=edits)  # type: ignore[arg-type]
    except ValidationError as exc:
        return _rejection_text(exc)

    # 2. Fetch the source .docx under matter scope (404-conflated cross-user).
    row = await _fetch_matter_docx(db, binding, proposal.document_name)
    if row is None:
        return (
            f'No document named "{proposal.document_name}" in this matter. Use '
            "search_documents (empty query) to list the matter's documents."
        )
    if row.mime_type != OOXML_DOCX_MIME:
        return (
            f'"{row.filename}" is not a Word .docx (it is {row.mime_type}). '
            "apply_redline only redlines .docx documents."
        )

    data = await _download_docx(row.storage_path)
    if data is None:
        return (
            f'"{row.filename}" could not be read from storage. Try again shortly '
            "or pick another document."
        )
    # Content sniff + OOXML hardening on untrusted bytes (XXE / zip-bomb) — fail
    # closed. guard_ooxml RAISES on a hostile/invalid container (returns None on OK).
    if ooxml_subtype(data) != "docx":
        return f'"{row.filename}" is not a valid .docx and was not redlined.'
    try:
        guard_ooxml(data)
    except Exception:
        logger.warning(
            "apply_redline source failed OOXML safety checks",
            extra={"event": "redline_source_unsafe_ooxml"},
        )
        return f'"{row.filename}" failed .docx safety checks and was not redlined.'

    document_text = (row.normalized_content or "").strip() or _extract_docx_text(data)
    if not document_text:
        return (
            f'"{row.filename}" has no extractable text yet (ingestion pending or '
            "failed); cannot place edits. Try again shortly."
        )

    # 3. Document-relative gate (D1/D4/D5).
    report = evaluate_gate(document_text, proposal.edits)
    if not report.ok:
        return report.rejection_text()

    # 4. Build the logical edits; the service decomposes them into fresh minimal
    #    regions on each call (most surgical render; fresh objects sidestep Adeu's
    #    process_batch mutation cycle).
    logical = [
        ProposedEdit(e.target_text, e.new_text, e.rationale.strip() or None) for e in proposal.edits
    ]

    # 5. D6: mandatory dry-run self-review. Any edit Adeu can't place (anchor not
    #    found in the document's runs) blocks the write — never a partial redline.
    preview = service.dry_run(data, logical)
    if preview.edits_applied == 0:
        return (
            "No changes could be applied — nothing was written. Re-quote the exact "
            "existing text in target_text."
        )
    if preview.edits_skipped > 0:
        return (
            f"{preview.edits_skipped} edit region(s) could not be located in the "
            "document (anchors not found in the underlying text). Nothing was "
            "written — re-quote the exact existing text in target_text."
        )

    # 6. Apply for real → redlined .docx bytes.
    result = service.apply(data, logical)
    redlined = result.docx_bytes

    # 7. Persist as a new matter document (ready; not re-ingested — work product,
    #    not a search source). Flush BEFORE the object PUT so a constraint failure
    #    rolls the row back without orphaning bytes (ADR 0005 GC reaps the rare
    #    commit-after-PUT orphan).
    new_file_id = uuid.uuid4()
    redlined_name = _redlined_filename(row.filename)
    file_row = File(
        id=new_file_id,
        owner_id=binding.user_id,
        project_id=binding.project_id,
        filename=redlined_name,
        mime_type=OOXML_DOCX_MIME,
        size_bytes=len(redlined),
        hash_sha256=hashlib.sha256(redlined).hexdigest(),
        storage_path=str(new_file_id),
        ingestion_status="ready",
    )
    db.add(file_row)
    await db.flush()
    await storage.upload_bytes(
        storage_path=str(new_file_id), body=redlined, content_type=OOXML_DOCX_MIME
    )

    # Domain receipt — counts/types/IDs only (no clause text); the guard also
    # writes its generic tool_call row.
    await audit_action(
        db,
        user_id=binding.user_id,
        action="commercial.redline_applied",
        resource_type="file",
        resource_id=str(new_file_id),
        project_id=binding.project_id,
        practice_area_id=binding.practice_area_id,
        details={
            "source_file_id": str(row.file_id),
            "proposed_edits": len(proposal.edits),
            "applied_regions": result.edits_applied,
        },
    )

    return (
        f"Applied {len(proposal.edits)} edit(s) ({result.edits_applied} tracked "
        f'change region(s)) to "{row.filename}". Saved the redlined document as '
        f'"{redlined_name}" in this matter — download it to review and accept or '
        f"reject each change. Every change is tracked; substantive ones carry a "
        f"comment explaining the rationale."
    )


async def _fetch_matter_docx(
    db: AsyncSession, binding: MatterBinding, document_name: str
) -> Row[Any] | None:
    """Resolve one matter document by filename (owner + matter scoped).

    Mirrors ``read_document``'s resolution: prefer an ingested (readable) copy,
    then the most recently added. Returns ``None`` when no such document exists
    in this matter (cross-user is the same 404-conflated absence — ADR-F035).
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


async def _download_docx(storage_path: str) -> bytes | None:
    """Buffer the original .docx bytes from object storage (size-capped)."""
    chunks: list[bytes] = []
    total = 0
    try:
        async with storage.stream_download(storage_path=storage_path) as stream:
            async for chunk in stream:
                total += len(chunk)
                if total > _MAX_DOCX_BYTES:
                    logger.warning(
                        "apply_redline source exceeds cap",
                        extra={"event": "redline_source_too_large", "bytes": total},
                    )
                    return None
                chunks.append(chunk)
    except Exception:
        logger.warning(
            "apply_redline source download failed",
            extra={"event": "redline_source_download_failed"},
        )
        return None
    return b"".join(chunks)


def _extract_docx_text(data: bytes) -> str:
    """Fallback full-text extraction (when the doc carries no normalized_content),
    via the C1 DocxReader so the gate sees the same text the agent would."""
    try:
        from app.pipeline.readers.docx import DocxReader

        return DocxReader().read(data).canonical_text
    except Exception:
        return ""


def _redlined_filename(original: str) -> str:
    """``contract.docx`` → ``contract (redlined).docx`` (keeps the extension)."""
    stem, dot, ext = original.rpartition(".")
    if dot and ext.lower() == "docx":
        return f"{stem} (redlined).{ext}"
    return f"{original} (redlined).docx"


def _rejection_text(exc: ValidationError) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no clause echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(edit)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        "Redline rejected — the proposed edits do not satisfy the surgical rules. "
        "Nothing was written. Fix the following and call apply_redline again:\n"
        + "\n".join(problems)
    )
