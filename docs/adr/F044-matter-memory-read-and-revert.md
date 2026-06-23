# F044 — Matter-memory read tools + human-authenticated, revert-to-version wiki undo

- Status: proposed (2026-06-23, with slice C3c-1 — the matter-memory read/revert backend)
- Date: 2026-06-23
- Relates: ADR-F042 (unit-of-work auto-write-then-correct — "the human owns the tier: correct/undo/delete";
  this is the *undo* primitive + the read surface), ADR-F043 (the consolidation pass whose `wiki_snapshot`
  rows this revert restores), ADR-F018 (code-validated agent input — reject-not-crash, reused for the read
  tools' untrusted args), ADR-F005 (audit contract: counts/types/IDs, never raw values), ADR-F002 (the
  practice area IS the agent — area-agnostic grant), ADR-F010 (gateway-only egress — N/A here: C3c-1 makes
  zero model calls).
- Milestone: COMMERCIAL — matter-memory track (C3a ✓ / C3b-1 ✓ / C3b-2 ✓ / **C3c**). **Accept with C3c-1.**

## Context

C3a–C3b built the matter-memory tier's whole **write/store/egress** substrate: the auto-written prose wiki
(`projects.context_md`) + human-pinned corrections (C3a), the dated bi-temporal **fact ledger** (C3b-1), and
the gateway-routed consolidation/Lint pass (C3b-2). What was missing is the **read/manage** half (ADR-F042
§C3c): the agent could *write* its fact ledger but not *query* it mid-run, and a human could neither inspect
what had accumulated nor exercise the "undo" ADR-F042 promised.

C3c was scoped as one slice (agent read tools + a GET endpoint + a revert endpoint + a cockpit memory
panel). The maintainer **split it**: C3c-1 is the backend (this ADR) — fully testable + live-provable via a
provider scenario and the REST API; C3c-2 is the cockpit panel (pure frontend consuming these endpoints).
The read substrate already exists and is tested (`facts_valid_at` / `live_facts` / `memory_log` /
`load_pinned_corrections`); no embeddings until B6 (gateway `/v1/embeddings` is 501) — at matter scale (tens
of facts) keyword/whole-set reads suffice. **No migration** (read + revert over existing rows). The
maintainer chose the four options below via AskUserQuestion (3 + 4 the live-corpus pin surfaced in design).

## Considered Options

**1. Slice scope.**
- A. **Split: backend now (C3c-1), cockpit panel next (C3c-2) (chosen).** Each ships a coherent, gated
  vertical — C3c-1 proves the agent can recall + a human can revert via API; C3c-2 is the UI over it. Two
  clean ADR-F005 gates instead of one heavy combined gate (backend suite + frontend vitest + Cypress + live).
- B. All in one PR. Rejected by the maintainer — a large diff and a combined gate.

**2. Wiki undo semantics (the ADR-F042 "undo" primitive).**
- A. **Revert to a chosen prior version (chosen).** The GET returns the wiki version history (the
  `wiki_snapshot` rows: timestamp + run provenance + a bounded preview); `POST .../memory/wiki/revert
  {snapshot_id}` restores that body, **snapshotting the current wiki FIRST** (so the revert is itself
  reversible). No ambiguity, pairs with the panel, and subsumes "undo last".
- B. Undo-last only (no target). Rejected — a second undo ping-pongs between two states rather than walking
  history; "restore the version I can see" is clearer and strictly more capable.

**3. Agent read-tool search corpus** (surfaced by the design pressure-test).
- A. **Live only (chosen).** `search_matter_memory` searches the LIVE corpus (current fact ledger + current
  wiki + live pinned corrections). Searching the full append-only log would feed the model a **superseded /
  retired / injected-then-superseded** statement as if current — a correctness *and* prompt-injection hazard.
  Historical recall is the separate `matter_facts_as_of` bi-temporal tool, which labels every fact by its
  validity window.
- B. Search the whole log. Rejected — stale/contradicted statements resurfacing as current is exactly what
  the bi-temporal model exists to prevent.

