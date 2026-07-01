# F056 — Per-matter selectable embedding provider (local vs inference)

- Status: **proposed**
- Date: 2026-07-01
- Deciders: maintainer (Arturs), agent
- Milestone: **Retrieval provider choice** (Phase 1). Builds on **ADR-F049** (native memory substrate +
  eval-gated retrieval; the `EmbeddingProvider` Door-A/Door-B seam), **ADR-F054** (per-matter config: the
  two-layer scope + resolve-time helper + byte-identical default path), **ADR-F010** (per-area Deep Agent),
  **ADR-0008** (single-egress gateway for embeddings). Companion plan:
  `docs/fork/plans/EMBEDDING-PROVIDER-choice.md`.

## Context

The matter/agent retrieval path embeds documents into `document_chunks.embedding_local` (`vector(768)`,
mig 0078) and, at query time, embeds the question with the configured `EmbeddingProvider` (ADR-F049 C1:
Door A = in-process fastembed bge-base; Door B = gateway `/v1/embeddings`). The provider is a single
process-global `Settings.embedding_provider` read identically by ingest and query.

A live incident (2026-07-01, matter `20ce20fb`) exposed three ways this silently breaks, and one product
gap:

1. **Ingest/query drift.** `.env EMBEDDING_PROVIDER` is wired to api + arq in compose but **not** to the
   ingest-worker, so ingestion embedded `embedding_local` with `local` while the query embedded with
   `gateway`. Vectors from two different models share one column but live in different spaces → cosine is
   meaningless. Nothing detects this: the column is a bare `vector(768)` with **no record of which model
   produced it**.
