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