**4. Correction management in C3c-1.**
- A. **Corrections read-only this slice (chosen).** The GET surfaces pinned corrections with provenance, but
  C3c-1 adds no retire/edit endpoint. A wrong pin is already overridable by pinning a newer correction
  (corrections inject newest-first). Keeps C3c-1's only write to the wiki revert.
- B. Add a correction-retire endpoint now. Deferred — a clean follow-up; not needed to ship the read/revert
  half, and it widens the slice's write surface.

## Decision Outcome

Adopt **1A + 2A + 3A + 4A**. C3c-1 ships, all owner-scoped and area-agnostic, **no model calls, no migration**:

- **Two agent read tools** (`app/agents/matter_read_tools.py`), granted to **every** matter-bound run (any
  area) with a grant set **disjoint** from the wiki / fact / consolidation / ROPA / assessment / commercial
  grants (confinement); both route through `guarded_dispatch` (reads are guarded too — the uniform
  chokepoint, per `list_assessments`):
  - `search_matter_memory(query)` — Python-side keyword match over the **live** corpus (never builds SQL from
    the model's query — no injection surface); returns a bounded digest with provenance.
  - `matter_facts_as_of(as_of_date)` — the bi-temporal "what did we believe at T" query. The model's date is
    normalised to UTC-aware at the schema boundary (`MatterFactsAsOfInput`, reusing `_utc_aware`) so the
    comparison against the tz-aware columns cannot raise — a bare ISO date or an unparseable string becomes a
    **reject-and-retry, never a crash** (the C3b-1 trap).
- **A composite GET** `GET /matters/{project_id}/memory` — the read-only projection that feeds the C3c-2
  panel: the current wiki (+ revertable-version count), the live facts, the live pinned corrections, and the
  most-recent slice of the append-only log (+ total). It **reuses the agent layer's tested read substrate**
  (`live_facts` / `memory_log`) — a deliberate, narrow **api→agents read edge**; no guard is needed because
  the route's own `ActiveUser` + `_load_visible_project` (404 on miss / cross-user / archived) is the authz.
- **A human-authenticated revert** `POST /matters/{project_id}/memory/wiki/revert {snapshot_id}` — restores a
  chosen `wiki_snapshot` body into `context_md` via the shared `snapshot_and_rewrite_wiki` (which snapshots
  the current wiki first — single-sourcing "snapshot before overwrite" is what makes the revert reversible).
  The snapshot lookup is scoped by **id AND project_id AND kind='wiki_snapshot'** → 404 (blocks a
  cross-matter id, a non-snapshot row, another user's matter). Append-only — nothing is deleted. **The agent
  has no revert tool**: undo is an authenticated *human* action only (ADR-F042 "the human owns the tier").
- **Audit:** the revert endpoint audits `matter_memory.wiki_revert` with IDs/counts only
  (`reverted_to_snapshot_id`, `new_chars`, `snapshotted_prior`) — never the wiki body; the read tools' guard
  envelope records `result_chars` only (the body IS returned to the model — that is the tool's job — but never
  to an audit row).

## Consequences

- **Bi-temporal integrity upheld:** live-only search means an automated/injected-then-superseded fact never
  resurfaces as current; the as-of tool is the only historical path and it always labels validity windows.
- **Undo is safe + reversible:** every revert snapshots the prior state first and deletes nothing, so the
  wiki history is a walkable, append-only chain (a revert of a blank wiki simply writes no prior snapshot —
  benign, surfaced via `snapshotted_prior=false`).
- **New layering edge:** `app.api.matter_memory` now imports read helpers from `app.agents.*`. Accepted and
  narrow — they are query-only "substrate" (no guard, no runtime deps), and reusing them keeps the GET's
  notion of "live" identical to what the agent reads and what consolidation operates on (no drift).
- **No migration / no new dependency / no egress:** C3c-1 reads existing rows and reuses
  `snapshot_and_rewrite_wiki` (whose `run_id` widens to `uuid.UUID | None` for the human, run-less revert).
- **Deferred (C3c-2 / backlog):** the cockpit memory panel; a correction-retire endpoint (4B); embedding /
  FTS search and log pagination beyond a tail cap; the marker-fence delimiter-injection hardening (a
  cross-cutting slice, not piecemeal here).
- **Licence/SBOM:** zero new dependencies; no NOTICES.md entry required.
