"""F0-S2: the factory's chat model tags every request body with lq_ai_purpose.

Verified at the wire level — a mock httpx transport is injected through
``build_gateway_chat_model``'s ``http_async_client`` seam (no
monkeypatching) and the captured request body must carry the
``lq_ai_purpose`` extension top-level, where the gateway's
``_purpose_from_request`` reads it for the routing-log ``purpose``
column. ``extra_body`` is the verified channel: the openai SDK merges
it into the request JSON (unknown top-level ``model_kwargs`` would
raise ``TypeError`` in ``create()`` instead).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents.factory import build_gateway_chat_model

pytestmark = pytest.mark.unit

_COMPLETION = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 1,
    "model": "smart",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "hello"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}


async def _invoke_and_capture(**factory_kwargs: object) -> httpx.Request:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_COMPLETION)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        model = build_gateway_chat_model(
            gateway_url="http://gateway.test:8001",
            gateway_key="test-gateway-key",
            http_async_client=http_client,
            **factory_kwargs,  # type: ignore[arg-type]
        )
        await model.ainvoke("What is the liability cap?")

    assert captured, "no request reached the transport"
    return captured[0]


async def test_default_purpose_agent_loop_lands_in_request_body() -> None:
    request = await _invoke_and_capture()
    body = json.loads(request.content)
    assert body["lq_ai_purpose"] == "agent_loop"
    # extra_body merges INTO the body — it must not appear as a nested key.
    assert "extra_body" not in body
    assert body["model"] == "smart"
    # Gateway auth still rides the header, not the bearer placeholder.
    assert request.headers["X-LQ-AI-Gateway-Key"] == "test-gateway-key"


async def test_purpose_parameter_overrides_default() -> None:
    request = await _invoke_and_capture(purpose="agent_loop_eval")
    body = json.loads(request.content)
    assert body["lq_ai_purpose"] == "agent_loop_eval"
