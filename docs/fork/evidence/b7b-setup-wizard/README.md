# B-7b — guided setup wizard: live verification

Live walk of `/lq-ai/admin/setup` on the dev stack (rebuilt `lq-ai-web` production bundle), driving the
real B-7a profiles API. Captured headless (chromium) via Cypress on 2026-07-11.

| # | Screen | What it shows |
|---|--------|---------------|
| 01 | `01-profile-picker.png` | "Set up" nav tab active; StepRail (1 active → 2 → 3 → 4); the three profile cards — Blank / Commercial (9 skills · 2 tools · 3 sub-agents) / Privacy — with kind badges. Next disabled until a profile is chosen. |
| 02 | `02-house-brief.png` | Step 1 completed (✓), step 2 active; the optional House Brief form (embeds the B-1 organization-profile surface) + teaching copy + link to the full House Brief page. |
| 03 | `03-review-activate.png` | Steps 1–2 completed, step 3 active; the **diff-preview** — "Activating Commercial will adopt 9 skills and 2 tool groups… and set a 3-sub-agent roster" — plus the real skill chips (msa-review-*, contract-qa, nda-review, surgical-redline, matter-memory, negotiation-review, deal-review, tabular-review) and tool chips (redlining, tabular), fetched live from `GET /profiles/commercial`. |

**Method note.** The committed acceptance scaffold `web/cypress/e2e/b7b-setup-wizard.cy.ts` drives the flow
through the real UI `login()` (needs the dev admin password via `--env LQAI_ADMIN_PASSWORD=…`, like
`b4-org-playbooks`; Cypress is not part of the CI gate). These evidence shots were captured with an
equivalent session-injection variant (a minted admin JWT placed in `localStorage`) so no credential is
embedded anywhere.

**Still on record — the maintainer's acceptance walk:** reset a fresh org → apply Commercial via the wizard
→ invite a member → the member runs the Commercial agent → it redlines with no manual Library curation (the
G13 kill).
