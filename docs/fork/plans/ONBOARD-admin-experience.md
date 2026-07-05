# ONBOARD-0 — Admin-experience dress rehearsal: observed gaps + design direction

**Status: living draft for maintainer edit** (ONBOARD-0 deliverable). Started 2026-07-05 during the
maintainer's first admin walkthrough on a fresh stack (main @ `20baf1e5`, DB at mig 0087, operator-handover
state: first-boot-minted admin + operator). Every gap below is grounded in code, not speculation —
file references included. The maintainer edits this doc; the edited version scopes ONBOARD-1/2.

## The rehearsal setup

Fresh `docker compose` stack on main, empty DB migrated to head, 5 seeded practice areas
(commercial, disputes, employment, m-and-a, privacy — mig 0055 doctrine prose only), admin +
operator minted via `FIRST_RUN_ADMIN_EMAIL` / `FIRST_RUN_OPERATOR_EMAIL`, one-time passwords from
api logs. Gateway config survived (host file via `GATEWAY_CONFIG_FILE`, not the wiped volume).

---

## Observed gaps

### G1 — First-run email validation asymmetry (found before the walkthrough began)
**Observed:** the operator account was minted as `operator@lq-local.test`; every login attempt 422s.
**Ground truth:** first-run bootstrap accepts any string as the email; the login endpoint's
`LoginRequest.email: EmailStr` (Pydantic `email-validator`) rejects IANA reserved TLDs (`.test`,
`.local`) *before* the request reaches auth. The account exists but can never log in — 422 on
format, not credentials. An operator following the SETUP guides could lock themselves out at
handover with no comprehensible error.
**Direction:** validate `FIRST_RUN_*` emails at boot with the *same* validator the login path uses;
reject at boot with a clear message. Tiny slice; belongs with SETUP hygiene rather than ONBOARD.
(Local rehearsal fixed by a one-line email UPDATE to `operator@lq-ai.internal`.)

### G2 — The House Brief has no web UI at all
**Observed:** password change fired on first login; nothing about the House Brief did.
**Ground truth:** the backend is complete — `GET /api/v1/organization-profile` (any user),
admin-only `PUT`, `/raw`, audit-logged (`api/app/api/organization_profile.py`). The web app has
**no page, no admin-nav entry (`admin/+layout.svelte:11-21`), and no API client binding** for it.
The forced-password-change flow terminates at re-login → home cockpit with no onboarding prompt.
A fresh DB seeds no row (mig 0010), so the House Brief is blank *and* unreachable from the UI.
**Why this is priority, not polish:** the House Brief is one of the four read-only DATA tiers
injected into every agent prompt (TierMemoryMiddleware, ADR-F049). An org that never sets it runs
every practice-area agent with an empty firm identity — silently degraded output. (Already bitten
once: the Commercial live UAT found the empty org profile and had to seed it by raw API.)
**Direction:** two halves. (a) A **House Brief admin page** — small well-shaped slice, zero backend
change. (b) The **first-login admin checklist** (the old SETUP-3c idea) as the ONBOARD-2 wizard's
entry point, so a fresh admin is *led* there: House Brief → users → areas → capabilities.

