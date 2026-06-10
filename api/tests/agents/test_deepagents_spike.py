"""F0-S1 spike: a deep agent drives a real tool-calling loop through the gateway.

Provider-marked (CI skips). Run against the live dev stack:

    pytest -m provider tests/agents/test_deepagents_spike.py -s

Requires a reachable gateway (LQ_AI_GATEWAY_URL, default http://localhost:8001
outside compose) with a configured provider behind the ``smart`` alias, and
LQ_AI_GATEWAY_KEY set. Per ADR-F004, pipeline tests never mock the LLM: this
exercises the real model. The assertion that matters is that the MODEL
initiated the tool call — Python never dispatches the tool itself.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_CLAUSE_TEXT = (
    "Clause 7.2 (Limitation of Liability): each party's aggregate liability "
    "is capped at the fees paid in the twelve (12) months preceding the claim."
)


async def test_deep_agent_completes_tool_loop_through_gateway() -> None:
    from app.agents import build_deep_agent, build_gateway_chat_model, build_gateway_http_client

    tool_calls: list[str] = []

    def read_clause(topic: str) -> str:
        """Return the verbatim text of the contract clause covering ``topic``."""
        tool_calls.append(topic)
        return _CLAUSE_TEXT

    http_client = build_gateway_http_client(gateway_key=os.environ["LQ_AI_GATEWAY_KEY"])
    async with http_client:
        model = build_gateway_chat_model(
            model_alias=os.environ.get("LQ_AI_SPIKE_MODEL_ALIAS", "smart"),
            gateway_url=os.environ.get("LQ_AI_GATEWAY_URL", "http://localhost:8001"),
            http_async_client=http_client,
        )
        agent = build_deep_agent(
            model=model,
            tools=[read_clause],
            system_prompt=(
                "You are a commercial contracts assistant. To quote any clause you "
                "MUST fetch it with the read_clause tool — never answer from memory."
            ),
        )

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "What is the liability cap under this contract?",
                    }
                ]
            }
        )

    assert tool_calls, "model never initiated a tool call through the gateway"
    final = str(result["messages"][-1].content)
    assert "twelve" in final or "12 months" in final, final
