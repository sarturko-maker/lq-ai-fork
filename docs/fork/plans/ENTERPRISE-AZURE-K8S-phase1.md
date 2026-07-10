# K8S-R — enterprise Azure/AKS deployment: Phase 1 research report

Date: 2026-07-10. Scope: the maintainer's thesis — the fork becomes a **distributable, per-customer enterprise deployment on Azure Kubernetes Service (AKS)** that deploys into the **customer's OWN Azure subscription / landing zone (we host nothing — the point of OSS)**; the VM/compose stack (ADR-F058 Option A, runbook AZ-5) is demo/prototype grade, AKS is the production path; customer #2 must be a **parameterised repeat, not a rewrite**. Foundry = **models only for now** (Anthropic + azure-openai routed through our gateway — the sole egress + sole key-holder). This report evaluates target topology, data plane, model access, identity, networking, secrets/keys, IaC + delivery, migrations/release, observability, a **code-grounded horizontal-scale audit**, and cost — and surfaces the hard decisions for the maintainer. **No code is implemented in this phase.**

Sources: Microsoft Learn / Azure docs fetched 2026-07-10 (URLs at the end) + direct repo inspection at `main` (`23a235b5`). Method: an 11-section research fan-out (one agent per section, Azure-fact web verification + fork-tree code grounding), followed by **adversarial code-verification of every §10 scale-blocker against the actual source** (21 agents total). Every Azure claim carries a cited source or an explicit `UNCONFIRMED` flag; every code claim carries `file:line` evidence. Reuses + generalises ADR-F069 (Key Vault), F070 (restricted egress), F072 (keyless managed identity), F058 (self-host charter), F064 (RBAC), BRAND-1/F068 (white-label).

> **§10 horizontal-scale audit result: 5 CONFIRMED · 1 PARTIAL · 1 REFUTED blockers** (code-verified). All five CONFIRMED blockers are scheduled into Phase 1 of the ladder below — they gate "effortless scale".

## Maintainer rulings (2026-07-10)

The maintainer reviewed this report and decided the headline questions. **These are authoritative and
override the "options" framing in the § Consolidated open decisions section below.**

1. **End-user login (D4) — DECIDED: SSO is OPTIONAL, per customer; our local login ALWAYS remains.** SSO is
   *not* a replacement for local auth — both coexist in the product and each customer chooses. A customer that
   mandates "work-account sign-in only" disables local login by configuration; the local auth substrate is
   never removed. This makes the SSO piece an **optional overlay** at the single `get_current_user` seam, not
   a rebuild of our auth.
2. **Data residency / Claude-in-EU (D7) — REMOVED (not ours to solve).** The customer deploys the models in
   their OWN Azure and picks the region/zone at deploy time; our gateway just points at the endpoint they
   configured. Region + model stay per-customer parameters (already true via the alias→deployment
   indirection). Residency is the customer's deploy-time responsibility — nothing for us to build, and no
   "is Claude available in Europe" dependency to design around.
3. **Azure Firewall ownership (D10) — DECIDED: reuse the customer's.** Default to sitting behind the customer's
   existing hub firewall; stand up our own only if a customer lacks one. The Phase-2 "cost cliff" largely
   disappears for enterprise customers.
4. **Legacy playbook executor (D13 / HS-6) — DECIDED: FIX it.** Playbooks ship in the enterprise product and
   are widely used, so migrate the executor onto the durable arq queue (survives pod eviction) + orphan sweep.
   Do NOT drop it.
5. **Confirmed defaults (no objection):** managed PaaS for the DB/cache (D1), in-cluster MinIO object store
   (D6), Terraform + Azure Verified Modules as the setup tool (D2).

## Verdict table

| # | Section | Bottom-line verdict / recommendation |
|---|---|---|
| §1 | Target topology | **One private AKS cluster per customer**, in the customer's own subscription/VNet — 3 zone-spanning node pools (tainted system, app, dedicated Guaranteed-QoS worker for ONNX/Docling/PyMuPDF, no GPU); 6 app containers → Deployments (arq KEDA-scaled, collabora single-replica), PDB on every Deployment, Cluster Autoscaler now / NAP later. **Gate: fix the §10 in-memory-brake + SSE-single-replica defects before any api/worker replica count exceeds 1.** |
| §2 | Data plane | **Managed-by-default for stateful cores, in-cluster for boundaries.** Postgres+pgvector → Azure DB for PostgreSQL Flexible Server (allowlist `vector` in `azure.extensions`); Redis → Azure Cache; **object storage stays in-cluster MinIO** (Blob has no S3 API, our layer is aioboto3) with managed Blob as an enterprise upgrade; ONNX + PyMuPDF/Collabora stay in-cluster. Ship a CloudNativePG overlay (same `DATABASE_URL`) for air-gapped/ADR-F070. |
| §3 | Foundry / model access | **Keyless via Workload Identity.** Add an SDK-free `WorkloadIdentityTokenProvider` alongside the IMDS one, selected by `AZURE_FEDERATED_TOKEN_FILE`; **append `/.default`** (the F072 bare-audience trap inverts on the v2 endpoint); per-deployment user-assigned MI, role **Cognitive Services OpenAI User**. Keyless Claude is a separate slice; Claude's missing EU data zone is a maintainer legal/product call. |
| §4 | Identity (service + user) | **Two tracks.** Service identity (Workload Identity for gateway/api/both workers) belongs in cut 1 — granting the Foundry role to the gateway pod alone strengthens sole-egress. End-user **Entra SSO + SCIM** is its own ADR'd workstream (verifies at the single `get_current_user` seam): **SSO-first, SCIM fast-follow**, operator kept out of the tenant SCIM group to preserve the F064 fence. **DECIDED: optional per-customer overlay — local login always retained; see § Maintainer rulings.** |
| §5 | Networking | **Fully-private posture = Phase 2 (ADR-F070 on AKS).** Private API server (create-time), Private Endpoints for data plane/KV/ACR/Foundry with public access disabled, `outboundType=UDR` → Azure Firewall deny-by-default (F070 §8.4 allowlist), Cilium default-deny NetworkPolicy so only the gateway reaches model endpoints, AGC + Azure WAF ingress. **Avoid AGIC / ingress-nginx**; retain Caddy in-cluster as the tested WOPI/internal/metrics deny layer. |
| §6 | Secrets & keys | **Key Vault CSI + Workload Identity as the sole secret-injection mechanism**, sourced from the customer's Key Vault, mounted as tmpfs files. Disable the gateway's in-process IMDS KV fetch on AKS (F069 addendum — it grabs the node identity). WI only removes Azure provider keys; gateway key/JWT/Fernet/non-Azure keys/DB+MinIO creds still need CSI. CMK: managed-disk (DES) baseline, etcd KMS + PaaS-CMK as enterprise opt-in. |
| §7 | IaC + delivery | **Terraform (azurerm) + Azure Verified Modules** as primary landing-zone IaC, state in a bootstrap storage account inside the customer's own subscription (we host nothing). Single umbrella Helm chart lifting `docker-compose.prod.yml`'s env contract 1:1; GitOps via managed `microsoft.flux` (Phase 2; pipeline-push Phase 1). **One `customer.values.yaml`** projected into both tfvars and values. Keep the boundary clean so Bicep stays a drop-in. |
| §8 | Migrations & release | **Replace migrate-on-boot with a Helm pre-install/pre-upgrade hook Job** (`alembic upgrade head`, weighted, `backoffLimit 0`) that gates the rollout; set `LQ_AI_SKIP_MIGRATIONS=1` on api + both workers (also kills the boot race). Mirror GHCR → customer ACR **by immutable digest** (`az acr import`), MI-based kubelet pull (F072 lineage), SHA-pinned values; support air-gapped ACR seed. Fix the `image.owner` default mismatch. |
| §9 | Observability | **Ship an OBS slice.** Real gap: call `_maybe_init_otel` from **both** worker `on_startup` hooks (spans hit a no-op tracer today). Chart: worker/collabora Deployments + liveness/startup probes + `prometheus.io/scrape` annotations on api/gateway. Target a **customer-run in-cluster OTel Collector** (not the preview native OTLP), telemetry opt-in (`OTEL_EXPORTER_OTLP_ENDPOINT` unset). Managed Prometheus/Grafana/Container Insights = documented landing-zone prereqs. |
| §10 | Horizontal-scale code audit | **Ship the HS hardening slices before advertising >1 replica of any tier.** CONFIRMED and gating: HS-1 (migrations off boot), HS-2 (gateway per-process config), HS-4 (agent worker `max_jobs` + ONNX limits), HS-6 (playbook durability → arq), HS-7 (collabora single-replica/affinity). **HS-3 REFUTED** — arq crons are already a cluster-wide singleton; preserve the single-shared-Redis + single-queue invariant. **HS-5 PARTIAL** — cost-governance gap (multi-resume ceiling + no aggregate budget), not a scale break. The agent-run happy path (leasing/SSE/HITL/auth) is already multi-replica-clean — do not re-engineer it. |
| §11 | Cost model & phasing | **Phase-1 MVP ~$1,000–1,200/mo infra + a separate usage-based Foundry token line**; RI/Savings Plans cut the ~$640/mo compute majority ~30–40%. **Phase-2 private networking is the cost cliff** — Azure Firewall (~$913/mo) + WAF_v2 (~$323–400/mo) roughly triples the bill, so **parameterise firewall/ingress/Log-Analytics** for customers with a hub firewall. SSO (Phase 3) ~$0 Azure, CMK (Phase 4) +$5–25/mo, multi-region (Phase 5) +80–100%. |

## §1 — Target topology: a dedicated, private AKS cluster per customer

**Verdict.** One **private AKS cluster per customer**, provisioned into the *customer's own* subscription and VNet, is the right production substrate and a clean generalisation of the ADR-F058 self-host charter. The 6 application containers become **Deployments** (not Jobs — the two `arq` workers are long-running queue consumers, `docker-compose.yml:342,445`); the DB/queue/object-store data plane is externalised to managed PaaS by default (see §2). **No GPU is required** — every in-cluster compute cost is CPU/RAM (fastembed bge embedder + cross-encoder reranker ONNX models, Docling, PyMuPDF). The two workers carry the memory-spiky ONNX load and **warrant a dedicated user node pool** with guaranteed-QoS sizing so a model-load spike cannot evict the latency-sensitive `api`/`gateway`/`web` pods. Three node pools (system + app + worker), spread zone-spanning across 3 availability zones, with per-Deployment PodDisruptionBudgets and both pod (HPA/KEDA) and node (Cluster Autoscaler or Node Auto-Provisioning) autoscaling, is the reference shape.

> One cross-cutting caveat, owned by §10 but load-bearing here: multi-replica `api`/`gateway`/`arq-worker` is the whole point of "effortless scale," yet the **R4 token brake and FanOutQuotaMiddleware are in-process today** and cockpit **SSE/HITL streaming assumes one replica**. §1 sizes the cluster *assuming those blockers are fixed*; do not raise `api`/worker replica counts in production until §10's defect list is closed.

### 1.1 Cluster model — private, per-customer, in the customer's subscription

- **Private cluster.** Use **API Server VNet Integration** in *private* mode: the API-server endpoint is projected into a delegated subnet in the customer's VNet, so control-plane↔node traffic stays on the private network with no Private Link tunnel. It is GA in all public-cloud regions except `qatarcentral`, and you can toggle public/private without redeploying — good for a bootstrap-then-lock-down rollout. [MS Learn: API Server VNet Integration]
- **Control plane is zone-resilient by default** and free; distributing *nodes* across zones also incurs no extra AKS charge (you pay only for the VMs). [MS Learn: AKS availability zones]
- **One cluster per customer** (not shared multi-tenant) is the correct tenancy: it matches "we host nothing," gives each customer their own blast radius, RBAC boundary, egress firewall (ADR-F070) and CMK scope, and makes customer #2 a *parameterised repeat* of the same Helm+IaC bundle rather than a new tenancy design. This is a hard-to-reverse call → **draft an ADR (tenancy-on-AKS = cluster-per-customer)**.

### 1.2 Node pools — 3 pools, zone-spanning across 3 AZs

Microsoft's guidance is to **isolate critical system pods from application pods** with a dedicated system node pool tainted `CriticalAddonsOnly=true:NoSchedule`; production system pools should have **≥3 nodes** for fault tolerance/AZ spread, and user pools ≥2. [MS Learn: Use system node pools]

| Pool | Mode | Runs | Why separate |
|---|---|---|---|
| **system** | System, `CriticalAddonsOnly` taint | CoreDNS, metrics-server, CSI drivers, AKS add-ons | Protects kube-system from a rogue/OOMing app pod [MS Learn: system pools] |
| **app** | User | `api`, `gateway`, `web`, `collabora`, `slack/teams-bridge` | Latency-sensitive, modest RAM; scale on CPU/RPS |
| **worker** | User, label+taint `workload=inference` | `arq-worker`, `ingest-worker` | ONNX/Docling/PyMuPDF **memory spikes**; guaranteed QoS + KEDA queue-scaling; isolates the OOM class the dev box hit |

**Does the embedder/reranker warrant a dedicated pool? Yes — via the *workers*, not per-model.** The ONNX models are loaded *in-process inside the two workers*, not as separate services: `api/Dockerfile:25,31` bake `BAAI/bge-base-en-v1.5` (embedder) and `Xenova/ms-marco-MiniLM-L-6-v2` (cross-encoder) into the image, and `docker-compose.yml:406-413` documents that on a run "the in-process ONNX models load in THIS [arq] worker." The dev box gave these workers `mem_limit: 2500m` (arq) and `3g` (ingest) precisely because "an unbounded spike made the kernel OOM-killer kill a Postgres backend" (`docker-compose.yml:367-374, 276-282`). On K8s that discipline becomes **requests==limits (Guaranteed QoS)** on a dedicated pool so a spike self-contains instead of evicting a co-tenant. A pool suffices; no *per-model* pool and **no GPU pool** (fastembed runs the ONNX CPU runtime).

**Zone spread.** Deploy each pool **zone-spanning across zones 1/2/3**; AKS balances node count across zones automatically. Note a VM SKU is only accepted if it supports the requested zones in that region. [MS Learn: AKS availability zones]

### 1.3 Mapping the compose services → K8s workloads

Six application services + three data-plane services + two optional bridges (`docker-compose.yml`). "Ollama" (Mode-2 local inference) is **out of scope** — Foundry is the model source.

