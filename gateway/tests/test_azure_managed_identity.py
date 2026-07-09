"""Unit tests for keyless managed-identity auth on the Azure OpenAI adapter (AZ-6, ADR-F072).

Hermetic: the IMDS token mint is faked by monkeypatching the static
``ManagedIdentityTokenProvider._get_json`` (the KV-1 test pattern) — no test opens a
socket or touches ``169.254.169.254``. Adapter round-trips use respx exactly like the
API-key tests in ``test_azure_openai_adapter.py``.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
from typing import Any

import httpx
import pytest
import respx

from app.azure_identity import (
    IDENTITY_RESOURCE_ENV,
    USE_MANAGED_IDENTITY_ENV,
    ManagedIdentityError,
    ManagedIdentityTokenProvider,
    managed_identity_enabled,
    managed_identity_resource,
)
from app.config import ProviderConfig
from app.main import build_adapter
from app.providers import AzureOpenAIAdapter, ProviderNetworkError
from app.providers.openai_schema import ChatCompletionMessage, ChatCompletionRequest

AZURE_BASE = "https://test-resource.openai.azure.com"
AZURE_API_VERSION = "2024-10-21"
AZURE_DEPLOYMENT = "gpt-54-prod"
AZURE_CHAT_PATH = (
    f"/openai/deployments/{AZURE_DEPLOYMENT}/chat/completions?api-version={AZURE_API_VERSION}"
)
AZURE_EMBED_PATH = (
    f"/openai/deployments/{AZURE_DEPLOYMENT}/embeddings?api-version={AZURE_API_VERSION}"
)


def _chat_payload() -> dict[str, Any]:
    return {
        "id": "chatcmpl-mi-1",
        "object": "chat.completion",
        "created": 0,
        "model": AZURE_DEPLOYMENT,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class _FakeTokenProvider:
    """A hermetic ``TokenProvider`` yielding a canned token; counts calls."""

    def __init__(self, token: str = "fake-mi-token") -> None:
        self._token = token
        self.calls = 0

    async def token(self) -> str:
        self.calls += 1
        return self._token


class _FailingTokenProvider:
    """A ``TokenProvider`` whose mint always fails (IMDS down)."""

    async def token(self) -> str:
        raise ManagedIdentityError("imds unreachable")


def _azure_provider() -> ProviderConfig:
    return ProviderConfig.model_validate(
        {
            "name": "azure-openai",
            "type": "azure_openai",
            "base_url": AZURE_BASE,
            "api_key_env": "AZURE_OPENAI_API_KEY",
            "tier": 3,
            "api_version": AZURE_API_VERSION,
        }
    )


def _fake_imds(access_token: str, *, expires_on: int, counter: dict[str, int]):
    def _get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        counter["mint"] = counter.get("mint", 0) + 1
        assert "169.254.169.254" in url
        assert headers.get("Metadata") == "true"
        return {"access_token": access_token, "expires_on": str(expires_on)}

    return _get_json


# --- Resource / scope: the silent-401 guardrails ----------------------------


@pytest.mark.unit
def test_default_resource_is_cognitiveservices_without_dot_default() -> None:
    """The IMDS ``resource`` audience is the BARE cognitiveservices audience — the
    ``/.default`` suffix (an MSAL ``scope`` form) must never appear (silent-401 trap)."""

    resource = managed_identity_resource({})
    assert resource == "https://cognitiveservices.azure.com"
    assert not resource.endswith("/.default")


@pytest.mark.unit
def test_resource_override_honored() -> None:
    """The newer ``/openai/v1/`` route's ``ai.azure.com`` audience is a one-var flip."""

    assert (
        managed_identity_resource({IDENTITY_RESOURCE_ENV: "https://ai.azure.com"})
        == "https://ai.azure.com"
    )


@pytest.mark.unit
def test_invalid_resource_rejected() -> None:
    """A malformed audience fails loudly at construction, never builds a wrong URL."""

    for bad in (
        "cognitiveservices.azure.com",  # no scheme
        "http://x",  # not https
        "https://x/.default",  # scope form, not a bare audience
        "https://x y",  # whitespace
    ):
        with pytest.raises(ManagedIdentityError):
            managed_identity_resource({IDENTITY_RESOURCE_ENV: bad})


@pytest.mark.unit
def test_imds_token_url_encodes_bare_resource() -> None:
    provider = ManagedIdentityTokenProvider(resource="https://cognitiveservices.azure.com")
    assert "resource=https%3A%2F%2Fcognitiveservices.azure.com" in provider._token_url
    assert "api-version=2018-02-01" in provider._token_url
    assert ".default" not in provider._token_url


