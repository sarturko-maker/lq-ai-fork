"""Per-run cost estimate — F2 Slice O-2 (ADR-F053 addendum).

Targets :mod:`app.agents.cost`:

* ``total_tokens`` None / 0 / negative → ``None`` (nothing to price).
* ``db=None`` uses the fallback rate (symmetry with app.citation.cost).
* Blended per-token rate: ``SUM(cost_estimate) / SUM(tokens_in+tokens_out)``
  over recent ``agent_loop`` rows, x ``total_tokens``.
* Cold-start / below-min-samples → fallback rate.
* Filter correctness — ``purpose='agent_loop'`` only; NULL cost / NULL
  token rows excluded; stale rows excluded.
* A DB error degrades to the fallback rate (settlement must never break).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.cost import (
    DEFAULT_AGENT_PER_TOKEN_USD,
    estimate_agent_run_cost_usd,
)
from app.models.inference import InferenceRoutingLog

_MILLION = 1_000_000


def _agent_row(
    *,
    cost_estimate: Decimal | None,
    tokens_in: int | None,
    tokens_out: int | None,
    purpose: str | None = "agent_loop",
    timestamp: datetime | None = None,
) -> InferenceRoutingLog:
    return InferenceRoutingLog(
        id=uuid.uuid4(),
        timestamp=timestamp or datetime.now(UTC),
        routed_provider="deepseek-prod",
        routed_model="deepseek-v4-flash",
        routed_inference_tier=3,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate=cost_estimate,
        purpose=purpose,
    )


# --- Nothing to price -------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("total_tokens", [None, 0, -5])
async def test_no_tokens_returns_none(total_tokens: int | None) -> None:
    """No positive token total → None, so the run row keeps cost_usd NULL."""

    assert await estimate_agent_run_cost_usd(None, total_tokens=total_tokens) is None


# --- db=None fallback -------------------------------------------------------


@pytest.mark.unit
async def test_db_none_uses_fallback_rate() -> None:
    """``db=None`` skips the query and prices at the fallback rate."""

    estimate = await estimate_agent_run_cost_usd(None, total_tokens=_MILLION)
    assert estimate == (DEFAULT_AGENT_PER_TOKEN_USD * _MILLION).quantize(Decimal("0.0001"))


# --- Defensive: a DB error degrades to the fallback rate --------------------


@pytest.mark.unit
async def test_query_error_falls_back_to_default_rate() -> None:
    """A DB hiccup on the rate query must not break settlement.

    The estimator catches the error and prices at the fallback rate
    rather than raising — the run still settles, just with an estimate.
    """

    class _BoomSession:
        async def execute(self, *_a: Any, **_k: Any) -> Any:
            raise RuntimeError("db down")

    estimate = await estimate_agent_run_cost_usd(
        cast(AsyncSession, _BoomSession()), total_tokens=_MILLION
    )
    assert estimate == (DEFAULT_AGENT_PER_TOKEN_USD * _MILLION).quantize(Decimal("0.0001"))


# --- Cold start / below min samples -----------------------------------------


@pytest.mark.integration
async def test_cold_start_no_rows_uses_fallback(db_session: AsyncSession) -> None:
    """No agent_loop rows at all → fallback rate x tokens."""

    estimate = await estimate_agent_run_cost_usd(db_session, total_tokens=_MILLION)
    assert estimate == (DEFAULT_AGENT_PER_TOKEN_USD * _MILLION).quantize(Decimal("0.0001"))


@pytest.mark.integration
async def test_below_min_samples_uses_fallback(db_session: AsyncSession) -> None:
    """Fewer than _MIN_SAMPLES=5 priced agent_loop rows → fallback."""

    for _ in range(3):
        db_session.add(_agent_row(cost_estimate=Decimal("0.0030"), tokens_in=500, tokens_out=1000))
    await db_session.flush()

    estimate = await estimate_agent_run_cost_usd(db_session, total_tokens=_MILLION)
    assert estimate == (DEFAULT_AGENT_PER_TOKEN_USD * _MILLION).quantize(Decimal("0.0001"))


# --- Blended per-token rate -------------------------------------------------


@pytest.mark.integration
async def test_blended_rate_computes_correctly(db_session: AsyncSession) -> None:
    """5+ priced agent_loop rows → blended rate SUM(cost)/SUM(tokens).

    5 rows, each cost=0.0030 over 1500 tokens (500 in + 1000 out):
    SUM(cost)=0.015, SUM(tokens)=7500 → rate=0.000002/token.
    For a 1,000,000-token run → 0.000002 * 1e6 = $2.0000 — and NOT the
    fallback ($3.0000), proving calibration is wired and weighted by size.
    """

    for _ in range(5):
        db_session.add(_agent_row(cost_estimate=Decimal("0.0030"), tokens_in=500, tokens_out=1000))
    await db_session.flush()

    estimate = await estimate_agent_run_cost_usd(db_session, total_tokens=_MILLION)
    assert estimate == Decimal("2.0000")
    assert estimate != (DEFAULT_AGENT_PER_TOKEN_USD * _MILLION).quantize(Decimal("0.0001"))


@pytest.mark.integration
async def test_blended_rate_is_size_weighted(db_session: AsyncSession) -> None:
    """SUM/SUM weights by call size (a faithful blended rate).

    One tiny expensive call + four large cheap calls. SUM(cost) and
    SUM(tokens) over all five give the size-weighted rate; a naive
    average of per-row rates would over-weight the tiny call.
    Row A: cost 0.0100 / 1000 tok. Rows B-E: cost 0.0100 / 9000 tok each.
    SUM(cost)=0.05, SUM(tokens)=37000 → rate≈0.0000013514/token.
    """

    db_session.add(_agent_row(cost_estimate=Decimal("0.0100"), tokens_in=400, tokens_out=600))
    for _ in range(4):
        db_session.add(_agent_row(cost_estimate=Decimal("0.0100"), tokens_in=4000, tokens_out=5000))
    await db_session.flush()

    estimate = await estimate_agent_run_cost_usd(db_session, total_tokens=_MILLION)
    # rate = 0.05 / 37000 = 0.0000013513...; * 1e6 = 1.3513..., quantized 1.3514.
    expected_rate = (Decimal("0.05") / Decimal("37000")).quantize(Decimal("0.0000000001"))
    assert estimate == (expected_rate * _MILLION).quantize(Decimal("0.0001"))


# --- Filter correctness -----------------------------------------------------


@pytest.mark.integration
async def test_purpose_filter_excludes_non_agent_loop(db_session: AsyncSession) -> None:
    """chat / judge / NULL-purpose rows are ignored — only agent_loop counts."""

    for purpose in ("chat", "judge_paraphrase", "embedding", None):
        for _ in range(5):
            db_session.add(
                _agent_row(
                    cost_estimate=Decimal("0.0200"),
                    tokens_in=500,
                    tokens_out=500,
                    purpose=purpose,
                )
            )
    await db_session.flush()

    estimate = await estimate_agent_run_cost_usd(db_session, total_tokens=_MILLION)
    # No agent_loop rows → fallback, NOT the 0.02-priced traffic above.
    assert estimate == (DEFAULT_AGENT_PER_TOKEN_USD * _MILLION).quantize(Decimal("0.0001"))


@pytest.mark.integration
async def test_null_cost_and_null_token_rows_excluded(db_session: AsyncSession) -> None:
    """agent_loop rows missing cost or tokens don't poison the rate.

    5 valid rows (cost 0.0030 / 1500 tok) + NULL-cost rows + NULL-token
    rows. The rate reflects only the 5 valid rows → $2.0000 for a 1M run.
    """

    for _ in range(5):
        db_session.add(_agent_row(cost_estimate=Decimal("0.0030"), tokens_in=500, tokens_out=1000))
    for _ in range(10):
        db_session.add(_agent_row(cost_estimate=None, tokens_in=500, tokens_out=1000))
    for _ in range(10):
        db_session.add(_agent_row(cost_estimate=Decimal("0.0030"), tokens_in=None, tokens_out=None))
    await db_session.flush()

    estimate = await estimate_agent_run_cost_usd(db_session, total_tokens=_MILLION)
    assert estimate == Decimal("2.0000")


@pytest.mark.integration
async def test_stale_rows_excluded(db_session: AsyncSession) -> None:
    """Rows older than _WINDOW_DAYS=30 are excluded.

    5 recent cheap rows (rate 0.000002) + 10 stale expensive rows. The
    estimate reflects only the recent data; if stale rows leaked in the
    rate would be far higher.
    """

    now = datetime.now(UTC)
    stale = now - timedelta(days=60)

    for _ in range(5):
        db_session.add(
            _agent_row(
                cost_estimate=Decimal("0.0030"), tokens_in=500, tokens_out=1000, timestamp=now
            )
        )
    for _ in range(10):
        db_session.add(
            _agent_row(
                cost_estimate=Decimal("0.5000"), tokens_in=100, tokens_out=100, timestamp=stale
            )
        )
    await db_session.flush()

    estimate = await estimate_agent_run_cost_usd(db_session, total_tokens=_MILLION)
    assert estimate == Decimal("2.0000")
