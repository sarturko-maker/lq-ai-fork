"""Practice-area read endpoint + seed — F1-S2 (fork, ADR-F002).

The test database migrates to alembic head (tests/conftest.py), so the
0053 standard-rows seed is PRESENT here — these tests pin the seeded
contract the cockpit's left rail renders, plus the seed's idempotency
(re-running it on a seeded database inserts nothing).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.practice_area import PracticeArea
from app.models.user import User
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration

_EXPECTED_SEED = [
    # (key, name, unit_label, configured) in position order — migration 0053.
    ("commercial", "Commercial", "Matter", True),
    ("disputes", "Disputes", "Matter", False),
    ("m-and-a", "M&A", "Deal", False),
    ("privacy", "Privacy", "Programme", False),
    ("employment", "Employment", "Matter", False),
]


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="practice-areas")


async def test_seed_rows_present_once_with_expected_shape(
    db_session: AsyncSession,
) -> None:
    """Migration 0053 seeded exactly the standard areas, exactly once."""
    rows = (
        (await db_session.execute(select(PracticeArea).order_by(PracticeArea.position)))
        .scalars()
        .all()
    )
    seeded = [r for r in rows if r.key in {k for k, *_ in _EXPECTED_SEED}]
    assert [(r.key, r.name, r.unit_label, r.configured) for r in seeded] == _EXPECTED_SEED
    # The list-equality above is the duplicate guard (a re-seeded key
    # would appear twice and break it); also pin key uniqueness directly.
    assert len({r.key for r in rows}) == len(rows)


async def test_seed_is_idempotent_on_a_seeded_database(
    db_session: AsyncSession,
) -> None:
    """Re-running the 0053 seed against the already-seeded DB is a no-op."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0053", versions / "0053_practice_areas.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0053"] = module
    try:
        spec.loader.exec_module(module)

        before = (
            await db_session.execute(select(func.count()).select_from(PracticeArea))
        ).scalar_one()
        conn = await db_session.connection()
        await conn.run_sync(lambda sync_conn: module._seed(sync_conn))
        after = (
            await db_session.execute(select(func.count()).select_from(PracticeArea))
        ).scalar_one()
        assert after == before
    finally:
        sys.modules.pop("migration_0053", None)


async def test_list_practice_areas_position_order(client: AsyncClient, user: User) -> None:
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    areas = resp.json()["practice_areas"]
    keys = [a["key"] for a in areas]
    assert keys == [k for k, *_ in _EXPECTED_SEED]
    commercial = areas[0]
    assert commercial["configured"] is True
    assert commercial["unit_label"] == "Matter"
    assert {a["key"] for a in areas if a["configured"]} == {"commercial"}


async def test_list_practice_areas_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/practice-areas")
    assert resp.status_code == 401
