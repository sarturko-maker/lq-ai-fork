"""Real-provider integration test for the Anthropic adapter.

Per CONTRIBUTING.md, tests that hit a real LLM provider are marked
``@pytest.mark.provider`` and skipped unless the relevant credential
environment variable is set. They run nightly in CI, not on every PR.

This file covers the verification step from
``docs/M1-IMPLEMENTATION-ORDER.md`` Task B3:

    With ANTHROPIC_API_KEY set, `curl` request to /v1/chat/completions
    with model `claude-sonnet-4-6` returns a real completion.

The test calls ``claude-haiku-4-5`` (cheapest tier in the example
config) by default to keep nightly cost minimal; operators can override
with ``LQ_AI_ANTHROPIC_TEST_MODEL`` in the test environment.
"""

from __future__ import annotations

import os

import httpx
import pytest

from app.providers import AnthropicAdapter, ChatCompletionRequest, ChatCompletionResponse

DEFAULT_TEST_MODEL = os.environ.get("LQ_AI_ANTHROPIC_TEST_MODEL", "claude-haiku-4-5")


@pytest.mark.provider
async def test_real_anthropic_chat_completion_roundtrip() -> None:
    """Live call against api.anthropic.com — only runs when
    ``ANTHROPIC_API_KEY`` is set."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set; skipping real-provider test")

    adapter = AnthropicAdapter(
        name="anthropic-real",
        base_url="https://api.anthropic.com",
        api_key=api_key,
        timeout_s=30.0,
    )
    try:
        request = ChatCompletionRequest.model_validate(
            {
                "model": DEFAULT_TEST_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": "Reply with the single word PONG and nothing else.",
                    }
                ],
                "max_tokens": 16,
                "temperature": 0.0,
            }
        )
        result = await adapter.chat_completion(request, model=DEFAULT_TEST_MODEL, stream=False)
    except httpx.HTTPError as exc:
        pytest.skip(f"network failure reaching Anthropic: {exc}")
    finally:
        await adapter.aclose()

    assert isinstance(result, ChatCompletionResponse)
    assert result.choices, "Anthropic returned no choices"
    content = result.choices[0].message.content or ""
    assert "PONG" in content.upper()
    assert result.usage.prompt_tokens > 0
    assert result.usage.completion_tokens > 0