2. **Silent semantic-off fallback.** The dev gateway's `embedding` alias → `openai-prod/
   text-embedding-3-small` has no OpenAI credential → `/v1/embeddings` 503s → `_embed_query` degrades to
   `query_embedding=None` (FTS-only). Retrieval "works" but is keyword-only; on long contracts recall
   collapses (E0: cross-doc hit@8 0.04), and the tabular agent thrashes (235 searches, 0 rows, 600-step
   cap). A degrade-to-FTS on a matter the operator *chose* to make semantic is a silent correctness loss.
3. **Half-built, undetectable index.** The local embedder OOM'd mid-ingest; 78/245 chunks embedded; the
   matter still looked "ingested". No coverage signal existed.

The **product gap**: the operator (admin/lawyer) has no *choice* of embedding provider. That choice is real
and per-matter: a **privileged/sensitive** matter should keep document text in-house (`local`, no egress,
$0); a routine matter may prefer a stronger **inference** embedder (`gateway` → OpenAI today; Voyage's
legal-domain `voyage-law-2` later) at the cost of egress + spend. Today the only lever is a global env var,
and flipping it silently invalidates every existing vector.

## Considered options

1. **Keep it a global env var; just lock the three services + add a coverage check.** Smallest. Fixes drift
   and the silent index gap, but gives the operator no per-matter choice and still can't switch a matter to
   inference without a global re-embed of everything.
2. **Per-matter provider column, but no provenance** — store `projects.embedding_provider`, re-embed on
   change, trust the vectors. Simpler schema, but a crash/partial re-embed leaves mixed-space vectors in one
   column with no way to tell them apart — the exact incident, re-armed. Rejected: provenance is the
   load-bearing safety property, not an add-on.
3. **Per-matter provider + per-chunk provenance + a single resolver + a re-embed job (CHOSEN).** A nullable
   `projects.embedding_provider` (NULL = inherit the firm default `Settings.embedding_provider`); a nullable
   `document_chunks.embedding_local_model` recording the model that produced each vector; ONE
   `resolve_matter_embedding(project) → (provider, model, dim)` resolver consumed by ingest, query, and the
   re-embed job so they can never drift; retrieval trusts a vector ONLY when its provenance matches the
   matter's active model (mismatch ⇒ treated as unembedded ⇒ graceful FTS, never garbage); a provider change
   enqueues an idempotent, batched, owner/admin-triggered re-embed. Providers reuse the existing
   `EmbeddingProvider` seam — v1 ships **local + gateway(OpenAI)**; **Voyage** is a later gateway provider +
   model option with no new app seam.

## Decision outcome

Adopt **option 3** (maintainer-confirmed granularity/sequencing/providers, 2026-07-01).

- **Per-matter, firm-default-inherited.** `projects.embedding_provider TEXT NULL` — NULL inherits
  `Settings.embedding_provider` (the firm default an admin sets). Practice-area-level default is explicit
  **backlog** (would slot as a middle layer in the resolver, mirroring F054's scope stack). Pin **dim = 768**
  for every provider (bge-base native; OpenAI via `dimensions=768`) so the shared `vector(768)` column needs
  **no dimension change** — provenance, not dimension, distinguishes the space.
- **Dimensions/model, not just provider, define the space.** Provenance stores the resolved **model id**
  (e.g. `local:BAAI/bge-base-en-v1.5`, `gateway:text-embedding-3-small`), so two matters on different models
  never cross-read even at the same dim.
- **One resolver, three consumers.** `resolve_matter_embedding` is the sole source of the (provider, model,
  dim) triple for (a) the ingest embed step, (b) `tools._search` / `_embed_query`, (c) the re-embed job.
  Ingest/query drift becomes structurally impossible. The ingest-worker compose block gains
  `EMBEDDING_PROVIDER` so the *firm default* also can't drift between services.
- **Mismatch degrades, never lies.** `matter_hybrid_search` adds `AND embedding_local_model = :active_model`
  to the vector arm. A chunk whose provenance ≠ the matter's active model is invisible to semantic search
  (falls to FTS) until re-embedded — the same graceful posture as an unembedded chunk. No mixed-space cosine.
- **Provider change ⇒ re-embed.** Changing `projects.embedding_provider` enqueues a matter re-embed
  (clear+recompute `embedding_local` where provenance ≠ active, batched, resumable, OOM-aware). Retrieval
  stays correct throughout (mismatched vectors are already excluded).
- **Coverage is observable.** A per-matter retrieval-health read (chunks total vs embedded-with-active-model
  vs stale) surfaced to the owner, so a partial/mismatched index is visible, not silent. FTS-only fallback
  on a semantic matter is logged as a degrade, not swallowed.
- **Egress is an explicit, audited per-matter decision.** `local` = no egress (the default for a
  `privileged` matter; the UI warns before switching a privileged matter to inference). `gateway`
  (OpenAI/Voyage) egresses document text via the single gateway (ADR-0008 preserved). Audit records the
  provider/model **id + kind + counts** on change and re-embed — never document text.
- **"System proposes, user owns."** The firm default is admin-set; the per-matter provider is owner-owned
  (like the F054 toggles). No agent tool sets it — it is a human choice.

## Consequences

- Two additive columns (`projects.embedding_provider`, `document_chunks.embedding_local_model`), one
  migration, backfilling existing chunk provenance to the current local model (`BAAI/bge-base-en-v1.5`,
  what actually produced them). No dimension change; the frozen E0/Slice-A FTS baselines + `_REFERENCE_FTS`
  drift guard stay byte-identical (the FTS-only fast path is untouched; the provenance filter is on the
  vector arm only).
- The **no-override, firm-default-local** path must be proven **byte-identical** to today's behavior (a
  regression test is the hard guard, per F054).
- Voyage lands later as a gateway provider config + an `embedding`-family model option + an SBOM/ADR note —
  no new app seam (the `EmbeddingProvider` Door-B path already routes through the gateway).
- A partial re-embed is safe by construction (provenance filter excludes not-yet-migrated vectors); the job
  is resumable. The dev-box OOM risk is mitigated by batching + rerank-off, not eliminated — the re-embed is
  a background job, never inline in an agent run.
- Switching a matter's provider is not free: it re-embeds the whole matter (cost/latency for inference; CPU
  for local). The UI states this before applying.
- **Gate.** Deterministic: resolver (matter override / firm-default inherit / dim pin); retrieval provenance
  filter (mismatch ⇒ FTS, match ⇒ hybrid; FTS fast path byte-identical); migration up→down→up on a throwaway
  pgvector; re-embed idempotence + resumability + provenance stamping; coverage calc; GET/PATCH
  (owner-scoped, cross-user/archived/sandbox → 404, 422 on unknown provider, audit body-free); no-override
  path byte-identical; web vitest on exported pure helpers. Live dev-stack: switch a matter local→gateway
  (with a key) → re-embed → semantic search returns; switch back → re-embed → returns; privileged-matter
  default local + switch warning; coverage reflects a mid-re-embed matter.
- **No new dependency** for v1 (local + gateway reuse the existing stack). Voyage's dep/provider is its own
  slice.

## Resource-aware execution (companion decision — extends ADR-F051/F053)

The same model-memory pressure that motivates the provider choice also crashes a small co-located host
directly. Two live incidents (2026-07-01) on the ~6 GB dev box: (i) an **agent run** fanned out 4 subagents
that each used the in-process local embedder → the Linux OOM-killer killed a **Postgres backend** → whole-app
crash-recovery ("Failed to fetch"); (ii) a **document upload** loaded Docling+EasyOCR+embedder (~2.5 GiB) in
the ingest-worker → same global OOM. Root cause is structural: every service (PG, api, both workers, gateway,
MinIO, Collabora) shares one host's RAM with **no limits and no isolation**, and the workers load big models
on demand. This is a class of failure the token/step/fan-out brakes (ADR-F051/F053) don't cover — those bound
*model cost*, not *process memory*.

**Decision (three layers, cheapest-first):**

1. **Static containment (SHIPPED 2026-07-01, dev only — no code, config only).** Per-container `mem_limit` on
   both workers (ingest 3g, arq 2.5g) so a runaway worker self-OOMs **within its own cgroup** (job/run fails +
   restarts) instead of the kernel killing Postgres; limits sized so a single-runaway (the observed case, one
   worker spiking while the other idles) stays under the host ceiling. Plus `LQ_AI_INGEST_WORKER_CONCURRENCY=1`
   and `FAN_OUT_QUOTA=4` to cut peak concurrency. These are `docker-compose.yml` + `.env` only; reversible;
   documented at the seams they govern.
2. **Self-sizing at boot (planned).** On startup, read the container's **cgroup memory limit** (NOT host RAM —
   inside a container the host figure is misleading) + core count and derive fan-out concurrency, ingest
   concurrency, and whether to load ONNX in-process at all. Requires layer 1's limits to exist (they are the
   only reliable in-container memory signal). Static per deployment, zero runtime cost.
3. **A live memory brake — "R7" (planned, ADR-worthy in its own right).** At the fan-out / ingest chokepoint
   (the existing `guarded_tool_call` / `FanOutQuotaMiddleware` seam), sample the cgroup's current vs limit
   memory; below a headroom threshold, **serialize** (concurrency → 1) or **defer** the work and degrade
   gracefully rather than OOM. Slots into the R4/R5/R6 brake family and the `BudgetEnvelope` abstraction as a
   resource dimension alongside token/step/wall-clock.

**Enterprise note (why this is a dev-box artifact, not a product limit).** A real deployment removes the root
cause rather than tuning it: Postgres is a **managed/dedicated DB** (a worker OOM can never crash it);
ingest and agent workers are **independently-sized, horizontally-scaled pools** (k8s Deployments with
memory requests/limits, autoscaled on CPU/mem/queue depth via HPA/KEDA) so one pod OOMs alone; and heavy
model work moves **off the critical path** — embeddings via the gateway to an inference provider (this ADR's
`gateway`/Voyage door) or a dedicated embedding service, so no worker loads a 2.5 GiB model in-process. In
that world layers 1–3 don't disappear — they become **cost/scaling governors** (fan-out quota → spend;
mem limits → autoscaling triggers) rather than survival hacks, while the per-run budget envelope still governs
behaviour and cost. Layer 3 (R7) may graduate to its own ADR when built; it is captured here because the same
incident and the same `gateway`-embedding lever drive both.

## Decisions (to CONFIRM with maintainer)

1. Granularity — ✅ **per-matter, firm-default-inherited** (practice-area layer backlog).
2. Sequencing — ✅ **plan + ADR now; implement after T4** (retrieval works today via the local alignment fix).
3. Providers v1 — ✅ **local + gateway(OpenAI); Voyage later.**
4. Dimension policy — proposed: **pin 768 for all providers** (OpenAI `dimensions=768`) so the column is
   shared; provenance distinguishes the space. (Alternative: per-provider dim + a second vector column —
   heavier; deferred.)
5. Privileged-matter posture — proposed: **default `local`; warn (not block) on switch to inference.**
   (Alternative: hard-block inference on `privileged` matters — confirm.)
