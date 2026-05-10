"""Unit tests for gateway encrypted-at-rest provider keys (ADR 0011)."""

from __future__ import annotations

import pytest

from app.secrets import (
    DecryptError,
    MasterKeyMissing,
    ProviderKeyResolver,
    encrypt_value,
    generate_master_key,
)


@pytest.mark.unit
def test_generate_master_key_returns_fernet_compatible_value() -> None:
    """``generate_master_key`` produces a value that round-trips through Fernet."""
    key = generate_master_key()
    token = encrypt_value("test-secret", master_key=key)
    resolver = ProviderKeyResolver(master_key=key, env={})
    out = resolver.resolve(
        provider_name="p", api_key_env=None, api_key_encrypted=token
    )
    assert out == "test-secret"


@pytest.mark.unit
def test_encrypt_value_emits_distinct_tokens_for_same_plaintext() -> None:
    """Fresh nonce per encrypt — same plaintext encrypts to different tokens."""
    key = generate_master_key()
    a = encrypt_value("same-input", master_key=key)
    b = encrypt_value("same-input", master_key=key)
    assert a != b


@pytest.mark.unit
def test_encrypt_value_rejects_empty_plaintext() -> None:
    key = generate_master_key()
    with pytest.raises(ValueError):
        encrypt_value("", master_key=key)


@pytest.mark.unit
def test_resolver_prefers_encrypted_over_env() -> None:
    """When both sources are set, the encrypted path wins.

    The validator on :class:`ProviderConfig` rejects this combination
    upstream, but the resolver itself must be deterministic if both
    arrive at its API surface (defense in depth).
    """
    key = generate_master_key()
    token = encrypt_value("from-encrypted", master_key=key)
    resolver = ProviderKeyResolver(
        master_key=key, env={"ANTHROPIC_API_KEY": "from-env"}
    )
    out = resolver.resolve(
        provider_name="anthropic-prod",
        api_key_env="ANTHROPIC_API_KEY",
        api_key_encrypted=token,
    )
    assert out == "from-encrypted"


@pytest.mark.unit
def test_resolver_falls_back_to_env() -> None:
    resolver = ProviderKeyResolver(
        master_key=None, env={"OPENAI_API_KEY": "from-env"}
    )
    out = resolver.resolve(
        provider_name="openai-prod",
        api_key_env="OPENAI_API_KEY",
        api_key_encrypted=None,
    )
    assert out == "from-env"


@pytest.mark.unit
def test_resolver_returns_empty_when_both_unset() -> None:
    """Legitimately keyless providers (Ollama, local OpenAI-compatible)."""
    resolver = ProviderKeyResolver(master_key=None, env={})
    out = resolver.resolve(
        provider_name="ollama-local",
        api_key_env=None,
        api_key_encrypted=None,
    )
    assert out == ""


@pytest.mark.unit
def test_resolver_returns_empty_when_env_var_absent() -> None:
    resolver = ProviderKeyResolver(master_key=None, env={})
    out = resolver.resolve(
        provider_name="anthropic-prod",
        api_key_env="ANTHROPIC_API_KEY",
        api_key_encrypted=None,
    )
    assert out == ""


@pytest.mark.unit
def test_resolver_raises_master_key_missing_when_unset() -> None:
    """Encrypted path requires a master key; missing → MasterKeyMissing."""
    key = generate_master_key()
    token = encrypt_value("v", master_key=key)
    resolver = ProviderKeyResolver(master_key=None, env={})
    with pytest.raises(MasterKeyMissing):
        resolver.resolve(
            provider_name="p", api_key_env=None, api_key_encrypted=token
        )


@pytest.mark.unit
def test_resolver_raises_master_key_missing_when_malformed() -> None:
    resolver = ProviderKeyResolver(master_key="not-a-real-key", env={})
    # Even building the Fernet fails with a malformed key. The error
    # surface is MasterKeyMissing (clearer for operators than the
    # raw ValueError from the cryptography library).
    with pytest.raises(MasterKeyMissing):
        resolver.resolve(
            provider_name="p",
            api_key_env=None,
            api_key_encrypted="anything",
        )


@pytest.mark.unit
def test_resolver_raises_decrypt_error_on_wrong_master_key() -> None:
    """Token encrypted under key A, decrypted under key B → DecryptError."""
    key_a = generate_master_key()
    key_b = generate_master_key()
    token = encrypt_value("v", master_key=key_a)
    resolver = ProviderKeyResolver(master_key=key_b, env={})
    with pytest.raises(DecryptError) as excinfo:
        resolver.resolve(
            provider_name="anthropic-prod",
            api_key_env=None,
            api_key_encrypted=token,
        )
    # Provider name is in the error message so operators can locate
    # the offending entry without grep-spelunking through gateway.yaml.
    assert "anthropic-prod" in str(excinfo.value)


@pytest.mark.unit
def test_resolver_raises_decrypt_error_on_corrupted_token() -> None:
    """A token with mutated body bytes fails MAC verification."""
    key = generate_master_key()
    token = encrypt_value("v", master_key=key)
    # Flip a byte deep in the ciphertext — Fernet authenticates the
    # whole token via HMAC-SHA256, so any modification fails the MAC
    # check. Picking position 25 lands inside the ciphertext+IV
    # region (versioned-prefix + timestamp are at the start).
    if len(token) <= 25:  # defensive
        token = token + "AAAA"
    body = list(token)
    flip_idx = 25
    body[flip_idx] = "A" if body[flip_idx] != "A" else "B"
    corrupted = "".join(body)
    resolver = ProviderKeyResolver(master_key=key, env={})
    with pytest.raises(DecryptError):
        resolver.resolve(
            provider_name="p", api_key_env=None, api_key_encrypted=corrupted
        )


@pytest.mark.unit
def test_provider_config_rejects_both_key_sources() -> None:
    """Mixing api_key_env + api_key_encrypted on one provider entry → validation error."""
    from pydantic import ValidationError

    from app.config import ProviderConfig

    with pytest.raises(ValidationError):
        ProviderConfig(
            name="anthropic-prod",
            type="anthropic",
            base_url="https://api.anthropic.com",
            api_key_env="ANTHROPIC_API_KEY",
            api_key_encrypted="gAAAAAB-not-real-but-non-empty",
            tier=4,
            models=["claude-opus-4-7"],
        )


@pytest.mark.unit
def test_provider_config_accepts_encrypted_only() -> None:
    from app.config import ProviderConfig

    cfg = ProviderConfig(
        name="anthropic-prod",
        type="anthropic",
        base_url="https://api.anthropic.com",
        api_key_encrypted="gAAAAAB-token-placeholder",
        tier=4,
        models=["claude-opus-4-7"],
    )
    assert cfg.api_key_env is None
    assert cfg.api_key_encrypted == "gAAAAAB-token-placeholder"
