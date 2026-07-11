# B-7 milestone acceptance walk — evidence (task #508, 2026-07-11)

**Delegated agentic walk; formal sign-off remains the maintainer's.**

Claim proven: a FRESH org (throwaway DB `lq_ai_b7walk`, migrated to head 0095,
`org_library_entries` empty — the G13 state) goes from first boot to a working
Commercial agent that produces a real tracked-changes redline, with ZERO manual
Library curation. The only capability-provisioning action anyone took was the
admin walking the B-7b setup wizard.

Rig: docker compose dev stack; api/arq-worker/ingest-worker temporarily repointed
at `lq_ai_b7walk`; web container serving the prebuilt bundle (includes the B-7b
wizard); headless Cypress/Chromium for all UI legs (real logins, no mocks);
plain curl for the API legs. No passwords, tokens, or JWTs appear in this
directory.

## Stage A — admin first run + setup wizard (PASS)

1. **Forced password change** — `admin@lq.ai` (bootstrap, `must_change_password=true`)
   logged in at `/lq-ai/login`, was forced to `/lq-ai/change-password`, completed the
   change, was signed out (server revokes sessions) and re-authenticated with the new
   password. Evidence: `00-first-run-password-change.mp4` (full flow on video);
   `GET /api/v1/users/me` afterwards showed `must_change_password: false`.
2. **Auto-launch on empty Library** — visiting `/lq-ai` as the admin redirected to
   `/lq-ai/admin/setup` (asserted on URL; the Library was empty). Screenshot:
   `01-auto-launch-wizard.png` (profile picker: Blank / Commercial / Privacy).
3. **Wizard walk** — picked Commercial → filled the House Brief (Helios Analytics
   GmbH, customer-protective posture; verified persisted: `organization_profile.content_md`
   220 chars) → review step showed the activation summary "9 skills and 2 tool
   groups … 3-sub-agent roster" (`02-review.png`) → clicked **Activate** → done step
   receipt "Commercial is ready. 11 capabilities adopted into your Library."
   (`03-activated.png`).
4. **Library populated** — `/lq-ai/admin/library` lists the adopted entries
   (`04-library-populated.png`). DB ground truth: 11 `org_library_entries`
   (9 skills + `redlining` + `tabular` tool groups); `practice_area_skills` = 9 and
   `practice_area_tool_groups` = 2 for area key `commercial`.

## Stage B — invite a member (PASS)

5. As admin: `POST /api/v1/admin/users/invites` (`role: member`) → 201 with
   `email_sent: false` and the out-of-band `accept_url` (mail-off fallback).
   The member opened `/lq-ai/accept-invite?token=…`, set a password + display
   name, and landed on the success card (`05-member-accepted.png`). Member login
   verified via `POST /api/v1/auth/login` → `role: member`, `is_admin: false`.
   - Deviation: `member@b7walk.test` was rejected by EmailStr (reserved `.test`
     TLD); used `member@b7walk-demo.com`.

## Stage C — member runs the Commercial agent (PASS)

6. As the member (API):
   - `POST /api/v1/projects` → matter "Helios Cloud MSA — Vendor Review",
     id `244d76a9-1811-45de-8899-4cb5709186c0`, bound to the `commercial`
     practice area (verified in DB — the read schema does not echo the field).
   - `POST /api/v1/files` (multipart, `project_id` form field) →
     `MSA-Helios-Cloud.docx` (39,299 bytes); `ingestion_status` reached `ready`
     within ~35 s of upload.
   - `POST /api/v1/agents/runs` with a customer-protective review + redline
     prompt → run `316ede1f-2cc2-464f-b26e-0652856e67e9`
     (thread `b418f657-0347-4389-ae8f-e022b26c8a27`), `model_alias: smart`,
     `budget_profile: balanced`.
7. **Run settled `completed`** — started 14:33:22Z, finished 14:36:38Z
   (**3 m 17 s**), 71 steps, 561,296 tokens, est. cost $1.68. No HITL pause
   occurred, so the resume/approve path was not exercised in this walk.
   Full receipt: `agent-run-receipt.json` (run + step rows).
8. **Acceptance criterion** —
   - Redline artifact exists in the matter's documents:
     `MSA-Helios-Cloud (redlined).docx` (43,939 bytes) with
     `created_by_run_id = 316ede1f-…` (`matter-files.json`).
   - Receipt shows redlining tool calls: `preview_redline` ×4 + `apply_redline`
     ×1 (plus retrieval, roster, matter-memory and matter-fact calls).
   - Artifact verified at OOXML level: the downloaded docx
     (`MSA-Helios-Cloud-redlined.docx`) is a real Word document containing
     **15 `<w:ins>` and 7 `<w:del>` tracked-change elements** — matching the
     agent's own "9 edits, 15 tracked-change regions" summary.
9. **Member UI evidence** — logged in as the member:
   `06-agent-run-receipt.png` (conversation with the run summary),
   `06b-agent-run-redline-steps.png` (timeline scrolled to the
   preview_redline / apply_redline steps),
   `07-redline-document.png` (Documents tab: the redline with its "Redline"
   badge next to the original upload).

## Findings for the maintainer

- **Sporadic "Failed to fetch" from the SPA to the api (dev rig)**: three
  occurrences during the walk (login POST, profiles GET, house-brief save POST),
  each on the first request after a few idle seconds. Pattern matches a stale
  keep-alive connection race (uvicorn's ~5 s idle close vs. connection reuse;
  possibly amplified by the Cypress proxy). Worked around in the temp specs by
  forcing `Connection: close` per request — zero failures afterwards. Worth a
  follow-up look (e.g. uvicorn `timeout_keep_alive`), though it may be
  test-rig-specific; not a B-7 blocker.
- Stage A ran in two spec passes because one of those flakes aborted the first
  pass after the password change had already committed; the change-password leg
  is therefore evidenced on video rather than a still screenshot.
- No HITL pause fired for `apply_redline` under the fresh-org default policy —
  if the milestone expects a stop-and-ask before the redline applies, that is a
  separate check to run; this walk neither configured nor removed any pause
  policy.

## Inventory

| File | What it shows |
|---|---|
| `00-first-run-password-change.mp4` | bootstrap login → forced change → re-login → auto-launch (video) |
| `01-auto-launch-wizard.png` | empty Library auto-launched the wizard (profile picker) |
| `02-review.png` | review & activate step, activation summary (9 skills / 2 tools / 3 sub-agents) |
| `03-activated.png` | done step receipt: 11 capabilities adopted |
| `04-library-populated.png` | admin Library page populated post-activation |
| `05-member-accepted.png` | member invite accepted ("You're all set") |
| `06-agent-run-receipt.png` | member's conversation view, run summary |
| `06b-agent-run-redline-steps.png` | run timeline: preview/apply redline steps |
| `07-redline-document.png` | Documents tab: redline artifact + Redline badge |
| `agent-run-receipt.json` | settled run + 71 step rows (tool calls incl. apply_redline) |
| `matter-files.json` | matter file listing with `created_by_run_id` provenance |
| `MSA-Helios-Cloud-redlined.docx` | the actual artifact (15 ins / 7 del tracked changes) |
