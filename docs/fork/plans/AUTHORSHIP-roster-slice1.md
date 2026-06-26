# Plan — Authorship Slice 1: matter **who-is-who roster** + hand-back author resolution (ADR-F048)

## Context

In a real negotiation, **many people redline a document, not just two counsels** (our lead + our associate
+ our client's GC, vs. their counsel + their client). Today the agent cannot tell them apart. The editor
Slice-5 hand-back tool uses a **naive filter** — `review_edited_document_tools.py:121`:
`changes = [c for c in state.changes if c.author != DEFAULT_AUTHOR]` — which treats **every** non-agent
author as "the supervising lawyer". A counterparty's (or an unknown third party's) tracked changes present in
a handed-back doc would be silently **incorporated as authoritative** (the over-trust defect, flagged in
`MILESTONES.md:525` and ADR-F047 Slice-5). The maintainer asked for a proper model: the agent learns who is
who from the signals it already sees (a docx's tracked-change author strings, an email's `From:` line, and the
user's own statements like "this is the other side's redline"); when it **isn't sure, it checks in with the
user**; and the **roles live in matter memory in a separate section the user can amend**.

Five subsystem maps established the ground truth:
- **Memory tier** (ADR-F042/F044): `matter_memory_entries` holds agent-written facts (`trust=normal`) + human
  corrections (`trust=human-pinned`). Facts are **agent-write-only** (no human-create endpoint); the human can
  only pin a free-text correction or retire. → too weak for a roster the lawyer must directly set.
- **Author seam**: authors are plain strings on `StateOfPlay.TrackedChange.author` /
  `CounterpartyComment.author` (`negotiation_service.py:96,104`, default `"unknown"`). Agent =
  `DEFAULT_AUTHOR="LQ.AI Commercial counsel"` (`redline_service.py:69`); lawyer = WOPI `UserFriendlyName`;
  counterparty = whatever their `.docx` carries. Two consumers: `_lawyer_edits` (hand-back) and
  `_render_state_of_play` (C5a, `commercial_tools.py:585`).
- **Email signal is already agent-visible**: `read_document()` returns the `From:` line inline in the email
  text (`pipeline/readers/_message.py:179`). No new ingestion code is needed for email attribution — it is
  doctrine. (A structured `get_document_metadata` tool is a *Slice-2* nicety, not required now.)
- **"Check in with the user" needs no new machinery**: there is **no** langgraph interrupt and **no**
  `ask_user` tool. The working pattern is *the agent asks in its text answer, the run ends, the user replies →
  a new run resumes on the same `thread_id` from the checkpoint* (`runner.py:613`, `agent_runs.py:330`). So
  check-in = a prompt doctrine + the existing `record_matter_participant` tool to capture the answer.
- **Memory panel** (`MemoryPanel.svelte`): four sections, `load(quiet)` + `loadGeneration` out-of-order
  guard + `runActive` poll/reconcile; pure helpers exported from `<script module>` and unit-tested (no
  `@testing-library/svelte`); every model body via `renderModelMarkdown`.

**Maintainer rulings (AskUserQuestion, 2026-06-26):** (1) **dedicated roster table**; (2) **side drives
treatment** — `ours` (our team incl. our client) → incorporate; `counterparty` → negotiation position, never
silently adopted; `unknown` → ask; a free-text role label rides along; (3) **direct edit, human wins** — the
lawyer adds/edits/removes; a human-set entry is `confirmed` and the agent won't override it (ADR-F042 "human
owns it after the write"); (4) **Slice 1 = foundation + hand-back resolution**; **defer to Slice 2** the C5a
negotiation-path classification + the structured email-metadata tool.

## Approach

A **dedicated `matter_participants` table** (auto-write-then-correct, ADR-F042), two guarded agent tools + a
prompt-injected roster + doctrine, **roster-based author classification** replacing the naive hand-back
filter, **human add/edit/remove** endpoints, and a **Participants** section in the Memory panel. New fork
**ADR-F048** (supersedes the ADR-F047 naive filter). One migration (`0076`); no new dependency.

### Backend — data model (migration `0076`, head is `0075`)
New table `matter_participants` + SQLAlchemy model `MatterParticipant` (in `api/app/models/project.py`,
beside `MatterMemoryEntry`):
- `id` UUID PK · `project_id` UUID FK→projects (CASCADE, indexed) · `display_name` Text
- `aliases` JSONB — the **match set**: author strings + emails we resolve against (normalised lower/trim in
  code, not SQL) · `organization` Text? · `role_label` Text? (descriptive, e.g. "Lead counsel", "Client GC")
- `side` Text **CHECK ∈ {'ours','counterparty','unknown'}** (the treatment driver; additive-extensible — a
  comment notes 'other' can be added later, mirroring the `fact_type` CHECK convention in `0070`)
- `trust` Text **CHECK ∈ {'inferred','confirmed'}** — `inferred`=agent-written, `confirmed`=human-set; **human
  wins** (agent must not override a `confirmed` row) · `author` Text — `'agent'` or the user UUID (session,
  never model input — mirrors the corrections `author` convention) · `source_citation` Text?
- `created_at` · `updated_at` · `superseded_at` Timestamp? (soft-remove; active = `superseded_at IS NULL`)
- Migration is module-level functions + a round-trippable downgrade (drop table), mirroring `0070`/`0073`.

### Backend — agent tools (`api/app/agents/matter_roster_tools.py`, NEW — mirrors `matter_fact_tools.py`)
- `MATTER_ROSTER_TOOL_NAMES = frozenset({"record_matter_participant", "list_matter_roster"})` (disjoint).
- `build_matter_roster_tools(session_factory, *, run_id, binding)` → guarded closures (R6 grant / R5 halt;
  counts/IDs-only `audit_action` — **never the name/email/role text**, identity is sensitive):
  - `record_matter_participant(name, side, role=None, organization=None, aliases=None, source=None)` —
    auto-write (`trust='inferred'`, `author='agent'`); validated by a Pydantic `RecordParticipantInput` (side
    ∈ enum; reject otherwise). **Human-wins guard:** if an active `confirmed` row already matches the
    identity, merge new aliases only — do **not** change its `side`/`role`. Matter-scoped, 404-conflated.
  - `list_matter_roster()` — active roster (so the agent sees who's known + the gaps).
- `classify_author(author: str, roster, *, agent_author=DEFAULT_AUTHOR) -> Literal['agent','ours',
  'counterparty','unknown']` — pure, Python-matched against normalised aliases (consistent with
  `search_matter_memory` doing Python matching, no model SQL). `==agent_author → 'agent'`; alias hit → that
  row's `side`; else `'unknown'`. Used by `review_edited_document` (this slice) and C5a (Slice 2).
- `load_roster_for_injection(...)` — a capped, counts-budgeted roster block (mirrors
  `load_pinned_corrections`) the composition root injects into the matter-bound prompt, so the agent always
  knows who's who.

### Backend — resolution rewire (the over-trust fix)
`api/app/agents/review_edited_document_tools.py`:
- `_review_edited_document` loads the matter roster, then `_lawyer_edits` (extended) **classifies every change
  / comment author** via `classify_author`: `agent` → excluded (the pending redline); `ours` → authoritative
  (incorporate, the Slice-5 trusted-supervisor frame); `counterparty` → a separate "negotiation position —
  not your edits" bucket; `unknown` → a separate "unidentified author — ASK who this is before treating their
  edits as authoritative" bucket.
- `_render_supervised_edits` renders the three buckets distinctly with the doctrine cues; audit carries
  per-bucket **counts only**. This is the real replacement of the naive `author != DEFAULT_AUTHOR` line.

### Backend — composition (`api/app/agents/composition.py`)
- Grant `build_matter_roster_tools(...)` to **every matter-bound run** (all areas), beside the matter-memory
  tools. Inject the roster block. Add `MATTER_ROSTER_DOCTRINE` (after `MATTER_REVIEW_DOCTRINE`): *maintain the
  who-is-who roster; record the sender when you read an email and whoever the user names; on a re-read the
  tool labels each author ours/counterparty/unknown — incorporate OURS, treat COUNTERPARTY as a negotiation
  position, and for UNKNOWN authors ASK the user, then `record_matter_participant` the answer; human-confirmed
  entries are authoritative — never override them.*

### Backend — human-amend endpoints (`api/app/api/matter_roster.py`, NEW, on the `/matters` router)
All `ActiveUser` + `_load_visible_project` (owner-scoped, **404** cross-user/archived); `trust='confirmed'`,
`author`=session user (structural, never model); counts/IDs-only audit:
- `POST   /matters/{project_id}/roster` — create a participant (name, side, role?, org?, aliases?).
- `PATCH  /matters/{project_id}/roster/{entry_id}` — edit (sets `trust='confirmed'`).
- `POST   /matters/{project_id}/roster/{entry_id}/retire` — soft-remove (`superseded_at=now`, idempotent;
  matches the corrections/facts retire convention).
- **Read folds into the existing composite** `GET /matters/{project_id}/memory`: add a `roster:
  MatterParticipantRead[]` field (active rows) so the panel still loads everything in one fetch under its
  existing poll/reconcile guard. Pydantic `MatterParticipantRead` + the request bodies in
  `api/app/schemas/matter_memory.py`.
- Register the router in `api/app/api/__init__.py`; update **`test_endpoints.IMPLEMENTED_ROUTES`** +
  **`test_openapi.EXPECTED_PATHS`** (3 new path strings).

### Frontend — Participants section in the Memory panel
- `web/src/lib/lq-ai/types.ts`: `MatterParticipantRead` + `roster` on `MatterMemoryRead`.
- `web/src/lib/lq-ai/api/matterMemory.ts`: `createParticipant` / `updateParticipant` / `retireParticipant`
  (read already arrives via `readMatterMemory`).
- `web/src/lib/lq-ai/components/matter/MemoryPanel.svelte`: a **Participants** section (after Working
  summary) — each row shows `display_name`, a **side badge** (Ours / Counterparty / Unknown, tone-coloured
  via `--color-status-*`), `role_label`, `organization`, the `aliases` (match strings), and a
  confirmed/inferred indicator. Controls: **+ Add participant** (structured form: name, side `<select>`,
  role, org, aliases) · **Edit** (inline form) · **Remove** (confirm `Dialog`). Writes gated on
  `canWrite(runActive)` (consistent with corrections; at amend-time the run is settled). New pure helpers in
  `<script module>` (`sideLabel`, `sideTone`, `participantTrustLabel`, `isParticipantSubmittable`,
  `parseAliases`) — unit-tested. The `loadGeneration`/poll/reconcile guard already covers the new field.

### Critical files
- NEW: `api/app/agents/matter_roster_tools.py`; `api/app/api/matter_roster.py`;
  `api/alembic/versions/0076_matter_participants.py`; `api/tests/agents/test_matter_roster.py` (+ endpoint
  tests in `api/tests/test_matter_roster_api.py`).
- EDIT: `api/app/models/project.py` (model); `api/app/schemas/matter_memory.py` (Pydantic in/out);
  `api/app/agents/review_edited_document_tools.py` (classify, the over-trust fix);
  `api/app/agents/composition.py` (grant + inject + doctrine); `api/app/api/matter_memory.py` (add `roster`
  to the composite GET) + `api/app/api/__init__.py`; `api/tests/test_endpoints.py`,
  `api/tests/test_openapi.py`, `api/tests/agents/test_review_edited_document.py`,
  `api/tests/agents/test_agent_composition.py`.
- EDIT (web): `types.ts`, `api/matterMemory.ts`, `components/matter/MemoryPanel.svelte`,
  `__tests__/MemoryPanel-helpers.test.ts`; a Cypress spec (extend `c3-update-memory.cy.ts` or a new
  `authorship-roster.cy.ts`, live/non-CI).
- REUSE: `guard.guarded_dispatch`/`GuardContext`, `audit_action`, `_load_visible_project`, `DEFAULT_AUTHOR`,
  `read_state_of_play`, the `MemoryPanel` load/poll/reconcile + `<script module>` test pattern.
- DOCS: `docs/adr/F048-matter-participant-roster.md` (NEW); `docs/fork/HANDOFF.md`; `docs/fork/MILESTONES.md`
  (retire the `:525` backlog line → this slice; add the Slice-2 follow-on line); commit this plan to
  `docs/fork/plans/AUTHORSHIP-roster-slice1.md`.

## Non-goals (explicit — deferred)
- **C5a negotiation-path classification** (label authors in `extract_counterparty_position` /
  `_render_state_of_play`) — **Slice 2** (it already has the no-silent-action gate; lower risk to defer).
- **Structured email-metadata tool** (`get_document_metadata` exposing `Document.structured_content`) —
  Slice 2 polish; email `From:` is already agent-visible as text for Slice 1.
- **Anti-spoofing of the author string.** A docx author string is untrusted model input; a counterparty
  could set theirs to our lawyer's name. The roster *reduces* over-trust (unknown → ask, instead of blind
  trust) but cannot cryptographically verify identity. A trusted authorship channel (e.g. the
  WOPI-authenticated editor stamping a verifiable identity) is future work — **called out honestly in
  ADR-F048**, not solved here.
- Auto-seeding the run-owner / WOPI user as an `ours` entry (nice-to-have; the ask-then-record flow covers
  the first hand-back). Only fold in if a clean seam appears; otherwise note it.
- No langgraph interrupt / new SSE frame / new run endpoint (check-in rides the existing thread resume).

## Verification (DoD — shown, not asserted)
1. **Backend (dev image `lq-ai-api-dev`, `./api`→`/app` + `./skills`→`/skills:ro`, throwaway pgvector DB):**
   migration `0076` upgrade→downgrade→upgrade round-trip; new `test_matter_roster` (tool auto-write;
   **human-confirmed-wins no-override**; `classify_author` agent/ours/counterparty/unknown incl.
   `DEFAULT_AUTHOR`; endpoints owner-scoped **404**; `trust='confirmed'`+session-author; **counts-only audit,
   no names/emails**); `test_review_edited_document` extended over a **three-author** docx (agent + ours +
   counterparty + unknown → ours incorporated, others surfaced separately, unknown triggers the ASK cue);
   composition test (granted to a **non-Commercial** matter-bound run + doctrine + injection); composite GET
   returns `roster`. Full api suite green; **ruff (repo-root config) + mypy clean**. Quote counts.
2. **Web:** `npm run check` 0 errors; `vitest` green (+ new helper cases); prettier clean. **Rebuild the
   prebuilt `web` container** before any UI/Cypress.
3. **Live (headed Cypress + real stack + DeepSeek/Atlas):** (a) the lawyer **adds/edits/removes** a
   participant in the Participants section (round-trips to the dedicated endpoints; light+dark screenshots);
   (b) a run where the agent **records a participant** from a chat statement, and a **hand-back whose doc
   carries a non-roster author** → the agent **surfaces it as not-ours and asks** (not silently incorporated)
   — verify via run steps / DB / audit. Evidence → `docs/fork/evidence/authorship-slice1/`.
4. **Fresh-context adversarial review** (4-dim × verify, ultracode) incl. the mandatory **security +
   simplification** pass: matter-scope/404 on every roster endpoint; `trust='confirmed'`/`author` provably
   session-sourced; **audit counts/IDs-only (no identity text)**; untrusted-author-string posture (no
   auto-elevation to `ours` that bypasses the ask/confirm path); no leaked secrets; no dead/dup code.
   Blockers/should-fixes fixed or deferred on record.
5. **ADR-F048** drafted (supersedes the ADR-F047 naive filter; references ADR-F042 auto-write-then-correct +
   ADR-F028 untrusted input); **HANDOFF + MILESTONES + memory** updated; merge under the **ADR-F005 gate**
   (CI green; suites quoted; live evidence; `gh pr create --repo sarturko-maker/lq-ai-fork`).

## Recommended order
migration `0076` + `MatterParticipant` model → `matter_roster_tools` (record/list/`classify_author`/inject)
→ composition grant + inject + doctrine → roster endpoints + composite-GET `roster` field + meta-tests →
backend tests green → rewire `review_edited_document` (classify, the over-trust fix) + its tests → frontend
Participants section + helpers + api client + types → web checks → rebuild web → live Cypress (amend +
ask-on-unknown) → evidence → ADR-F048 / HANDOFF / MILESTONES / plan-doc / memory → adversarial review → merge.
