"""Matter-memory endpoints — C3a (fork, ADR-F042): the human-authenticated pin.

The unit-of-work memory tier is **auto-write-then-correct**: the agent maintains the
matter wiki automatically (``update_matter_memory``), and the supervising lawyer
*corrects* it. A correction is an **enforced, un-overwritable** record — the agent's
auto-curation may never alter or drop it — so its ``trust='human-pinned'`` label must
be *structurally* true, not claimed by a writer. This endpoint is therefore the
**only** writer of a ``human-pinned`` entry: ``author`` (``user_id``) comes from the
authenticated session, never from agent/model input. An agent-asserted "the lawyer
said X" is untrusted, forgeable by document/prompt injection (ADR-F042 §Decision; B2),
so no agent-granted tool can mint a pin — only an authenticated human action here can.

**Per-user isolation.** The matter is loaded via the projects ``_load_visible_project``
rule: owner-scoped, archived-excluded, **404** on miss / cross-user / archived (never
403 — no existence leak), the same posture as the rest of the project surface.

Audited (``matter_memory.pin``) with counts/IDs only — never the correction body
(audit contract, ADR-F005 / 0013 D6). The seamless "correct in chat" cockpit UX is
C3c; C3a ships the safe enforced-correction primitive.

C3c-1 (ADR-F044) adds the **read + revert** half on the same owner-scoped router:

* ``GET /matters/{project_id}/memory`` — the read-only projection that feeds the
  cockpit memory panel (the current wiki + the live fact ledger + the live pinned
  corrections + the append-only log, capped + counted). It reuses the agent layer's
  tested read substrate (``live_facts`` / ``memory_log``) — a deliberate, narrow
  api→agents read edge (no guard needed: the route's own ``ActiveUser`` +
  ``_load_visible_project`` authz governs it).
* ``POST /matters/{project_id}/memory/wiki/revert`` — the human-authenticated "undo":
  restore the wiki to a chosen prior version. The current wiki is snapshotted FIRST (so
  the revert is itself reversible) and nothing is deleted (append-only). The agent has
  no revert tool — only an authenticated human action here can revert (ADR-F044).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.matter_fact_tools import live_facts, memory_log
from app.agents.matter_memory_tools import snapshot_and_rewrite_wiki
from app.api.dependencies import ActiveUser
from app.api.projects import _load_visible_project
from app.audit import audit_action
from app.db.session import get_db
from app.errors import NotFound
from app.models.project import MatterMemoryEntry

router = APIRouter(prefix="/matters", tags=["matter-memory"])

# C3c-1 (ADR-F044): the GET returns the most recent slice of the (append-only) log with
# a total count — the panel knows older entries exist without loading the whole history.
MEMORY_LOG_TAIL = 200
# Each log entry carries a bounded body preview (a wiki snapshot can be the full wiki
# budget); the live facts + corrections are returned in full (each is short, ≤ 4 000).
LOG_BODY_PREVIEW_CHARS = 280

# Boundary cap on a single correction (reject, don't truncate). A correction is a
# short, durable instruction-of-record ("we are the buyer; counterparty counsel is
# Smith Crowell"), not an essay; well under the DB body cap.
CORRECTION_MAX_CHARS = 4_000


class CorrectionCreateRequest(BaseModel):
    """``POST /api/v1/matters/{project_id}/memory/corrections`` body.

    ``str_strip_whitespace`` trims first, so a whitespace-only body collapses to
    "" and fails ``min_length=1`` with a 422 (reject at the boundary — never reach
    the DB CHECK as a 500). Reject, don't sanitize.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    body_md: str = Field(min_length=1, max_length=CORRECTION_MAX_CHARS)


class CorrectionResponse(BaseModel):
    """One recorded pinned correction (the enforced, un-overwritable record)."""

    id: uuid.UUID
    project_id: uuid.UUID
    body_md: str
    trust: str
    created_at: datetime


