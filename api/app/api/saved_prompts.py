"""Saved-prompts endpoints — Task D7.

Per PRD §9 DE-013 / Issue 04: per-user saved prompts complement skills
the way bookmarks complement Knowledge Bases. CRUD is per-user (the
caller can only see/modify their own); listing is newest-first by
``updated_at``.

The router is mounted under :data:`ActiveUser` at the
``api_router.include_router`` site, so every handler here can take a
:data:`ActiveUser` dependency and be confident the bearer token is
valid + the must-change-password gate has cleared. Cross-user reads
are blocked by filtering on ``user_id`` rather than relying on the
gate alone — defense in depth, and the same pattern used by the chats
and projects routers.

Audit logging: PRD §5.3 calls out "every state-changing API call writes
to ``audit_log``." Saved-prompts mutations are user-scoped (no project
involvement, no privilege bearing), so audit rows here are
non-privilege-marked and ride the same single-transaction commit as
the state change.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser
from app.audit import audit_action
from app.db.session import get_db
from app.models.saved_prompt import SavedPrompt

router = APIRouter(prefix="/saved-prompts", tags=["saved-prompts"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


_NAME_MAX = 200
_PROMPT_MAX = 50_000
_TAG_MAX = 50
_MAX_TAGS = 20


class SavedPromptResponse(BaseModel):
    """Mirrors the ``SavedPrompt`` component in
    ``docs/api/backend-openapi.yaml``."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    prompt_text: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SavedPromptCreate(BaseModel):
    """POST body. ``tags`` is optional and normalised to ``[]`` if absent."""

    name: str = Field(min_length=1, max_length=_NAME_MAX)
    prompt_text: str = Field(min_length=1, max_length=_PROMPT_MAX)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAGS)


class SavedPromptUpdate(BaseModel):
    """PATCH body. Every field is optional — partial updates only touch
    the supplied keys, leaving the others as-stored."""

    name: str | None = Field(default=None, min_length=1, max_length=_NAME_MAX)
    prompt_text: str | None = Field(default=None, min_length=1, max_length=_PROMPT_MAX)
    tags: list[str] | None = Field(default=None, max_length=_MAX_TAGS)


