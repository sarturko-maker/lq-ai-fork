# C5b-2 — the `negotiation-review` skill + binding + craft eval (live evidence)

ADR-F032 (the C5a/C5b negotiation loop) + ADR-F041 (craft = prompt quality tuned by eval, **not** a
runtime gate). C5b-2 ships the **craft layer** on the round-2 negotiation loop:

- **`skills/negotiation-review/SKILL.md`** — the round-2 companion to `surgical-redline`. It teaches the
  agent to decide every change/comment, counter a one-sided edit **surgically** (term-swap, not a
  wholesale rewrite — the C9 mutualisation lesson), **prefer counter-with-reply over reject-then-orphan**
  (the C5b-1 nuance), accept benign clarifications, and **escalate below-floor demands** rather than
  conceding them. It *teaches*; the code (`evaluate_coverage` / `evaluate_anchoring` / `evaluate_gate` +
  reconciliation) *enforces*.
- **Migration 0072** binds the skill to Commercial (idempotent `NOT EXISTS`) and refreshes the stale 0066
  negotiation doctrine paragraph (it predated the C5a tools) to point at `extract_counterparty_position` /
  `respond_to_counterparty` + the skill + the full taxonomy (never-clobber `REPLACE`, mirroring 0067).
- **A provider-marked craft eval** (`api/tests/agents/scenarios/test_commercial_negotiation_eval.py`) —
  a plain task (states our position, NOT the per-item verdicts) drives the **bound** skill; a judge grades
  the produced `.docx` for craft. Per ADR-F015 the craft rate is a **finding**, never a hard gate.

## Judge note (read this)

The C9 eval used Claude (Opus 4.8) as judge. On **this** local gateway Claude is **not reachable**
(`ANTHROPIC_API_KEY` is unset; there is no `claude` alias — only DeepSeek has quota). So the automated
judge ran on **`deepseek-pro`** (deepseek-v4-pro, the stronger DeepSeek tier), and the **authoritative
craft assessment below is Claude Opus 4.8 reading the produced artifacts directly** (as C9's `verdicts/`
were actually authored). The two judgements **agree** on every rep — the deepseek-pro verdicts in
`eval/repN-verdict.md` accurately describe the `.docx` (verified against `eval/repN-response.txt`).

## Live run — `eval/eval-report.json` (agent `deepseek` = deepseek-v4-flash, judge `deepseek-pro`, 3 reps)

| rep | status | model turns | respond calls | mutuality restored | floor held | counter-with-reply | craft pass |
|---|---|---|---|---|---|---|---|
| 1 | completed | 14 | 7 | ✅ | ✅ | ❌ | ✅ |
| 2 | completed | 14 | 7 | ✅ | ✅ | ❌ | ✅ |
| 3 | completed | 10 | 4 | ✅ | ✅ | ❌ | ✅ |

**Substantive craft: 3/3.** Every rep (see `eval/repN-response.txt`):

- **§3 one-sided strip → reverted to mutual, surgically.** The counterparty's
  `Each party shall protect the other party's` → `The Recipient shall protect the Discloser's` swap is
  reverted to the exact original mutual wording — only the party terms move, the obligation verb phrase
  stays bare. Mutuality restored without a wholesale rewrite.
- **§4 below-floor perpetuity → held at the floor, never conceded.** `three (3) years` → `perpetuity` is
  reverted (reps 1–2, a clean `reject`) or countered back to three years as a **visible** tracked change
  (rep 3) — the floor term is preserved, nothing silently accepted.
- **§2 benign `in writing` clarification → accepted.** Full coverage; nothing silently dropped.
- `respond_calls` **7 / 7 / 4** is the **gate adapting**: the agent's reply+reject attempts were refused
  (`WARNI counterparty response apply failed` — the C5b-1 anchoring gate / coverage gate), and it
  re-decided until every item was covered and no reply sat on an accept/reject change.

**Counter-with-reply: 0/3 — an honest tuning finding (recorded, not a blocker).** On `deepseek-flash` the
agent **reverts** §3 (a `reject` to the agreed original) rather than **countering** it, so the
counterparty's `Com:1` ("…this should stay mutual") is **preserved but orphaned** — the reply attempts
seen in the run log (`Adding comment … parent_id=1`) were refused by the anchoring gate when paired with
the reject, and the final `.docx` carries no reply to `Com:1` (rep 3 adds its *own* rationale comment
`Com:2` on the §4 counter, still not a reply to `Com:1`). This is the C5b-1 nuance playing out live:

- **The guarantee holds.** The comment is never silently dropped, and a reply is never silently lost —
  the gate refused the unsafe combination and the agent adapted to a correct outcome (ADR-F032/C5b-1).
- **The ideal is not yet driven.** The skill coaches *counter §3 + reply to `Com:1`* (keeps the thread
  anchored and visibly answered) over *revert §3* (cleaner doc, orphaned comment). At n=3 on
  deepseek-flash the model prefers the clean revert — substantively correct, but not the courteous
  engaged move. Reverting to the agreed original is itself defensible craft (it restores exactly what both
  sides signed), which is why this is a *tuning* signal, not a defect.

Per ADR-F015 + the C9 precedent (a craft fix can't be verified at low n → defer to backlog), the
counter-with-reply nudge is a **backlog tuning item**, not a fix to land in this slice. The skill already
carries the coaching (`skills/negotiation-review/SKILL.md` § "Engage the comment — don't orphan it"); the
finding is that deepseek-flash under-follows it on the revert-vs-counter choice.

## Files

- `eval/eval-report.json` — the aggregate run receipt (3 reps; agent + judge aliases; per-rep verdicts).
- `eval/counterparty-view.txt` — the counterparty markup as the judge sees it ([-del-][+ins+] + comment).
- `eval/repN-response.txt` — our response per rep (reconstruction + comment threads — the judge's view).
- `eval/repN-verdict.md` — the deepseek-pro judge's verdict per rep (concurred with by Claude Opus 4.8).

## How it was produced

```
DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... S3_*=... \
LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_JUDGE_MODEL=deepseek-pro \
LQ_AI_NEGOTIATION_EVAL_REPS=3 LQ_AI_SKILLS_DIR=/repo/skills \
UX_B1_EVIDENCE_DIR=/repo/docs/fork/evidence/c5b2 \
pytest -m provider tests/agents/scenarios/test_commercial_negotiation_eval.py -s
```

When `ANTHROPIC_API_KEY` + a `claude` alias return to the gateway, set `LQ_AI_JUDGE_MODEL=<claude-alias>`
to run the judge on Claude directly.
