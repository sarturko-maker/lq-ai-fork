# F081 — The living redline: `apply_redline` converges on the working head

Status: proposed (drafted 2026-07-11, maintainer bug report same day; amends F066 in part — see
Consequences)

## Context

The Commercial agent's redline loop is iterative by nature: the lawyer asks for a redline, reads
it, and asks for changes — potentially dozens of rounds before taking the document. R-1 (ADR-F066)
made the *input* side of that loop continuous: `resolve_working_docx` walks `files.parent_file_id`
lineage to the newest non-snapshot leaf, so a follow-up `apply_redline` builds on the previous
redline's bytes. The *output* side never converged: every apply minted a NEW `File` row
(`contract (redlined).docx` → `(redlined v2)` → …), so each round produced a new document in the
Documents tab and a new Collabora editor target. The maintainer's report (2026-07-11): the agent
must "redline continuously over the same redline" unless asked otherwise.

The codebase already contains the correct shape for a document whose bytes evolve under one stable
identity: WOPI PutFile (ADR-F047 Slice 3) mutates the live row in place — same id, same
`storage_path` — and preserves the prior version as an immutable `is_snapshot` row at the
**authorship boundary** (the first *human* save of *agent* bytes). The lineage resolver (F066)
explicitly anticipates in-place mutation: leaf recency is `coalesce(updated_at, created_at)` and
snapshots are never a working version.

## Considered options

1. **Keep new-row-per-apply** (status quo) — rejected: it is the reported bug; the document
   identity the lawyer works with changes every round, and the Documents tab fills with `(vN)`
   siblings.
2. **Update the working head in place, WOPI-symmetric** (snapshot at the authorship boundary,
   two durable steps) — chosen.
3. **A first-class document/version entity** (one "document" row over many version rows; UI and
   WOPI resolve the head) — rejected for now: it is the org-wide document-versioning ADR F066
   already reserved as future work (option-4 territory; also MILESTONES § Backlog), and this bug
   does not need it.

## Decision outcome

**Option 2.** `_apply_redline` gains an output-convergence branch:

- **When to converge:** the resolved working head is a *derived work product*
  (`parent_file_id IS NOT NULL AND NOT is_snapshot`), its filename matches the module's own
  redline naming (`… (redlined[ vN]).docx` — the anchor that keeps a **"(response)" document**,
  the per-round outbound record `respond_to_counterparty` dispatched, forever out of the converge
  path; filenames are stable post-creation since WOPI RENAME_FILE is disabled), and
  `start_fresh=False`. The head is re-fetched as a locked row (`SELECT … FOR UPDATE`) at persist
  time, and the write is guarded by a **wedge-aware hash CAS**: if the head row's `hash_sha256`
  no longer equals the hash of the bytes the redline was rendered over, the current storage bytes
  are re-hashed to distinguish two states — a **genuine race** (storage moved on since the
  render: reject with fix-and-retry, never clobber a concurrent write) from a **stale-row wedge**
  (the row disagrees with its *own* storage because a prior apply's step-2 commit failed after
  the overwrite: the render is over the true current bytes, so the apply proceeds and *repairs*
  the row — rejecting would wedge the living document forever, since every retry re-renders over
  the same bytes and re-mismatches the stale hash).
- **Original uploads are never mutated.** A root-resolved head (first redline) and
  `start_fresh=true` keep creating a new derived row; its name is now made **matter-unique**
  (`(redlined)` → `(redlined v2)` → …), fixing the pre-existing duplicate-name wart when a fresh
  branch coexists with a living head. Snapshot names are matter-unique the same way
  (`(lawyer draft)` → `(lawyer draft v2)` → …); WOPI's own `(agent draft)` snapshots keep their
  pre-existing colliding naming — a recorded follow-up, out of this slice.
- **Snapshot at the authorship boundary, mirrored:** WOPI snapshots *agent* bytes before the first
  *human* overwrite; this path snapshots *human* bytes (`created_by_run_id IS NULL` — the lawyer
  edited in Collabora since the agent last wrote) before the *agent* overwrite, as
  `<stem> (lawyer draft).docx`, `is_snapshot=True`, `parent_file_id=head`. Agent-over-agent
  overwrites do NOT snapshot: the new bytes strictly extend the old (tracked changes are additive
  — the prior version is recoverable by rejecting the newest change regions in Word), and the
  bytes' informational content is regenerable, unlike a lawyer's manual edits. This is the
  data-loss argument F047 §version-model requires, made explicitly.