### G3 — Invites: fully wired, email delivery is dormant config (not a gap in code)
**Observed:** maintainer asked whether inviting users is wired and how email would ever send.
**Ground truth:** the full lifecycle exists (SETUP-3a/b): admin mints a single-use 7-day invite
link (token HMAC-hashed at rest, never logged/audited raw; invitee sets their own password on
`/lq-ai/accept-invite`; atomic single-consume). A first-party stdlib-SMTP sender exists
(`api/app/email.py`, no third-party dependency) and **sends the invite email automatically when
`SMTP_HOST` is configured**; unconfigured, the UI falls back by design to showing the accept URL
once behind a Copy button ("hand this link over out-of-band").
**Direction:** nothing to build. Local rehearsal uses copy-link. For a hosted box, "configure
SMTP_HOST/PORT/USERNAME/PASSWORD/FROM + PUBLIC_BASE_URL, with SPF/DKIM/DMARC on the From domain"
becomes an operator-setup step → belongs in the SETUP-6 operator guide (task #462) and optionally
as a line in the operator wizard's checklist.

### G4 — Catalog vs Org Library vs Area Binding: the layers exist but are fused (the big one)
**Observed (maintainer):** "There is still confusion between what LQ.AI Oscar Edition inherits from
LQ.AI… an organisation may not need all of this by default. There needs to be a distinction between
LQ-inherited skills and logical set-up… I am thinking of an LQ 'Store'… My NDA skill may be entirely
different to what an LQ lawyer thinks it is."
**Ground truth of today's model** (chokepoint: `build_area_inventory`,
`api/app/agents/capabilities.py:402-509`):
- The "shipped pool" is **three different sources with three different natures**: tool groups =
  code registry (`TOOL_GROUP_REGISTRY`; grants stay code per ADR-F062); skills = filesystem scan of
  `skills/` at boot (incl. the `skills/community/` submodule; SIGHUP-reloadable); playbooks = DB rows.
- Deployment "Capabilities" toggles (mig 0086) are a **sparse, disable-only** gate: a row exists
  only where an admin turned something OFF. Everything ships ON — so the Capabilities page presents
  LQ's entire worldview as if the org had chosen it.
- Area bindings (three join tables) are validated against the shipped pool **but not against the
  toggle** — you can bind a deployment-disabled skill and it silently vanishes at resolve time
  (intersection happens in `build_area_inventory`, not at bind time). No UI warning. (Sub-gap G4a.)
- **Provenance hooks already exist**: `SkillSource` = `built-in` / `community` / `user` / `team`
  (`api/app/skills/schema.py:33-41`), and `lq_ai:` frontmatter carries `author`/`version`. But
  community-style *top-level* `author:`/`version:` (no `lq_ai:` block) are not parsed into
  summaries — they surface as author `None` / `"unversioned"`. (Sub-gap G4b, small parser fix.)

**Agreed design direction — the three-layer model:**
1. **Catalog ("LQ Store")** — what LQ ships: skills, playbooks, tool groups, area templates.
   Provenance-labelled, versioned, read-only. v1 = the existing registries presented *as a catalog*,
   not as the org's setup. The literal store (remote registry, downloads, updates from lq-skills)
   is a later milestone.
2. **Org Library** — what *this organisation* has deliberately adopted; later, what it has authored.
   v1 = invert today's polarity: admin **adopts into** the library instead of un-configuring LQ's
   defaults; every item carries its provenance (LQ / community / yours). Org-*authored* skills stay
   deferred (ratified §7 no-v1) — they are prompt-content, i.e. an injection surface needing the
   Practice-Knowledge-style harness + an ADR — but **namespace for shadowing now**, so a future org
   NDA skill can cleanly override the catalog's `nda-review` without collision.
3. **Area Binding** — what each practice-area Deep Agent actually carries: the template's universal
   defaults + admin additions *from the org library*, never directly from the catalog. The admin
   Capabilities page becomes the **Org Library view**; the practice-area page stays the **binding
   view**. Same pool, two lenses, clear provenance.

**Consequence for defaults:** area templates ship **minimal** — only what any firm would want
(Commercial: redlining + core doc tools; Privacy: ROPA + assessments) — everything else opt-in.
Mostly a data/seeding change, not machinery.