| Compose service | K8s workload | Placement / notes |
|---|---|---|
| `api` (FastAPI :8000) | **Deployment** + HPA; ClusterIP; ingress target | Stateless. **Migration must move off boot** — `entrypoint.sh:23-26` runs `alembic upgrade head` before uvicorn; on K8s make it a Helm pre-upgrade **Job/init container** and set `LQ_AI_SKIP_MIGRATIONS=1` on the Deployment (the escape hatch already exists, `entrypoint.sh:21`; alembic's advisory lock, `entrypoint.sh:12-15`, coordinates racers). Detail → §8. |
| `gateway` (:8001, **sole egress + key-holder**) | **Deployment** + HPA; ClusterIP | The only pod allowed egress to Foundry; enforce with a NetworkPolicy + egress firewall (§5). Keys via Key Vault CSI / Workload Identity (§3/§6), never in etcd where avoidable. |
| `arq-worker` (agent runs, ONNX in-process, fan-out) | **Deployment** on **worker pool**; **KEDA**-scaled on the `arq:m3a6` Redis queue | Guaranteed QoS (~3–4 Gi req==limit). Fan-out/token brakes are in-process → §10 before scaling replicas. |
| `ingest-worker` (Docling+PyMuPDF+EasyOCR+embedder) | **Deployment** on **worker pool**; **KEDA**-scaled on ingest queue | Needs a **model-cache volume**: `docker-compose.yml:337-339` mounts HF + EasyOCR caches so ~700 MB models download once. On K8s use a PVC (or an init-container warm) — the embedder/reranker are already baked (`Dockerfile:25,31`) but Docling/EasyOCR models are not. **PyMuPDF AGPL stays server-side-only here** (obligation; §2). |
| `web` (SvelteKit SPA on nginx :8080) | **Deployment** + HPA; ClusterIP; ingress target | Stateless static bundle. |
| `collabora` (WOPI editor, MPL, **no host port**) | **Deployment**, ClusterIP **only** (internal) | `docker-compose.yml:498-501`: no host port, reachable only by `web`'s same-origin proxy → internal Service, never an ingress. **WOPI edit sessions are sticky** (a doc is held in a specific coolwsd process) → needs session affinity if >1 replica; `home_mode` caps a replica to ~20 connections/10 docs (`docker-compose.yml:533-544`). Keep single-replica per customer initially; scale-out is an open decision. |
| `postgres` (pgvector) | **Managed** (Azure DB for PostgreSQL Flexible Server) *or* in-cluster StatefulSet (CloudNativePG) | Decision + pgvector parity → §2. |
| `redis` (arq queue + cache) | **Managed** (Azure Cache for Redis) *or* in-cluster StatefulSet | → §2. |
| `minio` (S3-compatible store) | **Azure Blob** (S3 path) *or* in-cluster StatefulSet | → §2. |
| `slack-bridge` / `teams-bridge` | Optional **Deployments** (profile-gated) | Only if the customer enables them. |

### 1.4 Availability, disruption budgets, autoscaling

- **PodDisruptionBudgets are mandatory**, one per Deployment (`minAvailable: 1` for singletons, `maxUnavailable: 1` for scaled sets). They protect availability during the node **drain** step of AKS upgrades/scale-down; Microsoft flags a *misconfigured PDB as the #1 cause of stuck upgrades*, and AKS now offers optional **automatic PDB management** (preview) that temporarily surges replicas so a blocking PDB doesn't stall a drain. Pair with `maxSurge: 33%` on node-pool upgrades (MS production recommendation). [MS Learn: automatic PDB management; upgrade/max-surge]
- **Pod autoscaling:** HPA (CPU/memory/custom) for `api`/`gateway`/`web`; **KEDA** (GA add-on, event-driven) for the two workers, scaling on **Redis queue depth** — the natural signal for agent-run and ingest backlog. [MS Learn: scaling options / KEDA]
- **Node autoscaling:** **Cluster Autoscaler** (per-pool min/max) is the conservative default; **Node Auto-Provisioning (NAP)** — AKS's managed **Karpenter**, **GA since ~July 2025** — picks right-sized VMs for pending pods and consolidates, and is the better fit for the bursty worker pool. Recommend CA for Phase-1 (predictable, simple to reason about in a customer sub) with NAP as a Phase-2 optimisation. [MS Learn / AKS blog: NAP-Karpenter GA] **UNCONFIRMED:** exact NAP GA date and its regional coverage in each customer's target region — verify against the region before committing.

### 1.5 Recommended node SKUs + reference cluster shape (Phase-1, single region)

D-series general-purpose ratio is **4 GiB RAM per vCPU**; the `Ddsv5` family (Intel Emerald/Ice Lake) supports **ephemeral OS disks** and local temp SSD — use ephemeral OS disks (free, faster, no managed-disk IOPS contention). Verified sizes: `D4ds_v5` = 4 vCPU/16 GiB, `D8ds_v5` = 8 vCPU/32 GiB, `D16ds_v5` = 16 vCPU/64 GiB. [MS Learn: Ddsv5 series]

| Pool | SKU | Nodes (×3 AZ) | Rationale |
|---|---|---|---|
| **system** | `Standard_D4ds_v5` (or `D8ds_v5`) | 3 | MS min for prod; ephemeral OS disk; `CriticalAddonsOnly` taint |
| **app** | `Standard_D4ds_v5` | 2–3 (CA 2→6) | api/gateway/web/collabora/bridges; HPA-driven |
| **worker** | `Standard_D8ds_v5` | 2–3 (KEDA/CA 1→6) | 32 GiB fits several ~3–4 Gi Guaranteed worker pods with headroom for the ONNX spike; the dev box's 2.5 g/3 g limits are the sizing signal (`docker-compose.yml:373,282`) |

For an AMD-cost-optimised variant, `Dadsv5` is the equivalent EPYC family (same vCPU/RAM ratio, ephemeral-OS-disk-capable) — an IaC `values` knob, not a redesign. A very small customer can collapse **app+worker into one pool** (`D8ds_v5`) and rely on the worker taint being dropped; a large one splits further — this is the parameterisation surface (§7), not a rewrite. **UNCONFIRMED:** per-customer region must actually offer `Ddsv5`/`Dadsv5` in ≥3 zones — verify at landing-zone time (SKU×zone availability is region-specific).

### 1.6 Region pinning (topology-relevant)

The cluster region is dictated by two constraints that must agree: (a) the customer's data-residency requirement, and (b) **Claude-on-Foundry's region restriction — East US2 or Sweden Central** per the existing Foundry Phase-1 finding (`docs/fork/plans/AZURE-FOUNDRY-phase1.md:53-54`). For an EU/GDPR legal customer, **Sweden Central** satisfies both the AKS AZ requirement and Claude availability. Model-region detail is §3's job; §1 only notes the cluster and the Foundry deployment should co-locate.

### Recommendation (this section)

Ship **one private AKS cluster per customer** (API Server VNet Integration, private mode) with **three zone-spanning node pools** — a tainted 3-node system pool, an app pool, and a **dedicated worker pool (Guaranteed QoS) for the two ONNX/Docling workers** — no GPU. Map the 6 app services to **Deployments** (workers KEDA-scaled on Redis queue depth; collabora internal ClusterIP, single-replica for now), externalise the data plane to managed PaaS (§2), enforce **PDBs on every Deployment**, and use **Cluster Autoscaler now / NAP later**. Reference: system `D4/D8ds_v5`×3, app `D4ds_v5`×2–3, worker `D8ds_v5`×2–3, ephemeral OS disks, Sweden Central (EU) or East US2. **Blocking dependency:** the §10 in-memory-brake/SSE-single-replica defects must close before `api`/worker replicas exceed 1 in production.

## §2 — Data plane: managed-first vs in-cluster

**Scope.** The four data-plane services in the compose stack — `postgres` (pgvector), `redis`, `minio`, plus the in-process ONNX models the workers load — mapped to the customer's own Azure subscription on AKS. Verdict per service, with the hard constraint that our retriever, langgraph checkpointer, and native Store/CompositeBackend all sit on the *same* Postgres and must port byte-clean.

### §2.0 Verdict table

| Data-plane concern | Recommendation | Confidence |
|---|---|---|
| **Postgres + pgvector** | **Managed by default: Azure Database for PostgreSQL Flexible Server**, zone-redundant HA. In-cluster CloudNativePG supported as the air-gapped / cost-floor alternative. | High — pgvector, ivfflat/HNSW, citext, pgcrypto all confirmed on Flex Server |
| **Redis (arq queue + cache)** | **Managed by default: Azure Cache for Redis** (Premium+ for persistence). In-cluster (Bitnami/`redis:7` StatefulSet) supported. | High |
| **Object storage (MinIO → ?)** | **In-cluster MinIO stays the default** (zero code change — our client speaks S3). Managed **Azure Blob is a code slice**, not a config swap: Blob has **no native S3 API**. | High on the constraint; the *path to Blob* is an open decision |
| **ONNX embedder + reranker** | **In-cluster, always** — they are in-process Python deps of the workers, not a service. | Certain (code-grounded) |
| **PyMuPDF / Collabora server-side boundary** | **In-cluster, always** — AGPL/MPL server-side-only obligation. | Certain (NOTICES.md obligation) |

**Headline:** managed-by-default is clean and low-risk for **Postgres** and **Redis**. It is *not* clean for **object storage** — Azure Blob does not speak S3, and our entire storage layer is `aioboto3`. Object storage is the one place where "managed" costs a code slice; in-cluster MinIO is the byte-clean default.

---

### §2.1 Postgres + pgvector — MANAGED BY DEFAULT (Flexible Server)

**Why this is the load-bearing decision.** Three independent subsystems share one Postgres:

- The KB + matter **retriever** runs raw pgvector cosine SQL (`ORDER BY dc.embedding_local <=> CAST(:q_emb AS vector)`), fused with Postgres FTS (`retrieval.py:444-448`, `:202-211`).
- The langgraph **checkpointer** (`AsyncPostgresSaver`) and native **Store/CompositeBackend** (`AsyncPostgresStore`) each open their *own* psycopg pool against the same DB and run the library's `setup()` to create and version their own tables (`store`, `store_migrations`, and — since Slice C2 — the pgvector `store_vectors` + `vector_migrations`) — deliberately **not** alembic-managed (`agents/store.py:9-29`, `agents/checkpointer.py:69-93`).
- Both library pools **must be `autocommit`** because `setup()` runs `CREATE INDEX CONCURRENTLY`, which Postgres forbids inside a transaction (`agents/store.py:118-121`).

So the managed instance must support: (a) the `vector` extension with ivfflat/HNSW access methods, (b) `CREATE INDEX CONCURRENTLY` from an autocommit connection (standard Postgres — fine on Flex Server), and (c) the `citext` + `pgcrypto` extensions our base schema installs (`0001_initial.py:44-45`, `0005:62`).

**Confirmed on Azure Database for PostgreSQL Flexible Server:**

- The **`vector` extension** (pgvector) is supported and provides *both* `ivfflat` and `hnsw` access methods. It must be added to the `azure.extensions` server-parameter allowlist, then `CREATE EXTENSION vector;` per database — note the extension name is **`vector`**, not `pgvector`, which is exactly what our migration already uses (`CREATE EXTENSION IF NOT EXISTS vector`, `0005:62`) ([Learn: pgvector on Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector), [Learn: allow extensions](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions)).
- **`citext` and `pgcrypto`** are both on the supported/allowlistable extension list ([Learn: extensions by name](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions)). Both must be added to `azure.extensions` — this is a **provisioning parameter, not a code change**.
- **ANN index dimension ceiling is 2000** for both ivfflat and hnsw. Our columns are `vector(1536)` (legacy `embedding`) and `vector(768)` (`embedding_local`, the live retriever column) — **both under the ceiling** ([Learn: pgvector](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector)).
- **HA:** zone-redundant HA provisions a synchronous warm standby in another AZ with **zero-data-loss failover in 60–120s** ([Learn: HA concepts](https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability)).
- **Backup / PITR:** automated backups with **7-day default retention, extensible to 35 days**, PITR to latest or custom restore point; backups land in **zone-redundant storage (ZRS)** in AZ regions ([Learn: backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore)).

**Our index type ports byte-clean.** Our migrations use **`ivfflat` with `vector_cosine_ops` (lists=100)**, not HNSW (`0005:177-186`, `0078:38-49`). ivfflat is supported on Flex Server, so the schema applies unchanged. HNSW is *available* if we ever want it, but see the caveat below.

**Two Azure-specific watch-items (flag, don't block):**

1. **pgvector 0.8.0 + HNSW CPU-instruction crash.** Microsoft Q&A reports pgvector 0.8.0 built with CPU optimizations that crash the server with HNSW indexes on certain Azure hardware (e.g. France Central, older CPUs) ([MS Q&A: pgvector 0.8.0 HNSW](https://learn.microsoft.com/en-us/answers/questions/5530146/pgvector-0-8-0-hnsw-on-azure-postgresql-flexible-s)). We are **less exposed because we use ivfflat, not HNSW** — but the exact pgvector version available depends on the PG major version + region, so pin/verify at deploy.
2. **DiskANN is the Azure-native scale path.** `pg_diskann` is GA on Flex Server, depends on the `vector` extension (allowlist + `CREATE EXTENSION pg_diskann CASCADE`), supports up to **16,000 dims with product quantization**, and Microsoft positions it as surpassing HNSW/ivfflat on latency+recall at scale ([Learn: DiskANN](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-use-pgdiskann)). Because DiskANN is *just another index access method on the same `vector` column*, adopting it later is an **additive index swap** (`USING diskann (embedding_local vector_cosine_ops)`) with **no schema change** — a good future optimization, out of scope for the byte-clean first port.

**In-cluster alternative (supported, not default): CloudNativePG.** Microsoft's own AKS guidance now anchors the recommended in-cluster Postgres pattern on the **CloudNativePG** operator, with PITR via the barman-cloud plugin streaming WAL + base backups to object storage (incl. Azure Blob) ([Learn: PostgreSQL HA on AKS](https://learn.microsoft.com/en-us/azure/aks/postgresql-ha-overview), [AKS blog: CloudNativePG](https://blog.aks.azure.com/2025/11/10/announce-pgsql-howto)). This is the right choice for **air-gapped / restricted-egress (ADR-F070)** customers who won't or can't use a PaaS DB, or who want a cost floor. The trade: the customer's team now owns Postgres patching, HA, and backup verification instead of Azure.

**Recommendation.** **Flexible Server, zone-redundant, by default.** It removes DB ops from the customer's plate (the enterprise-buyer expectation) and every extension we need is confirmed. Ship a **CloudNativePG overlay** as the supported in-cluster option, wired to the same `DATABASE_URL` contract so the retriever/checkpointer/Store code never knows the difference. **Regardless of choice, provisioning must allowlist `vector`, `citext`, `pgcrypto` in `azure.extensions`** (Flex Server) or install them in the operator's image (CloudNativePG) — this is a deploy-time gate, not code.

---

### §2.2 Redis (arq queue + cache) — MANAGED BY DEFAULT (Azure Cache for Redis)

Redis is the arq job queue (agent-run execution) plus cache (`REDIS_URL`, compose `redis:7-alpine` with `--appendonly yes`). arq needs a standard Redis endpoint — no RediSearch/modules — so any of the Azure tiers works.

**Confirmed:**
- **AOF persistence is Premium-tier-only** and is **not supported with multiple replicas** on Premium; Enterprise/Enterprise-Flash persist to a managed disk. Persistence is explicitly **not a PITR/backup feature** ([Learn: Redis data persistence](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-how-to-premium-persistence)).

**Implication for us:** the queue is **transient work-in-flight**, not a system of record — a lost queue means in-flight agent runs need re-driving, not data loss (durable run state lives in Postgres via the checkpointer + `agent_runs`). So persistence is a *nice-to-have* for Redis, not a correctness requirement. **Standard/Basic tier is functionally sufficient**; Premium buys persistence + VNet injection + zone redundancy for customers who want the queue to survive a node loss.

**Recommendation.** **Azure Cache for Redis by default** (Premium when the customer wants persistence + private-link/VNet, which the restricted-egress ADR-F070 profile will want). **In-cluster `redis:7` StatefulSet supported** for air-gapped/cost-floor, same `REDIS_URL` contract. This is a low-stakes swap either way.

---

### §2.3 Object storage (MinIO) — IN-CLUSTER MINIO IS THE DEFAULT; managed Blob is a code slice

**This is the one data-plane service where "managed by default" does not hold**, and it's the most important finding in this section.

**Code reality (grounded).** Every byte in/out of object storage goes through `api/app/storage.py`, which uses **`aioboto3`** (S3 SDK) with **path-style addressing** against a configurable `endpoint_url` (`storage.py:42-43, 98-103`). Config is fully endpoint-driven: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION` (`config.py:56-63`; compose defaults `S3_ENDPOINT_URL=http://minio:9000`). The surface used is **pure S3**: `head_bucket`, `create_bucket` (with region `LocationConstraint`), **multipart upload** (`create_multipart_upload`/`upload_part`/`complete_multipart_upload`), `get_object` streaming, `copy_object` (server-side, used by the editor save-back snapshot, ADR-F047), `put_object`, `delete_object`, and **presigned GET URLs** (`generate_presigned_url`, used by the D6 GDPR export).

**Azure fact:** **Azure Blob Storage does not natively expose an S3-compatible API.** boto3/aioboto3 cannot talk to Blob out-of-the-box; reaching Blob from S3 code requires either an **S3Proxy** translation layer or the **Azure Blob SDK** ([MS Q&A: S3 API over Blob](https://learn.microsoft.com/en-us/answers/questions/1183760/s3-api-support-over-azure-blob-storage)).

So there are three ways to run object storage on AKS, in increasing code cost:

| Option | Code change | Notes |
|---|---|---|
| **A. In-cluster MinIO** (StatefulSet on a PVC) | **Zero** — our S3 client is unchanged | Byte-clean port. Backup = PVC snapshots or `mc mirror` to Blob. **MinIO is AGPLv3** → server-side-only, self-hosted, not redistributed — same posture as PyMuPDF/Collabora (already in the shipped stack). Customer owns durability. |
| **B. S3Proxy sidecar → Azure Blob** | **Zero app code**; add a sidecar + config | S3Proxy (Apache-2.0) exposes S3, backs onto Blob via `azureblob-sdk`, supports key or managed-identity auth. Gets durable managed Blob **without** touching `storage.py`. Cost: an extra hop + operating the proxy; verify multipart + presigned-URL fidelity through it. |
| **C. Native Azure Blob backend** | **Real slice** — a storage abstraction | Put the ~10-method `storage.py` surface behind a `Protocol` and add a Blob implementation on the Azure SDK. Multipart → Block Blob staging; **presigned GET → Blob SAS token** (different mechanism, but expresses the same "time-bounded URL, no proxying" intent D6 needs); `copy_object` → Blob server-side copy. Feasible because the surface is small and lives in **one module**, but it is genuine code + tests, and presigned-URL/SAS semantics need care. |

**Recommendation.** **Default to in-cluster MinIO (Option A)** — it is the byte-clean port, keeps the first customer deployment a *parameterised repeat* with zero storage-layer risk, and its AGPL posture is identical to boundaries we already honour. **Offer managed Azure Blob as an enterprise upgrade**, and choose the road deliberately: **S3Proxy (B)** if we want managed Blob with no app-code change and can accept a sidecar; **native Blob backend (C)** if we want a first-class managed path and are willing to fund the storage-abstraction slice (it also cleanly future-proofs presigned URLs → SAS and pairs with the AZ-6 managed-identity posture). This is the top **open decision** for the maintainer.

---

### §2.4 What stays in-cluster REGARDLESS

- **The ONNX models.** The arq-worker loads an in-process fastembed embedder (`BAAI/bge-base-en-v1.5`, 768-dim) *and* a cross-encoder reranker; the ingest-worker loads the embedder (`embedding_provider.py:7-17, 48-49`; compose `EMBEDDING_PROVIDER=local`, `RERANK_ENABLED=true`). These are **Python in-process dependencies of the worker pods, not a data-plane service** — they have no managed-Azure equivalent and stay in the worker container image regardless. (They also drive pod sizing: memory-heavy, and known to OOM-spike — a §10/sizing concern, noted here only for completeness. "Door B" can route embeddings through the gateway instead, but the reranker has no gateway door today.)
- **The PyMuPDF AGPL and Collabora MPL server-side boundary.** PyMuPDF (ingest-worker) and Collabora (WOPI editor, no host port, internal-only) are **server-side-only obligations** (NOTICES.md), never redistributed to clients — they stay in-cluster workloads by license design, independent of any managed-vs-self-hosted data-plane choice.

---

### §2.5 Migrate-on-boot — a data-plane coupling worth flagging for the K8s slice

The `api` image entrypoint runs **`alembic upgrade head` before serving**, coordinated across replicas by a **Postgres advisory lock**, with an **`LQ_AI_SKIP_MIGRATIONS=1`** escape hatch explicitly documented for *"an external job, a sidecar, Kubernetes pre-deploy hook"* (`api/entrypoint.sh`). On AKS the clean pattern is a **Helm pre-install/pre-upgrade Job (or initContainer)** that runs migrations once against the managed/​in-cluster Postgres, with the api Deployment setting `LQ_AI_SKIP_MIGRATIONS=1`. The hook already exists — this is a wiring choice for the K8s workload agent, surfaced here because it is a direct api↔Postgres coupling. (The langgraph `store`/`checkpointer` `setup()` runs are *separate* and self-managed at pod startup — they are idempotent and safe under replicas, but note they need an autocommit connection to the same DB.)

## §3 — Foundry / model access on AKS

**Scope.** How the fork's gateway reaches its two model families — `azure_openai` (GPT + Mistral-Large-3 over the AOAI deployments route) and `azure-claude` (Anthropic on Foundry) — from an AKS pod, **keyless**, using **AKS Workload Identity** instead of the VM IMDS path shipped in AZ-6/ADR-F072. Foundry stays *models only*: every call still egresses through our gateway, which remains the sole key/credential holder.

### Verdict

| Question | Verdict |
|---|---|
| Keyless model auth on AKS is possible without a static key | **YES — GA.** AKS Workload Identity (Microsoft Entra Workload ID) is GA and is the recommended, Pod-Identity-superseding path. |
| The AZ-6/ADR-F072 IMDS code works unchanged on an AKS pod | **NO.** Workload Identity does **not** use IMDS. It exchanges a projected Kubernetes service-account JWT at the Entra **v2 token endpoint**. The current `azure_identity.py` hits `169.254.169.254` (IMDS), which is not the WI path. |
| The ADR-F072 scope trap ("BARE audience, NO `/.default`") carries over | **NO — it INVERTS.** WI uses the Entra v2 endpoint, whose `scope` **requires** the `/.default` suffix (`https://cognitiveservices.azure.com/.default`). The bare-resource form is IMDS-only. This is the single most important correction for the AKS port. |
| Claude-on-Foundry can go keyless with the same work | **NOT TODAY.** The `anthropic` adapter has no token-provider seam at all (it only sends `x-api-key`); keyless Claude needs adapter work *plus* the WI provider. |
| EU data residency for our model dependencies | **PARTIAL / a real GDPR flag.** `azure_openai` (GPT/embeddings) has genuine EU regions/data zones. **Claude on Foundry has no EU data zone** — East US2 / Sweden Central only, inference on Anthropic-hosted infra; Anthropic lists EU "Coming 2026". |

**Recommendation: build a second, WI-native token provider behind the seam AZ-6 already created — SDK-free, `/.default` scope — and treat Claude EU-residency as a maintainer decision, not an engineering default.** Detail below.

---

### 3.1 How Workload Identity actually mints a token (and why IMDS ≠ WI)

On AKS the pod does **not** call IMDS. The flow is OIDC federation:

1. The cluster is created with `--enable-oidc-issuer --enable-workload-identity`; it exposes an OIDC issuer URL. On **AKS Automatic** both are preconfigured. [ms-aks-wi-deploy]
2. A **user-assigned managed identity** (not the VM/cluster system-assigned identity) is federated to a specific Kubernetes ServiceAccount via `az identity federated-credential create --issuer <OIDC> --subject system:serviceaccount:<ns>:<sa> --audience api://AzureADTokenExchange`. [ms-aks-wi-deploy]
3. The ServiceAccount is annotated `azure.workload.identity/client-id: <uami-client-id>`; the pod is labelled `azure.workload.identity/use: "true"`. The mutating webhook then projects a signed SA token to a volume and injects env vars: **`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_FEDERATED_TOKEN_FILE`, `AZURE_AUTHORITY_HOST`**. [ms-aks-wi-overview]
4. The app reads the projected JWT from `AZURE_FEDERATED_TOKEN_FILE` and POSTs a **client-credentials-with-federated-credential** exchange to `${AZURE_AUTHORITY_HOST}${AZURE_TENANT_ID}/oauth2/v2.0/token`:
   - `grant_type=client_credentials`
   - `client_id=<AZURE_CLIENT_ID>`
   - `scope=https://cognitiveservices.azure.com/.default`  ← **/.default REQUIRED**
   - `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer`
   - `client_assertion=<contents of the projected token file>` [ms-v2-clientcreds]
5. Entra validates the SA JWT against the OIDC issuer's public keys and returns a ~1 h bearer token, which the gateway sends as `Authorization: Bearer <token>` — exactly the header AZ-6 already produces.

Microsoft states the scope rule explicitly: *"pass scopes using the Microsoft Entra ID v2 format `<resource>/.default` … A raw resource URI … can fail because workload identity uses the Microsoft Entra v2 token endpoint rather than the IMDS `resource` flow used by managed identity."* [ms-aks-wi-overview] This is the inversion of the ADR-F072 trap.

**RBAC is unchanged:** the user-assigned identity is granted **Cognitive Services OpenAI User** on the Foundry/AOAI resource (same role AZ-6 documents for the VM identity). [ise-aoai-wi]

### 3.2 What this means for the gateway code

The good news: **AZ-6 built the right seam.** `AzureOpenAIAdapter` already accepts an injected `TokenProvider` and, when present, sends `Authorization: Bearer <token>` with no `api-key` header (`_auth_headers_async`). The auth mechanism is fully decoupled from the body/tool-call translation, so tool-calling and streaming are untouched by a provider swap. The WI work is confined to *how the token is minted*, not to the adapter contract.

Three implementation options, in preference order:

- **Option B — native WI token provider (recommended).** Add a `WorkloadIdentityTokenProvider` alongside the IMDS one in `app/azure_identity.py`: read `AZURE_FEDERATED_TOKEN_FILE`/`AZURE_CLIENT_ID`/`AZURE_TENANT_ID`/`AZURE_AUTHORITY_HOST`, POST the federated client-assertion exchange, cache on `expires_in`. It is a single `urllib` POST — **stays SDK-free**, honouring the same ADR-F072 rationale that rejected `azure-identity`. Select it by env presence (`AZURE_FEDERATED_TOKEN_FILE` set ⇒ WI; else the existing IMDS path; else api-key). Scope defaults to `https://cognitiveservices.azure.com/.default` and reuses the existing `AZURE_OPENAI_IDENTITY_RESOURCE` override (append `/.default`).
- **Option A — proxy/migration sidecar (fastest, interim only).** Annotate the pod `azure.workload.identity/inject-proxy-sidecar: "true"`; the sidecar intercepts IMDS calls and performs the federated exchange, so the **current IMDS code runs unchanged**. Microsoft explicitly says the migration sidecar *"isn't intended to be a long-term solution."* [ms-aks-wi-overview] Useful for a first cluster bring-up; not the shipping design.
- **Option C — `azure-identity` SDK (`WorkloadIdentityCredential`).** Microsoft's documented path, but a new runtime dependency / SBOM surface — the same trade-off ADR-F072 already declined. Reject for consistency.

**Claude keyless is a separate, larger slice.** `anthropic.py::_auth_headers` only ever returns `x-api-key` + `anthropic-version` — there is no token-provider parameter to inject into. Making Claude-on-Foundry keyless needs (a) a token-provider seam added to the Anthropic adapter and (b) confirmation of the Entra audience for the `…/anthropic` route (AZ-6/ADR-F072 deliberately scoped MI to `azure_openai` only). Until then, Claude on AKS still needs an API key (sourced via ADR-F069 Key Vault → CSI Secrets Store, not baked into an image).

### 3.3 Data residency — the load-bearing legal flag

For an in-house EU legal team this is the sharpest constraint:

- **GPT + embeddings (`azure_openai`):** available Global-Standard in ~30 regions plus EU Data Zones — genuine EU residency is achievable; pin the Foundry deployment to the customer's region/geo. [az-foundry-region] (region matrix carried from AZ-R)
- **Claude on Foundry:** Global Standard in **East US2 or Sweden Central** only; `claude-opus-4-8` (Hosted on Azure) adds Data Zone Standard (US). **There is no EU data zone**, and even Sweden-Central selection routes inference to Anthropic-hosted infrastructure rather than staying inside Azure EU boundaries; Anthropic marks Foundry EU "Coming 2026". [ms-claude-foundry][infoq-claude-eu] For a customer with strict GDPR residency, depending on Claude as the agent model is currently a **documented gap**, not something the deployment can quietly satisfy. Options to surface to the maintainer: (i) run agents on GPT-class models in an EU region and reserve Claude for non-residency-bound work; (ii) accept Sweden-Central with a DPA covering Anthropic processing; (iii) Claude via another cloud is out of the "Foundry-only" scope.

Architecturally: because model choice is per-practice-area config routed through gateway aliases, the deployment must let **each customer pin region + model family independently** — the parameterisation must expose region and the Claude-vs-GPT agent-model choice as first-class knobs.

### 3.4 Content filtering / Responsible-AI as a customer-tunable

Azure applies a default guardrail (`Microsoft.DefaultV2`) that filters four harm categories at **medium** severity for prompts and completions; the Microsoft defaults themselves cannot be edited or deleted, **but** customers can create **custom RAI content-filter policies and assign them per deployment** (tighten, or loosen within approval limits), and these are expressible as-code (Terraform/Bicep). [ms-content-filters] The AKS parameterisation should therefore treat the RAI policy assignment as a **per-customer, per-deployment input** (some legal customers will need stricter filters; some will need a modified-content-management approval to reduce false positives on legal text). This is Azure-side config, not gateway code, but it belongs in the per-customer deployment manifest.

### 3.5 Leave-room-for notes (not in scope now)

- **PTUs / provisioned throughput and fine-tunes:** both are deployment-level Foundry constructs the gateway already addresses by deployment name — a PTU deployment is just another alias target. Keep the alias→deployment indirection (already present) so a customer can point an alias at a PTU deployment later with zero gateway change.
- **20 federated-credential-per-identity limit** [ms-aks-wi-overview] and the ~few-second FIC propagation delay are operational footnotes for the deployment automation, not blockers.

## §4 — Identity: service + end-user

Enterprise identity on AKS is two problems of very different size, and the report must not blur them:

| Problem | What it is | Size | Verdict |
|---|---|---|---|
| **Service identity** | How each pod authenticates to Key Vault, Postgres, Blob, and Foundry — keyless, no static secrets | Small: the AKS generalisation of ADR-F069/F072, one bounded gateway code delta | **In the first enterprise cut** |
| **End-user identity** | How a lawyer signs in: Entra ID SSO (OIDC/SAML) + SCIM provisioning replacing our local login + user-lifecycle | Large: its own workstream + ADR; touches the whole auth substrate's assumptions | **Flag as a separate sizeable workstream; SSO-first, SCIM fast-follow — maintainer decision below** |

---

### 4.1 Service identity — Workload Identity for pods (generalising ADR-F069/F072)

The target: every pod that talks to an Azure backing service mints a short-lived Entra token from its **federated Kubernetes service account** — no static keys anywhere. This is exactly the posture ADR-F072 (AZ-6) and ADR-F069 (KV-1) already chose on the VM, generalised from *one VM managed identity via IMDS* to *per-pod federated identities via the AKS OIDC issuer*.

**All four backing services accept Entra / Workload-Identity auth (confirmed):**

| Compose service → AKS workload | Azure backing service | Entra auth? | Least-priv built-in role |
|---|---|---|---|
| gateway (sole egress) | Azure AI Foundry / Azure OpenAI | ✅ (already built in F072) | **Cognitive Services OpenAI User** |
| gateway | Azure Key Vault (provider keys, if KV path kept) | ✅ | **Key Vault Secrets User** |
| api, arq-worker, ingest-worker | Azure DB for PostgreSQL Flexible Server | ✅ Entra auth GA — token passed in the password field, 5–60 min validity ([Learn: Entra concepts](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-concepts), [connect with MI](https://learn.microsoft.com/en-us/azure/postgresql/security/security-connect-with-managed-identity)) | Entra DB role (`azure_pg_admin` / granted role) |
| api, arq-worker, ingest-worker | Azure Blob (replacing MinIO for object store) | ✅ ([Learn: authorize blob with Entra](https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory)) | **Storage Blob Data Contributor** |

AKS Workload Identity is **GA**: enable `--enable-oidc-issuer` + `--enable-workload-identity`; a pod with an annotated ServiceAccount receives a projected SA token and exchanges it for an Entra access token via OIDC federation; max 20 federated credentials per managed identity ([Learn: AKS workload identity overview](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview)). Both Blob and Key Vault authorize via Azure RBAC over the Entra principal ([Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide)).

**This preserves the fork's hard constraints.** Only the **gateway** pod is granted the Foundry role, so the gateway stays the sole egress and sole key-holder — Workload Identity actually *strengthens* this: the api/worker pods have no path to Foundry at all, and no provider key exists to leak. The ADR-F072 honesty caveat ("trust boundary is the HOST, not the process — any process on the VM can mint the same IMDS token") is **materially improved** under Workload Identity: the token is scoped to the gateway's *federated ServiceAccount*, not shared by every process on a shared host.

#### The one real code delta (do not under-scope this)

ADR-F069 and ADR-F072 both mint their tokens by calling the **IMDS endpoint `http://169.254.169.254/metadata/identity/oauth2/token`** directly (`gateway/app/keyvault.py:107-108`, `gateway/app/azure_identity.py:100-101`). **AKS pods do not have IMDS access for Workload Identity** — instead the pod reads a projected federated SA JWT (`AZURE_FEDERATED_TOKEN_FILE`) and performs a client-assertion exchange against the Entra token endpoint (`login.microsoftonline.com`). So the "reuse + generalise" here is **not config-only**: both stdlib token providers need a second token-source path (federated-file → client-assertion). This is a well-scoped gateway slice (mirrors the existing IMDS provider shape, stdlib-only per the F069/F072 no-`azure-identity`-SDK ruling), and the `AZURE_OPENAI_IDENTITY_RESOURCE` audience knob (`azure_identity.py:91`) already generalises cleanly. Flag it as a named AKS-service-identity slice, not a checkbox.

> **UNCONFIRMED:** whether the maintainer wants to hold the stdlib-only line for the federated client-assertion exchange or adopt `azure-identity` (`DefaultAzureCredential` handles both IMDS and Workload Identity transparently). F069/F072 explicitly rejected the SDK for the VM's two IMDS calls; the federated exchange is more involved, so the SDK trade-off should be re-decided for AKS. Recommend a short ADR addendum.

---

### 4.2 End-user identity — Entra SSO + SCIM (the sizeable workstream)

Today the fork ships a **complete self-contained local auth substrate**. Enterprise buyers on Entra will often want their lawyers to sign in with corporate SSO and be provisioned/deprovisioned automatically. **DECIDED (maintainer, 2026-07-10): SSO is an OPTIONAL overlay, not a replacement — the local auth substrate is ALWAYS retained; a customer that mandates SSO-only disables local login by configuration. Both live side by side and each customer chooses.** The analysis below measures the seam so the optional overlay is well-scoped, not to justify ripping local auth out.

**How much of the app assumes local auth (measured):**

- **331 auth-dependency usages across 32 router files** — `ActiveUser` (123), `AdminUser` (92), `MutatingUser` (82), `OperatorUser` (17), `CurrentUser` (17). Every one funnels through a **single choke point**: `get_current_user` (`api/app/api/dependencies.py:51-75`) → `decode_access_token` (`api/app/security/jwt.py:125`) → **HS256 verification against a local `settings.jwt_secret`**.
- The **good news**: because there is exactly one seam, an Entra-issued bearer token can be verified there (validate an Entra JWT / accept an SSO-proxy identity) without touching 331 call sites — the role model downstream is unchanged.
- The **optionally-disabled surface** (retained in the product; a customer on SSO-only disables these by config — they are NOT removed, since local login stays supported for other customers): the local credential + lifecycle machinery — `POST /auth/login`, `/refresh`, `/logout`, `/change-password`, all `/mfa/*` (setup/enable/verify/disable), `/accept-invite`, `/password-reset(-request)` (`api/app/api/auth.py`), plus the admin lifecycle: `create_invite` / `resend` / `revoke` / `disable` / `enable` / `update_user_role` (`api/app/api/admin.py:1031+`, `:804`). Under Entra SSO these are owned by the IdP; under SCIM, user create/update/disable is driven by Microsoft Entra's provisioning service, not by our admin invites. MFA in particular moves entirely to Entra Conditional Access.
- **Web coupling**: `web/src/lib/lq-ai/auth/` (auth store), `web/src/routes/lq-ai/login/`, `web/src/lib/lq-ai/api/auth.ts` — the SPA login/refresh flow is rebuilt around an OIDC redirect.

**Standards confirmed:** Entra enterprise apps do **SSO via SAML or OIDC**, and **automatic provisioning via SCIM 2.0** (create/update/deactivate users *and groups*), with group-based provisioning driving access by group membership ([Learn: app provisioning / SCIM](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/user-provisioning), [Learn: build a SCIM endpoint](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups)). SCIM requires us to **build and host a SCIM 2.0 endpoint** that Entra calls — that is net-new API surface, not a config toggle.

#### Mapping our role model (ADR-F064) → Entra groups

Our RBAC is DB-backed and small, which maps cleanly to Entra groups/claims:

| Fork role | Backed by | Entra mapping |
|---|---|---|
| `admin` | `users.role` + `users.is_admin` (`api/app/models/user.py:35,40`) | Entra group → `admin` |
| `member` (the lawyer / "user") | `users.role` default `'member'` | Entra group → `member` (default) |
| `viewer` | `users.role`, enforced read-only (ADR-F064 D1) | Entra group → `viewer` |
| `operator` | `users.role`, **bootstrap-only, is_admin superset**, excluded from cross-user tenant data (ADR-F064 D2) | **Deliberately NOT an Entra group** — see caveat |

The assignable-role enum is `{admin, member, viewer}` (`api/app/api/admin.py:691`); **`operator` is intentionally excluded** and requesting it via the role API 422s (`admin.py:825-830`). That fence is load-bearing: the operator is "whoever runs the platform" (ADR-F064 context) and its separation-of-duties model — operator ⊅ cross-user tenant data — must survive SSO. **Recommendation: keep `operator` provisioned locally/out-of-band (or a tightly-scoped separate group), not through the same SCIM group flow as tenant users**, so an IdP misconfiguration can't mint an operator. This is an open design point (below), and a natural ADR.

#### Why this is its own workstream, not a line item

An honest SSO/SCIM cut requires: (1) an OIDC token-verification path at the `get_current_user` seam (or an authenticating reverse proxy in front of the api pod); (2) JIT user provisioning on first SSO login *or* a hosted SCIM 2.0 endpoint; (3) role↔group mapping + claim parsing; (4) deciding the fate of every local lifecycle endpoint (disable vs delete vs gate-behind-a-flag); (5) MFA/password policy handoff to Entra Conditional Access; (6) the SPA OIDC redirect rebuild; (7) preserving the `operator` fence outside the IdP. That is a milestone with its own ADR, not a slice.

---

### 4.3 Maintainer ruling (2026-07-10) — DECIDED

**SSO is OPTIONAL and per-customer; local login is ALWAYS retained.** SSO/SCIM is an opt-in identity overlay
a customer can enable; it does not replace or retire our local auth. A customer that mandates work-account-only
sign-in disables local login by configuration. The product must support **both, side by side**, with the
choice per deployment. The two bullets below are retained only as rationale for *which optional capability
lands first* (SSO before SCIM):

- **Fast-follow (recommended default):** ship cut 1 with **service identity keyless (Workload Identity)** + the **existing local login retained** for end users (admin-invite lifecycle already works, ADR-F061/F064). This de-risks the first customer — SSO is the single most common enterprise procurement blocker but rarely a *day-one* deployment blocker, and our local auth is already hardened (MFA, rate-limits, session caps, HMAC refresh index). SSO/SCIM lands as the very next milestone.
- **First-cut:** if the design-partner customer's security review *gates* on "no local passwords, SSO only," SSO (OIDC) must be in cut 1; SCIM provisioning can still trail (admins invite manually until SCIM lands).

The service-identity half should be **in the first cut regardless** — it is the keyless posture the enterprise story is sold on and the low-risk generalisation of decisions already made.

---

### 4.4 Recommendation

1. **Service identity → first cut.** Adopt AKS Workload Identity for gateway (Foundry + Key Vault), api, and the two workers (Postgres + Blob). All four backends are confirmed Entra-capable. Grant the Foundry role to the **gateway pod only** — this preserves and strengthens the sole-egress/sole-key-holder invariant. Budget **one bounded gateway slice** to add a federated-token-file / client-assertion path to `keyvault.py` + `azure_identity.py` (they hardcode IMDS today), and re-decide the stdlib-vs-`azure-identity` question in a short ADR addendum to F069/F072.
2. **End-user identity → its own ADR'd workstream, sequenced as a fast-follow** unless the first customer's security review gates on SSO. Land **Entra OIDC SSO first** (verify at the single `get_current_user` seam or via an auth proxy), then **SCIM provisioning** as a second slice (build the SCIM 2.0 endpoint). Map `admin`/`member`/`viewer` → Entra groups; **keep `operator` out of the tenant SCIM group flow** to protect the ADR-F064 operator fence.
3. **Leave room for the future.** The audience/scope knob (`AZURE_OPENAI_IDENTITY_RESOURCE`) already generalises across Foundry routes; the same federated-token provider is what PTU/fine-tuned deployments will authenticate through later, so no rework is implied when those enter scope.

## §5 — Networking: private cluster to enterprise controls

This section designs the AKS network posture for a per-customer, deploy-into-the-customer's-own-subscription instance. It is the AKS realisation of the fork's restricted-egress private profile (ADR-F070) and hardens, at the network layer, the fork's first law: **the Inference Gateway is the sole egress and sole key-holder** (ADR-F010, CLAUDE.md). Every Azure claim below is verified against Microsoft Learn (URLs inline); anything I could not verify to GA is flagged **UNCONFIRMED**.

### 5.0 Verdict summary

| Decision | Recommendation | Confidence |
|---|---|---|
| API server exposure | **Private cluster via API Server VNet Integration** (not the legacy Private Link tunnel) | High (GA) |
| Ingress + WAF | **Application Gateway for Containers (AGC) + Azure WAF, internal/private frontend** as the default; **Front Door Premium + WAF + Private Link** as an option for customers who mandate a global edge. **Do NOT build new on AGIC (legacy, patches-only through Nov 2026); do NOT hard-depend on ingress-nginx (community EOL 2026).** | Med-High |
| Data-plane reachability | **Private Endpoints** for Postgres Flexible Server, Key Vault, Blob, ACR (Premium); public network access disabled | High (GA) |
| Egress control | **`outboundType=userDefinedRouting` → Azure Firewall, deny-by-default, FQDN allowlist**; the AKS realisation of ADR-F070 §8.4's enumerable egress table | High (GA) |
| Gateway-sole-egress enforcement | **Belt-and-suspenders: default-deny K8s NetworkPolicy (Azure CNI powered by Cilium) + Azure Firewall app-rules** — only the gateway pod may reach Foundry | High (GA) |
| Collabora/WOPI | ClusterIP-only, no ingress route; NetworkPolicy: only `web` may reach it, it may reach only `api`, zero internet egress | High (design) |

### 5.1 Private cluster — API server exposure

Two Azure mechanisms give a private API server; they are **not** the same and the choice matters for a repeatable landing zone.

- **API Server VNet Integration (recommended).** The API server endpoint is projected into a **delegated subnet in the cluster VNet**, so control-plane↔node traffic stays on the private network **without a private-link tunnel**. It can be created as a **private** cluster (API server reachable only over private VNet connectivity) and is **GA in all public-cloud regions except qatarcentral** ([Microsoft Learn: API Server VNet Integration](https://learn.microsoft.com/en-us/azure/aks/api-server-vnet-integration)). Operational trap to carry into IaC: enabling it on an existing cluster **requires an immediate manual cluster restart** to take effect — so provision it **at create time** in Terraform/Bicep, never as a day-2 flip.
- **Legacy private cluster (Private Link + private FQDN).** The older model exposes the API server through a private endpoint / private DNS zone ([Microsoft Learn: Create a private AKS cluster](https://learn.microsoft.com/en-us/azure/aks/private-clusters)). Still supported, but VNet Integration is the cleaner, lower-latency default for a greenfield per-customer build.

Either way, cluster admin reaches the API server from the customer's network (hub VNet peering, Bastion, or a jump host) — consistent with ADR-F070's "access via SSH tunnel/Bastion, no public URL" posture, now at the control-plane layer.

**UNCONFIRMED:** exact interaction of authorized-IP-ranges with VNet Integration on a fully-private cluster (docs exist but I did not fully verify the private-cluster case) — resolve at implementation.

### 5.2 Ingress + WAF — AGIC vs Application Gateway for Containers vs Front Door

**Current Microsoft guidance has moved on from AGIC.** Microsoft is centring the future on the **Gateway API** and **Application Gateway for Containers (AGC)**; AGIC (the add-on) gets **support continuity through November 2026 (critical security patches only)** while investment goes to AGC ([Microsoft Community Hub: From Ingress to Gateway API](https://techcommunity.microsoft.com/blog/azurearchitectureblog/from-ingress-to-gateway-api-a-pragmatic-path-forward-and-why-it-matters-now/4489779); [Microsoft Learn: migrate from AGIC to AGC](https://learn.microsoft.com/en-us/azure/application-gateway/for-containers/migrate-from-agic-to-agc)). **Verdict: do not build a new enterprise product on AGIC.** Separately, the community **ingress-nginx** controller is EOL in 2026 — so the fork should not hard-depend on it either; the current Caddy edge (below) or an Azure-native L7 is the safer basis.

Two go-forward options, both giving a private frontend + Azure WAF:

1. **Application Gateway for Containers (AGC) — recommended default.** A ground-up, Kubernetes-native L7 offering with a dedicated control/data plane, an in-cluster **ALB controller**, native **Gateway API** support (also accepts Ingress), near-real-time route/pod updates, higher scale ceilings than AGIC, and **native WAF integration** ([Microsoft Learn: What is Application Gateway for Containers?](https://learn.microsoft.com/en-us/azure/application-gateway/for-containers/overview); [TechCommunity: AGC vs AGIC](https://techcommunity.microsoft.com/blog/appsonazureblog/application-gateway-for-containers-vs-application-gateway-ingress-controller---w/3914901)). It is **regional**, which fits single-region, data-residency-bound legal customers. AGC supports an internal frontend for a fully-private ingress ([Microsoft Q&A: AGC internal load balancer support](https://learn.microsoft.com/en-us/answers/questions/5845198/application-gateway-for-containers-internal-load-b)).
2. **Azure Front Door Premium + WAF + Private Link — option for a global edge.** Front Door Premium reaches an **AKS internal load balancer origin over Private Link** (it references the `kubernetes-internal` LB and provisions a managed private endpoint the customer approves), keeping the origin fully private while giving a global POP edge, WAF, and DDoS ([Microsoft Learn: Front Door Premium to internal LB with Private Link](https://learn.microsoft.com/en-us/azure/frontdoor/standard-premium/how-to-enable-private-link-internal-load-balancer); [Microsoft Learn: Secure your origin with Private Link](https://learn.microsoft.com/en-us/azure/frontdoor/private-link)). Constraint to design around: **Front Door forbids mixing public and private origins in one origin group.** Front Door is the right pick only when a customer already standardises on it or needs multi-region/global; for the single-tenant, single-region default it is more moving parts than AGC.

**How this maps to the existing artifact.** The current stack fronts everything with a custom **Caddy** edge that already performs WAF-like duties: security headers, an edge-deny of the service-to-service internal API (`/api/v1/internal/*`), an edge-deny of the WOPI protocol surface, `/metrics` denied at the edge, and access-log scrubbing of the WOPI `access_token` (`deploy/caddy/Caddyfile`, verified). On AKS these app-level denies should be **preserved as an in-cluster ingress/route layer behind the Azure L7+WAF** — the Azure WAF is the enterprise perimeter control the customer's security team wants to see, and the Caddy/route rules remain the application-aware defense in depth. Keeping the Caddy layer in-cluster (as the internal upstream behind AGC/Front Door) is the lowest-risk path since those denies are already written and tested.

**UNCONFIRMED:** the exact **GA state of WAF *on AGC*** and whether AGC WAF policy parity matches classic Application Gateway WAF — Microsoft describes AGC as having "native WAF integration" but I did not verify GA/feature-parity to the depth this decision warrants. Confirm before committing AGC as default; if AGC-WAF is still maturing, Front Door Premium + WAF becomes the safer Phase-1 default.

### 5.3 Data-plane reachability — Private Endpoints, public access disabled

Every managed dependency the fork's data plane maps to supports **Azure Private Link / Private Endpoint**, so the entire data plane can run with **public network access disabled**:

| Service | Private access | Source |
|---|---|---|
| Azure Database for PostgreSQL **Flexible Server** (Postgres + pgvector) | Private Endpoint via Private Link (in addition to VNet-injected private access) | [Microsoft Learn: PostgreSQL networking with Private Link](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private-link) |
| Azure **Key Vault** (ADR-F069 provider-key source) | Private Endpoint via Private Link | [Microsoft Learn: Integrate Key Vault with Private Link](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-service) |
| Azure **Blob** Storage (MinIO → Blob) | Private Endpoint per sub-resource (blob) | [Microsoft Learn: Use private endpoints for Storage](https://learn.microsoft.com/en-us/azure/storage/common/storage-private-endpoints) |
| Azure **Container Registry** (GHCR → customer ACR) | Private Endpoint — **Premium SKU only** (max 200 PEs), public access disable-able | [Microsoft Learn: Private Link for ACR](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-link) |
| Azure **AI Foundry / Azure OpenAI** (gateway's model egress) | Private Endpoint via Private Link; **public network access can be set to Disabled** | [Microsoft Learn: Configure network isolation for Foundry](https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link); [oneuptime: Azure OpenAI private endpoints](https://oneuptime.com/blog/post/2026-02-16-how-to-set-up-azure-openai-service-with-private-endpoints-for-network-isolation/view) |

**Load-bearing consequence for the gateway invariant:** because **Azure AI Foundry / Azure OpenAI itself supports a Private Endpoint with public access disabled**, the gateway pod can reach the customer's model deployments **entirely over the private network** — no internet egress needed for inference at all. That is the strongest possible realisation of "gateway is the sole egress": in the fully-private posture, model traffic never leaves the VNet. **UNCONFIRMED:** that the **Anthropic-Claude-on-Foundry** route specifically (`services.ai.azure.com/anthropic`, per the AZ-R report) is reachable over the AI Services Private Endpoint identically to azure-openai — highly likely (same AI Services resource surface) but I did not verify Claude-over-PE explicitly; confirm in the sandbox.

**ACR note for the parameterisation surface:** private-registry pull requires **ACR Premium**; the customer either mirrors the SHA-pinned images from GHCR into their ACR or uses a pull-through cache — this is the AKS version of ADR-F070 §8.4's "image side-load / registry mirror" line and a values-file input for customer #2.

### 5.4 Egress control — deny-by-default via Azure Firewall

The AKS realisation of ADR-F070's restricted-egress posture is **`outboundType=userDefinedRouting`**, which forces **all** node egress through a UDR to **Azure Firewall** with **no other egress path** ([Microsoft Learn: Limit egress traffic with Azure Firewall](https://learn.microsoft.com/en-us/azure/aks/limit-egress-traffic)). Azure Firewall filters outbound HTTP/S by **destination FQDN**, and the **`AzureKubernetesService` FQDN tag** auto-maintains the AKS control-plane/platform FQDNs the cluster must reach; separate network rules cover the non-HTTP/S platform dependencies ([Microsoft Learn: Outbound network and FQDN rules for AKS](https://learn.microsoft.com/en-us/azure/aks/outbound-rules-control-egress)). This is precisely the "small, fully-enumerable egress surface" ADR-F070 §8.4 designed for — the same inventory (Azure model endpoints; `*.vault.azure.net`; a one-time HuggingFace pull for Docling/EasyOCR; registry pulls) becomes a **firewall allowlist** instead of a runbook table.

Carry-over nuances from ADR-F070 §8.4 that become firewall rules:
- **Model endpoints** — allowlist the customer's `*.services.ai.azure.com` / `*.openai.azure.com` region host (or, in the fully-private posture of §5.3, route via Private Endpoint and **omit the firewall allow entirely**).
- **`ingest-worker` one-time model download** — Docling layout/TableFormer + EasyOCR (~700 MB from `huggingface.co`) is a **one-time first-ingest** egress. Best practice on AKS: **pre-bake or pre-seed** into the image/PVC so the steady-state firewall can keep `huggingface.co` denied; else open it in a maintenance-window app-rule, or set `LQ_AI_DOCLING_ENABLED=false`. (ADR-F070 §8.4 already documents all three mitigations.)
- **Key Vault / ACR** — reachable over Private Endpoint (§5.3), so no firewall allow needed once PEs exist.

### 5.5 Gateway-as-sole-egress expressed as NetworkPolicy + firewall (defense in depth)

The gateway-only-egress guarantee is **already enforced at the application layer** (ADR-F010: a direct provider call from agent code is a security regression; area config cannot carry a `model` string that would bypass the gateway). Code-grounded confirmation from this audit: **no api/worker code contains a provider endpoint** — a grep of `api/app` for `api.anthropic.com|*.openai.azure.com|services.ai.azure.com|api.openai.com` returns only a *comment* asserting their absence (`api/app/agents/matter_consolidation.py:33`), while provider base URLs live **only** in `gateway/app/providers/*` (e.g. `gateway/app/providers/azure_openai.py:148`). The api/workers reach the gateway solely via `lq_ai_gateway_url` (`api/app/config.py:317`), and every prod service is wired to `LQ_AI_GATEWAY_URL=http://gateway:8001` (`docker-compose.prod.yml`). So the app-level invariant holds; K8s adds **two independent network layers beneath it**:

1. **Kubernetes NetworkPolicy (pod-level), default-deny egress.** Recommend **Azure CNI Powered by Cilium** as the dataplane: it supports the standard `NetworkPolicy` resource (L3/L4 ingress+egress) **plus** `CiliumNetworkPolicy` with **L7 and FQDN-based egress filtering** on an eBPF dataplane, and is Microsoft's recommended choice for new clusters ([Microsoft Learn: Azure CNI Powered by Cilium](https://learn.microsoft.com/en-us/azure/aks/azure-cni-powered-by-cilium); [Microsoft Learn: Secure pod traffic with network policies](https://learn.microsoft.com/en-us/azure/aks/use-network-policies)). Policy shape:
   - **Default-deny all egress** in the app namespace.
   - **gateway** pod: the *only* pod with egress allowed to the Foundry destination (Private Endpoint IP, or `*.services.ai.azure.com` FQDN via CiliumNetworkPolicy) + Key Vault PE + Postgres PE (for its `inference_routing_log` writer).
   - **api / arq-worker / ingest-worker**: egress allowed only to the `gateway` ClusterIP, Postgres PE, Redis, Blob PE — **never** to the internet. (`ingest-worker` gets the scoped, temporary HuggingFace exception per §5.4.)
   - **web**: egress only to `api` (and to `collabora` per §5.6).
   - **collabora**: egress only to `api` (WOPI callbacks); **no internet egress**.
   - **Known Cilium limitation** to design around: a `NetworkPolicy` `ipBlock` cannot select pod or node IPs — use pod/namespace selectors for in-cluster rules and reserve `ipBlock`/FQDN for the private-endpoint/external destinations ([Microsoft Learn: Azure CNI Powered by Cilium](https://learn.microsoft.com/en-us/azure/aks/azure-cni-powered-by-cilium)).
2. **Azure Firewall (subnet/node-level), FQDN allowlist** (§5.4) — a second, node-level chokepoint so that even a pod that escaped its NetworkPolicy still cannot reach an arbitrary internet host.

Together: **app-level guarantee (ADR-F010) → pod-level NetworkPolicy → node-level firewall**, three layers, only the gateway pod authorised to reach model endpoints. This is the ADR-F070 posture generalised to K8s and is worth an F-series ADR ("gateway-sole-egress as NetworkPolicy + firewall on AKS") because it is a hard-to-reverse, cross-module network contract.

### 5.6 Collabora / WOPI network boundary

Verified topology today: Collabora has **no host port** and is reached only by the `web` nginx, which proxies `/browser/`, `/hosting/`, `/cool/` to `collabora:9980` (`web/nginx.conf:73-100`); its WOPI host allow-list points at `http://api:8000` (`aliasgroup1`, `docker-compose.prod.yml:482`); and the Caddy edge **denies the WOPI protocol surface and the Collabora admin channel** (`web/nginx.conf` regex-denies `cool/adminws`, `cool/getMetrics`, `browser/*/admin`; Caddy `@wopi` handle denies the WOPI surface). AKS translation:
- Collabora → a `Deployment` + **ClusterIP** Service (`:9980`), **never** a LoadBalancer, **never** an ingress route to the admin channel. It stays server-side-only, honouring the MPL self-hosted-not-redistributed boundary.
- **NetworkPolicy:** ingress to `collabora:9980` allowed **only from the `web` pod**; egress from `collabora` allowed **only to `api:8000`** (WOPI callbacks) with **zero internet egress**.
- The edge WAF (AGC/Front Door) must **keep denying** the WOPI surface, admin channel, and `/metrics` and keep scrubbing the WOPI `access_token` from logs — i.e. port the existing Caddy `@wopi`/`@internal`/`@metrics` deny rules forward. These are already written; they must not regress in the AKS ingress rewrite.
- Collabora needs the `MKNOD` capability for its chroot sandbox (`docker-compose.prod.yml:478`) — a **pod `securityContext.capabilities.add: [MKNOD]`** on AKS; do not grant `privileged`/`SYS_ADMIN` (matches the current posture). **UNCONFIRMED:** whether the customer's Azure Policy / Pod Security admission baseline permits adding `MKNOD` — enterprise clusters often run restricted PSA; this must be validated against the customer landing zone and may need a documented exception.

### 5.7 Recommendation (this section)

Adopt the **fully-private posture** as the enterprise default: **API Server VNet Integration** (private cluster, provisioned at create time); **all data-plane + Key Vault + ACR(Premium) + Foundry behind Private Endpoints with public access disabled** — which lets the gateway reach models entirely in-VNet; **`outboundType=userDefinedRouting` → Azure Firewall deny-by-default** with the ADR-F070 §8.4 egress inventory as the FQDN allowlist; **Azure CNI Powered by Cilium** with a **default-deny egress NetworkPolicy** where only the gateway pod may reach model endpoints (belt-and-suspenders behind ADR-F010); and **Application Gateway for Containers + Azure WAF (internal frontend)** as the default ingress, with **Front Door Premium + WAF + Private Link** offered for customers who need a global edge. **Explicitly avoid AGIC (legacy) and any hard dependency on ingress-nginx (EOL).** Preserve the existing Caddy WOPI/internal/metrics denies as the in-cluster application-aware layer behind the Azure WAF. Draft an F-series ADR for the gateway-sole-egress-on-AKS network contract.

Phasing fits the charter's ladder: an early single-region MVP can start with a **managed public ingress + selected-networks** and land **§5.1/5.3/5.4/5.5 private networking as the "Phase 2 — private networking" milestone** (the ADR-F070-on-AKS phase the charter already names), so the private posture is a coherent, testable slice rather than a big-bang.

## §6 — Secrets & keys: Key Vault CSI Driver + Workload Identity + CMK

### Verdict

| Concern | Verdict | Why |
|---|---|---|
| **Secret injection into pods** | **Azure Key Vault Provider for Secrets Store CSI Driver (managed add-on) + Microsoft Entra Workload Identity** | Both GA; the add-on mounts KV secrets as tmpfs files (no etcd), Workload Identity gives each pod its own federated identity — the exact "no secrets in etcd where avoidable" posture. This *generalises* ADR-F069 (VM IMDS → KV) to the cluster. |
| **ADR-F069 gateway self-fetch on AKS** | **Retire the in-process IMDS fetch on the AKS profile; keep it VM-only** | F069's `ImdsKeyVaultFetcher` hits the node metadata endpoint `169.254.169.254` (`gateway/app/keyvault.py:107`), which on AKS returns the **node/kubelet** identity, not the pod's Workload Identity — wrong-identity / least-privilege break. The CSI driver is the AKS-native replacement. |
| **ADR-F072 keyless azure-openai on AKS** | **CODE-CHANGE to generalise** | `azure_identity.py` also mints its Entra token from IMDS (`169.254.169.254`). On AKS the keyless path must use the **projected service-account token + `AZURE_FEDERATED_TOKEN_FILE`** (Workload Identity), not IMDS. The scope logic (bare `https://cognitiveservices.azure.com`, no `/.default`) and the "Cognitive Services OpenAI User" role carry over unchanged. |
| **CMK — managed disks / node + PV** | **CONFIRMED GA (Disk Encryption Set)** | Phase-in as a StorageClass + node OS/data-disk DES. Low effort. |
| **CMK — etcd secrets (KMS)** | **CONFIRMED, but classic doc is "legacy"; a newer "KMS data encryption" is Preview** | Needed only if secrets are *synced to K8s Secret objects*; flag preview status. |
| **CMK — Postgres / Blob (if Azure PaaS used)** | **CONFIRMED GA per service** | Only relevant if the data plane moves off in-cluster pgvector/MinIO onto Azure PaaS (§ data-plane section). |

---

### 6.1 What the fork actually needs injected (grounded in code)

Enumerated from `docker-compose.yml` and `.env.example`, the stack's secrets fall into three buckets. This is the set a K8s Secret/CSI strategy must cover — **not** just the Azure provider keys ADR-F069 addresses.

| Secret | Where consumed | Azure-MI-eliminable? |
|---|---|---|
| `LQ_AI_GATEWAY_KEY` | api↔gateway shared secret, **both directions**, in 4 services (`docker-compose.yml:91,209,324,404`) | **No** — internal shared secret, no Azure equivalent. Must live in KV → CSI. |
| `JWT_SECRET` | api auth signing (`docker-compose.yml:215`) | **No.** |
| `LQ_AI_GATEWAY_MASTER_KEY` (Fernet) / `LQ_AI_BRIDGE_MASTER_KEY` | gateway BYOK decrypt (ADR-F069 §Context); bridge (`docker-compose.yml:246`) | **No.** |
| `POSTGRES_PASSWORD` | every service's `DATABASE_URL` (`docker-compose.yml:30,98,198,298,389`) | **Only** if moved to Azure PostgreSQL Flexible Server + Entra auth; **No** for in-cluster pgvector. |
| `MINIO_ROOT_PASSWORD` → `S3_SECRET_KEY` | object store (`docker-compose.yml:62,204,308,440`) | **Only** if moved to Azure Blob + Workload Identity; **No** for in-cluster MinIO. |
| `COLLABORA_ADMIN_PASSWORD` | editor (`docker-compose.yml:525`) | **No.** |
| `AZURE_OPENAI_API_KEY` | gateway (`docker-compose.yml:106`) | **Yes** — ADR-F072 keyless MI (once generalised to Workload Identity). |
| `AZURE_ANTHROPIC_API_KEY`, `AZURE_FOUNDRY_API_KEY` | gateway (`:111,113`) | **Partially** — no MI path built yet (anthropic adapter sends `x-api-key`); KV-sourced secret until extended. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MINIMAX_API_KEY`, `DEEPSEEK_API_KEY`, `AWS_*`, `GOOGLE_APPLICATION_CREDENTIALS` | gateway (`:100–128`) | **No** — non-Azure providers have no Azure MI; always a stored secret. |
| `LANGFUSE_SECRET_KEY`, `SLACK_*`, `MICROSOFT_APP_PASSWORD`, `LQ_AI_BRIDGE_TOKEN` | observability / profile-gated bridges | **No** — third-party secrets. |

**Load-bearing conclusion:** even at maximum keyless posture, a substantial residue of secrets (`LQ_AI_GATEWAY_KEY`, `JWT_SECRET`, the Fernet master key, non-Azure provider keys, and — unless the data plane moves to Azure PaaS — Postgres/MinIO creds) **must** still be injected. Workload Identity removes the *Azure-provider* keys; it does not remove the need for a secret-injection mechanism. That mechanism is the CSI driver.

---

### 6.2 The recommended pattern: CSI Driver + Workload Identity

**Injection.** Enable the managed add-on at cluster create with `--enable-addons azure-keyvault-secrets-provider`, and Workload Identity with `--enable-oidc-issuer --enable-workload-identity` ([Microsoft Learn — CSI driver](https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-driver), [identity access](https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-identity-access)). Each workload (gateway, api, workers) gets a Kubernetes ServiceAccount federated to a **user-assigned managed identity** via `az identity federated-credential create`; a `SecretProviderClass` with `usePodIdentity:"false"` + `clientID:<uami>` mounts the named KV secrets at `/mnt/secrets-store` as tmpfs files.

**etcd avoidance.** Mounted-only secrets live in a tmpfs volume, **never in etcd**. The moment you add a `secretObjects` block to sync a mounted secret into a native K8s `Secret` (needed when a container reads a value from an env var rather than a file), that value **does** land in etcd — which is what makes §6.4's etcd CMK relevant. Prefer file mounts; sync to a K8s Secret only where the app can't read a file.

**Rotation.** The driver supports autorotation of both mounted content and synced K8s Secrets via `--enable-secret-rotation` (default poll interval **2 minutes**) ([Microsoft Learn — CSI driver](https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-driver)). **Fork caveat that survives to AKS:** ADR-F069 records that the *gateway rebuilds adapters only at process start / BYOK hot-apply, not on SIGHUP* — so a rotated provider key requires a **pod restart** to take effect even though the CSI mount updates within 2 min. Budget a rolling restart (or the BYOK hot-apply path) into rotation runbooks.

**Reconciling ADR-F069.** F069 chose an in-process, stdlib IMDS fetch precisely to avoid the `azure-identity` SDK on a VM. On AKS that rationale flips: the CSI add-on **is** the platform-supplied fetcher, so the gateway should read KV secrets from mounted files and the F069 `keyvault.py` IMDS path should be **disabled on the AKS profile** (it would otherwise resolve the node identity, `gateway/app/keyvault.py:107`). F069 stays valid and useful for the VM/demo tier (ADR-F058); AKS supersedes its *mechanism* while preserving its *intent* (keys off disk, sourced from the customer's KV). This is a generalise-don't-re-decide move; draft it as an F069 AKS addendum.

**Reconciling ADR-F072.** Same shape: the keyless azure-openai path is correct in intent but its IMDS token mint (`gateway/app/azure_identity.py`, header block) must gain a Workload-Identity branch (projected SA token at `AZURE_FEDERATED_TOKEN_FILE` exchanged for an Entra token) for AKS. The **scope trap is unchanged** — bare `https://cognitiveservices.azure.com`, no `/.default` — and the role stays "Cognitive Services OpenAI User". This is the single biggest code item in this section; everything else is deployment config.

---

### 6.3 Customer-managed keys (CMK) — a frequent large-enterprise mandate

CMK is **encryption-at-rest with the customer's own KV keys** (customer holds the Key Encryption Key; Azure wraps the per-resource Data Encryption Key). Confirmed support, per surface the fork touches:

| Surface | CMK support | Status | Source |
|---|---|---|---|
| **AKS node OS + data disks / Azure Disk PVs** | Disk Encryption Set referencing a KV key | **GA** | [Microsoft Learn — CMK for AKS managed disks](https://learn.microsoft.com/en-us/azure/aks/azure-disk-customer-managed-keys) |
| **AKS etcd (K8s secrets at rest)** | KMS provider, KV-held KEK envelope-encrypts etcd secrets | Classic doc marked **legacy**; newer **"KMS data encryption" is Preview** | [KMS etcd (legacy)](https://learn.microsoft.com/en-us/azure/aks/use-kms-etcd-encryption) · [KMS data encryption (Preview)](https://learn.microsoft.com/en-us/azure/aks/kms-data-encryption) |
| **Azure Blob / Storage account** (only if data plane moves off MinIO) | Account-level CMK; KV needs soft-delete + purge-protection | **GA** | [Storage CMK overview](https://learn.microsoft.com/en-us/azure/storage/common/customer-managed-keys-overview) |
| **Azure Database for PostgreSQL Flexible Server** (only if off in-cluster pgvector) | CMK data encryption (RSA 2048/3072/4096) | **GA, worldwide** | [PostgreSQL data encryption](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/security-data-encryption) |
| In-cluster **pgvector Postgres / MinIO** (self-hosted pods) | No app-level CMK; protected only by the **underlying managed-disk CMK (DES)** envelope | GA (via disk CMK) | as above |

**Two important CMK caveats to flag:**
- **etcd KMS won't work with a system-assigned identity** (the KV access policy must be set before the feature is enabled, and system-assigned MI doesn't exist until after cluster creation) — use a **user-assigned** identity. Also, a permanently deleted KEK renders etcd secrets undecryptable and can force cluster recreation ([KMS etcd](https://learn.microsoft.com/en-us/azure/aks/use-kms-etcd-encryption)). Treat the KEK lifecycle as a first-class operational obligation.
- The KV holding CMK KEKs must have **soft-delete + purge-protection** enabled (Storage/Postgres both require it).

---

### 6.4 Phasing (per-customer parameterised, not a rewrite)

**Phase A — Baseline (every customer, ships with the AKS profile).** CSI driver add-on + Workload Identity; all fork secrets (§6.1) in the *customer's* KV; mount as files, sync-to-Secret only where unavoidable; autorotation on. Generalise F069 (disable in-process IMDS on AKS) and F072 (Workload-Identity token branch). Platform-default SSE + **managed-disk CMK via DES** for node/PV disks — cheap, satisfies the common "our keys encrypt the disks" ask. Everything is a Helm/values parameter → customer #2 is a values file, not a rewrite.

**Phase B — Enterprise CMK mandate.** Add **etcd KMS encryption** with the customer's KEK (user-assigned identity; flag the Preview vs legacy path at deploy time), and, where the customer requires managed-PaaS data at rest under their key, offer the data-plane swap to **PostgreSQL Flexible Server (CMK)** + **Blob (CMK)** as an opt-in profile (this is primarily the data-plane section's call; §6 supplies the CMK confirmation).

**Phase C — Leave room for (note, don't build).** Managed HSM-backed KEKs for FIPS-140-3 mandates (KV Managed HSM is a documented CMK KEK store for Storage/Postgres); PTU/fine-tune identities would ride the same Workload-Identity + role-assignment machinery. No new architecture needed — the identity plumbing generalises.

---

### Honest UNCONFIRMED / flagged items
- **Workload Identity GA date** not separately pinned to a citation here; treated as GA on the strength of the Learn doc presenting it as the standard method and noting pod-managed identity was *deprecated* Oct 2022 (its successor). Confirm the exact GA milestone if the report needs it.
- **AKS "KMS data encryption"** (the successor to legacy etcd KMS) is **Preview** — do not commit a customer to it for GA SLAs; use the legacy KMS etcd path or platform default until it GAs.
- Whether the fork's **api/worker code can read secrets from CSI-mounted files vs requires env vars** was not exhaustively audited; several values (`DATABASE_URL`, `S3_SECRET_KEY`) are composed in `docker-compose.yml` and read from env — those will need either sync-to-Secret or an entrypoint that reads the file. Scope this in the AKS packaging slice.

## §7 — IaC + delivery: the repeatable centrepiece

This section answers the "customer #2 is a parameterised repeat, not a rewrite" mandate. Three decisions: (1) Terraform vs Bicep for the landing-zone infra; (2) how the app is packaged and delivered onto AKS; (3) the exact **parameterisation surface** — the finite set of values a customer fills in to stand up their instance. The surface is derived directly from the fork's existing compose env contract (`.env.prod.example`, `docker-compose.prod.yml`), so it is grounded, not invented: every knob a self-host tenant sets today becomes a Terraform input or a Helm value tomorrow.

### 7.1 Terraform (azurerm) vs Bicep

| Axis | Terraform (azurerm) | Bicep |
|---|---|---|
| Module reuse | **Azure Verified Modules** (Microsoft-maintained) publish AKS/PostgreSQL/KeyVault/Blob resource + pattern modules for Terraform; Microsoft ships a documented "deploy production AKS via AVM Terraform module" path [MS Learn]. | AVM also publishes **Bicep** modules for the same resources — parity is real, not a Terraform-only advantage. |
| State | External state required. `azurerm` backend stores it in an Azure Blob container with **native blob-lease locking** (default, no separate lock table) [HashiCorp / MS Learn]. | **Stateless** — ARM *is* the state. No state file to host, lock, or lose. |
| "We host nothing" fit | State must live **in the customer's subscription** (a bootstrap storage account we create first). Slightly more moving parts, but self-contained per customer. | Zero state-hosting problem — a genuine edge for an artifact shipped into a subscription we never operate. |
| Enterprise familiarity | The enterprise lingua franca; most customer platform teams already run Terraform + a state backend + CI. | Azure-native shops (especially Microsoft-partner-led ones) increasingly standardise on Bicep; some *mandate* it. |
| Reference implementation | AKS Landing Zone Accelerator ships **both** Terraform and Bicep reference modules; Azure Landing Zone accelerators for both are GA [MS Tech Community]. | Same accelerator, Bicep flavour. |

**Verdict: Terraform (azurerm) with Azure Verified Modules as the primary path, one root module + per-customer `*.tfvars`.** Rationale: it is the enterprise default our target customers already operate; AVM gives Microsoft-maintained AKS/Postgres/KeyVault/Blob building blocks so we assemble rather than author; and a single root module parameterised by a tfvars file is the cleanest expression of "customer #2 = same module, new variables." State lives in a **bootstrap storage account we create as step 0 inside the customer's own subscription** (azurerm backend, native blob-lease locking — nothing for us to host).

**Honest counter-argument to surface:** Bicep's statelessness removes the one awkward part of the Terraform story (where does state live when we host nothing), and AVM parity means we do not lose module reuse by choosing it. If early customers are Bicep-mandated Microsoft-partner shops, a Bicep root is a legitimate re-decision — **not** a rewrite of the app layer (Helm is IaC-tool-agnostic; only the infra root swaps). Recommend Terraform now, keep the infra/app boundary clean so a Bicep root is a drop-in alternative.

### 7.2 App packaging + delivery: Helm + GitOps (Flux via the managed AKS extension)

**Packaging — one umbrella Helm chart.** The eight compose services map to K8s workloads (`api`, `gateway`, `arq-worker`, `ingest-worker`, `web`, `collabora`, + Deployments/StatefulSets or managed-PaaS bindings for `postgres`/`redis`/object-store). A single umbrella chart with per-workload templates and one `values.yaml` is the natural port of `docker-compose.prod.yml`: the compose file is *already* a fully-parameterised, required-var (`${VAR:?}`) manifest — the Helm values map is a near-1:1 lift of its env block.

**Delivery — recommend GitOps via Flux, bootstrapped by pipeline-push.**

- The **"we host nothing"** constraint rules out any central delivery plane that reaches *into* customer clusters (a hosted Argo/Flux we operate, or a pipeline of ours with cluster creds). The correct model is **pull-based GitOps running inside the customer's cluster**, reconciling from a Git/OCI source the customer controls.
- Azure ships GitOps as a **first-class, Microsoft-supported, auto-upgraded AKS cluster extension** (`microsoft.flux`), managed via ARM/CLI/Portal/**Terraform** — so we *reuse* a managed capability rather than self-manage Flux controllers [MS Learn]. This directly generalises the "reuse Azure-managed pieces" pattern (ADR-F069/F072 lineage). Argo CD, by contrast, is self-installed and self-operated in-cluster — more ops surface for the customer, no Azure-native support contract.
- **Phasing:** Phase 1 bootstrap = **pipeline-push** (`helm upgrade` from the customer's own pipeline against their cluster) — simplest first cut, no GitOps prerequisite. Phase 2 = enable the `microsoft.flux` extension (installed by our Terraform) pointed at the customer's config repo/OCI artifact, so drift-correction and SHA-pinned rollouts become declarative. Image + chart SHA pinning carries over from the existing `LQ_AI_IMAGE_TAG=sha-<sha>` contract (never `:main`) — see §8 for ACR mirroring.

### 7.3 The parameterisation surface — what makes customer #2 a repeat

The surface already exists as the fork's prod env contract. Below it is re-expressed as a **single customer-facing manifest** split into two consumers: **Terraform inputs** (infra the customer's subscription must provision) and **Helm values** (app config injected into workloads). A few values are *generated* (never customer-authored) and a few are *derived*. Grouping mirrors `.env.prod.example`.

#### Proposed `customer.values.yaml` schema

```yaml
# ── Subscription / landing zone (Terraform inputs) ───────────────────────────
azure:
  subscriptionId: "00000000-…"        # customer's own subscription — we host nothing
  tenantId:       "…"                  # Entra tenant (also used for Workload Identity, §3/§4)
  location:       "swedencentral"      # region; MUST host the Foundry models we depend on (EU: Sweden Central)
  resourceGroup:  "rg-lqai-acme"
  clusterName:    "aks-lqai-acme"

# ── Networking / egress posture (Terraform; realises ADR-F070) ───────────────
network:
  profile:        "private"            # public | private (restricted-egress) — mirrors prod vs private compose overlay
  ingress:        "appgw"              # appgw (AGIC) | frontdoor  (§5 decides; both WAF-capable)
  privateCluster: true                 # private API server + Private Endpoints for PG/KV/Blob/ACR
  egress:         "azurefirewall"      # deny-by-default; gateway-as-sole-egress expressed as NetworkPolicy + FW rules

# ── Public identity + TLS ────────────────────────────────────────────────────
public:
  host:        "acme.lq-ai.example.com"   # LQ_AI_PUBLIC_HOST / LQ_AI_PUBLIC_ORIGIN
  acmeEmail:   "ops@acme.example.com"     # or: bring-your-own cert via KV (enterprise)

# ── Data plane (Terraform; §2 default = managed PaaS) ────────────────────────
data:
  postgres:  { mode: "flexibleServer", sku: "GP_Standard_D2ds_v5", storageGb: 128, ha: "zoneRedundant" }
  redis:     { mode: "azureCache",     sku: "Standard_C1" }
  objectStore: { mode: "blob", account: "stlqaiacme", bucket: "lqai-acme" }   # replaces MinIO/S3_*

# ── Foundry / models (Helm → gateway; keyless via Workload Identity, §3) ─────
models:
  azureOpenAiResource:      "acme-aoai"          # AZURE_OPENAI_RESOURCE
  azureAnthropicResource:   "acme-foundry"       # AZURE_ANTHROPIC_RESOURCE (East US2 | Sweden Central)
  azureFoundryResource:     "acme-foundry"       # AZURE_FOUNDRY_RESOURCE (non-OpenAI Foundry Models)
  useManagedIdentity:       true                 # AZ-6/ADR-F072 → Workload Identity on AKS
  identityResource:         "https://cognitiveservices.azure.com"  # ADR-F072 scope trap: BARE audience, NO /.default
  deployments:                                    # deployment names → gateway model_aliases
    chat:  "gpt-5.4"
    agent: "claude-opus-4-8"
  keyVault:                                       # ADR-F069 fallback if not fully keyless
    name: "kv-lqai-acme"
    secretNames: { openai: "aoai-key", anthropic: "anthropic-key", foundry: "foundry-key" }

# ── Branding (Helm → api; BRAND-1 / ADR-F068, api-only, seed-once) ───────────
branding:
  productName:  "Acme Counsel"      # BRAND_PRODUCT_NAME (1–80, quoted; header-injection-fenced)
  accentLight:  "#2b5cff"           # BRAND_ACCENT_LIGHT  (#RRGGBB)
  accentDark:   "#6f9bff"           # BRAND_ACCENT_DARK   (logo = admin-page upload post-boot, NOT seedable)

# ── First-run accounts + mail (Helm → api) ───────────────────────────────────
bootstrap:
  adminEmail:    "legal-admin@acme.example.com"    # FIRST_RUN_ADMIN_EMAIL
  operatorEmail: "platform-ops@acme.example.com"   # FIRST_RUN_OPERATOR_EMAIL (gateway-surface fence, ADR-F061)
  smtp: { host: "", port: 587, username: "", useTls: true }   # optional; password via secret

# ── Retrieval + budget (Helm → workers) ──────────────────────────────────────
runtime:
  embeddingProvider: "local"        # local ONNX = $0, no egress (default); azure text-embedding-3 (AZ-4a) if managed
  rerankEnabled:     true
  defaultBudgetProfile: "balanced"  # economy | balanced | generous (ADR-F063)

# ── Release pin (Terraform + Helm) ───────────────────────────────────────────
release:
  imageTag:  "sha-<12hex>"          # LQ_AI_IMAGE_TAG — SHA-pinned, never :main
  registry:  "acracme.azurecr.io"   # customer ACR mirror of GHCR (§8)

# ── Generated secrets (NEVER customer-authored — minted into customer KV) ─────
#   postgresPassword, jwtSecret, gatewayKey, gatewayMasterKey(optional),
#   collaboraAdminPassword — cf. scripts/gen-secrets.sh; on AKS these are minted
#   into the customer's Key Vault and mounted via the Secrets Store CSI driver (§6).
```

**Why this is the whole surface.** Every field above traces to an existing, code-grounded env var in `docker-compose.prod.yml` / `.env.prod.example` (columns 3 in the schema comments cite the var names). Nothing new is invented; the AKS work *re-homes* the same contract from a root-owned `.env.prod` file into (a) Terraform inputs for infra and (b) Helm values + CSI-mounted Key Vault secrets for the app. That 1:1 lineage is exactly what makes customer #2 a `tfvars` + `values.yaml` diff rather than a rewrite.

**Recommendation on manifest shape:** keep **one** customer-facing `customer.values.yaml` as the single source of truth; a thin adapter projects its `azure:`/`network:`/`data:` block into Terraform `*.tfvars` and its `models:`/`branding:`/`runtime:` block into Helm `--values`. One file the customer fills, two consumers — avoids the drift of two hand-maintained input files.

### 7.4 Migrations note (defer detail to §8)

`api` **auto-migrates on boot** today (`alembic upgrade head` in the entrypoint; the workers set `LQ_AI_SKIP_MIGRATIONS=1` and wait on api-healthy — `docker-compose.yml:291-305`). On AKS this must become a **Helm pre-install/pre-upgrade hook Job** (migrate → roll workers → roll api), reconciled with the hard rule "never host-side `alembic upgrade` on a live DB." Flagged here because it constrains the Helm chart's release ordering; §8 owns the design.

### Confirmed facts (Azure, cited)

- `microsoft.flux` is a **managed, Microsoft-supported, auto-upgraded AKS cluster extension** for GitOps (Flux v2), configurable via ARM/CLI/Portal/Terraform — Source, Kustomize, Helm, Notification controllers by default.
- **Azure Verified Modules** publish Microsoft-maintained IaC modules for **both** Terraform and Bicep; Microsoft documents a production-AKS-via-AVM-Terraform path.
- The **AKS Landing Zone Accelerator** ships reference modules in ARM, Bicep, and Terraform; Azure Landing Zone accelerators for Bicep and Terraform are GA.
- The **`azurerm` Terraform backend** stores state in Azure Blob with **native blob-lease state locking** (default; no separate lock resource).

### UNCONFIRMED / to verify at build time

- Exact **GA date** of the `microsoft.flux` AKS extension (docs confirm it as a first-class managed extension; a specific GA milestone date was not pinned by the sources) — treat as available/managed, verify billing/region gating at build.
- Whether AVM ships a **pattern** module matching our full topology (private AKS + Flexible Server + Private Endpoints + AGIC) or only resource modules we compose ourselves — verify against the AVM registry when authoring the root module.
- Front Door vs Application Gateway (AGIC) final choice is §5's call; the `network.ingress` value is a placeholder pending that recommendation.

## §8 — Migrations & Release

### Verdict

On K8s, **migration must move out of app boot and become a Helm-managed one-shot `Job` (a `pre-install`/`pre-upgrade` hook) using the api image** — Helm blocks until it completes before rolling any Deployment. The compose "api-as-sole-migrator + `LQ_AI_SKIP_MIGRATIONS=1` on workers + `depends_on: service_healthy`" pattern translates cleanly, and the fork already documents this exact gap internally (DE-327). Image supply is **GHCR → per-customer ACR** by SHA/digest — verified two supported mechanisms (`az acr import` server-side copy, or ACR artifact-cache pull-through; both list `ghcr.io` as a supported upstream). A private/air-gapped ACR (no egress to GHCR) is the P-2 / ADR-F070 posture and is fully supported by ACR import.

There is **one real code defect that makes migrate-on-boot unsafe under replicas** (below): `api/entrypoint.sh` claims Alembic holds a Postgres advisory lock to coordinate racing runners, but `env.py` acquires **no lock at all**. This is harmless at `replicaCount: 1` but becomes a data-race the moment the api scales — which is precisely why the migration Job (single runner by construction) is the correct K8s design, not merely a tidiness preference. (The migrate-on-boot-as-a-scale-defect flag is §10's to own; §8 owns the replacement mechanism.)

---

### How migrate-on-boot works today (code-grounded)

The api container's `ENTRYPOINT` runs `alembic upgrade head` before `exec`'ing uvicorn, gated by an opt-out env var:

- `api/Dockerfile:56-59` — `ENTRYPOINT ["/usr/local/bin/lq-ai-entrypoint"]`; the image bakes `COPY skills/ /skills/` so migration 0032 (seeds builtin NDA playbooks from `/skills/...`) can read its files.
- `api/entrypoint.sh:21-27` — `if [ "${LQ_AI_SKIP_MIGRATIONS:-0}" = "1" ]` skips; else runs `alembic upgrade head`, then serves. On failure the script fails and the container never serves a half-migrated schema.
- `api/entrypoint.sh:29-41` — the entrypoint runs migrations **regardless of CMD**, then honours the container's CMD. This is why workers (same image, `arq` CMD) must set `LQ_AI_SKIP_MIGRATIONS=1` or they, too, would migrate on boot.

Workers skip migration and wait for the api in compose:

- `docker-compose.yml:295-305` (ingest-worker) and `:383-399` (arq-worker): both `depends_on: api: {condition: service_healthy}` and set `LQ_AI_SKIP_MIGRATIONS: "1"`, with inline DE-326 comments naming the api as "the single schema migrator."
- The dedicated-migrate deploy path already exists for the VM/compose product: `scripts/deploy.sh:55-56` runs `dc run --rm -e LQ_AI_SKIP_MIGRATIONS=1 api alembic upgrade head` as an explicit step **before** `up -d --wait`, so a failed migration fails the deploy rather than crash-looping (ADR-F060 D5). **This is the compose analogue of the K8s Job we should build.**

Migration inventory: **95 revisions** in `api/alembic/versions/` (head `0095_org_playbook_versions.py`). `api/alembic/env.py:73-99` runs online migrations over a `NullPool` sync engine (strips `+asyncpg`); `DATABASE_URL` is the only required input.

#### The advisory-lock claim is false (verified)
`api/entrypoint.sh:11-15` asserts: *"Alembic acquires a Postgres advisory lock via its env.py setup, so multiple workers / replicas racing this step coordinate correctly."* **`api/alembic/env.py` contains no `pg_advisory_lock` / lock call**, and a repo-wide grep for `pg_advisory`/`advisory_lock` across `api/` returns nothing. So concurrent boot-time migrators are **uncoordinated**. Today this is masked because the api runs at `replicaCount: 1` and workers skip migration — but it removes any safety argument for keeping migrate-on-boot when the api scales. The Job design sidesteps it entirely (Helm runs exactly one hook Job).

---

### The existing Helm chart and its gap

A Helm chart already exists at `deploy/helm/lq-ai/` (Chart + values + templates). It ships:

- Deployments for **api, gateway, web only** (`templates/deployment-{api,gateway,web}.yaml`) and StatefulSets for postgres/redis/minio.
- **No worker Deployments** (arq-worker / ingest-worker) and **no migration mechanism** — grep for `kind: Job` / `helm.sh/hook` across `deploy/helm/` returns nothing.
- `templates/deployment-api.yaml:1-70` has **no initContainer, no migration step, and no `LQ_AI_SKIP_MIGRATIONS`** — the api pod relies entirely on the baked entrypoint to migrate on boot. `replicas: {{ .Values.api.replicaCount }}` (`values.yaml:69` default `1`).
- Readiness is wired correctly: `deployment-api.yaml:64-69` probes `/ready` (which checks DB+Redis+MinIO+gateway — `api/app/main.py:275-307`); liveness would use `/health` (`main.py:253-268`, always 200 while alive).

This gap is **already logged as DE-327** in `docs/PRD.md:4439-4447`: *"designate a single migrator — a one-shot pre-install/pre-upgrade migration `Job` (or an init-container on the api), set `LQ_AI_SKIP_MIGRATIONS=1` on the worker deployments, and order workers after the api/migration via readiness gating."* Our recommendation ratifies and extends DE-327.

---

### Recommended K8s release mechanism

**1. Migration as a Helm pre-upgrade/pre-install hook Job (single migrator).** Add `templates/job-migrate.yaml`: the **api image** (workers share it — see below), `command: ["alembic","upgrade","head"]`, `DATABASE_URL` wired as in `deployment-api.yaml:32-38`, annotated:

| Annotation | Value | Effect |
|---|---|---|
| `helm.sh/hook` | `pre-install,pre-upgrade` | runs after templates render, before any resource is created/updated ([Helm docs](https://helm.sh/docs/topics/charts_hooks/)) |
| `helm.sh/hook-weight` | `"-5"` | ascending order; negative runs first |
| `helm.sh/hook-delete-policy` | `before-hook-creation,hook-succeeded` | clean prior Job, delete on success |

Helm **waits for the Job to reach completion before rolling the Deployments** — this is exactly the "migrate first, fail the release on migration failure" contract that `scripts/deploy.sh` gives compose. `backoffLimit: 0` (roll-forward-only, matching ADR-F060). This honours the hard rule "never run host-side `alembic upgrade` against a live DB": the migrate runs **in-cluster from the pinned image**, never from an operator laptop.

**2. Ordered rollout: migrate → roll workers → roll api.**
- The **hook Job** is the ordered "migrate" step (Helm gates on it).
- On both the api Deployment **and** the new worker Deployments, set `LQ_AI_SKIP_MIGRATIONS=1` so no long-lived pod migrates on boot (the api pod must set it too now that the Job owns schema — this also neutralises the missing-advisory-lock race across api replicas).
- Because migration is now a completed fact before any pod starts, the compose "workers wait for api-as-migrator" ordering collapses to ordinary readiness: give api and workers an **initContainer that blocks until Postgres is reachable** (or `/ready` gating for anything that calls the api). The task's stated "roll workers → roll api" order is satisfiable via `helm.sh/hook-weight` on separate Jobs only if strict inter-Deployment ordering is required; in practice, with the schema already at head, workers and api can roll concurrently. **Caveat (backward-compat window):** the codebase has no enforced expand/contract migration discipline, so a non-additive migration creates a brief window where old pods run against the new schema during a rolling update. Recommend adopting expand/contract as forward discipline; note it, don't block on it.
- Worker Deployments to add (mirroring compose): `arq-worker` (`command: ["arq","app.workers.arq_setup.WorkerSettings"]`) and `ingest-worker` (`command: ["arq","app.workers.document_pipeline.WorkerSettings"]`), both the api image, both `LQ_AI_SKIP_MIGRATIONS=1`. (Resource sizing / OOM caps are §10/§ resource concerns; the ONNX embedder+reranker memory footprint noted in `docker-compose.yml:275-283,367-374` must carry into `resources.requests/limits`.)

**3. Idempotence & safety.** `alembic upgrade head` is a no-op when already at head, so the hook Job is safe to re-run (helm upgrade with unchanged head). Keep `backoffLimit: 0` + roll-forward-only; rollback = redeploy the prior pinned digest (ADR-F060 lineage).

---

### Image supply: GHCR → customer ACR, SHA-pinned

**What CI publishes today** (`/.github/workflows/images.yml`):
- Tags per push to main: `ghcr.io/<owner>/lq-ai-<service>:sha-<12hex>` **and** `:main` (`images.yml:74,92-94`). Services built: **api, gateway, web, caddy** — there is **no separate worker image** (workers run the api image with a different CMD), so the ACR mirror set is api+gateway+web (+caddy for the VM edge, not needed on AKS ingress).
- `release.yml` is the tag-triggered **SLSA/SBOM/cosign-signed** path; `deploy/helm/lq-ai/NOTES.txt` already prints a `cosign verify --certificate-identity-regexp .../lq-ai ...` command — so signature verification is part of the intended supply chain.
- **Ownership mismatch to fix:** `images.yml:33` publishes under `IMAGE_OWNER: sarturko-maker`, but Helm `values.yaml:11` defaults `image.owner: legalquants`. The chart's default pulls a non-existent path; per-customer values must set `image.registry`/`image.owner` to the customer's ACR anyway, but the default should be corrected or documented.

**Two verified mirror mechanisms into the customer's ACR** (both server-side, no laptop pull):
- **`az acr import`** — server-side copy from `ghcr.io/<owner>/lq-ai-api@sha256:<digest>` into the customer ACR, importing by **digest** for reproducibility ([Learn: Import container images](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-import-images)). This is the recommended "seed the customer ACR with the exact pinned build" step, run once per release per customer.
- **ACR artifact cache (pull-through)** — a cache rule with upstream `ghcr.io/*`; `ghcr.io` is an explicitly supported upstream, available on **Basic/Standard/Premium** ([Learn: Artifact cache overview](https://learn.microsoft.com/en-us/azure/container-registry/artifact-cache-overview)). This lets AKS pull `myacr.azurecr.io/ghcr/<owner>/lq-ai-api:sha-...` on demand while GHCR remains the source of truth. Auth the rule with GHCR creds to avoid rate limits.

**Helm wiring:** point `image.registry`/`image.owner`/`image.tag` at the customer ACR + pinned `sha-<hex>` (or digest), set `imagePullPolicy: IfNotPresent`, and grant the AKS kubelet pull rights via **`az aks update --attach-acr`** (managed-identity ACR pull — reuses the keyless-MI posture of ADR-F072; no registry secret in-cluster). *(UNCONFIRMED here — I did not fetch the `--attach-acr` doc this pass; verify the exact command/role before the runbook.)*

**Air-gapped / private-registry (P-2, ADR-F070 lineage):** a customer with no egress to GHCR uses `az acr import` from a jump host (or a one-time offline `oras`/`docker save` transfer) to seed the ACR; nothing at runtime reaches GHCR. This is the natural extension of the restricted-egress private profile. The digest-pinned import path makes this deterministic. Foundry-models-only + gateway-sole-egress is unaffected: image supply and inference egress are separate planes.

---

### Honest UNCONFIRMED flags
- **`az aks update --attach-acr` exact syntax/role** for kubelet MI pull — not fetched this pass; verify against Learn before the runbook lands.
- **Whether ACR artifact-cache honours immutable digests transparently** for `:sha-<hex>` tags (tags are effectively immutable here since CI never re-pushes a sha tag, but cache TTL/refresh semantics for a moving `:main` were not verified) — prefer `az acr import` by **digest** for the pinned release; treat cache as a convenience for base layers.
- **Backward-compatibility of the 95-migration chain under a rolling update** — no expand/contract audit was done; the compatibility-window caveat above is a design assumption, not a verified property.

## §9 — Observability

**Verdict: MOSTLY READY, with one load-bearing code gap.** The fork already ships the two building blocks an AKS customer needs — a Prometheus `/metrics` endpoint on the two HTTP services and an opt-in OpenTelemetry OTLP tracer keyed off `OTEL_EXPORTER_OTLP_ENDPOINT` — and Azure Monitor's managed Prometheus, Container Insights and managed Grafana are all GA and scrape/ingest these with no code changes. The unfinished work is real but small: **(1) the arq workers (`arq-worker`, `ingest-worker`) never bootstrap OTel, so the highest-value domain spans — agent runs, `guarded_tool_call`, fan-out, ingest — export nothing even when the endpoint is set; (2) OTel export is traces-only (no OTLP metrics/logs signal); (3) the existing Helm chart has no worker/collabora workloads, no `livenessProbe`, and no Prometheus scrape annotations.** None of this touches the "we host nothing" or "gateway is sole egress" constraints — Azure Monitor ingest is a customer-subscription concern, and telemetry stays off by default.

### What the fork already emits (code-grounded)

Both FastAPI services wire a shared observability module at startup:

- **Prometheus** is always-on: a `/metrics` endpoint plus request-count and latency-histogram metrics, prefixed `lq_ai_api_*` (api) and `lq_ai_gateway_*` (gateway) so a single scrape across both is unambiguous. Route labels use the FastAPI **template** (`/api/v1/chats/{chat_id}`), never the raw path, so label cardinality stays bounded under hostile traffic (`api/app/observability.py:38-56,99-104`).
- **OpenTelemetry** is opt-in and off by default: `_maybe_init_otel` returns immediately unless one of `OTEL_EXPORTER_OTLP_ENDPOINT` / `_TRACES_ENDPOINT` / `_METRICS_ENDPOINT` is set — the "no telemetry by default" guarantee (`api/app/observability.py:170-218`). When enabled it installs a `TracerProvider` + `BatchSpanProcessor(OTLPSpanExporter())` and auto-instruments FastAPI + httpx.
- **Domain spans** wrap the high-value operations — `citation.verify` and its stages (`api/app/citation/verification.py:589-643`), `skill.execute` (`api/app/api/chats.py:1702-1705`), `autonomous.tool_call` (`api/app/autonomous/guard.py:172`), `playbook.execute` / `tabular.execute` — via a `traced` decorator whose attribute hygiene is explicit: "callers pass counts and types, never raw entity values — the anonymization promise must not leak via telemetry" (`api/app/observability_helpers.py:1-18`). This dovetails with the audit contract (counts/types/IDs, never raw values).
- **Log hygiene**: a `uvicorn.access` filter redacts the WOPI `access_token` query param before it reaches container logs (`api/app/observability.py:122-161`) — this matters because Container Insights ships stdout/stderr straight to a Log Analytics workspace.

`OTEL_EXPORTER_OTLP_ENDPOINT` is already plumbed through compose for api, gateway, and both bridges (`docker-compose.yml:137,219,640,682`) and documented in `.env.example:305-317`.

### Gaps to close for AKS (code-grounded)

| # | Gap | Evidence | Fix |
|---|---|---|---|
| G1 | **Workers never init OTel.** `install_observability` / `_maybe_init_otel` are called only from the two FastAPI apps (`api/app/main.py:231`, `gateway/app/main.py:372`). The arq worker `on_startup` installs the skill registry, checkpointer, store and stream broker but never the tracer provider (`api/app/workers/arq_setup.py:145-230`). Agent runs execute **in the worker** — so `autonomous.tool_call`, agent fan-out and ingest spans hit a no-op provider and export nothing, even with the endpoint set. | Add a `_maybe_init_otel(...)` call to each worker `on_startup` (arq_setup + document_pipeline). Small, additive, honours the same env gate. |
| G2 | **Traces only — no OTLP metrics/logs signal.** Only `OTLPSpanExporter` is wired; no `MeterProvider`/`OTLPMetricExporter` or `LoggerProvider` (`api/app/observability.py:198-211`). Metrics reach Azure only via the Prometheus `/metrics` scrape path; workers, having no HTTP server, expose **no** `/metrics` at all. | Accept the split (Prometheus for metrics, OTLP for traces) OR add a metrics reader. For workers, either add a tiny metrics HTTP listener or push worker metrics via OTLP. |
| G3 | **Helm chart is incomplete for observability.** `deploy/helm/lq-ai` covers only api/gateway/web + postgres/redis/minio; **no** arq-worker, ingest-worker or collabora Deployment. Only `readinessProbe` is set (api→`/ready`, gateway→`/ready`), **no `livenessProbe`**, and **no `prometheus.io/scrape` pod annotations** (`deploy/helm/lq-ai/templates/deployment-api.yaml:64-69`). | Add worker/collabora workloads; add liveness probes; add scrape annotations (see below). |
| G4 | **Dead Langfuse config.** `LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST` exist in `.env.example:319-323` but **no code consumes them** (zero references under `api/` or `gateway/`). | Either wire Langfuse (an LLM-trace backend behind the gateway) or delete the stale env keys. |

### Health probes → K8s probes (compose is the source of truth)

Every compose service already declares a healthcheck; these map cleanly to K8s probes. The api additionally distinguishes liveness from readiness in code: `/health` is pure liveness ("is the process alive?", 200 as soon as serving) while `/ready` gathers DB + Redis + MinIO + gateway reachability and returns 503 with per-dependency status when any is down — deliberately keeping `/health` at 200 so a transient dep outage doesn't get the pod killed (`api/app/main.py:253-310`). The gateway mirrors this with `/health` + `/ready` (`gateway/app/main.py:402,421`).

| Service | Compose healthcheck (`docker-compose.yml`) | K8s liveness | K8s readiness |
|---|---|---|---|
| api | urllib GET `:8000/health` (`:260`) | httpGet `/health` | httpGet `/ready` (DB+Redis+MinIO+gateway) |
| gateway | urllib GET `:8001/health` (`:171`) | httpGet `/health` | httpGet `/ready` (config loaded + providers) |
| web (nginx SPA) | wget `:8080/health` (`:485`) | httpGet `/health` | httpGet `/health` |
| arq-worker | `redis.ping()` exec (`:348-349`) | `exec` redis-ping | (no traffic — omit or same exec) |
| ingest-worker | `redis.ping()` exec (`:450-451`) | `exec` redis-ping | same |
| collabora | bash `/dev/tcp` → `GET /hosting/discovery`, assert 200, `start_period:60s` (`:548-557`) | `exec` tcp probe **or** httpGet `/hosting/discovery` on 9980 | same, generous `initialDelaySeconds` |
| postgres | `pg_isready` (`:37`) | `exec` pg_isready | `exec` pg_isready |
| redis | `redis-cli ping` (`:51`) | `exec` | `exec` |
| minio | curl `:9000/minio/health/live` (`:69`) | httpGet `/minio/health/live` | httpGet `/minio/health/ready` |

Workers have no HTTP surface, so their K8s probes stay `exec` (Redis reachability) exactly as compose does. Note collabora's `start_period: 60s` → K8s `startupProbe` (or a large `initialDelaySeconds`) to avoid restart storms during its slow WOPI warm-up.

### Azure ingestion story (Azure-verified)

The recommended, constraint-respecting shape: **Prometheus metrics via Azure Monitor managed Prometheus (annotation scrape); container stdout/stderr + syslog via Container Insights; OTLP traces via an in-cluster OpenTelemetry Collector; visualise in Azure Managed Grafana.** All of this lives in the customer's subscription — we host nothing.

- **Managed Prometheus (GA):** enabling the Azure Monitor metrics add-on deploys an `ama-metrics` agent that scrapes annotated pods. Turn on annotation scraping via the `ama-metrics-settings-configmap` / `ama-metrics-prometheus-config` ConfigMap, then annotate our api + gateway pods with `prometheus.io/scrape: "true"`, `prometheus.io/port: "8000"|"8001"`, `prometheus.io/path: "/metrics"` (defaults are port 9102 / path `/metrics`, so port must be set). Verified: Microsoft Learn "Customize scraping of Prometheus metrics … using ConfigMap." Data lands in an **Azure Monitor Workspace (AMW)**.
- **Container Insights (GA):** logs add-on ships container stdout/stderr to a **Log Analytics workspace** (`ContainerLogV2` schema, managed-identity auth recommended and default on recent CLI). **Syslog collection from AKS nodes is GA** (agent ≥ 3.1.16). Our access-token log scrub means WOPI tokens never reach that workspace.
- **Managed Grafana (GA):** links to the AMW; Azure auto-configures the Prometheus data source and imports Kubernetes dashboards. As of Sept 2025 the Azure portal also offers native "Dashboards with Grafana" on the AKS/AMW blade (portal experience marked **preview**) at no extra cost.
- **OTLP traces:** the clean path for our raw-OTel-SDK export is `OTEL_EXPORTER_OTLP_ENDPOINT` → an in-cluster **OpenTelemetry Collector**, which forwards to the customer's chosen backend (Application Insights via the collector's Azure Monitor exporter, or any OTLP backend). **Native OTLP ingestion directly into Azure Monitor is in PREVIEW** (Learn "OpenTelemetry ingestion options (preview)", updated 2026-05-30) across three mechanisms — AKS OTLP add-on, Azure Monitor Agent (VMs), and the OTel Collector sending directly to Azure Monitor cloud endpoints with Microsoft Entra auth. **Recommendation: target a customer-run OTel Collector**, not the native preview endpoint — it decouples us from a preview surface, works in restricted-egress/air-gapped tenants (ADR-F070), and lets the customer choose their backend. Our export is OTLP/HTTP, so any collector `otlphttp` receiver accepts it.

### Recommendation

Ship an **OBS slice** alongside the AKS chart work:

1. **Close G1 (the real gap):** call `_maybe_init_otel` from both worker `on_startup` hooks so agent/ingest/tool-call spans actually export. This is the single highest-value fix — the workers are where the interesting work happens.
2. **Chart (G3):** add arq-worker/ingest-worker/collabora workloads; add `livenessProbe` (`/health` for HTTP services, exec-redis for workers); add `prometheus.io/scrape` annotations on api + gateway pods with explicit `port`/`path`; give collabora a `startupProbe`.
3. **Deploy-time toggle:** leave `OTEL_EXPORTER_OTLP_ENDPOINT` unset by default (telemetry stays off); document pointing it at the in-cluster OTel Collector service DNS. Document the managed-Prometheus/Container-Insights/Grafana add-on enablement as customer landing-zone prerequisites (they're subscription-level, not our chart's job).
4. **Housekeeping:** decide Langfuse in-or-out (G4); document the traces-only nature of OTLP export (G2) so operators don't expect OTLP metrics.

Leave PTU/fine-tune observability out of scope, but note the gateway's existing per-model cost metrics are the natural seam for future model-spend dashboards.

## §10 — Horizontal-scale code audit

**Verdict: the agent-run data path is already multi-replica-clean; the failures are at the edges.** The
hard work of horizontal scale for the *interesting* part — long-running agent runs and their live UI —
was done incidentally by three fork slices (F1-S1 DB leasing, F025 Redis-pub/sub streaming, the arq
migration). Runs execute out-of-process on the arq worker, their durability is a DB-fenced lease, and
their SSE stream is relayed over Redis pub/sub with a complete Postgres DB-tail fallback — so **no sticky
sessions are required and any api replica can serve any run's stream.** What actually blocks scaling out
are three *operational* singletons that were written assuming one process per role: **(1) migrate-on-boot
with no lock, (2) the gateway's mutable config file, (3) arq cron jobs that fire once per worker replica**
— plus two sizing/soundness gaps (**worker concurrency/OOM, per-run brakes that reset on HITL resume**).

None of these is a rewrite. All are parameterisable in the Helm/AKS layer plus a handful of small code
seams, which fits the "Customer #2 = parameterised repeat" thesis.

### Execution topology (grounded, so the rest reads correctly)

- **api** and **gateway** each run a *single* uvicorn worker per container (`api/entrypoint.sh:38` →
  `uvicorn app.main:app` with no `--workers`; `gateway/Dockerfile:49` likewise). Horizontal scale ⇒ more
  pods, each a single Python process. Every in-process broker/holder/singleton below is therefore
  **per-pod**, and the question is only whether pods coordinate through Postgres/Redis or silently diverge.
- **Agent runs do NOT execute in the api.** `POST /agents/runs` writes the row and `enqueue_agent_run_job`
  puts it on the arq `arq:m3a6` queue (`api/app/api/agent_runs.py:470`, `api/app/workers/queue.py:331-368`);
  the **arq-worker** claims and drives it (`api/app/agents/runner.py:execute_agent_run`). Good — the heavy
  work is already out-of-process and independently scalable.

### Blocker summary (severity-ranked)

| ID | Blocker | Sev | Where |
|----|---------|-----|-------|
| **HS-1** | Migrate-on-boot races across replicas — **no advisory lock** (entrypoint comment is false) | blocks-scale | `api/entrypoint.sh:21-26`, `api/alembic/env.py` |
| **HS-2** | Gateway mutable config is a per-pod file + in-memory holder — replicas **diverge** on admin edits | blocks-scale | `gateway/app/config_writer.py:313`, `gateway/app/config_holder.py:106`, `docker-compose.yml:159-166` |
| **HS-3** | arq **cron jobs fire once per worker replica**; the autonomous scheduler double-spawns | blocks-scale | `api/app/workers/arq_setup.py:284-298`, `api/app/workers/autonomous_worker.py:333-408` |
| **HS-4** | arq-worker has **no `max_jobs` cap** (arq default 10) + ONNX models in-process → OOM; docker `mem_limit` doesn't carry to K8s | degrades-scale | `api/app/workers/arq_setup.py:301-329`, `api/app/workers/document_pipeline.py:307`, `docker-compose.yml:373` |
| **HS-5** | R4 token brake + fan-out quota are per-`_drive_agent` counters that **reset on every HITL resume**; no cross-run/tenant aggregate budget | degrades-scale | `api/app/agents/runner.py:365,505,509`, `api/app/agents/fan_out_middleware.py:62-65` |
| **HS-6** | Legacy playbook executor runs in-process via FastAPI `BackgroundTasks` — api-pinned, no lease/sweep, lost on pod eviction | watch (legacy) | `api/app/api/playbooks.py:728` |
| **HS-7** | Collabora (WOPI editor) is stateful — holds open docs in memory, capped 20 conns/10 docs — needs per-document affinity | watch | `docker-compose.yml:539-544` |

---

### (HS-1) Migrate-on-boot has no lock — the entrypoint comment is *false* · blocks-scale

`api/entrypoint.sh:21-26` runs `alembic upgrade head` on every api container start unless
`LQ_AI_SKIP_MIGRATIONS=1`. The script's own comment (`api/entrypoint.sh:11-14`) claims *"Alembic acquires
a Postgres advisory lock via its env.py setup, so multiple workers / replicas racing this step coordinate
correctly."* **This is not true.** `api/alembic/env.py` (the whole file, 100 lines) does a plain
`engine_from_config(... poolclass=NullPool)` → `context.run_migrations()` with **no `pg_advisory_lock`**;
a repo-wide grep for `advisory` returns zero hits in the migration path (`api/app/admin_bootstrap.py:13`
even notes it deliberately *avoids* advisory locks elsewhere). Under a K8s Deployment with `replicas: N`,
all N api pods boot concurrently and each runs the same DDL against one database. Alembic does not
`SELECT ... FOR UPDATE` the `alembic_version` row, so the losers hit `relation already exists` (or a
half-applied schema) → **CrashLoopBackOff on rollout**, exactly when you scale.

Today Compose hides this because only the `api` service migrates and the workers set
`LQ_AI_SKIP_MIGRATIONS=1` (`docker-compose.yml:305,399`) — a *single* migrator. That guarantee evaporates
the moment `api` itself has >1 replica.

**Fix (this is §8's design; §10 flags it as a scale blocker):** set `LQ_AI_SKIP_MIGRATIONS=1` on *all*
Deployments and run `alembic upgrade head` exactly once as a Helm `pre-install`/`pre-upgrade` **Job**
(or an argo/flux pre-sync hook) gated to complete before the api rollout. Azure Database for PostgreSQL
Flexible Server supports the `vector` extension the schema needs (extension binary name `vector`,
allowlisted via the `azure.extensions` server parameter, then `CREATE EXTENSION vector`) — verified on
Microsoft Learn — so the managed DB is a drop-in for the `pgvector/pgvector:pg16` image.

### (HS-2) Gateway config is a per-pod mutable file — replicas diverge · blocks-scale

The gateway's providers/aliases live in `gateway.yaml`, held in an in-process `MutableConfigHolder`
(`gateway/app/config_holder.py`). The admin alias-CRUD surface *writes the file and reloads the local
holder*: `config_writer.py` calls `holder.reload_from_disk()` at `:313, :355, :404, :496, :534`, and
`reload_from_disk` (`config_holder.py:106`) swaps only **this process's** snapshot. There is **no
cross-replica reload signal** — other gateway pods keep their stale config until they independently
receive SIGHUP or restart (`install_sighup_reload`, `config_holder.py:143`). Worse, the file itself lives
in the `gateway-config` **named volume** (`docker-compose.yml:159-166`), which on AKS maps to a PVC:
the default Azure Disk CSI driver is **ReadWriteOnce** (single-node attach, verified on Microsoft Learn),
so >1 gateway pod can't even share the file without switching to Azure Files (ReadWriteMany) — and even
then the in-memory divergence remains.

Consequence: with >1 gateway replica, a runtime provider/alias edit takes effect on one pod and routing
becomes non-deterministic across the fleet. The gateway is the sole egress + sole key-holder, so this is
not a cosmetic bug.

**Fix — and it aligns with how the fork already wants to run in production:** the Compose file itself
documents a *"hardened deployment"* posture (bind-mount an immutable `gateway.yaml:ro` and accept that the
admin write endpoints fail — `docker-compose.yml:150-155`). On AKS that becomes: ship `gateway.yaml` as an
**immutable ConfigMap**, source provider keys from **Azure Key Vault** via the Secrets Store CSI driver
(reuse ADR-F069 KV sourcing / ADR-F072 keyless managed identity), and **disable the runtime alias-CRUD
write surface**. Providers are near-static per customer, so an immutable config is the natural K8s shape
and lets the gateway scale to N replicas freely. Interim: pin `gateway` to `replicas: 1` (it's a thin
proxy; vertical scale carries it a long way).

### (HS-3) arq cron jobs fire once *per worker replica* — the autonomous scheduler double-spawns · blocks-scale

arq registers cron jobs on `WorkerSettings.cron_jobs`, and **every worker process runs the full cron
schedule**. `api/app/workers/arq_setup.py:284-298` registers `autonomous_idle_watchdog` (second=0),
`autonomous_schedule_dispatcher` (second=0), `agent_run_orphan_sweep` (second=30), `checkpoint_gc_job`
(04:30); the ingest worker adds `export_gc_job` and `hard_delete_due_users_job`
(`api/app/workers/document_pipeline.py:270-274`). Scale any arq worker to N replicas and each cron runs
N× per tick.

Most are **idempotent or fenced**, so duplication only wastes cycles: `agent_run_orphan_sweep` settles via
the fenced `settle_run` conditional UPDATE (`api/app/agents/lease.py:138`), and the GC/delete crons are
delete-if-present. **But `autonomous_schedule_dispatcher` is not idempotent.** Its core
(`api/app/workers/autonomous_worker.py:333-408`) does a plain
`SELECT ... WHERE next_run_at <= now` (**no `FOR UPDATE SKIP LOCKED`, no atomic claim**), then for each due
schedule creates an `AutonomousSession`, enqueues it, and advances `next_run_at`. With N replicas ticking
at `second=0`, all N read the same due rows and each spawns a session ⇒ **N duplicate autonomous runs per
schedule**, each burning real gateway spend, before any one advances `next_run_at`.

(The autonomous subsystem is legacy, but the cron is live and ships in the same worker as the deep-agent
path, so it fires the moment that worker is scaled.)

**Fix:** run scheduled/cron work as a **singleton** — either a dedicated single-replica "beat"
Deployment (the arq worker split so only the beat pod carries `cron_jobs`), a leader-election lease, or
K8s `CronJob` objects — and/or make the dispatcher claim atomically
(`UPDATE autonomous_schedules SET next_run_at=… WHERE id=… AND next_run_at<=now() RETURNING`). The
singleton-beat pattern is the cleanest and fixes every cron at once.

### (HS-4) arq-worker runs uncapped concurrency with ONNX models in-process → OOM · degrades-scale

The agent/tabular/autonomous worker (`arq_setup.WorkerSettings`, lines 301-329) sets `functions`,
`queue_name`, `allow_abort_jobs`, `job_timeout` — but **no `max_jobs`**, so it inherits arq's default of
10 concurrent jobs. The ingest worker, by contrast, explicitly caps it
(`document_pipeline.py:307,329` → `max_jobs = settings.lq_ai_ingest_worker_concurrency`, default 2). Agent
runs execute in this uncapped worker and each one loads the **in-process ONNX local embedder + cross-encoder
reranker** (process-global lazy singletons: `get_embedding_provider` in
`api/app/knowledge/embedding_provider.py:159`, `get_rerank_provider` in
`api/app/knowledge/rerank_provider.py:113`) and holds up to `FAN_OUT_QUOTA` subagents' context. Up to ~10
concurrent heavy runs per pod.

Today the only thing standing between that and a co-tenant OOM is a **docker `mem_limit`** the dev box
learned the hard way (`docker-compose.yml:373` arq-worker `mem_limit: 2500m`; `:282` ingest `3g`; the
comments recount the kernel OOM-killer taking down Postgres). **`mem_limit` does not translate to K8s** —
Compose `mem_limit`/`mem_reservation` are ignored by a Kubernetes manifest; you need
`resources.requests/limits`. Ship without them and a fan-out spike OOM-kills whatever else lands on the
node.

The provider singletons themselves are *correct* under multi-replica (each pod lazily loads its own ONNX
copy once and shares it across that pod's jobs — no shared-state assumption); this is purely a **sizing**
problem, not a fragmentation one.

**Fix:** set `max_jobs` on the agent worker; give the agent-run pod K8s `requests`/`limits` sized for the
resident ONNX footprint (~2.5 GiB embedder+reranker) **plus** per-concurrent-run headroom, at Guaranteed
or tight-Burstable QoS so it can't evict co-tenants; keep `FAN_OUT_QUOTA`. The agent worker and ingest
worker are already separate Compose services — keep them as separate Deployments with independent sizing
and HPAs (ingest scales on queue depth; agent-run scales on run concurrency).

### (HS-5) Per-run brakes reset on HITL resume; no aggregate budget · degrades-scale

The R4 token brake sums `usage_metadata.total_tokens` into a **local** `cumulative_tokens` that is
initialised to 0 at the top of each `_drive_agent` call (`api/app/agents/runner.py:365`, accumulated at
`:505`, halted at `:509`). `FanOutQuotaMiddleware` is likewise **one instance per run** with an in-process
`self._count` (`api/app/agents/fan_out_middleware.py:62-65`). Two consequences:

1. **Within one continuous run these do NOT fragment across replicas** — a run is pinned to a single arq
   worker invocation, so the in-memory counters are sound and *no shared store is needed for the single-run
   case*. This is the reassuring half of the answer to the brief's question (a).
2. **They reset across a HITL pause/resume boundary.** Resume is explicitly *"a NEW run, never a re-claim"*
   (`runner.py:978-979`); the resume endpoint re-enqueues a fresh run on arq
   (`api/app/api/agent_runs.py:1224`) which starts a new `execute_agent_run` → both counters restart at 0.
   A conversation that pauses and resumes K times therefore has an effective ceiling of
   `(K+1) × run_token_budget` and `(K+1) × fan_out_quota`. For a runaway-*backstop* (the default 8M token
   budget is described as exactly that) this is tolerable; as an **enterprise cost control** it is not.
3. There is **no cross-run / per-tenant / per-org aggregate** cost or concurrency ceiling anywhere — N
   concurrent runs across M worker replicas each get a fresh per-run budget, so aggregate spend is bounded
   only by these per-run caps × unbounded concurrency.

**Fix direction:** persist the running token total on the run/thread row and seed the accumulator from it
on resume (makes the brake per-conversation, not per-`_drive_agent`); if enterprise governance is
required, add an optional per-tenant aggregate budget in Postgres/Redis checked at run admission. Neither
is needed to *run* at scale — they're needed to *bill/govern* at scale.

### (HS-6) Legacy playbook executor is api-pinned via BackgroundTasks · watch (legacy)

`api/app/api/playbooks.py:728` runs the classic playbook executor with FastAPI
`background.add_task(_run_in_background, …)` — **inside the api process**. Unlike deep-agent runs (arq +
DB lease + orphan sweep), tabular, autonomous, and easy-playbook (all on arq via
`api/app/workers/queue.py`), this path is pinned to whichever api pod received the POST and is **silently
lost on pod eviction/rolling deploy**, with no lease or sweep to settle the row. This is legacy
(bugfix-only per CLAUDE.md), but on K8s rolling deploys kill in-flight background work routinely.
**Fix:** if the classic executor is deprecated, leave it; otherwise move it onto arq like its siblings, or
at minimum drain it on SIGTERM.

### (HS-7) Collabora WOPI editor is stateful · watch

`collabora` (coolwsd) holds open documents in memory and, with `home_mode.enable=true`, is **capped at 20
concurrent connections / 10 open documents** per instance (`docker-compose.yml:539-544`). WOPI editing
sessions are sticky to the instance holding the document, so horizontal scaling needs **per-document
session affinity** (route by WOPISrc) or a single replica. It's an MPL, server-side-only, internal-only
service (no host port), so a single adequately-sized replica is a legitimate starting posture; flag it so
nobody naively sets `replicas: 3` and gets split-brain edits.

---

### What is already multi-replica-clean (verified, so we don't "fix" what isn't broken)

- **SSE streaming is cross-process by design (F025).** The worker publishes live parts to Redis pub/sub
  (`RedisStreamBroker`, `api/app/agents/stream.py:498`, wired in `arq_setup.on_startup` at
  `arq_setup.py:204`); the api subscribes and relays them into its local broker (`RedisStreamBridge`,
  `stream.py:582`, wired in `api/app/main.py:161`); and the SSE endpoint additionally serves a **complete,
  animation-free stream from the settled `agent_run_steps` rows in Postgres** as the fallback
  (`_stream_run_events`, `agent_runs.py:603+`). Redis pub/sub broadcasts to *all* subscribers, so any api
  replica gets any run's live parts and the DB-tail covers state ⇒ **no sticky sessions needed.** The only
  hard requirement is a **single shared Redis** (see open decisions).
- **HITL resume is not replica-pinned.** The paused state lives in the langgraph checkpointer (Postgres),
  and resume re-enqueues onto arq (`agent_runs.py:1224`) — any worker claims and resumes it; nothing is
  held in the memory of the pod that served the pause.
- **Run durability is a DB-fenced lease.** `claim_run` / `heartbeat_run` / `settle_run` are conditional
  UPDATEs on `agent_runs` fenced by `lease_token` and gated on `status='running'`, all using the **database
  clock `now()`** as the single authority (`api/app/agents/lease.py`). Survives replica loss; at-most-once
  via arq `max_tries=1` + `claimed_by IS NULL`; the orphan sweep is the backstop. This is textbook-correct
  for K8s.
- **Auth is stateless-verifiable + Redis-backed limiting.** JWT with a shared `JWT_SECRET` env + DB-backed
  `UserSession` rows ⇒ any replica validates; the auth rate limiter is Redis-backed
  (`RedisRateLimitBackend`, `main.py:167`), not an in-memory counter.
- **The per-user flood brake is DB-backed, not in-memory.** `_MAX_CONCURRENT_RUNS_PER_USER=3` is enforced
  by a live `SELECT count(*) ... WHERE user_id AND status='running'` (`agent_runs.py:384-393`), shared
  across replicas. It is check-then-act (a user could momentarily exceed 3 across simultaneous POSTs on
  different replicas), but the per-thread partial unique index `uq_agent_runs_thread_running`
  (`agent_runs.py:458`) makes the one-running-run-per-thread rule genuinely race-proof.

---

### Recommendation — the horizontal-scale slice ladder

Do these before advertising >1 replica of any tier. Ordered by blast radius:

1. **HS-1 first — migrations off the boot path.** `LQ_AI_SKIP_MIGRATIONS=1` everywhere + a single Helm
   pre-upgrade migration Job. Also delete the false advisory-lock comment in `entrypoint.sh`. *(Unblocks
   api replicas.)*
2. **HS-3 — singleton "beat".** Split the arq worker so `cron_jobs` runs only on a `replicas: 1` beat
   Deployment (or convert crons to K8s CronJobs); belt-and-braces, make `autonomous_schedule_dispatcher`
   claim atomically. *(Unblocks arq-worker replicas.)*
3. **HS-2 — immutable gateway config.** ConfigMap + Key Vault CSI (reuse ADR-F069/F072), disable runtime
   alias writes; pin `gateway: replicas: 1` until then. *(Unblocks gateway replicas.)*
4. **HS-4 — worker sizing.** `max_jobs` on the agent worker + K8s `requests/limits`/QoS sized for the ONNX
   spike; separate agent-run and ingest Deployments with independent HPAs.
5. **HS-5 — durable brakes (only if enterprise cost governance is in scope).** Seed the token accumulator
   from a persisted per-thread total on resume; optional per-tenant aggregate budget.
6. **HS-6 / HS-7** — legacy playbook drain + collabora affinity: address when those features are in the
   customer's scope.

Data-plane mapping (single shared instances, all confirmed viable on Azure): **postgres → Azure Database
for PostgreSQL Flexible Server** with the `vector` extension allowlisted; **redis → Azure Cache for Redis,
non-clustered single-shard** (arq co-locates its queue keys and our pub/sub needs one logical instance);
**minio → Azure Blob** via the existing `S3_ENDPOINT_URL`/S3 creds (or a MinIO/Blob gateway). These stay
single *logical* services — the app already assumes one Postgres, one Redis, one object store — so they
map to managed Azure services, not per-pod StatefulSets.

### Open decisions for the maintainer

- **Gateway replicas vs. immutable config:** accept `gateway: replicas: 1` for v1, or invest in the
  ConfigMap+KV immutable posture now to allow N replicas? The runtime alias-CRUD surface has to go either
  way for >1 replica.
- **Redis tier:** confirm a **non-clustered** Azure Cache for Redis (arq is not cluster-aware; SSE pub/sub
  needs one broadcast domain).
- **Ingress for SSE:** which ingress (AGIC/App Gateway vs nginx) and codify buffering/timeout annotations
  for the `text/event-stream` endpoint.
- **Autonomous subsystem fate:** if legacy autonomous scheduling is being retired, HS-3's dispatcher risk
  disappears — confirm whether the cron should ship at all in the enterprise image.

### UNCONFIRMED / caveats

- arq's default `max_jobs` value (stated as 10) is arq library behavior at the pinned `arq>=0.26.3,<0.27`
  and was **not** re-verified against arq's own docs in this pass; the *code-confirmed* fact is the
  **asymmetry** — the agent worker sets no `max_jobs` while the ingest worker sets one — which is the
  load-bearing point regardless of the exact default.
- The precise failure mode of concurrent `alembic upgrade head` (hard crash vs. silent no-op on the loser)
  depends on Postgres locking under load; the **code fact** (no advisory lock in the migration path) is
  confirmed, and it is the standard well-known Alembic-concurrency hazard.

## Horizontal-scale blocker ledger — code-verified

Each §10 candidate blocker was handed to an independent adversarial verifier that read the cited source and confirmed or refuted the multi-replica failure. Verdicts drive the Phase-1 hardening slices.

| ID | Verdict | Defect | Evidence |
|---|---|---|---|
| **HS-1** | CONFIRMED | Every api replica runs 'alembic upgrade head' on boot with NO advisory lock; the entrypoint comment falsely claims env.py takes one. Under >1 api pod, concurrent DDL races → losers crash (set -e) → Cr | api/entrypoint.sh:2 `set -e`; entrypoint.sh:12-15 comment asserts "Alembic acquires a Postgres advisory lock via its env.py setup, so multiple workers / replicas racing this step coordinate correctly"; entrypoint.sh:21-27 runs `alembic upgr |
| **HS-2** | CONFIRMED | Gateway mutable config is a per-process in-memory snapshot backed by a single local YAML file; admin alias/provider-key/tier edits reload only the writing pod, with zero cross-replica propagation, so  | Mechanism is a per-process instance attribute, not a shared store. MutableConfigHolder holds `self._config` (gateway/app/config_holder.py:69); reads are a bare attribute fetch (config_holder.py:81-90); `reload_from_disk()` re-reads the LOCA |
| **HS-3** | REFUTED | arq cron jobs are NOT once-per-replica: with unique=True (the default on every registered cron) arq builds a deterministic Redis job_id and dedups the enqueue cluster-wide, so autonomous_schedule_disp | The dispatcher's plain SELECT (no FOR UPDATE SKIP LOCKED, no conditional UPDATE) is real: api/app/workers/autonomous_worker.py:333-344 selects due schedules, then :385-408 spawns an AutonomousSession, enqueues the job, and advances last_run |
| **HS-4** | CONFIRMED | The agent/tabular/autonomous arq worker (arq_setup.WorkerSettings) sets no max_jobs (runs at arq default 10) while loading process-global ONNX embedder+reranker singletons and holding fanned-out subag | arq_setup.WorkerSettings (api/app/workers/arq_setup.py:301-329) declares functions/queue_name/allow_abort_jobs/job_timeout/on_startup/on_shutdown but NO max_jobs; its _populate_class_attrs (lines 332-363) sets only redis_settings, cron_jobs |
| **HS-5** | PARTIAL | The R4 token brake and fan-out quota are genuinely per-run in-process counters that reset on every HITL resume (which is a brand-new run), and no aggregate/tenant budget exists — but this is a cost-go | Every factual assertion in the claim checks out against the code: 1. Token brake is a local variable, reset per _drive_agent call. api/app/agents/runner.py:365 `cumulative_tokens = 0` (function-local), accumulated at :505 `cumulative_tokens |
| **HS-6** | CONFIRMED | Classic playbook executor runs in-process via FastAPI BackgroundTasks (api-pinned), while every sibling run type (easy-playbook, tabular, deep-agent, autonomous) dispatches to arq; no orphan sweep exi | api/app/api/playbooks.py:728 — execute_playbook() calls background.add_task(_run_in_background, execution_id=execution.id, gateway=gateway) using the endpoint's BackgroundTasks param (line 669). _run_in_background (playbooks.py:950-982) ope |
| **HS-7** | CONFIRMED | Collabora coolwsd is inherently stateful (holds each open document in an in-memory jailed child; capped 20 conns/10 docs per instance under home_mode) and requires per-document WOPISrc affinity — scal | docker-compose.yml:533-544 documents that home_mode.enable=true (default via COLLABORA_HOME_MODE:-true, set in extra_params at line 544) caps coolwsd to 20 concurrent connections / 10 open documents per instance. docker-compose.yml:490-557  |

**Fix directions (per confirmed/partial blocker):**

- **HS-1** (CONFIRMED): Make migrations a single serialized step, never a per-pod boot action. (1) Set LQ_AI_SKIP_MIGRATIONS=1 on ALL K8s Deployments (api + both workers). (2) Run `alembic upgrade head` exactly once as a Helm pre-install/pre-upgrade hook Job (helm.sh/hook: pre-install,pre-upgrade; hook-weight ordering; backoffLimit low) gated to complete before the api Deployment rolls; the Job uses the same image/entrypoint override. (3) Delete/fix the false advisory-lock comment in entrypoint.sh:12-15. Defense-in-depth: wrap the upgrade in a real session-level `SELECT pg_advisory_lock(<const key>)` acquired in env.py's run_migrations_online() before context.run_migrations() and released after, so even accidental concurrent runners serialize instead of racing (advisory locks are the standard Alembic multi-runner pattern). Confirm Azure DB for PostgreSQL Flexible Server has `vector` allowlisted via the azure.extensions server parameter before the Job runs, else the CREATE EXTENSION migration fails.
- **HS-2** (CONFIRMED): Move gateway config off the mutable local file for multi-replica deploys. Preferred K8s posture: ship gateway.yaml as an immutable, read-only ConfigMap and source provider secrets from Azure Key Vault via the Secrets Store CSI driver (reuse ADR-F069/F072 managed-identity path), then disable the runtime alias/provider-key/tier write surface (return 405/409 when config is mounted :ro — the code already tolerates a read-only mount per docker-compose.yml:150-155). If runtime admin edits must stay, relocate the source of truth to a shared store (Postgres table or Redis) that all replicas read, and add a pub/sub invalidation (Redis pub/sub or Postgres LISTEN/NOTIFY) so every pod calls reload after a write instead of relying on the writing process's in-memory swap; the atomic-swap holder then becomes a per-pod cache fed from the shared store rather than a per-pod file. Interim, pin gateway replicas:1 (single-node RWO) and document it as a scale ceiling.
- **HS-3** — REFUTED: The claimed mechanism — "crons fire once per worker replica because they're on WorkerSettings.cron_jobs" — is the exact scenario arq's unique-cron feature was built to prevent, and it is on by default here. The missing FOR UPDATE SKIP LOCKED is therefore not load-bearing for horizontal scale: the di
- **HS-4** (CONFIRMED): 1) Add max_jobs to arq_setup.WorkerSettings mirroring document_pipeline's pattern: introduce a dedicated Settings field (e.g. lq_ai_agent_worker_concurrency, defaulted low — 2-4 — because each job holds subagent context) and set WorkerSettings.max_jobs in _populate_class_attrs (and expose it in a settings_dict for tests/docs). 2) On the agent-run K8s Deployment set resources.requests/limits sized for the ~2.5 GiB ONNX resident footprint + per-run headroom x max_jobs, at Guaranteed or tight-Burstable QoS — the container memory limit is the true K8s replacement for docker mem_limit and bounds OOM blast radius to the pod itself. 3) Keep agent-run and ingest-worker as separate Deployments with independent HPAs (agent scaled on run-concurrency / queue depth of the arq:m3a6 queue; ingest on its own queue depth). 4) Keep FAN_OUT_QUOTA, and note economy/generous budget profiles hardcode fan-out (budget.py) bypassing the env cap — size K8s limits for the generous worst case. 5) Strongly consider moving the ONNX embed/rerank into a shared inference Deployment (or the already-stubbed gateway /rerank door) so each agent pod does not carry the 2.5 GiB resident model, decoupling model memory from job concurrency and shrinking per-pod requests.
- **HS-5** (PARTIAL): Two independent fixes, both Postgres-backed (no in-memory state needed, works under any replica count):

1. Per-conversation continuity (multi-resume): persist the running token total and fan-out count on the run/thread row, and on resume seed the accumulator and the middleware count from the prior run's persisted values keyed by thread_id. Concretely: pass a `seed_tokens`/`seed_fan_out` into _drive_agent (initialize cumulative_tokens from it at runner.py:365) and into FanOutQuotaMiddleware(quota=..., start=prior_count). On a resume in agent_runs.py, SUM total_tokens over the thread's prior runs (already persisted at settle, runner.py:1041) and carry the fan-out count forward. This makes the brake a per-conversation ceiling instead of a per-run ceiling.

2. Enterprise cost governance (aggregate): add an optional per-tenant/org aggregate budget in Postgres, checked at run admission (in the create/resume endpoints before enqueue) via a single SUM(total_tokens) WHERE org_id=… AND settled_at >= window query, refusing admission past the ceiling. Postgres is the shared source of truth so this is correct across replicas; use a short advisory lock or a conditional UPDATE on a per-org counter row if you need strict rather than eventually-consistent enforcement under concurrent admissions. No Redis/pubsub/singleton-Job is required — this is a shared-store read at admission, not a cross-pod runtime coordination problem.
- **HS-6** (CONFIRMED): Preferred: migrate the classic playbook execute path onto arq exactly like its siblings — add a PLAYBOOK_EXECUTION_JOB_NAME + enqueue_playbook_execution_job helper in app/workers/queue.py, a worker consumer that calls run_playbook_execution, and replace background.add_task at playbooks.py:728 with the enqueue call (return the same 202). Then extend the arq_setup.py startup orphan sweep (ADR-F009 pattern) to also settle/re-enqueue stale PlaybookExecution rows so a lost pod is recovered. This gives durability, cross-replica safety, and cancel-addressability for free. Cheaper stopgap if the executor is being deprecated: add a SIGTERM drain that awaits in-flight background tasks before shutdown (bounded by the pod terminationGracePeriodSeconds) and/or a startup query that marks orphaned running rows as error so they don't hang forever — but this does not survive a hard eviction, so the arq migration is the correct K8s fix. If leaving legacy as-is, at minimum flag PlaybookExecution as non-durable in the deploy runbook so rolling deploys are drained/quiesced for that surface.
- **HS-7** (CONFIRMED): Run collabora as a single-replica Deployment: replicas: 1 with strategy type Recreate (never round-robin behind a plain Service). If concurrent editing volume outgrows one adequately-sized instance, do NOT bump replicas naively — instead front multiple coolwsd pods with WOPISrc-based session affinity so every session for a given document pins to the same pod: use an nginx-ingress consistent-hash on the WOPISrc query param (Collabora's documented multi-host reverse-proxy pattern), or a headless Service + hash-by-WOPISrc router. Keep home_mode off (COLLABORA_HOME_MODE=false) for production to drop the 20-conn/10-doc cap, per the deferred ADR-F047 self-build productionisation note. No api/ code change is required; this is a K8s manifest/topology constraint on the collabora service only.

## §11 — Cost model & phasing

This section prices a **single-customer, single-region AKS deployment into the customer's own Azure subscription** at a reference size of **~5–25 legal users**, then lays out a **five-phase ladder** where every phase is a runnable, testable milestone tied to the ADR it generalises. All figures are **infrastructure only**; Foundry token spend is usage-driven and priced separately (see below). Prices are Linux, pay-as-you-go (PAYG), East US-class regions, mid-2026; every Azure line is cited and honest-flagged where the source is an aggregator rather than the canonical Azure pricing page.

> **Framing verdict.** At this reference size the deployment is **not compute-bound — it is floor-cost-bound.** The AKS control plane, two small node pools, and managed Postgres/Redis/Blob land a Phase-1 MVP in the **~$900–1,200/month** band regardless of how few users are active. The single largest swing in the whole model is **Phase-2 egress control (Azure Firewall ≈ $913/mo fixed)** — and that line frequently **disappears** when the customer's landing zone already provides a hub firewall. Design so our footprint *reuses* the customer's platform services rather than duplicating them.

### Reference cluster shape (from §1)

Inference is external (Foundry via the gateway), so **no GPU** is needed. But the in-cluster CPU/memory load is real: `arq-worker` and `ingest-worker` load in-process ONNX models (the fastembed **bge** embedder + the **cross-encoder reranker**) plus **Docling/PyMuPDF/EasyOCR**. The dev compose caps these at `mem_limit: 2500m` (arq) and `3g` (ingest) — evidence the workers need genuine memory headroom, which drives a **memory-optimised (E-series) user node pool**.

| Pool | Purpose | Reference SKU | Nodes |
|---|---|---|---|
| System | CoreDNS, metrics-server, CSI drivers, ingress controller | `Standard_D2s_v5` (2 vCPU / 8 GB) | 2 (HA) |
| User | `api`, `gateway`, `web`, `arq-worker`, `ingest-worker`, `collabora` | `Standard_E4s_v5` (4 vCPU / **32 GB**) | 2 → autoscale 3 |

Two user nodes give the ONNX-heavy workers headroom while surviving a node loss; the memory-optimised E-series is chosen specifically so an ingest/rerank spike cannot OOM a co-tenant pod (the K8s realisation of the dev-box OOM shield).

### Phase-1 MVP monthly cost (single region, managed PaaS, basic ingress, Workload Identity)

| Component | SKU / basis | ~$/month | Source status |
|---|---|---|---|
| AKS control plane | Standard tier, $0.10/cluster-hr × 730 | **73** | confirmed |
| System node pool | 2 × D2s_v5 | **~140** | D2s_v5 exact price UNCONFIRMED (≈ half D4s_v5's $140) |
| User node pool | 2 × E4s_v5 @ ~$0.252/hr | **~368** | confirmed |
| PostgreSQL Flexible Server | D2ds_v5 (2 vCPU/8 GB) + 128 GB, HA off | **~135** | derived from D4ds_v5 confirmed price |
| Azure Cache for Redis | Standard C1 (1 GB, replicated) | **~90** | confirmed (range $70–100) |
| Blob Storage | Hot LRS, 100–250 GB + transactions | **~10** | confirmed ($0.018/GB) |
| Container Registry (ACR) | Standard | **~20** | UNCONFIRMED (commonly ~$0.667/day) |
| Ingress | Standard Load Balancer + managed NGINX | **~25** | UNCONFIRMED |
| Log Analytics / Container Insights | ingestion, usage-driven | **~50–150** | usage-driven, flag |
| **Phase-1 infra subtotal** | | **~$900–1,200/mo** | |

**Cost levers (apply before quoting a customer):**
- **Reserved Instances / Savings Plans** cut the node-pool + Postgres compute (the ~$640/mo majority) by **~30–40%** on a 1- or 3-year commit — the single biggest legitimate reduction.
- **Customer hub firewall / shared platform services.** Enterprise landing zones usually already run a hub Azure Firewall, Log Analytics workspace, and sometimes a shared App Gateway/Front Door. Where they do, Phase-2 egress cost drops toward $0 on *our* bill. Make firewall/ingress **parameters**, not baked-in resources.
- **Downsize the DB in tiny deployments.** A Burstable `B2ms` Flexible Server (~$60–70/mo) covers <10 users; reserve General Purpose for HA/throughput.

### Foundry token cost (separate, usage-driven — flag clearly)

Anthropic (Claude) + azure-openai run **pay-per-token through our gateway** and are **not part of infra spend**. They scale with lawyer activity (agent runs fan out subagents; the R4 brake defaults to a **2M-token** per-run ceiling — see code facts). Model this as a **separate usage line** in any customer quote; a heavy Deep-Agent day on a frontier model can rival a day of infra. No PTUs/fine-tunes are in scope, but the architecture must leave room for a customer to later pin a **Provisioned Throughput Unit** deployment behind the same gateway alias — a config change, not a re-architecture.

### The phased ladder

Each phase is an independently runnable, testable milestone. Incremental cost is **on top of the prior phase**.

| Phase | What lands | Realises ADR | Incremental $/mo | Milestone / test |
|---|---|---|---|---|
| **1 — MVP** | Single-region AKS; managed Postgres/Redis/Blob; **Workload Identity** (keyless pod→Foundry/KV/DB/Blob); migration as a Helm/Job hook (not app-boot); basic ingress | **F072** (keyless MI → federated Workload Identity), **F069** (KV via CSI driver), **F058** (self-host charter) | **baseline ~$900–1,200** | Clean stand-up from a values file; agent run completes end-to-end through the gateway; keyless token mints against Foundry |
| **2 — Private networking** | Private AKS API server; Private Endpoints for Postgres/KV/Blob/ACR; App Gateway WAF_v2 or Front Door + WAF; **Azure Firewall** egress deny-by-default; NetworkPolicy pinning gateway-as-sole-egress | **F070** (restricted-egress private profile) | **+$1,300–1,400** (Firewall ~$913 + WAF_v2 ~$323–400 + ~5 Private Endpoints ~$40) — **or ~+$400 if customer hub firewall is reused** | Egress blocked except gateway→Foundry; WAF fronts ingress; verify no pod can reach the internet directly |
| **3 — Entra SSO / SCIM** | Entra ID OIDC/SAML SSO + SCIM provisioning **replacing** local login/user-lifecycle; role map operator/admin/user/viewer → Entra groups | **F064** (RBAC role model) | **~+$0 infra** (uses the customer's existing Entra ID P1/P2) — **large engineering cost** | User signs in via corporate IdP; SCIM deprovision revokes access; roles map to F064 |
| **4 — CMK + residency hardening** | Customer-managed keys (customer Key Vault) on managed disks, Postgres, Blob; region/geo pinning of data + Foundry model deployments | **F069** (KV) extended; **F070** posture | **~+$5–25** (KV key + ops; Premium/HSM keys ~$1/key/mo) | Data at rest wraps under customer key; key rotation/revocation cuts access; deployment pinned to customer geo |
| **5 — Multi-region HA** | Second-region cluster; geo-replicated Postgres; GRS/RA-GRS Blob; Front Door global routing | (new HA ADR) | **~+80–100% of Phase-2 total** (~+$2,000–3,000) | Region failover keeps service; RPO/RTO measured |

**Phase-boundary rationale.** Phase 1 proves the keyless, managed-PaaS artifact stands up repeatably (the customer-#2-is-a-parameterised-repeat test). Phase 2 is where the ADR-F070 private profile becomes real on AKS and where the cost model's biggest variable lives — so it is deliberately its own milestone, not folded into MVP. Phase 3 (SSO/SCIM) is sized as its **own sizeable workstream** because it *replaces* local auth (§4); its Azure cost is ~$0 but its engineering cost is high, so it should not be gated behind the expensive networking phase — a customer may want SSO before full private networking. Phases 4–5 are enterprise-mandate add-ons that most reference-size customers will not need on day one.

### Recommendation

**Quote Phase-1 MVP at ~$1,000–1,200/month infra + separate usage-based Foundry tokens, with Reserved-Instance pricing offered as a ~30–40% reducer on commit.** Treat Phase-2 networking as the deployment's cost cliff and **parameterise the firewall/ingress/Log-Analytics resources so the customer's landing zone can supply them** — in a mature Azure enterprise this can halve or better the private-networking delta. Keep SSO/SCIM (Phase 3) decoupled from networking (Phase 2) in the ladder so it can ship on its own cadence. Foundry tokens stay a separate line item with headroom left for a future PTU deployment behind the same gateway alias.

### UNCONFIRMED / honest flags
- **AKS $0.10/cluster-hr** control-plane fee: the Learn tiers page confirms the *tier + SLA* but points to the pricing-details page for the number; the $0.10 figure is corroborated by multiple aggregators, not fetched from the canonical pricing page in this pass.
- **D2s_v5 system-node price (~$70/mo)** derived as roughly half the confirmed D4s_v5 ($140/mo) — not independently fetched.
- **Postgres D2ds_v5 (~$135/mo)** scaled down from the confirmed D4ds_v5 ($259.88/mo, from a Feb-2025 third-party comparison, not the live Azure page).
- **ACR Standard (~$20/mo)** and **basic ingress (~$25/mo)** are commonly-cited estimates, not fetched.
- **Log Analytics / Container Insights** ingestion is genuinely usage-driven; the $50–150 band is an estimate for reference-size telemetry.
- **Azure Cache for Redis Basic/Standard/Premium** tiers are being migrated to the newer **Azure Managed Redis** product — verify the exact SKU/price at deploy time as the legacy tiers phase out.

## Phased delivery ladder — enterprise deployment on AKS

The five phases follow the charter. **All five CONFIRMED §10 blockers are scheduled into Phase 1**, because Phase 1 is the earliest phase where the app runs on AKS Deployments and the enterprise proposition ("effortless scale") is made — a single-replica-only MVP would not honour it. HS-3 is refuted (a *preserve-invariant* item, not a fix); HS-5 is a conditional cost-governance slice.

---

### Phase 1 — MVP (single-region, managed PaaS, Workload Identity, basic ingress)
**What lands:** one private AKS cluster per customer (3 node pools, PDBs, Cluster Autoscaler); umbrella Helm chart lifting the compose env contract 1:1; managed Postgres Flexible Server (+`vector`) and Azure Cache for Redis; in-cluster MinIO; **keyless Foundry via Workload Identity** (gateway user-assigned MI, `Cognitive Services OpenAI User`); Key Vault CSI for residual secrets; **Helm pre-upgrade migration Job** replacing migrate-on-boot; basic internal ingress with SSE buffering disabled; OBS wiring (worker OTel init + probes + scrape annotations); local user login retained; managed-disk CMK (DES) as a cheap default.
**ADRs realised:** F073 tenancy-on-AKS, F074 data-plane default, F075 IaC choice, F076 AKS Workload Identity (generalises F069/F072), F077 migrate-as-Job, F080 gateway multi-replica config; F069 AKS addendum (disable in-process IMDS KV fetch).
**CONFIRMED §10 blockers fixed here:**
- **HS-1** — migrations off the boot path (the migration Job *is* the delivery mechanism; needed even single-replica).
- **HS-2** — gateway config as immutable ConfigMap + KV CSI, runtime alias/key write surface disabled on `:ro` mount (interim ceiling: pin gateway `replicas:1`; KV CSI is already in this phase).
- **HS-4** — agent-worker `max_jobs` + K8s requests/limits/QoS sized for the ~2.5 GiB ONNX footprint; agent-run and ingest as separate Deployments with independent HPAs.
- **HS-6** — classic playbook executor migrated onto arq + startup orphan sweep extended to `PlaybookExecution` (or explicitly retired — see open decisions).
- **HS-7** — collabora as a single-replica `Recreate` Deployment, `home_mode` off; multi-pod WOPISrc-affinity path documented, not enabled.
- **HS-3 (invariant, not a fix)** — codify single shared non-clustered Redis + single `queue_name` as a deployment invariant so arq's cluster-wide cron dedup keeps holding.
**Conditional:** **HS-5** (per-conversation token/fan-out seed on resume + optional per-tenant aggregate budget) only if enterprise cost governance is in scope for v1.

### Phase 2 — Private networking (ADR-F070 on AKS)
**What lands:** private cluster via API Server VNet Integration (create-time); Private Endpoints for Postgres/Redis/KV/ACR(Premium)/Foundry with public access disabled; `outboundType=UDR` → Azure Firewall deny-by-default using the F070 §8.4 egress inventory; Azure CNI Powered by Cilium default-deny NetworkPolicy (only the gateway pod reaches model endpoints); AGC + Azure WAF internal ingress with Caddy retained in-cluster; GitOps upgraded to the managed `microsoft.flux` extension; air-gapped ACR seed; CloudNativePG in-cluster data-plane overlay for restricted-egress customers.
**ADRs realised:** F078 gateway-sole-egress-on-AKS network contract (NetworkPolicy + Firewall, F070 on AKS).
**§10 dependencies:** no new blockers, but this is where **HS-2 must be fully resolved** (shared-store config or accepted `replicas:1` ceiling) if gateway N-replica is needed, and where the restricted-egress OTel-Collector path (§9) is confirmed reachable.

### Phase 3 — Entra SSO / SCIM
**What lands:** Entra OIDC/SAML SSO verified at the single `get_current_user` seam; SPA OIDC rebuild; hosted SCIM 2.0 endpoint with role↔group mapping and auto-deprovision; MFA handed off to Conditional Access; local lifecycle endpoints gated/retired (or kept as break-glass); operator provisioned out-of-band to preserve the F064 fence.
**ADRs realised:** F079 end-user identity / SSO+SCIM model.
**§10 dependencies:** none.

### Phase 4 — CMK + data residency
**What lands:** etcd KMS encryption opt-in (customer KEK, with the KEK-deletion → cluster-recreation obligation made explicit); PaaS per-service CMK (Flexible Server + Blob); region + agent-model-family as per-customer parameters; the Claude-EU-data-zone decision realised per customer. (Managed-disk CMK already shipped in Phase 1 as the baseline default.)
**ADRs realised:** CMK/data-residency ADR if the etcd-KMS + PaaS-CMK combination is adopted as a supported profile.
**§10 dependencies:** none.

### Phase 5 — Multi-region HA
**What lands:** multi-region data replication (geo-redundant Postgres, RA-GRS Blob), global traffic routing (Front Door Premium), zone-redundant HA on every managed service, and the final removal of the gateway `replicas:1` ceiling.
**ADRs realised:** multi-region-HA ADR (future).
**§10 dependencies:** this is where full multi-replica of *every* tier — including the gateway — is mandatory, so **HS-2's shared-store resolution and HS-5's aggregate governance become load-bearing here** if not already delivered.

## Consolidated open decisions for the maintainer

> **STATUS 2026-07-10:** the maintainer has DECIDED the headline items — see **§ Maintainer rulings** at the
> top. **D4** (SSO optional overlay, local login retained), **D10** (reuse customer firewall), **D13** (fix
> playbooks), and the defaults **D1/D2/D6** are settled; **D7 (residency) is REMOVED** (the customer deploys
> models + picks the zone — not ours to solve). The remaining decisions (D3 phasing, D5 tenancy, D8/D9/D11/
> D12/D14) stay open. The entries below are kept for rationale.

### D1. Data-plane default: managed PaaS vs in-cluster stateful cores (charter i)
- **Options:** (A) Azure DB for PostgreSQL Flexible Server + Azure Cache for Redis by default, in-cluster CloudNativePG/redis overlay for air-gapped/ADR-F070; (B) in-cluster pgvector + redis StatefulSets everywhere (customer owns DB ops); object storage is a fixed exception either way (in-cluster MinIO default, Blob as upgrade — Blob has no S3 API).
- **Recommendation:** Managed-by-default (A): Flexible Server + Azure Cache is the enterprise-buyer expectation (Azure owns patching/HA/backup) and unlocks per-service CMK; ship CloudNativePG as the same-DATABASE_URL overlay for restricted-egress. Confirm the first target customer's landing zone permits a PaaS DB vs mandates in-VNet/in-cluster.

### D2. IaC language: Terraform vs Bicep (charter ii)
- **Options:** (A) Terraform + Azure Verified Modules (state must be hosted — bootstrap storage account in the customer's subscription); (B) Bicep (stateless, no state-hosting problem, AVM parity, Microsoft-partner-native).
- **Recommendation:** Terraform + AVM as the shipped default (mature multi-cloud ecosystem, single root module + per-customer tfvars), but keep the infra/app boundary clean so a Bicep root stays a drop-in for Bicep-mandated customers. Confirm customer-subscription-hosted Terraform state is acceptable.

### D3. Security-control phasing order (charter iii)
- **Options:** The controls are: service identity (Workload Identity, §4/§6), private networking (ADR-F070, §5), CMK/residency (§6/§4), and end-user SSO/SCIM (§4). Order options: (A) service-identity → private-net → SSO → CMK; (B) service-identity + SSO both in cut 1; (C) private-net earlier if the design partner mandates it.
- **Recommendation:** Service identity (Workload Identity + KV CSI) in Phase 1, private networking Phase 2, SSO/SCIM Phase 3, CMK/residency Phase 4 — this front-loads the keyless, sole-egress-strengthening control at lowest cost and defers the ~3x networking cost cliff. Re-order only if a design-partner security review gates go-live on private networking or SSO-only.

### D4. Entra SSO/SCIM in the first cut vs fast-follow (charter iv)
- **Options:** (A) service identity in cut 1, keep local login for users, land SSO then SCIM as the next milestone; (B) OIDC SSO in cut 1 (required if the partner mandates 'SSO only, no local passwords'); SCIM JIT-provision-on-login vs hosted SCIM 2.0 before go-live.
- **Recommendation:** SSO-first / SCIM fast-follow (A) unless the design partner's security review gates on no-local-passwords. Prefer hosted SCIM 2.0 over JIT for the enterprise auto-deprovision story, but it is net-new hosted API surface — sequence it after SSO. Keep the operator OUT of the tenant SCIM group flow so an IdP group misconfig cannot mint a platform operator (F064).

### D5. Tenancy model on AKS
- **Options:** (A) one dedicated private AKS cluster per customer in the customer's own subscription; (B) shared multi-tenant AKS with namespace/network isolation.
- **Recommendation:** Cluster-per-customer (A) — matches 'we host nothing', gives the strongest isolation/residency/billing boundary, and is what the distributable is built around. This is hard to reverse, so ratify it in ADR-F073.

### D6. Road to managed object storage (Azure Blob)
- **Options:** (A) in-cluster MinIO as the only supported store; (B) S3Proxy sidecar in front of Blob (zero app-code, extra hop — verify multipart + presigned-URL fidelity); (C) native Azure Blob backend behind a storage Protocol (real slice: presigned GET→SAS, copy_object→server-side copy, multipart→Block Blob staging).
- **Recommendation:** Ship MinIO in-cluster as the default (byte-clean, honours the AGPL server-side posture) and offer (C) native Blob as the enterprise upgrade for customers who want Entra/Workload-Identity storage auth and one fewer stateful pod. Treat (B) S3Proxy as an interim if a customer needs Blob before (C) is funded. Maintainer picks the default enterprise posture.

### D7. Claude-on-Foundry EU data residency — ❌ REMOVED (not ours to solve)
> **Maintainer ruling:** the customer deploys the models in their own Azure and picks the region/zone at
> deploy time; our gateway points at that endpoint. Region + model are per-customer parameters (alias→
> deployment indirection already supports this). Residency is the customer's deploy-time responsibility —
> nothing for us to build. The options below are moot.
- **Options:** (a) run agents on GPT-class in an EU region and reserve Claude for non-residency work; (b) accept Sweden Central under a DPA covering Anthropic processing; (c) treat Claude as unavailable until Anthropic ships Foundry EU (~2026).
- **Recommendation:** This is a legal/product call per customer, not an engineering default — surface it explicitly. Keep region + agent-model-family as per-customer parameters and the alias→deployment indirection intact so the choice is a config change, not a code change.

### D8. Gateway multi-replica config posture (HS-2)
- **Options:** (A) accept gateway replicas:1 for v1 (thin proxy, scales vertically) with the runtime alias/key write surface disabled; (B) invest now in immutable ConfigMap + KV CSI (read-only, admin edits disabled) to allow N replicas; (C) relocate config to a shared store (Postgres/Redis) + pub/sub invalidation to keep runtime admin edits at N replicas.
- **Recommendation:** (B) immutable ConfigMap + KV CSI in Phase 1 with the write surface disabled on the :ro mount — it reuses the F069/F072 MI path and lifts the replica ceiling cheaply. Defer (C) shared-store-with-pubsub until runtime admin edits at scale are actually required. Either way the alias-CRUD write surface must be disabled for >1 replica, and a controlled path to add per-customer provider entries must remain.

### D9. Default ingress on AKS
- **Options:** (A) Application Gateway for Containers + Azure WAF (regional, Gateway-API-native, fits residency-bound single-region customers); (B) Front Door Premium + WAF + Private Link (global edge, DDoS, but forbids mixed public/private origin groups, more moving parts).
- **Recommendation:** AGC + WAF as the default, Front Door as an option for customers needing a global edge — but gate the default on confirming AGC-WAF GA/feature-parity (flagged UNCONFIRMED in §5.2). Codify SSE annotations (disable response buffering, long read timeouts) on the chosen ingress regardless.

### D10. Azure Firewall ownership (biggest Phase-2 cost swing)
- **Options:** (A) the Phase-2 profile deploys its own Azure Firewall (~$913/mo fixed); (B) require and reuse the customer's landing-zone hub firewall.
- **Recommendation:** Parameterise firewall/ingress/Log-Analytics as own-resource vs reuse-customer-platform so a customer whose landing zone already provides a hub firewall pays little-to-nothing extra. Default to reuse-customer-hub where present; own-resource only when the customer has no hub. This single decision roughly triples-or-not the Phase-2 bill.

### D11. Federated-token exchange: stdlib vs azure-identity SDK (re-decides F069/F072)
- **Options:** (A) hold the stdlib-only line and add a federated-token-file/client-assertion path by hand (one urllib POST); (B) adopt azure-identity's WorkloadIdentityCredential / DefaultAzureCredential (Microsoft's documented path, but a new SBOM dependency F069/F072 previously declined).
- **Recommendation:** Option A (stdlib) for consistency with F069/F072 and to avoid the SBOM/supply-chain surface — the federated exchange is one more urllib POST than the IMDS path. But the exchange is heavier than the two VM IMDS calls that justified the original SDK rejection, so re-decide explicitly in an F072 ADR addendum with maintainer sign-off.

### D12. Enterprise aggregate cost governance in scope for v1 (HS-5)
- **Options:** (A) per-run runaway backstop (R4 token brake) is sufficient for v1; (B) add a per-tenant/org aggregate spend ceiling checked at run admission, plus per-conversation continuity so multi-resume does not multiply the per-run ceiling.
- **Recommendation:** Determine from the design partner's contract model. If usage is billed directly on the customer's own Foundry subscription, (A) is likely sufficient for v1 and HS-5 defers. If we meter/cap, ship (B) as Postgres-backed (SUM at admission + seed-on-resume) — it is correct across replicas with no Redis/pubsub/singleton needed. Do not build it speculatively.

### D13. Classic playbook executor fate (HS-6)
- **Options:** (A) migrate the classic executor onto arq (enqueue + worker consumer + orphan sweep) for durability/cross-replica safety; (B) it is legacy and being deprecated — add only a SIGTERM drain + startup orphan-mark stopgap; (C) leave as-is and flag PlaybookExecution non-durable in the runbook (drain/quiesce on rolling deploy).
- **Recommendation:** Confirm whether the classic executor ships in the enterprise image at all. If it does, migrate onto arq (A) — it is the only option that survives hard eviction and gives cancel-addressability for free. If it is being retired, drop it from the image rather than shipping a known-non-durable run surface.

### D14. Log Analytics / Container Insights workspace ownership
- **Options:** (A) ship our own Azure Monitor workspace per deployment (usage cost lands on our line); (B) emit to the customer's existing central workspace (ties into §9 observability and 'we host nothing').
- **Recommendation:** Emit to the customer's workspace (B) by default — consistent with 'we host nothing' and keeps the cost on the customer's subscription; provision our own only when the customer's landing zone has none. Document whether the deploy tooling provisions the Azure Monitor Workspace + Data Collection Rules or assumes the landing zone already has the managed Prometheus/Container Insights/Grafana add-ons enabled.

## Proposed slice ladder — MILESTONES.md entries (K8S enterprise deployment)

Vertical, end-to-end, testable slices (each ≤2–3 days, one PR), grouped by phase. **Each CONFIRMED §10 blocker is an early Phase-1 hardening slice** (marked ⚠︎).

### Phase 1 — MVP (single-region, managed PaaS, Workload Identity, basic ingress)
- **K8S-1** — Umbrella Helm chart: lift `docker-compose.prod.yml`'s parameterised env contract 1:1 into values; api/gateway/web/collabora + arq-worker + ingest-worker as Deployments, PDB on each.
- **K8S-2 ⚠︎(HS-1)** — Migrations off the boot path: Helm pre-install/pre-upgrade hook Job (`alembic upgrade head`, gated), `LQ_AI_SKIP_MIGRATIONS=1` on api + both workers, delete the false advisory-lock comment, add a real `pg_advisory_lock` in `env.py` as defense-in-depth.
- **K8S-3** — Terraform root module + Azure Verified Modules + per-customer tfvars; bootstrap Terraform state storage account created inside the customer's subscription.
- **K8S-4** — `customer.values.yaml` single manifest + thin adapter projecting it into both tfvars and Helm values; every field traces to an existing env var.
- **K8S-5** — Keyless Foundry: SDK-free `WorkloadIdentityTokenProvider` in the gateway selected by `AZURE_FEDERATED_TOKEN_FILE` (append `/.default`), per-deployment user-assigned MI federated to the gateway ServiceAccount, `Cognitive Services OpenAI User` role.
- **K8S-6** — Key Vault CSI + Workload Identity for residual secrets (gateway key, JWT, Fernet master, non-Azure provider keys); tmpfs file mounts, sync-to-Secret only where the app can't read a file; disable the gateway in-process IMDS KV fetch on AKS.
- **K8S-7 ⚠︎(HS-2)** — Gateway config as immutable read-only ConfigMap + KV CSI; return 405/409 on runtime alias/provider-key/tier writes when mounted `:ro`; document the interim `replicas:1` ceiling.
- **K8S-8 ⚠︎(HS-4)** — Agent-worker `max_jobs` (new `lq_ai_agent_worker_concurrency`, default 2–4) + K8s requests/limits/QoS sized for the ~2.5 GiB ONNX footprint × max_jobs; agent-run and ingest as separate Deployments with independent HPAs.
- **K8S-9 ⚠︎(HS-7)** — Collabora single-replica Deployment, `strategy: Recreate`, `home_mode` off for production; document (do not enable) the WOPISrc-consistent-hash multi-pod path.
- **K8S-10 ⚠︎(HS-6)** — Migrate the classic playbook executor onto arq (`enqueue_playbook_execution_job` + worker consumer) and extend the F009 startup orphan sweep to `PlaybookExecution`. **DECIDED (maintainer): FIX — playbooks ship in the enterprise product and are widely used; do NOT drop.**
- **K8S-11 ⚠︎(HS-3 invariant)** — Codify single shared non-clustered Azure Cache for Redis + single `queue_name` as an explicit deployment invariant (preserves arq's cluster-wide cron dedup); atomic per-schedule advance (`UPDATE … WHERE next_run_at <= now RETURNING id`) as belt-and-braces.
- **K8S-12** — OBS slice: call `_maybe_init_otel` from both worker `on_startup` hooks; liveness/startup probes for HTTP services, workers, and collabora's warm-up; `prometheus.io/scrape` annotations on api/gateway; in-cluster OTel Collector target, telemetry opt-in.
- **K8S-13** — SSE-on-AKS ingress hardening: basic internal ingress with response buffering disabled + long read timeouts for `text/event-stream` (app already sends `x-accel-buffering: no`).
- **K8S-14** — ACR supply chain: mirror GHCR → customer ACR by immutable digest (`az acr import`), MI-based kubelet pull (`--attach-acr`, F072 lineage), SHA-pinned values; fix the `image.owner` default (legalquants → sarturko-maker).
- **K8S-15 (conditional, HS-5)** — Per-conversation token/fan-out seed on resume (SUM prior-run `total_tokens` by thread) + optional per-tenant aggregate budget checked at run admission — only if enterprise cost governance is in scope for v1.

### Phase 2 — Private networking (ADR-F070 on AKS)
- **K8S-16** — Private cluster via API Server VNet Integration, provisioned at create time.
- **K8S-17** — Private Endpoints for Postgres/Redis/KV/ACR(Premium)/Foundry; public network access disabled.
- **K8S-18** — `outboundType=UDR` → Azure Firewall deny-by-default, seeded from the ADR-F070 §8.4 egress FQDN allowlist; handle the ingest-worker one-time HuggingFace model pull (pre-bake / PVC-seed / maintenance-window rule).
- **K8S-19** — Azure CNI Powered by Cilium default-deny egress NetworkPolicy: only the gateway pod may reach model endpoints (belt-and-suspenders beneath ADR-F010).
- **K8S-20** — AGC + Azure WAF internal ingress; retain Caddy in-cluster as the tested WOPI/internal/metrics deny upstream.
- **K8S-21** — GitOps via the managed `microsoft.flux` extension; air-gapped ACR seed path.
- **K8S-22** — CloudNativePG in-cluster data-plane overlay (same `DATABASE_URL` contract) for restricted-egress/cost-floor customers.

### Phase 3 — Entra SSO / SCIM
- **K8S-23** — Entra OIDC/SAML SSO at the single `get_current_user` seam + SPA OIDC rebuild (331 downstream call sites untouched).
- **K8S-24** — Hosted SCIM 2.0 endpoint + role↔group mapping + auto-deprovision; operator kept out of the tenant SCIM group (F064 fence).
- **K8S-25** — Make local login **optionally disable-able per deployment** (config flag) — RETAIN the local lifecycle substrate (login/refresh/MFA/invite/reset); a customer on SSO-only turns local login off, MFA handed to Entra Conditional Access. Never removes the substrate (other customers use it).

### Phase 4 — CMK + data residency
- **K8S-26** — Managed-disk CMK via Disk Encryption Set (baseline default; may pull forward to Phase 1).
- **K8S-27** — etcd KMS encryption opt-in with a customer KEK; make the KEK-deletion → cluster-recreation operational obligation explicit.
- **K8S-28** — PaaS per-service CMK (Flexible Server + Blob) + region/model-family residency parameters; realise the Claude-EU decision per customer.

### Phase 5 — Multi-region HA
- **K8S-29** — Multi-region data replication (geo-redundant Postgres, RA-GRS Blob) + full zone-redundant HA.
- **K8S-30** — Global traffic routing (Front Door) + final removal of the gateway `replicas:1` ceiling (HS-2 shared-store resolution) + HS-5 aggregate governance if not already shipped.

## Recommended ADRs (F-series drafts to write)

| Proposed | Title | Decision | Why hard to reverse |
|---|---|---|---|
| **F073** | Tenancy model on AKS — one dedicated private cluster per customer | Deploy one private AKS cluster per customer into the customer's own subscription/VNet (we host nothing), rather than a shared multi-tenant cluster. | It fixes the isolation, residency, billing, and network boundary for every deployment. Moving from cluster-per-customer to shared multi-tenancy (or back) re-architects the whole distributable — namesp |
| **F074** | Data-plane default on AKS — managed PaaS cores with an in-cluster overlay | Default the stateful cores to managed PaaS (Azure DB for PostgreSQL Flexible Server + pgvector, Azure Cache for Redis) with a CloudNativePG/redis in-cluster overlay on the same DATABASE_URL contract for air-gapped/ADR-F0 | It sets the storage/connection contract, CMK reach (per-service CMK only exists on the PaaS route), and who owns patching/HA/backup. The object-storage decision in particular commits the aioboto3 laye |
| **F075** | Infrastructure-as-Code choice — Terraform + Azure Verified Modules as primary | Adopt Terraform (azurerm) + AVM as the primary landing-zone IaC with state in a customer-subscription bootstrap storage account, keeping the infra/app boundary clean enough that a Bicep root stays a drop-in alternative. | The IaC language dictates state hosting, the module ecosystem, and the per-customer delivery pipeline. Migrating a landing zone from Terraform to Bicep (or vice-versa) after customers are live is effe |
| **F076** | AKS Workload Identity keyless service identity — generalisation of F069/F072 | Generalise the F069/F072 keyless posture to AKS by adding a Workload-Identity (federated ServiceAccount token / client-assertion) branch alongside the existing IMDS path in the gateway token/KV providers, federating a pe | It re-decides the token-provider seam and the secret-injection mechanism across gateway/api/both workers, and re-opens the F069/F072 SBOM/supply-chain call (adopting azure-identity is hard to undo onc |
| **F077** | Migrate-as-Job — schema migrations off the boot path | Replace per-pod migrate-on-boot with a single gated Helm pre-install/pre-upgrade hook Job; set LQ_AI_SKIP_MIGRATIONS=1 on api and both workers; the release fails if the Job fails. Optionally add a real pg_advisory_lock i | It changes the release-gating and rollout-ordering contract (Helm blocks on migration before Deployments roll) and the entrypoint's boot semantics — the K8s twin of the deploy.sh dedicated migrate ste |
| **F078** | Gateway-sole-egress-on-AKS network contract — NetworkPolicy + Firewall (ADR-F070 on AKS) | Realise the fully-private posture as the enterprise default: private API server (create-time), Private Endpoints with public access disabled, UDR → Azure Firewall deny-by-default with the F070 §8.4 allowlist, and a Ciliu | Private API Server VNet Integration is provisioned at cluster-create time — enabling it day-2 forces a cluster restart — so the network posture is baked into provisioning. The two-layer gateway-sole-e |
| **F079** | End-user identity on AKS — Entra SSO + SCIM provisioning model | Adopt Entra OIDC/SAML SSO verified at the single get_current_user seam, SSO-first with hosted SCIM 2.0 as a fast-follow, MFA handed to Conditional Access, **local login RETAINED (SSO is an optional per-customer overlay at `get_current_user`; SSO-only disables local login by config, never removes it)**, and the ADR-F064 operato | It retires or gates the entire local login/invite/MFA/password lifecycle, rebuilds the SPA auth flow, and moves the source of truth for users to the customer's IdP — an identity-model migration that c |
| **F080** | Gateway multi-replica config model — immutable ConfigMap + KV CSI (supersedes the 0010 runtime write surface on AKS) | On the AKS profile, ship gateway.yaml as an immutable read-only ConfigMap with provider secrets via Key Vault CSI and disable the runtime alias/provider-key/tier write surface (405/409 on :ro mount); relocate to a shared | It is the HS-2 fix and it changes the admin config contract established by ADR-0010 (hot-reload of a local mutable file): the per-process in-memory snapshot cannot propagate across replicas, and an RW |

## Cited sources

- https://arq-docs.helpmanual.io/ (some claims UNCONFIRMED)
- https://azure.github.io/Azure-Verified-Modules/
- https://azure.github.io/redis-on-azure-workshop/labs/03-pub-sub-in-azure-cache-for-redis.html
- https://azure.microsoft.com/en-us/pricing/details/azure-firewall/
- https://azure.microsoft.com/en-us/pricing/details/cache/
- https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/
- https://azure.microsoft.com/en-us/pricing/details/private-link/
- https://azure.microsoft.com/en-us/pricing/details/storage/blobs/
- https://blog.aks.azure.com/2025/09/18/azure-monitor-grafana-dashboards-portal
- https://devblogs.microsoft.com/ise/consuming-azure-openai-resources-in-aks-with-workload-identities/
- https://developer.hashicorp.com/terraform/language/backend/azurerm
- https://github.com/Azure/AKS-Landing-Zone-Accelerator
- https://helm.sh/docs/topics/charts_hooks/
- https://instances.vantage.sh/azure/vm/d4s-v5
- https://instances.vantage.sh/azure/vm/e4s-v5
- https://learn.microsoft.com/en-us/answers/questions/1183760/s3-api-support-over-azure-blob-storage
- https://learn.microsoft.com/en-us/answers/questions/5530146/pgvector-0-8-0-hnsw-on-azure-postgresql-flexible-s
- https://learn.microsoft.com/en-us/answers/questions/5845198/application-gateway-for-containers-internal-load-b
- https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/how-to/configure-content-filters
- https://learn.microsoft.com/en-us/azure/aks/api-server-vnet-integration
- https://learn.microsoft.com/en-us/azure/aks/automatic-pod-disruption-budget-management
- https://learn.microsoft.com/en-us/azure/aks/azure-cni-powered-by-cilium
- https://learn.microsoft.com/en-us/azure/aks/azure-disk-customer-managed-keys
- https://learn.microsoft.com/en-us/azure/aks/best-practices-performance-scale-large
- https://learn.microsoft.com/en-us/azure/aks/concepts-scale (some claims UNCONFIRMED)
- https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-driver
- https://learn.microsoft.com/en-us/azure/aks/csi-secrets-store-identity-access
- https://learn.microsoft.com/en-us/azure/aks/deploy-cluster-terraform-verified-module
- https://learn.microsoft.com/en-us/azure/aks/free-standard-pricing-tiers
- https://learn.microsoft.com/en-us/azure/aks/kms-data-encryption
- https://learn.microsoft.com/en-us/azure/aks/limit-egress-traffic
- https://learn.microsoft.com/en-us/azure/aks/outbound-rules-control-egress
- https://learn.microsoft.com/en-us/azure/aks/postgresql-ha-overview
- https://learn.microsoft.com/en-us/azure/aks/private-clusters
- https://learn.microsoft.com/en-us/azure/aks/reliability-availability-zones-configure
- https://learn.microsoft.com/en-us/azure/aks/tutorial-kubernetes-prepare-acr (some claims UNCONFIRMED)
- https://learn.microsoft.com/en-us/azure/aks/use-kms-etcd-encryption
- https://learn.microsoft.com/en-us/azure/aks/use-network-policies
- https://learn.microsoft.com/en-us/azure/aks/use-system-pools
- https://learn.microsoft.com/en-us/azure/aks/workload-identity-deploy-cluster
- https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview
- https://learn.microsoft.com/en-us/azure/application-gateway/for-containers/migrate-from-agic-to-agc
- https://learn.microsoft.com/en-us/azure/application-gateway/for-containers/overview
- https://learn.microsoft.com/en-us/azure/application-gateway/understanding-pricing
- https://learn.microsoft.com/en-us/azure/azure-arc/kubernetes/conceptual-gitops-flux2
- https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-how-to-premium-persistence
- https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/scripts/create-manage-premium-cache-cluster
- https://learn.microsoft.com/en-us/azure/azure-monitor/containers/opentelemetry-protocol-ingestion
- https://learn.microsoft.com/en-us/azure/azure-monitor/containers/opentelemetry-summary
- https://learn.microsoft.com/en-us/azure/azure-monitor/containers/prometheus-metrics-scrape-configuration
- https://learn.microsoft.com/en-us/azure/azure-monitor/metrics/prometheus-grafana
- https://learn.microsoft.com/en-us/azure/container-registry/artifact-cache-overview
- https://learn.microsoft.com/en-us/azure/container-registry/container-registry-import-images
- https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-link
- https://learn.microsoft.com/en-us/azure/developer/terraform/store-state-in-azure-storage
- https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/configure-entra-id (some claims UNCONFIRMED)
- https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude
- https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link
- https://learn.microsoft.com/en-us/azure/frontdoor/standard-premium/how-to-enable-private-link-internal-load-balancer
- https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-service
- https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide
- https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore
- https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions
- https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector
- https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-use-pgdiskann
- https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/security-data-encryption
- https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability
- https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private-link
- https://learn.microsoft.com/en-us/azure/postgresql/security/security-connect-with-managed-identity
- https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-concepts
- https://learn.microsoft.com/en-us/azure/security/fundamentals/encryption-customer-managed-keys-support
- https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory
- https://learn.microsoft.com/en-us/azure/storage/common/customer-managed-keys-overview
- https://learn.microsoft.com/en-us/azure/storage/common/storage-private-endpoints
- https://learn.microsoft.com/en-us/azure/storage/files/azure-kubernetes-service-workloads
- https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/dadsv5-series
- https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/ddsv5-series
- https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow
- https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups
- https://learn.microsoft.com/en-us/entra/identity/app-provisioning/user-provisioning
- https://techcommunity.microsoft.com/blog/azurearchitectureblog/from-ingress-to-gateway-api-a-pragmatic-path-forward-and-why-it-matters-now/4489779
- https://techcommunity.microsoft.com/blog/azureobservabilityblog/announcing-ga-collect-syslog-from-your-aks-nodes-using-container-insights/3980648
- https://techcommunity.microsoft.com/blog/azuretoolsblog/azure-landing-zones-accelerators-for-bicep-and-terraform-announcing-general-avai/4029866
- https://www.infoq.com/news/2026/07/claude-foundry-ga-europe/
