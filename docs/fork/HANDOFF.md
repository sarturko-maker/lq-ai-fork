# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

> ═══════════════════════════════════════════════════════════════════════════════════════════════════════
> **OVERNIGHT RUN COMPLETE (2026-07-11 → 07-12, maintainer travelling, "run until the morning").**
> The maintainer's four-thread directive is fully discharged; BOTH feature threads are MERGED to main:
>
> **① WORKSPACE ✅ MERGED PR #271 (`bbedd04d`, ADR-F082, mig 0096).** Duplicate detection (code-computed
> from `hash_sha256`, matter+owner scoped, never agent-asserted) + per-document summaries
> (`record_document_summary`, auto-write-then-correct) surfaced three ways: agent inventory markers, a
> 6th read-only prompt tier (data-only fence, 30 lines/8k chars, visible "+K more" tail), and
> `MatterFileRead.summary/duplicate_of` → amber "identical to X" badge + summary subtitle in the
> Documents panel. Full gate: CI ×3; **18-finding adversarial review ALL fixed** — highlights: the
> summary resolver now mirrors `read_document`'s exact rule (case-insensitive, readable-first);
> newline/"(duplicate of" forgery REJECTED at the write boundary; the human half exists (`PUT
> /matters/{id}/files/{file_id}/summary`, `summary_author` 'agent'|'human', **pins win** — the agent
> refuses to overwrite a human summary); stale summaries carry an explicit suffix (`summary_stale`);
> work products render F066 provenance, never "not yet read". Live-verified on the rebuilt trio
> (evidence in the PR comment).
>
> **② ADV-1 ✅ MERGED PR #272 (`482c6078`, ADR-F084, mig 0097).** The agent-OFFERED hostile reader:
> `adversarial_review` = a TOP-LEVEL lead tool riding the redlining grant set (subagents are
> HITL-un-gateable — that's WHY it's a lead tool), one purpose-specific gateway pass
> (`lq_ai_purpose="adversarial_review"` — now in the gateway `_KNOWN_PURPOSES`; **gateway RESTART
> needed on deploy**), full accept-all text (60k cap, honest truncation; the negotiation
> `clean_view` is 8k-bounded — extracted directly instead), strict-JSON findings (25 cap, severity ×
> {over_reach, under_protection, inconsistency, gap}), reject-not-crash, counts-only audit.
> `skills/adversarial-review` coaches WHEN to offer (stance-distinct from deal-review /
> negotiation-review). Bound the post-B7a way (mig 0097 bind + users-gated Library adoption +
> manifest + RECOMMENDED together — parity oracle green). **Default OFF**; the admin HITL toggle is
> the confirm card. Review: 5 confirmed → 4 fixed (incl. focus fenced as steer-only + echoed
> "FOCUS APPLIED" in the render; textless-docx reject before spend), 1 deferred on record
> (shared gateway-JSON helper — MILESTONES backlog). **Deferred on record:** seeded-defect recall
> eval (box OOMs ONNX; recipe in `docs/fork/plans/ADV-hostile-reader.md`) + the live offer walk
> (maintainer VM session).
>
> **③ MODEL QUESTION answered + ④ ROUTER research delivered** — `docs/fork/plans/ROUTER-model-selection.md`
> (research ONLY, per the maintainer): smart/fast/budget is the wrong primary axis → three orthogonal
> axes (capability-role `reasoning`/`balanced`/`bulk` × operator task-class aliases × the existing tier
> floor); NDA→balanced, M&A fan-out = reasoning lead + bulk workers; smallest build = config-only
> gateway.yaml; the REAL prerequisite is eval-gating (CUAD/masked-judge harness); F083 reserved.
> Per-subagent models = gateway-bound INSTANCE injected in composition only (config path is a dead
> end); verify deepagents 0.6.8 honours a per-spec instance before building.
>
> ◀ **PICK UP HERE: DIRECTION SET 2026-07-12 — product-first, enterprise-last** (resolves the
> enterprise-vs-product call). Maintainer's 4-phase roadmap:
> **(1) VM UAT bug-fixing — ACTIVE.** Maintainer tests the shipped stack on the Azure VM and sends
>     feedback (ad-hoc/random, *may branch into side-quests*); we FIX broken bugs/features FIRST,
>     before any new build. No proactive slice — next work = whatever the feedback surfaces.
> **(2) CUSTODIAN** — per-matter obligation/exposure/why/outcome capture (#510/#512–#514; ADV-1 done).
> **(3) Matter-wisdom escalation = Practice Knowledge** (ADR-F050 / `PRACTICE-KNOWLEDGE-prize.md`): the
>     de-identify→guard→curator-approve harness. DESIGNED, NOT built; CUSTODIAN WHY-1/OUTCOME-1 bank
>     its raw material. NB the authoring pipeline (propose→approve→Library→bind) + knowledge-collection
>     tool group already exist — they escalate HUMAN-authored content; this escalates AGENT-noticed
>     matter wisdom, which is why it needs the confidentiality+poison harness. Slice-1 = light up the
>     write-only Lawyer Preferences shelf (cheapest on-ramp).
> **(4) Enterprise-grade deployment** — K8S/AKS ladder (F073–F080; the 5 confirmed scale bugs). Real
>     customer runs on the demo-grade VM/compose path meanwhile; scale-hardening waits for this phase.
> **Still-open QUICK CALLS (fold into phase 1, not blockers):** shipped-profile HITL defaults
> (`apply_redline` + `adversarial_review`); the 5 untracked strays (one carries a RUF002 `×`); router —
> adopt taxonomy / when to build (research, ~phase 4).
> GATED/deferred: CLEAN-3b #505; #504 claim-grace; AZ-4 parked; AZ-6 keyless-MI branch unpushed;
> ADV seeded-defect eval + live walk; SUMMARY-EDIT / NEAR-DUP / GATEWAY-JSON helper (MILESTONES backlog).
>
> **MAINTAINER'S AZURE-VM LIVE-TEST SCRIPT (pull main `482c6078`+, rebuild SERIAL with cache —
> never `--no-cache ×4`; stale web bundle hides features; the gateway needs a RESTART for the
> adversarial_review purpose tag):**
> ① Fresh-org wizard (B-7 sign-off) — empty Library → auto-launch → Commercial → agent redlines.
> ② F081 living redline — "redline it" → "further redline" → SAME doc updates in place.
> ③ WORKSPACE — upload the same contract twice → amber "identical to …" badge; ask the agent about
> the documents → it names the duplicate and works from one; after it reads a doc, the summary
> appears under the filename (stale suffix after you edit the doc; you can correct/clear it via the
> PUT endpoint — panel affordance is backlogged).
> ④ ADV — set Commercial `hitl_policy` = adversarial_review → ask for a redline of a high-stakes
> doc → the agent OFFERS the hostile-reader pass → "Waiting for your go-ahead" card → Approve →
> severity-ordered findings (try `focus`: the render shows "FOCUS APPLIED").
> ⑤ HITL-3 UAT (apply_redline card) · ⑥ B-4/PUBLISH UATs · ⑦ decide profile-HITL defaults ·
> ⑧ AZ-6 keyless-MI review+push+smoke.
> ═══════════════════════════════════════════════════════════════════════════════════════════════════════