### G5 — Skill content is viewable in the UI, but unreachable from where admins look
**Observed:** "annoyingly I cannot click on any skills" (practice-area detail page).
**Ground truth:** a full skill-source viewer **exists** (`/lq-ai/skills/{name}`, Source tab renders
raw frontmatter + markdown body — the transparency rule is technically satisfied). But: admin
area/capabilities pages render bound skills as plain text with no link
(`admin/areas/[key]/+page.svelte:483-497`), and the `/lq-ai/skills` list shows only user/team
skills plus built-in *table-mode* skills — ordinary built-ins (nda-review, msa-review-saas, …) are
listed nowhere. Content readable only by typing the URL by hand. Practically, transparency is
violated for exactly the skills an admin is configuring.
**Direction:** small slice — link every skill name in the admin pages to the existing viewer; list
built-ins (read-only, provenance-labelled) in the skills catalog view. Zero backend change.

### G6 — Fresh-area emptiness + seeded-defaults inventory (feeds ONBOARD-1 templates)
**Ground truth:** admin-*created* areas start with nothing (no doctrine, no bindings, empty
roster). The seeded areas' defaults, for reference when designing templates: Commercial = 9 skills
(migs 0056/0067/0069/0072/0073/0083), 2 tool groups (`redlining`, `tabular`), 3-subagent roster
(document-researcher / clause-drafter / clause-reviewer), **0 playbooks** — no area ships a bound
playbook at all. Privacy = 3+1 skills, tool groups `ropa`/`assessment`. Templates-as-data
(ONBOARD-1) replaces this migration-seeding chain as the way defaults reach a new org.

