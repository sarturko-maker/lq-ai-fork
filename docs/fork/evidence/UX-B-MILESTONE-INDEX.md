# UX-B — milestone index: "Deep Agents truly work / cockpit perfect"

The closing map for the **UX-B** milestone (capability convergence — the gate for the agentic-**modules** /
Oscar-Privacy direction). It ties the six slices together and records, in one place, the **honest state of
the loop**: what a tier-4 model (MiniMax-M3 — the only S9-qualified provider today) *does* and *does not* do
across areas, skills, and delegation, and what the cockpit now shows. Compiled in **UX-B-6** (the verify +
consistency sweep) from the committed per-slice evidence; nothing here is aspirational.

Governing decision: **ADR-F015** (scenario-based qualification is the gate — a committed behavior report,
never a model pass/fail CI gate; nothing ships `configured`/activated until the report shows M3 handles it;
findings are kept verbatim, never tuned green). Design language: **ADR-F012/F013**.

## Slice trail

| Slice | PR | What shipped | Evidence |
| --- | --- | --- | --- |
| UX-B-0 | #89 | ADR-F015 accepted + UX-B decomposition (docs) | `docs/adr/F015-*`, `docs/fork/plans/UX-B-*` |
| UX-B-1 | #90 | Scenario harness + Commercial baseline (test infra, no `app/` change) | [`ux-b-1/`](ux-b-1/behavior-report.md) |
| UX-B-2 | #91 | Default profiles for Disputes / M&A / Privacy / Employment (migration 0055) | [`ux-b-2/`](ux-b-2/README.md) |
| UX-B-3 | #92 | Skills activation — registry-backed read-only backend, ADR-F016 (migration 0056) | [`ux-b-3/`](ux-b-3/README.md) |
| UX-B-4 | #93 | Live `document-researcher` subagent — per-subagent skill sources, ADR-F017 (migration 0057) | [`ux-b-4/`](ux-b-4/README.md) |
| UX-B-5 | #94 | Cockpit web — area-pick at creation + delegation boundary + read-only area config (web-only) | [`ux-b-5/`](ux-b-5/README.md) |
| UX-B-6 | (this) | Verify + consistency sweep; this index | (this file) |

## Cross-slice consistency check (UX-B-6 — verified against the live dev DB, read-only)

The claims the milestone rests on, re-verified at the close (a `SELECT` against the dev Postgres — never an
`alembic upgrade`, never `down -v`):

- **All 5 areas configured + profiled.** `commercial`, `disputes`, `m-and-a`, `privacy`, `employment` all
  carry a non-empty `profile_md` and `configured = true` (the derived `_is_configured` is the source of
  truth the API list + the matter-creation gate read). Migrations **0054** (Commercial) + **0055** (the
  other four).
- **Tier floors NULL for every area.** MiniMax-M3 is the only S9-qualified model (tier 4); any floor > 4
  fails `tier_below_minimum`, a floor of 4 is redundant. Operators set one via the admin PATCH once a
  stronger model qualifies (the 0054 rationale, held).
- **Skills bound per area** (migration **0056**, focused subsets — not the catalogue): Commercial 4
  (`contract-qa`, `msa-review-commercial-purchase`, `msa-review-saas`, `nda-review`), Disputes 2
  (`action-items-from-client-alert`, `contract-qa`), M&A 3 (`contract-qa`, `contract-snapshot`,
  `nda-review`), Privacy 3 (`contract-qa`, `dpa-checklist-review`, `vendor-privacy-policy-first-pass`),
  Employment 3 (`action-items-from-client-alert`, `contract-qa`, `nda-review`).
- **One live subagent** (migration **0057**): Commercial's `document-researcher`, with skills
  `[contract-qa, nda-review]` — a true **⊆** of Commercial's 4 bound skills (the ADR-F017 subset rule holds
  in stored data, not just at PATCH time). No other area carries a subagent (`agent_config = '{}'`).
- **Cockpit surfaces the loop honestly** (UX-B-5): the area picker offers only configured areas; the
  delegation boundary renders only when a `task` step exists; the area-config disclosure shows what the
  agent *can* do (its configured skills/subagents), never a promise of what it will do.

Every claim matched the database. No drift between the docs and the running stack.

## The honest behaviour map (MiniMax-M3, tier-4-weak)

Live runs are **non-deterministic** — step counts / tool choices vary run to run, and that variance is
itself the tier-4 observation. The **final-answer excerpt** in each per-slice report is the authoritative
record; the `shape_matched` column is a coarse substring+step-bound heuristic, not a verdict. Scenario
totals below are the committed snapshots.

### What M3 does well (consistent across all 5 areas)

