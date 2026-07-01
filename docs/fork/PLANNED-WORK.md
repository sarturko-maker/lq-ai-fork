# PLANNED-WORK — categorized snapshot of everything NOT yet shipped

> **Snapshot dated 2026-07-01.** A readable, category-grouped overview of the fork's *unshipped* work,
> derived from `docs/fork/MILESTONES.md` + `docs/fork/HANDOFF.md` + the ADRs/plans/memory on this date.
> **`MILESTONES.md` remains the source of truth**; this file is a periodically-refreshed bird's-eye view so
> the whole todo survives context-compaction in one place. Shipped items are deliberately omitted.
>
> **CURRENT DIRECTION (2026-07-01): pivot to build the AI COMPLIANCE deep agent** (a second regulatory
> module, near-twin of Privacy). Plan: `docs/fork/plans/AI-COMPLIANCE-module.md`. Everything below is the
> backlog that this pivot is prioritised *ahead of* (tabular T5 / F056 etc. continue as the prior track).

Tags: `[merge]` code done, awaiting merge · `[next]` teed up · `[deferred]` blocked on a decision/box ·
`[backlog]` later · `[research]` decide-before-building · `[bug]`/`[security]`.

## AI Compliance module (NEW — the pivot)
- `[next]` See `docs/fork/plans/AI-COMPLIANCE-module.md` — the near-twin-of-Privacy EU AI Act register +
  deterministic risk-classification rules engine + conversational intake + cockpit register UI. Rides
  ADR-F018 (typed domain + code-validated writes + domain UI) + F020 (intake) + F021 (authz), never precedes
  them. Reference-only: the maintainer's private `EU_AI_Act` repo (take the idea, not the code).

## Tabular review
- `[merge]` **#185** — T6 cockpit-stage interactivity + sticky-column fix (current branch)
- `[merge]` **T4 / #187** — no-thrash retrieval-fill (awaiting API CI + maintainer nod)
- `[next]` **T5** — live cell fill (row-by-row animation; uses `gather_row_evidence` as seam)
- `[deferred]` **T4 eval gate** — retrieval-fill vs read-in-full cell quality (OOM → needs isolated box)
- `[deferred]` **T8b** — combine_documents (needs per-cell `document_id` first)
- `[backlog]` **T9** source-highlighting in Collabora · **T10** rich grid affordances · **T11** per-cell cost preview
- `[backlog]` **T6 phases P2–P5** (verified/flagged cells + meter → output-types → party column → deliverables)
- `[backlog]` cross-cutting: agent-facing grid-listing tool · grid→Word deliverables · virtualization >100 rows
- `[next]` **Phase-2: tabular as in-matter tool + LQ-Grid** (needs its own plan + ADR; React-vs-Svelte call)

## Retrieval & embeddings
- `[merge]` **#186** — OOM hardening + ADR-F056 doc (CI green)
- `[next]` **F056** — per-matter embedding provider (local vs OpenAI/Voyage) + config fix: lock ingest-worker
  to shared `EMBEDDING_PROVIDER`
- `[research]` **Slice P — PageIndex** (gateway-bound, vectorless; runs on this box; draft ADR-F052)
- `[deferred]` N=150 hybrid+rerank calibration · Phase-3 recency + Documents-MAP (need ≥16 GB box / unmet triggers)
- `[deferred]` `cost_usd` exact per-run attribution · `[backlog]` "typical run ~$X" pre-run hint
- `[backlog]` embedding provider for KB + chat vector search

