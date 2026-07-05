# F054 — Per-matter capability toggles + the capability-inventory abstraction

- Status: accepted (maintainer-ratified SETUP ladder, 2026-07-05); D1 superseded-by-F062 (tool-group
  availability only — grants stay code)
- Date: 2026-06-30
- Deciders: maintainer (Arturs), agent
- Milestone: **Capability panel + in-matter Tabular review** (Phase 1). Builds on **ADR-F002**
  (practice-area = agent identity), **ADR-F010** (per-area Deep Agent), **ADR-F016** (skills activation
  registry backend), **ADR-F049** (memory tiers / `TierMemoryMiddleware`). Companion plan:
  `docs/fork/plans/CAPABILITY-PANEL-slice.md`.

## Context

The practice-area Deep Agent's capability set is fixed at composition (`compose_and_execute_run`): the
area's bound skills are always on (`practice_area_skills` → `area_spec.skills` →
`build_area_skill_wiring`); domain tools are granted by a hardcoded `if area_key == PRIVACY_AREA_KEY …
elif COMMERCIAL_AREA_KEY` branch that bakes a static `GuardContext.granted` frozenset; and playbooks are
not consumed at all (`Playbook`/`PlaybookPosition` data exists, the linear executor is FROZEN, and
`agent_config.playbooks` is validated but read nowhere).

The maintainer wants a cockpit panel where the AREA curates the AVAILABLE capabilities (skills, tools,
playbooks; MCP later) and the LAWYER toggles a subset on/off, **persisted per matter** ("system proposes,
user owns"). A "playbook" here is the firm's wish-list of preferred negotiation positions (NDA-review,
MSA-review) — reuse the existing `playbooks`/`playbook_positions` DATA, never the frozen executor.

This requires (a) a uniform capability identity, (b) an area↔playbook availability binding (none exists),
(c) per-matter toggle storage, (d) a read-only consumption path for playbooks, and (e) the toggles to
actually remove a capability from the agent at the existing guard/skill/tier seams.

## Considered options

1. **Per-matter `projects.capability_overrides` JSONB "disabled set"** (one column, no tables). Smallest
   diff; but tools-as-data still needs a model, the blob is unqueryable, and a disabled-only list silently
   re-enables on any key rename.
2. **Fully normalized: `practice_area_tools` + `practice_area_playbooks` + `matter_capability_toggles`.**
   Clean and uniform, but `practice_area_tools` duplicates code-canonical tool grants as data and forces a
   seed that must byte-match today's grants forever — a standing regression hazard.
3. **Hybrid (CHOSEN):** a normalized sparse `matter_capability_toggles` table (one row = one explicit
   deviation; absence = `default_enabled`) + a `practice_area_playbooks` availability binding (playbooks
   ARE rows and have no area binding); tool availability stays a per-area CODE map (the area-key branch +
   `*_TOOL_NAMES` frozensets are the truth); skills reuse `practice_area_skills`. One pure inventory
   module computes availability + resolves enabled, consumed by BOTH the API and `compose_and_execute_run`.
   Playbooks are consumed as a new read-only "Practice Playbook" tier on the `TierMemoryMiddleware` seam
   (ADR-F049); MCP/tabular are future inventory entries with no schema change.

## Decision outcome

Adopt **option 3**.

- **Per-matter, not per-run.** Toggles persist across the matter's conversations; the run-create API is
  unchanged; composition reads them at run start (so they apply to the NEXT run — a live run's `granted`
  frozenset is fixed). A per-run override is explicitly backlog (it would later ride `AgentRunCreate` like
  `budget_profile`).
- **Two-layer scope.** AVAILABLE = area-curated (skills via `practice_area_skills`; playbooks via the new
  `practice_area_playbooks` binding; tools via the per-area code group map). ENABLED = the lawyer's
  per-matter toggles overlaid on `default_enabled` (all available capabilities default ON except the MCP
  placeholder).
- **Off → genuinely removed at the source.** Skills filtered before `build_area_skill_wiring` (no source,
  absent from `ls`/prompt); tool groups not built (so absent from `GuardContext.granted`; R6 fail-closes
  with the existing `AgentToolNotGranted`); playbooks not injected. The hardcoded area-key tool branch
  becomes a data-driven loop over a tool-group map, keeping the per-group area-key guard so a misconfigured
  row can never cross-grant.