- **Grounds + cites.** On a direct fact it reaches for `search_documents` (often then `read_document`) and
  answers with the document name + page/section — it does not invent. (UX-B-1 single-tool fetch; every
  UX-B-2 area's grounded scenario.)
- **Declines honestly.** Asked to do something it has no tool for (delete + email; issue/serve a claim;
  sign + wire funds; terminate + email) it states its inability and the governance reasons — it never fakes
  a confirmation. (UX-B-1 guard/refusal; the refusal scenario in each UX-B-2 area.)
- **Answers general questions directly** when told not to consult documents — it doesn't burn a tool call it
  was told to skip. (UX-B-1 no-tool-needed.)
- **Clarifies an ambiguous referent** rather than guessing, for 3 of 4 UX-B-2 areas — the calibrated profile
  sentence ("ask one brief clarifying question before guessing") is visibly echoed.

### What M3 does *not* do reliably (the calibration findings — kept verbatim, ADR-F015)

- **Multi-step efficiency is inconsistent.** On some grounded fetches it issues a redundant second
  `search_documents` / `read_document` before answering, pushing past the soft step bound. The answer is
  still correct and cited; the finding is *over-exploration*. (UX-B-1, UX-B-2, UX-B-4 single-fact 7-vs-6
  step "miss".)
- **A broad ask over a large skill surface can fail to converge.** With skills on, a focused review grounds
  + cites cleanly, but a broad "structured risk review" prompt led M3 to read multiple `SKILL.md` files and
  spend its whole step budget without producing a deliverable (`cap_exceeded`, 16 steps). Skills are wired
  correctly; the bigger surface gives a tier-4-weak model more room to wander. (UX-B-3: 1/2 completed.)
- **It does not *elect* to delegate at small matter sizes.** Given a 4-document RFQ review with a
  `document-researcher` available, M3 read all four documents itself and produced a structured comparison —
  `task_calls=0`, no fan-out. This is *reasonable* (four short docs fit one context); delegation earns its
  keep on genuinely large matters. The delegation plumbing is proven **deterministically in CI**
  (`test_subagent_delegation_nests_steps_via_parent_step_id` — a `task` step with subagent steps nested via
  `parent_step_id`), not by a live run. (UX-B-4: 2/2 completed, 0 delegations.)

### Scenario snapshot totals (per the committed reports)

| Area / mode | Scenarios | Ran to `completed` | Shape-matched | Report |
| --- | --- | --- | --- | --- |
| Commercial (baseline) | 5 | 5/5 | 4/5 | `ux-b-1/` |
| Disputes | 3 | 3/3 | 3/3 | `ux-b-2/disputes/` |
| M&A | 3 | 3/3 | 1/3 | `ux-b-2/m-and-a/` |
| Privacy | 3 | 3/3 | 3/3 | `ux-b-2/privacy/` |
| Employment | 3 | 3/3 | 2/3 | `ux-b-2/employment/` |
| Commercial — skills on | 2 | 1/2 | 1/2 | `ux-b-3/commercial/` |
| Commercial — subagent | 2 | 2/2 | 0/2 | `ux-b-4/commercial/` |

A shape-miss or a non-`completed` run is a **finding**, not a failure (ADR-F015). The two notable ones — the
UX-B-3 broad-review `cap_exceeded` and the UX-B-4 `task_calls=0` — are exactly the honest signals UX-B exists
to surface, and are kept verbatim.

## Open calibration question (backlog — NOT a UX-B blocker)

**Does a tier-4 model ever elect to fan out on a genuinely large matter?** UX-B-4 establishes the delegation
machinery is correct and isolated, but M3 doesn't choose to delegate at the matter sizes tested. Resolving
*whether and when* it would is a follow-up, not a gate on shipping UX-B. Options, in rough order of effort:

1. A **profile nudge** naming the researcher for large/multi-thread matters (cheapest; risks gaming the
   qualification if it reads as "you must delegate" — keep it conditional on real size).
2. A **larger fixture** (dozens of documents, several independent investigation threads) to see if scale
   alone triggers election.
3. A **stronger qualified model** (requires running it through the S9 / ADR-F015 gate first).

Recorded in the decomposition § Backlog. Do not build it inside UX-B.

## What this unblocks

With UX-B closed, the **agentic-modules / Oscar-Privacy** direction is unblocked as its own milestone: the
substrate now demonstrably works end-to-end (configured areas → per-area + per-subagent skill subsets →
on-demand delegation → an honest cockpit), and the qualification discipline (ADR-F015) is the template for
admitting any new capability or model. The honest map above is the calibration baseline that direction
inherits.
