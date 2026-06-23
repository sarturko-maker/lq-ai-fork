# F043 — Matter-memory consolidation as a gateway-routed, supersede-only agent tool

- Status: proposed (2026-06-23, with slice C3b-2 — the consolidation/Lint egress slice that builds on it)
- Date: 2026-06-23
- Relates: ADR-F042 (unit-of-work auto-write-then-correct — the tier this consolidates; its §C3b obligation
  lands here), ADR-F010 (gateway-only egress + no direct provider — the obligation this slice discharges),
  ADR-F018 (code-validated agent writes — validate-before-commit, reused), ADR-F026 (agent-run budget/timeout —
  what bounds invocation count), ADR-F005 (audit contract: counts/types/IDs, never raw values), ADR-F002 (the
  practice area IS the agent — area-agnostic grant).
- Milestone: COMMERCIAL — matter-memory track (C3a ✓ / C3b-1 ✓ / **C3b-2** / C3c). **Accept with C3b-2.**
- Research: `docs/fork/research/matter-memory-patterns.md`, `docs/fork/research/matter-memory-reuse.md`.

## Context

C3a gave the matter a prose wiki (auto-write) and C3b-1 a dated, supersede-able typed **fact ledger** — both
**zero model calls**. As a live matter runs, the ledger drifts: facts duplicate, a later fact contradicts an
earlier one, some go stale, and the wiki falls behind. ADR-F042 §C3b always intended an **automated
consolidation/Lint pass** (the ported mem0 ADD/UPDATE/DELETE/NOOP loop + the Karpathy/OpenClaw "Lint" for
contradictions/stale/orphans) to keep the memory honest.

This pass is the **first matter-memory code to call a model**, so it is where the ADR-F042 §C3b / ADR-F010
**egress obligation lands** (every model call through the gateway; no direct provider) — and where a **cost
posture** must be chosen, because it is also the first *agent* tool to spend gateway tokens inside one tool
call (every agent tool's R4 cost brake is a documented no-op until F1's per-run budgets). The matter has tens
of facts, so the set loads **whole** — no retrieval, no embeddings (the gateway `/v1/embeddings` is 501 until
B6). The maintainer split C3b precisely to review this egress slice in isolation (C3b-1 was the model-free
store; C3b-2 is the egress), and chose, via AskUserQuestion, the four options below.

## Considered Options

**1. Trigger — how does the consolidation pass fire?**
- A. **In-run guarded agent tool (chosen).** The agent calls `consolidate_matter_memory` during a run; it runs
  through `guarded_dispatch` like every other tool. No new infrastructure; an agent tool needs a live run, and
  no post-run/cron hook exists in the fork today.
- B. Background cron / scheduled worker. Deferred (backlog) — eventual-consistency autonomy is a later upgrade;
  it needs a scheduler the fork does not yet have and a careful re-entrancy story.

**2. Scope — what may the pass write?**
- A. **Facts + wiki (chosen).** Consolidate the typed ledger AND rewrite the prose one-pager in the one tool —
  the full ADR-F042 §C3b intent; the wiki and ledger stay consistent in a single atomic pass.
- B. Facts-only (leave the wiki to the agent's own `update_matter_memory`). Considered (tighter first egress
  slice) but rejected by the maintainer — splitting the rewrite across two tools risks a ledger/wiki skew.

**3. Mutation primitive — how may a fact change?**
- A. **Supersede-only (chosen).** The pass may only close a fact's window (`retire` ⇒ set `invalid_at`, no
  replacement; `replace` ⇒ insert ONE new consolidated fact, then set each superseded prior's
  `invalid_at` + `superseded_by`). A corrected statement is a NEW fact. Full bi-temporal history is preserved —
  the "what did we believe at signing" guarantee stays intact; one mutation primitive to reason about.
- B. In-place fact-body `UPDATE` (the literal mem0 op). Rejected — overwriting `body_md` loses the edit history
  and muddies the bi-temporal model (an "edited" fact no longer reflects what was recorded).

**4. Cost — how is the in-tool gateway spend handled?**
- A. **Match the existing R4-no-op posture + gateway-routing-log audit (chosen).** Keep R4 a no-op (as for
  every agent tool today); bound the call **structurally** — exactly ONE gateway call per invocation + a hard
  `max_tokens` cap; the spend is recorded in the routing log under `lq_ai_purpose="consolidate_matter_memory"`
  (auditable); the agent's ADR-F026 step/time budget bounds how often it can be invoked. Per-run $ budgets stay
  F1's job. Consistent with the current architecture; introduces no one-off cost mechanism.