def _validate_tags(tags: list[str]) -> list[str]:
    """Normalise + validate tag values.

    Each tag must be non-empty and at most ``_TAG_MAX`` chars after
    stripping. Duplicates are deduplicated (preserving first-seen
    order). Order otherwise reflects the caller's submission so users
    can curate display order.
    """

    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        if not isinstance(raw, str):
            raise HTTPException(
                status_code=422,
                detail="tag values must be strings",
            )
        tag = raw.strip()
        if not tag:
            raise HTTPException(
                status_code=422,
                detail="tag values must be non-empty",
            )
        if len(tag) > _TAG_MAX:
            raise HTTPException(
                status_code=422,
                detail=f"tag values must be at most {_TAG_MAX} characters",
            )
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def _to_response(prompt: SavedPrompt) -> SavedPromptResponse:
    return SavedPromptResponse(
        id=prompt.id,
        user_id=prompt.user_id,
        name=prompt.name,
        prompt_text=prompt.prompt_text,
        tags=list(prompt.tags or []),
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


async def _load_owned(
    db: AsyncSession, *, prompt_id: uuid.UUID, user_id: uuid.UUID
) -> SavedPrompt:
    """Fetch a saved prompt by id; 404 if missing OR owned by another user.

    Conflating "doesn't exist" and "exists but belongs to someone else"
    avoids leaking the existence of other users' prompts via id-probing.
    The chats/projects routers use the same pattern.
    """

    stmt = select(SavedPrompt).where(
        SavedPrompt.id == prompt_id, SavedPrompt.user_id == user_id
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="saved prompt not found"
        )
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[SavedPromptResponse],
    summary="List the calling user's saved prompts (newest first)",
)
async def list_prompts(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SavedPromptResponse]:
    """GET /api/v1/saved-prompts — all of the caller's saved prompts.

    Sorted by ``updated_at DESC`` so the most recently touched prompt
    appears first; the ``(user_id, updated_at DESC)`` index covers
    this query.
    """

    # Secondary sort by id breaks ties when two rows share an
    # updated_at value (clock-resolution collisions, batch imports,
    # tests that use transaction-bound now()), so list ordering is
    # deterministic for the UI's stable-key rendering.
    stmt = (
        select(SavedPrompt)
        .where(SavedPrompt.user_id == user.id)
        .order_by(SavedPrompt.updated_at.desc(), SavedPrompt.id.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows]


@router.post(
    "",
    response_model=SavedPromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new saved prompt for the calling user",
)
async def create_prompt(
    payload: SavedPromptCreate,
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SavedPromptResponse:
    """POST /api/v1/saved-prompts — create + return the new row."""

    tags = _validate_tags(payload.tags)
    prompt = SavedPrompt(
        user_id=user.id,
        name=payload.name.strip(),
        prompt_text=payload.prompt_text,
        tags=tags,
    )
    db.add(prompt)
    await db.flush()

    await audit_action(
        db,
        user_id=user.id,
        action="saved_prompt.create",
        resource_type="saved_prompt",
        resource_id=str(prompt.id),
        request=request,
        details={"name": prompt.name, "tags": tags},
    )
    await db.commit()
    await db.refresh(prompt)

    return _to_response(prompt)


@router.get(
    "/{prompt_id}",
    response_model=SavedPromptResponse,
    summary="Fetch a single saved prompt (owner-only)",
    responses={404: {"description": "Saved prompt not found"}},
)
async def get_prompt(
    prompt_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SavedPromptResponse:
    """GET /api/v1/saved-prompts/{id} — single prompt by id.

    Returns 404 if the id doesn't exist OR belongs to another user;
    see :func:`_load_owned`.
    """

    prompt = await _load_owned(db, prompt_id=prompt_id, user_id=user.id)
    return _to_response(prompt)


@router.patch(
    "/{prompt_id}",
    response_model=SavedPromptResponse,
    summary="Update a saved prompt (partial; owner-only)",
    responses={404: {"description": "Saved prompt not found"}},
)
async def update_prompt(
    prompt_id: uuid.UUID,
    payload: SavedPromptUpdate,
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SavedPromptResponse:
    """PATCH /api/v1/saved-prompts/{id} — partial update."""

    prompt = await _load_owned(db, prompt_id=prompt_id, user_id=user.id)

    changed: dict[str, object] = {}
    if payload.name is not None:
        new_name = payload.name.strip()
        if new_name != prompt.name:
            prompt.name = new_name
            changed["name"] = new_name
    if payload.prompt_text is not None and payload.prompt_text != prompt.prompt_text:
        prompt.prompt_text = payload.prompt_text
        changed["prompt_text_length"] = len(payload.prompt_text)
    if payload.tags is not None:
        new_tags = _validate_tags(payload.tags)
        if new_tags != list(prompt.tags or []):
            prompt.tags = new_tags
            changed["tags"] = new_tags

    if not changed:
        # No-op PATCH: return current state without an audit row to avoid
        # log churn on idempotent re-saves from the UI.
        return _to_response(prompt)

    await audit_action(
        db,
        user_id=user.id,
        action="saved_prompt.update",
        resource_type="saved_prompt",
        resource_id=str(prompt.id),
        request=request,
        details={"changed_fields": sorted(changed.keys())},
    )
    await db.commit()
    await db.refresh(prompt)

    return _to_response(prompt)


@router.delete(
    "/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved prompt (owner-only)",
    responses={404: {"description": "Saved prompt not found"}},
)
async def delete_prompt(
    prompt_id: uuid.UUID,
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """DELETE /api/v1/saved-prompts/{id} — owner-only delete."""

    prompt = await _load_owned(db, prompt_id=prompt_id, user_id=user.id)

    await db.delete(prompt)
    await audit_action(
        db,
        user_id=user.id,
        action="saved_prompt.delete",
        resource_type="saved_prompt",
        resource_id=str(prompt_id),
        request=request,
        details={"name": prompt.name},
    )
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
