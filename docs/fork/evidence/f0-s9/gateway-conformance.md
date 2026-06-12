# F0-S9 gateway conformance — live verification (2026-06-12)

Prerequisite to every score in the model-qualification matrix: a low tool-call
or uptake score must indict the model, not the serving layer
(`docs/fork/research/deepagents-ecosystem.md` §1.3; the vLLM/K2 precedent was a
model "failing" at <20% tool-call parse rate purely from serving bugs).

Both probes ran against the LIVE dev gateway (`http://127.0.0.1:8001/v1`,
alias `smart` → `minimax/MiniMax-M3`), anonymization disabled (dev default).
Archived evidence: probe 1 raw SSE in `gateway-probe1-streamed-tool-call.sse`;
probe 2 request/response in `gateway-probe2-history-roundtrip-{request,response}.json`.

Runnable probe commands (used verbatim for any new provider/model — e.g. the
Kimi K2.x row; substitute the alias):

```bash
# Probe 1 — streamed tool call: inspect delta ids + reasoning shape
KEY=$(grep -E '^LQ_AI_GATEWAY_KEY=' .env | cut -d= -f2-)
curl -sS -N -m 120 http://127.0.0.1:8001/v1/chat/completions \
  -H "X-LQ-AI-Gateway-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"model":"smart","stream":true,"max_tokens":2000,
       "messages":[{"role":"user","content":"What is the weather in Berlin right now? Use the get_weather tool."}],
       "tools":[{"type":"function","function":{"name":"get_weather","description":"Get current weather for a city",
         "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],
       "tool_choice":"auto"}'

# Probe 2 — history resend: echo the FULL probe-1 assistant message
# (content incl. <think> + tool_calls) plus a tool result; expect 200 +
# a grounded continuation. Template: gateway-probe2-history-roundtrip-request.json
curl -sS -m 120 http://127.0.0.1:8001/v1/chat/completions \
  -H "X-LQ-AI-Gateway-Key: $KEY" -H "Content-Type: application/json" \
  -d @docs/fork/evidence/f0-s9/gateway-probe2-history-roundtrip-request.json
```

## Probe 1 — streamed tool call (response direction)

Request: `stream=true`, one `get_weather` tool, user asks for Berlin weather.

Findings, all PASS:

| Property | Observed |
|---|---|
| Opening tool-call delta id | `call_function_xplk3zli8lqh_1` — non-empty, provider-supplied |
| Continuation deltas | `index`-keyed, arguments-only, no id (per OpenAI wire contract) |
| `finish_reason` | `tool_calls` |
| Reasoning shape | **dual-channel**: inline `<think>…</think>` in `delta.content` AND a duplicate `reasoning` string field on each delta |
| Gateway pass-through | both channels survive (`extra="allow"` schemas + `model_dump(exclude_none=True)` re-emit) |
| Usage | `completion_tokens_details.reasoning_tokens` present (26 of 61 completion tokens) |

## Probe 2 — history resend (the direction that actually breaks loops)

Request: non-streaming; the FULL probe-1 assistant message (content including
the verbatim `<think>` block + the `tool_calls` array) echoed back, followed by
a `tool` message with the matching `tool_call_id` and a fake weather result.

Result: **HTTP 200, `finish_reason=stop`**, and a grounded final answer that
uses the tool result ("Temperature: 18°C … Partly cloudy"), with a fresh
`<think>` block. MiniMax-M3 accepts its own `<think>` history verbatim through
our gateway — the deepagents#1630 failure class (reasoning stripped or rejected
on resend) does not occur on this stack. 588 tokens.

## What was changed because of the probes

1. **Defensive id synthesis** (`gateway/app/providers/openai.py`,
   `_ensure_stream_tool_call_ids`): MiniMax supplies ids today, but
   deepagents#3587 puts the omitted-id fix on gateways — opening tool-call
   deltas arriving without an id now get a stable `call_lqgw_<uuid>_<idx>`;
   provider ids and continuation deltas are never touched. Unit-tested with
   the live MiniMax wire shape.
2. **`use_responses_api=False`** pinned in `build_gateway_chat_model`
   (deepagents#3190 — Responses-API auto-detect breaks OpenAI-compatible
   endpoints).
3. **`profile={"max_input_tokens": 200_000}`** on the gateway-injected model:
   unprofiled models get deepagents' fixed 170k-token summarization trigger;
   profiled models get a window-relative 0.85× trigger. **Research-doc
   correction**: MiniMax-M3's native window is 1M tokens (not <170k as
   `deepagents-ecosystem.md` §1.2 implied). 200k derives from the gateway's
   DECLARED request cap (`request_validation.max_total_request_chars` = 1e6
   chars ≈ 250k tokens) — note honestly: that cap is config-only today
   (nothing in `gateway/app` enforces it), so 200k is a conservative
   operating point under the declared envelope, not an enforced ceiling.
   It also changes the post-compaction KEEP policy for all agent runs
   (fraction-of-window 0.10 instead of last-6-messages) — intended.
4. **MiniMax-M3 harness profile** registered (empty baseline, by design) under
   `openai:{smart,fast,budget}` — `api/app/agents/profiles.py`.
5. **langgraph floor → `>=1.2.4`** (`api/pyproject.toml`, deepagents#2781).

## Conformance verdicts for the matrix (MiniMax-M3 row, serving layer)

- L0 streamed tool-call frames: structural, ids stable — PASS (live)
- L0 reasoning round-trip (delta + history): PASS (live, both directions)
- Responses-API hazard: neutralized by explicit pin
- Token spend for both probes: ~1.1k tokens (≈ $0.001)

## Post-deploy verification (rebuilt images, slice code live)

After the slice's gateway/api changes were deployed (all four touched
services rebuilt), both probes re-ran against the NEW gateway:

- probe 1: `finish_reason=tool_calls`, provider id
  `call_function_0lqzsu9i099o_1` passed through UNTOUCHED — the stateful
  id-synthesis never rewrites provider ids (raw SSE:
  `gateway-probe1-postdeploy.sse`)
- probe 2: HTTP 200, grounded continuation — history round-trip intact

Plus an N=1x4 post-deploy spot-check through the full harness
(`results-postdeploy/`): 4/4 completed, metrics consistent with the N=20
baseline (which ran on pre-slice images — see provenance note in
`docs/fork/model-compatibility.md`).
