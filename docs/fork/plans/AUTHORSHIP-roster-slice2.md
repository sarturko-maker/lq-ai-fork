# Plan — Authorship **Slice 2**: roster-aware negotiation + richer authorship signals (ADR-F048 addendum)

## Context

Authorship Slice 1 (ADR-F048, mig `0076`, merged `7dc31f7`) gave the matter a **who-is-who roster**
(`matter_participants`: identity + alias match-set → `side` ∈ {ours, counterparty, unknown} + role, `trust`
∈ {inferred, confirmed}) the agent auto-populates and the lawyer amends, and rewired the editor **hand-back**
tool (`review_edited_document`) to bucket each author's edits ours→incorporate / counterparty→negotiate /
unknown→ask. Four follow-ons were deferred **on record** (ADR-F048 §Consequences, MILESTONES, HANDOFF);
this slice delivers all four:

1. **The C5a negotiation path still ignores the roster.** `extract_counterparty_position` renders every
   marked-up author flat as `(by {author})` (`commercial_tools.py:_render_state_of_play`) — in a real
   multi-redliner round (our associate + their counsel + a third party all in one returned `.docx`) the
   agent can't tell our side's edits from the counterparty's. The roster classifier exists and is proven on
   the editor path; the negotiation render just doesn't use it yet.
2. **Authorship signals are text-only.** Email `From:` is visible only as an inline line in the read text;
   the structured `From/To/Cc/Date/Subject` already sit unused in `Document.structured_content`, and a docx's
   authoring metadata is never read. The agent has no robust, structured attribution source.
