"""Unit tests for optional Azure Key Vault provider-key sourcing (KV-1, ADR-F069).

Hermetic: a fake :class:`~app.keyvault.KeyVaultFetcher` is injected through the
``fetcher=`` seam, so no test opens a socket or touches IMDS. The wiring cases
exercise ``build_adapter`` with the overlay merged into an env mapping — the same
path the lifespan uses — without running the lifespan.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.config import ProviderConfig
from app.keyvault import (
    ImdsKeyVaultFetcher,
    KeyVaultFetchError,
    keyvault_env_overlay,
)
from app.main import build_adapter
from app.providers import AzureOpenAIAdapter


class _FakeFetcher:
    """A hermetic ``KeyVaultFetcher``: returns canned values keyed by secret name.

    Records every ``(vault, secret_name)`` call so a test can assert one injected
    instance served all secrets (the token-reuse property) and that an unknown
    secret raises (the fetch-failure path).
    """

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values
        self.calls: list[tuple[str, str]] = []

    def fetch(self, vault: str, secret_name: str) -> str:
        self.calls.append((vault, secret_name))
        try:
            return self._values[secret_name]
        except KeyError as exc:
            raise KeyVaultFetchError(
                f"secret {secret_name!r} not found in vault {vault!r}"
            ) from exc


def _azure_provider() -> ProviderConfig:
    """An Azure-OpenAI provider entry whose key comes from ``AZURE_OPENAI_API_KEY``."""

    return ProviderConfig.model_validate(
        {
            "name": "azure-openai",
            "type": "azure_openai",
            "base_url": "https://res.openai.azure.com",
            "api_key_env": "AZURE_OPENAI_API_KEY",
            "tier": 3,
            "api_version": "2024-10-21",
        }
    )


# --- (a) unset → {} and zero fetches -----------------------------------------


@pytest.mark.unit
def test_overlay_empty_when_unset_and_never_fetches() -> None:
    fake = _FakeFetcher({})
    # No vault named at all.
    assert keyvault_env_overlay({}, fetcher=fake) == {}
    # Vault named but no per-key secret-name var set.
    assert keyvault_env_overlay({"AZURE_KEY_VAULT_NAME": "myvault"}, fetcher=fake) == {}
    assert fake.calls == []


# --- (b) vault + one secret-name → exactly that key --------------------------


@pytest.mark.unit
def test_overlay_single_key() -> None:
    fake = _FakeFetcher({"openai-secret": "kv-openai-value"})
    env = {
        "AZURE_KEY_VAULT_NAME": "myvault",
        "AZURE_OPENAI_KEY_SECRET_NAME": "openai-secret",
    }
    overlay = keyvault_env_overlay(env, fetcher=fake)
    assert overlay == {"AZURE_OPENAI_API_KEY": "kv-openai-value"}
    assert fake.calls == [("myvault", "openai-secret")]


# --- (c) all three → all fetched via one instance ----------------------------


@pytest.mark.unit
def test_overlay_all_three_one_instance() -> None:
    fake = _FakeFetcher(
        {
            "openai-secret": "v-openai",
            "anthropic-secret": "v-anthropic",
            "foundry-secret": "v-foundry",
        }
    )
    env = {
        "AZURE_KEY_VAULT_NAME": "myvault",
        "AZURE_OPENAI_KEY_SECRET_NAME": "openai-secret",
        "AZURE_ANTHROPIC_KEY_SECRET_NAME": "anthropic-secret",
        "AZURE_FOUNDRY_KEY_SECRET_NAME": "foundry-secret",
    }
    overlay = keyvault_env_overlay(env, fetcher=fake)
    assert overlay == {
        "AZURE_OPENAI_API_KEY": "v-openai",
        "AZURE_ANTHROPIC_API_KEY": "v-anthropic",
        "AZURE_FOUNDRY_API_KEY": "v-foundry",
    }
    # The single injected fetcher served all three (in the live path, one IMDS
    # token is minted and reused for all three secrets).
    assert len(fake.calls) == 3
    assert {name for _vault, name in fake.calls} == {
        "openai-secret",
        "anthropic-secret",
        "foundry-secret",
    }


@pytest.mark.unit
def test_imds_fetcher_caches_token_across_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """The live fetcher mints the IMDS token once and reuses it per secret."""

    counts = {"token": 0, "secret": 0}

    def _fake_get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        if "169.254.169.254" in url:
            counts["token"] += 1
            assert headers.get("Metadata") == "true"
            return {"access_token": "tok-123"}
        counts["secret"] += 1
        assert headers.get("Authorization") == "Bearer tok-123"
        return {"value": "secret-value"}

    monkeypatch.setattr(ImdsKeyVaultFetcher, "_get_json", staticmethod(_fake_get_json))
    fetcher = ImdsKeyVaultFetcher()
    assert fetcher.fetch("myvault", "s1") == "secret-value"
    assert fetcher.fetch("myvault", "s2") == "secret-value"
    assert counts["token"] == 1  # minted once, reused for the second secret
    assert counts["secret"] == 2


# --- (d) fetch failure → fail-open, isolated to that key ---------------------


@pytest.mark.unit
def test_fetch_failure_is_fail_open_and_isolated(caplog: pytest.LogCaptureFixture) -> None:
    # anthropic-secret is absent from the fake → fetch raises for it only.
    fake = _FakeFetcher({"openai-secret": "v-openai", "foundry-secret": "v-foundry"})
    env = {
        "AZURE_KEY_VAULT_NAME": "myvault",
        "AZURE_OPENAI_KEY_SECRET_NAME": "openai-secret",
        "AZURE_ANTHROPIC_KEY_SECRET_NAME": "anthropic-secret",
        "AZURE_FOUNDRY_KEY_SECRET_NAME": "foundry-secret",
    }
    with caplog.at_level(logging.WARNING):
        overlay = keyvault_env_overlay(env, fetcher=fake)
    assert overlay == {
        "AZURE_OPENAI_API_KEY": "v-openai",
        "AZURE_FOUNDRY_API_KEY": "v-foundry",
    }
    assert "AZURE_ANTHROPIC_API_KEY" not in overlay
    assert any(
        "Key Vault fetch failed for AZURE_ANTHROPIC_API_KEY" in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING
    )


# --- (e) invalid vault name → warn + skip, no fetch --------------------------


@pytest.mark.unit
def test_invalid_vault_name_skips_without_fetch(caplog: pytest.LogCaptureFixture) -> None:
    fake = _FakeFetcher({"openai-secret": "v-openai"})
    env = {
        "AZURE_KEY_VAULT_NAME": "bad_name!",  # underscore + bang → invalid
        "AZURE_OPENAI_KEY_SECRET_NAME": "openai-secret",
    }
    with caplog.at_level(logging.WARNING):
        overlay = keyvault_env_overlay(env, fetcher=fake)
    assert overlay == {}
    assert fake.calls == []
    assert any("not a valid vault name" in r.getMessage() for r in caplog.records)


@pytest.mark.unit
def test_invalid_secret_name_skips_that_key(caplog: pytest.LogCaptureFixture) -> None:
    fake = _FakeFetcher({"good-secret": "v-good"})
    env = {
        "AZURE_KEY_VAULT_NAME": "myvault",
        "AZURE_OPENAI_KEY_SECRET_NAME": "bad secret name",  # space → invalid
        "AZURE_FOUNDRY_KEY_SECRET_NAME": "good-secret",
    }
    with caplog.at_level(logging.WARNING):
        overlay = keyvault_env_overlay(env, fetcher=fake)
    assert overlay == {"AZURE_FOUNDRY_API_KEY": "v-good"}
    assert fake.calls == [("myvault", "good-secret")]
    assert any(
        "secret name from AZURE_OPENAI_KEY_SECRET_NAME is invalid" in r.getMessage()
        for r in caplog.records
    )


# --- (f) the secret VALUE never appears in any log record --------------------


@pytest.mark.unit
def test_secret_value_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    secret_value = "SUPER-SECRET-VALUE-9f8e7d"
    fake = _FakeFetcher({"openai-secret": secret_value})
    env = {
        "AZURE_KEY_VAULT_NAME": "myvault",
        "AZURE_OPENAI_KEY_SECRET_NAME": "openai-secret",
        # a stale plaintext value present → exercises the override info line too
        "AZURE_OPENAI_API_KEY": "stale-plain",
    }
    with caplog.at_level(logging.DEBUG):
        overlay = keyvault_env_overlay(env, fetcher=fake)
    assert overlay["AZURE_OPENAI_API_KEY"] == secret_value
    for record in caplog.records:
        assert secret_value not in record.getMessage()
        assert secret_value not in str(record.args)
    # the override was announced (without the value)
    assert any("overriding the existing plaintext" in r.getMessage() for r in caplog.records)


# --- (g) wiring: overlay key reaches the built adapter; unset is identical ----


@pytest.mark.unit
def test_wiring_overlay_key_reaches_adapter() -> None:
    fake = _FakeFetcher({"openai-secret": "kv-sourced-key"})
    env = {
        "AZURE_KEY_VAULT_NAME": "myvault",
        "AZURE_OPENAI_KEY_SECRET_NAME": "openai-secret",
        "AZURE_OPENAI_API_KEY": "stale-plain-key",  # overlay must win over this
    }
    overlay = keyvault_env_overlay(env, fetcher=fake)
    merged = {**env, **overlay}

    adapter = build_adapter(_azure_provider(), env=merged)
    assert isinstance(adapter, AzureOpenAIAdapter)
    assert adapter._api_key == "kv-sourced-key"


@pytest.mark.unit
def test_wiring_unset_is_byte_identical() -> None:
    fake = _FakeFetcher({"openai-secret": "unused"})
    # No vault configured → overlay empty, fetcher never called.
    overlay = keyvault_env_overlay({"AZURE_OPENAI_API_KEY": "plain-key"}, fetcher=fake)
    assert overlay == {}
    assert fake.calls == []

    # With no overlay, resolution is exactly today's plain-env-var path.
    adapter = build_adapter(_azure_provider(), env={"AZURE_OPENAI_API_KEY": "plain-key"})
    assert isinstance(adapter, AzureOpenAIAdapter)
    assert adapter._api_key == "plain-key"


def test_empty_secret_value_is_ignored_not_overriding(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An EMPTY Key Vault value must never enter the overlay: overriding a valid
    plaintext key with "" would skip the provider while the log claimed success
    (review finding #3). The key is omitted — fail-open to the plain env var."""
    fetcher = _FakeFetcher({"gpt-key": ""})
    env = {
        "AZURE_KEY_VAULT_NAME": "kv-unit",
        "AZURE_OPENAI_KEY_SECRET_NAME": "gpt-key",
        "AZURE_OPENAI_API_KEY": "plaintext-fallback",
    }
    with caplog.at_level(logging.WARNING, logger="app.keyvault"):
        overlay = keyvault_env_overlay(env, fetcher=fetcher)
    assert overlay == {}
    assert fetcher.calls == [("kv-unit", "gpt-key")]
    assert any("EMPTY value" in record.getMessage() for record in caplog.records)
