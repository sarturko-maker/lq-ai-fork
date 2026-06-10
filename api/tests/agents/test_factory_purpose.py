"""F0-S2/S4: the factory's chat model tags every request body correctly.

Verified at the wire level — a mock httpx transport is injected through
``build_gateway_http_client``'s ``transport`` seam (no monkeypatching)
and the captured request must carry:

* ``lq_ai_purpose`` top-level, where the gateway's
  ``_purpose_from_request`` reads it for the routing-log ``purpose``
  column. ``extra_body`` is the verified channel: the openai SDK merges
  it into the request JSON (unknown top-level ``model_kwargs`` would
  raise ``TypeError`` in ``create()`` instead).
* the matter envelope (F0-S4): ``lq_ai_project_minimum_inference_tier``
  and ``lq_ai_privileged`` when a matter binding supplies them — the
  chat path's D1 / M2-B3 fields, enforced gateway-side.
* the gateway key on the HEADER only — it rides the injected client
  (S1-review carry-over: ``default_headers`` is a serializable pydantic
  field on ``ChatOpenAI``; the key must never appear in a model dump).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents.factory import build_gateway_chat_model, build_gateway_http_client

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

    http_client = build_gateway_http_client(
        gateway_key="test-gateway-key",
        transport=httpx.MockTransport(handler),
    )
    async with http_client:
        model = build_gateway_chat_model(
            gateway_url="http://gateway.test:8001",
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
    # Gateway auth rides the client's header, not the bearer placeholder.
    assert request.headers["X-LQ-AI-Gateway-Key"] == "test-gateway-key"


async def test_purpose_parameter_overrides_default() -> None:
    request = await _invoke_and_capture(purpose="agent_loop_eval")
    body = json.loads(request.content)
    assert body["lq_ai_purpose"] == "agent_loop_eval"


async def test_unbound_run_sends_no_matter_envelope() -> None:
    request = await _invoke_and_capture()
    body = json.loads(request.content)
    assert "lq_ai_project_minimum_inference_tier" not in body
    assert "lq_ai_privileged" not in body


async def test_matter_envelope_lands_in_request_body() -> None:
    request = await _invoke_and_capture(project_minimum_inference_tier=4, privileged=True)
    body = json.loads(request.content)
    assert body["lq_ai_project_minimum_inference_tier"] == 4
    assert body["lq_ai_privileged"] is True


async def test_gateway_key_never_serializes_off_the_model() -> None:
    """S1-review carry-over (closed in F0-S4): the key must not be a
    ``ChatOpenAI`` field — ``default_headers`` leaks into dumps/traces;
    the injected client does not."""
    http_client = build_gateway_http_client(
        gateway_key="test-gateway-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=_COMPLETION)),
    )
    async with http_client:
        model = build_gateway_chat_model(
            gateway_url="http://gateway.test:8001",
            http_async_client=http_client,
        )
        dumped = model.model_dump_json()
        assert "test-gateway-key" not in dumped
