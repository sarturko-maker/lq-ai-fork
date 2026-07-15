# VM2-B — matter-memory coaching, area-agnostic (task #526)

Fix for the maintainer's VM-UAT observation: **"No memory recorded despite a long conversation"**
(custom *IT Procurement* area). Planned via a 6-way code-seam investigation + adversarial critique
(2026-07-15). **Nothing here is implemented yet** — this is the plan for maintainer edit.

## The diagnosis (sharpened by the investigation — it is NOT what the task title says)

The task title frames this as *area*-specific. The code says otherwise: the real trigger is
**wiki-emptiness, not practice area.** Verified against current `composition.py`:

- The matter-memory **write tools are already correct and area-agnostic** — `update_matter_memory`,
  `record_matter_fact` (+ consolidate/read/roster/doc-summary siblings) are granted to *every*
  matter-bound run inside one `if binding is not None:` block (`composition.py:972-1045`), with **zero
  practice-area branching**, each routed through `guarded_dispatch`. Capability is present everywhere.
  **Do not touch this path.**
- The **only prose in the whole file that names `update_matter_memory`** is a single parenthetical
  buried inside the `MATTER_MEMORY_PROMPT` *data fence* (`composition.py:397`) — and
  `render_memory_tiers` emits that fence **only when the wiki is already non-empty**
  (`if matter_wiki and matter_wiki.strip():`, `composition.py:516`).
- So a **fresh matter (empty wiki) in ANY area** gets the write tool but **zero coaching to use it** —
  a genuine **chicken-and-egg**: nothing tells the agent to write memory until a wiki already exists,
  and the wiki never gets a first write. The custom *IT Procurement* area merely **compounds** it (it
  also lacks the `matter-memory` SKILL, bound only to the 5 seeded areas via mig `0069`'s hardcoded
  `_AREA_KEYS`), but the doctrine-layer gap is area-independent.
- **There is NO standalone `MATTER_MEMORY_DOCTRINE` constant today.** The asymmetry with
  `MATTER_ROSTER_DOCTRINE` — appended **unconditionally** at `composition.py:568`, which is exactly
  why participants *were* recorded while memory was not — **is the bug.**

Good news for the fix: one unconditional doctrine constant closes the reported symptom for **every**
area at once, deterministically.

**Honesty caveat (from the critique):** the evidence proves *coaching-absent from the code*; it did
not trace the actual failing VM run to confirm the tool was *granted-and-never-called* vs.
*called-and-errored*. A 30-second glance at the VM run log rules out a second cause before we close #526.

## Goal
Break the coaching asymmetry: every matter-bound run — any area, empty wiki included — is coached to
keep its working memory current with `update_matter_memory` / `record_matter_fact`, mirroring how the
roster doctrine already coaches `record_matter_participant`.

## Non-goals
- **No change to the write path / tool grants** (`composition.py:972-1045`) — already correct.
- **No change to the `MATTER_MEMORY_PROMPT` data fence or its empty-wiki gate** (`:516`) — an empty
  wiki *should* still inject an empty DATA block into nothing; that gate is a different concern and is
  not superseded by the doctrine.
- **No profile-manifest edit** — the originally-proposed "bind the skill in the manifests" is a
  **dead end**: `profiles/blank` has no bindings block and its apply branch hardcodes `skills=[]`, and
  the custom `POST /practice-areas` path binds zero skills by design. Manifest edits only touch
  `area`-kind profiles, which already list `matter-memory`. See Decision 3.
- No migration. No middleware change (middleware is for gated DATA tiers — routing coaching through it
  would re-introduce a gate). No `record_document_summary` empty-workspace bootstrap (same pattern,
  distinct + shallower bug → backlog). No `RECOMMENDED_LIBRARY_SETS` cosmetic edit (display-only).

## The change (tight S slice)

