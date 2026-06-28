"""F2 N1 (ADR-F049): TierMemoryMiddleware — unit + real-agent integration.

The pure appender is unit-tested directly; the middleware itself is driven
through the REAL deepagents graph (``build_deep_agent`` + a scripted model),
mirroring the composition e2e tests, so we assert on what the model actually
receives after middleware augmentation — not on an isolated mock.
"""

from __future__ import annotations

import uuid

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agents.area_agent import AreaAgentSpec
from app.agents.composition import render_memory_tiers, system_prompt_for
from app.agents.factory import build_deep_agent
from app.agents.tier_middleware import TierMemoryMiddleware, _append_text_block
from app.agents.tools import MatterBinding
from tests.agents.fakes import ScriptedToolCallingModel, final_message


def _flatten(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _system_text(model: ScriptedToolCallingModel) -> str:
    """Flattened system-message text from the model's first call."""
    first: list[BaseMessage] = model.seen_messages[0]
    return "\n".join(_flatten(m.content) for m in first if isinstance(m, SystemMessage))


# --- the pure appender -------------------------------------------------------


def test_append_text_block_to_none_creates_single_block() -> None:
    assert _append_text_block(None, "hello").text == "hello"


def test_append_text_block_to_string_message_separates_with_blank_line() -> None:
    assert _append_text_block(SystemMessage(content="BASE"), "TIER").text == "BASE\n\nTIER"


def test_append_text_block_preserves_existing_blocks() -> None:
    base = _append_text_block(SystemMessage(content="BASE"), "FIRST")
    assert _append_text_block(base, "SECOND").text == "BASE\n\nFIRST\n\nSECOND"


# --- the middleware through the real deep agent ------------------------------


async def test_tier_text_reaches_model_after_base_prompt() -> None:
    model = ScriptedToolCallingModel(responses=[final_message("ok")])
    mw = TierMemoryMiddleware(tier_text="\n\n## TIER BLOCK\n\nmatter detail")
    agent = build_deep_agent(model=model, tools=[], system_prompt="BASE IDENTITY.", middleware=[mw])
    await agent.ainvoke({"messages": [HumanMessage("hi")]})

    text = _system_text(model)
    assert "BASE IDENTITY." in text
    assert "## TIER BLOCK" in text
    assert "matter detail" in text
    # The tier lands AFTER the static base (the F2 N1 ordering contract).
    assert text.index("BASE IDENTITY.") < text.index("## TIER BLOCK")


def test_tier_text_reaches_model_on_the_sync_path() -> None:
    model = ScriptedToolCallingModel(responses=[final_message("ok")])
    mw = TierMemoryMiddleware(tier_text="## SYNC TIER\n\ndetail")
    agent = build_deep_agent(model=model, tools=[], system_prompt="BASE.", middleware=[mw])
    agent.invoke({"messages": [HumanMessage("hi")]})

    text = _system_text(model)
    assert "BASE." in text
    assert "## SYNC TIER" in text


async def test_production_assembly_orders_area_method_before_data_tiers() -> None:
    """Lock the F2 N1 ordering delta on the REAL renderers: with system_prompt_for as
    the static base (ending in the area suffix) and render_memory_tiers on the
    middleware, the model sees the area method BEFORE the data tiers — the deliberate,
    benign reorder this slice introduces (data closest to the conversation)."""
    binding = MatterBinding(
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Acme MSA",
        privileged=False,
        minimum_inference_tier=None,
    )
    area = AreaAgentSpec(system_prompt_suffix="\n\nYou are the TestArea agent.")
    base = system_prompt_for(binding, area)  # identity + matter doctrine + area suffix
    tier_text = render_memory_tiers(
        client_context="House: we act for the buyer.",
        matter_wiki="Matter wiki body.",
    )
    model = ScriptedToolCallingModel(responses=[final_message("ok")])
    agent = build_deep_agent(
        model=model,
        tools=[],
        system_prompt=base,
        middleware=[TierMemoryMiddleware(tier_text=tier_text)],
    )
    await agent.ainvoke({"messages": [HumanMessage("hi")]})

    text = _system_text(model)
    assert "You are the TestArea agent." in text
    assert "----- BEGIN CLIENT / HOUSE CONTEXT -----" in text
    assert "----- BEGIN MATTER MEMORY -----" in text
    # The area method (static base) precedes BOTH data tiers (middleware-injected).
    assert text.index("You are the TestArea agent.") < text.index(
        "----- BEGIN CLIENT / HOUSE CONTEXT -----"
    )
    assert text.index("You are the TestArea agent.") < text.index("----- BEGIN MATTER MEMORY -----")


async def test_empty_tier_text_matches_no_middleware() -> None:
    """Degradation: an empty tier block is a true no-op — the model sees exactly
    what it would with no TierMemoryMiddleware at all."""
    base_model = ScriptedToolCallingModel(responses=[final_message("ok")])
    base_agent = build_deep_agent(model=base_model, tools=[], system_prompt="BASE ONLY.")
    await base_agent.ainvoke({"messages": [HumanMessage("hi")]})

    noop_model = ScriptedToolCallingModel(responses=[final_message("ok")])
    noop_agent = build_deep_agent(
        model=noop_model,
        tools=[],
        system_prompt="BASE ONLY.",
        middleware=[TierMemoryMiddleware(tier_text="")],
    )
    await noop_agent.ainvoke({"messages": [HumanMessage("hi")]})

    assert _system_text(noop_model) == _system_text(base_model)
    assert "BASE ONLY." in _system_text(noop_model)
