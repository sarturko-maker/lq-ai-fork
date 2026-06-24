# F032 — Negotiation rounds: counterparty extraction + the no-silent-action gate

- Status: proposed
- Date: 2026-06-24
- Deciders: maintainer (Arturs), agent
- Slice: C5a (provable core of the commercial milestone's C5)

## Context

After the commercial agent reads, reviews, redlines, and remembers a deal (C1/C2/C4/C8/C3) and
the lawyer downloads the redline (C7a), the missing capability is the **second round**: the
counterparty returns a *marked-up* `.docx` — their tracked changes plus Word comments — and the
agent must respond to **every** change and **every** comment. The maintainer set the load-bearing
requirement: *"how do we know the agent never silently accepts or rejects, and that everything it
does is either a tracked change, or a comment in the right place, or a reply to a comment in the
right place?"* That completeness property — not the mechanics of reading/writing markup — is the
hard part.

Two findings shaped the design (both verified before coding):

1. **Adeu 1.12.1 does the OOXML read/write natively** (confirmed live on the pin). Read:
   `extract_text_from_stream(stream, clean_view=False)` → CriticMarkup with stable `Chg:N` ids +
   authors; `engine.comments_manager.extract_comments_data()` → `Com:N` with author/text/date/
   `resolved`/`parent_id`. Write: `engine.apply_review_actions([AcceptChange | RejectChange |
   ReplyComment])` and `ModifyText(target, new, comment=…)` for a counter, both returning
   `(applied, skipped)` with failures in `engine.skipped_details`. So we build no OOXML walkers,
   comment writers, or anchoring code.
2. **The prior-art project `Claude-Plugin-MCP`** (the maintainer's, MIT) decomposes this exact
   problem and its *concepts* transfer — a closed action taxonomy, the layer-don't-reject
   invariant, a per-id "state of play" — but its Adeu calls are an older API, and, critically, it
   **does not solve the completeness guarantee**: it leaves "address every change" to the prompt +
   a human eyeball (no coverage pass; its `no_action` is a literal silent drop; its output
   validator only checks the file opens in Word). The code-enforced guarantee is therefore the
   net-new piece this slice owns.

C6 (controlling playbooks) and its severity-scale reconciliation (F036) are not built, so C5a does
**not** touch the `PlaybookPosition` mechanism — the agent classifies against the **prose** house
positions the bound review skills already carry.

Scope (maintainer, locked): split — **C5a is the provable backend core**; deferred to **C5b** are
the `negotiation-review` skill calibration, the inline live verdict chips (a `data-deal-change`
clone of the `data-ropa-change` seam), and a multi-round Claude-judged eval.

## Considered Options

1. **Two guarded tools + a two-phase code-enforced coverage/reconciliation gate** (chosen). A
   deterministic read tool builds a `StateOfPlay` checklist (every `Chg`/`Com` ref); a write tool
   requires exactly one decision per ref (upfront), applies via Adeu, and re-reads the output to
   prove every decision landed (`applied`, not `skipped`).
2. **Prompt-only completeness** (the prior art's approach): a skill instructs "address every
   change" and a human reviews. Rejected — it makes the guarantee depend on model compliance,
   exactly the failure the maintainer asked us to close; "never silently" cannot rest on a prompt.
3. **A persisted negotiation-round entity** (tables for positions/rounds with a status workflow).
   Rejected for C5a — heavier schema + UI than the guarantee needs; matter memory (facts) +
   documents already carry round-to-round state (the decomposition's non-goal), and a structured
   entity can come later if the workflow demands it.

## Decision Outcome

**Chosen: option 1.** Two guarded agent tools on the commercial area, model-judges / code-disposes
(ADR-F018):

- `extract_counterparty_position(document_name)` — deterministic, **no model call** (ADR-F010):
  fetch the matter `.docx` (owner+matter scoped via `_matter_files_query`, 404-conflated), read it
  via Adeu into a `StateOfPlay`, and return a numbered checklist tagged `provenance=counterparty`.
  The returned markup is **untrusted model input** — framed explicitly as the other side's *text*,
  never instructions (prompt-injection boundary).
- `respond_to_counterparty(document_name, decisions)` — guarded write. Closed taxonomy: a change is
  `accept | reject | counter | leave_open | escalate`; a comment is `reply | leave_open | escalate`.
  **Layer-don't-reject**: a reject leaves a recorded tracked change, a counter is a surgical
  `ModifyText` (held to the same D1–D6 gate as `apply_redline`) layered over theirs.

**The no-silent-action guarantee is two-phase, in code:**

- **Upfront coverage gate** (`evaluate_coverage`, model-free) — re-extracts the `StateOfPlay` as
  ground truth (not the model's view) and requires **exactly one decision per `Chg`/`Com` ref**: a
  missing ref (a silent accept) → reject; unknown/duplicate ref → reject. Collect-all-errors, before
  any mutation.
- **Post-write reconciliation** (`apply_decisions`) — every decision becomes an Adeu action whose
  `(applied, skipped)` is checked: any `skipped` (or an under-applied counter) → reject and persist
  nothing; the output must also re-read cleanly. Silent-accept fails upfront; silent-reject is
  impossible (a reject is a recorded `RejectChange`).

`leave_open` / `escalate` make **no document mutation** — they are recorded decisions (the audit row
+ a matter-memory receipt fact), so an item is never silently dropped, and a below-floor demand is
escalated, never silently conceded. The response `.docx` is persisted as a matter `File` with
`created_by_run_id` (downloadable via C7a).

Reuse, not rebuild: Adeu for read/write; the existing surgical gate (`schemas/commercial.py`) +
word-diff (`redline_service.word_diff_edits`, ADR-F045, extracted to a module function) for
counters; `created_by_run_id` (migration 0071). **No migration, no new HTTP endpoint, no new
dependency.**

## Consequences

- **Good:** the "agent never silently accepts/rejects" property is now auditable the way the D1–D5
  redline gate makes over-rewording auditable — a code invariant, prompt-independent. The guarantee
  holds even with a thin prompt (proven by the C5a tests + live run before C5b's skill lands).
- **Good:** small surface — two tools + one adapter over Adeu's native API; no OOXML/comment code of
  our own.
- **Adeu-imposed limits (recorded for backlog):** there is no public "pure margin comment on a range
  with no edit" — C5a anchors comments to a change/counter, and `accept`/`reject` carry their reason
  in the receipt rather than a Word comment (a comment-on-accept needs the pure-comment helper).
  Per-revision *dates* are not in Adeu's projection. Accepting a counterparty change deletes the
  comment thread anchored to it (correct: the acceptance resolves their comment), so reconciliation
  trusts Adeu's applied/skipped counts rather than re-counting threads.
- **Deferred (C5b):** the negotiation skill calibration (materiality/authority zones/worked
  examples), the inline live signal, and a multi-round eval. **Deferred (C6/F036):** structured
  `PlaybookPosition` classification — C5a uses prose positions.
- **Counter-anchoring is gated against the counterparty's "final ask"** (the accept-all view), with
  the post-write reconciliation as the backstop if a target does not anchor.
