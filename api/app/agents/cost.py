"""Per-run USD cost estimate for deep-agent runs (F2 Slice O-2, ADR-F053).

Turns a run's persisted ``total_tokens`` (Slice G) into a rough dollar
figure for the run row + budget UI. Mirrors :mod:`app.citation.cost`
(M2-E2): a rolling average over the inference routing log — but here a
*blended per-token* rate over recent ``agent_loop`` traffic, multiplied
by the run's token total.

Why blended per-token (not per-call like the judge estimator)
-------------------------------------------------------------
A judge call is a fixed-shape single inference, so :mod:`app.citation.cost`
averages *per-call* cost. A deep-agent run is many calls of wildly
varying size (a large context turn vs a one-line tool result), and the
only run-level quantity we persist is ``total_tokens`` — not a call
count. So the honest rate is blended per-token::

    rate = SUM(cost_estimate) / SUM(tokens_in + tokens_out)  # over the window
    cost = rate * total_tokens

Summing then dividing weights the rate by call size (a more faithful
blended rate than averaging per-row rates).

Why an estimate, not the exact cost
-----------------------------------
The routing log carries no run / agent-run id (only ``chat_id`` /
``message_id``), so a run's own rows cannot be summed directly — exact
per-run attribution is a deferred cross-service slice (routing-log
``run_id``). ADR-F053 accepts the rolling-average estimate; the UI labels
the figure as approximate.

Cold-start / unpriced models
----------------------------
The gateway leaves ``cost_estimate`` NULL for models absent from its
``cost_tracking.rates`` map ("don't overclaim"). When fewer than
:data:`_MIN_SAMPLES` priced ``agent_loop`` rows exist, this falls back to
:data:`DEFAULT_AGENT_PER_TOKEN_USD` — a conservative blended placeholder
that self-calibrates once priced traffic accumulates inside the window.

No cache (unlike the judge estimator)
-------------------------------------
:mod:`app.citation.cost` caches because the cost pre-flight fires several
times per chat message (a hot path). This estimator runs exactly **once
per run, at settlement** — a cold path — so a process-global cache would
buy nothing and is deliberately omitted (one query per settled run).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inference import InferenceRoutingLog

logger = logging.getLogger(__name__)


_AGENT_LOOP_PURPOSE = "agent_loop"
"""The routing-log ``purpose`` tag the agent factory sets on every
deep-agent gateway call (``app.agents.factory``)."""

DEFAULT_AGENT_PER_TOKEN_USD: Decimal = Decimal("0.000003")
"""Cold-start fallback blended rate (~$3 / million tokens) — a mid-tier
guess used only until at least :data:`_MIN_SAMPLES` priced ``agent_loop``
rows exist. Deliberately rough: the UI always labels the figure as an
estimate, and real routing-log data overrides it within the window."""

_MIN_SAMPLES = 5
"""Minimum priced ``agent_loop`` rows before the blended rate is trusted
over the fallback. Below this, one outlier (a huge-context turn) would
distort the rate."""

_WINDOW_SAMPLES = 100
"""Most recent priced ``agent_loop`` rows included in the blended rate."""

_WINDOW_DAYS = 30
"""Maximum lookback; protects against price-stale data on low traffic."""

_RATE_QUANTUM = Decimal("0.0000000001")
"""Per-token rate precision (1e-10) — small relative to per-call costs."""

_COST_QUANTUM = Decimal("0.0001")
"""Matches ``agent_runs.cost_usd`` / ``inference_routing_log.cost_estimate``
``NUMERIC(10, 4)`` — the persisted figure never exceeds column precision."""


async def _agent_loop_per_token_usd(db: AsyncSession) -> Decimal:
    """Blended per-token USD rate over recent ``agent_loop`` routing rows.

    ``SUM(cost_estimate) / SUM(tokens_in + tokens_out)`` over the last
    :data:`_WINDOW_SAMPLES` priced rows (no older than :data:`_WINDOW_DAYS`).
    Falls back to :data:`DEFAULT_AGENT_PER_TOKEN_USD` when fewer than
    :data:`_MIN_SAMPLES` such rows exist, when the token sum is zero, or
    when the query errors — the estimate is best-effort and must never
    break settlement.
    """
    cutoff = datetime.now(UTC) - timedelta(days=_WINDOW_DAYS)
    window = (
        select(
            InferenceRoutingLog.cost_estimate.label("cost"),
            (InferenceRoutingLog.tokens_in + InferenceRoutingLog.tokens_out).label("toks"),
        )
        .where(
            InferenceRoutingLog.purpose == _AGENT_LOOP_PURPOSE,
            InferenceRoutingLog.cost_estimate.is_not(None),
            InferenceRoutingLog.tokens_in.is_not(None),
            InferenceRoutingLog.tokens_out.is_not(None),
            InferenceRoutingLog.timestamp >= cutoff,
        )
        .order_by(InferenceRoutingLog.timestamp.desc())
        .limit(_WINDOW_SAMPLES)
        .subquery()
    )
    stmt = select(
        func.sum(window.c.cost),
        func.sum(window.c.toks),
        func.count(window.c.cost),
    )

    try:
        sum_cost, sum_toks, count = (await db.execute(stmt)).one()
    except Exception as exc:
        logger.warning(
            "agent_loop cost calibration query failed: %s",
            exc,
            extra={"event": "agent_cost_query_error", "error_type": type(exc).__name__},
        )
        return DEFAULT_AGENT_PER_TOKEN_USD

    if count is None or count < _MIN_SAMPLES or not sum_cost or not sum_toks:
        return DEFAULT_AGENT_PER_TOKEN_USD
    return (Decimal(str(sum_cost)) / Decimal(str(sum_toks))).quantize(_RATE_QUANTUM)


async def estimate_agent_run_cost_usd(
    db: AsyncSession | None,
    *,
    total_tokens: int | None,
) -> Decimal | None:
    """Rough USD estimate for a run: blended ``agent_loop`` rate x tokens.

    Returns ``None`` when there is nothing to price (no positive token
    total) so the run row keeps ``cost_usd`` NULL. ``db=None`` uses the
    fallback rate (kept for symmetry with :mod:`app.citation.cost`;
    production always passes a session). Best-effort: the rate query is
    internally defensive, so this never raises on a DB hiccup.
    """
    if total_tokens is None or total_tokens <= 0:
        return None
    rate = DEFAULT_AGENT_PER_TOKEN_USD if db is None else await _agent_loop_per_token_usd(db)
    return (rate * Decimal(total_tokens)).quantize(_COST_QUANTUM)
