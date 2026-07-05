"""Tests for `app.config.Settings`.

Per CLAUDE.md, decisions are explicit: the backend reads its configuration
from environment variables (and a `.env` file) via pydantic-settings. These
tests pin that behaviour: required-feeling fields *load* from env, defaults
apply when env is absent, and the `lru_cache`-backed accessor reflects
re-reads after a cache clear.
"""

from __future__ import annotations

import pytest

from app.config import Settings, assert_boot_secrets_configured, get_settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.mark.unit
def test_defaults_apply_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings constructs cleanly with no overrides — defaults are usable."""
    # Wipe out any inherited values so we exercise the defaults.
    for var in (
        "DATABASE_URL",
        "REDIS_URL",
        "S3_ENDPOINT_URL",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_BUCKET",
        "S3_REGION",
        "LQ_AI_GATEWAY_URL",
        "LQ_AI_GATEWAY_KEY",
        "JWT_SECRET",
        "JWT_ACCESS_TOKEN_TTL_SECONDS",
        "JWT_REFRESH_TOKEN_TTL_SECONDS",
        "LOG_LEVEL",
        "LQ_AI_DEV_MODE",
    ):
        monkeypatch.delenv(var, raising=False)

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.database_url.startswith("postgresql+asyncpg://")
    assert s.redis_url.startswith("redis://")
    assert s.s3_bucket == "lq-ai-files"
    assert s.s3_region == "us-east-1"
    assert s.jwt_access_token_ttl_seconds == 900
    assert s.jwt_refresh_token_ttl_seconds == 604800
    assert s.log_level == "info"
    assert s.lq_ai_dev_mode is False


@pytest.mark.unit
def test_overrides_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each declared field reads from its corresponding env var."""
    env = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@h:5432/d",
        "REDIS_URL": "redis://r:6379/3",
        "S3_ENDPOINT_URL": "https://s3.example.com",
        "S3_ACCESS_KEY": "AK",
        "S3_SECRET_KEY": "SK",
        "S3_BUCKET": "custom-bucket",
        "S3_REGION": "us-west-2",
        "LQ_AI_GATEWAY_URL": "http://gw:9999",
        "LQ_AI_GATEWAY_KEY": "gw-key",
        "JWT_SECRET": "jwt-secret",
        "JWT_ACCESS_TOKEN_TTL_SECONDS": "120",
        "JWT_REFRESH_TOKEN_TTL_SECONDS": "240",
        "LOG_LEVEL": "debug",
        "LQ_AI_DEV_MODE": "true",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.database_url == env["DATABASE_URL"]
    assert s.redis_url == env["REDIS_URL"]
    assert s.s3_endpoint_url == env["S3_ENDPOINT_URL"]
    assert s.s3_access_key == env["S3_ACCESS_KEY"]
    assert s.s3_secret_key == env["S3_SECRET_KEY"]
    assert s.s3_bucket == env["S3_BUCKET"]
    assert s.s3_region == env["S3_REGION"]
    assert s.lq_ai_gateway_url == env["LQ_AI_GATEWAY_URL"]
    assert s.lq_ai_gateway_key == env["LQ_AI_GATEWAY_KEY"]
    assert s.jwt_secret == env["JWT_SECRET"]
    assert s.jwt_access_token_ttl_seconds == 120
    assert s.jwt_refresh_token_ttl_seconds == 240
    assert s.log_level == "debug"
    assert s.lq_ai_dev_mode is True


# ---------------------------------------------------------------------------
# assert_boot_secrets_configured (SAAS-2, ADR-F059 §6-item-9)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_boot_refuses_non_dev_default_secret() -> None:
    """Non-dev + shipped default JWT secret → refuse to boot (RuntimeError)."""
    s = _settings(lq_ai_dev_mode=False, jwt_secret="dev-jwt-secret-change-me")
    with pytest.raises(RuntimeError) as exc:
        assert_boot_secrets_configured(s)
    # The message names the setting but NEVER echoes the value.
    assert "JWT_SECRET" in str(exc.value)
    assert "dev-jwt-secret-change-me" not in str(exc.value)


@pytest.mark.unit
def test_boot_refuses_non_dev_empty_secret() -> None:
    s = _settings(lq_ai_dev_mode=False, jwt_secret="")
    with pytest.raises(RuntimeError):
        assert_boot_secrets_configured(s)


@pytest.mark.unit
def test_boot_allows_dev_mode_on_default_secret() -> None:
    """Dev mode is a no-op even on the obvious default — the local harness runs."""
    s = _settings(lq_ai_dev_mode=True, jwt_secret="dev-jwt-secret-change-me")
    assert assert_boot_secrets_configured(s) is None


@pytest.mark.unit
def test_boot_allows_non_dev_real_secret() -> None:
    s = _settings(lq_ai_dev_mode=False, jwt_secret="a-real-strong-secret-value")
    assert assert_boot_secrets_configured(s) is None


@pytest.mark.unit
def test_get_settings_is_cached() -> None:
    """`get_settings()` returns the same instance until the cache is cleared."""
    a = get_settings()
    b = get_settings()
    assert a is b
    get_settings.cache_clear()
    c = get_settings()
    assert c is not a


@pytest.mark.unit
def test_run_default_budget_profile_defaults_to_none() -> None:
    """SETUP-5a (ADR-F063): unset ⇒ None (the run-create chain falls through
    to balanced)."""
    assert _settings().run_default_budget_profile is None


@pytest.mark.unit
def test_run_default_budget_profile_empty_string_normalizes_to_none() -> None:
    """The prod compose forwards `${RUN_DEFAULT_BUDGET_PROFILE:-}`, so an unset
    key reaches pydantic as EMPTY STRING — it must read as "no default", never
    as a value (the SETUP-3b `${VAR:-}` trap)."""
    assert _settings(run_default_budget_profile="").run_default_budget_profile is None


@pytest.mark.unit
@pytest.mark.parametrize("profile", ["economy", "balanced", "generous"])
def test_run_default_budget_profile_accepts_the_three_profiles(profile: str) -> None:
    assert _settings(run_default_budget_profile=profile).run_default_budget_profile == profile


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["lavish", "Economy", "balanced "])
def test_run_default_budget_profile_rejects_unknown_values_at_boot(bad: str) -> None:
    """A misconfigured deployment fails LOUD at Settings construction (boot),
    never silently runs every run on an unintended tier."""
    with pytest.raises(Exception) as exc:
        _settings(run_default_budget_profile=bad)
    assert "RUN_DEFAULT_BUDGET_PROFILE" in str(exc.value)
