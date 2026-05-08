"""Unit tests for the B4 router (alias resolution + tier derivation + fallback).

These tests exercise :mod:`app.router` directly without spinning up the
FastAPI app. Adapter behavior is faked with a :class:`FakeAdapter`
implementing the :class:`ProviderAdapter` contract; the router doesn't
care that the adapter isn't real, only that it implements the contract.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.config import (
    CostRateEntry,
    GatewayConfig,
    InferenceTiersConfig,
    ModelAliasConfig,
    ModelTarget,
    ProviderConfig,
)
from app.config_loader import ConfigLoadError, load_config
from app.providers import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ProviderAdapter,
    ProviderAuthError,
    ProviderHealth,
    ProviderHTTPError,
    ProviderNetworkError,
    ProviderUnsupportedError,
)
from app.router import (
    ModelResolutionError,
    NoAdapterAvailableError,
    Router,
    derive_routed_inference_tier,
    estimate_cost,
    is_fallback_eligible,
    resolve_alias_chain,
    synthesize_request_id,
)

# --- Fixtures -----------------------------------------------------------------


def _provider(
    name: str,
    *,
    type_: str = "anthropic",
    tier: int = 4,
    models: list[str] | None = None,
    enabled: bool = True,
) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        type=type_,  # type: ignore[arg-type]
        base_url=f"https://{name}.example.com",
        api_key_env=f"{name.upper().replace('-', '_')}_API_KEY",
        tier=tier,
        models=models or [],
        enabled=enabled,
    )


def _config(
    *,
    providers: list[ProviderConfig],
    aliases: dict[str, ModelAliasConfig] | None = None,
    inference_tiers: InferenceTiersConfig | None = None,
    rates: dict[str, CostRateEntry] | None = None,
) -> GatewayConfig:
    raw: dict[str, Any] = {
        "providers": [p.model_dump(exclude_none=True) for p in providers],
        "model_aliases": ({k: v.model_dump(exclude_none=True) for k, v in (aliases or {}).items()}),
    }
    if inference_tiers is not None:
        raw["inference_tiers"] = inference_tiers.model_dump(exclude_none=True)
    if rates is not None:
        raw["cost_tracking"] = {
            "rates": {k: v.model_dump(exclude_none=True) for k, v in rates.items()},
        }
    return GatewayConfig.model_validate(raw)


class FakeAdapter(ProviderAdapter):
    """In-memory adapter for router tests."""

    def __init__(
        self,
        name: str,
        *,
        response: ChatCompletionResponse | None = None,
        chunks: list[ChatCompletionChunk] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.name = name
        self._response = response
        self._chunks = chunks or []
        self._raises = raises
        self.calls: list[tuple[str, bool]] = []

    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        *,
        model: str,
        stream: bool,
    ) -> ChatCompletionResponse | AsyncIterator[ChatCompletionChunk]:
        self.calls.append((model, stream))
        if self._raises is not None:
            raise self._raises
        if stream:

            async def gen() -> AsyncIterator[ChatCompletionChunk]:
                for chunk in self._chunks:
                    yield chunk

            return gen()
        if self._response is None:
            raise RuntimeError("FakeAdapter has no response configured")
        return self._response

    async def embeddings(self, request: Any, *, model: str) -> Any:
        raise ProviderUnsupportedError("not used in tests", details={"model": model})

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, reachable=True, latency_ms=1)

    async def aclose(self) -> None:
        return None


def _ok_response(model: str = "claude-opus-4-7") -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="cc_test",
        created=1_700_000_000,
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content="ok"),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(prompt_tokens=12, completion_tokens=7, total_tokens=19),
    )


# --- Alias resolution: single-level ------------------------------------------


@pytest.mark.unit
def test_resolve_alias_single_level() -> None:
    """``smart`` -> ``(anthropic-prod, claude-opus-4-7)`` with no fallback."""

    cfg = _config(
        providers=[_provider("anthropic-prod", tier=4, models=["claude-opus-4-7"])],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
            ),
        },
    )

    candidates = resolve_alias_chain(requested_model="smart", config=cfg)

    assert len(candidates) == 1
    primary = candidates[0]
    assert primary.provider.name == "anthropic-prod"
    assert primary.native_model == "claude-opus-4-7"
    assert primary.role == "primary"
    assert primary.routed_inference_tier == 4


@pytest.mark.unit
def test_resolve_alias_with_fallback() -> None:
    """Primary + fallback in declaration order."""

    cfg = _config(
        providers=[
            _provider("anthropic-prod", tier=4, models=["claude-opus-4-7"]),
            _provider("openai-prod", type_="openai", tier=4, models=["gpt-4-turbo"]),
        ],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
                fallback=[ModelTarget(provider="openai-prod", model="gpt-4-turbo")],
            ),
        },
    )

    candidates = resolve_alias_chain(requested_model="smart", config=cfg)

    assert [c.provider.name for c in candidates] == ["anthropic-prod", "openai-prod"]
    assert [c.role for c in candidates] == ["primary", "fallback"]


@pytest.mark.unit
def test_resolve_alias_native_model_passthrough() -> None:
    """A provider-native model name resolves directly without an alias."""

    cfg = _config(
        providers=[
            _provider("anthropic-prod", tier=4, models=["claude-opus-4-7", "claude-sonnet-4-6"]),
        ],
    )

    candidates = resolve_alias_chain(requested_model="claude-sonnet-4-6", config=cfg)

    assert len(candidates) == 1
    assert candidates[0].native_model == "claude-sonnet-4-6"
    assert candidates[0].provider.name == "anthropic-prod"
    assert candidates[0].role == "primary"


@pytest.mark.unit
def test_resolve_alias_unknown_model_raises() -> None:
    cfg = _config(
        providers=[_provider("anthropic-prod", tier=4, models=["claude-opus-4-7"])],
    )

    with pytest.raises(ModelResolutionError, match="does not resolve"):
        resolve_alias_chain(requested_model="unknown-model", config=cfg)


@pytest.mark.unit
def test_resolve_alias_skips_duplicate_fallback() -> None:
    """A fallback duplicating the primary is silently dropped."""

    cfg = _config(
        providers=[_provider("anthropic-prod", tier=4, models=["claude-opus-4-7"])],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
                fallback=[ModelTarget(provider="anthropic-prod", model="claude-opus-4-7")],
            ),
        },
    )

    candidates = resolve_alias_chain(requested_model="smart", config=cfg)
    assert len(candidates) == 1


# --- Alias resolution: multi-level -------------------------------------------


@pytest.mark.unit
def test_resolve_alias_multi_level() -> None:
    """``premium -> smart -> claude-opus-4-7`` resolves through both hops."""

    cfg = _config(
        providers=[_provider("anthropic-prod", tier=4, models=["claude-opus-4-7"])],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
            ),
            "premium": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="smart"),
            ),
        },
    )

    candidates = resolve_alias_chain(requested_model="premium", config=cfg)

    assert len(candidates) == 1
    assert candidates[0].native_model == "claude-opus-4-7"


# --- Cycle detection at config load -----------------------------------------


@pytest.mark.unit
def test_alias_cycle_rejected_at_load(tmp_path: Any) -> None:
    """``a -> b -> a`` is rejected at config load, not at request time."""

    cfg_path = tmp_path / "gw.yaml"
    cfg_path.write_text(
        """
