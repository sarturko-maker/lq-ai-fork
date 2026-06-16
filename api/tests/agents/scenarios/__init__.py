"""UX-B-1 scenario harness — live model qualification (ADR-F015).

A reusable, provider-marked rig that drives the REAL practice-area Deep
Agent through the production composition point
(:func:`app.agents.composition.compose_and_execute_run`) against the
LIVE gateway (real MiniMax-M3), then reads back the settled
:class:`~app.models.agent_run.AgentRun` + :class:`AgentRunStep` rows as
honest receipts (tool selection, step count, final answer, refusal) and
emits a committed **behavior report**.

The model is dependency-injected (MiniMax-M3 today, swappable) — this
harness is the natural home for the S9 qualification gate: re-run it on
any model swap and the report tells you what regressed. It runs
out-of-CI (``@pytest.mark.provider`` + a ``LQ_AI_GATEWAY_KEY`` skipif);
the scripted-model unit tests stay the CI gate (ADR-F015 §Decision).

Nothing here holds a provider key: the production path builds the model
via :func:`app.agents.factory.build_gateway_chat_model` and the key
rides the gateway http client's header, sourced from settings. The
report carries OBSERVATIONS ONLY — tool names, counts, pass/fail,
bounded answer excerpts — never keys or raw secret-bearing payloads.
"""
