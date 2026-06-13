"""Per-practice-area Deep Agent renderer — F1-S3 (fork, ADR-F002/F004/F010).

ONE renderer turns a :class:`~app.models.practice_area.PracticeArea` row's
declarative config into the pieces ``compose_and_execute_run`` folds into the
agent: a system-prompt suffix (the area profile), the area's default tier floor,
the area-scoped skills to attach, and the declarative subagent specs.

No per-area code branches (ADR-F004): every area is the same data flowing
through this function. The renderer is pure — it takes already-loaded data
(the area row's fields + the set of skill names the registry currently knows)
and returns a structured spec; the composition point owns the DB and the
registry lookup.

Security (ADR-F010, verified against deepagents 0.6.8 source): a declarative
subagent spec must NEVER carry a ``model`` key — deepagents hands a string
``model`` to ``init_chat_model``, which builds a provider SDK client directly
from environment keys, bypassing the Inference Gateway entirely. Area subagents
OMIT ``model`` so they inherit the parent's already-gateway-bound model
instance. :func:`reject_model_bearing_subagents` is the hard gate, enforced at
the ``build_deep_agent`` seam.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

# Keys a declarative area subagent spec may define. ``model`` is deliberately
# ABSENT — ADR-F010 forbids it (gateway bypass). ``tools`` is absent in v1:
# subagents inherit the parent's guarded matter tools (omitting the key =
# inherit, per deepagents 0.6.8 graph.py:670); explicit per-subagent tool
# subsets are a later slice.
_ALLOWED_SUBAGENT_KEYS = frozenset({"name", "description", "system_prompt", "skills"})
_REQUIRED_SUBAGENT_KEYS = ("name", "description", "system_prompt")


@dataclass(frozen=True)
class AreaAgentSpec:
    """What the renderer produces for the composition point to apply."""

    #: Appended to the system prompt after the matter addendum (area profile).
    system_prompt_suffix: str = ""
    #: The area's default minimum inference tier (1..5) or None. The caller
    #: combines it with the matter floor via min() before sending to the gateway.
    tier_floor: int | None = None
    #: Skill names to attach to the main agent (already filtered to the
    #: registry's known set by the caller).
    skills: list[str] = field(default_factory=list)
    #: deepagents declarative SubAgent specs (dicts) — guaranteed model-free.
    subagents: list[dict[str, Any]] = field(default_factory=list)


def reject_model_bearing_subagents(subagents: object) -> None:
    """Raise if any declarative subagent spec carries a non-gateway ``model``.

    ADR-F010: a string ``model`` reaches deepagents' ``init_chat_model`` and
    constructs a provider SDK client straight from env keys — a complete
    gateway bypass. App-authored area subagents must omit ``model`` (inherit
    the gateway-bound parent instance). A pre-built gateway ``BaseChatModel``
    instance is the only acceptable ``model`` value, and the renderer never
    sets one — so in practice any ``model`` key is rejected.
    """
    if not subagents:
        return
    if not isinstance(subagents, (list, tuple)):
        raise ValueError("subagents must be a list of declarative specs")
    for i, spec in enumerate(subagents):
        if not isinstance(spec, dict):
            # Pre-built CompiledSubAgent/AsyncSubAgent are not emitted by the
            # area renderer; the agent path only passes declarative dicts.
            raise ValueError(
                f"subagent[{i}] must be a declarative dict spec (got {type(spec).__name__})"
            )
        if "model" in spec and not isinstance(spec["model"], BaseChatModel):
            name = spec.get("name", "?")
            raise ValueError(
                f"subagent[{i}] {name!r} carries a non-gateway 'model' "
                f"({type(spec['model']).__name__}); per ADR-F010 area subagents must omit "
                "'model' to inherit the gateway-bound parent — a provider string bypasses "
                "the Inference Gateway."
            )


def build_area_subagents(agent_config: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build deepagents declarative SubAgent specs from area ``agent_config``.

    Each ``agent_config['subagents']`` entry is a declarative dict with
    ``name``/``description``/``system_prompt`` (required) and optional
    ``skills`` (names). Tools are intentionally OMITTED so each subagent
    inherits the parent's guarded matter tools (deepagents inherit-on-absent
    semantics) — the parent's GuardContext still mediates every dispatch.
    A ``model`` key is rejected (ADR-F010).
    """
    if not agent_config:
        return []
    raw = agent_config.get("subagents") or []
    if not isinstance(raw, list):
        raise ValueError("agent_config.subagents must be a list")
    specs: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"agent_config.subagents[{i}] must be an object")
        extra = set(entry) - _ALLOWED_SUBAGENT_KEYS
        if extra:
            raise ValueError(
                f"agent_config.subagents[{i}] has unsupported keys {sorted(extra)}; "
                f"allowed: {sorted(_ALLOWED_SUBAGENT_KEYS)} (ADR-F010 forbids 'model')"
            )
        for k in _REQUIRED_SUBAGENT_KEYS:
            if not entry.get(k) or not isinstance(entry[k], str):
                raise ValueError(f"agent_config.subagents[{i}] requires non-empty string {k!r}")
        spec: dict[str, Any] = {
            "name": entry["name"],
            "description": entry["description"],
            "system_prompt": entry["system_prompt"],
        }
        skills = entry.get("skills")
        if skills is not None:
            if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
                raise ValueError(f"agent_config.subagents[{i}].skills must be a list of strings")
            spec["skills"] = skills
        specs.append(spec)
    # Defense in depth: the specs we just built carry no 'model', but assert it.
    reject_model_bearing_subagents(specs)
    return specs


def render_area_agent(
    *,
    profile_md: str | None,
    default_tier_floor: int | None,
    agent_config: dict[str, Any] | None,
    bound_skill_names: Iterable[str],
    known_skill_names: Iterable[str],
) -> AreaAgentSpec:
    """Render the per-area agent pieces from an area's config.

    ``bound_skill_names`` are the area's ``practice_area_skills`` rows;
    ``known_skill_names`` is the registry's current set — bound names the
    registry no longer knows are dropped (registry is source of truth) so a
    removed skill never breaks a run.
    """
    suffix = ""
    if profile_md and profile_md.strip():
        suffix = "\n\n" + profile_md.strip()
    known = set(known_skill_names)
    skills = [s for s in bound_skill_names if s in known]
    subagents = build_area_subagents(agent_config)
    return AreaAgentSpec(
        system_prompt_suffix=suffix,
        tier_floor=default_tier_floor,
        skills=skills,
        subagents=subagents,
    )


def combine_tier_floors(*floors: int | None) -> int | None:
    """Strongest (lowest) non-null floor, or None if all are null.

    Lower tier number = stronger security (gateway combiner uses min()).
    """
    present = [f for f in floors if f is not None]
    return min(present) if present else None
