"""resolve_envelope — budget profile tiers (ADR-F053, Slice O).

Deterministic, no DB, no model: the profile → four-brake envelope mapping and the
maintainer's "default tier is >= 4x the conservative tier" requirement.
"""

from __future__ import annotations

import pytest

from app.agents.budget import (
    MAX_PROFILE_WALL_CLOCK_SECONDS,
    BudgetEnvelope,
    resolve_envelope,
)
from app.config import get_settings
from app.schemas.agent_runs import BudgetProfile


def test_economy_is_the_conservative_tier() -> None:
    env = resolve_envelope(BudgetProfile.economy, get_settings())
    assert env == BudgetEnvelope(2_000_000, 8, 100, 900.0)


def test_generous_is_the_deep_work_tier() -> None:
    env = resolve_envelope(BudgetProfile.generous, get_settings())
    assert env == BudgetEnvelope(16_000_000, 48, 600, 5400.0)


def test_balanced_reads_from_settings() -> None:
    s = get_settings()
    env = resolve_envelope(BudgetProfile.balanced, s)
    assert env == BudgetEnvelope(
        s.run_token_budget, s.fan_out_quota, s.run_max_steps, s.run_wall_clock_seconds
    )


def test_balanced_default_is_at_least_4x_economy() -> None:
    # The maintainer ask (Slice O): the default tier is >= 4x the conservative tier.
    economy = resolve_envelope(BudgetProfile.economy, get_settings())
    balanced = resolve_envelope(BudgetProfile.balanced, get_settings())
    assert balanced.token_budget >= 4 * economy.token_budget
    assert balanced.fan_out_quota >= 4 * economy.fan_out_quota
    assert balanced.max_steps >= 4 * economy.max_steps
    assert balanced.wall_clock_seconds >= 4 * economy.wall_clock_seconds


@pytest.mark.parametrize("profile", [None, "", "bogus"])
def test_unknown_or_legacy_profile_falls_back_to_balanced(profile: str | None) -> None:
    s = get_settings()
    assert resolve_envelope(profile, s) == resolve_envelope(BudgetProfile.balanced, s)


def test_string_values_resolve_like_the_enum() -> None:
    s = get_settings()
    assert resolve_envelope("economy", s) == resolve_envelope(BudgetProfile.economy, s)
    assert resolve_envelope("generous", s) == resolve_envelope(BudgetProfile.generous, s)


def test_generous_wall_clock_is_the_advertised_max() -> None:
    env = resolve_envelope(BudgetProfile.generous, get_settings())
    assert env.wall_clock_seconds == MAX_PROFILE_WALL_CLOCK_SECONDS
