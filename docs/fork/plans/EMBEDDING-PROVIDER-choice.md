# Plan — Per-matter selectable embedding provider (ADR-F056)

**Status:** proposed (plan + ADR for sign-off). **Sequencing:** implement AFTER tabular **T4** (the
search-per-cell cap stops thrash regardless of retrieval quality; retrieval already works today via the
2026-07-01 local-alignment fix). **Granularity:** per-matter, firm-default-inherited. **Providers v1:**
local + gateway(OpenAI); Voyage later.

## Why (one paragraph)

The 2026-07-01 incident (matter `20ce20fb`) proved the embedding provider is (a) silently drift-prone —
ingest embedded `embedding_local` with `local`, the query embedded with `gateway`, cosine compared two
vector spaces = garbage, and nothing recorded which model made each vector; (b) silently degradable — the
dev gateway's `embedding` alias 503s (no OpenAI key) so the query fell back to FTS-only and the tabular
agent thrashed to the 600-step cap; (c) unobservable — a half-embedded matter looked "ingested". It also
surfaced a real product need: the operator should CHOOSE, per matter, between **local** (private, $0,
sensitive) and **inference** (stronger embeddings, egress + spend). This slice makes that choice a
first-class, safe, per-matter setting. See [[embedding-provider-mismatch-and-choice]].

## Goals

1. **A per-matter provider choice** (`projects.embedding_provider`, NULL = inherit firm default), owner-owned,
   admin sets the firm default.
2. **Structural ingest↔query lock** — ONE `resolve_matter_embedding(project) → (provider, model, dim)`
   consumed by ingest, query, and re-embed; plus `EMBEDDING_PROVIDER` added to the ingest-worker compose block
   so the firm default itself can't drift between services.
3. **Per-chunk provenance** (`document_chunks.embedding_local_model`) so a vector is trusted only when it
   matches the matter's active model — mismatch degrades to FTS, never garbage.
4. **A re-embed job** triggered on provider change (idempotent, resumable, batched, OOM-aware, background).
5. **Observable coverage** — a per-matter retrieval-health read (total / embedded-with-active-model / stale),
   and an FTS-only-fallback *degrade log* instead of a silent swallow.
6. **v1 providers:** local (bge-base) + gateway(OpenAI `text-embedding-3-small` @ dim 768). Voyage seam left
   clean.

## Non-goals

- **No dimension change.** Pin dim=768 for all providers (OpenAI via `dimensions=768`); the `vector(768)`
  column and the frozen E0/Slice-A FTS baselines + `_REFERENCE_FTS` guard stay byte-identical.
- **No Voyage** in v1 (its gateway provider + dep + SBOM/ADR is a follow-up; no app seam needed then).
- **No practice-area default layer** (backlog — a middle layer in the resolver).
- **No per-run override** (per-matter only, mirroring F054).
- **No change to the KB/chat `embedding` (1536) column** or its gateway ingest — this is the matter
  `embedding_local` path only.
- **No T4 work here** (separate slice; this depends on it landing first).

## Implementation

### A. Schema — migration `00NN` (additive)
- `projects.embedding_provider TEXT NULL` (NULL = inherit `Settings.embedding_provider`).
- `document_chunks.embedding_local_model TEXT NULL` — the model id that produced `embedding_local`.
- **Backfill** existing non-null `embedding_local` rows to `BAAI/bge-base-en-v1.5` (what actually made them).
- up→down→up on a throwaway pgvector; rebuild api+arq+ingest together.

### B. Resolver — NEW `resolve_matter_embedding(project, settings) → (provider_key, model_id, dim)`
- Single source of truth. `provider_key = project.embedding_provider or settings.embedding_provider`;
  `model_id` = the provider's canonical model (local→`embedding_model`; gateway→the gateway embedding model);
  `dim` = 768 always. Returns a small frozen dataclass.
- Consumed by: the ingest embed step, `tools._search`/`_embed_query`, the re-embed job. No other code reads
  `settings.embedding_provider` for the matter path.

