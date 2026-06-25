# C5b-3 — inline `data-deal-change` live verdict chips (live evidence)

ADR-F032 (the C5a/C5b negotiation loop) + ADR-F024 (the run-scoped change-ledger seam, now
generalised) + ADR-F004 (render-determinism: the chip is best-effort animation; the saved response
`.docx` + run timeline are the record). C5b-3 ships the **live signal** on the round-2 negotiation
loop: as the Commercial agent responds to a counterparty's marked-up contract, the cockpit flashes a
transient **verdict chip per item** inline in the conversation — "C1 · accepted", "C3 · countered",
"Com:1 · escalated" — so the lawyer *watches the negotiation round happen*.

This **clones the `data-ropa-change` seam** (PRIV-9b): a run-scoped ledger → runner drain at each
`tool_result` → transient `data-*` SSE frame → web parse → render. The one divergence: ropa washes a
register row in a co-visible panel; Commercial has no deal-terms panel, so the chip renders **inline in
the conversation** (`ConversationPanel`). The seam was generalised (a `LiveChange` / `ChangeLedger`
Protocol) so the runner drain is area-agnostic — `RopaChange` and the new `DealChange` each publish
themselves. No new dependency / endpoint / migration / gate change.

The frame carries only `{ref, verdict}` — audit-safe (a synthetic decision ref + a closed-taxonomy
enum, never raw clause text).

## Live integration — `deal-change-frames.json` (DeepSeek, the REAL agent end-to-end)

The provider-marked `test_commercial_deal_change_frames_live` subscribes a `RunStreamBroker` BEFORE the
run (the frames are transient — a late subscriber misses them), drives the real negotiation loop on the
counterparty NDA, and captures the `data-deal-change` frames published onto the run stream. This proves
the integration link the deterministic tests can't: **the live agent's `respond_to_counterparty` call →
ledger record → runner drain → publisher → frame.**

5 frames fired in one round (82 s, DeepSeek):

| ref | verdict |
|---|---|
| C1 | accept |
| C2 | reject |
| C3 | accept |
| C4 | escalate |
| Com:1 | leave_open |

Each frame is `transient: true`, carries a `ref` + a taxonomy `verdict`, and **no clause text** — exactly
what the cockpit renders as a chip.

## Browser render — `cypress/` (deterministic, light + dark)

`web/cypress/e2e/c5b3-deal-change.cy.ts` drives the REAL chip code path in the REAL browser: a Commercial
matter is opened and the run stream is intercepted with a real `data-deal-change` SSE body (one frame per
verdict tone). The chips render inline per ref, coloured by verdict:

- **accept** → green (positive / `--color-status-completed`)
- **counter** / **reply** → blue (info / `--color-status-running`)
- **reject** → red (negative / `--color-status-failed`)
- **escalate** → amber (warning / `--color-status-attention`)
- **leave_open** → neutral (`--color-status-cancelled`)

`cypress/c5b3-deal-change-light.png` + `-dark.png` — the five chips (C1 accepted / C2 countered / C3
rejected / C4 escalated / Com:1 replied) inline under the running turn, both themes, correct contrast.

The chips persist across stream re-opens (the poll re-delivers the transient frames every 2 s, resetting
the 6 s decay) and reset on a run change / thread switch / decay — a dropped frame loses a chip, never
data (ADR-F004).

## Deterministic test chain (CI, every link)

- `api/tests/agents/test_deal_changes.py` — the ledger drain (FIFO, once-each, cursor).
- `api/tests/agents/test_agent_stream.py` — `deal_changed` emits a transient frame + is not seeded to
  late subscribers.
- `api/tests/agents/test_agent_stream_redis.py` — the frame survives the cross-process round-trip.
- `api/tests/agents/test_agent_runner.py` — the runner drain seam is area-agnostic (`change.publish`).
- `api/tests/agents/test_commercial_tools.py` — `respond_to_counterparty` records one verdict per
  decision on success, and records **nothing** on a rejected round.
- `web/.../agents/__tests__/run-stream.test.ts` — `parseDealChangePayload` (ref + verdict load-bearing,
  unknown verdict rejected) + the label/tone presenters.

## How it was produced

```
# live integration frames (DeepSeek):
DATABASE_URL=... LQ_AI_GATEWAY_URL=http://gateway:8001 LQ_AI_GATEWAY_KEY=... S3_*=... \
LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_SKILLS_DIR=/repo/skills \
UX_B1_EVIDENCE_DIR=/repo/docs/fork/evidence/c5b3 \
pytest -m provider tests/agents/scenarios/test_commercial_deal_change_live.py -s

# browser chips (rebuild the prebuilt `web` container first):
cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
  --spec 'cypress/e2e/c5b3-deal-change.cy.ts' --env LQAI_ADMIN_PASSWORD=...
```
