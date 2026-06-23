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
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser
from app.api.projects import _load_visible_project
from app.audit import audit_action
from app.db.session import get_db
from app.models.project import MatterMemoryEntry

router = APIRouter(prefix="/matters", tags=["matter-memory"])

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
