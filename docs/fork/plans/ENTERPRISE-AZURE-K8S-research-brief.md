# Research charter — enterprise Azure / AKS deployment (K8S-R)

**Status:** charter for a research task (not implementation). **Owner decision on record:** maintainer,
2026-07-10. **Deliverable:** a Phase-1 research report → `docs/fork/plans/ENTERPRISE-AZURE-K8S-phase1.md`
(mirror the depth/shape of `AZURE-FOUNDRY-phase1.md`: verdicts, confirmed facts, phased plan, open
decisions surfaced for the maintainer), plus a proposed slice ladder into `MILESTONES.md` and, where a
hard-to-reverse cross-module call is made, a drafted ADR (F-series).

> **This charter is the compaction-survival artifact.** A fresh session picks this up, runs the research,
> and writes the phase-1 report. Nothing here is implemented yet.

---

## The thesis (maintainer, verbatim intent)

The fork must become a **distributable, per-customer enterprise deployment** — **not a platform we host.**
Concretely:

- **Deploys into the CUSTOMER's own Azure subscription / landing zone.** We host nothing. That is the whole
  point of OSS. (Answers the earlier BYO-subscription fork: customer brings the tenant; we ship the artifact.)
- **On AKS (Kubernetes)** so a customer scales effortlessly — the VM/compose stack (ADR-F058 Option A,
  runbook AZ-5) is **demo/prototype grade**; this is the production path.
- **Repeatable per customer.** There is a real customer deployment driving this and a second Azure prospect.
  Customer #2 must be a **parameterised repeat**, not a rewrite. "One dedicated, generalisable" deployment.
- **Start where the market is:** customers already on the Azure stack (many).
- **Foundry = models only, for now** (Anthropic + azure-openai routed through our gateway — the sole egress
  and sole key-holder). No broader Foundry footprint (PTUs, fine-tunes, custom content pipelines) in scope
  yet — but note where the architecture should leave room.

Everything else (managed PaaS vs in-cluster data plane, Terraform vs Bicep, which enterprise security
controls land in which phase) is **the research's job to evaluate and recommend** against a customer-owned
landing zone.

---

## What the research must produce (sections of the phase-1 report)

### 1. Target topology — dedicated AKS per customer, in the customer's subscription
- Cluster model: private AKS cluster per customer; system vs user node pools; **CPU sizing** (inference is
  external via Foundry, but the in-cluster CPU load is real: the fastembed **bge embedder** + **cross-encoder
  reranker** ONNX models, **Docling** ingest, **PyMuPDF**). No GPU needed for inference; confirm whether the
  embedder/rerank warrant a dedicated node pool. Map our **8 compose services** → K8s workloads:
  `api`, `gateway`, `arq-worker`, `ingest-worker`, `web`, `collabora` (WOPI editor, MPL), + the data plane.
- Multi-AZ / availability zones; PodDisruptionBudgets; node autoscaling.

### 2. Data plane — managed-first vs in-cluster (decision matrix + recommendation)
- **Postgres + pgvector:** Azure Database for PostgreSQL **Flexible Server** (confirm current pgvector
  version/support + HNSW), vs in-cluster operator (CloudNativePG). Our retriever, checkpointer, and native
  langgraph **Store/CompositeBackend** all sit on Postgres — verify pgvector parity so the retriever ports
  byte-clean. PITR/HA/backup story per option.
- **Redis:** Azure Cache for Redis vs in-cluster (arq queue + cache).
- **Object storage:** MinIO → **Azure Blob**; confirm our S3-compat access path (SDK/endpoint) works against
  Blob or needs an abstraction.
- Recommend **managed-by-default, in-cluster-supported** (different customers mandate different postures) and
  say what stays in-cluster **regardless**: the ONNX models and the **PyMuPDF AGPL server-side boundary**
  (obligation, not preference — NOTICES.md).

### 3. Foundry / model access on AKS
- azure-openai + Anthropic through the gateway; **keyless via AKS Workload Identity** — this **extends AZ-6 /
  ADR-F072** (today: VM IMDS → Entra token) to **federated Workload Identity** (pod → Entra, no key, no
  secret). Confirm the token-scope trap from ADR-F072 (bare `https://cognitiveservices.azure.com`, no
  `/.default`) carries over.
- **Data residency:** Foundry model availability is region-specific — pin model deployments to the customer's
  region/geo; flag which models we depend on and whether they exist in EU regions (relevant for legal/GDPR).
- Content filters / responsible-AI config as a customer-tunable.

### 4. Identity
- **Service identity:** Workload Identity for pod→(Key Vault, Postgres, Blob, Foundry) — keyless everywhere,
  the AKS generalisation of ADR-F072.
- **End-user identity (PHASED, big):** Entra ID **SSO** (OIDC/SAML) + **SCIM** provisioning would **replace
  our local login + user-lifecycle** (SETUP-3a/3b) for enterprise. Map our role model (operator/admin/user/
  viewer, ADR-F064) → Entra groups. **Flag this as its own sizeable workstream/ADR, not a line item.**

### 5. Networking (design to the customer's enterprise controls)
- **Fully private:** private cluster API server; **Private Endpoints** for Postgres/Key Vault/Blob/ACR;
  ingress via **Application Gateway (AGIC) or Front Door + WAF**; **egress control** (Azure Firewall / NAT,
  deny-by-default) — this is the AKS realisation of the restricted-egress private profile (**ADR-F070**).