1. **New constant `MATTER_MEMORY_DOCTRINE`** in `api/app/agents/composition.py`, defined beside
   `MATTER_ROSTER_DOCTRINE` (~`:270-286`). **Minimal, in the exact register of the roster doctrine** —
   a *when-to-reach-for-it* nudge that **also carries the tightness cue**, but does **not** re-teach the
   full craft:
   > As you learn durable facts about this matter, keep its working memory current with
   > `update_matter_memory` — a brief living one-pager, fold facts in rather than append — and record
   > dated, supersede-able facts with `record_matter_fact`.
   Name only those two tools; leave `consolidate_matter_memory` and the deeper fold/supersede *craft* to
   the SKILL. The "brief living one-pager, fold don't append" clause is load-bearing: a custom area that
   gets **only** the doctrine (not the full skill) must still be coached to keep it *tight*, or we trade
   "no memory" for "bloated memory." **Wording must not contradict `skills/matter-memory/SKILL.md`**
   (e.g. never imply plain "append") — the two must reinforce, not fight (Decisions 2 + 4).

2. **Append it unconditionally** in `system_prompt_for`'s `if binding is not None:` block
   (`composition.py:564-572`), positioned **before** the conditional `TABULAR_FILL_DOCTRINE` (`:572`).
   Because production calls the same `system_prompt_for` base (`:1227-1229`) and the binding-block
   doctrines are the run-invariant **static base** (the DATA tiers ride `TierMemoryMiddleware`
   separately), this reaches production faithfully with no middleware touch.

3. **Update the docstring** at `system_prompt_for` (`:552-562`) to list the new doctrine.

4. **Proactive-tightness receipt (folded in from "B", decision 2026-07-15 — not backlogged).**
   In `matter_memory_tools.py._update_matter_memory` (~`:150`), extend the success receipt with a
   deterministic high-water mark, e.g. *"(12,400 / 16,000 chars — consolidate soon if it keeps growing)"*
   once the wiki passes a threshold (say 75% of `MATTER_WIKI_MAX_CHARS`). CLAUDE.md discipline is to prune
   *before* the file rots, not to wait for the hard reject at 16k. Small, deterministic, no schema change.
   Add a unit-test assertion on the threshold wording.

That alone closes the reported bug for every area and keeps the wiki tight by construction.

## Decision 3 borderline / recommended fast-follow (surface, don't silently bundle)

**Secondary hardening — baseline skill, NOT manifests.** To upgrade custom/blank areas from the terse
doctrine to the *full* `matter-memory` craft skill, the only seam that structurally works is a
composition-seam union (mirrors how the **tools** are already made unconditional via
`_MATTER_SCOPE_TOOL_NAMES`, `capabilities.py:309-319`):

- add `BASELINE_SKILL_NAMES = frozenset({"matter-memory"})` and union it into `bound_skill_names`
  right after the `practice_area_skills` query (`composition.py:~777-787`), still filtered through
  `known_skill_names` so a registry missing the skill degrades to silence (never crashes), and
  set-unioned so a manual admin binding doesn't duplicate.
- no migration, no manifest edit, no Library adoption (composition resolves skills from the in-memory
  registry, not `org_library_entries`).
- one guard test: a brand-new `PracticeArea` with zero `practice_area_skills` rows still resolves
  `matter-memory` into its skill set (reuse the custom-area pattern at
  `test_agent_composition.py:2009-2078`).

