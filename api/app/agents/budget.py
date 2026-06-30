"""Per-run budget envelopes (cost/effort tiers) — F2 Slice O (ADR-F053).

A run's ``budget_profile`` (economy / balanced / generous) selects a tier of the
four per-run brakes — the token budget (ADR-F051), the fan-out quota (ADR-F049
Slice E), the settled-step ceiling, and the wall-clock timeout. The **balanced**
tier is the default and is read from :class:`~app.config.Settings`, so an operator
can shift the default envelope via env without a code change; **economy** dials the
brakes down to the conservative pre-Slice-O values, and **generous** raises them
for deep work.

"System proposes, user owns": balanced is deliberately generous so the agent can
fan out and read freely (cost stops being the day-to-day throttle); the human dials
*down* (economy) for a cheaper, faster, tighter run. The brakes still fire at
whichever tier's ceiling applies — the ceiling is a runaway backstop, not a budget.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.schemas.agent_runs import BudgetProfile


@dataclass(frozen=True)
class BudgetEnvelope:
    """The concrete four-brake ceiling a ``budget_profile`` resolves to."""

    token_budget: int
    fan_out_quota: int
    max_steps: int
    wall_clock_seconds: float


# Economy = the conservative pre-Slice-O tier (the dial-down option).
_ECONOMY = BudgetEnvelope(
    token_budget=2_000_000,
    fan_out_quota=8,
    max_steps=100,
    wall_clock_seconds=900.0,
)

# Generous = the deep-work tier (dial-up). Its wall clock MUST stay below the arq
# job timeout (workers.agent_run_worker.AGENT_RUN_JOB_TIMEOUT_SECONDS) so the
# runner's own clean cap fires before arq hard-cancels the worker.
_GENEROUS = BudgetEnvelope(
    token_budget=16_000_000,
    fan_out_quota=48,
    max_steps=600,
    wall_clock_seconds=5400.0,
)

# The largest wall clock any profile may request — the arq job timeout must exceed
# it (asserted in workers.agent_run_worker). Kept beside the tiers so they move
# together.
MAX_PROFILE_WALL_CLOCK_SECONDS = _GENEROUS.wall_clock_seconds


def resolve_envelope(profile: BudgetProfile | str | None, settings: Settings) -> BudgetEnvelope:
    """Resolve a ``budget_profile`` to its concrete :class:`BudgetEnvelope`.

    ``None`` / unknown (legacy rows created before the column existed) → the
    balanced default. The balanced tier is sourced from ``settings`` (env-tunable);
    economy and generous are fixed tiers.
    """

    key = profile.value if isinstance(profile, BudgetProfile) else (profile or "")
    if key == BudgetProfile.economy:
        return _ECONOMY
    if key == BudgetProfile.generous:
        return _GENEROUS
    return BudgetEnvelope(
        token_budget=settings.run_token_budget,
        fan_out_quota=settings.fan_out_quota,
        max_steps=settings.run_max_steps,
        wall_clock_seconds=settings.run_wall_clock_seconds,
    )
