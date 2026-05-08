"""Integration tests for :class:`SQLRoutingLogWriter` against real Postgres.

Skipped unless ``DATABASE_URL`` is set and points at a database where
the ``inference_routing_log`` table exists (i.e., A2's migration has
been applied). The unit-test coverage in ``test_routing_log.py`` uses
mocks; this test exists so the gateway's bind-parameter shape stays in
sync with the migration.

Run via:

    PG_PASS=$(grep "^POSTGRES_PASSWORD=" .env | cut -d= -f2)
    DATABASE_URL="postgresql+asyncpg://lq_ai:${PG_PASS}@localhost:5433/lq_ai" \\
      gateway/.venv/bin/pytest gateway/tests/test_routing_log_db.py
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import build_engine
from app.routing_log import InferenceRoutingLogRow, SQLRoutingLogWriter

_DB_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    _DB_URL is None,
    reason="DATABASE_URL not set; skipping DB-backed routing-log tests",
)


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    assert _DB_URL is not None  # narrowed by skipif
    engine = build_engine(_DB_URL)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.integration
async def test_sql_writer_inserts_row(db_engine: AsyncEngine) -> None:
    """A successful write produces a row readable by the same connection."""

    writer = SQLRoutingLogWriter(db_engine)
    request_id = "lq_b4_routing_log_test_1"

    # Clean any leftover row from a prior failed run so the assertion below
    # picks the row we just inserted, not a duplicate.
    async with db_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM inference_routing_log WHERE request_id = :rid"),
            {"rid": request_id},
        )

    await writer.write(
        InferenceRoutingLogRow(
            routed_provider="anthropic-prod",
            routed_model="claude-opus-4-7",
            routed_inference_tier=4,
            requested_model="smart",
            tokens_in=10,
            tokens_out=5,
            cost_estimate=Decimal("0.0123"),
            latency_ms=42,
            request_id=request_id,
        )
    )

    async with db_engine.begin() as conn:
        rs = await conn.execute(
            text(
                "SELECT routed_provider, routed_model, routed_inference_tier, "
                "tokens_in, tokens_out, cost_estimate, latency_ms, request_id, "
                "refused, anonymization_applied "
                "FROM inference_routing_log WHERE request_id = :rid"
            ),
            {"rid": request_id},
        )
        row = rs.one()
        assert row.routed_provider == "anthropic-prod"
        assert row.routed_model == "claude-opus-4-7"
        assert row.routed_inference_tier == 4
        assert row.tokens_in == 10
        assert row.tokens_out == 5
        assert row.cost_estimate == Decimal("0.0123")
        assert row.latency_ms == 42
        assert row.refused is False
        assert row.anonymization_applied is False
        # Cleanup
        await conn.execute(
            text("DELETE FROM inference_routing_log WHERE request_id = :rid"),
            {"rid": request_id},
        )
