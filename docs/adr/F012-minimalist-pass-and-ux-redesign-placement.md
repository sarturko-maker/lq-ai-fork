# F012 — Minimalist (scira-style) visual pass, and where the UX redesign belongs

- Status: accepted
- Date: 2026-06-15
- Deciders: maintainer (Arturs) — accepted 2026-06-15 ("what is the right move from a technical
  perspective" → split by dependency, recommended approach approved)
- Extends: [[F006]] (UI stack + design system), [[F011]] (AI Elements adoption); interprets and sequences
  the F3 commitment in [[F002]] (practice-areas-and-agent-home)
- Supersedes: none

## Context

The AI Elements series (AE0–AE7, F011) closed, so the conversation/agent components carry a calm modern
look. The maintainer wants the **whole** interface taken toward the minimalist aesthetic + positioning of
[`scira`](https://github.com/zaidmukaddam/scira), and has stated a deeper UX intent: users should **land
in the cockpit**, **reach the tools from there** (Chats, Playbooks, Tabular…), with the project's real
centre — **deep agents per practice area** — as the place you land.

`scira` is **AGPL-3.0**. We treat it as **REFERENCE ONLY**: study its look / IA / positioning, never fetch
or copy its code (copying would force AGPL onto our Apache-2.0 stack — stricter than the MIT AI Elements
port we *do* vendor under F011).

Two relevant facts constrain the work:

1. **Two eras coexist.** The modern **Cockpit** (`/lq-ai` → `cockpit/Cockpit.svelte`) is already the
   landing, already on semantic tokens, already lands on practice areas (`AreaGrid`), and its header
   already has a **Tools menu**. The legacy **`(tools)`** surfaces run a parallel `TopTabBar` IA still on
   `--lq-*` tokens. The cockpit is already the direction; the legacy IA has not yet converged into it.
2. **F002 already governs the destination.** F002 binds conversations to (practice area, unit of work) —
   "free-floating agent chat with no unit of work is not offered" — and commits **F3** to "promote area
   pages to the top-level IA and demote tool tabs to in-context capabilities." The maintainer's UX intent
   *is* that F3 commitment; the open question is **where it belongs** relative to a visual pass and to the
   practice-area pivot work that is still in flight.

The pivot work the deep end-state depends on does not exist yet: the `practice_area` / `unit_of_work`
**schema is absent** (CLAUDE.md blocker #5; area ids are presentation-only and the backlog forbids letting
them leak into stored rows until the schema lands), area-skill/subagent **activation** is pending
(S9-gated), and the **visible** agent run needs **F1-S4** (subagent tree + SSE projection) + **F1-S5**
(attribution). Until those land, "tools as in-context agent capabilities" cannot be built honestly — only
faked, which violates the transparency principle (F002, PRD §1.3).

## Considered options

1. **Fold the UX redesign into the minimalist visual pass (one effort).** Rejected: conflates
   presentation (reversible) with architecture (coupled to the pivot); lets a "screenshot slice" quietly
   make IA decisions that belong in an ADR; and would either block the visual pass on pivot work or ship a
   dishonest hollow shell of capabilities the agent can't yet drive.
2. **Do the full UX redesign now as the primary track.** Rejected: front-runs the absent schema (turns F1
   into a data-repair exercise — the explicit backlog guard) and the agent-capability/SSE work; the deep
   "land in the agent, tools as capabilities" experience cannot be honest before its enablers exist.
3. **Defer all of it until the pivot finishes.** Rejected: the visual minimalism + a calm area-first
   landing + reaching tools from the cockpit deliver real, honest value now and are not blocked; waiting
   wastes that and leaves the two-era split in place longer.
4. **Split the UX redesign by dependency; do the reversible visual work now.** Chosen.

## Decision outcome

**Option 4.** Three separable concerns, sequenced by what each depends on:

- **F2 — Minimalist visual pass (now).** Presentation-only, **reversible**, forward-compatible. Calms the
  cockpit + global chrome; makes the cockpit a calm **area / deep-agent-first** landing (a centered
  *intent launcher*, per the honest-launcher rule below); **visually condenses** the tab bar; migrates any
  touched chrome `--lq-*` → semantic tokens (which *is* the dark-mode fix, per F006/CLAUDE.md). Decomposed
  into slices F2-M0…M9 (`docs/fork/plans/F2-minimalist-pass-decomposition.md`).
- **UX-A — Navigational convergence (its own milestone, right after F2; own ADR + decomposition).** Make
  the cockpit the *single* shell; promote tools-from-cockpit (build on the existing `CockpitHeader` Tools
  menu) to the primary tool access; retire/relocate the legacy `TopTabBar` + `(tools)` shell. Almost
  entirely frontend IA → not blocked by the schema, but it *does* retire IA → staged + reversible
  (de-emphasise → hide-behind-Tools → retire). This is the navigational half of F002's F3 commitment.
- **UX-B — Capability convergence (folds into the pivot track).** "Land in the practice-area deep agent;
  tools become in-context capabilities the agent picks/exposes" (F002's "glass cockpit" capability rail +
  live activity feed). Built **as its enablers land** — the practice_area/unit_of_work schema, area
  activation, and F1-S4/S5 — never before. This is the capability half of F002's F3 commitment.

**Load-bearing rules for F2 (the reversibility / no-retire contract):**

- **No irreversible IA move.** F2 deletes no tab, route, or surface. All 11 tabs stay visible and
  clickable; "condense" means visual calm + grouping + muted styling, **not** an overflow/More menu, hide,
  or delete. Surface retirement is wholly UX-A/F3's job.
- **Honest launcher, not an unbound composer.** The cockpit centered entry is an *intent launcher* that
  routes into the F002 area→matter binding flow (carrying the typed text forward as the composer draft) —
  it never manufactures a free-floating thread (F002). It must **invent no content**: recents come from
  settled `GET /agents/matters` (ADR-F004); starter chips, if any, come only from the user's own
  SavedPrompts (the AE7 honest-source precedent); unconfigured areas degrade to the existing inert state.
- **Token policy:** touched chrome migrates to semantic tokens; F2 introduces **no new `--lq-*`** and
  forks **no new token scale** (the `app.css` semantic palette is the system). Coordinate with the in-
  flight F1 R-CHROME/R-TYPO (migrate-and-calm once, or calm-on-semantic if the R-slice already merged).
- **Presentation-only:** KEEP the gateway / SSE / `guarded_tool_call` / audit / `renderModelMarkdown`
  substrate; add no `{@html}` sink.

## Consequences

- The UX redesign is on record and sequenced; F2's visual slices are reviewed against this destination
  rather than drifting into ad-hoc IA decisions.
- UX-A becomes cheap because F2 stays additive: de-emphasised legacy nav flips to retired with little
  churn. UX-B is explicitly gated on the pivot enablers, so it can't ship dishonestly.
- F2 touches files the F1 R-series also targets (`TopTabBar`, `AmbientTrustChrome`, `(tools)/+layout`,
  etc.); each F2 slice must check R-series landed-state and never re-introduce `--lq-*`.
- A later ADR (UX-A) will record the actual nav convergence + retire decisions; this ADR deliberately does
  not pre-decide them beyond the "reversible, staged" contract.
- Risk: the cockpit centered entry ossifies into a fake search bar. Mitigation: it is an honest launcher
  bound to F002's flow with no invented content, and it is one component reverted by deleting one render
  line.
