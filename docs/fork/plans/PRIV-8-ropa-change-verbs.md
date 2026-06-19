# PRIV-8 — ROPA change verbs: the agent can *change/retire*, not only *add*

**Status:** PRIV-8a DELIVERED (PR open, branch `priv-8a-ropa-change-verbs`); PRIV-8b + PRIV-9 PENDING ·
**Date:** 2026-06-19 · **Decisions taken:** change-verbs first; **soft-retire / supersede** semantics
(maintainer choice — global retire is correct, soft-retire so it's auditable). ADR landed as **F023**
(F022 was already the data-flow ADR).

## Context — the gap the group chat surfaced

The product thesis from the group chat: a lawyer should be able to say *"we moved off mixpanel and use
hotjar now"* (or forward the email that says it) and the agent updates the register. Three scouts
confirmed the blocker is **not** the model:

- The Privacy/ROPA agent has **14 tools, all create / link / tag / read** (`api/app/agents/ropa_tools.py:88`).
  There is **no edit, delete, retire, unlink, or replace** verb. So "change mixpanel to hotjar" cannot
  succeed: the best the agent can do is *add* Hotjar and leave Mixpanel linked → the register lists both.
- The register read surface (`api/app/api/ropa.py`) and the agent `list_*` tools both return every row —
  there is no notion of a retired row to hide.
- The harness can't seed a *pre-existing* register (every test builds from empty), so there's no substrate
  to test an "update" against. `snapshot_register` does expose entities **by name** (`ropa_eval.py`), which
  the test needs.

The "side-panel chat + live-updating view" UX is mostly already wired (chat is already a panel; the SSE
stream already carries live thinking + tool-call rows) and is captured here as a **separate follow-up
slice (PRIV-9)** — it is independent of and downstream from the capability.

## Goals

1. Give the Privacy agent **guarded change verbs**: retire an entity, unlink an entity from an activity —
   so a vendor/system can be *replaced*, not just *added alongside*.
2. Keep the register **honest and auditable**: never destroy a row (soft-retire); retired rows vanish from
   the live register but remain for audit. Every write stays on the ADR-F018 guarded, code-validated path.
3. Prove it end-to-end with the maintainer's literal test — **"we moved off mixpanel and use hotjar now"** —
   on a live provider, asserting by name that Mixpanel is gone-from-live and Hotjar is linked.

## Non-goals (explicit; some → Backlog)

- **No un-retire / restore verb** in v1 (Backlog — reversibility is a later slice + its own audit story).
- **No edit-in-place** (rename/field-edit of an existing row) — rejected in ADR-F023 (rewrites a shared
  global row's identity/provenance). "Change" = add-new + retire-old.
- **No category unlink** (`remove_data_category_from_activity`) in v1 — not needed for the vendor/system
  swap; Backlog.
- **No frontend** in PRIV-8 — the co-visible/live-updating cockpit is PRIV-9.
- **No autonomy change** — "system proposes, user owns" holds; the agent still only acts inside a
  matter-bound, guarded run.

## Key decisions (the ADR-F023 content)

### D1 — Soft-retire, not delete
Add a nullable `retired_at TIMESTAMPTZ` (+ nullable `retirement_reason TEXT`) to the four **mutable**
entities: `processing_activities`, `systems`, `vendors`, `transfers`. `retired_at IS NULL` = live.
A retire sets `retired_at = now()`. The row is never deleted — audit/provenance survive (ADR-F018/F019).
The two **label vocabularies** (`data_subject_categories`, `data_categories`) get no retire column — they
are immutable shared labels; "we stopped processing X" is an unlink, deferred (Backlog).

### D2 — Reads exclude retired by default, everywhere
- API list endpoints (`/processing-activities`, `/systems`, `/vendors`, `/data-flow`,
  `/programme-summary`, `/export`) filter `retired_at IS NULL`. List endpoints accept `?include_retired=true`
  (default false) for an audit view; the per-entity `GET /{id}` returns the row regardless (deep-links and
  audit still resolve) with `retired_at` populated.
- The agent `list_*` tools filter retired by default (the agent works on the *live* register and must not
  re-link a retired vendor). They append a one-line `(N retired, hidden)` footer so the agent knows they
  exist (and won't recreate one).
- `_load_register` (export/summary/graph) filters retired. A transfer whose recipient vendor is retired
  renders with **no recipient** (the read treats a retired cross-referenced entity as absent).
- Read DTOs gain `retired_at: datetime | None` (`SystemRead`, `VendorRead`, `ProcessingActivityRead`,
  `TransferSummary`) so PRIV-9 can render retired rows muted under `include_retired`.

### D3 — The verb set (6 new guarded tools)
All go through `guarded_dispatch` exactly like the existing tools (R6 grant set, R5 live re-check, one audit
row carrying tool/IDs/**size** — never raw values). All parse UUIDs and reject an unknown id with a
fix-and-retry message; all are **idempotent** (retiring an already-retired row / unlinking a non-link is a
friendly no-op, mirroring the existing link idempotency).

- `retire_vendor(vendor_id, reason=None)` · `retire_system(system_id, reason=None)`
- `retire_processing_activity(activity_id, reason=None)` · `retire_transfer(transfer_id, reason=None)`
- `unlink_vendor_from_activity(processing_activity_id, vendor_id)` — hard-delete the one M:N join row
  ("this activity no longer discloses to this vendor"), audited.
- `unlink_system_from_activity(processing_activity_id, system_id)` — symmetric.

`ROPA_TOOL_NAMES` grows from 14 → 20; the composition grant (`composition.py:214`) is unchanged (still
grants the whole set to a Privacy matter).

### D4 — The swap is *composed*, taught by a skill
There is deliberately no single `replace_vendor` macro. The agent composes primitives — and a new
`ropa-maintenance` skill teaches the method: *find the old one → add the replacement → link it → unlink the
old one from each affected activity → retire the old one if the company no longer uses it anywhere → confirm
with `list_*` → report exactly what changed.* **Never leave both the old and new linked.** Bound **test-only
first** (PRIV-7 precedent); a default-binding migration follows once validated.

## Slice decomposition (3 PRs)

### PRIV-8a — capability + soft-retire (CI-gated, no live provider needed)
The whole guarded change capability, provable without a gateway key.
- **Migration** (new alembic rev): add `retired_at` + `retirement_reason` to the 4 tables. Verify on a
  throwaway pgvector container; rebuild `api` + `arq-worker` + `ingest-worker` together (dev rule).
- `api/app/models/ropa.py`: add the two columns to the 4 models.
- `api/app/schemas/ropa.py`: add `retired_at` to the 4 Read DTOs.
- `api/app/agents/ropa_tools.py`: 6 new tools + helpers (`_retire`, `_unlink_vendor`, `_unlink_system`),
  add names to `ROPA_TOOL_NAMES`, add the `(N retired, hidden)` footer + retired filter to the `list_*`
  helpers.
- `api/app/api/ropa.py`: retired filter on the list/load/graph/summary/export queries + `include_retired`
  query param; `retired_at` flows through the Read DTOs.
- **ADR `docs/adr/F023-ropa-change-verbs-soft-retire.md`** (new): D1–D4, considered options (hard-delete,
  edit-in-place, soft-delete-joins), consequences.
- **CI unit tests** (`api/tests/...`, non-provider): retire sets `retired_at` + the entity drops out of the
  list/read; idempotent re-retire; `unlink_*` removes exactly one join row + idempotent re-unlink; API list
  hides retired and `include_retired=true` shows it; `transfer` with a retired recipient renders no
  recipient; guard grant set contains the 6 names.

### PRIV-8b — the live mixpanel→hotjar proof + the skill
- `skills/ropa-maintenance/SKILL.md` (new): the change method above (folder name == `name:`).
- `api/tests/agents/scenarios/harness.py` (or `ropa_eval.py`): `seed_ropa_register(factory,
  source_project_id, …)` — plant a "Product Analytics" activity + a **Mixpanel** vendor
  (`processor`/`in_place`/US) linked to it (and a Mixpanel `analytics` system). Extend
  `snapshot_register`/`ActivityView` to expose each entity's `retired` state.
- `api/tests/agents/scenarios/test_ropa_update_scenario.py` (new; `@pytest.mark.provider` +
  `LQ_AI_GATEWAY_KEY` skipif — **not** notice-gated, the register is synthetic): seed → prompt *"We've moved
  off Mixpanel — we use Hotjar now for product analytics. Update the register."* → snapshot → assert **by
  name**: Hotjar present + linked to the activity; Mixpanel unlinked from the activity and retired. Arms:
  `deepseek` no-skill (baseline), `deepseek` +skill, optionally `deepseek-pro` +skill. `bind_area_skill`
  test-only in `try`/`finally` (PRIV-7 pattern).
- Evidence → `docs/fork/evidence/priv-8/` (behavior reports + FINDINGS, incl. an honest *did it leave the
  register coherent?* read — and whether the no-skill arm honestly reports the gap vs. silently half-does it).

### PRIV-9 — cockpit: co-visible chat + live-updating register (frontend; separate milestone entry)
Independent of 8a/8b. Make chat and the ROPA register **co-visible** (split, not the current
mutually-exclusive tabs in `ConversationHost.svelte`) and give `RopaRegister.svelte` a **poll-while-a-run-is-
active** refresh (mirror the conversation's existing poll) so writes appear as the agent works; render
retired rows muted under `include_retired`. Paneforge infra already exists at the shell. Own ADR if it
retires the tab IA. (Captured in MILESTONES; planned after the capability lands.)

## Verification (per slice; ADR-F005 full gate)

- **8a:** `cd api && ruff format && ruff check && pytest` (counts shown); migration verified on throwaway
  pgvector then workers rebuilt; fresh-context adversarial **+ security + simplification** pass (this is a
  guarded-write path → deeper security pass: the new verbs can only act inside the granted set, audit leaks
  nothing, reads can't be tricked into showing/hiding the wrong rows, no SQL built by string).
- **8b:** the live run executed on the dev gateway with evidence in the PR (the register before/after by
  name); CI self-skips the provider test.
- **9:** `npm run check` + vitest + headed before/after screenshots (light/dark × wide/narrow); rebuild the
  `web` container before screenshotting.
- HANDOFF.md updated at the end of each slice; merge per ADR-F005 against `sarturko-maker/lq-ai-fork`.

## Risks / edges

- **Retired entity still cross-referenced** (a transfer's recipient vendor; a retired system on a live
  activity). Handled by D2 (reads treat a retired cross-ref as absent) — covered by a unit test.
- **Global retire vs. one matter.** The register is deployment-global (ADR-F019): retiring Mixpanel retires
  it company-wide, which is the correct reading of "we moved off Mixpanel." The skill says so; the agent
  reports it.
- **Parallel-tool-call deadlock** (the PRIV-7 HIGH follow-up) is *not* fixed here but the new verbs touch the
  same guarded path — the unit tests run serially and the skill discourages racing writes; note it in the PR.
- **Migration discipline:** never run `alembic upgrade` against the live dev DB; verify on throwaway, rebuild
  workers.