providers:
  - name: anthropic-prod
    type: anthropic
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    tier: 4
    models: [claude-opus-4-7]
model_aliases:
  a:
    primary: {provider: anthropic-prod, model: b}
  b:
    primary: {provider: anthropic-prod, model: a}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError, match="cycle"):
        load_config(cfg_path)


@pytest.mark.unit
def test_alias_self_loop_rejected_at_load(tmp_path: Any) -> None:
    """An alias whose primary.model is its own name is a 1-cycle."""

    cfg_path = tmp_path / "gw.yaml"
    cfg_path.write_text(
        """
providers:
  - name: anthropic-prod
    type: anthropic
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    tier: 4
    models: [claude-opus-4-7]
model_aliases:
  loopy:
    primary: {provider: anthropic-prod, model: loopy}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError, match="cycle"):
        load_config(cfg_path)


@pytest.mark.unit
def test_alias_chain_too_deep_rejected(tmp_path: Any) -> None:
    """A linear chain longer than MAX_ALIAS_DEPTH is rejected."""

    levels = "\n".join(
        f"  a{i}:\n    primary: {{provider: anthropic-prod, model: a{i + 1}}}" for i in range(20)
    )
    cfg_path = tmp_path / "gw.yaml"
    cfg_path.write_text(
        f"""
providers:
  - name: anthropic-prod
    type: anthropic
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    tier: 4
    models: [claude-opus-4-7]
model_aliases:
{levels}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError):
        load_config(cfg_path)


