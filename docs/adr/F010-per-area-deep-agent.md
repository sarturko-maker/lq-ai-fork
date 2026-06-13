# F010 — Per-area Deep Agent: gateway-only model binding; model-bearing subagent specs are rejected

Status: proposed (drafted in F1-S3)

## Context

F1-S3 stands up the per-practice-area Deep Agent: a `practice_areas` row becomes an agent
identity (profile, default tier floor, area-scoped skills, declarative subagent specs) rendered
into a `deepagents.create_deep_agent` graph through the existing `build_gateway_chat_model` →
`build_deep_agent` seam (ADR-F002, ADR-F004). This is the first code in the fork to pass an
explicit `subagents=[...]` list — until now deepagents only auto-added its default
general-purpose subagent, which shares the parent's gateway-bound model.

The fork's first law is that **every LLM call routes through the Inference Gateway** — the only
egress, the only key-holder, where tier floors, anonymization, routing logs, and `lq_ai_purpose`
are enforced (CLAUDE.md; ADR-F001; `factory.py` docstring: "a direct provider call from agent
code is a security regression").

Verified from the installed `deepagents==0.6.8` source, a subagent spec carries an optional
`model: NotRequired[str | BaseChatModel]` field (`middleware/subagents.py:89`). In
`create_deep_agent`, `raw = spec.get("model", model); resolve_model(raw)` (`graph.py:608-609`),
and `resolve_model` (`_models.py:33-36`) does:

```python
if isinstance(model, BaseChatModel):
    return model
return init_chat_model(model, **apply_provider_profile(model))
```

So a **string** `model` (e.g. `"openai:gpt-5.5"`, `"anthropic:claude-…"`) is handed to
LangChain's `init_chat_model`, which constructs a provider SDK client directly from
`OPENAI_API_KEY`/`ANTHROPIC_API_KEY` in the environment and talks straight to the provider —
a complete bypass of the gateway. The same call path exists for the parent (`graph.py:567`) and
inside `SubAgentMiddleware` (`subagents.py:717`). Area `agent_config` is operator-authored data
that round-trips the config API and the DB; treating it as a place where a `model` string could
appear is treating it as a gateway-bypass vector.

Inheritance semantics (also source-verified) make omission safe: when a subagent omits `model`,
`spec.get("model", model)` returns the **exact parent `ChatOpenAI` instance** and `resolve_model`
passes it through untouched — so an omitting subagent inherits the gateway binding for free.
Likewise `permissions` REPLACE the parent's (no merge), `tools` OVERRIDE when the key is present
(else inherit the parent's), and middleware never inherits (a fresh default stack is built per
subagent). A correct per-area renderer must therefore emit COMPLETE per-subagent declarations
rather than rely on inheritance for anything security-relevant.

## Considered options

1. **Trust area config; pass `model` through if present.** Smallest code. Rejected: any area
   config (or a future area-creation UI, or a compromised admin row) could name a provider string
   and silently exfiltrate to a non-gateway provider with the host's env keys — the exact failure
   the gateway architecture exists to prevent. Non-starter.
2. **Allow a `model` field but validate it's a known gateway alias and re-resolve to a gateway
   instance.** Keeps per-subagent model choice. Rejected for v1: it reintroduces model-string
   handling in app code (the thing we're trying to forbid), adds an alias-allowlist to keep in
   sync with the gateway, and the use case (a cheaper tier for a fan-out subagent) is better
   served by constructing a second `build_gateway_chat_model` instance and passing the
   **instance** — no string ever appears.
3. **Forbid the `model` key entirely in app-authored subagent specs; the renderer never sets it;
   `build_deep_agent` rejects any spec that carries it.** Chosen.

## Decision

**The per-area renderer (`area_agent.py`) builds `deepagents.SubAgent` specs that NEVER set a
`model` key**, so every subagent inherits the single parent `ChatOpenAI` built by
`build_gateway_chat_model` (gateway base URL, key on the injected async client, tier floor +
privilege in `extra_body`). Per-subagent model differentiation, if ever needed, is expressed by
passing a second gateway-bound `BaseChatModel` **instance** — never a string.

**`build_deep_agent` enforces this as a hard gate**: before calling `create_deep_agent`, it
inspects any `subagents=` kwarg and raises `ValueError` if a `dict`-shaped (declarative) spec
carries a `model` key whose value is anything other than an already-constructed gateway
`BaseChatModel` instance — in practice, app code passes no `model` at all, so any `model` key is
rejected. The guard recurses is unnecessary (deepagents 0.6.8 declarative subagents do not nest),
but `CompiledSubAgent`/`AsyncSubAgent` (pre-built graphs / remote `graph_id`) are out of scope for
the renderer and not emitted by it.

Per-area model/tier policy is expressed ONLY through the gateway envelope: the area
`default_tier_floor` is combined with the matter floor via `min()` API-side and sent as
`lq_ai_project_minimum_inference_tier`, which the gateway enforces.

This is enforced at the `factory.py` seam (the single `deepagents` import site) and covered by a
test asserting a model-bearing subagent spec raises.

## Consequences

- **Good**: the gateway stays the only egress even as the agent fans out; area config cannot
  introduce a direct provider call; the guard lives at the one seam all agent construction passes
  through; the rule is one line of policy with a test, not a runtime allowlist to maintain.
- **Cost**: per-subagent model choice is not configurable via area JSON. Acceptable — the only
  legitimate need (differentiated tiers) is met by passing gateway instances, and all aliases
  route to MiniMax-M3 today anyway.
- **Forward**: if a future slice genuinely needs declarative per-subagent tiers, it adds an area
  config field naming a gateway **alias** (not a provider string), and the renderer constructs the
  corresponding gateway instance — the guard (no raw string reaches deepagents) is unchanged.
- Governs the seam at `api/app/agents/factory.py::build_deep_agent` and
  `api/app/agents/area_agent.py`; referenced in commit messages and a one-line comment at both.
