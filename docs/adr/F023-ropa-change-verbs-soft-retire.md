# F023 — ROPA change verbs: soft-retire / supersede + unlink

- Status: accepted
- Date: 2026-06-19
- Extends: ADR-F018 (agentic modules = typed domain + code-validated agent writes), ADR-F019 (relational,
  deployment-global ROPA inventory)
- Milestone: PRIV-8a (Privacy / ROPA module — the agent can *change* the register, not only append)

## Context

The Privacy Deep Agent could only ever **add** to the ROPA: PRIV-1/2/3/5/6 gave it `propose_*`, `link_*`,
`add_*` and `list_*` — 14 create/link/tag/read tools, **zero** edit/delete/retire/unlink. A lawyer's natural
ask — *"we moved off Mixpanel, we use Hotjar now"* — is therefore impossible to satisfy correctly: the agent
can add Hotjar but cannot remove Mixpanel, leaving the register listing **both** (wrong). The product thesis
("just tell the agent in plain language and the register updates") needs **change verbs**, not just add verbs.

The register is **audited, append-only-by-design, and deployment-global** (ADR-F018/F019): one company-wide
standing record shared firm-wide, with one audit row per guarded write and `source_project_id` as provenance
(not ownership). A maintainer owns it. Any "change" capability must preserve those properties — a destructive
delete would erase the audit trail and the history of what the register used to say.

Two questions: **how does "change/remove" work on this register**, and **what is the verb set**?

## Considered Options

1. **Hard delete / replace.** Add `delete_*` verbs that remove the row (and cascade its links). Cleanest data
   and simplest reads, but **destroys history** — "did we ever use Mixpanel? when did we stop?" becomes
   unanswerable — and cuts directly against the audited, shared, deployment-global posture (a row may be
   referenced by several matters' provenance). Rejected.
2. **Edit-in-place.** Add `update_*` verbs that mutate an existing row's fields (rename "Mixpanel" → "Hotjar",
   change `country`, …). Fewest moving parts for a "swap", but it **rewrites the identity and provenance of a
   shared global row** and conflates "we switched vendors" with "that vendor was always Hotjar" — a reader of
   the register (or its audit) can no longer tell a correction from a real-world change. Rejected.
3. **Soft-retire / supersede + unlink (CHOSEN).** Never destroy a row: a retire sets a `retired_at` timestamp
   (+ optional `retirement_reason`) so the change is fully auditable and reversible-later; reads exclude
   retired rows from the *live* register by default (`?include_retired=true` shows them). A separate `unlink`
   verb removes one M:N link ("this activity stopped using X" while X stays live elsewhere). The "swap" is
   **composed** from primitives (add the new → link it → unlink the old → retire the old) and taught by a
   skill — no single `replace` macro that would hide the steps from the audit trail.

## Decision Outcome

**Option 3.** The maintainer's call (2026-06-19): global retire is correct ("someone maintains the
company-wide ROPA"), and soft-retire is required precisely **so the change can be audited**.

- **`retired_at TIMESTAMPTZ NULL` (+ `retirement_reason TEXT NULL`)** on the four *mutable* entities
  (`processing_activities`, `systems`, `vendors`, `transfers`). The two Article 30(1)(c) label vocabularies
  (`data_subject_categories`, `data_categories`) are immutable tags — no retire (a "we no longer process X"
  unlink is deferred; see Backlog). Additive + nullable → existing rows are live by construction, no backfill.
- **Six new guarded tools**, on the same ADR-F018 path (R6 grant set, R5 live re-check, one audit row carrying
  tool/IDs/result-size — never raw values): `retire_processing_activity`, `retire_system`, `retire_vendor`,
  `retire_transfer`, `unlink_system_from_activity`, `unlink_vendor_from_activity`. All validate ids, reject
  unknowns with a fix-and-retry message, and are idempotent (re-retire / re-unlink is a friendly no-op).
- **Reads exclude retired everywhere by default** — the list/detail/export/summary/data-flow endpoints AND the
  agent's own `list_*` tools (including the category usage-counts and the transfers list). Relationships are
  filtered with one mechanism, SQLAlchemy `with_loader_criteria`, so a retired *related* row uniformly
  disappears: a retired vendor/system drops off an activity's links; a category's per-term count reflects only
  live activities; a transfer whose recipient vendor is retired keeps the transfer but shows **no recipient**;
  and a transfer is hidden when it is itself retired *or* its parent activity is retired. `?include_retired=true`
  (list endpoints) is the full audit view (lead + nested); detail endpoints resolve a retired row by id but
  still show only live links; the agent `list_*` tools append a `(N retired, hidden)` footer so a name the
  agent can't see isn't accidentally recreated. The write/link/tag/transfer verbs likewise refuse a **retired
  target**, so the live register never grows a hidden link to a retired row.
- **Retire is company-wide** (the register is deployment-global): retiring Mixpanel removes it from every
  activity. The skill states this and the agent reports it. To stop using something for one activity only,
  the agent uses `unlink_*` instead.

## Consequences

- **Auditable change, by construction.** Every retire/unlink is a guarded dispatch with an audit row; nothing
  is ever destroyed, so the register's history ("used Mixpanel until 2026-06; replaced by Hotjar") is
  recoverable. This is the property the maintainer explicitly required.
- **Reads must filter — the load-bearing risk.** Any read path over the register MUST exclude retired rows or
  it silently resurfaces them. The API side centralises this in `app.api.ropa._hide_retired()` / `_live_only()`
  (lead `.where` + nested `with_loader_criteria`); the agent tools filter at source (`_list_*` +
  `_retired_count`, incl. the category usage-count and the transfer parent/recipient). Both surfaces are
  covered by tests; called out for any future PRIV read surface.
- **No un-retire (restore) yet** and **no category unlink** — Backlog. Reversibility needs its own audit story.
- **The swap is multi-step**, so it depends on the agent sequencing primitives correctly (and on an adequate
  step budget — see the PRIV-7 recursion-limit fix). Mitigated by the `ropa-maintenance` skill (PRIV-8b),
  bound test-only first, then by migration once validated.
- **Parallel-tool-call deadlock** (the open PRIV-7 follow-up) touches the same guarded path; not fixed here.
- Supersedes nothing; extends F018/F019. The data-flow rendering decision keeps F022.
