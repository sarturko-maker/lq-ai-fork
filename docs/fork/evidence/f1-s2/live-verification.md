# F1-S2 live verification — dev stack, 2026-06-12

Stack: 8 services healthy; api/arq-worker/ingest-worker/web rebuilt on the
slice code; **DB migrated 0052 → 0053 by the api's boot auto-migrate**
(never host-side), seed verified in-DB:

```
 version_num: 0053
 commercial | t | 1     disputes | f | 2     m-and-a | f | 3
 privacy    | f | 4     employment | f | 5
```

## Cypress against the live stack

| Spec | Result | What it proves |
|---|---|---|
| `f1-s2-cockpit.cy.ts` (new) | **5/5** | Login lands in the cockpit; rail lists the 5 seeded areas; 4 inert cards honest + non-navigating; enter Commercial → matters list; create matter in place (real `POST /projects` 201) → conversation view with the matter pre-selected; unfiled bucket (resume-only, no composer); theme toggle → dark charcoal ≠ black; Tools menu → legacy Skills page with tab chrome intact; brand link returns to the cockpit |
| `f0-s5-multi-turn.cy.ts` | **1/1** | END-TO-END with the REAL model (MiniMax-M3 via the gateway): matter + composer upload + ingestion + a multi-turn agent run with document grounding, on the moved `(tools)` agents route |
| `wave-a-chrome.cy.ts` | **3/3** | Legacy tab chrome intact on tools routes; trust chrome in the cockpit header (2 point-in-time-stale tests retired with dated comments: ComingSoonModal-on-Matters — red since Wave C; AmbientFooter-on-`/lq-ai` — asserted the pre-Wave-B chat-shell landing) |
| `m4-autonomous.cy.ts` | **9/9** | Autonomous gating intact (tab gating asserted on a tools route) |
| `wave-b-surfaces.cy.ts` | 4/6 | Cockpit landing, Tools-menu navigation, trust + developer cards pass (the featured-tools test retired with its dashboard consumer). The 2 fails (Enhance-Prompt composer, skill-detail) **reproduce identically against the PRE-SLICE bundle** (control below) — pre-existing |
| `wave-c-matters.cy.ts` | 4/5 | Matters page + workspace pass. The 1 fail (chat-in-matter rail entry) likewise reproduces on the pre-slice bundle — pre-existing |

**Control run:** `main` (`e788fc9`) web image built in a worktree and swapped
onto :3000; the original wave-b/wave-c specs against it fail the SAME 3
tests the slice bundle fails (and its dashboard-era tests pass) — the
remaining failures are box/data-state issues that predate this slice.

## Screenshots (1280×800, uncropped viewport)

- `f1-s2-1-cockpit-landing.png` — light-first warm canvas, area grid,
  honest inert cards, single indigo accent. No black anywhere.
- `f1-s2-2-matters-list.png` — matters under Commercial with status pills
  + relative activity, New-matter affordance.
- `f1-s2-3-matter-view.png` — conversation list + re-homed
  ConversationPanel, matter pre-selected, Run gated until prompt.
- `f1-s2-4-dark-mode.png` — charcoal dark (canvas oklch 0.23 ≈ #1B1E24),
  explicitly not black; cards/borders keep hierarchy.

## Found-and-fixed live (in this slice)

- **`POST /auth/refresh` froze the api event loop**: the legacy handler
  bcrypt-compares the presented refresh token against EVERY active
  session row inline (auth.py "scan candidates" loop) — with 186
  accumulated dev sessions ≈ tens of seconds of blocked loop; concurrent
  logins stalled behind it (deterministic Cypress beforeEach failures).
  Fixed (legacy bugfix, security-sensitive path — flagged for the extra
  review pass): the scan now runs in `asyncio.to_thread`, semantics
  unchanged; 27 auth/session tests pass. The deterministic-HMAC index
  column remains the real fix (already tracked in-code as a DE
  candidate); dev-stack session prune left to the maintainer.
- Ingest worker hit a transient `asyncpg connection is closed` mid-parse,
  leaving a file at `processing` (startup-only recovery — the known
  fragility the re-plan §S1 noted); worker restart's startup sweep
  requeued it → `ready`, f0-s5 then passed. No code change (ingest cron
  sweep stays a backlog item).

## Post-review re-verification (final images)

Adversarial review (32 verified findings: 26 confirmed in-slice — ALL
fixed; 3 pre-existing recorded on HANDOFF; 3 refuted — plus the 2
found-live entries above) triggered an api+web rebuild; on the FINAL images:
`f1-s2-cockpit.cy.ts` 5/5 again (screenshots refreshed) and
`wave-b-surfaces.cy.ts` 4/6 with only the two control-proven pre-existing
failures. Full api suite re-run after the auth re-check fix: counts in
the PR body.
