"""Pydantic schemas for practice areas — F1-S2 (fork, ADR-F002).

Wire shapes for the cockpit's left rail. The list is curated seed data
in S2 (migration 0053); S3 adds the config vocabulary and admin API.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PracticeAreaRead(BaseModel):
    """ORM-read view of a :class:`~app.models.practice_area.PracticeArea`.

    ``configured`` drives the F002 inert-card semantics in the cockpit:
    unconfigured areas are not enterable (no composer, no rail, no
    matter creation under them). ``unit_label`` is the unit-of-work noun
    the UI renders — data, not code (ADR-F004).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    unit_label: str
    configured: bool
    position: int
    created_at: datetime
    updated_at: datetime


class PracticeAreaListResponse(BaseModel):
    """Full curated list, ``position`` order. Unpaginated: the set is a
    bounded handful of operator-curated rows, not user data."""

    practice_areas: list[PracticeAreaRead]
