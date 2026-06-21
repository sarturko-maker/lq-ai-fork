"""Shared org-profile test helpers (C-CLIENT, ADR-F030).

The Organization Profile is a singleton (migration 0010, partial unique index
on ``((true))``) and the test DB seeds NO row. Tests that exercise the
company/client memory tier upsert one then delete it in ``finally`` — they use a
COMMITTING factory (the per-test rollback ``db_session`` would hide the row from
the agent loop, which reads across short-lived sessions), so they must clean up
explicitly. Both the composition e2e test (``comp_env.factory``) and the
scenario A/B test (``commit_factory``) need the same upsert/clear, so it lives
here rather than duplicated per file. Factory-agnostic: pass whichever
committing ``async_sessionmaker`` the caller already has.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization_profile import OrganizationProfile


async def set_org_profile(factory: async_sessionmaker[AsyncSession], content_md: str) -> None:
    """Upsert the singleton org profile in the committed test DB."""
    async with factory() as db:
        row = (await db.execute(select(OrganizationProfile).limit(1))).scalar_one_or_none()
        if row is None:
            db.add(OrganizationProfile(content_md=content_md))
        else:
            row.content_md = content_md
        await db.commit()


async def clear_org_profile(factory: async_sessionmaker[AsyncSession]) -> None:
    """Restore the clean (no-row) singleton state — the test DB seeds none."""
    async with factory() as db:
        await db.execute(delete(OrganizationProfile))
        await db.commit()