## Research questions (decide before building)
- `[research]` **max_steps vs token-cap** — is the 400-step brake right, or should tokens govern? (ADR-worthy)
- `[research]` tier-4 large-matter delegation (model won't fan out at realistic sizes)

## Dev-box / infra
- `[next]` give Postgres an OOM floor / lower arq mem_limit (sum of limits > host RAM)
- `[security]` rotate leaked dev creds: Postgres password, DEEPSEEK key, gateway key
- `[backlog]` economy/generous budget tiers ignore `.env FAN_OUT_QUOTA` (only balanced reads it)
- `[deferred]` ADR-F056 resource-aware layers 2 (self-size from cgroup) + 3 (live "R7" memory brake)
- `[gotcha]` revert gateway aliases (smart/fast/budget) to MiniMax when quota returns
- `[backlog]` per-phase/per-tool cost budgets · checkpoint pruning + ShallowPostgresSaver · ingest-orphan
  robustness · checkpoint-row cleanup on delete · deploy/helm values cleanup

## Memory tiers
- `[deferred]` **Practice Knowledge (ADR-F050)** — cross-matter shared learning; the prize, own milestone
- `[backlog]` wire Lawyer Preferences into prompts (`load_kept_memory` uncalled) · client/counterparty profile
  entity · matter digests + "where were we?" card · memory-manager UI · runtime isolation tests ·
  search-past-chat-within-matter
- `[deferred]` per-turn conversation granularity · `[backlog]` revisit Zep/Graphiti temporal graph

## Practice areas & platform
- `[deferred]` Commercial **C6** playbook-controlled skills (blocked on ADR-F036/F038)
- `[backlog]` counter-with-reply skill tuning (0/3) · deepagents profile for deepseek · configurable ethics
  gates per area · email entry points + Word add-in revival
- `[backlog]` **F1**: decision inbox · trust chrome (citations/receipts) · `work_product_attributions` fan-out
  extension · auto-filing resolver
- `[backlog]` **F3**: promote area pages to top-level IA · heartbeat absorption · unified search box ·
  background continuation on laptop-close
- `[deferred]` **Oscar Edition rebrand** (needs its own ADR; required pre-release)

## Privacy module
- `[deferred]` ROPA intake half (~50-question intake + bulk-extract UX)
- `[bug]` find-or-create **DeadlockDetectedError** under parallel tool calls (HIGH)
- `[backlog]` ship ropa-population skill migration · ROPA quality gaps (invariant/transfers/recipient-role) ·
  PRIV-6d controller scope + Art 30 export · P2 tracks (DSAR/breach/DPA/reg-gap/reporting) ·
  populate-records-from-a-source family
- `[deferred]` ROPA private-to-shared info-flow gap (closed by F021)

## Redlining module
- `[in-flight]` Module 2 framing/decomposition (mostly realised via Commercial slices; needs own ADR)
- `[backlog]` surgical-gate friction / agent thrash · strong-judge confidence-interval eval
- `[deferred]` Adeu MCP Apps interactive redline review (MCP-gated)

## Authorization
- `[deferred]` **ADR-F021** areas-of-responsibility (users↔areas, roles, sharing, phases 1–5) — load-bearing
  design contract *now*, needs acceptance to enforce

## MCP
- `[deferred]` MCP capability milestone (approval-gated; upstream-sync proposal + ADR) · per-area MCP servers (F3)

## Security (defense-in-depth)
- `[backlog]` guard DB-error message scrubbing · `user_sessions` HMAC index (DoS) · nginx CSP/security headers ·
  streaming anonymization rehydration test · MessageBubble DOMPurify image-beacon · guard frontend-static
  area-ids leaking into rows

## Licensing
- `[backlog]` PyMuPDF AGPL cleanup · Collabora production licence posture (self-build vs subscription)

## Housekeeping / polish
- `[backlog]` flip ~12 stale "proposed" ADRs that already shipped → accepted · decide on untracked demo packs +
  live scenario tests · reconcile `c3-update-memory-ux` branch · cockpit chat polish (GFM final answer,
  quieten tool calls) · **EU AI Act register module** (now superseded by the AI Compliance pivot above) ·
  project rename pre-release
- `[backlog]` **long tail (~15 web/deploy nits):** thread-list pagination · eslint-9 flat config · openapi
  regen · searchable matter picker · notification bell · restyle bare selects · retire legacy Cypress specs ·
  `<think>` block handling · per-block thinking ribbons · Matters-page file UI · reconcile file↔project relations