- B. A bespoke per-tool guard now (refuse if the live fact set exceeds N rows; cap invocations per run).
  Rejected — duplicates the F1 per-run-budget work with a one-off mechanism ahead of it.

## Decision Outcome

Adopt **1A + 2A + 3A + 4A**. C3b-2 ships **one in-run guarded agent tool**, `consolidate_matter_memory`,
granted to **every** matter-bound run (any practice area), with a grant set disjoint from the matter-memory /
fact-ledger / ROPA / assessment / commercial grants (confinement). One invocation:

- **Loads** the matter's live `kind='fact'` rows whole (`live_facts`), the wiki (`projects.context_md`), and the
  pinned corrections (`load_pinned_corrections`). **0 live facts ⇒ no gateway call** (a free lower bound on
  egress) + a benign receipt.
- **Routes ONE gateway chat completion** via `GatewayClient.chat_completion` under
  `lq_ai_purpose="consolidate_matter_memory"` (registered in the gateway `_KNOWN_PURPOSES`), `max_tokens`
  capped, `anonymize=False` (the pass must judge the REAL fact text — equivalence/contradiction over masked
  text is impossible; same posture as the playbook extractor; the gateway is still the sole egress and
  key-holder). **This discharges the ADR-F010 egress obligation:** the tool's only model access is the injected
  `GatewayClient` — no provider SDK, no `api.openai.com` (asserted by a unit test on the call + a static
  egress-guard test on the module source).
- **Validates** the untrusted model output against `ConsolidationResult` (reject-not-truncate), then a **pure
  second pass** checks every op id is a **live `kind='fact'` row of THIS matter**, no id is referenced twice,
  and a `replace`'s `valid_from` post-dates each fact it supersedes — **before any write**.
- **Applies all-or-nothing, supersede-only:** any reject path leaves the matter untouched; on success it closes
  the superseded facts' windows (never deletes, never edits a body in place) and, if the wiki changed,
  snapshots the prior + rewrites it (the C3a `snapshot_and_rewrite_wiki` helper, single-sourced).
- **Pinned corrections are immutable to the loop — structurally.** They are passed as read-only ground truth and
  are never in the op space (the live-`kind='fact'` id validation makes a correction id unreachable), so
  ADR-F042's no-fabrication + no-overwrite (B2) both hold without relying on prose. A gateway failure becomes a
  reject-and-retry string, not a crash (an `asyncio.CancelledError` still propagates so a wall-clock cancel is
  honoured).
- **Receipt + audit:** the tool returns a counts summary (+ the model's `lint_notes`) to the agent; the
  guard's own envelope records `tool`/`outcome`/`result_chars` only — **never a fact/wiki body** (ADR-F005).

## Consequences

- **Egress + audit honoured:** every consolidation model call goes through the gateway under a dedicated,
  filterable purpose; the audit envelope leaks no matter text. The gateway `_KNOWN_PURPOSES` frozenset is read
  at module load, so **the gateway must be restarted** to recognise the new purpose (covered by the standard
  api+workers+**gateway** rebuild after the slice).
- **History preserved:** supersede-only means the bi-temporal ledger and the as-of query (`facts_valid_at`)
  stay correct after an automated pass — a consolidated-away fact is still reconstructable as-of any past date.
- **Cost is bounded but not budgeted here:** the in-tool token spend is invisible to R4 until F1 (mitigated — one
  bounded call per invocation, capped tokens, audited at the gateway under the purpose; the agent's ADR-F026
  budget bounds invocation count). Per-run $ budgets remain F1's slice.
- **No migration / no new dependency:** reuses the `0070` typed-fact columns + `projects.context_md`; the new
  code is one agent-tool module + schemas + a shared wiki helper extraction.
- **Deferred (C3c / backlog):** background-cron autonomy (1B); matter-scoped read tools / REST / cockpit memory
  panel + undo endpoint (C3c); structured Citation-Engine references (prose `source_citation` only); embedding /
  vector retrieval (the whole-set load suffices at our scale; gateway embeddings 501 until B6).
- **Licence/SBOM:** zero new dependencies; the consolidation prompt is ported convention/pattern from the
  MIT/Apache-2.0 sources recorded in the research memos (no code vendored; no NOTICES.md entry required).
