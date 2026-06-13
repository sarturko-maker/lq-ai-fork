"""Per-area Deep Agent renderer + the ADR-F010 gateway-bypass guard — F1-S3.

The load-bearing security test is :func:`test_model_bearing_subagent_rejected`:
a declarative subagent spec carrying a ``model`` key must never reach
deepagents (a string model bypasses the Inference Gateway via
``init_chat_model``). The renderer never emits one, and ``build_deep_agent``
re-asserts it at the single construction seam.
"""

from __future__ import annotations

import pytest

from app.agents.area_agent import (
    AreaAgentSpec,
    build_area_subagents,
    combine_tier_floors,
    reject_model_bearing_subagents,
    render_area_agent,
)

pytestmark = pytest.mark.unit


# --- the security guard ----------------------------------------------------


def test_model_bearing_subagent_rejected() -> None:
    """ADR-F010: a string ``model`` on a subagent spec is rejected."""
    with pytest.raises(ValueError, match="bypasses the Inference Gateway"):
        reject_model_bearing_subagents(
            [{"name": "x", "description": "d", "system_prompt": "p", "model": "openai:gpt-5.5"}]
        )


def test_model_bearing_via_build_area_subagents_rejected() -> None:
    """The config path rejects a ``model`` key before it can be stored."""
    with pytest.raises(ValueError, match=r"unsupported keys|model"):
        build_area_subagents(
            {"subagents": [{"name": "x", "description": "d", "system_prompt": "p", "model": "m"}]}
        )


def test_none_and_empty_subagents_pass() -> None:
    reject_model_bearing_subagents(None)
    reject_model_bearing_subagents([])


def test_non_list_subagents_rejected() -> None:
    with pytest.raises(ValueError, match="list"):
        reject_model_bearing_subagents({"name": "x"})


def test_non_dict_subagent_rejected() -> None:
    with pytest.raises(ValueError, match="declarative dict"):
        reject_model_bearing_subagents(["not-a-dict"])


def test_build_deep_agent_seam_rejects_model_bearing_subagent() -> None:
    """The guard fires at the single construction seam (ADR-F010), before
    deepagents ever sees the spec."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from app.agents.factory import build_deep_agent

    with pytest.raises(ValueError, match="bypasses the Inference Gateway"):
        build_deep_agent(
            model=FakeListChatModel(responses=["x"]),
            tools=[],
            system_prompt="p",
            subagents=[
                {"name": "x", "description": "d", "system_prompt": "p", "model": "openai:gpt-5.5"}
            ],
        )


def test_gateway_model_instance_is_allowed() -> None:
    """A pre-built gateway BaseChatModel instance is the one acceptable
    ``model`` value (the renderer never sets it, but the guard permits it)."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    model = FakeListChatModel(responses=["ok"])
    # Should NOT raise — it's a BaseChatModel instance, not a provider string.
    reject_model_bearing_subagents(
        [{"name": "x", "description": "d", "system_prompt": "p", "model": model}]
    )


# --- the declarative subagent builder --------------------------------------


def test_build_area_subagents_happy_path() -> None:
    specs = build_area_subagents(
        {
            "subagents": [
                {
                    "name": "researcher",
                    "description": "Finds passages in the matter documents.",
                    "system_prompt": "You research the matter's documents.",
                    "skills": ["nda-review"],
                }
            ]
        }
    )
    assert len(specs) == 1
    spec = specs[0]
    assert spec["name"] == "researcher"
    assert spec["skills"] == ["nda-review"]
    # No model key — inherits the gateway-bound parent (ADR-F010).
    assert "model" not in spec
    # No tools key — inherits the parent's guarded matter tools.
    assert "tools" not in spec


def test_build_area_subagents_unknown_key_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported keys"):
        build_area_subagents(
            {"subagents": [{"name": "x", "description": "d", "system_prompt": "p", "tools": []}]}
        )


def test_build_area_subagents_missing_required_rejected() -> None:
    with pytest.raises(ValueError, match="requires non-empty string"):
        build_area_subagents({"subagents": [{"name": "x", "description": "d"}]})


def test_build_area_subagents_bad_skills_rejected() -> None:
    with pytest.raises(ValueError, match="skills must be a list"):
        build_area_subagents(
            {"subagents": [{"name": "x", "description": "d", "system_prompt": "p", "skills": "no"}]}
        )


def test_build_area_subagents_empty_config() -> None:
    assert build_area_subagents(None) == []
    assert build_area_subagents({}) == []
    assert build_area_subagents({"subagents": []}) == []


# --- the renderer ----------------------------------------------------------


def test_render_area_agent_folds_profile_and_tier() -> None:
    spec = render_area_agent(
        profile_md="  You are the Commercial agent.  ",
        default_tier_floor=2,
        agent_config={},
        bound_skill_names=[],
        known_skill_names=[],
    )
    assert isinstance(spec, AreaAgentSpec)
    assert spec.system_prompt_suffix == "\n\nYou are the Commercial agent."
    assert spec.tier_floor == 2
    assert spec.subagents == []


def test_render_area_agent_empty_profile_no_suffix() -> None:
    spec = render_area_agent(
        profile_md="   ",
        default_tier_floor=None,
        agent_config=None,
        bound_skill_names=[],
        known_skill_names=[],
    )
    assert spec.system_prompt_suffix == ""
    assert spec.tier_floor is None


def test_render_area_agent_drops_unknown_skills() -> None:
    """Bound skills the registry no longer knows are dropped (registry is
    source of truth) — a removed skill never breaks a run."""
    spec = render_area_agent(
        profile_md="x",
        default_tier_floor=None,
        agent_config={},
        bound_skill_names=["nda-review", "deleted-skill"],
        known_skill_names=["nda-review", "msa-review"],
    )
    assert spec.skills == ["nda-review"]


# --- tier-floor combine ----------------------------------------------------


def test_combine_tier_floors() -> None:
    assert combine_tier_floors(None, None) is None
    assert combine_tier_floors(3, None) == 3
    assert combine_tier_floors(None, 2) == 2
    # Strongest (lowest) wins — lower tier number = stronger security.
    assert combine_tier_floors(3, 2) == 2
    assert combine_tier_floors(1, 4, 2) == 1