**Recommendation:** include it in **this** slice only if kept to that single constant + one test;
otherwise ship the doctrine alone and fast-follow. It's a genuine improvement for custom areas but a
*distinct* concern from the reported bug. (Leaning: bundle it — it's ~10 lines and removes the "custom
area silently lacks the skill" trap permanently.)

## Verification / DoD (ADR-F005 gate)

- **Primary gate — deterministic pure-function unit test** (no DB, no model), mirroring
  `test_system_prompt_assembly` (`test_agent_composition.py:249-275`):
  build a `MatterBinding`, call `system_prompt_for(binding)` with an **empty/omitted wiki** and
  `area=None`, assert `"update_matter_memory" in prompt` (+ `"record_matter_fact"`) and one stable
  prose marker. **RED today** (fragment absent for empty wiki), **GREEN after** the constant lands.
  Add a second assertion with a generic custom `AreaAgentSpec` to prove area-independence.
- **Required drift-guard update:** extend the `prompt.endswith(...)` concatenation in
  `test_system_prompt_assembly` (`:265-271`) to include the new constant **in its exact insertion
  position** (before the tabular doctrine; the endswith uses `tabular_enabled=False`, so it stays valid
  once the constant is added to the chain). This is the one guard that silently mis-pins if missed.
- If the baseline-skill union ships: add the fresh-custom-area skill-resolution guard test above.
- **Do NOT gate on** `test_matter_memory_scenario.py` — it's provider-marked, Commercial-only,
  non-deterministic, and never exercises the empty-wiki or custom-area path.
- **CI commands quoted** (in-container, **repo root** so root `ruff.toml` line-length 100 is used —
  the recurring 88-vs-100 trap): `ruff format --check` + `ruff check` + full `tests/agents/` counts.
- **No image rebuild strictly needed** for behavior (prompt is code, api-only) — but run the
  container suite for `api`; if verifying live, rebuild `api` only + `docker image prune -f` (dangling).
- **Live check (optional, cheap):** a fresh matter in a custom area, short conversation, confirm the
  Matter File / Matter Facts now populate (and confirm from the VM run log the tool is actually called
  — closes the honesty caveat).
- **Adversarial review incl. mandatory security + simplification pass:** trivial surface (a constant +
  an append); confirm no craft-conflict with SKILL.md, no stray files, doctrine text carries no
  secrets. No ADR needed (this restores intended behavior; it doesn't make an architectural call) —
  a one-line comment at the code seam citing #526 suffices.
- HANDOFF + memory updated.

## Files
- EDIT `api/app/agents/composition.py` — new `MATTER_MEMORY_DOCTRINE` constant (~`:286`), unconditional
  append in the binding block (~`:571`), docstring (`:552-562`); *(optional)* `BASELINE_SKILL_NAMES`
  union (~`:787`).
- EDIT `api/tests/agents/test_agent_composition.py` — new empty-wiki RED→GREEN test + `endswith`
  drift-guard extension; *(optional)* the baseline-skill guard test.
- NO edits to the tool-grant block, `MATTER_MEMORY_PROMPT`, the manifests, or any migration.

## Tightness & the tier budget (resolved 2026-07-15)

Matter memory is effectively a **CLAUDE.md for the matter**, injected alongside **House Brief** (company)
and **Practice Playbook** (area). It must stay tight. Findings:

- The matter wiki **already has** the right discipline: a **deterministic 16,000-char cap**
  (`MATTER_WIKI_MAX_CHARS`, `schemas/matter_memory.py:29`), **reject-not-truncate** (the model must
  consolidate, never a silent cut), a `consolidate_matter_memory` prune tool, and a "living one-pager"
  skill. This slice only *reinforces* it (change 1's tightness clause + change 4's high-water receipt).
- **No single cross-tier "memory budget" is warranted** (decision): per-tier deterministic caps already
  bound the total deterministically (it's their sum); a dynamic shared budget adds complexity *and*
  non-determinism (one tier starving another, same input → different injection). The real risk is a
  **per-tier cap set wrong** — and one is:
- **House Brief is capped at 200,000 chars (~50k tokens)** (`api/app/api/organization_profile.py:63`)
  and injected **whole** into **every** prompt (`composition.py:603`, no injection-time trim) — 12.5× the
  matter wiki, on every run. That is the actual bloat bug. Split out as **task #532 (VM2-G)**: lower the
  write cap to a one-pager size (proposed 32k chars; maintainer confirms), reject-at-write not
  silent-inject-trim, + audit the other tiers' caps. **Not part of VM2-B** (different endpoint/tier), but
  it is the higher-impact tightness fix.

## Open decisions for the maintainer (defaults chosen — confirm/override)
1. **Doctrine scope** — name `update_matter_memory` + `record_matter_fact`, leave `consolidate` to the
   skill? *(recommended)*
2. **Register** — minimal *when-to-reach-for-it*, consistent with `SKILL.md` (mirror the roster
   doctrine), not a fuller re-teach? *(recommended — avoids conflicting double-coaching)*
3. **Baseline-skill union** — ship in this slice or fast-follow? Confirm the profile-manifest route is
   abandoned. *(recommended: bundle if it stays 1 constant + 1 test)*
4. **Tightness** — RESOLVED (2026-07-15): the doctrine carries the "brief one-pager, fold don't append"
   cue (change 1); add the high-water-mark receipt (change 4, folded in, not backlogged); no cross-tier
   budget; House Brief cap tightened separately as #532. *(The earlier "strip the redundant `:397` clause"
   question is moot — leave the clause; it's harmless and stripping churns the oracle tests.)*
5. **`record_document_summary` empty-workspace bootstrap** (same pattern, shallower) — backlog line, not
   this slice? *(recommended)*
