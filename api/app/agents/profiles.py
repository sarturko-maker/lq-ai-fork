"""Harness profiles for the deep-agent loop (F0-S9, ADR-F004).

Model qualification is per-(model, harness-profile) pair — scores
measured on an untuned harness are noise (LangChain measured 10-20pt
swings from profile alone; docs/fork/research/deepagents-ecosystem.md
§1.2). The MiniMax-M3 baseline profile registered here is deliberately
EMPTY: every behavioural tweak (tool description rewrites, prompt
suffixes, excluded middleware) enters through this seam WITH a measured
eval delta attached, per the subtractive-doctrine rule inherited from
oscar-gc (ADR-F004: positive imperative, ≤1 collapsed exclusion, never
stacked NEVER lists — and adding prompt text makes things worse by
default). The qualification matrix in docs/fork/evidence/f0-s9/ names
the profile it measured.

Key shape: deepagents resolves a profile for a PRE-BUILT model by
``{provider}:{identifier}``. For the gateway-injected ``ChatOpenAI``
that is ``openai:{alias}`` — the gateway alias (``smart``/``fast``/
``budget``) is the only model identifier the api ever sees; the
alias→provider/model mapping lives in gateway.yaml. All three aliases
currently route to minimax/MiniMax-M3.

deepagents is imported lazily (same hygiene as
:func:`app.agents.factory.build_deep_agent` — the package is pre-1.0).
"""

from __future__ import annotations

# Gateway aliases the agent loop dispatches on, all routing to
# MiniMax-M3 today (gateway.yaml model_aliases).
_GATEWAY_ALIAS_PROFILE_KEYS = ("openai:smart", "openai:fast", "openai:budget")

_registered = False


def ensure_harness_profiles_registered() -> None:
    """Register the fork's model harness profiles (idempotent).

    Called from :func:`app.agents.factory.build_deep_agent` so the
    registry is populated before any agent is constructed — no
    import-time side effects (CLAUDE.md composition-root rule).
    deepagents' registry is process-global; re-registration merges,
    so the guard flag is an optimization, not a correctness need.
    """
    global _registered
    if _registered:
        return
    from deepagents import HarnessProfile, register_harness_profile

    # MiniMax-M3 baseline: the empty profile. See module docstring for
    # why empty is the measured starting point, not an omission.
    minimax_m3 = HarnessProfile()
    for key in _GATEWAY_ALIAS_PROFILE_KEYS:
        register_harness_profile(key, minimax_m3)
    _registered = True
