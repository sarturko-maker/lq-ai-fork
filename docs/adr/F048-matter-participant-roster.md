# F048 — Matter authorship roster (who-is-who) + roster-based author resolution

- Status: proposed
- Date: 2026-06-26
- Deciders: maintainer (Arturs), agent
- Slice: authorship Slice 1 (foundation + hand-back resolution; the C5a negotiation-path
  classification + a structured email-metadata tool are a deferred Slice 2)

## Context

A real negotiation has **many people redlining a document**, not just two counsels: our lead +
our associate + our client's GC on one side, their counsel + their client on the other. The agent
must know **whose tracked changes are whose** to act correctly — incorporate our side's edits,
treat the counterparty's as a position to negotiate, and not silently adopt a stranger's.

The editor Slice-5 hand-back (ADR-F047) shipped a **naive author filter**
(`review_edited_document_tools.py`): `changes = [c for c in state.changes if c.author != DEFAULT_AUTHOR]`
— it equated "ours" with the single agent author (`"LQ.AI Commercial counsel"`) and treated
**every** other author as the trusted supervising lawyer. In a multi-party document that
**over-trusts**: a counterparty's (or an unknown third party's) tracked changes present in a
handed-back `.docx` would be incorporated as if authoritative. The maintainer flagged this when
choosing the Slice-5 filter (MILESTONES Backlog) and asked for a proper model: the agent learns
who is who from the signals it already sees (a docx's tracked-change author strings, an email's
`From:` line, the user's own statements like "this is the other side's redline"); when it isn't
sure it **checks in with the user**; and the **roles live in matter memory in a separate section
the user can amend**.

Five subsystem maps established the ground: author strings are plain text on
`StateOfPlay.TrackedChange.author` / `CounterpartyComment.author` (default `"unknown"`); the
matter-memory tier (ADR-F042/F044) stores agent-written facts + human-authenticated corrections,
but facts are **agent-write-only** (no human-create endpoint) — too weak for a roster the lawyer
must directly set; an email's `From:` line is **already agent-visible** in `read_document()` text
(no new ingestion needed); and "check in with the user" needs **no new machinery** — there is no
langgraph interrupt and no `ask_user` tool, the working pattern is *ask in the answer, the run
ends, the user replies → a new run resumes on the same `thread_id`* (ADR-F008).

Constraints (CLAUDE.md): cross-user access → 404 not 403; audit rows carry counts/types/IDs only,
never identity text; retrieved/edited documents are untrusted model input; the unit-of-work tier
is auto-write-then-correct (ADR-F042 — the agent maintains it, the human owns it after).

## Considered options

1. **Dedicated `matter_participants` table + roster-based `classify_author`, human-writable, with a
   check-in-when-unclear doctrine (CHOSEN).** A typed per-matter roster — identity (display name +
   an `aliases` match-set of author strings/emails) → `side ∈ {ours, counterparty, unknown}` +
   a free-text `role_label`, plus `trust ∈ {inferred, confirmed}` (agent vs human). The agent
   auto-records (`record_matter_participant`, `inferred`); the lawyer adds/edits/removes
   (`POST/PATCH/retire`, `confirmed`) and a confirmed entry's side/role is never overridden. The
   hand-back re-read classifies every author against the roster (ours → incorporate, counterparty
   → negotiating position, unknown → ask) — replacing the naive filter.

2. **Reuse the facts ledger (`fact_type='participant'`).** Cheaper (the table + read/amend UX
   exist), but facts are agent-write-only and freeform `body_md` — the lawyer could only pin a
   free-text correction or retire, never directly *set* a person→role, and a freeform body is a
   fragile match key. Rejected: the whole point is structured, human-settable identity.

3. **A wiki "Participants" section.** Zero schema cost but unstructured, no per-entry amend, no
   reliable join key. Rejected.

4. **A langgraph interrupt for "check in with the user".** A true pause/resume for the ambiguous-author
   question. Rejected for this slice: the architecture has no interrupt path, and thread-resume
   already delivers the behaviour (the agent asks, stops, the user answers, the run continues) with
   zero new protocol.

## Decision outcome

Chosen: **option 1** — maintainer rulings (AskUserQuestion, 2026-06-26): dedicated roster table;
**side drives treatment** (ours incl. our client → incorporate; counterparty → negotiate; unknown
→ ask; a role label rides along); **direct edit, human wins**; **Slice 1 = foundation + hand-back
resolution**, the C5a path + structured email tool deferred to Slice 2.

- **Data** (`matter_participants`, migration `0076`): matter-scoped (CASCADE), `aliases` JSONB
  match-set (matched Python-side, normalised lower/trim — never SQL from untrusted input), `side`
  + `trust` CHECK-bounded (additive-extensible, mirroring `_MATTER_FACT_TYPES`), soft-retire via
  `superseded_at`.
- **Agent** (`matter_roster_tools.py`, zero model calls): `record_matter_participant` (auto-write,
  human-confirmed never overridden — at most aliases widen), `list_matter_roster`, the pure
  `classify_author`, and a prompt-injected roster block + `MATTER_ROSTER_DOCTRINE` (record from
  emails/statements; on a re-read incorporate ours, treat counterparty as a position, **ask** on
  unknown then record the answer). Granted to **every** matter-bound run (all areas), grant set
  disjoint from every other matter + domain grant.
- **Resolution**: `review_edited_document` classifies each change/comment via the roster into
  ours / counterparty / unknown buckets (the agent's own `DEFAULT_AUTHOR` dropped) and renders
  them distinctly with the ask cue — the real replacement of the naive filter.
- **Human surface** (`matter_roster.py`): `POST/PATCH/retire` (owner-scoped 404, `trust='confirmed'`
  + `user_id` from session, counts/IDs-only audit) + the active roster folded into the composite
  `GET /matters/{id}/memory`; a **Participants** section in the cockpit Memory panel (add/edit/remove).

## Consequences

- The over-trust defect is fixed: an unrostered author is now surfaced for the agent to **ask**,
  never silently incorporated; the lawyer's edits are trusted once they are on the roster (recorded
  by the agent or confirmed by the lawyer).
- **Author strings are untrusted and forgeable.** A counterparty could set their docx author to our
  lawyer's name to be classified `ours`. The roster *reduces* over-trust (unknown → ask) but is a
  heuristic over an untrusted field, **not** cryptographic identity. A trusted authorship channel
  (e.g. the WOPI-authenticated editor stamping a verifiable identity) is future work — called out
  here, not solved. The hand-back's residual safety rests on human supervision (the lawyer handed
  it back) + the human-confirmed roster.