- Collabora/WOPI network boundary; the gateway-as-sole-egress invariant expressed as NetworkPolicy + egress
  firewall rules (defense in depth behind the app-level guarantee).

### 6. Secrets & keys
- **Key Vault** (ADR-F069) via the **Secrets Store CSI driver** + Workload Identity (no secrets in etcd where
  avoidable).
- **Customer-managed keys (CMK):** encryption-at-rest with the customer's Key Vault keys across managed disks,
  Postgres, Blob — a frequent large-enterprise mandate. Phase it.

### 7. IaC + delivery (the "effortless scale / repeatable" centrepiece)
- **Terraform (azurerm) vs Bicep** for the landing-zone infra — evaluate for *deploying into arbitrary
  customer subscriptions* (portability, module reuse, customer familiarity). Recommend.
- **Helm charts** for the app; **GitOps (Flux/Argo) vs pipeline-push** delivery.
- **The parameterisation surface:** what a customer fills in to stand up their instance (region, domains,
  Entra tenant, KV, DB SKU, model deployments, branding per BRAND-1) — a values file / TF module inputs.
  This is what makes customer #2 a repeat.

### 8. Migrations & release
- Today `api` **auto-migrates on boot** (compose). On K8s that must become a controlled **migration Job /
  init container / Helm hook**, not app-boot — reconcile with the hard rule *"never host-side `alembic
  upgrade` on a live DB."* Define the ordered rollout (migrate → roll workers → roll api).
- Image supply: GHCR → customer **ACR** mirror (or pull-through cache); SHA-pinned images (ties into
  UP-OPS-1). Air-gapped/private-registry option (the P-2 backlog idea, ADR-F070 lineage).

### 9. Observability
- Azure Monitor / Container Insights; we already emit **OpenTelemetry spans** (M3-F2) — wire to Azure Monitor
  / a customer OTel collector. Optional Prometheus/Grafana. Health/readiness probes per service.

### 10. Horizontal-scale code audit (CRITICAL — surface what BLOCKS effortless scaling)
Run this against the actual tree. Multi-replica `api`/workers break any in-process assumption:
- **In-memory brakes/quotas:** the **R4 token-budget brake** (F2 Slice F — noted **in-memory, default 2M**)
  and **FanOutQuotaMiddleware** (F2 Slice E) — do these fragment across replicas? Need a shared store
  (Postgres/Redis)?
- **SSE streaming under >1 replica:** cockpit streaming + HITL — sticky sessions vs a pub/sub fan-out;
  does resume (`POST /runs/{id}/resume`, HITL-2) route to the right replica?
- **Run durability/leasing** (F1-S1 lease/sweep/cancel) — confirm it's DB-backed (it is: `agent_runs`
  leasing) so it survives replica loss; verify the sweep cadence under K8s.
- **The OOM discipline:** the dev-box embedder OOM shield → K8s **resource requests/limits + QoS class**;
  size the ingest/arq pods so the ONNX spike can't OOM a co-tenant.
- **Local/host assumptions:** any `localhost:8000` hardcode (upstream had DE-380), file-path assumptions,
  single-writer assumptions.
- Output: a concrete **"blocks horizontal scale" defect list** feeding the implementation ladder.

### 11. Cost model & phasing
- Rough monthly cost per customer (AKS + managed PaaS + Foundry) at a reference size.
- **Phased ladder**, e.g.: Phase 1 MVP (single-region, managed PaaS, Workload Identity, basic ingress) →
  Phase 2 private networking (ADR-F070 on AKS) → Phase 3 Entra SSO/SCIM → Phase 4 CMK + data-residency
  hardening → Phase 5 multi-region HA. Each phase a runnable, testable milestone.

---

## Constraints the research must honour (non-negotiable)
- **We host nothing** — every recommendation deploys into the customer's subscription.
- **Gateway stays the sole egress + sole key-holder;** provider keys only inside the gateway.
- **PyMuPDF AGPL = server-side-only** (obligation); Collabora MPL boundary intact.
- **ADR-F001:** upstream frozen — this is our own architecture; no upstream deployment code pulled.
- **Reuse, don't re-decide:** ADR-F069 (Key Vault), ADR-F070 (restricted egress), ADR-F072 (keyless MI),
  ADR-F058 (self-host charter), BRAND-1 (per-customer white-label). The AKS work *generalises* these.

## Method (how to run it, post-compaction)
- Multi-agent research fan-out (Workflow): one agent per report section researching Azure docs + auditing the
  fork tree for the section's code facts, a synthesizer, and a verify pass on the **§10 scale-blocker** claims
  against the real code (those drive implementation and must be code-grounded, not assumed). WebSearch/WebFetch
  for current Azure service facts (pgvector version on Flexible Server, Workload Identity GA state, AGIC vs
  Front Door), each verified — Azure surface changes fast.
- Produce the phase-1 report + the slice ladder; draft ADR(s) for the hard calls (tenancy-on-AKS,
  data-plane default, IaC choice). Maintainer accepts.

## Open decisions to SURFACE for the maintainer (do not pre-decide)
1. Managed PaaS vs in-cluster data plane default (recommend + rationale).
2. Terraform vs Bicep (recommend, considering customer-subscription portability).
3. Security-control phasing order (private networking / SSO+SCIM / CMK / residency) — which is Phase 1 vs later.
4. Whether Entra SSO/SCIM is in the first enterprise cut or a fast-follow (it replaces local auth — sizeable).
