"""Fixtures for the scenario harness.

``commit_factory`` is a real (committing) session factory bound to the
session-scoped ``test_engine`` — the agent loop reads run/step/document
rows across short-lived sessions, so the harness must COMMIT its seed
and its run row (the per-test rollback ``db_session`` fixture would hide
them from the loop). Mirrors the composition tests' factory.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)