### C. Retrieval provenance filter — `api/app/knowledge/retrieval.py`
- Vector arm (`_MATTER_VEC_*`) gains `AND embedding_local_model = :active_model`. FTS arm + the FTS-only
  fast path are **untouched** (byte-identical guard holds). `matter_hybrid_search` takes an `active_model`
  param (from the resolver at the call site in `tools._search`).
- `_embed_query`: on gateway 503 / provider error, keep the existing FTS fallback BUT emit a structured
  `retrieval_semantic_degraded` log (matter id, provider, reason) — no silent loss.

### D. Ingest + re-embed — `api/app/knowledge/embed.py`
- `embed_local_chunks_for_file`: stamp `embedding_local_model` on write; select `WHERE embedding_local IS
  NULL OR embedding_local_model <> :active_model` (so a re-embed replaces stale-space vectors). Provider from
  the resolver (matter-aware), not the global.
- NEW `reembed_matter_job` (arq): resolve active model, clear+recompute mismatched/null chunks for every file
  in the matter, batched + resumable; audit `embedding.matter_reembedded` (counts + model id, body-free).
  Enqueued by the PATCH in §E on a provider change.

### E. API — matter provider get/set + coverage
- `GET /api/v1/matters/{project_id}/retrieval` → `{provider (effective), source: 'matter'|'firm-default',
  coverage: {chunks, embedded_active, stale}}`. Owner-scoped; cross-user/archived/sandbox → 404.
- `PATCH …/retrieval {provider}` → validates against the known provider set (422 on unknown), writes
  `projects.embedding_provider`, enqueues `reembed_matter_job`, audits `embedding.provider_changed` (id/kind).
  Warns (payload flag) when switching a `privileged` matter to inference. New `/api/v1` path ⇒ the governance
  guards in `test_endpoints.py`/`test_openapi.py` + count bump.
- Firm default: admin sets `Settings.embedding_provider` (existing env) — document it; optionally a read on
  an admin endpoint (no new write surface needed for v1).

### F. Web — matter retrieval setting + coverage chip
- A "Retrieval / Embeddings" control in the matter capability/settings surface (app.css `var(--brand)`):
  provider radio (Local — private · Inference — OpenAI), effective-source hint, coverage chip
  (`245/245 embedded`), and the privileged-switch warning. Owner-owned; pure helpers unit-tested (vitest;
  no @testing-library/svelte). Rebuild the prebuilt web bundle before any screenshot/Cypress.

### G. Config / compose
- Add `EMBEDDING_PROVIDER: ${EMBEDDING_PROVIDER:-local}` to the **ingest-worker** service block (anti-drift).
- Keep `RERANK_ENABLED=false` on the ~6 GB dev box (OOMs both ONNX models; embedder-alone is fine).

## Resource-aware execution (companion — ADR-F056 §Resource-aware execution)

The provider work and box stability share one root cause (in-process model memory). This slice carries the
resource-aware companion in three layers:

- **Layer 1 — static containment (DONE 2026-07-01, dev config only, already applied):**
  `docker-compose.yml` worker `mem_limit` (ingest 3g / arq 2.5g) + `mem_reservation` so a runaway worker
  self-OOMs in its own cgroup instead of killing Postgres; `.env` `LQ_AI_INGEST_WORKER_CONCURRENCY=1` and
  `FAN_OUT_QUOTA=4` (forwarded to arq-worker in compose) to cut peak concurrency. Verified: limits effective,
  `settings.fan_out_quota==4`. Reversible; no app code. CAVEAT: `FAN_OUT_QUOTA` binds only the **balanced**
  budget profile — economy (8) and generous (48) are hardcoded in `api/app/agents/budget.py`, so a run
  launched on "generous" fans out to 48 regardless; on a constrained box the `mem_limit` cgroup is then the
  only containment.