### G7 — Accept-invite page is blank on direct load (BUG — FIXED, PR #223 `2f3039e0`)
**Observed:** the invited member opened `/lq-ai/accept-invite?token=…` and got a blank page.
**Ground truth:** `accept-invite/+page.svelte:47` calls SvelteKit's `replaceState` (the F7
token-scrub) inside `onMount`. On a **direct URL load** the router is not yet initialized and the
call throws — `mounted = true` on the next line never runs, so the page stays in its deliberate
render-nothing state. The bug only manifests on direct entry (exactly how invite links are opened),
never on in-app navigation — which is how it escaped SETUP-3b verification. Blast radius: the same
pattern exists in `reset-password/+page.svelte:54` (the other direct-entry lifecycle page); all
other `replaceState` uses are the safe `goto(..., {replaceState: true})` form.
**Resolution:** FIXED same day — both pages moved the scrub into `afterNavigate` (proven against
SvelteKit's router source), two Cypress direct-load regression specs added, merged as PR #223
`2f3039e0` and verified live against the production web container (2/2). (Rehearsal had been
unblocked meanwhile by consuming the token via the API — member account minted server-side.)

### G8 — Model routing is invisible to the admin (and has no fallback)
**Observed:** the member's Commercial run failed with a raw provider error ("APIError: Token Plan
usage limit reached… (2056)" — the MiniMax account's plan exhausted). The admin went looking for
"switch the model" and found nothing.
**Ground truth:**
- The lead agent runs on the gateway alias `smart` (factory default `agents/factory.py:60`; run
  create default `schemas/agent_runs.py:82`); live config points `smart`/`fast`/`budget` all at
  `minimax/MiniMax-M3`. One provider outage/quota = every default run fails.
- A full alias-management surface EXISTS end-to-end — gateway `/admin/v1/aliases` CRUD ⇄ api proxy
  (`api/app/api/admin.py:516+`) ⇄ the `/lq-ai/admin/models` page — but it is **operator-fenced**
  (ADR-F061 D4: aliases proxy the key-holding egress, so they're platform infrastructure). The
  org-admin can't see the page *by design*. Switching to DeepSeek is a 30-second operator-UI action.
- Per-run `model_alias` is accepted by `POST /agent-runs` (any alias name) but **no composer UI
  exposes it** — users have no model lever at all.
- Every live alias has `fallback: []`. The alias schema supports fallback chains; a
  `minimax → deepseek` fallback would have turned this hard failure into a degraded-but-working run.
**Direction (three separable strands):**
(a) **Discoverability/transparency:** the admin should at least *see* what model an area's agent
runs on (read-only), even while switching stays operator turf — currently nothing tells them.
(b) **Ownership split to decide:** provider keys are unambiguously operator; is per-area model
*choice* (from operator-exposed aliases) an admin setting? Natural sibling of ADR-F063's
`default_budget_profile` chain (`practice_areas.default_model_alias`?). ADR territory.
(c) **Resilience + error UX:** seed fallback chains in the shipped gateway config example; and the
raw provider error string surfaces verbatim to the member — should be a friendly "provider quota
exhausted — contact your administrator/operator" with the detail in the run receipt/audit instead.

---

## Implications for ONBOARD-1/2 slicing (proposal — maintainer edits)

> **PRIORITY DECISION (maintainer, 2026-07-05):** the G4 Store-vs-Org redesign moves FIRST —
> "this takes priority… we need clean and clear UX." Plan drafted at
> `docs/fork/plans/STORE-org-library.md`; the template catalog (ONBOARD-1) and wizard (ONBOARD-2)
> follow it, and the remaining gaps stay queued.

- **ONBOARD-1 (template catalog)** absorbs G4's v1: templates live *in the Catalog* alongside
  skills/tool-groups; a template = doctrine + minimal universal bindings + unit vocabulary +
  budget/tier defaults. Unit-of-work types are first-class in templates (maintainer refinement:
  "Matter", "Project/Programme" exist; **"Investigation" is missing**; some unit types may need
  structure beyond `unit_label` — flag as ADR territory, adjacent to the contentious-area deferral).
- **ONBOARD-2 (admin wizard)** absorbs G2b (first-login checklist as entry point) and presents the
  Catalog → Library → Binding flow: pick template → name area + unit label → review doctrine →
  adopt/bind capabilities → invite users → done.
- **Independent small slices** (can land before/alongside): G1 boot validation; G2a House Brief
  admin page; G5 skill-viewer linking; G4a bind-while-disabled warning; G4b provenance parser fix.

## Open questions for the maintainer

1. Naming: "LQ Store" as the user-facing name for the catalog, or something quieter ("Catalog",
   "Library") until the remote-store milestone makes it a real store?
2. Should the Capabilities page's disable-only toggles survive at all in the Library model, or is
   "not adopted" the only off-state an org needs (toggles kept as an operator-level kill switch)?
3. Minimal defaults: agree Commercial = redlining + core docs, Privacy = ROPA + assessments — what
   is the *universal* baseline for disputes/employment/m-and-a until their templates exist?
4. Unit-of-work vocabulary for v1 templates: Matter / Project / Programme / Investigation / …?
   Which (if any) need structure beyond a label in v1?

## Walkthrough log (append as observed)

- 2026-07-05: G1 (operator email 422), G2 (House Brief absent from UI), G3 (invite mechanics
  question), G4 (catalog/library confusion, "LQ Store" direction), G5 (skills not clickable).
- 2026-07-05 (cont.): invite created + copy-link handed over ✓; accept-invite page blank on direct
  load → G7 (root-caused; member minted via API to keep the rehearsal moving). Capability toggling
  verified working in the Capabilities tab; maintainer notes the toggle UX is moot pending the
  G4 Catalog/Library model (feeds open question 2 — toggles as operator kill-switch vs "not
  adopted" as the only off-state).
- 2026-07-05 (cont.): member leg started; Commercial run failed on MiniMax plan exhaustion → G8
  (model routing operator-fenced + no fallback + raw provider error shown to the member).
- 2026-07-05 (cont.): maintainer switched `smart`/`fast`/`budget` → `deepseek-v4-flash` LIVE via
  the operator UI (Models page) — first real dress-rehearsal of the alias surface, worked
  (hot-apply, no restart). Member re-ran the Commercial agent: **run completed** ✓. Member leg
  proven end-to-end: invite → accept (API workaround for G7) → login → agent run.
- *(pending, optional: area creation from blank; anything else the maintainer wants to poke)*
