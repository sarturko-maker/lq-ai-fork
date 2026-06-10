# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-10, end of F0-S1)

- F0-S1 MERGED (PR #24, squash `816f5ac`); ADR-F001..F005 accepted (F005 = agent-merge policy with
  hardened gates — read it before merging anything). F0 re-sequenced: visible agent at S3.
- Dev stack: `docker compose` 8 services healthy on the Chromebook. Gateway aliases
  `smart`/`fast`/`budget` → `minimax/MiniMax-M3` (tier 4). MiniMax key in `.env` (`MINIMAX_API_KEY`).
  Gateway's LIVE config lives in a named volume — edit `gateway.yaml`, then copy into the container
  (`docker exec lq-ai-gateway-1 cp /usr/share/lq-ai/gateway.yaml.example /etc/lq-ai/gateway.yaml`)
  and `docker compose restart gateway` (SIGHUP reloads config but not adapters).
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!

## Done (F0-S1)

- **Dependency migration** (closes DE-319): langgraph 1.2.4, langchain 1.3.6, langchain-openai 1.3.0,
  langgraph-checkpoint-postgres 3.1.0, `deepagents==0.6.8` (EXACT). Three legacy executors re-typed
  with per-module callback Protocols (type-only break, zero runtime changes). api suite: 1930 passed.
- **Agent substrate**: `api/app/agents/factory.py` — `build_gateway_chat_model()` (gateway is the only
  egress; auth via `X-LQ-AI-Gateway-Key` header) + `build_deep_agent()` (single deepagents import site).
- **Gateway OpenAI-compat hardening**: block-form `messages[].content` accepted and forwarded
  verbatim; `tools`/`tool_choice` passthrough covered by tests; fixed pre-existing `lq_ai_privileged`
  leak into provider bodies; isinstance guards in anonymization/skill-assembly/anthropic (text-only
  paths). Gateway: mypy --strict green, 566 passed.
- **LIVE PROOF**: provider-marked spike passed — deep agent drove a model-initiated `read_clause`
  tool call through the gateway on MiniMax-M3 and used the result (`inference_routing_log` rows
  11:58:27 + 11:58:32, two loop steps). Run: `pytest -m provider api/tests/agents/`.

## Next slice: F0-S2 — gateway tools formalization + agent-run records (see MILESTONES F0-S2)

- Promote `tools`/`tool_choice` (request) and tool-call deltas (streaming) from `extra="allow"`
  passthrough to typed schema fields; tag agent-loop steps in the routing log (`purpose`).
- Streaming tool-calls end-to-end (delta frames carry `tool_calls` chunks) — prerequisite for SSE v2.
- Anthropic adapter: `tool_use`/`tool_result` translation + block content (every `F0-S1` comment
  marker in `gateway/app` is an S2 entry point — `grep -rn "F0-S1" gateway/app`).
- Decide anonymization coverage for block-form content (skip is now observable: span attr
  `anonymization.block_content_skipped` + warning; fully-skipped requests report applied=False).
- From the F0-S1 adversarial review (deferred notes): (a) factory key exposure — move the gateway
  key out of `ChatOpenAI(default_headers=...)` into a pre-built httpx client so `repr()`/LangSmith
  serialization can't leak it; (b) `build_deep_agent` must reject/wrap model-bearing subagent
  specs so a subagent can't be given a provider-direct model that bypasses the gateway.
- NEW in S2 (re-sequence): `agent_runs` + `agent_run_steps` tables (steps persisted as they
  complete — the S3 polling contract), POST/GET run endpoints, interim caps (max steps, wall-clock,
  per-run cost via routing log). Then S3 = FIRST VISIBLE AGENT (Agents tab v0, polled capability
  rail), S4 multi-turn (`chats.py:~1370`), S5 SSE v2, S6 eval gate (ADR-F004 N≥20).

## Pick up exactly here

1. Read CLAUDE.md → ADR-F001..F004 → this file. 2. Branch `fork/f0-s2-agent-runs` from main. 4. Sanity rerun of the live spike (one command):

```bash
GW_KEY=$(grep '^LQ_AI_GATEWAY_KEY=' .env | cut -d= -f2)
docker run --rm --network lq-ai_default --entrypoint sh -v "$PWD":/repo -w /repo/api \
  -e LQ_AI_GATEWAY_URL=http://gateway:8001 -e LQ_AI_GATEWAY_KEY="$GW_KEY" lq-ai-api:latest -c \
  'pip install -q -e ".[dev]" && pip install -q --force-reinstall --no-deps langgraph langgraph-prebuilt langgraph-checkpoint && pytest -m provider tests/agents/ -v'
```

## Gotchas

- **In-place pip upgrade clobbers langgraph-prebuilt** (0.2's uninstall removes 1.x files):
  `pip install --force-reinstall --no-deps langgraph langgraph-prebuilt langgraph-checkpoint`.
  Fresh image builds are unaffected — rebuild `api` + `arq-worker` + `ingest-worker` together.
- langgraph 1.x has no `__version__` (use `importlib.metadata`); `add_node` requires callback
  protocols with a NAMED `state` param (see `app/{autonomous,playbooks,tabular}/nodes.py`).
- langchain-openai 1.x: `api_key` is `SecretStr`; clients send block-form content — the gateway's
  OpenAI-compatible path forwards it; Anthropic/Ollama adapters read it as EMPTY until S2.
- Host Python is 3.11; api/gateway need 3.12 — all tooling runs in containers (`--entrypoint sleep`,
  the api image's default entrypoint runs alembic and dies without `DATABASE_URL`).
- Tests: NEVER against the live compose postgres — throwaway `pgvector/pgvector:pg16` with
  `DATABASE_URL=postgresql+asyncpg://lq_ai:lq_ai@<pg>:5432/lq_ai` (conftest auto-migrates).
- MiniMax-M3 emits `<think>` blocks inline in chat (backlog: MessageBubble rendering).