3. **No third-party side.** The `side` set is {ours, counterparty, unknown}; a known third party (escrow
   agent, lender's counsel) has nowhere to live and gets mis-bucketed as the counterparty or as "unknown".
4. **The operator isn't on their own roster.** Every matter starts with an empty roster, so the agent must
   ask "who's our side?" even though the lawyer running the matter is structurally "ours".

**Maintainer rulings (AskUserQuestion, 2026-06-26):** (1) `'other'` edits render in a **distinct
third-party bucket** ("not your side, not the direct counterparty; weigh and respond, do not silently
adopt") in *both* the hand-back and negotiation renders; (2) auto-seed the operator **lazily at run start**
(covers all matters incl. the live Atlas matter; idempotent; no data backfill); (3) `get_document_metadata`
exposes **email metadata + docx core-properties author**.

Decisions ride **ADR-F048 (addendum)** — no new ADR number (mirrors the F047/F032 slice-addendum pattern).

## Approach

Four coherent sub-items, one PR. All reuse Slice-1 machinery; the only new schema is a one-line CHECK
extension. **No new HTTP route** (the tool is an agent tool; the seed is in composition) → **no
`test_endpoints`/`test_openapi` change** (the Slice-1 path-count trap does NOT recur here).

### Item 1 — roster-aware negotiation render (the C5a classification)
- **Promote the editor bucketer to shared, add the third-party bucket.** In
  `api/app/agents/review_edited_document_tools.py`, make `_classify_edits`/`_ClassifiedEdits` public
  (`classify_edits`/`ClassifiedEdits`) and add `other_changes`/`other_comments` buckets (the editor render
  gains a THIRD-PARTY section too). Both consumers operate on the same `StateOfPlay` shapes and already share
  `classify_author` (`matter_roster_tools.py`); this is genuine shared logic, so factor it once (no
  editor↔commercial coupling beyond importing the public symbol — `review_edited_document_tools` does **not**
  import `commercial_tools`, so the direction is acyclic).
- **Thread the roster into the negotiation render.** `api/app/agents/commercial_tools.py`:
  `_extract_counterparty_position` (≈556–582) loads `roster = await live_participants(db, binding.project_id)`
  and passes it to `_render_state_of_play`, which classifies each change/comment via `classify_edits` and
  renders **OUR SIDE / COUNTERPARTY / THIRD PARTY / UNIDENTIFIED(ASK)** sections (distinct prose from the
  editor's trusted-hand-back frame) — keeping the explicit cue that **every ref still needs a decision** and
  that UNIDENTIFIED authors should be ASKed-then-recorded before `respond_to_counterparty`.
- **No gate change.** `evaluate_coverage`/`evaluate_anchoring` key on refs only (`schemas/commercial.py`);
  classification is purely additive labeling on the read side. The no-silent-action guarantee is untouched.
- `build_commercial_tools` already carries `session_factory` + `binding.project_id` + `run_id` — nothing new
  to wire.

### Item 2 — `get_document_metadata` agent tool
- **`api/app/agents/tools.py`:** add `"get_document_metadata"` to `MATTER_TOOL_NAMES` (keeps grant sets
  disjoint) and a `get_document_metadata(name)` closure beside `read_document`, dispatched through
  `guarded_dispatch` over the same `_matter_files_query` matter-scope (owner-scoped, **404-conflated**).
  Impl `_document_metadata(db, binding, name)`:
  - **email:** read the stored `Document.structured_content["messages"]` (From/To/Cc/Date/Subject + threading
    ids) — no re-parse.
  - **docx:** fetch bytes via the existing `load_matter_docx_bytes` and read `python-docx`
    `Document.core_properties.author` / `.last_modified_by` / `.created` / `.modified` (≈5 lines; no
    re-ingestion, no migration).
  - Returns a compact labeled text block; **untrusted-input framing** in the docstring/return (these strings
    are forgeable model input — they *inform* roster candidacy, they do **not** override the roster).
  - Auto-granted via `build_matter_tools` (already called for every matter-bound run) — **no composition
    wiring** beyond the doctrine line below.

### Item 3 — `'other'` third-party side
- **Migration `0077`** (`down_revision="0076"`): drop+recreate the `side` CHECK to add `'other'` — exact
  precedent `0070` (`drop_constraint` + `create_check_constraint`); downgrade restores the 3-value CHECK.
  Round-trip on a throwaway pgvector container.
- **Literal updates (keep in sync):** `_MATTER_PARTICIPANT_SIDES` (`app/models/project.py`),
  `MatterParticipantSide` enum `+ OTHER = "other"` (`app/schemas/matter_memory.py`), and frontend
  `PARTICIPANT_SIDES` + `sideLabel('other') → "Third party"` + `sideToneClass('other')` (a distinct
  violet/slate tone, e.g. `border-violet-500/20 bg-violet-500/10 text-violet-600 dark:text-violet-400`) in
  `web/src/lib/lq-ai/components/matter/MemoryPanel.svelte`. The participant-form `<select>` and the `'other'`
  bucket prose (Item 1) follow.

### Item 4 — lazy auto-seed of the operator as `ours`
- **`api/app/agents/matter_roster_tools.py`:** new `ensure_operator_participant(db, project_id, user)` beside
  `live_participants`, reusing `_normalize`/`_match_set`/`_aliases_excluding_name`: if no active participant's
  match-set already contains the operator's `display_name`/`email`, insert one — `display_name = user.display_name
  or user.email`, **alias = user.email** (so the operator's own email on a docx/email author string classifies
  `ours`), `side="ours"`, `trust="confirmed"`, `user_id=user.id`, `run_id=None`. Idempotent; the confirmed row
  means the agent's `classify_author` finds it and `_best_identity_match` won't override it (at most widens
  aliases).
- **`api/app/agents/composition.py`:** when `binding is not None`, load the run-owner `User`
  (`run.user_id`) and call `ensure_operator_participant(...)` before tool assembly (the existing run-start
  `session_factory()` session). One indexed query per matter-bound run; covers existing matters.

### Doctrine (composition prompt)
Extend `MATTER_ROSTER_DOCTRINE`: the new `'other'` side for third parties; use `get_document_metadata` for
robust sender/author attribution (then `record_matter_participant`); the operator is pre-seeded as `ours`
(don't re-record yourself).

## Critical files
- **Migration:** `api/alembic/versions/0077_participant_other_side.py` (NEW).
- **Backend edit:** `app/agents/commercial_tools.py` (render classification), `app/agents/tools.py`
  (`get_document_metadata` + grant), `app/agents/review_edited_document_tools.py` (promote+`other` bucket),
  `app/agents/matter_roster_tools.py` (`ensure_operator_participant`), `app/agents/composition.py` (seed call
  + doctrine), `app/models/project.py` + `app/schemas/matter_memory.py` (the `'other'` literal/enum).
- **Frontend edit:** `web/src/lib/lq-ai/components/matter/MemoryPanel.svelte` (side helpers + `<select>`),
  `web/src/lib/lq-ai/types.ts` (no shape change; `side` stays `string`).
- **Tests:** extend `api/tests/agents/test_matter_roster.py` (classify→`other`, record `other`,
  `ensure_operator_participant` idempotency/seed/no-dup), `api/tests/test_matter_roster_api.py` (create
  `side='other'`), `api/tests/agents/test_review_edited_document.py` (the `other` bucket), NEW negotiation-render
  classification test (commercial render groups by side), NEW `get_document_metadata` test (email + docx author,
  404-conflation, matter-scope), composition seed test; web `__tests__/MemoryPanel-helpers.test.ts` (`other`
  label/tone). A provider-marked DeepSeek scenario under `tests/agents/scenarios/`.
- **Reuse:** `classify_author`/`live_participants`/`format_roster_block`/`_match_set`/`_normalize`
  (`matter_roster_tools.py`); `_classify_edits`/`_render_supervised_edits` (promote);
  `read_state_of_play`/`StateOfPlay` (`negotiation_service.py`); `load_matter_docx_bytes`/`_matter_files_query`/
  `guarded_dispatch` (`tools.py`); the `0070` CHECK-extension migration pattern; the Slice-1 roster create/seed
  conventions (`trust='confirmed'`, `user_id` from session, `run_id=None`).
- **Docs:** ADR-F048 (addendum section), HANDOFF (new pickup), MILESTONES (Slice-2 line → done), this plan →
  `docs/fork/plans/AUTHORSHIP-roster-slice2.md`, evidence `docs/fork/evidence/authorship-slice2/`, memory.

## Non-goals (explicit)
- **No anti-spoofing.** Author strings (email headers, docx props, tracked-change authors) stay untrusted/
  forgeable — they inform candidacy, never override the roster; a trusted authorship channel (WOPI-stamped)
  remains future work (ADR-F048 §Consequences, unchanged).
- **No re-ingestion / no `structured_content` schema change** — email metadata is read as-is; docx props read
  live from bytes.
- **No new HTTP route, no SSE/frame change, no new dependency** (python-docx already a dep).
- **No coverage/anchoring gate change** — classification is additive labeling only.
- No data-backfill migration (the lazy seed covers existing matters by design).

## Verification (DoD — shown, not asserted)
1. **Backend (dev image `lq-ai-api-dev`, `./api`→/app + `./skills`→/skills:ro, throwaway pgvector DB):**
   migration `0077` upgrade→downgrade→upgrade round-trip; the new/updated tests above; full api suite green
   with counts quoted; **ruff (repo-root config) + mypy clean**. Confirm **no `test_endpoints`/`test_openapi`
   change** and grant sets still disjoint.
2. **Web:** `npm run check` 0 errors; vitest green (+`other` helper cases); prettier clean. **Rebuild the
   prebuilt `web` container** before any UI/Cypress.
3. **Live (rebuild api+arq on the migration, then web):** a DeepSeek scenario over a matter whose returned
   `.docx`/email carries a third-party author + the operator pre-seeded — assert the agent calls
   `get_document_metadata`, the negotiation/hand-back render groups by side incl. a THIRD-PARTY bucket, and a
   `record_matter_participant(side='other')` lands; Cypress shows the **Third party** badge in the Participants
   section (light+dark). Evidence → `docs/fork/evidence/authorship-slice2/`.
4. **Fresh-context adversarial review (ultracode 4-dim × verify)** incl. the mandatory security + simplification
   pass: `get_document_metadata` matter-scoped/404, untrusted strings never auto-elevate to `ours`; auto-seed
   identity provably session-sourced (`trust='confirmed'`, `user_id` from the run owner, never model input);
   audit counts/IDs+side-only (no name/email/clause text); seed idempotency (no duplicate operator row under
   concurrent runs); no leaked secrets; no dead/dup code (the promote-not-duplicate call). Blockers/should-fixes
   fixed or deferred on record.
5. **ADR-F048 addendum** + HANDOFF + MILESTONES + plan-doc + memory updated; merge under the **ADR-F005 gate**
   (`gh pr create/merge --repo sarturko-maker/lq-ai-fork`).

## Recommended order
mig `0077` + `'other'` literal/enum → `ensure_operator_participant` + composition seed → promote
`classify_edits` + `other` bucket (editor render) → negotiation render classification (`commercial_tools`) →
`get_document_metadata` tool + grant + doctrine → backend tests green → frontend `other` side + helpers + tests
→ web checks → rebuild api+arq+web → live DeepSeek scenario + Cypress → evidence → ADR addendum / HANDOFF /
MILESTONES / plan-doc / memory → adversarial review → merge.
