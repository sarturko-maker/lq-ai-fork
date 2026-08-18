"""Pydantic wire shapes for the admin ``/admin/intake-mailboxes`` CRUD surface — INTAKE-1 (ADR-F086).

Mirrors the shape of ``app.schemas.intake_bridges`` (the sibling admin
surface for the Slack/Teams OAuth bridges) but for the mailbox-to-
practice-area binding the plan calls for: one mailbox binds to one
practice area and one owner user (the queue owner — owns every candidate
matter/run this mailbox produces and gives every approval in v1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agent_runs import BudgetProfile

_PROVIDER_MAX_LEN = 50
_INBOX_ID_MAX_LEN = 500
_ADDRESS_MAX_LEN = 320


class IntakeMailboxCreate(BaseModel):
    """Body for ``POST /admin/intake-mailboxes``."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="agentmail", min_length=1, max_length=_PROVIDER_MAX_LEN)
    inbox_id: str = Field(..., min_length=1, max_length=_INBOX_ID_MAX_LEN)
    address: str = Field(..., min_length=1, max_length=_ADDRESS_MAX_LEN)
    practice_area_id: uuid.UUID
    owner_user_id: uuid.UUID
    default_budget_profile: BudgetProfile | None = None
    max_steps: int | None = Field(default=None, ge=1, le=600)


class IntakeMailboxUpdate(BaseModel):
    """Body for ``PATCH /admin/intake-mailboxes/{id}``.

    Every field is optional; only fields the caller actually sets are
    applied (``model_dump(exclude_unset=True)`` at the handler, the same
    partial-update idiom ``app.api.projects.update_project`` uses).
    Deliberately excludes ``provider``/``inbox_id``/``address`` — the
    provider binding is create-only; rebind by deleting and recreating.
    """

    model_config = ConfigDict(extra="forbid")

    active: bool | None = None
    owner_user_id: uuid.UUID | None = None
    default_budget_profile: BudgetProfile | None = None
    max_steps: int | None = Field(default=None, ge=1, le=600)


class IntakeMailboxResponse(BaseModel):
    """Wire shape returned by all four admin endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    inbox_id: str
    address: str
    practice_area_id: uuid.UUID
    owner_user_id: uuid.UUID
    default_budget_profile: str | None
    max_steps: int | None
    active: bool
    created_at: datetime
    updated_at: datetime
