"""Unit tests for :class:`app.providers.anthropic.AnthropicAdapter`.

Covers the translation logic and HTTP handling without going through
the FastAPI surface. Outbound HTTP is mocked with ``respx``.

Test surface:

* System-message extraction from OpenAI ``messages`` into Anthropic's
  top-level ``system`` field.
* ``stop_reason`` mapping (``end_turn`` -> ``stop``, ``max_tokens`` ->
  ``length``, ``tool_use`` -> ``tool_calls``, ``stop_sequence`` ->
  ``stop``).
* Token-usage translation (``input_tokens`` / ``output_tokens`` ->
  ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``).
* Streaming: SSE event sequence is translated into OpenAI chunks with
  the expected role-then-deltas-then-finish ordering.
* Network failure -> :class:`ProviderNetworkError`.
* Upstream 401 -> :class:`ProviderAuthError` with no key in the
  surfaced message or details.
* ``embeddings`` -> :class:`ProviderUnsupportedError`.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.providers import (
    AnthropicAdapter,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingsRequest,
    ProviderAuthError,
    ProviderHTTPError,
    ProviderNetworkError,
    ProviderUnsupportedError,
)
from app.providers.anthropic import (
    DEFAULT_MAX_TOKENS,
    _to_anthropic_request,
)

ANTHROPIC_BASE = "https://api.anthropic.com"


def _make_adapter(api_key: str = "sk-ant-test") -> AnthropicAdapter:
    """Build an adapter pointed at the standard production base URL."""

    return AnthropicAdapter(
        name="anthropic-test",
        base_url=ANTHROPIC_BASE,
        api_key=api_key,
    )


def _basic_request(**overrides: object) -> ChatCompletionRequest:
    """Build a minimal valid :class:`ChatCompletionRequest`."""

    payload: dict[str, object] = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ],
    }
    payload.update(overrides)
    return ChatCompletionRequest.model_validate(payload)


# --- Pure-translation tests (no HTTP) -----------------------------------------


@pytest.mark.unit
def test_to_anthropic_request_extracts_system_message() -> None:
    """System messages move to the top-level ``system`` field; user /
    assistant messages stay in ``messages`` in order."""

    req = ChatCompletionRequest.model_validate(
        {
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "system", "content": "You are concise."},
                {"role": "system", "content": "Always cite."},
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
                {"role": "user", "content": "Continue"},
            ],
        }
    )

    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)

    assert body["system"] == "You are concise.\n\nAlways cite."
    assert body["messages"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Continue"},
    ]
    # max_tokens default is applied
    assert body["max_tokens"] == DEFAULT_MAX_TOKENS
    # Stream flag is forwarded
    assert body["stream"] is False


@pytest.mark.unit
def test_to_anthropic_request_passes_through_optional_fields() -> None:
    req = ChatCompletionRequest.model_validate(
        {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 256,
            "temperature": 0.3,
            "top_p": 0.9,
            "stop": ["END"],
        }
    )

    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=True)

    assert body["max_tokens"] == 256
    assert body["temperature"] == 0.3
    assert body["top_p"] == 0.9
    assert body["stop_sequences"] == ["END"]
    assert body["stream"] is True


@pytest.mark.unit
def test_to_anthropic_request_string_stop_becomes_list() -> None:
    """OpenAI accepts ``stop: "END"``; Anthropic only takes a list."""

    req = ChatCompletionRequest.model_validate(
        {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hi"}],
            "stop": "END",
        }
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["stop_sequences"] == ["END"]


@pytest.mark.unit
def test_to_anthropic_request_no_system_when_no_system_messages() -> None:
    """If the OpenAI request has no system messages, ``system`` is omitted
    rather than sent as an empty string."""

    req = _basic_request(messages=[{"role": "user", "content": "hi"}])
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert "system" not in body


@pytest.mark.unit
def test_to_anthropic_request_translates_tool_messages() -> None:
    """OpenAI ``tool`` role messages become Anthropic ``tool_result`` blocks
    nested in a user message."""

    req = ChatCompletionRequest.model_validate(
        {
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "user", "content": "use a tool"},
                {"role": "assistant", "content": "calling..."},
                {
                    "role": "tool",
                    "content": "tool result text",
                    "tool_call_id": "call_abc123",
                },
            ],
        }
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["messages"][-1] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "call_abc123",
                "content": "tool result text",
            }
        ],
    }


# --- AZ-2b: tool-calling request translation -----------------------------------


_OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_clause",
            "description": "Return the clause covering a topic.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "no_description_tool",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {"name": "no_parameters_tool", "description": "No schema."},
    },
]


@pytest.mark.unit
def test_to_anthropic_request_translates_tools() -> None:
    """OpenAI function tools map to Anthropic ``tools`` entries: name /
    description (omitted when absent) / ``parameters`` -> ``input_schema``
    (missing -> the minimal object schema). Non-function entries skip."""

    req = _basic_request(
        tools=[*_OPENAI_TOOLS, {"type": "web_search"}],
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)

    assert body["tools"] == [
        {
            "name": "read_clause",
            "description": "Return the clause covering a topic.",
            "input_schema": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
        },
        {
            "name": "no_description_tool",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "no_parameters_tool",
            "description": "No schema.",
            "input_schema": {"type": "object"},
        },
    ]
    # tool_choice was not set -> omitted (Anthropic defaults to auto).
    assert "tool_choice" not in body


@pytest.mark.unit
@pytest.mark.parametrize(
    "openai_choice,expected",
    [
        ("auto", {"type": "auto"}),
        ("required", {"type": "any"}),
        ("none", {"type": "none"}),
        (
            {"type": "function", "function": {"name": "read_clause"}},
            {"type": "tool", "name": "read_clause"},
        ),
    ],
)
def test_to_anthropic_request_translates_tool_choice(
    openai_choice: object, expected: dict[str, object]
) -> None:
    req = _basic_request(tools=_OPENAI_TOOLS, tool_choice=openai_choice)
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["tool_choice"] == expected


@pytest.mark.unit
def test_to_anthropic_request_omits_unrecognized_tool_choice() -> None:
    """An unknown ``tool_choice`` value is omitted rather than guessed."""

    req = _basic_request(tools=_OPENAI_TOOLS, tool_choice="mystery-mode")
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert "tool_choice" not in body


@pytest.mark.unit
def test_to_anthropic_request_parallel_tool_calls_false() -> None:
    """``parallel_tool_calls: false`` (OpenAI extension) becomes
    ``disable_parallel_tool_use: true`` on the tool_choice object — and
    materializes an explicit ``auto`` when tool_choice was omitted."""

    # With explicit tool_choice "required" -> flag rides on {"type": "any"}.
    req = _basic_request(tools=_OPENAI_TOOLS, tool_choice="required", parallel_tool_calls=False)
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}

    # With tool_choice omitted -> explicit auto carries the flag.
    req = _basic_request(tools=_OPENAI_TOOLS, parallel_tool_calls=False)
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}

    # Never on "none" (disabling parallel calls on no-calls is nonsense).
    req = _basic_request(tools=_OPENAI_TOOLS, tool_choice="none", parallel_tool_calls=False)
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["tool_choice"] == {"type": "none"}

    # parallel_tool_calls True (the default) adds nothing.
    req = _basic_request(tools=_OPENAI_TOOLS, tool_choice="auto", parallel_tool_calls=True)
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["tool_choice"] == {"type": "auto"}


@pytest.mark.unit
def test_to_anthropic_request_assistant_tool_calls_become_tool_use() -> None:
    """Assistant ``tool_calls`` translate to ``tool_use`` blocks: the JSON
    string ``arguments`` parses to ``input``; text (when present) leads."""

    req = _basic_request(
        messages=[
            {"role": "user", "content": "read the cap"},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "read_clause",
                            "arguments": '{"topic": "liability"}',
                        },
                    }
                ],
            },
        ],
        tools=_OPENAI_TOOLS,
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["messages"][-1] == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Let me check."},
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "read_clause",
                "input": {"topic": "liability"},
            },
        ],
    }


@pytest.mark.unit
def test_to_anthropic_request_assistant_tool_calls_edge_cases() -> None:
    """Empty / malformed arguments -> ``{}``; missing id -> synthesized
    ``call_lqgw_`` id; entries without a function name are skipped."""

    req = _basic_request(
        messages=[
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_empty",
                        "type": "function",
                        "function": {"name": "no_parameters_tool", "arguments": ""},
                    },
                    {
                        "type": "function",
                        "function": {"name": "read_clause", "arguments": "{not json"},
                    },
                    {
                        "id": "call_skipme",
                        "type": "function",
                        "function": {"arguments": "{}"},
                    },
                ],
            },
        ],
        tools=_OPENAI_TOOLS,
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    blocks = body["messages"][-1]["content"]
    # No text block (content was None); the nameless entry is skipped.
    assert [b["type"] for b in blocks] == ["tool_use", "tool_use"]
    assert blocks[0]["id"] == "call_empty"
    assert blocks[0]["input"] == {}
    assert blocks[1]["name"] == "read_clause"
    assert blocks[1]["input"] == {}
    assert blocks[1]["id"].startswith("call_lqgw_")


@pytest.mark.unit
def test_to_anthropic_request_deeply_nested_arguments_degrade() -> None:
    """Absurdly nested ``arguments`` (RecursionError inside ``json.loads``,
    NOT a ``JSONDecodeError``) degrade to ``input == {}`` instead of
    escaping as an unhandled 500 — arguments is untrusted model output."""

    req = _basic_request(
        messages=[
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_deep",
                        "type": "function",
                        "function": {
                            "name": "read_clause",
                            "arguments": "[" * 3000 + "]" * 3000,
                        },
                    },
                ],
            },
        ],
        tools=_OPENAI_TOOLS,
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    blocks = body["messages"][-1]["content"]
    assert blocks == [
        {"type": "tool_use", "id": "call_deep", "name": "read_clause", "input": {}},
    ]


@pytest.mark.unit
def test_to_anthropic_request_extracts_block_form_content() -> None:
    """Block-form content (langchain 1.x) extracts its text parts for
    system and user messages — no longer collapses to ``""`` (AZ-2b)."""

    req = ChatCompletionRequest.model_validate(
        {
            "model": "claude-sonnet-4-6",
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {"type": "text", "text": "Be "},
                        {"type": "text", "text": "brief."},
                        {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
                    ],
                },
                {"role": "user", "content": [{"type": "text", "text": "cap?"}]},
            ],
        }
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["system"] == "Be brief."
    assert body["messages"] == [{"role": "user", "content": "cap?"}]


@pytest.mark.unit
def test_to_anthropic_request_merges_consecutive_tool_messages() -> None:
    """Consecutive OpenAI ``tool`` messages merge into ONE Anthropic user
    message with a ``tool_result`` block per result, in order — Anthropic
    requires all results for a parallel tool_use turn in the single next
    user message."""

    req = _basic_request(
        messages=[
            {"role": "user", "content": "compare two clauses"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": "read_clause", "arguments": '{"topic": "cap"}'},
                    },
                    {
                        "id": "call_b",
                        "type": "function",
                        "function": {"name": "read_clause", "arguments": '{"topic": "term"}'},
                    },
                ],
            },
            {"role": "tool", "content": "cap clause text", "tool_call_id": "call_a"},
            {"role": "tool", "content": "term clause text", "tool_call_id": "call_b"},
        ],
        tools=_OPENAI_TOOLS,
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert body["messages"][-1] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "call_a", "content": "cap clause text"},
            {"type": "tool_result", "tool_use_id": "call_b", "content": "term clause text"},
        ],
    }
    # Not merged into anything earlier: user, assistant, merged-results.
    assert len(body["messages"]) == 3


@pytest.mark.unit
def test_to_anthropic_request_tool_messages_split_by_user_message() -> None:
    """A user message between tool results ends the merge window — only
    CONSECUTIVE tool messages share one user message."""

    req = _basic_request(
        messages=[
            {"role": "tool", "content": "first", "tool_call_id": "call_1"},
            {"role": "user", "content": "interject"},
            {"role": "tool", "content": "second", "tool_call_id": "call_2"},
        ],
    )
    body = _to_anthropic_request(req, model="claude-sonnet-4-6", stream=False)
    assert len(body["messages"]) == 3
    assert body["messages"][0]["content"][0]["tool_use_id"] == "call_1"
    assert body["messages"][1] == {"role": "user", "content": "interject"}
    assert body["messages"][2]["content"][0]["tool_use_id"] == "call_2"


@pytest.mark.unit
def test_to_anthropic_request_without_tools_has_no_tool_keys() -> None:
    """Regression guard: a no-tools request body carries neither ``tools``
    nor ``tool_choice`` — byte-identical to the pre-AZ-2b body."""

    body = _to_anthropic_request(_basic_request(), model="claude-sonnet-4-6", stream=False)
    assert "tools" not in body
    assert "tool_choice" not in body


# --- Non-streaming HTTP path --------------------------------------------------


@pytest.mark.unit
@respx.mock
async def test_chat_completion_unary_translates_response() -> None:
    """Anthropic response shape is converted to OpenAI's, including usage
    and stop-reason."""

    route = respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_01ABC",
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "text", "text": "Hello there!"},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 5},
            },
        )
    )

    adapter = _make_adapter()
    try:
        result = await adapter.chat_completion(
            _basic_request(),
            model="claude-sonnet-4-6",
            stream=False,
        )
    finally:
        await adapter.aclose()

    assert isinstance(result, ChatCompletionResponse)
    assert result.id == "msg_01ABC"
    assert result.model == "claude-sonnet-4-6"
    assert len(result.choices) == 1
    choice = result.choices[0]
    assert choice.message.role == "assistant"
    assert choice.message.content == "Hello there!"
    assert choice.finish_reason == "stop"
    assert result.usage.prompt_tokens == 12
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 17

    # Headers we sent upstream are correct.
    assert route.called
    sent = route.calls[-1].request
    assert sent.headers["x-api-key"] == "sk-ant-test"
    assert sent.headers["anthropic-version"]
    body = json.loads(sent.content)
    assert body["model"] == "claude-sonnet-4-6"
    assert body["stream"] is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "anthropic_reason,expected_finish",
    [
        ("end_turn", "stop"),
        ("max_tokens", "length"),
        ("stop_sequence", "stop"),
        ("tool_use", "tool_calls"),
    ],
)
@respx.mock
async def test_stop_reason_mapping(anthropic_reason: str, expected_finish: str) -> None:
    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg",
                "model": "claude-sonnet-4-6",
                "content": [{"type": "text", "text": "x"}],
                "stop_reason": anthropic_reason,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
    )
    adapter = _make_adapter()
    try:
        result = await adapter.chat_completion(
            _basic_request(), model="claude-sonnet-4-6", stream=False
        )
    finally:
        await adapter.aclose()
    assert isinstance(result, ChatCompletionResponse)
    assert result.choices[0].finish_reason == expected_finish


@pytest.mark.unit
@respx.mock
async def test_chat_completion_concatenates_multiple_text_blocks() -> None:
    """Anthropic occasionally returns multiple text blocks in one
    response; the adapter joins them into a single OpenAI message."""

    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg",
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "text", "text": "Part 1. "},
                    {"type": "text", "text": "Part 2."},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 3, "output_tokens": 6},
            },
        )
    )
    adapter = _make_adapter()
    try:
        result = await adapter.chat_completion(
            _basic_request(), model="claude-sonnet-4-6", stream=False
        )
    finally:
        await adapter.aclose()
    assert isinstance(result, ChatCompletionResponse)
    assert result.choices[0].message.content == "Part 1. Part 2."


# --- Streaming path -----------------------------------------------------------


SSE_FIXTURE_BODY = (
    "event: message_start\n"
    'data: {"type":"message_start","message":{"id":"msg_stream","model":"claude-sonnet-4-6",'
    '"usage":{"input_tokens":7,"output_tokens":0}}}\n\n'
    "event: content_block_start\n"
    'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n\n'
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}\n\n'
    "event: content_block_stop\n"
    'data: {"type":"content_block_stop","index":0}\n\n'
    "event: message_delta\n"
    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}\n\n'
    "event: message_stop\n"
    'data: {"type":"message_stop"}\n\n'
)


@pytest.mark.unit
@respx.mock
async def test_chat_completion_streaming_translates_sse() -> None:
    """SSE event sequence becomes OpenAI chunks: role chunk, delta
    chunks, final chunk with finish_reason and usage."""

    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            text=SSE_FIXTURE_BODY,
            headers={"content-type": "text/event-stream"},
        )
    )

    adapter = _make_adapter()
    try:
        result = await adapter.chat_completion(
            _basic_request(stream=True),
            model="claude-sonnet-4-6",
            stream=True,
        )
        assert not isinstance(result, ChatCompletionResponse)
        chunks: list[ChatCompletionChunk] = []
        async for chunk in result:
            chunks.append(chunk)
    finally:
        await adapter.aclose()

    # Expect: 1 role-init chunk + 2 content delta chunks + 1 final chunk.
    assert len(chunks) == 4
    assert chunks[0].choices[0].delta.role == "assistant"
    assert chunks[0].choices[0].delta.content is None
    assert chunks[1].choices[0].delta.content == "Hello"
    assert chunks[2].choices[0].delta.content == " world"
    final = chunks[-1]
    assert final.choices[0].finish_reason == "stop"
    assert final.usage is not None
    assert final.usage.prompt_tokens == 7
    assert final.usage.completion_tokens == 2
    assert final.usage.total_tokens == 9
    # Anthropic's message_start id is preserved across the stream.
    for chunk in chunks:
        assert chunk.id == "msg_stream"
        assert chunk.model == "claude-sonnet-4-6"


# --- AZ-2b: tool-calling response translation ----------------------------------


@pytest.mark.unit
@respx.mock
async def test_chat_completion_unary_tool_use_only() -> None:
    """A tool_use-only response becomes OpenAI ``tool_calls`` with
    ``content: None`` and ``finish_reason: "tool_calls"``."""

    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_tool",
                "model": "claude-sonnet-4-6",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01A",
                        "name": "read_clause",
                        "input": {"topic": "liability"},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )
    )
    adapter = _make_adapter()
    try:
        result = await adapter.chat_completion(
            _basic_request(tools=_OPENAI_TOOLS), model="claude-sonnet-4-6", stream=False
        )
    finally:
        await adapter.aclose()

    assert isinstance(result, ChatCompletionResponse)
    message = result.choices[0].message
    assert message.content is None
    assert message.tool_calls == [
        {
            "id": "toolu_01A",
            "type": "function",
            "function": {"name": "read_clause", "arguments": '{"topic": "liability"}'},
        }
    ]
    assert result.choices[0].finish_reason == "tool_calls"


@pytest.mark.unit
@respx.mock
async def test_chat_completion_unary_mixed_text_and_tool_use() -> None:
    """Text + tool_use blocks yield both ``content`` and ``tool_calls``;
    ``input`` re-serializes as a JSON string."""

    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_mixed",
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "text", "text": "Checking the clause."},
                    {
                        "type": "tool_use",
                        "id": "toolu_01B",
                        "name": "read_clause",
                        "input": {"topic": "term"},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 5, "output_tokens": 9},
            },
        )
    )
    adapter = _make_adapter()
    try:
        result = await adapter.chat_completion(
            _basic_request(tools=_OPENAI_TOOLS), model="claude-sonnet-4-6", stream=False
        )
    finally:
        await adapter.aclose()

    assert isinstance(result, ChatCompletionResponse)
    message = result.choices[0].message
    assert message.content == "Checking the clause."
    assert message.tool_calls is not None
    assert len(message.tool_calls) == 1
    assert message.tool_calls[0]["function"]["arguments"] == json.dumps({"topic": "term"})
    assert result.choices[0].finish_reason == "tool_calls"


# --- AZ-2b: streaming tool calls ------------------------------------------------


SSE_TOOL_FIXTURE_BODY = (
    "event: message_start\n"
    'data: {"type":"message_start","message":{"id":"msg_tool_stream",'
    '"model":"claude-sonnet-4-6","usage":{"input_tokens":11,"output_tokens":0}}}\n\n'
    "event: content_block_start\n"
    'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta",'
    '"text":"Let me look."}}\n\n'
    "event: content_block_stop\n"
    'data: {"type":"content_block_stop","index":0}\n\n'
    "event: content_block_start\n"
    'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use",'
    '"id":"toolu_stream_1","name":"read_clause","input":{}}}\n\n'
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta",'
    '"partial_json":"{\\"topic\\": "}}\n\n'
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta",'
    '"partial_json":"\\"liability\\"}"}}\n\n'
    "event: content_block_stop\n"
    'data: {"type":"content_block_stop","index":1}\n\n'
    "event: message_delta\n"
    'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},'
    '"usage":{"output_tokens":14}}\n\n'
    "event: message_stop\n"
    'data: {"type":"message_stop"}\n\n'
)


@pytest.mark.unit
@respx.mock
async def test_streaming_tool_use_after_text_block() -> None:
    """A tool_use block AFTER a text block gets OpenAI tool-call index 0:
    the index is the ordinal over tool calls only, NOT Anthropic's
    content-block index (which counts the text block too)."""

    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            text=SSE_TOOL_FIXTURE_BODY,
            headers={"content-type": "text/event-stream"},
        )
    )

    adapter = _make_adapter()
    try:
        result = await adapter.chat_completion(
            _basic_request(tools=_OPENAI_TOOLS, stream=True),
            model="claude-sonnet-4-6",
            stream=True,
        )
        assert not isinstance(result, ChatCompletionResponse)
        chunks: list[ChatCompletionChunk] = []
        async for chunk in result:
            chunks.append(chunk)
    finally:
        await adapter.aclose()

    # role chunk + text delta + tool-open + 2 argument deltas + final.
    assert len(chunks) == 6
    assert chunks[0].choices[0].delta.role == "assistant"
    assert chunks[1].choices[0].delta.content == "Let me look."

    opening = chunks[2].choices[0].delta.tool_calls
    assert opening == [
        {
            "index": 0,  # ordinal over TOOL CALLS, not block index 1
            "id": "toolu_stream_1",  # real id from content_block_start
            "type": "function",
            "function": {"name": "read_clause", "arguments": ""},
        }
    ]

    continuations = [
        chunk.choices[0].delta.tool_calls
        for chunk in chunks[3:5]
        if chunk.choices[0].delta.tool_calls
    ]
    assert [c[0]["index"] for c in continuations] == [0, 0]
    joined = "".join(c[0]["function"]["arguments"] for c in continuations)
    assert json.loads(joined) == {"topic": "liability"}

    final = chunks[-1]
    assert final.choices[0].finish_reason == "tool_calls"
    assert final.usage is not None
    assert final.usage.prompt_tokens == 11
    assert final.usage.completion_tokens == 14


SSE_TWO_TOOLS_FIXTURE_BODY = (
    "event: message_start\n"
    'data: {"type":"message_start","message":{"id":"msg_two_tools",'
    '"model":"claude-sonnet-4-6","usage":{"input_tokens":4,"output_tokens":0}}}\n\n'
    "event: content_block_start\n"
    'data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use",'
    '"id":"toolu_a","name":"read_clause","input":{}}}\n\n'
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta",'
    '"partial_json":"{\\"topic\\": \\"cap\\"}"}}\n\n'
    "event: content_block_stop\n"
    'data: {"type":"content_block_stop","index":0}\n\n'
    "event: content_block_start\n"
    'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use",'
    '"id":"toolu_b","name":"read_clause","input":{}}}\n\n'
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta",'
    '"partial_json":"{\\"topic\\": \\"term\\"}"}}\n\n'
    "event: content_block_stop\n"
    'data: {"type":"content_block_stop","index":1}\n\n'
    "event: message_delta\n"
    'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},'
    '"usage":{"output_tokens":8}}\n\n'
    "event: message_stop\n"
    'data: {"type":"message_stop"}\n\n'
)


@pytest.mark.unit
@respx.mock
async def test_streaming_two_tool_use_blocks_get_sequential_ordinals() -> None:
    """Two parallel tool_use blocks open with OpenAI indexes 0 and 1, and
    each argument fragment routes to its own ordinal."""

    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            200,
            text=SSE_TWO_TOOLS_FIXTURE_BODY,
            headers={"content-type": "text/event-stream"},
        )
    )

    adapter = _make_adapter()
    try:
        result = await adapter.chat_completion(
            _basic_request(tools=_OPENAI_TOOLS, stream=True),
            model="claude-sonnet-4-6",
            stream=True,
        )
        assert not isinstance(result, ChatCompletionResponse)
        chunks = [chunk async for chunk in result]
    finally:
        await adapter.aclose()

    tool_deltas = [
        chunk.choices[0].delta.tool_calls[0]
        for chunk in chunks
        if chunk.choices and chunk.choices[0].delta.tool_calls
    ]
    openings = [d for d in tool_deltas if d.get("id")]
    assert [(d["index"], d["id"]) for d in openings] == [(0, "toolu_a"), (1, "toolu_b")]
    args_by_index: dict[int, str] = {}
    for delta in tool_deltas:
        args_by_index[delta["index"]] = (
            args_by_index.get(delta["index"], "") + delta["function"]["arguments"]
        )
    assert json.loads(args_by_index[0]) == {"topic": "cap"}
    assert json.loads(args_by_index[1]) == {"topic": "term"}
    assert chunks[-1].choices[0].finish_reason == "tool_calls"


# --- Error mapping ------------------------------------------------------------


@pytest.mark.unit
@respx.mock
async def test_upstream_401_raises_provider_auth_error_without_leaking_key() -> None:
    """A 401 from Anthropic raises :class:`ProviderAuthError`; neither the
    error message nor its details echo the API key value."""

    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            401,
            json={
                "type": "error",
                "error": {"type": "authentication_error", "message": "invalid x-api-key"},
            },
        )
    )
    secret = "sk-ant-secret-do-not-leak"
    adapter = _make_adapter(api_key=secret)
    try:
        with pytest.raises(ProviderAuthError) as excinfo:
            await adapter.chat_completion(_basic_request(), model="claude-sonnet-4-6", stream=False)
    finally:
        await adapter.aclose()

    err = excinfo.value
    serialized = json.dumps(err.to_envelope())
    assert secret not in serialized
    assert err.details["upstream_status"] == 401
    assert err.details.get("upstream_error_type") == "authentication_error"


@pytest.mark.unit
@respx.mock
async def test_upstream_500_raises_provider_http_error() -> None:
    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(
        return_value=httpx.Response(
            500,
            json={"type": "error", "error": {"type": "api_error", "message": "internal"}},
        )
    )
    adapter = _make_adapter()
    try:
        with pytest.raises(ProviderHTTPError) as excinfo:
            await adapter.chat_completion(_basic_request(), model="claude-sonnet-4-6", stream=False)
    finally:
        await adapter.aclose()
    assert excinfo.value.upstream_status == 500


@pytest.mark.unit
@respx.mock
async def test_network_error_raises_provider_network_error() -> None:
    respx.post(f"{ANTHROPIC_BASE}/v1/messages").mock(side_effect=httpx.ConnectError("dns failure"))
    adapter = _make_adapter()
    try:
        with pytest.raises(ProviderNetworkError):
            await adapter.chat_completion(_basic_request(), model="claude-sonnet-4-6", stream=False)
    finally:
        await adapter.aclose()


@pytest.mark.unit
async def test_embeddings_raises_unsupported() -> None:
    """Anthropic has no embeddings endpoint; the adapter says so explicitly."""

    adapter = _make_adapter()
    try:
        with pytest.raises(ProviderUnsupportedError):
            await adapter.embeddings(
                EmbeddingsRequest(model="claude-sonnet-4-6", input="hi"),
                model="claude-sonnet-4-6",
            )
    finally:
        await adapter.aclose()


# --- Health check -------------------------------------------------------------


@pytest.mark.unit
@respx.mock
async def test_health_check_reports_reachable_on_200() -> None:
    respx.get(f"{ANTHROPIC_BASE}/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    adapter = _make_adapter()
    try:
        health = await adapter.health_check()
    finally:
        await adapter.aclose()
    assert health.reachable is True
    assert health.error is None
    assert health.latency_ms is not None


@pytest.mark.unit
@respx.mock
async def test_health_check_reports_auth_error_distinctly() -> None:
    """A 401 to /v1/models means the upstream is reachable but our
    credentials are bad — distinct from a network failure."""

    respx.get(f"{ANTHROPIC_BASE}/v1/models").mock(return_value=httpx.Response(401))
    adapter = _make_adapter()
    try:
        health = await adapter.health_check()
    finally:
        await adapter.aclose()
    assert health.reachable is True
    assert "auth" in (health.error or "").lower()


@pytest.mark.unit
@respx.mock
async def test_health_check_reports_unreachable_on_network_error() -> None:
    respx.get(f"{ANTHROPIC_BASE}/v1/models").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    adapter = _make_adapter()
    try:
        health = await adapter.health_check()
    finally:
        await adapter.aclose()
    assert health.reachable is False
    assert health.error is not None


# --- from_config -------------------------------------------------------------


@pytest.mark.unit
def test_from_config_missing_env_raises_clearly() -> None:
    """Construction-time failure (env var unset) raises a ValueError that
    names the missing variable and the provider — operators should see a
    legible message at startup, not at first request."""

    from app.config import ProviderConfig

    provider = ProviderConfig.model_validate(
        {
            "name": "anthropic-test",
            "type": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key_env": "ANTHROPIC_API_KEY_DOES_NOT_EXIST_SHOULD_BE_UNSET",
            "tier": 4,
        }
    )
    with pytest.raises(ValueError) as excinfo:
        AnthropicAdapter.from_config(provider, env={})
    assert "ANTHROPIC_API_KEY_DOES_NOT_EXIST_SHOULD_BE_UNSET" in str(excinfo.value)
    assert "anthropic-test" in str(excinfo.value)


@pytest.mark.unit
def test_from_config_rejects_non_anthropic_provider() -> None:
    from app.config import ProviderConfig

    provider = ProviderConfig.model_validate(
        {
            "name": "openai-prod",
            "type": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
            "tier": 4,
        }
    )
    with pytest.raises(ValueError):
        AnthropicAdapter.from_config(provider, env={"OPENAI_API_KEY": "x"})


@pytest.mark.unit
def test_from_config_succeeds_with_env_set() -> None:
    from app.config import ProviderConfig

    provider = ProviderConfig.model_validate(
        {
            "name": "anthropic-test",
            "type": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key_env": "ANTHROPIC_API_KEY",
            "tier": 4,
        }
    )
    adapter = AnthropicAdapter.from_config(provider, env={"ANTHROPIC_API_KEY": "sk-ant-x"})
    assert adapter.name == "anthropic-test"