# --- Tier derivation ---------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "provider_type,defaults,expected",
    [
        ("anthropic", {"anthropic": 4}, 4),
        ("openai", {"openai": 4}, 4),
        ("ollama", {"ollama": 1}, 1),
        ("vertex", {"vertex": 3}, 3),
        ("bedrock", {"bedrock": 3}, 3),
    ],
)
def test_tier_derivation_uses_provider_type_default(
    provider_type: str, defaults: dict[str, int], expected: int
) -> None:
    """``inference_tiers.defaults[<provider_type>]`` wins over the provider's tier."""

    provider = _provider("p1", type_=provider_type, tier=5)  # provider says 5
    tiers = InferenceTiersConfig(defaults=defaults)  # type: ignore[arg-type]

    derived = derive_routed_inference_tier(
        provider=provider,
        native_model="m1",
        inference_tiers=tiers,
    )
    assert derived == expected


@pytest.mark.unit
def test_tier_derivation_pair_override_beats_defaults() -> None:
    provider = _provider("anthropic-prod", type_="anthropic", tier=4)
    tiers = InferenceTiersConfig(
        defaults={"anthropic": 4},  # type: ignore[arg-type]
        overrides={"anthropic-prod/claude-opus-4-7": 3},
    )

    derived = derive_routed_inference_tier(
        provider=provider,
        native_model="claude-opus-4-7",
        inference_tiers=tiers,
    )
    assert derived == 3


@pytest.mark.unit
def test_tier_derivation_provider_override_beats_defaults() -> None:
    provider = _provider("anthropic-prod", type_="anthropic", tier=4)
    tiers = InferenceTiersConfig(
        defaults={"anthropic": 4},  # type: ignore[arg-type]
        overrides={"anthropic-prod": 2},
    )

    derived = derive_routed_inference_tier(
        provider=provider,
        native_model="claude-opus-4-7",
        inference_tiers=tiers,
    )
    assert derived == 2


@pytest.mark.unit
def test_tier_derivation_fallback_to_provider_tier_when_no_block() -> None:
    """With no ``inference_tiers`` block, provider's own tier is used."""

    provider = _provider("anthropic-prod", type_="anthropic", tier=4)
    tiers = InferenceTiersConfig()

    derived = derive_routed_inference_tier(
        provider=provider,
        native_model="claude-opus-4-7",
        inference_tiers=tiers,
    )
    assert derived == 4


@pytest.mark.unit
def test_tier_derivation_pair_override_more_specific_than_provider_override() -> None:
    """Pair-level override is more specific than provider-level override."""

    provider = _provider("p1", type_="anthropic", tier=4)
    tiers = InferenceTiersConfig(
        overrides={"p1": 3, "p1/m-special": 2},
    )

    assert (
        derive_routed_inference_tier(
            provider=provider, native_model="m-default", inference_tiers=tiers
        )
        == 3
    )
    assert (
        derive_routed_inference_tier(
            provider=provider, native_model="m-special", inference_tiers=tiers
        )
        == 2
    )


# --- Cost estimate -----------------------------------------------------------


@pytest.mark.unit
def test_estimate_cost_returns_none_for_unknown_pair() -> None:
    cost = estimate_cost(
        provider_name="p1",
        native_model="m1",
        usage=ChatCompletionUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
        rates={},
    )
    assert cost is None


