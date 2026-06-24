# C5b-1 — the comment-wipe fix (live evidence)

ADR-F032 (C5a) + the C5b-1 fix. The C5a negotiation loop shipped with a **document-level**
gap: when the agent *replied* to a counterparty comment **and** accepted/rejected the change that
comment was anchored to, Adeu deletes the whole comment thread — **silently wiping the reply** while
reporting the action as `applied`. C5a's count-based reconciliation missed it; only raw-OOXML
inspection revealed it (the lesson this evidence re-applies).

C5b-1 closes it with three code layers (no migration / endpoint / dep):
- **anchor-map capture** — `read_state_of_play` records `comment_anchors: {Com:N → Cn}` from the
  CriticMarkup meta block (a `[Com:N]` token co-occurring with a change's `[Chg:N]` lines);
- **upfront anchoring gate** (`schemas.commercial.evaluate_anchoring`) — a `reply` on a comment
  anchored to a change being **accept/reject**-ed is rejected *before any write*, with a message
  telling the model to counter the change or leave the comment open instead;
- **document-level reply-survival reconciliation** (`negotiation_service.apply_decisions`) — re-reads
  the output and proves every reply we made still exists; any wiped reply → reject, persist nothing.

The model is also *taught the coupling up front*: `extract_counterparty_position` annotates an anchored
comment ("anchored to change Cn — accepting/rejecting Cn removes this thread; counter Cn instead").

## Live re-run (DeepSeek `deepseek` = deepseek-v4-flash), `negotiation-report.json`

- `status: completed`, `step_count: 25`, `model_turns: 9`, `latency_s: 84.6`.
- `tools_called`: `extract_counterparty_position` → **`respond_to_counterparty` ×4** → `update_matter_memory`.
  The **four** respond calls are the proof the gate bit: the agent first tried *reply + reject* on the
  mutuality-swap change (whose comment is "this should stay mutual"); the anchoring gate **refused it**
  (no silent reply loss), and the agent adapted.

## The decisive check — raw OOXML of the produced `.docx`

| Part | C5a bug (before) | C5b-1 (this run) |
|---|---|---|
| `word/comments1.xml` | counterparty comment **deleted** (only the agent's surviving counter-comment remained) | counterparty comment **survives**: *"We act for both sides equally — this should stay mutual."* |
| agent reply | written then **silently wiped** by the reject | **none written** — the gate steered the agent to record its position via leave_open/escalate instead of a reply that would vanish |

`document.xml` of the response: the only pending tracked change is `[-three (3) years from the date of
disclosure-][+perpetuity+]` (Opposing Counsel) — the **below-floor demand escalated, left visible, not
conceded**. The one-sided swap was **rejected** (reverted to mutual, cleanly). C1 ("in writing")
accepted; C3 (affiliates carve-out) handled. Full coverage held in-tool.

**Honest nuance (recorded for C5b-2 craft, not a silent loss):** because the agent *rejected* the
commented change, the counterparty's comment is preserved in the package but **orphaned** (its in-body
anchor range is gone — `commentRangeStart/End/reference = 0`), so Word may not render it. The *ideal*
move is to **counter** the swap (which keeps the original change + its thread anchored) and then reply —
both visible. Coaching the agent to prefer counter-with-reply over reject-then-leave-open when there is
a comment to engage is C5b-2 (the `negotiation-review` skill). C5b-1's guarantee — **the agent never
silently loses a reply it wrote, and a comment is never silently dropped** — holds: the gate prevents
the wipe combination, the reconciliation backstops it, and every comment decision is recorded
(audit + matter-memory receipt).

## Files
- `Mutual NDA (counterparty markup).docx` — seeded counterparty markup (input).
- `Mutual NDA (counterparty markup) (response).docx` — the agent's response (comment survives).
- `counterparty-state-of-play.txt` — the markup as the agent reads it.
- `response-reconstruction.txt` — readable `[-del-][+ins+]` view (perpetuity left as a tracked change).
- `negotiation-report.json` — the run receipt (4 respond calls = the gate adapting).
