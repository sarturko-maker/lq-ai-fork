"""Unit tests for the OpenAI provider adapter (Task C6 / ADR 0008).

Targets the embeddings translation, the auth-header wiring, the
chat-completion-stub posture, error mapping (auth, network, HTTP), and
``from_config`` construction.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.config import ProviderConfig
from app.providers import (
    ChatCompletionChunk,
    ChatCompletionResponse,
    OpenAIAdapter,
    ProviderAuthError,
    ProviderHTTPError,
    ProviderNetworkError,
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


# --- Chat completions (B6) ----------------------------------------------


def _basic_chat_request(stream: bool = False) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="gpt-4o",
        messages=[
            ChatCompletionMessage(role="system", content="be brief"),
            ChatCompletionMessage(role="user", content="say hi"),
        ],
        max_tokens=64,
        stream=stream,
    )


@pytest.mark.unit
async def test_chat_completion_unary_happy_path() -> None:
    """B6: a 200 response translates to ChatCompletionResponse with usage."""

    payload = {
        "id": "chatcmpl-abc123",
        "object": "chat.completion",
        "created": 1715000000,
        "model": "gpt-4o-2024-08-06",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hi there!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
    }
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            result = await adapter.chat_completion(
                _basic_chat_request(), model="gpt-4o", stream=False
            )
        finally:
            await client.aclose()
    assert isinstance(result, ChatCompletionResponse)
    assert result.id == "chatcmpl-abc123"
    assert result.choices[0].message.content == "Hi there!"
    assert result.choices[0].finish_reason == "stop"
    assert result.usage.total_tokens == 14
    # The request we sent upstream uses the provider-native model name
    # (not whatever the alias resolved from) and stream=False.
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "gpt-4o"
    assert sent["stream"] is False


@pytest.mark.unit
async def test_chat_completion_strips_lq_ai_extension_keys() -> None:
    """B6: LQ.AI extension fields never leak to OpenAI (it 400s on unknowns)."""

    payload = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
    }
    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatCompletionMessage(role="user", content="hi")],
        minimum_inference_tier=3,
        skill_name="nda-review",
        lq_ai_skills=["nda-review"],
        lq_ai_chat_id="11111111-1111-1111-1111-111111111111",
        lq_ai_message_id="22222222-2222-2222-2222-222222222222",
        lq_ai_user_id="33333333-3333-3333-3333-333333333333",
        lq_ai_purpose="judge_paraphrase",
        chat_id="audit-tag",
        anonymize=True,
    )
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            await adapter.chat_completion(request, model="gpt-4o", stream=False)
        finally:
            await client.aclose()
    sent = json.loads(route.calls.last.request.content)
    for forbidden in (
        "minimum_inference_tier",
        "lq_ai_project_minimum_inference_tier",
        "skill_name",
        "chat_id",
        "anonymize",
        "lq_ai_skills",
        "lq_ai_skill_inputs",
        "lq_ai_inline_skills",
        "lq_ai_chat_id",
        "lq_ai_message_id",
        "lq_ai_user_id",
        "lq_ai_purpose",
    ):
        assert forbidden not in sent, f"LQ.AI extension {forbidden!r} leaked to OpenAI"


@pytest.mark.unit
async def test_chat_completion_strips_per_message_lq_ai_skip_anonymization() -> None:
    """M2-D2: per-message ``lq_ai_skip_anonymization`` is stripped before sending.

    OpenAI's body validation rejects unknown fields, including
    unknown per-message fields. The api/ sets this flag on the
    retrieval-context system message so the gateway middleware
    leaves the content un-pseudonymized, but the flag itself must
    never leave the gateway — OpenAI would 400.
    """

    payload = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
    }
    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[
            ChatCompletionMessage(
                role="system",
                content="Retrieved context: ...",
                lq_ai_skip_anonymization=True,
            ),
            ChatCompletionMessage(role="user", content="hi"),
        ],
    )
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            await adapter.chat_completion(request, model="gpt-4o", stream=False)
        finally:
            await client.aclose()
    sent = json.loads(route.calls.last.request.content)
    for msg in sent["messages"]:
        assert "lq_ai_skip_anonymization" not in msg, (
            f"per-message LQ.AI extension leaked to OpenAI: {msg}"
        )


@pytest.mark.unit
async def test_chat_completion_inline_skill_body_does_not_leak_to_openai() -> None:
    """Wave D.2 Task 3.0 security — ``lq_ai_inline_skills`` (and the
    verbatim user-drafted body inside it) must NEVER reach OpenAI.

    Regression for the C1 finding in the Task 3.0 code+security review:
    ``lq_ai_inline_skills`` was missing from the adapter's then exact-name
    extension-key blocklist (``_LQ_AI_EXTENSION_KEYS``, replaced by the
    ``strip_internal_fields`` prefix strip in GW-STRIP), so a chat routed
    through an openai-protocol provider transmitted the inline body to
    ``api.openai.com``. OpenAI 400s on unknown fields but the body has
    already left our gateway by then and lands in OpenAI's request logs /
    error telemetry.
    """

    from app.providers.openai_schema import InlineSkillRef

    payload = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
    }
    sentinel = "THIS-MUST-NOT-LEAK-TO-OPENAI-INLINE-BODY-SENTINEL"
    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatCompletionMessage(role="user", content="hi")],
        lq_ai_inline_skills=[
            InlineSkillRef(name="__inline__deadbeef", body=sentinel, source="wizard-tryout")
        ],
    )
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            await adapter.chat_completion(request, model="gpt-4o", stream=False)
        finally:
            await client.aclose()

    sent_raw = route.calls.last.request.content
    sent = json.loads(sent_raw)
    assert "lq_ai_inline_skills" not in sent, (
        "lq_ai_inline_skills leaked to OpenAI provider request body"
    )
    # Defense-in-depth: the inline-body sentinel must not appear ANYWHERE
    # in the serialized outbound payload, regardless of which key it
    # nested under.
    assert sentinel not in sent_raw.decode("utf-8"), (
        "verbatim inline_body content leaked to OpenAI provider request body"
    )


@pytest.mark.unit
async def test_chat_completion_forces_model_and_stream() -> None:
    """B6: model + stream on the body are overwritten by adapter args."""

    payload = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
    }
    # Caller set model="alias-name" + stream=True; adapter args override.
    request = ChatCompletionRequest(
        model="some-alias",
        messages=[ChatCompletionMessage(role="user", content="hi")],
        stream=True,
    )
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            await adapter.chat_completion(request, model="gpt-4o-mini", stream=False)
        finally:
            await client.aclose()
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "gpt-4o-mini"
    assert sent["stream"] is False


@pytest.mark.unit
async def test_chat_completion_streaming_translates_sse() -> None:
    """B6: OpenAI SSE chunks pass through to ChatCompletionChunk objects."""

    sse_body = (
        'data: {"id":"chatcmpl-s1","object":"chat.completion.chunk","created":1,'
        '"model":"gpt-4o","choices":[{"index":0,"delta":{"role":"assistant"},'
        '"finish_reason":null}]}\n\n'
        'data: {"id":"chatcmpl-s1","object":"chat.completion.chunk","created":1,'
        '"model":"gpt-4o","choices":[{"index":0,"delta":{"content":"Hel"},'
        '"finish_reason":null}]}\n\n'
        'data: {"id":"chatcmpl-s1","object":"chat.completion.chunk","created":1,'
        '"model":"gpt-4o","choices":[{"index":0,"delta":{"content":"lo"},'
        '"finish_reason":null}]}\n\n'
        'data: {"id":"chatcmpl-s1","object":"chat.completion.chunk","created":1,'
        '"model":"gpt-4o","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":7,"completion_tokens":2,"total_tokens":9}}\n\n'
        "data: [DONE]\n\n"
    )
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, text=sse_body, headers={"content-type": "text/event-stream"}
            )
        )
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            result = await adapter.chat_completion(
                _basic_chat_request(stream=True), model="gpt-4o", stream=True
            )
            assert not isinstance(result, ChatCompletionResponse)
            chunks: list[ChatCompletionChunk] = [c async for c in result]
        finally:
            await client.aclose()
    # 1 role chunk + 2 content chunks + 1 final chunk with finish_reason + usage.
    assert len(chunks) == 4
    assert chunks[0].choices[0].delta.role == "assistant"
    assert chunks[1].choices[0].delta.content == "Hel"
    assert chunks[2].choices[0].delta.content == "lo"
    final = chunks[-1]
    assert final.choices[0].finish_reason == "stop"
    assert final.usage is not None
    assert final.usage.total_tokens == 9
    # Streaming opts include_usage so the final usage block arrives.
    sent = json.loads(route.calls.last.request.content)
    assert sent["stream"] is True
    assert sent.get("stream_options", {}).get("include_usage") is True


@pytest.mark.unit
async def test_chat_completion_401_translates_to_auth_error() -> None:
    """B6: a 401 from chat completions raises ProviderAuthError; key not echoed."""

    error_body = {
        "error": {
            "message": "Incorrect API key provided",
            "type": "invalid_request_error",
            "code": "invalid_api_key",
        }
    }
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/chat/completions").mock(return_value=httpx.Response(401, json=error_body))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        secret = "sk-test-do-not-leak"
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key=secret,
                client=client,
            )
            with pytest.raises(ProviderAuthError) as excinfo:
                await adapter.chat_completion(_basic_chat_request(), model="gpt-4o", stream=False)
        finally:
            await client.aclose()
    serialized = json.dumps(excinfo.value.to_envelope())
    assert secret not in serialized
    assert excinfo.value.details.get("upstream_status") == 401


@pytest.mark.unit
async def test_chat_completion_500_translates_to_http_error() -> None:
    """B6: a 500 from chat completions raises ProviderHTTPError."""

    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/chat/completions").mock(
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
            with pytest.raises(ProviderHTTPError) as excinfo:
                await adapter.chat_completion(_basic_chat_request(), model="gpt-4o", stream=False)
        finally:
            await client.aclose()
    assert excinfo.value.upstream_status == 500


@pytest.mark.unit
async def test_chat_completion_network_error_translates() -> None:
    """B6: transport failures raise ProviderNetworkError."""

    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/chat/completions").mock(side_effect=httpx.ConnectError("boom"))
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            with pytest.raises(ProviderNetworkError):
                await adapter.chat_completion(_basic_chat_request(), model="gpt-4o", stream=False)
        finally:
            await client.aclose()


@pytest.mark.unit
async def test_chat_completion_streaming_upstream_error_raises() -> None:
    """B6: a non-200 on the streaming POST surfaces a structured error,
    not a hung generator."""

    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/chat/completions").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"message": "rate limited", "type": "rate_limit_error"}},
            )
        )
        client = httpx.AsyncClient(base_url="https://api.openai.com/v1")
        try:
            adapter = OpenAIAdapter(
                name="openai-prod",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                client=client,
            )
            result = await adapter.chat_completion(
                _basic_chat_request(stream=True), model="gpt-4o", stream=True
            )
            with pytest.raises(ProviderHTTPError) as excinfo:
                async for _ in result:  # type: ignore[union-attr]
                    pass
        finally:
            await client.aclose()
    assert excinfo.value.upstream_status == 429


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


# --- F0-S9 gateway conformance (agent-harness prerequisites) -------------
#
# Three properties every score in the model-qualification matrix depends
# on (docs/fork/research/deepagents-ecosystem.md §1.3):
#
#   (a) opening tool-call deltas carry a non-empty, unique, stable id —
#       synthesized by the gateway when the provider omits one
#       (deepagents#3587 puts the fix on gateways);
#   (b) reasoning content is never stripped from streamed deltas
#       (MiniMax-M3 emits BOTH inline ``<think>`` in content AND a
#       ``reasoning`` delta field — verified live 2026-06-12);
#   (c) reasoning content survives the HISTORY direction — assistant
#       messages with ``<think>`` text + tool_calls echoed back through
#       ``_to_openai_request`` reach the provider verbatim (the risk is
#       the resent history, not the response; deepagents#1630).


def _stream_adapter_and_body(sse_body: str) -> tuple[OpenAIAdapter, respx.MockRouter]:
    router = respx.mock(base_url="https://api.openai.com/v1")
    router.post("/chat/completions").mock(
        return_value=httpx.Response(
            200, text=sse_body, headers={"content-type": "text/event-stream"}
        )
    )
    return (
        OpenAIAdapter(
            name="openai-prod",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        ),
        router,
    )


@pytest.mark.unit
async def test_streaming_tool_call_opening_delta_without_id_synthesized() -> None:
    """F0-S9 (a): a missing/empty id on an OPENING tool-call delta is
    synthesized (non-empty, unique per call); continuation deltas — which
    legitimately carry no id on the OpenAI wire — are left untouched."""

    sse_body = (
        # Opening delta, id MISSING entirely.
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m",'
        '"choices":[{"index":0,"delta":{"role":"assistant","tool_calls":[{"type":"function",'
        '"function":{"name":"get_weather","arguments":""},"index":0}]}}]}\n\n'
        # Continuation delta: arguments only — must NOT get an id.
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m",'
        '"choices":[{"index":0,"delta":{"tool_calls":[{"function":{"arguments":"{\\"city\\":\\"Berlin\\"}"},'
        '"index":0}]}}]}\n\n'
        # Second tool call, id EMPTY STRING.
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m",'
        '"choices":[{"index":0,"delta":{"tool_calls":[{"id":"","type":"function",'
        '"function":{"name":"read_document","arguments":""},"index":1}]}}]}\n\n'
        "data: [DONE]\n\n"
    )
    adapter, router = _stream_adapter_and_body(sse_body)
    with router:
        result = await adapter.chat_completion(
            _basic_chat_request(stream=True), model="m", stream=True
        )
        assert not isinstance(result, ChatCompletionResponse)
        chunks = [c async for c in result]
    await adapter.aclose()

    first = (chunks[0].choices[0].delta.tool_calls or [])[0]
    cont = (chunks[1].choices[0].delta.tool_calls or [])[0]
    second = (chunks[2].choices[0].delta.tool_calls or [])[0]
    assert first.get("id", "").startswith("call_lqgw_")
    assert "id" not in cont  # continuation untouched
    assert second.get("id", "").startswith("call_lqgw_")
    assert first["id"] != second["id"]  # unique per call


@pytest.mark.unit
async def test_streaming_tool_call_provider_ids_pass_through() -> None:
    """F0-S9 (a): provider-supplied ids are never rewritten. Shape is the
    live MiniMax-M3 wire format captured through this gateway 2026-06-12."""

    sse_body = (
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"MiniMax-M3",'
        '"choices":[{"index":0,"delta":{"role":"assistant","tool_calls":[{"id":"call_function_xplk3zli8lqh_1",'
        '"type":"function","function":{"name":"get_weather","arguments":""},"index":0}]}}]}\n\n'
        "data: [DONE]\n\n"
    )
    adapter, router = _stream_adapter_and_body(sse_body)
    with router:
        result = await adapter.chat_completion(
            _basic_chat_request(stream=True), model="MiniMax-M3", stream=True
        )
        assert not isinstance(result, ChatCompletionResponse)
        chunks = [c async for c in result]
    await adapter.aclose()

    entry = (chunks[0].choices[0].delta.tool_calls or [])[0]
    assert entry["id"] == "call_function_xplk3zli8lqh_1"


@pytest.mark.unit
async def test_streaming_reasoning_content_round_trips() -> None:
    """F0-S9 (b): inline ``<think>`` content AND the ``reasoning`` extra
    delta field survive chunk validation and re-serialization — the route
    handler re-emits via ``model_dump(exclude_none=True)``, so extras
    surviving the dump is exactly what the wire needs."""

    sse_body = (
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"MiniMax-M3",'
        '"choices":[{"index":0,"delta":{"role":"assistant",'
        '"content":"<think>\\nplanning\\n</think>\\nHello","reasoning":"planning"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    adapter, router = _stream_adapter_and_body(sse_body)
    with router:
        result = await adapter.chat_completion(
            _basic_chat_request(stream=True), model="MiniMax-M3", stream=True
        )
        assert not isinstance(result, ChatCompletionResponse)
        chunks = [c async for c in result]
    await adapter.aclose()

    delta = chunks[0].choices[0].delta
    assert delta.content == "<think>\nplanning\n</think>\nHello"
    dumped = chunks[0].model_dump(mode="json", exclude_none=True)
    assert dumped["choices"][0]["delta"]["reasoning"] == "planning"
    assert "<think>" in dumped["choices"][0]["delta"]["content"]


@pytest.mark.unit
def test_request_preserves_think_history_and_strips_only_lq_ai_keys() -> None:
    """F0-S9 (c): the HISTORY direction. An assistant message carrying
    ``<think>`` text, tool_calls, and a ``reasoning_content`` extra field
    must reach the provider body verbatim; only LQ.AI extension keys are
    stripped. This is the resend path a multi-turn agent loop exercises
    on every tool turn (verified live against MiniMax-M3 2026-06-12)."""

    from app.providers.openai import _to_openai_request

    request = ChatCompletionRequest.model_validate(
        {
            "model": "smart",
            "lq_ai_purpose": "agent_loop",
            "messages": [
                {"role": "user", "content": "weather in Berlin?"},
                {
                    "role": "assistant",
                    "content": "<think>\nuse the tool\n</think>\nChecking.",
                    "reasoning_content": "use the tool",
                    "tool_calls": [
                        {
                            "id": "call_function_xplk3zli8lqh_1",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": '{"city": "Berlin"}'},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_function_xplk3zli8lqh_1",
                    "content": '{"temp_c": 18}',
                },
            ],
        }
    )
    body = _to_openai_request(request, model="MiniMax-M3", stream=False)

    assistant = body["messages"][1]
    assert assistant["content"] == "<think>\nuse the tool\n</think>\nChecking."
    assert assistant["reasoning_content"] == "use the tool"
    assert assistant["tool_calls"][0]["id"] == "call_function_xplk3zli8lqh_1"
    assert body["messages"][2]["tool_call_id"] == "call_function_xplk3zli8lqh_1"
    assert "lq_ai_purpose" not in body


@pytest.mark.unit
def test_strip_internal_fields_drops_prefix_and_nonprefixed_keeps_native() -> None:
    """GW-STRIP unit: the shared strip removes the whole internal namespace
    (every ``lq_ai_*`` key + the closed non-prefixed set) and preserves
    everything else, including native OpenAI extras. Not an allowlist."""

    from app.providers.openai import strip_internal_fields

    stripped = strip_internal_fields(
        {
            # native fields — MUST survive
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "f"}}],
            "seed": 7,
            "response_format": {"type": "json_object"},
            "reasoning_content": "keep me",
            "stream_options": {"include_usage": True},
            # internal, non-prefixed — MUST be dropped
            "minimum_inference_tier": 3,
            "skill_name": "nda-review",
            "chat_id": "c-1",
            "anonymize": True,
            # internal, lq_ai_* prefix — MUST be dropped
            "lq_ai_file_ids": ["doc-1"],
            "lq_ai_purpose": "chat",
            "lq_ai_privileged": False,
            "lq_ai_future_marker": "not-yet-invented",
        }
    )

    assert stripped == {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "f"}}],
        "seed": 7,
        "response_format": {"type": "json_object"},
        "reasoning_content": "keep me",
        "stream_options": {"include_usage": True},
    }


@pytest.mark.unit
def test_to_openai_request_strips_lq_ai_file_ids_and_all_internal_fields() -> None:
    """GW-STRIP regression (OpenAI family): the exact leak — ``lq_ai_file_ids``
    riding ``extra="allow"`` into ``model_extra`` — plus every other internal
    control field is stripped from the outbound body, while native extras and
    a would-be future ``lq_ai_*`` field are handled correctly."""

    from app.providers.openai import _to_openai_request

    request = ChatCompletionRequest.model_validate(
        {
            "model": "smart",
            "messages": [{"role": "user", "content": "hi"}],
            # native OpenAI extras — MUST be preserved
            "seed": 11,
            "response_format": {"type": "json_object"},
            # non-prefixed internal — MUST be stripped
            "minimum_inference_tier": 3,
            "skill_name": "nda-review",
            "chat_id": "c-1",
            "anonymize": True,
            # lq_ai_* internal — MUST be stripped (file_ids is the reported bug;
            # empty-list case still leaks under exclude_none, so also assert []),
            "lq_ai_file_ids": ["doc-1", "doc-2"],
            "lq_ai_purpose": "chat",
            "lq_ai_privileged": False,
            "lq_ai_future_marker": "not-yet-invented",
        }
    )
    body = _to_openai_request(request, model="gpt-4o", stream=False)

    assert not any(k.startswith("lq_ai_") for k in body), (
        f"lq_ai_* leaked: {sorted(k for k in body if k.startswith('lq_ai_'))}"
    )
    for forbidden in ("minimum_inference_tier", "skill_name", "chat_id", "anonymize"):
        assert forbidden not in body, f"internal field {forbidden!r} leaked"
    # Native extras survive; model/stream are stamped.
    assert body["seed"] == 11
    assert body["response_format"] == {"type": "json_object"}
    assert body["model"] == "gpt-4o"
    assert body["stream"] is False


@pytest.mark.unit
def test_to_openai_request_strips_empty_lq_ai_file_ids() -> None:
    """GW-STRIP edge: the leak shipped on EVERY chat request because an
    empty ``lq_ai_file_ids=[]`` survives ``exclude_none=True`` (only ``None``
    is dropped). The prefix strip must remove it even when empty."""

    from app.providers.openai import _to_openai_request

    request = ChatCompletionRequest.model_validate(
        {
            "model": "smart",
            "messages": [{"role": "user", "content": "hi"}],
            "lq_ai_file_ids": [],
        }
    )
    body = _to_openai_request(request, model="gpt-4o", stream=False)
    assert "lq_ai_file_ids" not in body


@pytest.mark.unit
async def test_streaming_tool_call_repeated_type_continuations_not_resynthesized() -> None:
    """F0-S9 review fix: some nonconforming providers repeat ``type`` (or
    even ``function.name``) on CONTINUATION deltas. Opening detection is
    stateful by (choice, tool_call) index — only an index's first delta
    may synthesize, so continuations never get a fresh (call-splitting)
    id, no matter what shape they arrive in."""

    sse_body = (
        # Opening delta, id missing — synthesize here.
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m",'
        '"choices":[{"index":0,"delta":{"role":"assistant","tool_calls":[{"type":"function",'
        '"function":{"name":"get_weather","arguments":""},"index":0}]}}]}\n\n'
        # Continuation that REPEATS type — must NOT synthesize.
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m",'
        '"choices":[{"index":0,"delta":{"tool_calls":[{"type":"function",'
        '"function":{"arguments":"{\\"city\\""},"index":0}]}}]}\n\n'
        # Continuation that repeats type AND name — must NOT synthesize.
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m",'
        '"choices":[{"index":0,"delta":{"tool_calls":[{"type":"function",'
        '"function":{"name":"get_weather","arguments":": \\"Berlin\\"}"},"index":0}]}}]}\n\n'
        "data: [DONE]\n\n"
    )
    adapter, router = _stream_adapter_and_body(sse_body)
    with router:
        result = await adapter.chat_completion(
            _basic_chat_request(stream=True), model="m", stream=True
        )
        assert not isinstance(result, ChatCompletionResponse)
        chunks = [c async for c in result]
    await adapter.aclose()

    opening = (chunks[0].choices[0].delta.tool_calls or [])[0]
    cont1 = (chunks[1].choices[0].delta.tool_calls or [])[0]
    cont2 = (chunks[2].choices[0].delta.tool_calls or [])[0]
    assert opening.get("id", "").startswith("call_lqgw_")
    assert "id" not in cont1
    assert "id" not in cont2