- **Two durable steps** (F047 §data-safety ordering, mirrored): **(1)** *(snapshot case only)*
  `copy_object` live → snapshot key, insert the snapshot row, flip the head's
  `created_by_run_id = run_id`, **bump `updated_at`**, **commit**; on failure delete the orphan
  snapshot object and raise. Flipping provenance inside step 1 means a retry after a step-2
  failure can never re-snapshot already-overwritten bytes; bumping `updated_at` inside step 1
  means a Collabora save landing after this commit trips the `X-COOL-WOPI-Timestamp` backstop
  (409/1010 — the editor warns) instead of sailing through it. Because this commit **releases
  the FOR UPDATE lock**, step 2 **re-acquires the head row and re-runs the CAS** before any byte
  is overwritten (review blocker: a writer slipping into the inter-commit window — an editor
  save, a concurrent run — must never be silently clobbered; any such writer re-stamps both the
  bytes and the provenance itself, so aborting on the re-check leaves a consistent head plus a
  now-redundant but still-true lawyer-draft snapshot). **(2)** overwrite the live object **at
  the head's own `storage_path`** (key reuse is load-bearing: no GC sweep exists, a new key
  would leak the old object forever), bump `hash_sha256`/`size_bytes`/`updated_at`, set
  `created_by_run_id = run_id`, audit, **commit inside the tool body**. The body-side commit is
  deliberate: `guarded_dispatch`'s failed-audit path rolls the session back after the tool
  returns, and that rollback must not be able to discard row metadata for an object that was
  already overwritten.
- **`updated_at` bump is load-bearing twice:** the F066 resolver's `coalesce(updated_at,
  created_at)` leaf pick, and WOPI's `X-COOL-WOPI-Timestamp` save-race backstop (409/1010), which
  is what keeps a lawyer's concurrent editor save warn-not-clobber.
- **`created_by_run_id` semantics change** from "the run that created the row" to "the run that
  last wrote the bytes" (ADR-F046's timeline reading follows the living document to the latest
  run). Each `commercial.redline_applied` audit row now carries the per-apply result hash
  (`redlined_sha256` — an ID, not content) plus `updated_in_place`/`snapshot_file_id`, so
  earlier receipts stay resolvable to the exact bytes their run produced even though the row
  evolves. WOPI's snapshot-on-human-save keys on the same flag and re-arms correctly after each
  agent write (the human↔agent alternation intentionally yields one `(agent draft)` snapshot per
  boundary — history at every authorship change, no snapshot on same-author iteration).
- **No editor-lock refusal.** The Collabora lock is held for essentially the whole "chat beside
  the open viewer" session (edit-mode is unconditional), so refusing on a held lock would break
  the primary flow this ADR exists to fix, and a crashed session would dead-block the agent for
  the 30-minute lock TTL with no force-unlock path. Instead: the web re-keys its redline announce
  on `(id, updated_at)` so round-2+ updates re-fire `redlineready`; an open pristine editor
  reloads, a dirty one gets a reload banner; and the WOPI timestamp backstop covers the remaining
  race. `GET /files/{id}/content` also stops pinning `Content-Length` from the row (the same
  stale-window hazard WOPI GetFile already documents and avoids).

## Consequences

- ADR-F066 is **amended in part**: its write-side bullet ("redline … outputs set `parent_file_id`
  = their source row's id" — i.e. new-row-per-apply) and its version-aware-naming chain now apply
  only to the **branch-creating** cases (first redline from a root; `start_fresh`). Migration
  0089, the resolver, `start_fresh`, and the response-path semantics are unchanged. F066 carries a
  status pointer to this ADR; per fork rules it is not rewritten.
- ADR-F047's invariant "PutFile is the only path that mutates bytes in place" is no longer true;
  F047 carries an addendum. The `LastModifiedTime = updated_at or created_at` reading stays honest
  because this path bumps `updated_at` identically.
- `respond_to_counterparty` deliberately keeps new-row-per-round: a response document is the
  per-round *outbound* artifact (a record of what was dispatched), its resolution path has no
  lineage walk, and the converge predicate's redline-name anchor excludes it structurally.
  Its duplicate-name quirk is recorded in `docs/fork/MILESTONES.md` § Backlog (together with
  WOPI's colliding `(agent draft)` snapshot naming).
- Residual (accepted, documented): a step-2 commit failure after the object overwrite leaves row
  metadata stale relative to storage — the same storage/DB non-atomicity WOPI accepts. Where
  WOPI converges via the editor's idempotent PutFile retry, this path converges via the
  wedge-aware CAS: the **next apply detects the row-vs-own-storage mismatch, proceeds over the
  true current bytes, and repairs the row** (a plain retry, exactly what the tool's error path
  invites). Until that next apply, WOPI-side effects of the stale row (no-op-autosave detection,
  `X-WOPI-ItemVersion`) misread — bounded and self-healing. Concurrent WOPI-vs-agent writes in
  the snapshot path's inter-commit window are handled warn-not-clobber (step-1 `updated_at` arms
  the 1010 backstop; step-2 re-lock + re-CAS aborts the agent side); the one cosmetic residual is
  that a lawyer save landing in that window snapshots the pre-save bytes under WOPI's
  `(agent draft)` label while this path had already preserved the same bytes as
  `(lawyer draft)` — a duplicate, correctly-preserved prior version with an imprecise label.
- The D6 user-export race (metadata hash vs streamed bytes under concurrent mutation) widens
  marginally; pre-existing since F047, unchanged in kind.