@pytest.mark.unit
def test_estimate_cost_computes_decimal_with_4dp() -> None:
    cost = estimate_cost(
        provider_name="anthropic-prod",
        native_model="claude-opus-4-7",
        usage=ChatCompletionUsage(prompt_tokens=1_000_000, completion_tokens=500_000),
        rates={
            "anthropic-prod/claude-opus-4-7": CostRateEntry(
                input_per_mtok=15.0, output_per_mtok=75.0
            )
        },
    )
    # 15 USD/MTok * 1MTok input + 75 * 0.5MTok output = 15 + 37.5 = 52.5
    assert cost == Decimal("52.5000")


# --- Fallback eligibility ----------------------------------------------------


@pytest.mark.unit
def test_fallback_eligibility() -> None:
    """Network errors and 5xx/429 are eligible; auth and 4xx are not."""

    assert is_fallback_eligible(ProviderNetworkError("dns")) is True
    assert is_fallback_eligible(ProviderHTTPError("svc down", upstream_status=503)) is True
    assert is_fallback_eligible(ProviderHTTPError("rate", upstream_status=429)) is True
    assert is_fallback_eligible(ProviderHTTPError("bad req", upstream_status=400)) is False
    assert is_fallback_eligible(ProviderAuthError("nope")) is False
    assert is_fallback_eligible(ProviderUnsupportedError("nope")) is False


# --- Router behavior with fakes ---------------------------------------------


@pytest.mark.unit
async def test_router_returns_primary_response() -> None:
    cfg = _config(
        providers=[_provider("anthropic-prod", tier=4, models=["claude-opus-4-7"])],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
            ),
        },
    )
    adapter = FakeAdapter("anthropic-prod", response=_ok_response())
    router = Router(config=cfg, adapters={"anthropic-prod": adapter})

    request = ChatCompletionRequest(
        model="smart",
        messages=[ChatCompletionMessage(role="user", content="hi")],
    )

    result = await router.chat_completion(request)

    assert result.target.provider.name == "anthropic-prod"
    assert result.target.routed_inference_tier == 4
    assert result.fallbacks_tried == []
    assert adapter.calls == [("claude-opus-4-7", False)]


@pytest.mark.unit
async def test_router_falls_back_on_5xx() -> None:
    cfg = _config(
        providers=[
            _provider("anthropic-prod", tier=4, models=["claude-opus-4-7"]),
            _provider("openai-prod", type_="openai", tier=4, models=["gpt-4-turbo"]),
        ],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
                fallback=[ModelTarget(provider="openai-prod", model="gpt-4-turbo")],
            ),
        },
    )
    primary = FakeAdapter(
        "anthropic-prod",
        raises=ProviderHTTPError("Internal error", upstream_status=503),
    )
    fallback = FakeAdapter("openai-prod", response=_ok_response("gpt-4-turbo"))
    router = Router(
        config=cfg,
        adapters={"anthropic-prod": primary, "openai-prod": fallback},
    )

    request = ChatCompletionRequest(
        model="smart",
        messages=[ChatCompletionMessage(role="user", content="hi")],
    )
    result = await router.chat_completion(request)

    assert result.target.provider.name == "openai-prod"
    # Primary tried first and failed -> in fallbacks_tried.
    assert result.fallbacks_tried == ["anthropic-prod"]
    # Primary was attempted exactly once.
    assert primary.calls == [("claude-opus-4-7", False)]
    assert fallback.calls == [("gpt-4-turbo", False)]


@pytest.mark.unit
async def test_router_does_not_fall_back_on_auth_error() -> None:
    """Auth errors must surface immediately — wearing out the next provider's
    credentials is operator-hostile."""

    from app.router import RoutedProviderError

    cfg = _config(
        providers=[
            _provider("anthropic-prod", tier=4, models=["claude-opus-4-7"]),
            _provider("openai-prod", type_="openai", tier=4, models=["gpt-4-turbo"]),
        ],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
                fallback=[ModelTarget(provider="openai-prod", model="gpt-4-turbo")],
            ),
        },
    )
    primary = FakeAdapter("anthropic-prod", raises=ProviderAuthError("bad key"))
    fallback = FakeAdapter("openai-prod", response=_ok_response())
    router = Router(
        config=cfg,
        adapters={"anthropic-prod": primary, "openai-prod": fallback},
    )

    request = ChatCompletionRequest(
        model="smart",
        messages=[ChatCompletionMessage(role="user", content="hi")],
    )
    with pytest.raises(RoutedProviderError) as exc_info:
        await router.chat_completion(request)
    # The wrapped error is the original auth error; the wrapper carries the
    # target attribution that the route handler needs for the audit row.
    assert isinstance(exc_info.value.error, ProviderAuthError)
    assert exc_info.value.target.provider.name == "anthropic-prod"
    # Fallback must not have been called.
    assert fallback.calls == []


