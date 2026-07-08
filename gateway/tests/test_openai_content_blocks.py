"""F0-S1: OpenAI-standard block-form message content and tools passthrough.

langchain/langchain-openai 1.x clients (the fork's deep agents) send
``messages[].content`` as a list of typed blocks and drive tool-calling
loops. The gateway must validate the block form and forward it — plus
``tools``/``tool_choice`` — verbatim to OpenAI-compatible providers.
"""

from __future__ import annotations

from app.providers.openai import _to_openai_request
from app.providers.openai_schema import (
    ChatCompletionMessage,
    ChatCompletionRequest,
)

_BLOCKS = [{"type": "text", "text": "What is the liability cap?"}]

_TOOLS = [
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
    }
]


def test_block_content_validates_and_forwards_verbatim() -> None:
    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[
            ChatCompletionMessage(role="system", content="be brief"),
            ChatCompletionMessage(role="user", content=_BLOCKS),
        ],
    )
    body = _to_openai_request(request, model="gpt-4o", stream=False)
    assert body["messages"][0]["content"] == "be brief"
    assert body["messages"][1]["content"] == _BLOCKS


def test_tools_and_tool_choice_forward_verbatim() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "cap?"}],
            "tools": _TOOLS,
            "tool_choice": "auto",
        }
    )
    body = _to_openai_request(request, model="gpt-4o", stream=False)
    assert body["tools"] == _TOOLS
    assert body["tool_choice"] == "auto"
    assert all(not key.startswith("lq_ai_") for key in body)


def test_anthropic_adapter_extracts_block_content_text() -> None:
    """AZ-2b: block-form content translates to its text parts (the B3
    posture collapsed it to ``""``, which dropped langchain 1.x prompts)."""
    from app.providers.anthropic import _to_anthropic_request

    request = ChatCompletionRequest(
        model="claude-x",
        messages=[
            ChatCompletionMessage(role="user", content="real text"),
            ChatCompletionMessage(role="user", content=_BLOCKS),
        ],
    )
    body = _to_anthropic_request(request, model="claude-x", stream=False)
    assert body["messages"][0]["content"] == "real text"
    assert body["messages"][1]["content"] == "What is the liability cap?"


def test_ollama_adapter_reads_block_content_as_empty() -> None:
    from app.providers.ollama import _to_ollama_request

    request = ChatCompletionRequest(
        model="qwen3.5:9b",
        messages=[ChatCompletionMessage(role="user", content=_BLOCKS)],
    )
    body = _to_ollama_request(request, model="qwen3.5:9b", stream=False)
    assert body["messages"][0]["content"] == ""


async def test_streaming_tool_call_deltas_pass_through() -> None:
    """F0-S2: tool_call chunks in OpenAI SSE deltas survive translation —
    the agent loop and (later) SSE v2 depend on them arriving intact."""
    import httpx
    import respx

    from app.providers.openai import OpenAIAdapter

    sse_body = (
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
        '"model":"gpt-4o","choices":[{"index":0,"delta":{"role":"assistant",'
        '"tool_calls":[{"index":0,"id":"call_1","type":"function",'
        '"function":{"name":"read_clause","arguments":""}}]},'
        '"finish_reason":null}]}\n\n'
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
        '"model":"gpt-4o","choices":[{"index":0,"delta":{"tool_calls":'
        '[{"index":0,"function":{"arguments":"{\\"topic\\":\\"liability\\"}"}}]},'
        '"finish_reason":null}]}\n\n'
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,'
        '"model":"gpt-4o","choices":[{"index":0,"delta":{},'
        '"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/chat/completions").mock(
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
            request = ChatCompletionRequest.model_validate(
                {
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": "cap?"}],
                    "tools": _TOOLS,
                    "stream": True,
                }
            )
            chunks = [
                chunk
                async for chunk in await adapter.chat_completion(
                    request, model="gpt-4o", stream=True
                )
            ]
        finally:
            await client.aclose()

    deltas = [c.choices[0].delta for c in chunks if c.choices]
    tool_deltas = [d.tool_calls for d in deltas if d.tool_calls]
    assert tool_deltas, "tool_call deltas were dropped in streaming translation"
    assert tool_deltas[0][0]["function"]["name"] == "read_clause"
    finish = [c.choices[0].finish_reason for c in chunks if c.choices]
    assert "tool_calls" in finish
