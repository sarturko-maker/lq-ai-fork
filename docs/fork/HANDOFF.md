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
> ◀ **PICK UP HERE: HOLD (again).** Everything remaining is maintainer-gated. **DECISIONS AWAITING
> (do not pre-empt):** (1) enterprise-vs-product call (CUSTODIAN #510/#512–#514 gated); (2) shipped-
> profile HITL defaults — now covers `apply_redline` AND `adversarial_review`; (3) fate of the 5
> untracked strays (4× scenario `test_*_live.py` + `sample-documents/` — one carries a RUF002 `×`
> that trips broad ruff sweeps); (4) router: adopt the taxonomy / pick the seam / when to build.
> GATED/deferred: CLEAN-3b #505; AZ-4 parked; AZ-6 keyless-MI branch unpushed; B-2c live scenario;
> ADV seeded-defect eval + live walk; SUMMARY-EDIT panel affordance + NEAR-DUP + GATEWAY-JSON helper
> (MILESTONES backlog).
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

## Next slice

None startable — all queue items maintainer-gated (decisions list in the banner). On return:
run the VM live-test script, make the four decisions, then the queue unblocks (CUSTODIAN or the
K8S ladder per decision 1; ADV eval + live walk; router build per decision 4).

## Gotchas (this session — history in memory topics)

- Containerized pytest reads the live repo mount at collection AND app-boot: never edit api/, add
  migrations, or add skills/ mid-run; never run vitest concurrently (silent OOM kill, empty output,
  exit 0). Clean re-run before diagnosing phantom errors.
- Gateway checks CANNOT run locally (prod image, no dev deps) — the gateway CI job is the gate.
- The `adversarial_review` purpose tag requires a gateway restart to register (C3b-2 trap class).
- Same-transaction file seeds share `created_at` → dup canonicality falls to the id tiebreaker
  (test artifact only; real uploads are separate transactions).