- "Check in with the user" is doctrine + thread-resume, not a guaranteed gate: the agent is
  *instructed* to ask on an unknown author. The deterministic guarantee is the **classification +
  rendering** (unknown items are bucketed and labelled "ASK"), not a forced pause.
- Deferred (Slice 2, on record): roster classification in the C5a negotiation path
  (`extract_counterparty_position` / `respond_to_counterparty`); a structured `get_document_metadata`
  tool exposing `Document.structured_content` for robust email-sender attribution; an `'other'` side
  for third parties (regulator/escrow); auto-seeding the operator/WOPI user as `ours`.

## Slice 2 addendum (2026-06-26) — richer signals + roster-aware negotiation

Delivers the four Slice-1 deferrals. Decisions (AskUserQuestion, maintainer): a **distinct
third-party bucket** for `'other'` in both renders; **lazy auto-seed** of the operator at run start;
`get_document_metadata` exposes **email metadata + docx core-properties author**. Migration `0077`;
no new HTTP route, no new dependency.

- **`'other'` third-party side** (migration `0077`: drop+recreate the `side` CHECK to add `'other'`,
  precedent `0070`). A known third party (escrow agent, lender's counsel, regulator) classifies as
  its own side and renders in a **distinct THIRD-PARTY bucket** ("not your side, not the direct
  counterparty; weigh and respond, do not silently adopt") in the hand-back and negotiation renders —
  rather than being mis-bucketed as the counterparty or as unknown.

- **`get_document_metadata` tool** (`tools.py`, in `MATTER_TOOL_NAMES`, granted to every matter-bound
  run): for an **email** it returns the stored `Document.structured_content` headers (From/To/Cc/Date/
  Subject — no re-parse, no ingestion change); for a **.docx** it reads the core-properties author /
  last-modified-by live from the matter bytes (via the shared, safety-gated `load_matter_docx_bytes`).
  Matter-scoped + 404-conflated; counts-only guard audit. These strings are **untrusted, forgeable
  model input** — the tool docstring/return frame them as a clue to who a participant is (then
  `record_matter_participant`), never authoritative identity. No new HTTP route.

- **Roster-aware negotiation render (the C5a classification).** `extract_counterparty_position` now
  loads the roster and `_render_state_of_play` groups each change/comment **by side** (OUR SIDE /
  THIRD PARTY / COUNTERPARTY). Key divergence from the hand-back: the agent has deliberately opened
  the *counterparty's* document, so an author it cannot place **defaults to the counterparty** here
  (preserving the proven C5a respond-to-every-ref loop) — whereas the trusted hand-back treats an
  unknown author as unexpected and **asks**. Classification is **additive labelling only**: every ref
  still requires exactly one decision; the `evaluate_coverage` / `evaluate_anchoring` gates (which key
  on refs, not authors) and the no-silent-action guarantee are unchanged. (Implementation note: the
  editor and negotiation renders deliberately do **not** share a bucketer — the negotiation render
  keeps full coverage parity and a counterparty-default, so it classifies inline via the shared,
  already-public `classify_author` rather than the editor's `_classify_edits` which drops the agent's
  own/resolved items.)

- **Lazy auto-seed of the operator as `ours`** (`ensure_operator_participant`, called at run-start in
  `composition.py` when a matter is bound). The run owner (the authenticated session user — never
  model input) is seeded once as a **confirmed `'ours'`** row (`display_name = display_name or email`,
  email as an alias), idempotent (matched on name/email), so the agent need not ask who its own side
  is and the lawyer's own edits classify `ours` from the first run. Seeding **lazily at run start**
  (vs eager at matter-create) covers existing matters too, with no data backfill. `trust='confirmed'`
  means the agent's auto-curation can never override it (B2).

### Slice-2 consequences
- The untrusted-author-string limitation (above) is **unchanged** — `get_document_metadata` adds a
  richer but still-forgeable signal; it informs candidacy, it does not authenticate. A trusted
  authorship channel remains future work.
- The operator auto-seed has a benign, self-healing race: two brand-new threads composing on the same
  brand-new matter could each seed once before either commits → at most one duplicate `'ours'` row,
  which classifies identically and the lawyer can retire; every later run matches the existing row.
  Accepted over schema creep (a dedicated unique constraint would also block the lawyer adding people).
- Still deferred (Slice 3, if pursued): WOPI-stamped trusted authorship; C5a-path **action**
  classification beyond the render (e.g. auto-skipping coverage for our-own edits — explicitly NOT
  done, to keep the no-silent-action gate intact).