@pytest.mark.unit
def test_flag_detection() -> None:
    for on in ("true", "1", "YES", "on", "True"):
        assert managed_identity_enabled({USE_MANAGED_IDENTITY_ENV: on})
    for off in ("false", "", "0", "no"):
        assert not managed_identity_enabled({USE_MANAGED_IDENTITY_ENV: off})
    assert not managed_identity_enabled({})


# --- Token minting / caching / refresh --------------------------------------


@pytest.mark.unit
async def test_token_minted_once_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    counter: dict[str, int] = {}
    monkeypatch.setattr(
        ManagedIdentityTokenProvider,
        "_get_json",
        staticmethod(_fake_imds("tok-abc", expires_on=1000 + 3600, counter=counter)),
    )
    provider = ManagedIdentityTokenProvider(
        resource="https://cognitiveservices.azure.com", now=lambda: 1000.0
    )
    assert await provider.token() == "tok-abc"
    assert await provider.token() == "tok-abc"
    assert counter["mint"] == 1  # cached, not re-minted per call


@pytest.mark.unit
async def test_token_refreshed_within_skew_of_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    counter: dict[str, int] = {}
    clock = {"t": 1000.0}
    monkeypatch.setattr(
        ManagedIdentityTokenProvider,
        "_get_json",
        staticmethod(_fake_imds("tok-1", expires_on=1000 + 3600, counter=counter)),
    )
    provider = ManagedIdentityTokenProvider(
        resource="https://cognitiveservices.azure.com", now=lambda: clock["t"]
    )
    assert await provider.token() == "tok-1"
    assert counter["mint"] == 1
    # Comfortably before the 5-min refresh skew of the 4600 expiry → still cached.
    clock["t"] = 1000 + 3000
    assert await provider.token() == "tok-1"
    assert counter["mint"] == 1
    # Now within the refresh skew (expiry 4600, skew 300 → refresh at 4300) → re-mint.
    clock["t"] = 1000 + 3600 - 100
    assert await provider.token() == "tok-1"
    assert counter["mint"] == 2


@pytest.mark.unit
async def test_mint_failure_raises_managed_identity_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        raise OSError("no imds here")

    monkeypatch.setattr(ManagedIdentityTokenProvider, "_get_json", staticmethod(_boom))
    provider = ManagedIdentityTokenProvider(resource="https://cognitiveservices.azure.com")
    with pytest.raises(ManagedIdentityError):
        await provider.token()