- **Playbooks reuse the DATA, read-only.** Enabled playbooks' preferred positions render as a new
  read-only "Practice Playbook" tier on `TierMemoryMiddleware`, data-only-fenced (no authority; treated as
  untrusted-shaped input), length-capped. No agent tool mutates a playbook. The FROZEN linear executor is
  not touched.
- **Privacy ROPA and Assessment are independent toggles** — Assessment degrades to empty lists when ROPA
  is off (it reads ROPA activity ids at runtime), never a crash.
- **Audit** rows carry kinds/keys/counts only — never playbook content or values.
- **MCP** is a visible-but-disabled placeholder (no DB, no wiring) until its own approval-gated milestone
  (ADRs 0014/0015).

## Consequences

- A new capability-inventory abstraction that **tabular-as-a-tool** (next milestone) and **real MCP**
  extend with no new surface — one new tool-group entry / one inventory section, no schema change.
- The hardcoded area-key tool branch becomes a data-driven loop — its highest blast radius is the
  no-toggle (default) path, which must be proven **byte-identical** to today's tool+skill+prompt assembly
  (a regression test is the hard guard).
- Tool availability stays code-defined (no admin UI for it); playbook availability gets a table + a minimal
  admin attach/detach endpoint now, the curation UI later.
- The "Practice Playbook" tier from the canonical memory-tiers table (CLAUDE.md) goes partly live,
  read-only — its source of truth stays the `playbooks`/`playbook_positions` SQL.
- Stale toggle rows are tolerated (resolve-time drift drop, the established `area_agent` posture); the PATCH
  boundary rejects writing a key absent from the matter's available set.
- **Gate.** Deterministic: pure inventory tests; GET/PATCH (defaults all-on, override reflected, unfiled →
  empty, cross-user/archived/sandbox → 404, 422 on unknown/non-toggleable/oversized, audit body-free);
  composition (disabled skill/tool/playbook genuinely absent; **no-toggle path byte-identical**); migration
  `0081` up→down→up on a throwaway pgvector; admin attach/detach; `render_practice_playbook` formatting/cap.
  Web vitest on the exported pure helpers. Live dev-stack: toggle Redlining off → agent cannot redline;
  toggle a playbook on → its positions in the run's injected context; persistence across a new conversation.
- **No new dependency.** Additive migration only; the gateway is untouched.

## Decisions (CONFIRMED by maintainer, 2026-06-30)

All six settled on the recommended defaults (the Decision outcome above already reflects these):

1. Tool availability source — ✅ per-area CODE map (no `practice_area_tools` table).
2. Playbook consumption path — ✅ read-only "Practice Playbook" tier on `TierMemoryMiddleware`.
3. Per-matter toggle default — ✅ all-available-on (MCP placeholder excepted).
4. ROPA ↔ Assessment — ✅ independent toggles; Assessment degrades to empty when ROPA off.
5. Tool toggle granularity — ✅ by GROUP.
6. Scope — ✅ per-matter only this slice; per-run override stays backlog.

## Addendum — D1 supersession (SETUP-5a, 2026-07-05)

- **D1 superseded, for AVAILABILITY only, by ADR-F062.** D1 read: "tool availability [is a] per-area
  CODE map (the area-key branch + `*_TOOL_NAMES` frozensets are the truth)." ADR-F062 (SETUP-4a) moves
  *availability* to data: `practice_area_tool_groups` rows carry tool-group **names only**, resolved
  through the code `TOOL_GROUP_REGISTRY`. Grants are untouched — a group's grant set is still its
  `build_*_tools`' `*_TOOL_NAMES` frozenset, exactly as D1 required. This is why F054's own
  rejected-option-2 ("fully normalized `practice_area_tools` … duplicates code-canonical tool grants as
  data") is **honored, not violated**: option 2 would have put tool *names* in a table as grants;
  F062 puts *group names* in a table as availability, with grants staying code-canonical. The
  distinction the option-2 rejection was protecting — grants must never live in data — survives intact.
- **Consequences superseded.** The two Consequences lines "tool availability stays code-defined (no
  admin UI for it)" and "the hardcoded area-key tool branch becomes a data-driven loop" are superseded
  by F062 (the registry + `practice_area_tool_groups`) and by the SETUP-4b admin UI
  (`/lq-ai/admin/areas/{key}` tool-group attach/detach), which together deliver exactly that data-driven
  loop and admin surface.
- **D2–D6 unchanged and still binding.** In particular D5 (tool toggle granularity — by GROUP) is the
  granularity the SETUP-4b admin UI (and any future capability UI) must continue to expose; it is not
  touched by the D1 supersession.
