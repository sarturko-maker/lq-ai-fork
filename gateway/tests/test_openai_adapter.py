"""Unit tests for the OpenAI provider adapter (Task C6 / ADR 0008).

Targets the embeddings translation, the auth-header wiring, the
chat-completion-stub posture, error mapping (auth, network, HTTP), and
``from_config`` construction.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import ProviderConfig
from app.providers import (
    OpenAIAdapter,
    ProviderAuthError,
    ProviderHTTPError,
    ProviderNetworkError,
    ProviderUnsupportedError,
)
from app.providers.openai_schema import (
    ChatCompletionMessage,
    ChatCompletionRequest,
    EmbeddingsRequest,
)

# --- Construction -------------------------------------------------------


def _provider(provider_type: str = "openai") -> ProviderConfig:
    return ProviderConfig.model_validate(
        {
            "name": "openai-prod",
            "type": provider_type,
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY_TEST",
            "tier": 4,
            "models": ["text-embedding-3-small"],
        }
    )


@pytest.mark.unit
def test_from_config_accepts_openai_provider_with_key() -> None:
    """C6: OpenAI provider with a key in env constructs cleanly."""

    adapter = OpenAIAdapter.from_config(
        _provider(),
        env={"OPENAI_API_KEY_TEST": "sk-test-123"},
    )
    assert adapter.name == "openai-prod"


@pytest.mark.unit
def test_from_config_rejects_wrong_type() -> None:
    """C6: a non-openai provider type raises ValueError."""

    bogus = ProviderConfig.model_validate(
        {
            "name": "x",
            "type": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key_env": "ANTHROPIC_API_KEY",
            "tier": 4,
            "models": [],
        }
    )
    with pytest.raises(ValueError, match=r"(?i)provider\.type"):
        OpenAIAdapter.from_config(bogus, env={})


@pytest.mark.unit
def test_from_config_cloud_openai_requires_key() -> None:
    """C6: cloud OpenAI without OPENAI_API_KEY raises ValueError."""

    with pytest.raises(ValueError, match=r"(?i)environment variable"):
        OpenAIAdapter.from_config(_provider(), env={})


@pytest.mark.unit
def test_from_config_openai_compatible_no_key_ok() -> None:
    """C6: openai_compatible (local vLLM/llama-cpp) accepts a missing key."""

    config = ProviderConfig.model_validate(
        {
            "name": "vllm-local",
            "type": "openai_compatible",
            "base_url": "http://vllm:8000/v1",
            "api_key_env": "",
            "tier": 1,
            "models": [],
        }
    )
    adapter = OpenAIAdapter.from_config(config, env={})
    assert adapter.name == "vllm-local"


# --- Embeddings ---------------------------------------------------------


@pytest.mark.unit
async def test_embeddings_happy_path() -> None:
    """C6: a 200 response from upstream translates to EmbeddingsResponse."""

    payload = {
        "object": "list",
        "data": [{"object": "embedding", "embedding": [0.1, 0.2, 0.3], "index": 0}],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/embeddings").mock(return_value=httpx.Response(200, json=payload))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            response = await adapter.embeddings(
                EmbeddingsRequest(model="text-embedding-3-small", input="hello"),
                model="text-embedding-3-small",
            )
        finally:
            await client.aclose()
    assert len(response.data) == 1
    assert response.data[0].embedding == [0.1, 0.2, 0.3]
    assert response.usage.prompt_tokens == 5


@pytest.mark.unit
async def test_embeddings_batch_input() -> None:
    """C6: batched input produces multiple data entries."""

    payload = {
        "object": "list",
        "data": [
            {"object": "embedding", "embedding": [0.1], "index": 0},
            {"object": "embedding", "embedding": [0.2], "index": 1},
        ],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 4, "total_tokens": 4},
    }
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/embeddings").mock(return_value=httpx.Response(200, json=payload))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            response = await adapter.embeddings(
                EmbeddingsRequest(
                    model="text-embedding-3-small",
                    input=["a", "b"],
                ),
                model="text-embedding-3-small",
            )
        finally:
            await client.aclose()
    assert len(response.data) == 2
    # Check the request body had list input.
    sent = route.calls.last.request
    body = sent.content
    assert b'"input":["a","b"]' in body or b'"input": ["a", "b"]' in body


@pytest.mark.unit
async def test_embeddings_dimensions_passthrough() -> None:
    """C6: caller-set ``dimensions`` flows through to the upstream body."""

    payload = {
        "object": "list",
        "data": [{"object": "embedding", "embedding": [0.1], "index": 0}],
        "model": "text-embedding-3-large",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/embeddings").mock(return_value=httpx.Response(200, json=payload))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            await adapter.embeddings(
                EmbeddingsRequest(
                    model="text-embedding-3-large",
                    input="hello",
                    dimensions=512,
                ),
                model="text-embedding-3-large",
            )
        finally:
            await client.aclose()
    sent = route.calls.last.request
    assert b'"dimensions":512' in sent.content or b'"dimensions": 512' in sent.content


@pytest.mark.unit
async def test_embeddings_auth_error_translates_to_provider_auth_error() -> None:
    """C6: 401 from upstream raises ProviderAuthError."""

    error_body = {
        "error": {
            "message": "Incorrect API key provided",
            "type": "invalid_request_error",
            "code": "invalid_api_key",
        }
    }
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/embeddings").mock(return_value=httpx.Response(401, json=error_body))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            with pytest.raises(ProviderAuthError):
                await adapter.embeddings(
                    EmbeddingsRequest(model="x", input="y"),
                    model="x",
                )
        finally:
            await client.aclose()


@pytest.mark.unit
async def test_embeddings_500_translates_to_provider_http_error() -> None:
    """C6: 500 from upstream raises ProviderHTTPError with upstream_status."""

    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/embeddings").mock(
            return_value=httpx.Response(500, json={"error": {"message": "boom"}})
        )
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            with pytest.raises(ProviderHTTPError) as exc_info:
                await adapter.embeddings(
                    EmbeddingsRequest(model="x", input="y"),
                    model="x",
                )
            assert exc_info.value.upstream_status == 500
        finally:
            await client.aclose()


@pytest.mark.unit
async def test_embeddings_network_error_translates() -> None:
    """C6: a transport failure (DNS/TCP) raises ProviderNetworkError."""

    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/embeddings").mock(side_effect=httpx.ConnectError("boom"))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            with pytest.raises(ProviderNetworkError):
                await adapter.embeddings(
                    EmbeddingsRequest(model="x", input="y"),
                    model="x",
                )
        finally:
            await client.aclose()


@pytest.mark.unit
async def test_embeddings_authorization_header_set() -> None:
    """C6: cloud OpenAI calls carry a Bearer Authorization header."""

    payload = {
        "object": "list",
        "data": [{"object": "embedding", "embedding": [0.1], "index": 0}],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/embeddings").mock(return_value=httpx.Response(200, json=payload))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test-123",
                client=client,
            )
            await adapter.embeddings(
                EmbeddingsRequest(model="x", input="y"),
                model="x",
            )
        finally:
            await client.aclose()
    sent = route.calls.last.request
    assert sent.headers.get("authorization") == "Bearer sk-test-123"


@pytest.mark.unit
async def test_embeddings_no_authorization_when_no_key() -> None:
    """C6: openai_compatible providers without keys omit the header entirely.

    Some local servers reject any Authorization header outright; we skip
    rather than send 'Bearer ' (empty).
    """

    payload = {
        "object": "list",
        "data": [{"object": "embedding", "embedding": [0.1], "index": 0}],
        "model": "x",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }
    with respx.mock(base_url="http://vllm:8000/v1") as router:
        route = router.post("/embeddings").mock(return_value=httpx.Response(200, json=payload))
        client = httpx.AsyncClient(base_url="http://vllm:8000/v1")
        try:
            adapter = OpenAIAdapter(
                name="vllm-local",
                base_url="http://vllm:8000/v1",
                api_key="",
                client=client,
            )
            await adapter.embeddings(
                EmbeddingsRequest(model="x", input="y"),
                model="x",
            )
        finally:
            await client.aclose()
    sent = route.calls.last.request
    assert "authorization" not in {k.lower() for k in sent.headers}


# --- Chat completions (stubbed) ----------------------------------------


@pytest.mark.unit
async def test_chat_completion_raises_unsupported() -> None:
    """C6: chat completions are deferred to B6; the call raises."""

    adapter = OpenAIAdapter(
        name="openai-prod",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )
    try:
        with pytest.raises(ProviderUnsupportedError):
            await adapter.chat_completion(
                ChatCompletionRequest(
                    model="gpt-4o",
                    messages=[ChatCompletionMessage(role="user", content="hi")],
                ),
                model="gpt-4o",
                stream=False,
            )
    finally:
        await adapter.aclose()


# --- Health --------------------------------------------------------------


@pytest.mark.unit
async def test_health_check_ok() -> None:
    """C6: GET /models 200 means reachable + key accepted."""

    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.get("/models").mock(return_value=httpx.Response(200, json={"data": []}))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            health = await adapter.health_check()
        finally:
            await client.aclose()
    assert health.reachable is True
    assert health.error is None


@pytest.mark.unit
async def test_health_check_auth_rejected() -> None:
    """C6: GET /models 401 reports reachable but auth-rejected."""

    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.get("/models").mock(return_value=httpx.Response(401, json={}))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="bad",
                client=client,
            )
            health = await adapter.health_check()
        finally:
            await client.aclose()
    assert health.reachable is True
    assert "auth" in (health.error or "").lower()