- **Layer 2 — self-sizing at boot (build with this slice):** a small startup helper that reads the container's
  **cgroup memory limit** (`/sys/fs/cgroup/memory.max`, cgroup v2; fall back to v1 / host with a logged
  warning) + core count and derives safe defaults for fan-out + ingest concurrency + whether to load ONNX
  in-process. Pure, injected, unit-tested against synthetic cgroup values. Depends on Layer 1's limits (the
  only reliable in-container signal).
- **Layer 3 — live memory brake "R7" (design here; implement as its own follow-up, may get its own ADR):** at
  the `FanOutQuotaMiddleware` / ingest chokepoint, sample cgroup used-vs-limit; under a headroom threshold,
  serialize to concurrency 1 or defer, degrading gracefully. Slots into the R4/R5/R6 brake family + the
  `BudgetEnvelope` as a resource dimension. Out of scope to *implement* in this slice; the plan reserves the
  seam and the config field.

## Critical files
- NEW resolver module (or a function in `api/app/knowledge/embedding_provider.py`); `retrieval.py`
  (provenance filter + degrade log); `embed.py` (stamp + re-embed select + `reembed_matter_job`);
  `api/app/agents/tools.py` (`_search` passes the resolved active_model); NEW matter-retrieval API +
  router registration; `api/app/config.py` (doc the firm default); migration `00NN`; `docker-compose.yml`
  (ingest-worker env); web matter-settings component + api client.
- Tests: resolver; retrieval provenance filter + FTS byte-identical; migration up/down; re-embed idempotence
  + provenance stamping + resumability; coverage calc; API get/patch (owner 404s, 422, audit body-free);
  no-override byte-identical; web vitest helpers.
- Docs: ADR-F056 (this slice); `MILESTONES.md`; `HANDOFF.md`; memory
  [[embedding-provider-mismatch-and-choice]]; evidence dir.

## Verification / DoD (ADR-F005 gate)
- Deterministic suites (dev image, repo root + `skills→/skills:ro`, `--network lq-ai_default`,
  `DATABASE_URL` by NAME): all of the above, counts quoted; CI `ruff check`/`ruff format --check`/`mypy`
  clean; the `_REFERENCE_FTS`/E0/Slice-A baselines byte-identical.
- Live dev-stack: switch a matter local→gateway (once an OpenAI key is on the gateway) → re-embed →
  `matter_hybrid_search` returns; switch back → re-embed → returns; privileged-matter default local + switch
  warning; coverage endpoint reflects a mid-re-embed matter. Screenshots/logs in the evidence dir.
- Image: rebuild api+arq+ingest together; `docker image prune -f` (dangling only) after.
- Fresh-context adversarial review incl. the mandatory security + simplification pass: no secret/text in
  audit or logs; provider choice is a human write (no agent tool); egress only via the gateway; owner-scoped
  404s; injected resolver (no global reach in business logic); no stray files; dead-code/dup sweep.
- Merge under the full ADR-F005 gate (`gh … --repo sarturko-maker/lq-ai-fork`; branch+PR; commit trailer).

## Risks / gotchas
- **Mixed-space vectors** are the whole point of provenance — never compare a vector whose model ≠ active.
  The regression test that the no-override path is byte-identical is the hard guard.
- **Gateway embeddings need a real key** — v1's inference door is inert on the dev box until an OpenAI
  credential is set on `openai-prod`; the coverage/degrade log makes that state obvious rather than silent.
- **Dev-box OOM** — re-embed is a background job, batched, rerank-off; never inline in a run.
- **Dimension pin** — if a future provider can't do 768, that forces a second vector column (deferred, noted
  in ADR §Consequences).
- **Secret hygiene** — during the incident the dev Postgres password + DEEPSEEK_API_KEY leaked to the
  session transcript; ROTATE. Inspect env by NAME; never widen a `.env` read.

## Recommended order
migration + provenance backfill → resolver → retrieval provenance filter (+ FTS byte-identical test) →
embed stamp + `reembed_matter_job` → tools._search wiring → matter-retrieval API + guards/count → web
control + coverage chip → compose ingest lock → docs/ADR/HANDOFF/memory → adversarial review → PR + merge.
