"""F0-S9: the factory's chat model satisfies the agent-harness contract.

Three pins, all prerequisites to any model-qualification score being
real (docs/fork/research/deepagents-ecosystem.md §1.2-1.3):

* ``use_responses_api=False`` — langchain-openai's Responses-API
  auto-detect breaks OpenAI-compatible endpoints (deepagents#3190).
* ``profile["max_input_tokens"]`` set — deepagents' summarization
  middleware falls back to a fixed 170k-token trigger for unprofiled
  models; with the profile the trigger is window-relative (0.85x).
* the MiniMax-M3 harness profile resolves for every gateway alias the
  agent loop dispatches on — qualification is per-(model, profile).
"""

from __future__ import annotations

import httpx
import pytest

from app.agents.factory import (
    DEFAULT_MAX_INPUT_TOKENS,
    build_gateway_chat_model,
    build_gateway_http_client,
)
from app.agents.profiles import (
    _GATEWAY_ALIAS_PROFILE_KEYS,
    ensure_harness_profiles_registered,
)

pytestmark = pytest.mark.unit


def _model(**kwargs: object):  # test helper; return type is ChatOpenAI
    client = build_gateway_http_client(
        gateway_key="test-gateway-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
    )
    return build_gateway_chat_model(
        gateway_url="http://gateway.test:8001",
        http_async_client=client,
        **kwargs,  # type: ignore[arg-type]
    )


def test_responses_api_pinned_off() -> None:
    """deepagents#3190: Chat Completions pinned, never auto-detected."""
    assert _model().use_responses_api is False


def test_model_profile_carries_max_input_tokens() -> None:
    model = _model()
    assert model.profile == {"max_input_tokens": DEFAULT_MAX_INPUT_TOKENS}


def test_max_input_tokens_override_and_opt_out() -> None:
    assert _model(max_input_tokens=64_000).profile == {"max_input_tokens": 64_000}
    assert _model(max_input_tokens=None).profile is None


def test_profile_activates_window_relative_compaction() -> None:
    """Pins the deepagents contract the profile exists for: WITH
    max_input_tokens the summarization trigger is fraction-based; the
    unprofiled fallback is the fixed 170k-token trigger that would
    never fire window-relative compaction."""
    from deepagents.middleware.summarization import compute_summarization_defaults

    profiled = compute_summarization_defaults(_model())
    assert profiled["trigger"] == ("fraction", 0.85)

    unprofiled = compute_summarization_defaults(_model(max_input_tokens=None))
    assert unprofiled["trigger"] == ("tokens", 170000)


def test_harness_profile_resolves_for_every_gateway_alias() -> None:
    """The registry keys must match how deepagents derives a profile key
    for a pre-built model (``{provider}:{identifier}``). Pins the
    version-pinned package's derivation + registry lookup directly —
    ``_harness_profile_for_model`` falls back to an empty profile on a
    MISS, so the null-returning getter is the only honest assertion; if
    a deepagents bump changes key derivation, this test is the tripwire."""
    from deepagents._models import get_model_identifier, get_model_provider
    from deepagents.profiles.harness.harness_profiles import _get_harness_profile

    ensure_harness_profiles_registered()

    for alias in ("smart", "fast", "budget"):
        model = _model(model_alias=alias)
        derived_key = f"{get_model_provider(model)}:{get_model_identifier(model)}"
        assert derived_key == f"openai:{alias}"
        assert derived_key in _GATEWAY_ALIAS_PROFILE_KEYS
        assert _get_harness_profile(derived_key) is not None