@router.post(
    "/{project_id}/memory/corrections",
    status_code=status.HTTP_201_CREATED,
    response_model=CorrectionResponse,
)
async def create_matter_correction(
    project_id: uuid.UUID,
    payload: CorrectionCreateRequest,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> CorrectionResponse:
    """Record a supervising-lawyer correction for a matter — the only pin writer.

    The matter must be the caller's own active project (404 otherwise). The entry is
    written with ``trust='human-pinned'`` and ``user_id`` from the session; the
    agent's auto-curation cannot create or overwrite it.
    """
    # 404 on miss / cross-user / archived (no existence leak) — projects posture.
    project = await _load_visible_project(db, project_id, user.id)

    entry = MatterMemoryEntry(
        project_id=project.id,
        user_id=user.id,
        kind="correction",
        body_md=payload.body_md,  # already stripped + min_length-validated at the boundary
        trust="human-pinned",
        run_id=None,
    )
    db.add(entry)
    await db.flush()
    # Capture the persisted values (incl. the server-default created_at) BEFORE the
    # commit, so building the response never triggers an attribute reload after
    # commit (the async lazy-load-after-commit pitfall).
    response = CorrectionResponse(
        id=entry.id,
        project_id=entry.project_id,
        body_md=entry.body_md,
        trust=entry.trust,
        created_at=entry.created_at,
    )

    # Counts/IDs only — never the correction body (audit contract).
    await audit_action(
        db,
        user_id=user.id,
        action="matter_memory.pin",
        resource_type="project",
        resource_id=str(project.id),
        project=project,
        request=request,
        details={"entry_id": str(response.id), "body_chars": len(response.body_md)},
    )
    await db.commit()

    return response


# --- C3c-1 (ADR-F044): the read surface + the human-authenticated wiki revert ------


class WikiRead(BaseModel):
    """The matter's current wiki + how many prior (revertable) versions exist."""

    content_md: str
    char_count: int
    version_count: int  # count of wiki_snapshot rows = revertable prior versions


class FactRead(BaseModel):
    """One LIVE typed fact (the current ledger; superseded facts are excluded)."""

    id: uuid.UUID
    body_md: str
    fact_type: str | None
    source_citation: str | None
    author: str | None
    valid_at: datetime | None
    created_at: datetime


class CorrectionRead(BaseModel):
    """One LIVE pinned correction (the supervising lawyer's enforced record)."""

    id: uuid.UUID
    body_md: str
    trust: str
    created_at: datetime


class LogEntryRead(BaseModel):
    """One append-only log entry (any kind), with a bounded body preview + provenance.

    ``superseded`` is true when a fact's window has closed (``invalid_at``) or a
    correction has been retired (``superseded_at``). The frontend offers wiki revert on
    ``kind == 'wiki_snapshot'`` rows (whose ``id`` is the revert target).
    """

    id: uuid.UUID
    kind: str
    created_at: datetime
    run_id: uuid.UUID | None
    author: str | None
    fact_type: str | None
    source_citation: str | None
    superseded: bool
    body_preview: str


class MatterMemoryRead(BaseModel):
    """The full read-only projection of one matter's working memory (C3c-2 panel)."""

    project_id: uuid.UUID
    wiki: WikiRead
    facts: list[FactRead]
    corrections: list[CorrectionRead]
    log: list[LogEntryRead]
    log_total: int


class WikiRevertRequest(BaseModel):
    """``POST /matters/{project_id}/memory/wiki/revert`` body."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: uuid.UUID


class WikiRevertResponse(BaseModel):
    """The outcome of a wiki revert: which version was restored + the new state."""

    reverted_to_snapshot_id: uuid.UUID
    snapshotted_prior: bool  # False only when the pre-revert wiki was blank (nothing to keep)
    wiki: WikiRead


def _log_entry(entry: MatterMemoryEntry) -> LogEntryRead:
    body = entry.body_md or ""
    preview = body[:LOG_BODY_PREVIEW_CHARS]
    if len(body) > LOG_BODY_PREVIEW_CHARS:
        preview = preview.rstrip() + "…"
    return LogEntryRead(
        id=entry.id,
        kind=entry.kind,
        created_at=entry.created_at,
        run_id=entry.run_id,
        author=entry.author,
        fact_type=entry.fact_type,
        source_citation=entry.source_citation,
        superseded=entry.invalid_at is not None or entry.superseded_at is not None,
        body_preview=preview,
    )


@router.get("/{project_id}/memory", response_model=MatterMemoryRead)
async def read_matter_memory(
    project_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MatterMemoryRead:
    """Read a matter's full working memory (wiki + live facts + pinned corrections + log).

    The read-only projection of the unit-of-work memory tier that feeds the cockpit
    memory panel. Owner-scoped (404 on miss / cross-user / archived). An
    empty-but-existing matter returns empty lists (not 404). Reuses the agent layer's
    tested read substrate so "live" here is identical to what the agent reads/consolidates.
    """
    project = await _load_visible_project(db, project_id, user.id)

    facts = await live_facts(db, project.id)
    log_rows = await memory_log(db, project.id)
    corrections = (
        (
            await db.execute(
                select(MatterMemoryEntry)
                .where(
                    MatterMemoryEntry.project_id == project.id,
                    MatterMemoryEntry.kind == "correction",
                    MatterMemoryEntry.superseded_at.is_(None),
                )
                .order_by(MatterMemoryEntry.created_at.asc(), MatterMemoryEntry.id.asc())
            )
        )
        .scalars()
        .all()
    )

    wiki_body = project.context_md or ""
    return MatterMemoryRead(
        project_id=project.id,
        wiki=WikiRead(
            content_md=wiki_body,
            char_count=len(wiki_body),
            version_count=sum(1 for e in log_rows if e.kind == "wiki_snapshot"),
        ),
        facts=[
            FactRead(
                id=f.id,
                body_md=f.body_md,
                fact_type=f.fact_type,
                source_citation=f.source_citation,
                author=f.author,
                valid_at=f.valid_at,
                created_at=f.created_at,
            )
            for f in facts
        ],
        corrections=[
            CorrectionRead(id=c.id, body_md=c.body_md, trust=c.trust, created_at=c.created_at)
            for c in corrections
        ],
        # Most-recent slice of the append-only log (chronological), with the total so the
        # panel knows older entries exist. Slice the TAIL — memory_log is oldest-first.
        log=[_log_entry(e) for e in log_rows[-MEMORY_LOG_TAIL:]],
        log_total=len(log_rows),
    )


@router.post("/{project_id}/memory/wiki/revert", response_model=WikiRevertResponse)
async def revert_matter_wiki(
    project_id: uuid.UUID,
    payload: WikiRevertRequest,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> WikiRevertResponse:
    """Revert a matter's wiki to a chosen prior version (human-authenticated; ADR-F044).

    Restore the body of a chosen ``wiki_snapshot`` into ``context_md``. The current wiki
    is snapshotted FIRST (so the revert is itself reversible) and nothing is deleted
    (append-only). Owner-scoped (404). The agent has no revert tool — only this
    authenticated human action can revert. Audited with IDs/counts only (never the body).
    """
    # 404 on miss / cross-user / archived (no existence leak) — projects posture.
    project = await _load_visible_project(db, project_id, user.id)

    # The snapshot must be a wiki_snapshot of THIS matter: id + project + kind together
    # block a cross-matter id, a non-snapshot row (a fact/correction id), and — via the
    # project load above — another user's matter. 404 on miss (no existence leak).
    snapshot = (
        await db.execute(
            select(MatterMemoryEntry).where(
                MatterMemoryEntry.id == payload.snapshot_id,
                MatterMemoryEntry.project_id == project.id,
                MatterMemoryEntry.kind == "wiki_snapshot",
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise NotFound(
            f"Wiki version {payload.snapshot_id} not found for this matter.",
            details={"snapshot_id": str(payload.snapshot_id)},
        )

    # Capture before commit (avoid the async lazy-load-after-commit pitfall).
    restored_body = snapshot.body_md
    snapshot_id = snapshot.id
    snapshotted_prior = bool((project.context_md or "").strip())

    # The shared helper snapshots the current wiki BEFORE overwriting — single-sourcing
    # "snapshot before overwrite" is exactly what makes this revert reversible.
    await snapshot_and_rewrite_wiki(
        db, project, run_id=None, user_id=user.id, new_content=restored_body
    )

    # Count revertable versions AFTER the new snapshot is flushed (still pre-commit).
    version_count = (
        await db.execute(
            select(func.count())
            .select_from(MatterMemoryEntry)
            .where(
                MatterMemoryEntry.project_id == project.id,
                MatterMemoryEntry.kind == "wiki_snapshot",
            )
        )
    ).scalar_one()

    # Counts/IDs only — never the wiki body (audit contract).
    await audit_action(
        db,
        user_id=user.id,
        action="matter_memory.wiki_revert",
        resource_type="project",
        resource_id=str(project.id),
        project=project,
        request=request,
        details={
            "reverted_to_snapshot_id": str(snapshot_id),
            "new_chars": len(restored_body),
            "snapshotted_prior": snapshotted_prior,
        },
    )
    await db.commit()

    return WikiRevertResponse(
        reverted_to_snapshot_id=snapshot_id,
        snapshotted_prior=snapshotted_prior,
        wiki=WikiRead(
            content_md=restored_body,
            char_count=len(restored_body),
            version_count=version_count,
        ),
    )