## State

- `main` = `482c6078` — WORKSPACE (#271) + ADV-1 (#272) merged on top of the wrapped B-stack;
  deployable for the VM pull. Branches deleted. Dev stack rebuilt on main (migs 0096+0097 applied,
  keep-alive 130s, healthy at wrap time).
- Docs: ADR-F082 + ADR-F084 (proposed — maintainer accepts); plans WORKSPACE-awareness /
  ADV-hostile-reader / ROUTER-model-selection; CLAUDE.md tier table gains **Matter Documents**;
  MILESTONES § Backlog gains SUMMARY-EDIT, NEAR-DUP, GATEWAY-JSON lines.
- Memory topic: `workspace-awareness-shipped.md` (traps: mounted-repo test races; suites run ALONE —
  concurrent vitest OOM-kills pytest SILENTLY; gateway prod image has no dev deps — gateway checks
  are CI-only; new-shipped-skill 4-piece checklist).

## Done (this session)

WORKSPACE WS-1/2/3 merged (#271, 18-finding review fixed, live-verified) · ADV-1 merged (#272,
5-finding review fixed/deferred) · router research delivered (doc final) · model-per-subagent
question answered · HANDOFF/memory current.

**Phase-1 VM UAT fix #1 (task #521, branch `fix/web-healthcheck-ipv4`):** web container falsely
`(unhealthy)` on the Azure image — nginx `listen 8080;` binds IPv4-only `0.0.0.0:8080`, but that
image's `/etc/hosts` resolves `localhost`→`::1` first, so the `wget http://localhost:8080/health`
probe gets connection-refused while it serves fine on IPv4. Fixed `localhost`→`127.0.0.1` in ALL
THREE tracked sites (the maintainer's grep found them; the suggested fix covered only compose):
`docker-compose.yml:488`, `docker-compose.prod.yml:410`, `web/Dockerfile:34` HEALTHCHECK (image
default → bare `docker run` / Caddy overlay). Helm web probe is a kubelet→pod-IP httpGet, NOT
localhost — unaffected, left alone. No app behaviour changed. Live-verified: rebuilt web → `healthy`
+ `127.0.0.1:3000/health`→200 `ok`. This was the FIRST piece of maintainer VM feedback.

**Phase-1 VM UAT fix #2 (task #523, branch `fix/cors-allow-put`, PR #276):** saving House Brief
(`PUT /organization-profile`) and Branding (`PUT /branding`) failed cross-origin with browser
"Failed to fetch" while chats (POST) worked. Root cause: `api/app/main.py` CORS `allow_methods`
listed GET/POST/PATCH/DELETE/OPTIONS but **not PUT** → the PUT preflight (OPTIONS) 400s and the
browser never issues the request (no HTTP status reaches the app → fetch-level error, not a 4xx).
Only bites cross-origin (`LQ_AI_CORS_ORIGINS` set: Compose `web:3000` vs `api:8000`, or split-origin
deploy). **All FOUR PUT endpoints were dead** — also the WORKSPACE matter-file summary correction
(`PUT /matters/{id}/files/{file_id}/summary`) and the practice-area HITL-policy save
(`PUT /practice-areas/{key}/hitl-policy`, the adversarial-review toggle). Fix = add PUT (hoisted to a
`CORS_ALLOW_METHODS` constant) + regression test (PUT preflight allowed + a drift guard: every verb
the router serves must be allowlisted). CORS is browser-only, not authz — each PUT still enforces
AdminUser server-side; `allow_origins` stays a strict allowlist. Live: all four preflights 400→200.
ruff+mypy clean, new test 2 passed.

## Next slice

**Phase 1 ACTIVE — VM UAT bug-fixing** (direction set 2026-07-12; product-first sequence in the
banner: 1 VM-bugs → 2 CUSTODIAN → 3 Practice Knowledge → 4 enterprise K8S). No proactive slice: the
next work is whatever the maintainer's VM feedback surfaces — triage → fix under the full ADR-F005
gate; side-quests expected; create a concrete task per bug as it lands. CUSTODIAN (#510/#512–#514,
OBLIG-1 first) is the phase-2 queue, unchanged.

## Gotchas (this session — history in memory topics)

- Containerized pytest reads the live repo mount at collection AND app-boot: never edit api/, add
  migrations, or add skills/ mid-run; never run vitest concurrently (silent OOM kill, empty output,
  exit 0). Clean re-run before diagnosing phantom errors.
- Gateway checks CANNOT run locally (prod image, no dev deps) — the gateway CI job is the gate.
- The `adversarial_review` purpose tag requires a gateway restart to register (C3b-2 trap class).
- Same-transaction file seeds share `created_at` → dup canonicality falls to the id tiebreaker
  (test artifact only; real uploads are separate transactions).
