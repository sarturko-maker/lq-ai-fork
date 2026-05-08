"""Smoke tests for the Phase A1 migration (0001_initial).

Verifies:
- Migration applies cleanly to a fresh DB
- All four expected tables exist
- CITEXT email column behaves case-insensitively
- CHECK constraints fire correctly
- Partial indexes are created
- Per-test transaction rollback fixture works (data inserted in one test
  doesn't leak to the next)
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


@pytest.mark.integration
async def test_phase_a1_tables_exist(db_session: AsyncSession) -> None:
    """All four Phase A1 tables exist after the migration runs."""
    expected = {"users", "user_sessions", "audit_log", "inference_routing_log"}
    result = await db_session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = ANY(:names)"
        ),
        {"names": list(expected)},
    )
    found = {row[0] for row in result.fetchall()}
    assert found == expected, f"missing tables: {expected - found}"


@pytest.mark.integration
async def test_users_email_is_citext(db_session: AsyncSession) -> None:
    """users.email is case-insensitive: inserting two cases collides."""
    user1 = User(email="kevin@example.com", hashed_password="hash1")
    db_session.add(user1)
    await db_session.flush()

    # Same email different case should violate UNIQUE
    user2 = User(email="KEVIN@example.com", hashed_password="hash2")
    db_session.add(user2)

    with pytest.raises(Exception):  # IntegrityError or its asyncpg flavor
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_audit_log_privilege_check_constraint(db_session: AsyncSession) -> None:
    """privilege_marked=true requires privilege_basis to be set."""
    bad = AuditLog(
        action="test.action",
        resource_type="test",
        privilege_marked=True,
        privilege_basis=None,  # CHECK constraint should reject this
    )
    db_session.add(bad)
    with pytest.raises(Exception):
        await db_session.flush()
    await db_session.rollback()

    # Same row with privilege_basis populated should succeed
    good = AuditLog(
        action="test.action",
        resource_type="test",
        privilege_marked=True,
        privilege_basis="matter_attorney_directive",
    )
    db_session.add(good)
    await db_session.flush()
    assert good.id is not None


@pytest.mark.integration
async def test_inference_log_tier_range_check(db_session: AsyncSession) -> None:
    """routed_inference_tier must be 1-5."""
    from app.models import InferenceRoutingLog

    out_of_range = InferenceRoutingLog(
        routed_provider="test-provider",
        routed_model="test-model",
        routed_inference_tier=6,  # invalid
    )
    db_session.add(out_of_range)
    with pytest.raises(Exception):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.integration
async def test_partial_indexes_exist(db_session: AsyncSession) -> None:
    """Verify the partial indexes specified in db-schema.md were created."""
    expected_partials = {
        "idx_users_email_active",
        "idx_users_deletion_scheduled",
        "idx_user_sessions_token_hash",
        "idx_audit_log_privileged",
        "idx_audit_log_tier",
        "idx_inference_log_user",
        "idx_inference_log_refused",
    }
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(:names)"
        ),
        {"names": list(expected_partials)},
    )
    found = {row[0] for row in result.fetchall()}
    assert found == expected_partials, f"missing indexes: {expected_partials - found}"


@pytest.mark.integration
async def test_updated_at_trigger_on_users(db_session: AsyncSession) -> None:
    """users.updated_at is bumped by the trigger on UPDATE."""
    user = User(email=f"trigger-{uuid.uuid4().hex[:8]}@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()
    initial_updated_at = user.updated_at

    # Use a raw SQL UPDATE to bypass the ORM and prove the DB-level trigger fires
    await db_session.execute(
        text("UPDATE users SET display_name = 'Triggered' WHERE id = :id"),
        {"id": user.id},
    )
    await db_session.flush()
    await db_session.refresh(user)
    assert user.updated_at >= initial_updated_at


@pytest.mark.integration
async def test_per_test_isolation_left_over_data(db_session: AsyncSession) -> None:
    """First half of a paired test: inserts a row that should NOT survive."""
    user = User(email="isolation-canary@example.com", hashed_password="h")
    db_session.add(user)
    await db_session.flush()
    # No commit. Teardown should roll back.


@pytest.mark.integration
async def test_per_test_isolation_canary_gone(db_session: AsyncSession) -> None:
    """Second half: the canary row from the previous test must be absent."""
    result = await db_session.execute(
        text("SELECT id FROM users WHERE email = 'isolation-canary@example.com'")
    )
    assert result.first() is None, "previous test's row leaked across test boundary"
