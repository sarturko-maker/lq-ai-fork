# B-2b live UI verification — org-skill propose / review / provenance

**Date:** 2026-07-08 · **Branch:** `b2b-propose-review-ui` (`20a53073`) · **Stack:** dev
`docker compose` (api + web rebuilt from this branch) · **Runner:** Cypress 13 headless
(Electron), temporary spec `web/cypress/e2e/b2b-probe.cy.ts` (deleted after the run).

**Probe users:** `b2b-probe-author@example.com` (member), `b2b-probe-admin@example.com`
(admin). Credentials rode `CYPRESS_B2B_PROBE_PASSWORD`; never in the spec or logs.

**Result: 12/12 passing** (steps 1–10, with 7 split into 7a/7b/7c) on the final evidence
run. Full loop: author creates a personal skill → proposes → admin reviews raw bytes +
content hash → approves → adopt + area-bind (API) → provenance badges on three admin
surfaces → author sees approved pill → second propose → reject-with-note → author sees the
note → admin revokes the approved version via the two-click modal → non-admin lockout →
teardown.

**Version numbers in the evidence read v19/v20**, not v1/v2: `org_skill_versions` is an
append-only, immutable ledger keyed by slug, and earlier probe iterations during selector
tuning consumed v1–v18. On the first (clean-DB) iteration the same loop produced exactly
v1/v2 with identical behavior. The rows are left for the lead's SQL sweep as instructed.
The final teardown left: 0 library entries, 0 practice areas, 0 active user_skills with
the probe slug — only `org_skill_versions` rows (v1–v20, all terminal states) + the two
probe users remain.

## Step-by-step outcomes

| # | Surface | Outcome |
|---|---|---|
| 1 | API `POST /user-skills` (author) | PASS — 201, slug `b2b-probe-ui-skill`, body carries the marker sentence. |
| 2 | UI `/lq-ai/skills` (author) | PASS — own user-scope row shows **Propose to Library**; click → success banner `Proposed "b2b-probe-ui-skill" v19 to the Library — an admin will review it.` → `02-propose-success-banner.png` |
| 3 | UI `/lq-ai/admin/library` (admin) | PASS — **Review queue** section (`lq-admin-review-queue`) lists the row `b2b-probe-ui-skill · v19` with author email + proposed timestamp + size + truncated hash; expand → Raw view renders frontmatter + body verbatim in a `<pre>` (marker sentence visible) and the **full** `content_hash` (`35f6dd3d98f005519a7dc255c3b324fe689453e89d0c2e0accb3bca29d55dbdb` — the element's text asserted equal to the API value); Approve → row leaves the proposed view; API cross-check shows state `approved`. → `03-review-queue-expanded-raw-hash.png` |
| 4 | API (admin) | PASS — adopt `{kind:'skill', key:'b2b-probe-ui-skill'}` 201; create area `b2b-probe-ui-area` (with required `profile_md`) 201; bind skill 204/201. |
| 5 | UI badges (admin) | PASS on all three surfaces (exact badge text below). → `05a-library-adopted-org-badge.png`, `05b-store-catalog-org-badge.png`, `05c-area-binding-org-badge.png` |
| 6 | UI edit page (author) | PASS — Proposals section shows the v19 row with the **Approved** pill. |
| 7a | UI propose again (author) | PASS — banner `Proposed "b2b-probe-ui-skill" v20 to the Library — an admin will review it.` |
| 7b | UI reject with note (admin) | PASS — v20 row → Reject → modal note textarea (`lq-admin-review-queue-reject-note`) typed `probe rejection note` → confirm → row leaves the proposed view. |
| 7c | UI edit page (author) | PASS — v20 row shows the **Rejected** pill AND `Reason: probe rejection note`. |
| 8 | UI revoke (admin) | PASS — Approved filter → v19 row → **Revoke** (click 1) opens the confirm modal; copy asserts verified: *"Agents across your company stop loading this skill immediately — it fails closed at the next run. The Library entry and any practice-area bindings stay visible but show as unavailable until you remove or replace them. The author keeps their personal copy."* → `lq-admin-org-skill-revoke-confirm` (click 2) → row leaves the approved view; API shows state `revoked`. → `08-revoke-two-click-confirm-modal.png` |
| 9 | Non-admin lockout (author) | PASS — visiting `/lq-ai/admin/library` as the author client-redirects away (URL leaves `/admin/library`, no review-queue node in the DOM); API `GET /admin/org-skills` with the author token → **403**. (Operator silent-hide skipped — no operator creds; ADR-F064 behavior untested here.) |
| 10 | API teardown (best-effort) | PASS — unbind skill 204, delete area 204, remove library entry 204, archive author skill 204. DB end state: 0 probe library entries / areas / active user_skills. |

## Exact badge text observed (step 5)

* `/lq-ai/admin/library` (adopted Skills card):
  **`Org-authored · approved by b2b-probe-admin@example.com`**
  — the author is deliberately absent here: the card renders from `GET /library`, the
  member-visible read model, which "exposes no AUTHOR identity, only that an admin
  reviewed and approved the content" (`api/app/api/library.py`, B-2a/B-2b design). Not a
  bug; noted because the plan sketch expected the full badge on this surface too.
* `/lq-ai/admin/store` (catalog card, `GET /admin/capabilities`):
  **`Org-authored · b2b-probe-author@example.com · approved by b2b-probe-admin@example.com`**
* `/lq-ai/admin/areas/b2b-probe-ui-area` (badge beside the skill binding):
  **`Org-authored · b2b-probe-author@example.com · approved by b2b-probe-admin@example.com`**

## Rig traps hit (for future UI probes — not product bugs)

* **`cy.session` self-destructs against the activity refresher.** The app posts
  `/auth/refresh` on any click (`sessionActivity.ts`, ≤1/min) and rotation invalidates the
  snapshot cy.session restored — the next admin action 401s ("Not authenticated" in the
  reject modal). Fix: one API login per user, seed `lq_ai_auth` localStorage in
  `cy.visit#onBeforeLoad` with `refresh_token: null` (the tracker skips refresh when no
  token is present; the 15-min access token carries the whole run).
* **Scrolling the app shell for screenshots:** the scroller is the inner
  `<main class="… overflow-y-auto scroll-smooth">`; Cypress `.scrollIntoView()` AND native
  `element.scrollIntoView()` are both no-ops there (measured `scrollTop` stays 0), and
  element-capture screenshots come out blank (headless window is 1280x720 with the
  1440x900 viewport scaled). What works: assign `scrollTop` directly on the nearest
  scrollable ancestor with `style.scrollBehavior='auto'` temporarily set, then take a
  viewport capture.

## Observations (not blocking)

* Store page subtitle reads "Add what your **firm** uses to your Library" — pre-B-2b copy
  (STORE-2) that now contradicts the 2026-07-08 in-house ruling ("the company's legal
  team", never "the firm"). One-line copy fix for a future slice.

## Evidence files

* `02-propose-success-banner.png` — author list page, success banner naming the slug.
* `03-review-queue-expanded-raw-hash.png` — queue row expanded: raw source + full content hash + Approve.
* `05a-library-adopted-org-badge.png` — Library adopted card with the approver-only org badge.
* `05b-store-catalog-org-badge.png` — Store catalog card with the full org badge + "In Library ✓".
* `05c-area-binding-org-badge.png` — area page Skills binding with the full org badge chip.
* `08-revoke-two-click-confirm-modal.png` — revoke confirm modal with the fail-closed copy.