@pytest.mark.unit
async def test_router_returns_no_adapter_error_when_registry_empty() -> None:
    cfg = _config(
        providers=[_provider("anthropic-prod", tier=4, models=["claude-opus-4-7"])],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
            ),
        },
    )
    router = Router(config=cfg, adapters={})  # nothing instantiated

    request = ChatCompletionRequest(
        model="smart",
        messages=[ChatCompletionMessage(role="user", content="hi")],
    )
    with pytest.raises(NoAdapterAvailableError):
        await router.chat_completion(request)


@pytest.mark.unit
async def test_router_falls_through_missing_adapter_to_fallback() -> None:
    """A primary with no instantiated adapter is skipped, not an error."""

    cfg = _config(
        providers=[
            _provider("anthropic-prod", tier=4, models=["claude-opus-4-7"]),
            _provider("openai-prod", type_="openai", tier=4, models=["gpt-4-turbo"]),
        ],
        aliases={
            "smart": ModelAliasConfig(
                primary=ModelTarget(provider="anthropic-prod", model="claude-opus-4-7"),
                fallback=[ModelTarget(provider="openai-prod", model="gpt-4-turbo")],
            ),
        },
    )
    fallback = FakeAdapter("openai-prod", response=_ok_response("gpt-4-turbo"))
    router = Router(config=cfg, adapters={"openai-prod": fallback})

    request = ChatCompletionRequest(
        model="smart",
        messages=[ChatCompletionMessage(role="user", content="hi")],
    )
    result = await router.chat_completion(request)
    assert result.target.provider.name == "openai-prod"
    # Primary had no adapter -> recorded in fallbacks_tried.
    assert result.fallbacks_tried == ["anthropic-prod"]


@pytest.mark.unit
async def test_router_propagates_resolution_error_when_model_unknown() -> None:
    cfg = _config(providers=[_provider("anthropic-prod", tier=4, models=["m1"])])
    router = Router(config=cfg, adapters={})

    request = ChatCompletionRequest(
        model="unknown",
        messages=[ChatCompletionMessage(role="user", content="hi")],
    )
    with pytest.raises(ModelResolutionError):
        await router.chat_completion(request)


# --- Misc ---------------------------------------------------------------------


@pytest.mark.unit
def test_synthesize_request_id_uses_provided_value() -> None:
    assert synthesize_request_id("req_abc") == "req_abc"


@pytest.mark.unit
def test_synthesize_request_id_generates_when_none() -> None:
    assert synthesize_request_id(None).startswith("req_")


@pytest.mark.unit
async def test_router_chat_completion_uses_async_mock() -> None:
    """Sanity: the router treats the adapter as a black-box async API.

    Demonstrates the dispatch contract is registry-based, not type-coupled
    to AnthropicAdapter — any implementation of the protocol plugs in.
    """

    response = _ok_response()
    adapter = AsyncMock(spec=ProviderAdapter)
    adapter.chat_completion.return_value = response
    adapter.name = "fake-prod"

    cfg = _config(
        providers=[_provider("fake-prod", type_="anthropic", tier=2, models=["m1"])],
    )
    router = Router(config=cfg, adapters={"fake-prod": adapter})

    request = ChatCompletionRequest(
        model="m1",
        messages=[ChatCompletionMessage(role="user", content="hi")],
    )
    result = await router.chat_completion(request)

    assert result.target.routed_inference_tier == 2
    adapter.chat_completion.assert_awaited_once()