@pytest.mark.unit
async def test_missing_access_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_token(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        return {"expires_on": "9999999999"}

    monkeypatch.setattr(ManagedIdentityTokenProvider, "_get_json", staticmethod(_no_token))
    provider = ManagedIdentityTokenProvider(resource="https://cognitiveservices.azure.com")
    with pytest.raises(ManagedIdentityError):
        await provider.token()


@pytest.mark.unit
async def test_serve_stale_token_on_refresh_failure_within_validity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refresh that fails INSIDE the skew window serves the still-valid cached
    token (no 503); once the token is actually expired the error surfaces."""

    clock = {"t": 1000.0}
    state = {"fail": False}

    def _get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        if state["fail"]:
            raise OSError("imds blip")
        return {"access_token": "tok-1", "expires_on": str(1000 + 3600)}

    monkeypatch.setattr(ManagedIdentityTokenProvider, "_get_json", staticmethod(_get_json))
    provider = ManagedIdentityTokenProvider(
        resource="https://cognitiveservices.azure.com", now=lambda: clock["t"]
    )
    assert await provider.token() == "tok-1"

    # Enter the refresh-skew window (expiry 4600, skew 300 → refresh at 4300) with
    # the refresh failing: the still-valid token is served, not raised.
    state["fail"] = True
    clock["t"] = 4500  # within skew, before expiry
    assert await provider.token() == "tok-1"

    # Past actual expiry, refresh still failing → the error surfaces.
    clock["t"] = 4610
    with pytest.raises(ManagedIdentityError):
        await provider.token()


@pytest.mark.unit
async def test_expires_in_relative_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """IMDS returning only ``expires_in`` (relative seconds) yields an absolute expiry."""

    counter: dict[str, int] = {}
    clock = {"t": 1000.0}

    def _get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        counter["mint"] = counter.get("mint", 0) + 1
        return {"access_token": "tok-in", "expires_in": "3600"}

    monkeypatch.setattr(ManagedIdentityTokenProvider, "_get_json", staticmethod(_get_json))
    provider = ManagedIdentityTokenProvider(
        resource="https://cognitiveservices.azure.com", now=lambda: clock["t"]
    )
    assert await provider.token() == "tok-in"
    assert counter["mint"] == 1
    clock["t"] = 4000  # expiry 1000+3600=4600; before the 4300 refresh point → cached
    assert await provider.token() == "tok-in"
    assert counter["mint"] == 1
    clock["t"] = 4400  # within the skew of 4600 → re-mint
    assert await provider.token() == "tok-in"
    assert counter["mint"] == 2


@pytest.mark.unit
async def test_no_expiry_uses_fallback_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """No expiry field ⇒ the fallback TTL (> skew) still yields a cache hit before re-minting."""

    counter: dict[str, int] = {}
    clock = {"t": 1000.0}

    def _get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        counter["mint"] = counter.get("mint", 0) + 1
        return {"access_token": "tok-fb"}

    monkeypatch.setattr(ManagedIdentityTokenProvider, "_get_json", staticmethod(_get_json))
    provider = ManagedIdentityTokenProvider(
        resource="https://cognitiveservices.azure.com", now=lambda: clock["t"]
    )
    assert await provider.token() == "tok-fb"
    assert counter["mint"] == 1
    # Fallback expiry = 1000 + 600 = 1600; cached until the 1300 refresh point.
    clock["t"] = 1200
    assert await provider.token() == "tok-fb"
    assert counter["mint"] == 1  # cache HIT — fallback TTL sits above the skew
    clock["t"] = 1400
    assert await provider.token() == "tok-fb"
    assert counter["mint"] == 2


@pytest.mark.unit
async def test_boot_retry_recovers_from_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single transient IMDS failure at mint is absorbed by the one boot-retry."""

    state = {"calls": 0}

    def _get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        state["calls"] += 1
        if state["calls"] == 1:
            raise urllib.error.URLError("boot blip")
        return {"access_token": "tok-retry", "expires_on": "9999999999"}

    monkeypatch.setattr(ManagedIdentityTokenProvider, "_get_json", staticmethod(_get_json))
    provider = ManagedIdentityTokenProvider(resource="https://cognitiveservices.azure.com")
    assert await provider.token() == "tok-retry"
    assert state["calls"] == 2  # first failed, retry succeeded


@pytest.mark.unit
async def test_concurrent_first_callers_mint_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """N concurrent first-callers mint exactly once (the under-lock double-check
    prevents a thundering herd against IMDS)."""

    counter: dict[str, int] = {}

    def _get_json(url: str, *, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        counter["mint"] = counter.get("mint", 0) + 1
        return {"access_token": "tok-conc", "expires_on": "9999999999"}

    monkeypatch.setattr(ManagedIdentityTokenProvider, "_get_json", staticmethod(_get_json))
    provider = ManagedIdentityTokenProvider(resource="https://cognitiveservices.azure.com")
    results = await asyncio.gather(*[provider.token() for _ in range(6)])
    assert results == ["tok-conc"] * 6
    assert counter["mint"] == 1  # minted once, not once per caller


# --- Adapter: Bearer replaces api-key ---------------------------------------


@pytest.mark.unit
async def test_chat_sends_bearer_not_api_key() -> None:
    tp = _FakeTokenProvider("fake-mi-token")
    with respx.mock(base_url=AZURE_BASE) as router:
        route = router.post(AZURE_CHAT_PATH).mock(
            return_value=httpx.Response(200, json=_chat_payload())
        )
        client = httpx.AsyncClient(base_url=AZURE_BASE)
        try:
            adapter = AzureOpenAIAdapter(
                name="azure-test",
                base_url=AZURE_BASE,
                api_key="",
                api_version=AZURE_API_VERSION,
                client=client,
                token_provider=tp,
            )
            await adapter.chat_completion(
                ChatCompletionRequest(
                    model="alias",
                    messages=[ChatCompletionMessage(role="user", content="hi")],
                ),
                model=AZURE_DEPLOYMENT,
                stream=False,
            )
        finally:
            await client.aclose()
    sent = route.calls.last.request
    assert sent.headers.get("authorization") == "Bearer fake-mi-token"
    # The api-key header must NOT be sent under managed identity.
    assert "api-key" not in {k.lower() for k in sent.headers}
    assert tp.calls == 1


@pytest.mark.unit
async def test_tool_calling_survives_under_token_auth() -> None:
    """Tool-call translation is auth-independent — a request with ``tools`` sent under
    Bearer auth still carries ``tools``/``tool_choice`` in the outgoing body (the
    ``_to_openai_request`` path is reused verbatim regardless of the auth header)."""

    tp = _FakeTokenProvider()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]
    with respx.mock(base_url=AZURE_BASE) as router:
        route = router.post(AZURE_CHAT_PATH).mock(
            return_value=httpx.Response(200, json=_chat_payload())
        )
        client = httpx.AsyncClient(base_url=AZURE_BASE)
        try:
            adapter = AzureOpenAIAdapter(
                name="azure-test",
                base_url=AZURE_BASE,
                api_key="",
                api_version=AZURE_API_VERSION,
                client=client,
                token_provider=tp,
            )
            await adapter.chat_completion(
                ChatCompletionRequest(
                    model="alias",
                    messages=[ChatCompletionMessage(role="user", content="weather in Riga?")],
                    tools=tools,
                    tool_choice="auto",
                ),
                model=AZURE_DEPLOYMENT,
                stream=False,
            )
        finally:
            await client.aclose()
    sent = route.calls.last.request
    assert sent.headers.get("authorization") == "Bearer fake-mi-token"
    body = json.loads(sent.content)
    assert body.get("tools")
    assert body["tools"][0]["function"]["name"] == "get_weather"
    assert body.get("tool_choice") == "auto"


@pytest.mark.unit
async def test_embeddings_send_bearer() -> None:
    from app.providers.openai_schema import EmbeddingsRequest

    payload = {
        "object": "list",
        "data": [{"object": "embedding", "embedding": [0.1, 0.2], "index": 0}],
        "model": AZURE_DEPLOYMENT,
        "usage": {"prompt_tokens": 3, "total_tokens": 3},
    }
    tp = _FakeTokenProvider("emb-token")
    with respx.mock(base_url=AZURE_BASE) as router:
        route = router.post(AZURE_EMBED_PATH).mock(return_value=httpx.Response(200, json=payload))
        client = httpx.AsyncClient(base_url=AZURE_BASE)
        try:
            adapter = AzureOpenAIAdapter(
                name="azure-test",
                base_url=AZURE_BASE,
                api_key="",
                api_version=AZURE_API_VERSION,
                client=client,
                token_provider=tp,
            )
            await adapter.embeddings(
                EmbeddingsRequest(model="alias", input="hello"),
                model=AZURE_DEPLOYMENT,
            )
        finally:
            await client.aclose()
    sent = route.calls.last.request
    assert sent.headers.get("authorization") == "Bearer emb-token"
    assert "api-key" not in {k.lower() for k in sent.headers}


@pytest.mark.unit
async def test_token_mint_failure_surfaces_as_network_error() -> None:
    """A token-mint failure maps to ProviderNetworkError (handled like unreachable),
    and never leaks token material."""

    client = httpx.AsyncClient(base_url=AZURE_BASE)
    try:
        adapter = AzureOpenAIAdapter(
            name="azure-test",
            base_url=AZURE_BASE,
            api_key="",
            api_version=AZURE_API_VERSION,
            client=client,
            token_provider=_FailingTokenProvider(),
        )
        with pytest.raises(ProviderNetworkError):
            await adapter.chat_completion(
                ChatCompletionRequest(
                    model="alias",
                    messages=[ChatCompletionMessage(role="user", content="hi")],
                ),
                model=AZURE_DEPLOYMENT,
                stream=False,
            )
    finally:
        await client.aclose()


@pytest.mark.unit
async def test_health_check_unhealthy_when_mint_fails() -> None:
    client = httpx.AsyncClient(base_url=AZURE_BASE)
    try:
        adapter = AzureOpenAIAdapter(
            name="azure-test",
            base_url=AZURE_BASE,
            api_key="",
            api_version=AZURE_API_VERSION,
            client=client,
            token_provider=_FailingTokenProvider(),
        )
        health = await adapter.health_check()
    finally:
        await client.aclose()
    assert health.reachable is False
    assert health.error is not None


# --- Wiring: from_config / build_adapter ------------------------------------


@pytest.mark.unit
def test_from_config_managed_identity_needs_no_key() -> None:
    """With the flag set, a provider with NO api key constructs (keyless)."""

    adapter = build_adapter(_azure_provider(), env={USE_MANAGED_IDENTITY_ENV: "true"})
    assert isinstance(adapter, AzureOpenAIAdapter)
    assert adapter._token_provider is not None
    assert adapter._api_key == ""


@pytest.mark.unit
def test_from_config_flag_unset_is_byte_identical_key_path() -> None:
    adapter = build_adapter(_azure_provider(), env={"AZURE_OPENAI_API_KEY": "plain-key"})
    assert isinstance(adapter, AzureOpenAIAdapter)
    assert adapter._token_provider is None
    assert adapter._api_key == "plain-key"


@pytest.mark.unit
def test_from_config_resource_override() -> None:
    adapter = build_adapter(
        _azure_provider(),
        env={USE_MANAGED_IDENTITY_ENV: "true", IDENTITY_RESOURCE_ENV: "https://ai.azure.com"},
    )
    assert isinstance(adapter, AzureOpenAIAdapter)
    assert adapter._token_provider is not None
    assert isinstance(adapter._token_provider, ManagedIdentityTokenProvider)
    assert adapter._token_provider._resource == "https://ai.azure.com"


@pytest.mark.unit
def test_from_config_no_key_no_flag_still_raises() -> None:
    """Without a key AND without the flag, construction still fails (unchanged)."""

    with pytest.raises(ValueError, match=r"(?i)environment variable|managed identity"):
        build_adapter(_azure_provider(), env={})
