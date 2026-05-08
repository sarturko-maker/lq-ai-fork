# InHouse AI — Product Requirements Document

**Project:** InHouse AI
**Stewarded by:** LegalQuants
**License:** Apache 2.0
**PRD Version:** 0.2 (Competitive Research and Security Posture Absorption)
**Authored by:** Kevin Keller, contributed to LegalQuants
**Date:** May 7, 2026
**Status:** Draft for review

**Changelog from v0.1:** Absorbed competitive-research and security-posture recommendations from a separate research session. Added five new top-level concepts: Projects (matter-scoped containers, M1), Organization Profile (org-wide voice/standards skill, M1), Inference Tier model (five-tier security spectrum), Inference Tier Awareness UI (M1), and Anonymization Layer (Inference Gateway middleware, M2). Added §1.8 Security Posture as a new top-level section. Added Tabular/Multi-Document Review (M3), Slack/Teams Light Intake Bridge (M3), Contract Repository auto-relationship detection (M4). Expanded the competitor list in §1.2. Added M5–M7 Forward-Looking Roadmap (workflow-aware context layer; community-driven; not committed). Added MCP-client subsystem as an architectural slot in M1–M2 to leave room for M5+ workflow intelligence. Added approximately 40 new deferred enhancements across new "Capability extensions," "Security and compliance," and "Workflow intelligence" subsections. Added Appendix E (Pre-Empted Procurement Objections, 17 entries).

---

## Table of Contents

1. [Product Overview](#1-product-overview) (§1.1 Vision · §1.2 Positioning · §1.3 Transparency · §1.4 Target Users · §1.5 Deployment Modes and the Inference Choice Spectrum · §1.6 Out of Scope · §1.7 Success Criteria · §1.8 Security Posture)
2. [Architecture](#2-architecture)
3. [Capability Specifications](#3-capability-specifications) (§3.1–3.10 plus new §3.11 Projects · §3.12 Organization Profile · §3.13 Inference Tier Awareness · §3.14 Tabular / Multi-Document Review · §3.15 Slack/Teams Light Intake Bridge · §3.16 Contract Repository — Auto-Relationship Detection)
4. [The InHouse AI Inference Gateway](#4-the-inhouse-ai-inference-gateway) (now includes Anonymization Layer middleware)
5. [Cross-Cutting Concerns](#5-cross-cutting-concerns)
6. [Deployment](#6-deployment)
7. [Open Source Posture](#7-open-source-posture)
8. [Roadmap](#8-roadmap) (M1–M4 plus M5+ Forward-Looking)
9. [Deferred Enhancements and Identified Future Work](#9-deferred-enhancements-and-identified-future-work)
10. [Appendices](#10-appendices) (A Glossary · B License Matrix · C Known Risks · D Companion Documents · E Pre-Empted Procurement Objections)

---

## 1. Product Overview

### 1.1 Vision

InHouse AI is an open-source AI platform purpose-built for in-house legal teams. It delivers the core capabilities of commercial in-house legal AI products — fast, accurate contract drafting and review, verifiable citations, reusable workflow skills, playbook-driven contract analysis, and a Microsoft Word integration — as a fully self-hostable system that runs on a laptop, an internal server, or a cloud VM.

The project's reason for existing is simple: in-house legal teams should not have to choose between AI assistance and data sovereignty. Every other capable tool in this category is a closed-source SaaS that requires sending privileged information to a third-party vendor. InHouse AI runs in the customer's environment, with the customer's keys, against the customer's choice of model — including fully air-gapped deployments using local inference.

The longer-term ambition extends beyond the core capability set. Over time, InHouse AI is intended to evolve from a tool the user reaches for into a workflow-aware context layer that integrates with the email, calendar, task systems, and document stores the user already lives in — surfacing the right matter at the right moment, with rationale, with one-click actions, with full transparency about what the system is doing on the user's behalf. That evolution is forward-looking and out of scope for v1; the M5+ Forward-Looking Roadmap (§8.5) names the trajectory so that v1 architectural choices leave room for it rather than painting the project into a corner.

### 1.2 Positioning

> **InHouse AI** — open-source AI for in-house legal teams. Bring your own keys, run it where you want, own your data.

The product positions against three categories:

- **Commercial in-house legal AI:** the category is more crowded than a three-name list (GC.AI, Spellbook, Legora) suggests. Direct competitors include GC.AI, Ivo, Legalfly (Belgian, "legal operating system for corporates"), Spellbook, Legora, Harvey-for-in-house, Eudia, and ContractPodAi (rebranded Leah). Robin AI was a fourth-tier-product structure player but collapsed in late 2025; its features are documented for reference in the deferred-enhancement list. A separate adjacent category — in-house workflow / matter management — includes Streamline AI, Checkbox, LawVu, and Dazychain; the boundary with that category is addressed in §1.6. InHouse AI matches the analytical-AI core capability set, runs on the customer's infrastructure, costs nothing in license fees, and ships every shaping artifact as inspectable open source — a posture no closed-source competitor can match without abandoning their architectural assumptions.
- **Generalist AI (ChatGPT, Claude, Microsoft Copilot, etc.):** InHouse AI is purpose-built for legal workflows, ships with a curated skill library for legal tasks, and produces verifiable citations. It also addresses the privilege-and-confidentiality concerns that have made generalist tools a liability for legal practice (per *U.S. v. Heppner*).
- **Internal tools / DIY stacks:** InHouse AI is a turn-key alternative to building it yourself, with a coherent architecture, a maintained skill format, and a community.

For procurement and security teams evaluating InHouse AI: the security-posture story is consolidated in §1.8 Security Posture, with detailed responses to common procurement objections in Appendix E (Pre-Empted Procurement Objections). The forward-looking trajectory toward workflow-aware context (§8.5) describes the project's longer-term differentiation beyond feature parity.

### 1.3 Transparency as a Founding Principle

InHouse AI's commercial competitors treat their prompt engineering as proprietary moat. The skills, playbooks, citation logic, and verification heuristics that shape what the user sees are hidden inside closed-source applications, presented as "AI" but functionally indistinguishable from "a system prompt the vendor refuses to show you." This is smoke and mirrors. Much of the time, the emperor has no clothes — what looks like advanced legal AI is a moderately well-tuned prompt that the vendor charges hundreds of dollars per seat per month to keep secret.

InHouse AI inverts this. **Every artifact that shapes the user's experience is visible work product.** The skills are open source. The playbooks are open source. The citation engine's verification logic is open source. The Enhance Prompt rewriter is open source. The autonomous-agent instructions are open source. The Organization Profile (§3.12) — the org-wide voice, templates, and "what good looks like" reference that shapes every output — is open source. When a user clicks "view this skill" on any active skill, they see the actual SKILL.md and supporting files, formatted for human reading, with provenance and the ability to fork. There is no hidden layer between the user's prompt and the model's output that the user cannot inspect.

This commitment shapes three concrete product decisions:

1. **No proprietary "secret sauce" in the open-source release.** Optimizations that depend on undisclosed prompt engineering, undisclosed routing rules, or undisclosed verification heuristics are not part of InHouse AI. If we use a clever technique, the technique is in the repo, documented, and contributable.
2. **Skill inspectability is a first-class application feature** (§3.4), not a developer-debug affordance. Every active skill is one click away from being readable. Users learn the patterns, build trust through verification, and disagree-fork-replace when the skill is wrong.
3. **The skills *are* the product.** The value of InHouse AI comes from the curation and authoring of skills — which the community can read, contribute to, and improve — not from hiding them behind a paywall. Skills written for InHouse AI work in any agentskills.io-compatible runtime; users are not locked in.

The position implied by all of this is uncomfortable for the rest of the legal-AI category, and that is intentional. Customers who have been paying significant per-seat fees for software whose only real innovation is a hidden system prompt are entitled to see what they have actually been buying. When the curtain is pulled back, some of those products will hold up. Many will not. InHouse AI's bet is that an open, transparent product built on community-curated skills is better than a closed, opaque product built on the assumption that the user cannot see what is happening — and that the resulting trust is worth more than the marketing.

Practical implication for contributors and operators: treat skills as the canonical artifact. When something in the system produces a wrong answer, the answer to "why" is almost always in a SKILL.md somewhere. When the right answer is something we want the system to do consistently, the way to get there is to write or improve a skill. Skills are not configuration; they are the substance of the product.

### 1.4 Target Users

**Primary user:** in-house counsel at organizations of any size, from solo General Counsel to enterprise legal departments. The product assumes legal training and aims to extend the user's capacity, not replace judgment.

**Operator:** the person or team deploying InHouse AI within an organization. Could be the legal team itself (technical GC, legal-ops manager) or IT/SRE deploying on legal's behalf. The operator cares about deployment ergonomics, key management, audit trails, and integration with existing identity providers.

**Contributor:** the open-source community. Skill authors, playbook authors, plugin developers, and engineers extending the platform. The product must be friendly to contribution.

### 1.5 Deployment Modes and the Inference Choice Spectrum

InHouse AI's deployment posture has two dimensions. The first dimension is the **deployment mode** — where the application itself runs and how inference is reached. The second dimension is the **Inference Choice Spectrum** — what kind of trust relationship the operator has with whichever party is actually running the model. The two dimensions are orthogonal: a single deployment mode can map to multiple tiers depending on what the operator configures inside the gateway.

#### 1.5.1 Two deployment modes

Both modes use the same Docker Compose deployment. The Inference Gateway routes to whichever providers are configured.

**Mode 1: Self-hosted with cloud LLM keys.** The operator deploys InHouse AI on their infrastructure (laptop, server, or cloud VM) and configures it with API keys for one or more cloud LLM providers (Anthropic, OpenAI, Google, Cohere, Azure OpenAI, Bedrock). Inference happens at the cloud provider; the rest of the system stays in the operator's environment.

**Mode 2: Self-hosted with local inference (air-gap-capable).** The operator deploys InHouse AI alongside Ollama (or any OpenAI-compatible local inference endpoint) and runs all inference locally. This mode supports fully air-gapped deployments with no outbound network traffic.

#### 1.5.2 The Inference Choice Spectrum: five tiers

In practice, the security posture varies along a five-tier spectrum. The tiers are first-class concepts in the configuration and are surfaced to the user in real time via the Inference Tier Awareness UI (§3.13). Skills and Projects can require minimum tiers; deployments can disallow tiers globally. The tier spectrum is the central organizing concept of §1.8 Security Posture and Appendix E.

**Tier 1 — Local-only inference (air-gap-capable).** Inference runs on operator hardware via Ollama, vLLM, llama.cpp, or any OpenAI-compatible local endpoint. No outbound network is required. Customer data, prompts, and model outputs never leave the deployment. This is Mode 2. Suitable for the most sensitive work product (privileged communications, strategic-deal information, regulated-data deployments). The trade-off is performance: a model that fits on local hardware is, today, smaller and slower than the best cloud-hosted models.

**Tier 2 — Customer-hosted cloud inference.** Inference runs on infrastructure the operator owns: vLLM/llama.cpp on the operator's VPC, AWS Bedrock under the operator's AWS account, Azure OpenAI under the operator's Azure tenant, or Google Vertex AI under the operator's GCP project. Customer data leaves the InHouse AI deployment but stays inside the operator's cloud account boundary. No third-party processor is introduced. This tier offers near-Tier-3 performance with stronger custody than direct API access because the operator's cloud-provider DPA covers the data flow.

**Tier 3 — Enterprise managed inference with ZDR / no-training commitments.** Inference runs against a cloud provider's enterprise tier with explicit zero-data-retention or no-training contractual terms (Anthropic with a ZDR addendum, OpenAI Enterprise, Google Vertex AI, AWS Bedrock under Commercial Terms, Cohere Enterprise). The provider processes customer data per the enterprise DPA, does not use it for model training, and either does not retain it after the response is returned (ZDR) or retains it for a narrow safety/abuse window (commonly 7–30 days). This tier is what most pragmatic enterprise deployments use; this is where InHouse AI's posture matches what closed-source commercial in-house legal AI products provide today.

**Tier 4 — Standard cloud API under default commercial terms.** Inference runs against a cloud provider's standard commercial API without the enterprise ZDR addendum. The provider does not train on customer data (under standard commercial terms across major providers as of May 2026), but data is retained for the provider's default window (commonly 30 days, going to 7 days for some providers in late 2025/2026 changes). Suitable for many in-house deployments; less defensible for the most sensitive work product.

**Tier 5 — Consumer or free tier.** Inference runs against a consumer-tier endpoint (e.g., a personal Anthropic Pro account, a personal OpenAI account) where the provider's consumer terms may permit training-on-data unless explicitly opted out. As of August–September 2025, several major providers shifted consumer terms toward training-by-default-with-opt-out. This tier is unsuitable for client-confidential legal work; the application warns prominently when configured to use it.

When customer data privacy is a requirement but Tier 1 / Tier 2 is impractical, the Anonymization Layer (§4) offers a privacy fallback for Tier 3+: sensitive entities are pseudonymized prior to processing and rehydrated after. The Provider Compliance Matrix (`docs/compliance/provider-compliance-matrix.md`) details each supported provider's terms, certifications, and data-residency options for tier classification.

### 1.6 Out of Scope (v1)

Explicitly not in scope for v1, to keep the initial release focused:

- **Hosted SaaS offering.** No legalquants.com-hosted instance. Self-hosted only.
- **Tucuxi cognitive-architecture integration** (Director RNN, Cognitive Compilation Engine, RSH framework, Wisdom Database/GUD). These remain proprietary to Tucuxi and are not part of the open-source InHouse AI release.
- **Mobile applications.** Web UI is responsive, but no native iOS/Android apps.
- **E-discovery or litigation-specific workflows.** Focus is in-house counsel work: contracts, policies, regulatory matters, advice. Litigation tools are a separate product category.
- **Direct integrations with CLM systems** (Ironclad, Concord, etc.). Out of scope for v1; potential v2 work.
- **Billing / time tracking.** Not a feature of in-house legal work.
- **Full intake / triage / matter-management workflow** (request portal, SLAs, approvals, escalations, dashboards). InHouse AI is the analytical AI layer; Streamline AI and Checkbox occupy the operational-workflow layer. They are complementary; v1 stays on the analytical side. Light intake bridges (§3.x Slack/Teams Bridge in M3) are in scope; full operational workflow is not.

### 1.7 Success Criteria for v1 (M1 Release)

- Operator can go from `git clone` to a working chat with files and skills in under 15 minutes on a laptop with Docker installed.
- Documented Mode 1 (cloud keys) and Mode 2 (Ollama) deployments both work on first attempt for a competent technical user.
- 10 starter skills ship with the release and produce useful output on real contracts.
- The Inference Gateway successfully routes to all v1 supported providers (Anthropic, OpenAI, Google, Cohere, Ollama, Azure OpenAI, Bedrock).
- Project clears 1,000 GitHub stars within 90 days of public release (community-traction proxy).
- At least 5 external contributors land merged PRs within 90 days (contribution-friendliness proxy).
- At least 3 deployed instances (across any organizations) report having created at least one Project (§3.11) and one Organization Profile (§3.12) within 60 days, indicating the matter-context model is being used as designed (adoption-quality proxy).

### 1.8 Security Posture

InHouse AI's security posture is structurally different from the closed-source commercial alternatives in the category. Three principles shape it.

**The operator chooses the deployment's posture.** InHouse AI does not run a SaaS that holds your data on our infrastructure; you run it on yours. The most consequential security decisions — where the deployment lives, what inference provider it routes to, how the audit log is retained, who has access — are yours, and the application makes the implications of each decision explicit. A closed-source vendor's compliance posture is only as strong as the audit reports they will hand over and the contractual commitments they will sign. InHouse AI's compliance posture is verifiable in source.

**The Inference Choice Spectrum is the central security trade-off.** Inference is where customer data leaves the deployment, if it does. The five-tier spectrum (§1.5.2) maps the choice across local-only inference (Tier 1), customer-hosted cloud inference (Tier 2), enterprise managed inference with ZDR / no-training commitments (Tier 3), standard cloud API (Tier 4), and consumer or free tier (Tier 5). Tier 3 is recommended for most pragmatic enterprise deployments and matches what closed-source commercial in-house legal AI products provide. Tier 1 is recommended for the most sensitive privileged work. The application surfaces the routed tier in the chat UI in real time (§3.13); Skills and Projects can require minimum tiers; deployments can disallow tiers globally; the audit log captures every routing decision.

**Transparency replaces opacity.** Every artifact that shapes the user's experience is open source and inspectable: skills, playbooks, the Citation Engine's verification logic, the Enhance Prompt rewriter, autonomous-agent instructions, the Organization Profile (§3.12), the prioritization logic in any future workflow-context features. Every release ships with an SBOM (Software Bill of Materials), signed container images (Sigstore/cosign), SLSA-3 build provenance attestations, and a published threat model (`docs/security/threat-model.md`). Every framework an operator's auditor will ask about — SOC 2, ISO 27001, ISO 42001, GDPR, HIPAA, FedRAMP — has a corresponding alignment document (`docs/compliance/`) mapping our design choices to the framework's controls and identifying which controls are project-provided, operator-provided, or joint. Where InHouse AI does not yet match a specific commercial competitor's control, it is named on the public deferred-enhancements list (§9) with a roadmap rather than glossed over in marketing.

Procurement-defense materials, including a structured Pre-Empted Procurement Objections appendix (Appendix E) and the Compliance Alignment Pack (referenced above), are maintained in the repository and updated each release.

Detailed cross-cutting security and compliance concerns are covered in §5; deployment-mode and inference-tier configuration in §1.5 and the Inference Gateway specification in §4; the deferred security and compliance enhancement roadmap in §9 (Security and Compliance subsection).

---

## 2. Architecture

### 2.1 Reference Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLIENT SURFACES                              │
│   Web App (OpenWebUI fork)    │    Word Add-In (Office.js)           │
│   - Chat, skills, files        │    - Redlining                      │
│   - Skill Library UI            │    - Playbook execution             │
│   - Playbook Manager            │    - Inline comments                │
└──────────────────┬─────────────┴────────────────┬────────────────────┘
                   │                              │
                   │  OpenAPI 3.1 over HTTPS      │
                   ▼                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  InHouse AI Backend (FastAPI)                        │
│                                                                      │
│   Authn/Authz  │  Audit Log  │  RBAC  │  OpenAPI Surface              │
└──────┬───────────────┬─────────────┬────────────┬───────────────┬────┘
       │               │             │            │               │
       ▼               ▼             ▼            ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌───────────┐ ┌────────────┐ ┌─────────┐
│ Inference   │ │   Skill     │ │  Playbook │ │  Document  │ │Knowledge│
│  Gateway    │ │  Service    │ │  Service  │ │  Pipeline  │ │ Service │
│             │ │             │ │           │ │ Docling +  │ │ Hybrid  │
│ Multi-      │ │agentskills  │ │ Schema +  │ │ PyMuPDF +  │ │ search: │
│ provider    │ │ format      │ │ Easy      │ │ Mistral    │ │ vector  │
│ router with │ │             │ │ Playbook  │ │ OCR        │ │ + FTS   │
│ fallback,   │ │ Skill       │ │ generator │ │            │ │         │
│ rate limit, │ │ Library +   │ │           │ │ Citation   │ │ pgvector│
│ cost track  │ │ Creator     │ │ LangGraph │ │ Engine     │ │         │
│             │ │             │ │ executor  │ │            │ │         │
└──────┬──────┘ └──────┬──────┘ └─────┬─────┘ └──────┬─────┘ └────┬────┘
       │               │              │              │            │
       └───────────────┴──────────────┴──────────────┴────────────┘
                                      │
                ┌─────────────────────┼─────────────────────┐
                ▼                     ▼                     ▼
        ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
        │ PostgreSQL   │      │    Redis     │      │   MinIO /    │
        │ + pgvector   │      │  (sessions,  │      │   S3-compat  │
        │              │      │   queues,    │      │   (files)    │
        │ App data,    │      │   pubsub)    │      │              │
        │ vectors,     │      │              │      │              │
        │ FTS, audit   │      │              │      │              │
        └──────────────┘      └──────────────┘      └──────────────┘

LLM PROVIDERS (any combination, configured by operator):
  Cloud:  Anthropic │ OpenAI │ Google Vertex │ Cohere │ Azure OpenAI │ AWS Bedrock
  Local:  Ollama │ vLLM │ llama.cpp │ any OpenAI-compatible endpoint

OBSERVABILITY (optional):
  OpenTelemetry → Grafana / Tempo / Loki     │     Langfuse (LLM-specific tracing)
```

### 2.2 Technology Decisions and Rationale

**Application shell: OpenWebUI.** Chosen over LibreChat because: 9 vector DB backends, native SCIM 2.0, built-in OpenTelemetry, mature RBAC, Pipelines plugin framework (which we use for the autonomous agent layer in M4), Redis-backed multi-worker scaling, Google Drive/OneDrive integration. Branding clause is acceptable since InHouse AI is open-source itself; we follow OpenWebUI's branding requirements and document the relationship clearly. We fork at the latest stable version and pull updates regularly rather than diverging.

**Backend: FastAPI.** OpenAPI 3.1 by construction, async-native, Pydantic models for request/response validation, excellent ecosystem. Aligns with operator expectations for a Python-backend AI product.

**Agent runtime: LangGraph.** Stateful, graph-based agent workflows are the right shape for legal work — contract review is multi-step (parse → classify → playbook-match → redline → cite-verify). State persists across long-running operations. MIT-licensed, production-tested.

**Skill format: agentskills.io / Anthropic Claude Skills.** Open standard, interoperable with Claude Code and Hermes Agent ecosystems. A skill is a folder containing a `SKILL.md` (with YAML frontmatter for metadata) plus optional supporting files. Skills are version-controllable, shareable, and human-readable.

**Inference Gateway: built in-house.** LiteLLM has had a meaningful security history (proxy auth bypasses, SSRF vulnerabilities, sprawling codebase). For an open-source project where users may run our gateway with privileged API keys, that surface area is unacceptable. We build a focused, auditable gateway in ~3,000 lines of Python. Full spec in §4.

**Document pipeline: Docling + PyMuPDF + Mistral OCR.** Docling for structure-aware parsing, PyMuPDF for character-precise byte offsets (server-side use only — AGPL is not contagious through HTTP API boundaries), Mistral OCR API as a paid fallback for scanned documents. Operators who want fully air-gapped deployments use PaddleOCR-VL instead of Mistral OCR.

**Vector store: pgvector.** Same Postgres instance we already have for app data — one less moving part, no separate vector DB to operate. Hybrid search via PostgreSQL's full-text search alongside vector similarity. Operators with scale needs can swap in Qdrant via configuration.

**Auth/RBAC: OpenWebUI built-in for v1.** OpenWebUI's auth supports LDAP/AD, SCIM 2.0, OAuth, trusted-header SSO, and granular RBAC. Sufficient for v1. Operators with complex IdP needs can front the deployment with Authentik or Keycloak via reverse proxy.

**Observability: OpenTelemetry + Langfuse.** OTel for app traces/metrics/logs to standard sinks, Langfuse for LLM-specific tracing, prompt versioning, and evaluation. Both optional, both self-hostable, both Apache 2.0 / MIT.

### 2.3 Data Isolation Model

Single-tenant by deployment. There is no cross-tenant isolation problem because each deployment serves one organization. Within a deployment, RBAC scopes data to users and groups:

- **Personal scope:** chats, files, skills, and playbooks owned by the user.
- **Group scope:** shared with explicitly-named groups; group membership controlled by admin.
- **Organization scope:** available to all users in the deployment.

All scopes share the same database; access control is enforced at the API layer with explicit scope checks on every read/write. Operators who need stronger isolation between business units run multiple InHouse AI deployments.

### 2.4 Deployment Topology

**Mode 1 — Self-hosted with cloud LLM keys (default):**

```
Operator's Environment
├── docker compose up
│   ├── inhouse-ai-web (OpenWebUI fork, port 3000)
│   ├── inhouse-ai-api (FastAPI, port 8000)
│   ├── inhouse-ai-gateway (Inference Gateway, port 8001)
│   ├── postgres (with pgvector)
│   ├── redis
│   └── minio (or S3-compatible)
└── Outbound HTTPS to cloud LLM providers
    ├── Anthropic API (operator's key)
    ├── OpenAI API (operator's key)
    └── ...
```

**Mode 2 — Fully local inference (air-gap-capable):**

```
Operator's Environment
├── docker compose up (with --profile local)
│   ├── inhouse-ai-web
│   ├── inhouse-ai-api
│   ├── inhouse-ai-gateway
│   ├── ollama (with locally-pulled models)
│   ├── postgres (with pgvector)
│   ├── redis
│   ├── minio
│   └── paddleocr-vl (replaces Mistral OCR API)
└── No outbound network required
```

Both modes use the same images. The difference is which `--profile` flag is passed to Compose and which environment variables are set in `.env`.

---

## 3. Capability Specifications

This section specifies each major capability. Every capability section follows the same structure:
- **Description** — what the capability does.
- **User stories** — how users invoke it.
- **Functional requirements** — what the system must do.
- **Non-functional requirements** — performance, accuracy, reliability targets.
- **API surface** — relevant FastAPI endpoints.
- **Data model** — primary entities.
- **Dependencies** — what other capabilities this relies on.
- **Open questions** — decisions deferred.

### 3.1 Conversational Core

**Description.** Multi-turn chat with persistent history, organized in a sidebar grouped by recency. Users can rename, delete, search, and share chats. Each chat is associated with the user who created it and optionally shared with groups or the whole organization. Chats can have files, skills, and playbooks attached.

**User stories.**
- As a user, I start a new chat by clicking "New Chat" in the sidebar.
- As a user, I attach skills to a chat with `+ → Skills`.
- As a user, I attach files to a chat by drag-and-drop or `+ → Files`.
- As a user, I search across all my chat history by keyword.
- As a user, I share a chat with a teammate or my whole organization.
- As a user, I create a chat inside a Project (§3.11) and the chat inherits the Project's attached files, skills, playbooks, and free-form context document.
- As an admin, I see audit logs of all chat activity in my organization.

**Functional requirements.**
- Chats persist across sessions and are restored on login.
- Each chat carries a list of attached resources (skills, files, playbooks).
- Each chat has an optional `project_id` (FK to Project per §3.11); chats in a Project inherit the Project's resources and context.
- Users can rename, delete, archive, pin, and share chats.
- Full-text search across chat content (own chats + chats shared with user).
- Streaming model responses (SSE).
- Markdown rendering, including LaTeX and code blocks.
- Copy-as-Markdown, Copy-as-Plain-Text, Export-to-DOCX.

**Non-functional requirements.**
- First token latency < 2s for cloud providers, < 5s for local Ollama on reasonable hardware.
- Chat list loads in < 500ms for users with up to 1,000 chats.
- Search across 10,000 chats returns results in < 1s.

**API surface.**
- `POST /api/v1/chats` — create chat.
- `GET /api/v1/chats` — list user's chats.
- `GET /api/v1/chats/{id}` — get chat with messages.
- `POST /api/v1/chats/{id}/messages` — post message, stream response.
- `PATCH /api/v1/chats/{id}` — update chat (rename, archive, pin, share).
- `DELETE /api/v1/chats/{id}` — delete chat.
- `GET /api/v1/chats/search?q=...` — search chats.

**Data model.**
- `Chat`: id, owner_id, title, created_at, updated_at, archived, pinned, shared_with_groups, shared_with_org, project_id (nullable — links to an enclosing Project per §3.11).
- `Message`: id, chat_id, role (user|assistant|system|tool), content, created_at, token_counts, model_used, routed_inference_tier (per §3.13).
- `ChatAttachment`: chat_id, resource_type (skill|file|playbook), resource_id.

**Dependencies.** Inference Gateway (§4), Skill Service (§3.4), Knowledge Service (§3.5), Playbook Service (§3.7), Project Service (§3.11, optional — chats can be created inside or outside a Project).

**Open questions.** Should chat-level fork/branch be a v1 feature? OpenWebUI supports it; recommend keeping it.

### 3.2 Enhance Prompt

**Description.** A prompt-rewriting skill that runs as an optional pre-step. The user types a short, natural-language question; Enhance Prompt expands it into a structured legal prompt (role, jurisdiction, audience, scope, output format, constraints, citation expectations) and shows the user the expanded version before submission. The user can edit the expansion, submit as-is, or skip and submit the original. The skill is *itself* inspectable — the user can view the SKILL.md and supporting files driving the enhancement at any time.

**User stories.**
- As a user, I type "review this NDA for unusual provisions" and click Enhance Prompt; the system rewrites my prompt into a detailed legal review prompt and shows it to me before submitting.
- As a user, I edit the Enhance Prompt output before submitting.
- As a user, I skip Enhance Prompt and submit my original prompt as-is.
- As a user, I click "view this skill" on the review screen and read the actual instructions driving the enhancement, so I can decide whether I trust them.
- As a user, I configure my account-level preference for whether reasoning is shown by default, hidden behind a disclosure, or always visible.

**Functional requirements.**
- Enhance Prompt runs as a separate, fast model call (typically a smaller/cheaper model).
- The expansion uses the user's recently-attached skills as context, not just the raw input.
- The expansion includes a *reasoning section* explaining why each addition was made (so users learn the prompt-engineering moves).
- The skill correctly identifies prompts that should *not* be expanded (follow-up questions, conversational turns, already-structured prompts, operational asks) and returns a skip decision.
- When an attached skill has a missing required input, Enhance Prompt surfaces the missing input as a structured form-like prompt rather than expanding the prompt's text — see §3.4 on the skill-input-form pattern.
- Enhance Prompt is a toggle; off by default for power users. Per-prompt invocation also available via button.
- **Reasoning visibility:** account-level setting with three modes — `always_show` (reasoning visible by default), `disclosure` (reasoning collapsed behind a "why these changes?" disclosure, default), `on_request` (reasoning hidden until user opens the skill inspector).
- **Skill inspectability:** the review-before-sending screen includes a "view this skill" affordance that opens the actual SKILL.md and supporting files in a side panel. This is the general skill-inspectability pattern (§3.4) applied to Enhance Prompt specifically.

**Non-functional requirements.**
- Enhance Prompt expansion completes in < 3s.
- Skill inspector opens in < 500ms.

**API surface.**
- `POST /api/v1/enhance-prompt` — accepts raw user input plus chat context, returns expanded prompt + reasoning + skip decision (structured per the SKILL.md output schema).
- `GET /api/v1/skills/{id}/contents` — returns the skill's full contents (SKILL.md + supporting files) for inspection. Used by the skill inspector; see §3.4.

**Data model.**
- `EnhancePromptInteraction`: id, user_id, raw_input, expansion_applied (bool), expanded_output, reasoning, skip_reason, used (bool), edited_before_use (bool), created_at. Used for telemetry and improvement.

**Dependencies.** Inference Gateway, Skill Service.

**Open questions.** None blocking.

### 3.3 Citation Engine (Exact Quote)

**Description.** End-to-end pipeline that guarantees character-fidelity from document → model context → cited output → rendered viewer. When the model produces a claim with a citation, the system can highlight the exact substring in the source document, in the original page, with character precision. Includes a verification step that fails the citation if the cited substring does not appear verbatim in the source.

This is the single most differentiated capability in the product. Specified in detail.

**User stories.**
- As a user, I upload a contract and ask a question; the answer includes inline citations like `[Doc1, p.3]` that I can click.
- As a user, clicking a citation slides in a side-panel viewer showing the original document page with the cited passage highlighted.
- As a user, I am confident the cited passage is verbatim — the system has verified it.
- As a user, I see a clear failure mode (citation marked as "unverified") if the system could not verify a citation, rather than silent error.

**Functional requirements.**

*Ingestion.*
- Documents are parsed by Docling for structural understanding and PyMuPDF for character offsets.
- Output is a *citable chunk schema*:
  ```python
  class CitableChunk(BaseModel):
      chunk_id: UUID
      doc_id: UUID
      page_number: int
      char_start: int       # offset within doc
      char_end: int         # offset within doc
      bbox: List[float]     # [x0, y0, x1, y1] for rendering overlay
      text: str             # the verbatim text in this chunk
      structural_role: str  # "heading"|"paragraph"|"clause"|"footnote"|"table_cell"|...
      hierarchy: List[str]  # ["Section 4", "4.2", "4.2(b)"] for clause-level docs
  ```
- Chunks are sized for retrieval (target ~500 tokens, soft boundaries on structural breaks).
- Both vector embeddings and full-text indexing are computed per-chunk.

*Retrieval.*
- Hybrid retrieval: vector similarity + BM25 full-text + structural-role filtering.
- Top-k retrieval returns chunks with full citation metadata, not just text.

*Generation.*
- The system prompt requires the model to cite *only* chunk IDs from the retrieved set.
- Structured output enforces a JSON shape:
  ```json
  {
    "answer_with_citations": [
      {"text": "Section 4 limits liability to fees paid in the prior 12 months.", "citations": ["chunk-uuid-1"]},
      {"text": "However, Section 4(c) carves out willful misconduct.", "citations": ["chunk-uuid-2"]}
    ]
  }
  ```

*Verification.*
- A secondary, cheap model (or deterministic check) verifies that the asserted claims are supported by the cited chunks.
- A deterministic check verifies that any verbatim quote in the answer appears verbatim in at least one cited chunk.
- Failed verifications are flagged in the rendered output ("citation unverified — review source").

*Rendering.*
- Inline citations are clickable in the chat UI.
- Clicking opens a side-panel PDF viewer (PDF.js).
- The viewer scrolls to the right page and overlays a bounding-box highlight at the chunk's bbox coordinates.
- Multiple citations to the same document open the same viewer with sequential highlights.

**Non-functional requirements.**
- Document ingestion: < 30s for a 50-page PDF on reasonable hardware.
- Citation verification: < 500ms per cited claim.
- Side-panel viewer renders in < 1s.

**API surface.**
- `POST /api/v1/documents` — upload document.
- `GET /api/v1/documents/{id}` — document metadata.
- `GET /api/v1/documents/{id}/chunks?query=...` — retrieve relevant chunks.
- `POST /api/v1/citations/verify` — verify a list of cited claims against cited chunks.
- `GET /api/v1/documents/{id}/render?page={n}&highlight={bbox}` — render page with highlight overlay (returns PNG or PDF page).

**Data model.**
- `Document`: id, owner_id, filename, mime_type, page_count, ingestion_status, created_at.
- `CitableChunk`: as specified above. Stored in pgvector + FTS index.
- `Citation`: id, message_id, chunk_id, claim_text, verification_status, verified_at.
- `WorkProductAttribution` (new in v0.2): id, message_id, user_id, chat_id (with optional project_id), routed_inference_tier, provider, model, model_version, skill_ids (array), playbook_id (nullable), timestamp, content_hash. This is the chain of custody for legal work product. The metadata is exposed in the per-user export bundle (§5.3) and is pre-requisite for the privilege-and-custody story in §1.8 and the deferred cryptographic-timestamping enhancement (§9 Security and Compliance).

**Dependencies.** Document Pipeline, Knowledge Service, Inference Gateway.

**Open questions.**
- Should the verifier be a dedicated cheap model (Haiku, Gemini Flash) or a deterministic substring check, or both? Recommend both: deterministic substring check first (catches verbatim quotes), LLM judge for paraphrased claims.
- Side-panel viewer: PDF.js is the obvious choice for PDFs. For DOCX sources, do we render a synthesized PDF or a styled HTML view? Recommend HTML view for DOCX with span-level offset markers.

### 3.4 Skill Library and Skill Creator

**Description.** Skills are reusable, structured prompt artifacts that users attach to chats. They follow the agentskills.io / Claude Skills format: a folder containing `SKILL.md` (with YAML frontmatter) and optional supporting files. Three tiers: built-in skills (ship with the product), user skills (created by the user), and shared skills (shared by other users in the organization).

The Skill Creator is itself a skill — a meta-skill the user invokes to build new skills via conversation.

**User stories.**
- As a user, I open the Skill Library and browse skills by category.
- As a user, I attach one or more skills to a chat.
- As a user, I chain multiple skills (e.g., "review this contract" + "rewrite in plain language") and the system applies both.
- As a user, I invoke the Skill Creator via conversation to build a new skill, and it produces a valid skill folder.
- As a user, I save any chat as a skill ("turn this into a skill").
- As a user, I share a skill with my team or organization.
- As a user, I edit a skill's content directly via a built-in editor.
- As a user, I ask the system to update a skill based on what I just did in this chat.

**Functional requirements.**

*Skill format.* Each skill is a folder with this structure:

```
my-skill/
├── SKILL.md              # Required. Main instruction file with YAML frontmatter.
├── reference/            # Optional. Reference material the skill cites.
│   └── ...
├── examples/             # Optional. Worked examples.
│   └── ...
└── scripts/              # Optional. Executable helpers (Python).
    └── ...
```

`SKILL.md` frontmatter:

```yaml
---
name: nda-review
title: NDA Review
description: Review a non-disclosure agreement for unusual provisions and risks.
version: 1.0.0
author: LegalQuants
tags: [contracts, nda, review]
trigger_examples:
  - "review this NDA"
  - "what should I watch for in this confidentiality agreement"
  - "redline this NDA"
inputs:
  required:
    - document
  optional:
    - jurisdiction
    - perspective  # "discloser"|"recipient"|"mutual"
inhouse:
  output_format: report   # "report" | "table" | "issue_list" (table reserved for §3.14 Tabular Review)
  minimum_inference_tier: 2   # optional; if set, skill refuses to run below this tier (per §3.13)
  is_organization_profile: false   # optional; true marks this skill as the singleton Org Profile (per §3.12)
---
```

The `inhouse:` namespace fields are the project-specific extensions to the agentskills.io standard frontmatter. Skills authored against the open standard work without them; the InHouse application uses them when present. See §3.13 for the inference-tier model and §3.14 for the tabular output mode.

*Skill chaining.* When multiple skills are attached, their `SKILL.md` instructions are concatenated in the order attached, with clear delimiters. The model is instructed to apply all skills.

*Skill Creator.* A built-in skill that, when attached, drives a structured conversation:
1. What does the skill do?
2. When should it trigger?
3. What inputs does it need?
4. What output format?
5. What edge cases should it handle?
6. What examples can you give?

The output is a complete `SKILL.md` file plus optional supporting files.

*Save chat as skill.* The user invokes "Turn this into a skill" — the system distills the conversation into a skill folder.

*Skill self-improvement.* The user can attach an instruction to a skill: *"After execution, ask the user if any improvements are needed and update this skill accordingly."* This makes the skill a learning artifact.

**Non-functional requirements.**
- Skill Library loads in < 500ms.
- Skill creation via Skill Creator completes in < 2 minutes for a simple skill.

**API surface.**
- `GET /api/v1/skills` — list available skills (built-in + user's + shared).
- `POST /api/v1/skills` — create skill (accepts skill folder as a tarball or JSON-serialized form).
- `GET /api/v1/skills/{id}` — get skill content.
- `PATCH /api/v1/skills/{id}` — update skill.
- `DELETE /api/v1/skills/{id}` — delete skill.
- `POST /api/v1/skills/{id}/share` — share with users/groups/org.
- `POST /api/v1/skills/from-chat/{chat_id}` — generate a skill from a chat.

**Data model.**
- `Skill`: id, name, title, description, version, author, tags, frontmatter (JSONB), content, owner_id, scope (personal|group|org|builtin), created_at, updated_at.
- `SkillFile`: skill_id, path, content_blob_id.
- `SkillAttachment`: chat_id, skill_id, attached_at, order.

**Dependencies.** Inference Gateway, Knowledge Service.

**Skill inspectability (cross-cutting principle).** Every skill that affects a chat must be inspectable by the user. When a skill is attached to a chat, when Enhance Prompt is acting on the user's input, when an autonomous-layer agent (M4) reads a skill to decide an action — in every case the user can click through to read the actual SKILL.md and its supporting files. This is a foundational transparency principle of the project, not an Enhance-Prompt-specific feature. The skill inspector renders the skill's contents in a side panel with:

- The full SKILL.md (frontmatter + body).
- Each supporting file as a separate tab.
- A "where this came from" line: builtin / authored by [user] / shared by [user/group/org] / forked from [parent skill].
- A "fork this skill" affordance for users who want to create their own version.

The corresponding API endpoint is `GET /api/v1/skills/{id}/contents`, which returns all files in the skill folder. Skills are not opaque artifacts; they are open-source work product the user can read, modify, and replace.

**Skill-input-form pattern.** Skills declare their required and optional inputs in the `inhouse:` frontmatter namespace (see §3.4 skill format). When a skill is attached to a chat and required inputs are not yet provided, the application surfaces those inputs as a structured form-like prompt rather than letting the model ask for them in the response. This pattern is used by Enhance Prompt (§3.2) and by any other skill author who wants their skill to feel form-driven rather than purely conversational. The application:

- Reads `inputs.required` and `inputs.optional` from the skill's frontmatter.
- Identifies which required inputs have not been provided (via prior conversation, attached files, or explicit user input).
- Renders the missing inputs as form elements (single-select for enums, text fields for free text, file pickers for documents).
- Submits the prompt with structured input values once the user provides them.

The API endpoint `GET /api/v1/skills/{id}/inputs` returns the skill's input schema for use by the application UI.

**Open questions.**
- Should skills support arbitrary code execution (`scripts/`)? Recommend: yes, but sandboxed, opt-in, and permission-gated. Not in v1; defer to M4.

### 3.5 Files / Knowledge Bases

**Description.** Persistent collections of documents accessible across chats. Files are uploaded once, ingested into the citation pipeline, and made available for retrieval. Knowledge Bases group files for shared access (e.g., "Privacy Compliance Library," "Standard Templates").

**User stories.**
- As a user, I upload my company's standard MSA template once and reference it across many chats.
- As a user, I create a "GDPR Reference" Knowledge Base with the regulation, guidelines, and our internal policies.
- As a user, I share a Knowledge Base with my team.
- As a user, I ask a question and the system retrieves from the relevant Knowledge Base automatically.

**Functional requirements.**
- File upload via drag-and-drop or file picker.
- Supported formats v1: PDF, DOCX, TXT, MD, RTF, HTML.
- Document ingestion runs the Citation Engine pipeline (§3.3).
- Knowledge Bases can have multiple files; files can belong to multiple Knowledge Bases.
- Per-file and per-KB sharing controls (personal, group, org).
- `#` command in chat to attach a file or KB inline.

**Non-functional requirements.**
- Upload progress visible to user.
- Ingestion happens asynchronously; chat is usable immediately, citations from this file become available when ingestion completes.

**API surface.**
- `POST /api/v1/files` — upload file.
- `GET /api/v1/files` — list files.
- `GET /api/v1/files/{id}` — file metadata.
- `DELETE /api/v1/files/{id}` — delete file.
- `POST /api/v1/knowledge-bases` — create KB.
- `POST /api/v1/knowledge-bases/{id}/files` — add file to KB.

**Data model.**
- `File`: id, owner_id, filename, mime_type, size, storage_path, ingestion_status, scope, created_at.
- `KnowledgeBase`: id, owner_id, name, description, scope, created_at.
- `KnowledgeBaseFile`: kb_id, file_id.

**Dependencies.** Document Pipeline (§3.3), Knowledge Service.

**Open questions.** None blocking.

### 3.6 Research

**Description.** Real-time legal information retrieval from authoritative sources, with the same Citation Engine fidelity as document-based citations. Web sources are fetched, parsed, and treated as ephemeral documents in the citation pipeline.

**User stories.**
- As a user, I ask "what does GDPR Article 28 require for processors?" and receive an answer with citations to the official EUR-Lex source.
- As a user, I ask about a recent SEC rule and the system fetches the relevant Federal Register entry.
- As a user, I see clear source attributions and can click through to the original.

**Functional requirements.**
- Web search via configured providers: SearXNG (default, self-hosted, MIT), Tavily, Brave, Google PSE, Kagi (operator-configurable).
- *Legal source connectors* with direct fetchers and source-specific parsing:
  - CourtListener (US case law, free)
  - GovInfo (US federal documents)
  - Congress.gov
  - Federal Register
  - EUR-Lex (EU law)
  - SEC EDGAR
- Fetched content runs through the document pipeline; citations work the same way as for uploaded files.
- Source-priority configurable: operator can boost certain domains (e.g., "always prefer .gov over secondary commentary").

**Non-functional requirements.**
- Research query end-to-end latency: < 15s for a typical question.

**API surface.**
- `POST /api/v1/research` — run a research query, return answer with citations.
- `GET /api/v1/research/sources` — list configured search providers and legal source connectors.

**Data model.**
- Research results are stored as ephemeral documents in the citation pipeline; standard `Document` and `CitableChunk` entities.
- `ResearchQuery`: id, user_id, query, sources_used, results_summary, created_at.

**Dependencies.** Document Pipeline, Knowledge Service.

**Open questions.**
- Should research results be cached? Recommend: yes, with a configurable TTL (default 24h), and the cache is queryable as a "Research Cache" knowledge base.

### 3.7 Playbooks

**Description.** Structured, reusable contract-review automation. A Playbook codifies an organization's standard positions and fallback positions on common contract issues. When applied to a contract, the Playbook produces a per-position assessment: matches standard, deviates (with severity), or missing entirely. Includes redline suggestions.

**User stories.**
- As a user, I select "Apply NDA Playbook" against an uploaded NDA; the system produces a structured review report.
- As a user, I see for each position: the standard language, what the contract says, the assessment, and a suggested redline.
- As a user, I create a custom Playbook by uploading 5–10 prior negotiated agreements; the system clusters typical positions and drafts a Playbook for my approval.
- As a user, I edit Playbook positions via a structured editor.
- As a user, I run a Playbook from inside Microsoft Word against the open document.

**Functional requirements.**

*Playbook schema.*

```python
class Playbook(BaseModel):
    id: UUID
    name: str
    contract_type: str  # "NDA"|"MSA-SaaS"|"MSA-Commercial"|"DPA"|...
    description: str
    version: str
    positions: List[Position]

class Position(BaseModel):
    id: UUID
    issue: str  # "Limitation of Liability"
    description: str
    standard_language: str  # the org's preferred clause
    fallback_tiers: List[FallbackTier]  # ranked acceptable alternatives
    redline_strategy: str  # how to redline if deviating
    severity_if_missing: Literal["critical", "high", "medium", "low"]
    detection_keywords: List[str]  # to find this issue in a contract
    detection_examples: List[str]  # example clauses for embedding-based matching
```

*Built-in playbooks (M3 release).*
- Generic SaaS MSA Playbook
- NDA Playbook (mutual + unilateral variants)
- DPA Playbook (GDPR-aligned)
- Commercial MSA Playbook (purchase-side)

*Easy Playbook (auto-generation).* Wizard:
1. Upload 5–20 prior agreements of the same contract type.
2. System extracts clauses, clusters by issue, identifies the user's most-common positions.
3. System drafts a Playbook with suggested standard language and fallback tiers.
4. User reviews, edits, approves.

*Playbook execution.* LangGraph workflow:
1. Parse target contract via Document Pipeline.
2. For each Playbook position, retrieve the matching clause(s) in the target contract via hybrid search.
3. Classify: matches standard / matches fallback tier N / deviates / missing.
4. For deviations, draft a redline using the redline_strategy.
5. Compile into a structured review report with citations.

*Playbook execution in Word.* The same LangGraph workflow runs against the Word document via the Office.js add-in, with redlines applied as Word tracked changes and assessments as Word comments.

**Non-functional requirements.**
- Playbook execution against a 50-page MSA: < 3 minutes.
- Easy Playbook generation from 10 prior agreements: < 10 minutes.

**API surface.**
- `GET /api/v1/playbooks` — list playbooks.
- `POST /api/v1/playbooks` — create playbook.
- `POST /api/v1/playbooks/easy` — start Easy Playbook generation.
- `GET /api/v1/playbooks/easy/{id}` — check generation status.
- `POST /api/v1/playbooks/{id}/execute` — execute against a target document.
- `GET /api/v1/playbook-executions/{id}` — get execution result.

**Data model.**
- `Playbook` and `Position` as schemas above.
- `PlaybookExecution`: id, playbook_id, target_document_id, user_id, status, results (JSONB), created_at, completed_at.

**Dependencies.** Document Pipeline, Inference Gateway, Knowledge Service.

**Open questions.**
- How granular are the redline suggestions? Recommend: redlines are structured ({old_text, new_text, justification}) so they can be applied either as Word tracked changes or rendered as a diff in the web UI.

### 3.8 Multi-Model Ensemble Verification

**Description.** GC.AI markets "multi-model RAG (calls 5 different AI models)" as an accuracy feature. InHouse AI implements this as an *optional* ensemble step where multiple models are queried in parallel and their outputs are reconciled. Off by default (cost reasons); on for specific high-stakes operations like Playbook execution and Citation Engine verification.

**User stories.**
- As an operator, I configure ensemble mode for the Citation Engine verification step.
- As a user, I see a confidence score on the answer reflecting agreement across models.
- As an operator running Mode 2 (local Ollama only), the ensemble degrades gracefully to "diversified prompts on the same model" rather than failing.

**Functional requirements.**
- Ensemble runs N parallel model calls (configurable, default N=3 in cloud mode, N=1 in pure-local mode).
- Models can be different providers (Anthropic + OpenAI + Google) or the same provider with different models, or in local mode the same model with different temperatures and prompt phrasings.
- Reconciliation step: a final model call (or deterministic logic) resolves disagreements.
- Cost tracking: ensemble calls are tagged so operators see ensemble vs single-model spend.

**Non-functional requirements.**
- Ensemble adds at most 30% latency over the slowest single call (parallelism, not sequential).

**API surface.**
- Ensemble is invoked internally by other capabilities; not a user-facing endpoint. Configuration via:
- `GET /api/v1/admin/ensemble-config` and `PATCH /api/v1/admin/ensemble-config`.

**Dependencies.** Inference Gateway.

**Open questions.**
- Reconciliation strategy: voting (for classification tasks), LLM judge (for open-ended), or both? Recommend: configurable per-capability, with sensible defaults.
- **Inference tier exposure for multi-tier ensembles.** When the ensemble spans multiple Inference Tiers (a chat using Tier 3 cloud + Tier 1 local for cross-verification), how is the chat's effective tier represented in the UI (§3.13)? Recommended resolution: surface the *minimum* tier across the ensemble as the chat's effective tier, since that is the privacy posture that actually applies — every model in the ensemble has seen the data, so the chat's effective tier is the floor.

### 3.9 Word Add-In (M3)

**Description.** Microsoft Office.js add-in that brings InHouse AI capabilities directly into Word. Users can run skills, execute Playbooks, get redlines, ask questions about the document, and act on the assistant's suggestions — all without leaving Word.

**User stories.**
- As a user editing an MSA in Word, I open the InHouse AI pane and click "Apply MSA-SaaS Playbook"; the system reviews the document and applies tracked changes + comments.
- As a user, I select a clause and ask "make this more favorable to us as the customer"; the redline appears as a tracked change.
- As a user, I ask a question about the document and the answer appears in the side pane with citations to specific clauses.
- As an admin, I distribute the add-in to my organization via the Microsoft 365 Admin Center.

**Functional requirements.**
- Word add-in (manifest XML + hosted JS bundle) communicates with the same FastAPI backend as the web app.
- Add-in authenticates via OAuth with the InHouse AI deployment.
- Supported Word clients: Desktop (Win/Mac), Word Online, Word for iPad.
- Capabilities exposed in Word:
  - Chat against the open document
  - Apply skills to selection or whole document
  - Execute Playbooks against the document
  - Generate redlines as Word tracked changes
  - Generate comments as Word comments
  - Insert AI-drafted clauses at cursor
  - **Inference Tier badge** in the task pane mirroring the web UI (per §3.13). Click opens the same tier-detail panel the web UI uses.
- The task pane is structured to accept a future "Today view" compact equivalent (per §8.5 forward-looking M5+ workflow intelligence) without architectural change; the M3 task pane reserves the slot.

**Non-functional requirements.**
- Add-in pane loads in < 2s.
- Playbook execution renders progressive results (don't block on full completion).

**API surface.**
- The Word add-in uses the same OpenAPI surface as the web app. No Word-specific backend endpoints.

**Distribution.**
- Enterprise sideload first (manifest + hosted JS distributed via Microsoft 365 Admin Center).
- AppSource public listing as a follow-up.

**Dependencies.** All backend capabilities. Office.js (Microsoft, free).

**Open questions.**
- Hosting of the add-in JS bundle: where does it live for self-hosted deployments? Options: (a) bundled with the InHouse AI deployment and served by it; (b) hosted on a LegalQuants-controlled CDN; (c) downloadable from GitHub releases. Recommend (a) — self-hosted deployment serves its own add-in, minimizing external dependencies.

### 3.10 Autonomous Layer (M4)

**Description.** Long-running per-user agents that observe activity, learn patterns, take proactive actions, and create skills autonomously. Runs as OpenWebUI Pipelines, off by default, opt-in per user.

**User stories.**
- As a user, I opt in to "autonomous skill suggestions"; after I review my fifth SaaS DPA, the system asks if I'd like it to draft a custom DPA Playbook based on my reviews.
- As a user, I configure a watch on a Knowledge Base; when new documents arrive, the autonomous agent runs a configured Playbook and notifies me of issues.
- As a user, I schedule a weekly compliance scan against our standard contract repository.
- As a user, I see a "memory" view showing what the autonomous agent has learned about my preferences.

**Functional requirements.**
- Autonomous agents run as background pipelines, not user-facing requests.
- Per-user persistent memory store (separate from chat history) tracks patterns, preferences, and past actions.
- Memory is *user-curated* — the user can view, edit, delete entries.
- Cron scheduling for periodic tasks.
- Notifications via email, Slack, or in-app.
- Hard isolation between users — no cross-user memory leakage.

**Non-functional requirements.**
- Autonomous activity must not interfere with interactive use; runs at lower priority.

**API surface.**
- `GET/POST /api/v1/autonomous/memory` — view and edit user memory.
- `GET/POST /api/v1/autonomous/schedules` — manage scheduled tasks.
- `GET/POST /api/v1/autonomous/watches` — manage watches.

**Dependencies.** All other capabilities. OpenWebUI Pipelines framework.

**Open questions.**
- This is M4 territory; detailed design deferred. The PRD commits to the capability and the architectural slot, not to the full design.
- **Distinction from Projects (§3.11).** Autonomous-layer memory is system-curated and observed; Project context is user-curated and matter-scoped. Both serve different purposes; one informs the other. The autonomous layer can *propose* additions to a Project's context, but the user owns the Project.
- **Forward extension to M5+ (§8.5).** The autonomous layer's memory and scheduled-pipelines substrate is the foundation on which the M5+ workflow-intelligence direction extends. M4 design choices should anticipate that extension — particularly multi-step agents that take external-side-effecting actions with human approval gates, since retrofitting that into a memory-and-watches-only autonomous layer is harder than designing for it from the start.

---

### 3.11 Projects (M1)

**Description.** A Project is a user-curated container that scopes a set of chats, files, skills, playbooks, and a free-form context document around a single matter — a deal, a counterparty, a regulatory question, a policy refresh. Chats inside a Project automatically inherit the Project's attached files and skills. The Project's free-form context document ("we are the customer; counterparty is Acme; their counsel is Smith Crowell; we agreed to a 12-month liability cap last round") is read into every chat in the Project as context. Projects are the operational answer to the question "what about *this matter*?" — distinct from per-chat attachments (which solve "this conversation") and from autonomous-layer memory (which is system-curated rather than user-authored).

Persistent matter memory is the single most-cited capability across in-house users in the competitive research and is the reason GC.AI customers cite stickiness. Projects are the single most consequential capability addition to v1.

**Distinction from autonomous memory (§3.10).** Autonomous-layer memory is system-curated, derived from observed user activity, and runs as background pipelines. Project context is user-curated, explicitly authored, and matter-scoped. They complement: the autonomous layer can *propose* additions to a Project's context, but the user owns the Project.

**User stories.**
- I create a Project for "Acme MSA renewal," attach the prior MSA, our standard MSA template, and the MSA Playbook. Three chats later, the latest chat still knows we are the customer and what was negotiated last round.
- I share a Project with a teammate; both of us see the same matter context.
- I archive a Project when the matter closes; it is searchable but does not clutter the active list.
- I mark a Project as `privileged: true`. The application enforces a minimum inference tier (default Tier 2), disables anonymization (which complicates a privilege analysis), and marks every chat and audit-log entry in the Project as privileged for later e-discovery filtering.

**Functional requirements.**
- Project as a top-level resource with name, description, free-form context document (Markdown), attached files, attached skills, attached playbooks, default model alias, owner, share scope, optional `privileged` flag, optional `minimum_inference_tier`.
- Chats can be created inside or outside a Project; chats inside a Project inherit its attachments and context.
- A user can move a chat into or out of a Project.
- Project context document is editable as Markdown.
- Search across Projects and search within a Project are both supported.
- Skill inspectability extends naturally — viewing a skill in a Project context shows the skill itself plus the Project's note "this skill is attached at the Project level."

**API surface.**
- `POST /api/v1/projects` — create.
- `GET /api/v1/projects` — list (filter by owner, share scope, archived).
- `GET /api/v1/projects/{id}` — fetch with attachments and context.
- `PATCH /api/v1/projects/{id}` — update name, description, context, attachments, privileged flag, minimum_inference_tier.
- `DELETE /api/v1/projects/{id}` — delete (soft-delete with retention per audit policy).
- `POST /api/v1/projects/{id}/chats` — create a chat inside this Project.
- `POST /api/v1/projects/{id}/share` — share with another user or group.

**Data model.**
- `Project` table: id, name, description, context_markdown, owner_id, share_scope, privileged (bool), minimum_inference_tier (int, nullable), archived_at (nullable), created_at, updated_at.
- `ProjectAttachment` table: project_id, attachment_type (file / skill / playbook), attachment_id.
- `Chat` table gains a nullable `project_id` field (FK to Project).

**Dependencies.** Conversational Core (§3.1), Files / Knowledge Bases (§3.5), Skill Service (§3.4), Playbooks (§3.7), RBAC (§5.2), Audit Logging (§5.3).

**Architectural placement.** No new service required. Fits within the existing FastAPI backend. Reference architecture diagram in §2.1 should show Projects as a top-level resource alongside Files / Skills / Playbooks.

---

### 3.12 Organization Profile (M1)

**Description.** A singleton skill that captures the organization's voice, templates, and "what good looks like" reference, available as ambient context to every chat and skill execution in the deployment. The Organization Profile is implemented as a skill with `inhouse: { is_organization_profile: true }` frontmatter — same skill format as everything else, same inspectability, same fork-and-replace pattern, but treated as a singleton by the Skill Service. Single-instance per deployment; admin-edited; user-readable.

**Why a singleton skill (rather than a separate construct).** Treating the Organization Profile as a skill with special metadata preserves the architectural simplicity (one extensibility surface, not two) and the transparency principle (the Organization Profile is open source and inspectable like every other shaping artifact — see §1.3).

**User stories.**
- As an admin, I create the Organization Profile capturing our company's tone of voice, our standard contract preferences, our key clauses, our typical counterparty types, and our internal escalation paths.
- As a user, every chat I open implicitly reads the Organization Profile as context. The same NDA Review skill produces output calibrated to our standards.
- As a contributor, I can fork the Organization Profile, propose changes through the standard skill PR flow, and version it.

**Functional requirements.**
- Organization Profile is a skill (same SKILL.md format).
- The skill is marked as singleton via frontmatter — the Skill Service ensures only one Organization Profile exists per deployment.
- The Organization Profile is admin-editable but user-readable; the Skill Inspector (§3.4) shows it like any other skill.
- The Organization Profile is automatically applied as ambient context to every chat unless the user explicitly opts out for that chat.
- First-run onboarding (§6.2) prompts the operator to create or import an Organization Profile (or skip and create later).

**Data model.** Reuses Skill Service tables; the singleton constraint is enforced at the application layer.

**API surface.** Reuses Skill Service endpoints with the singleton constraint.

**Dependencies.** Skill Service (§3.4). No new architectural component.

---

### 3.13 Inference Tier Awareness (M1)

**Description.** A persistent badge in the chat UI shows the current Inference Tier (1–5) and the specific provider routing for the current chat. A click on the badge opens a panel explaining what the tier implies: where the data is going, what the provider's retention policy is, whether the prompt is being logged in the operator's audit log, whether anonymization (§4) is on, and whether the deployment is air-gapped. The same panel is available in the Word add-in. This is the most important security-posture feature of the entire project and one of the smallest pieces of code: every chat already routes against an inference provider; the application already knows which one; surfacing that to the user is a UI affordance away. The transparency philosophy in §1.3 requires it.

**User stories.**
- I look at my chat header and see "Tier 3 — Anthropic Enterprise (ZDR)." I know what that means.
- I have a privileged communication to draft. I look at the badge and see "Tier 4 — OpenAI standard." I downgrade my chat to the local Tier 1 model before continuing, or I cancel and use a Project that requires Tier 1–2.
- I am an admin. I configure the deployment to refuse Tier 4–5 routing globally; users see a "Tier 4 not allowed by your administrator" message if they try.
- I author a skill. I declare in the skill's frontmatter `inhouse: { minimum_inference_tier: 2 }`. The application refuses to run the skill if the routed tier is below 2 and shows the user why.

**Functional requirements.**
- A `Tier` enum (1–5) with rules for derivation from the routed provider/model and the gateway's configuration.
- The Inference Gateway annotates every routed request with its derived tier; the backend includes the tier in the chat metadata.
- The web UI displays the tier badge in the chat header and in the prompt-input area.
- The Word add-in displays the tier in its task pane.
- Skills can declare `minimum_inference_tier` in their frontmatter (default: none).
- Projects (§3.11) can declare `minimum_inference_tier`.
- The deployment configuration can declare `allowed_inference_tiers` globally and per-group.
- Tier-violation attempts are logged in the audit log.
- The tier-detail panel renders provider-specific compliance facts pulled from the Provider Compliance Matrix (`docs/compliance/provider-compliance-matrix.md`).

**API surface.**
- `GET /api/v1/inference/current-tier?provider={provider}&model={model}` — returns derived tier and human-readable explanation.
- `GET /api/v1/inference/tier-config` — returns the deployment's allowed-tier configuration.
- `PATCH /api/v1/admin/inference/tier-config` — admin-only configuration update.

**Data model.**
- Existing `Message` row gains a `routed_inference_tier` field.
- Existing `Skill` and (per §3.11) `Project` rows gain `minimum_inference_tier`.
- Configuration adds `inference_tiers` block to `gateway.yaml` and global config.

**Dependencies.** Inference Gateway (§4), Skill Service (§3.4), Conversational Core (§3.1), Provider Compliance Matrix (documentation deliverable in M1).

**Architectural placement.** The tier derivation is a small piece of Inference Gateway code. The UI rendering is a header component in the OpenWebUI fork and a corresponding panel in the Word add-in. No new service required.

**Open questions.**
- How do we handle ensemble verification (§3.8) where the ensemble spans multiple tiers? Recommended resolution: surface the *minimum* tier across the ensemble as the chat's effective tier, since that is the privacy posture that actually applies.
- Do we expose tier downgrade prompts ("the model you have access to is Tier 1; the answer would be better at Tier 3 — would you like to switch and re-run?") proactively? Recommend: yes, but only when the user has already explicitly opted in to the upgrade in their account preferences. Do not nudge by default.

---

### 3.14 Tabular / Multi-Document Review (M3)

**Description.** A view that takes (a) a set of documents (a Knowledge Base, a Project's files, a free selection) and (b) a set of questions or clauses to extract, and produces a row-per-document, column-per-question grid. Each cell is a citation-grounded answer that opens the side-panel viewer (§3.3) on click. The "compare clauses across N contracts in a grid" pattern (Legora Tabular Review, Harvey Vault, Ivo Repository columns) is a different UI shape than chat. In-house teams use it for due diligence, audits, portfolio-wide policy checks, and "what is market across the deals we have signed."

**User stories.**
- I select 30 NDAs and ask "what is the term length, the survival period, the carveouts, and the governing law for each?" — I get a 30-row, 4-column table with citations.
- I select a Project's files and ask "show me defined-terms inconsistencies across these documents."
- I export the table as XLSX or CSV.

**Functional requirements.**
- Tabular Review runs as a LangGraph workflow: for each document × column, run a skill-like extraction with the Citation Engine.
- Columns can be specified ad hoc, saved, and reused (a "Tabular Review skill" — same skill format, output type is `table` not `report`).
- Cells link to the cited chunk(s) in the source document.
- Failed extractions render as "not found" with a "verify" affordance, never as a confident wrong answer.
- Bulk operations: "redline column 3 in all rows," "draft a memo summarizing column 5."
- Cost preview before execution; user confirms (200 docs × 10 columns = 2,000 model calls is non-trivial).

**Architectural fit.** This is mostly a new Skill output type plus a UI surface. The Citation Engine (§3.3), Document Pipeline, Knowledge Service (§3.5), and LangGraph runtime all already exist for it. Update §3.4 (Skill format) to document the `output_format: table` mode.

**Open questions.**
- Should ensemble verification (§3.8) be on by default for tabular cells, given the volume? Recommended: yes for high-stakes columns, configurable per-column.

**Dependencies.** Citation Engine (§3.3), Skill Service (§3.4), Files / Knowledge Bases (§3.5), Inference Gateway (§4), LangGraph runtime.

---

### 3.15 Slack / Teams Light Intake Bridge (M3)

**Description.** A Slack and Teams bot that supports two flows: (1) **forward as a chat** — a user `/inhouse` slash-command on a message thread creates an InHouse AI chat with the thread's content as initial context; (2) **quick ask** — `/inhouse ask "is this an MSA or an order form?"` runs a short skill (configurable via Org Profile) and replies in-thread. Replies render in the Slack/Teams thread; deeper engagement opens the web app. No matter management, no triage, no SLA tracking — that is the boundary with Streamline AI's category, which is explicitly out of scope per §1.6.

In-house teams report (across the competitive research) that the majority of incoming requests arrive via Slack, Teams, or email — not via direct visits to the legal portal. A web-only product structurally underweights the channels users live in. A *light* Slack/Teams bridge — not full intake/triage like Streamline AI — closes this gap with bounded scope.

**Functional requirements.**
- OAuth-based install on the org's Slack or Teams.
- Permission model: bot can only post in channels it is invited to; bot does not read silent channels.
- Confidentiality: thread contents are stored in InHouse AI under the user's chat history, with the same RBAC as any other chat.
- Bot configuration is in the InHouse AI admin UI, not in Slack.

**Architectural fit.** Optional service in the Docker Compose (`slack-bridge`, `teams-bridge` with `--profile slack` etc.). Reuses Conversational Core, Auth/RBAC, Skill Service. No new core architecture.

**Dependencies.** Conversational Core, Auth/RBAC, Skill Service.

---

### 3.16 Contract Repository — Auto-Relationship Detection (M4)

**Description.** A pipeline that runs over a Knowledge Base of contracts and produces a relationship graph: amendments (modifies-X), restatements (replaces-X), references (cross-references-X), and master/sub (parent-of-X) edges. The graph is queryable and visible in the UI as a sidebar on each document. Contracts about a counterparty rarely stand alone, and answering questions like "which liability cap actually governs?" requires knowing which document supersedes which. This is Ivo's positioning — that contracts are not isolated documents but a graph — and is not currently addressed in the PRD's flat Knowledge Base model.

**Functional requirements.**
- Detection runs as a Knowledge Base post-ingestion step or on demand.
- A skill or LangGraph workflow analyzes each new document's references and signals (effective date, "this Amendment Number 3 to the MSA dated ..."), proposing edges.
- Edges are user-confirmable; not all detections are correct.
- When asked a question scoped to a Knowledge Base, the system uses the graph to determine the operative document chain ("for this question about liability caps, the operative documents are the MSA + Amendment 2 + the side letter, but not Amendment 1 which Amendment 2 superseded").

**Architectural fit.** Mostly a new resource type (contract-relationship edges) plus skills that produce and consume them. Edges stored in the existing Postgres (a graph extension is a deferred enhancement candidate; not required for v1). No new external dependencies.

**Dependencies.** Document Pipeline, Knowledge Service (§3.5), Skill Service (§3.4).

---

## 4. The InHouse AI Inference Gateway

### 4.1 Why We Build This

Every other component in this stack is something we adopt from the OSS ecosystem. The Inference Gateway is the one component we build ourselves, for two reasons:

1. **Security surface.** This is the component holding privileged API keys for cloud LLM providers. Operators deploying InHouse AI will trust it with significant credentials. The candidate alternative (LiteLLM) has a non-trivial vulnerability history including proxy auth bypasses and SSRF in document loaders. For an open-source project where users may run with our defaults, that surface is unacceptable.
2. **Scope match.** We need a focused subset of functionality — about 15% of LiteLLM's feature surface. Building it ourselves yields ~3,000 lines of code that is fully auditable, has zero supply-chain risk, and ships without features we don't need carrying maintenance burden.

The Inference Gateway is a separate container, importable as a standalone service, with its own OpenAPI specification. Other open-source projects can use it independently.

### 4.2 Functional Scope

**In scope.**
- OpenAI-compatible API surface (`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/models`).
- Streaming responses (SSE pass-through).
- Provider adapters for: Anthropic, OpenAI, Google Vertex, Cohere, Azure OpenAI, AWS Bedrock, Ollama, vLLM, llama.cpp (any OpenAI-compatible local endpoint).
- Provider routing rules (per-model, per-tag, per-capability).
- Fallback chains (provider A fails → try B → try C).
- Rate limiting per-key and per-model (Redis-backed token bucket).
- Cost tracking per-request (tokens × per-model rates from a config file).
- Model aliases (operator can define "fast", "smart", "cheap" → resolves to specific provider+model).
- Health checks per provider.
- Structured logging.
- OpenTelemetry instrumentation.
- **Tier derivation** (new in v0.2): every request is annotated with its derived Inference Tier (1–5 per §1.5.2 and §3.13) based on the routed provider/model and the gateway's configuration. The tier is included in the response metadata for the application to display.
- **Anonymization middleware** (new in v0.2; M2): an optional pre/post middleware stage that pseudonymizes sensitive entities before the model call and rehydrates them after. See §4.7 for detail.

**Out of scope.**
- Prompt caching (defer to v2).
- Fine-tuning management (out of scope entirely; that's the operator's relationship with the provider).
- Vector search (handled by the Knowledge Service, not the Gateway).
- Multimodal beyond what providers natively support.

### 4.3 Architecture

```
                         OpenAI-compatible API
                                    │
                                    ▼
                         ┌──────────────────┐
                         │  FastAPI surface │
                         └────────┬─────────┘
                                  │
                ┌─────────────────┼──────────────────┐
                ▼                 ▼                  ▼
        ┌─────────────┐    ┌──────────────┐   ┌─────────────┐
        │  Auth       │    │   Router     │   │  Rate Limit │
        │ (API key    │    │ (provider    │   │  (Redis     │
        │  resolution)│    │  selection,  │   │  token      │
        │             │    │  fallback)   │   │  bucket)    │
        └─────────────┘    └──────┬───────┘   └─────────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  Tier Derivation │  (annotates request
                         │  (per §1.5.2 /   │   with routed_inference_
                         │   §3.13)         │   tier; refuses if below
                         │                  │   skill/Project minimum)
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  Anonymization   │  (M2; optional pre/post
                         │  (§4.7) — pre    │   middleware; pseudonymizes
                         │                  │   PII before provider call,
                         │                  │   rehydrates on return)
                         └────────┬─────────┘
                                  │
                ┌─────────────────┼──────────────────┐
                ▼                 ▼                  ▼
        ┌─────────────┐    ┌──────────────┐   ┌─────────────┐
        │  Provider   │    │  Cost        │   │   Telemetry │
        │  Adapters   │    │  Tracker     │   │   (OTel)    │
        │             │    │              │   │             │
        │ Anthropic / │    │              │   │             │
        │ OpenAI /    │    │              │   │             │
        │ Vertex /    │    │              │   │             │
        │ Cohere /    │    │              │   │             │
        │ Azure /     │    │              │   │             │
        │ Bedrock /   │    │              │   │             │
        │ Ollama /    │    │              │   │             │
        │ vLLM        │    │              │   │             │
        └──────┬──────┘    └──────────────┘   └─────────────┘
               │
               ▼
       (provider HTTP/gRPC APIs)
               │
               ▼
        ┌──────────────────┐
        │  Anonymization   │  (post — rehydrates pseudonyms in
        │  (§4.7) — post   │   response and citations)
        └──────────────────┘
```

### 4.4 Configuration

Configuration via a single YAML file (`gateway.yaml`), reloadable without restart.

```yaml
# gateway.yaml
providers:
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
    base_url: https://api.anthropic.com
    timeout_s: 60
    rate_limit:
      requests_per_minute: 1000
      tokens_per_minute: 200000
  openai:
    api_key_env: OPENAI_API_KEY
    base_url: https://api.openai.com/v1
    timeout_s: 60
  ollama:
    base_url: http://ollama:11434
    timeout_s: 300

models:
  # Operator-defined model registry
  - alias: smart
    provider: anthropic
    model: claude-opus-4-7
    cost_per_1k_input_tokens_usd: 0.015
    cost_per_1k_output_tokens_usd: 0.075
    fallback: [smart-openai]
  - alias: smart-openai
    provider: openai
    model: gpt-4-turbo
    cost_per_1k_input_tokens_usd: 0.01
    cost_per_1k_output_tokens_usd: 0.03
  - alias: fast
    provider: anthropic
    model: claude-haiku-4-5-20251001
    cost_per_1k_input_tokens_usd: 0.0008
    cost_per_1k_output_tokens_usd: 0.004
  - alias: local
    provider: ollama
    model: llama3.1:70b

routing:
  default: smart
  capabilities:
    embeddings: openai-text-embedding-3-large
  rules:
    - when: { tag: "verification" }
      use: fast
    - when: { tag: "ensemble" }
      use: [smart, smart-openai, local]

api_keys:
  # Operator-issued keys for clients of this gateway
  - id: inhouse-ai-backend
    key_hash: <sha256 of the actual key>
    allowed_models: ["*"]
    rate_limit_override: null

# --- Inference Tier configuration (new in v0.2; per §1.5.2 / §3.13) ---
inference_tiers:
  # Map each provider/model to a tier so the application can surface it.
  # Operators can override per-deployment to reflect their contractual posture
  # (e.g., "anthropic" set to Tier 3 if the operator has a ZDR addendum).
  defaults:
    anthropic: 4         # Tier 4 by default; override to 3 if ZDR addendum is in place
    anthropic_enterprise: 3
    openai: 4
    openai_enterprise: 3
    google_vertex: 3
    aws_bedrock: 3        # under operator's AWS account → Tier 2 if customer-hosted
    azure_openai: 3       # under operator's Azure tenant → Tier 2 if customer-hosted
    cohere_enterprise: 3
    ollama: 1
    vllm: 1
    "llama.cpp": 1
  allowed_tiers_global: [1, 2, 3, 4]   # disallow Tier 5 globally; warn on Tier 4
  allowed_tiers_per_group:
    privileged-matters: [1, 2]          # privilege-flagged Projects
    privacy-sensitive: [1, 2, 3]
  warn_on_tiers: [4]                    # surface a banner when routing at this tier or below
  refuse_on_tiers: [5]                  # block the request with a clear error

# --- Anonymization Layer (new in v0.2; M2; per §4.7) ---
anonymization:
  default: disabled       # "disabled" | "preferred" | "required"
  fail_closed: true       # if anonymization fails and tier > 2, refuse the request
  entity_types:
    - persons
    - organizations
    - locations
    - monetary_amounts
    - account_numbers
    - email_addresses
    - phone_numbers
  custom_patterns:
    - name: internal_employee_id
      regex: 'EMP-\d{6}'
      replacement: 'EMPLOYEE_{N}'
  ner_backend: "spacy"     # "spacy" | "small_llm" | "hybrid"
  llm_fallback_alias: "fast"  # used for ambiguous spans when ner_backend is "hybrid"
```

### 4.5 OpenAPI Surface

OpenAI-compatible (so OpenWebUI and any OpenAI-SDK-using client just works):

- `POST /v1/chat/completions`
- `POST /v1/completions`
- `POST /v1/embeddings`
- `GET /v1/models`

Plus admin endpoints under `/admin/v1`:

- `GET /admin/v1/providers/health` — per-provider health.
- `GET /admin/v1/usage` — per-key, per-model usage and cost.
- `POST /admin/v1/config/reload` — reload `gateway.yaml`.
- `GET /admin/v1/tier-config` — return current Inference Tier configuration (defaults, allowed tiers globally and per-group, warn/refuse settings). New in v0.2 (per §3.13 / §1.5.2).
- `PATCH /admin/v1/tier-config` — admin-only update to tier configuration.
- `GET /v1/inference/current-tier?provider={provider}&model={model}` — return the derived tier and a human-readable explanation; used by the application to surface the tier badge (per §3.13).
- `GET /admin/v1/anonymization-config` — return current anonymization configuration. New in v0.2 (per §4.7).
- `PATCH /admin/v1/anonymization-config` — admin-only update.

### 4.6 Implementation Plan

- ~3,000 lines of Python (anonymization adds ~600 lines; tier derivation adds ~100 lines).
- httpx for HTTP (async), tenacity for retries.
- Pydantic for config schema validation.
- pytest with provider-mock fixtures.
- Per-provider integration tests behind environment-variable-gated marks.
- Fuzzed compliance tests against the OpenAI API spec to ensure compatibility.

### 4.7 Anonymization Layer (M2)

A pre-processing step in the Inference Gateway pipeline (per the architecture diagram in §4.3): configurable patterns and an entity-recognition pass identify sensitive spans, replace them with stable pseudonyms, send the anonymized text to the model, then post-process the response to rehydrate the pseudonyms. The mapping is held only in the deployment's process memory for the duration of the request and never persists.

**Why include in v1.** Mode 2 (full local inference, Tier 1) is one answer to the data-sovereignty question; an anonymization-then-rehydrate layer for Mode 1 with Tier 3+ is the other answer, and it is what privacy-conscious enterprises that still want cloud-LLM quality reach for. Including it positions InHouse AI's Mode 1 at parity with privacy-first commercial tools without sacrificing the cloud-LLM choice. Legalfly built a defensible category position around this; the architectural placement is straightforward middleware in the Gateway.

**Functional requirements.**
- Configured per-skill, per-Project, or per-deployment via a flag (`anonymization: required | preferred | disabled`).
- Default `disabled`. When enabled, the gateway refuses to forward to non-Tier-1/2 providers if anonymization fails (fail-closed).
- Handles common entity types: persons, organizations, locations, monetary amounts, account numbers, email addresses, phone numbers. Plus regex-based custom patterns for org-specific identifiers (employee IDs, internal codes).
- Pseudonyms are stable within a single request (the same name maps to the same pseudonym across multiple occurrences) but unique across requests.
- The mapping table for a request is logged in the audit log as hash-of-pseudonym → hash-of-original; the originals are never logged.
- Rehydration on the response side restores pseudonyms inside cited chunks too, so the citation experience stays correct.
- Inspectable: users can view the anonymized prompt the model actually saw via a "view what was sent" affordance in the chat UI.

**Backend choices.**
- Default `ner_backend: spacy` — fast, offline, deterministic; occasional misses on ambiguous spans.
- `ner_backend: small_llm` — slower, more accurate; uses the Inference Gateway's `fast` model alias for the anonymization pass.
- `ner_backend: hybrid` — spaCy first, LLM fallback only on ambiguous spans; default for production.

**Architectural placement.** Between the Router and the Provider Adapters in the Gateway pipeline (per §4.3). The Gateway already has the pieces for a pre/post middleware step.

**Open questions.**
- How does anonymization interact with the Citation Engine's character-fidelity guarantee? Verbatim substring verification operates on the original text, not the anonymized text — verification happens after rehydration. Confirmed feasible.
- Should anonymization be allowed on Tier 1 (where it adds processing without privacy benefit)? Recommend: configurable but default off for Tier 1, since the entity is staying local anyway and rehydration adds an extra failure mode.

**Privilege interaction.** Per §3.11 and §1.8, Projects flagged `privileged: true` disable anonymization by default. Anonymization rehydration introduces an additional process step that complicates a privilege analysis; for privileged content, the operator is better served by Tier 1 with no third-party touch.

**Dependencies.** Inference Gateway core (§4.1–§4.6), Citation Engine (§3.3).

---

## 5. Cross-Cutting Concerns

### 5.1 Authentication and Authorization

The InHouse AI **backend (FastAPI) owns authentication**. The web client (the OpenWebUI fork) and the Word add-in are configured to delegate to the backend's auth surface rather than running OpenWebUI's built-in auth. There is one identity store, one session model, and one audit-log trail across all surfaces. (Earlier PRD drafts described "v1 uses OpenWebUI's built-in auth" — that direction was reversed during M1 planning when the OpenAPI surface and the backend's audit-log requirements made backend-owned auth the simpler architecture. The decision is recorded in `docs/adr/0002-backend-owned-auth.md`.)

**Identity and credentials.**
- Local accounts with bcrypt-hashed passwords as the v1 baseline. Email and display name on every account.
- OAuth (Google, Microsoft, GitHub), SAML 2.0, LDAP / Active Directory, SCIM 2.0, and trusted-header SSO are first-class IdP integrations. The backend implements each as a pluggable auth provider; the OpenWebUI fork does not do its own IdP integration.
- Operators with complex IdP needs front the deployment with Authentik or Keycloak via reverse proxy; the backend trusts the proxy's authenticated headers. Documented integration recipe.

**Sessions and tokens.**
- Web client (OpenWebUI fork) and Word add-in use short-lived JWT access tokens (~15 min) plus longer-lived refresh tokens (default 7 days, hashed at rest in the `user_sessions` table). Refresh tokens are rotated on each refresh.
- Programmatic clients use API tokens with scoped permissions; tokens are listable and revocable per-user.
- Every API request authenticates via `Authorization: Bearer <jwt>` in the standard FastAPI dependency.

**MFA-mandatory option** (M1): operators can configure the deployment to require multi-factor authentication for all logins. The backend implements TOTP via `pyotp` (M1) with WebAuthn as a tracked enhancement (DE-### TBD). Recovery codes are single-use, hashed at rest, and rotated when the user re-enrolls. Configuration is documented in the deployment guide as a recommended default for any deployment handling client-confidential data.

**Session timeouts** (M1): configurable absolute and idle timeouts; default 8 hours absolute, 30 minutes idle. Both are enforced in the backend; the OpenWebUI client respects them by 401-on-expired-token.

**Role-bounded admin actions audit** (M1): admin actions on the audit log itself, RBAC changes, and tier-config changes are logged with elevated detail and cannot be silently dropped.

### 5.2 RBAC

- Three default roles: **Admin**, **Member**, **Viewer**.
- Permissions on every resource: read, write, share, delete.
- Custom roles supportable via OpenWebUI's existing role system.
- All API endpoints enforce permissions via FastAPI dependency injection.

### 5.3 Audit Logging

- Every state-changing API call writes to an `audit_log` table.
- Read-only access to audit log via `/api/v1/admin/audit-log` (admin role only).
- Audit log entries: timestamp, actor_user_id, action, resource_type, resource_id, before_state_hash, after_state_hash, ip_address, user_agent, **`privilege_marked`** (boolean — set when the action affects a privilege-flagged Project per §3.11; new in v0.2), **`privilege_basis`** (free-text reference to the matter or instruction that establishes privilege; new in v0.2), **`routed_inference_tier`** (where the action involved an inference call; populated from the Gateway's tier annotation per §4 and §3.13).
- Audit log export to JSON or CSV.
- Optional log streaming to operator's SIEM via syslog or HTTP webhook.
- **Per-user data export (M1).** A user can download all their chats, files, skills, and Project content as a portable bundle via `POST /api/v1/users/{id}/export`. Includes the WorkProductAttribution metadata (per §3.3) for chain-of-custody.
- **Per-user data deletion (M1).** A user can delete their account and all associated content (chats, files, skills, autonomous-layer memory, Projects they own) via `DELETE /api/v1/users/{id}`. This is a GDPR Article 17 minimum for any deployment serving EU data subjects.
- **Tamper-evidence and cryptographic timestamping** are deferred enhancements (per §9 Security and Compliance), not v1 commitments. The v1 audit log relies on the operator's database integrity; tamper-evidence layers come later.

### 5.4 Observability

- OpenTelemetry instrumentation in every service.
- Default OTel exporter: OTLP/HTTP. Operator points it at their backend (Grafana Tempo, Honeycomb, etc.).
- Langfuse self-hosted alongside the deployment for LLM-specific tracing (optional, off by default).
- `/health` and `/ready` endpoints on every service.
- Prometheus-format metrics on `/metrics`.

### 5.5 Cost Tracking

- Inference Gateway tags every request with the originating user, capability, and chat (when applicable).
- Cost per request computed from configured per-model rates.
- Aggregations exposed via `/api/v1/admin/usage` with filters (user, date range, capability).
- Operator-facing cost dashboard in the admin UI.

### 5.6 Encryption

- TLS in transit (operator provides certificates; documented Let's Encrypt recipe via Caddy or Traefik reverse proxy).
- At rest: pgcrypto-backed column encryption for sensitive fields (API keys, audit log payload).
- Storage volumes encrypted at the operator's infrastructure level (their responsibility).
- **HSM and external-secrets-manager integration** (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager) is a deferred enhancement (per §9 Security and Compliance). v1's pgcrypto column encryption is sufficient for most operators; high-assurance deployments will want pluggable secrets backends, which the v1 architecture leaves room for.

### 5.7 No Telemetry by Default

- The deployment emits no telemetry to LegalQuants or any third party by default.
- Optional opt-in anonymous usage stats (version, deployment mode, capability counts; no content) via a clearly-disclosed flag.
- Documented in privacy.md.

---

## 6. Deployment

### 6.1 Reference Docker Compose

Single `docker-compose.yml` with profiles for the two modes.

```yaml
# docker-compose.yml (excerpt)
services:
  web:
    image: legalquants/inhouse-ai-web:latest
    ports: ["3000:3000"]
    depends_on: [api]
    environment:
      INHOUSE_AI_API_URL: http://api:8000

  api:
    image: legalquants/inhouse-ai-api:latest
    ports: ["8000:8000"]
    depends_on: [postgres, redis, gateway]
    env_file: .env

  gateway:
    image: legalquants/inhouse-ai-gateway:latest
    ports: ["8001:8001"]
    volumes: ["./gateway.yaml:/etc/gateway.yaml:ro"]
    env_file: .env

  postgres:
    image: pgvector/pgvector:pg16
    volumes: ["pgdata:/var/lib/postgresql/data"]
    env_file: .env.db

  redis:
    image: redis:7-alpine
    volumes: ["redisdata:/data"]

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    volumes: ["miniodata:/data"]
    env_file: .env.minio

  # --- Mode 2 (local inference) profile ---
  ollama:
    image: ollama/ollama:latest
    profiles: ["local"]
    volumes: ["ollamadata:/root/.ollama"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  paddleocr:
    image: legalquants/paddleocr-vl:latest
    profiles: ["local"]

  # --- Slack / Teams Light Intake Bridge (M3); optional, off by default ---
  slack-bridge:
    image: legalquants/inhouse-ai-slack-bridge:latest
    profiles: ["slack"]
    depends_on: [api]
    env_file: .env.slack
    # Configure Slack OAuth in the InHouse AI admin UI; this service exposes
    # only the Slack Events API endpoint for bot interactions.

  teams-bridge:
    image: legalquants/inhouse-ai-teams-bridge:latest
    profiles: ["teams"]
    depends_on: [api]
    env_file: .env.teams
    # Configure Microsoft Teams app in the InHouse AI admin UI.

volumes:
  pgdata:
  redisdata:
  miniodata:
  ollamadata:
```

### 6.2 First-Run Experience

```bash
git clone https://github.com/legalquants/inhouse-ai.git
cd inhouse-ai
cp .env.example .env
# Edit .env with at least one LLM provider API key (or use local profile)
docker compose up -d              # Mode 1
# OR
docker compose --profile local up -d   # Mode 2
```

After ~2 minutes (first run pulls images, runs migrations, seeds skills):

```
✓ InHouse AI is ready at http://localhost:3000
✓ First-run admin account: see logs for password
✓ API documentation: http://localhost:8000/docs
✓ Inference Gateway: http://localhost:8001/docs

Next steps shown in the web UI:
1. Create your Organization Profile (§3.12) — your team's voice, templates,
   and "what good looks like." Or skip and create later.
2. Configure Inference Tier policy (§3.13) — which tiers are allowed for
   your deployment; what is the minimum for privileged work.
3. Optionally enable MFA (§5.1) and review session timeout settings.
4. Create your first Project (§3.11) and try the starter skills.
```

### 6.3 Production Deployment

- **Helm chart** for Kubernetes: `helm install inhouse-ai legalquants/inhouse-ai -f values.yaml`.
- **Reverse proxy recipes**: Caddy (simplest, automatic TLS), Traefik (production-grade), nginx.
- **Reference architectures** documented: small (single-node Docker), medium (single-node K8s with HA Postgres), large (multi-node K8s with horizontal API scale, external Postgres).

### 6.4 Air-Gapped Deployment

- All container images can be mirrored to a private registry.
- Models pulled to Ollama once, then deployment runs without internet.
- No outbound calls in Mode 2 (verified by integration test).
- Documented air-gap install guide.
- **Tier 1 framing.** An air-gapped deployment is the canonical Tier 1 deployment per §1.5.2 and §3.13. The Inference Tier badge in the chat UI shows "Tier 1 — local inference (air-gapped)" for every chat in this configuration. Skills that declare `minimum_inference_tier` are unaffected; air-gap is the most restrictive operational posture and satisfies any minimum tier requirement.

### 6.5 Backup and Restore

- Documented `pg_dump` + MinIO snapshot recipe.
- Reference cron job for nightly backups.
- Restore tested in CI.
- **Backup encryption** is a deferred enhancement (per §9 Security and Compliance): backup bundles are unencrypted by default in v1; operators are responsible for encrypting backup volumes at rest at the infrastructure level. A configurable backup-encryption-with-rotation path is on the roadmap.

---

## 7. Open Source Posture

### 7.1 Project Philosophy

InHouse AI is open source because the alternative — closed-source legal AI built on hidden prompt engineering — does not deserve the trust of the legal profession. Lawyers are licensed because their judgment is accountable to clients, courts, regulators, and ethics boards. The tools that shape that judgment should be accountable in kind. A skill that produces a wrong answer should be readable, debuggable, and forkable by the lawyer who relies on it. A playbook that codifies a position should be inspectable by the team that signed off on it. A citation engine that asserts verbatim quotes should be auditable by anyone who cares to check.

Open source is therefore not a distribution choice. It is a fitness-for-purpose requirement. A closed-source legal AI is structurally unsuited to the work it claims to do, in the same way that a black-box statute would be unsuited to law. We did not build InHouse AI as an open-source project as a marketing posture; we built it open because we could not see how to do this work honestly any other way.

This philosophy carries operational consequences worth naming explicitly:

- **Substantive contributions are welcome and credited.** Skills, playbooks, jurisdictional adaptations, and verification heuristics contributed by practicing lawyers carry the same weight in the project as code contributed by engineers. Both are work product. Both deserve attribution.
- **No "open core" gating.** Features useful to in-house legal teams are in the open-source release. We will not move features behind a paid offering as the project matures. (LegalQuants may build commercial *services* — hosted deployments, custom skill authoring, training, support — but the software itself stays whole.)
- **Forks are encouraged, not resisted.** If a customer or a community wants to build a derivative product that incorporates their proprietary improvements, the Apache 2.0 license permits it. We treat that as ecosystem health, not competition.
- **Skills are the canonical artifact of value.** When the project produces a wrong answer, the answer to "why" is almost always in a SKILL.md. Improving InHouse AI is mostly improving skills, which is mostly within reach of any practicing lawyer with a few hours and a clear view of what the right answer should have been.

### 7.2 License

**Apache License 2.0** for the InHouse AI codebase.

Rationale: patent-grant clause (important given LegalQuants' ecosystem), explicit trademark protection, enterprise-friendly, compatible with most other OSS licenses for ecosystem integration.

OpenWebUI fork (the `web` component) inherits OpenWebUI's license. We follow OpenWebUI's branding requirements and document the relationship in the README.

PyMuPDF (AGPL) is used server-side only and not redistributed as a library; the AGPL boundary is the HTTP API. Documented.

### 7.3 Trademark and Naming

- **InHouse AI** is the project name, descriptive enough that strong trademark protection is unlikely.
- **LegalQuants** is the protectable mark; remains LegalQuants' property.
- Tagline: *"InHouse AI — open-source AI for in-house legal teams, by LegalQuants."*

### 7.4 Governance

- **Initial model: BDFL.** Kevin Keller is the initial maintainer.
- LegalQuants stewards the project (owns the GitHub org, controls trademark, employs maintainer).
- Documented commitment to community contribution: "InHouse AI welcomes contributions from any in-house counsel, legal-ops practitioner, or engineer who wants to advance open legal AI."
- Path to broader governance documented but not implemented in v1: as the project matures, consider transition to a maintainer team and formal governance (see CNCF or Apache Software Foundation models).

### 7.5 Contribution Model

- **DCO sign-off**, not CLA. Industry-standard, lightweight, sufficient legal cover.
- `CONTRIBUTING.md` documents:
  - How to set up a development environment.
  - How to run tests.
  - PR process and expectations.
  - Code style (ruff + mypy for Python; Prettier + ESLint for JS).
  - Commit message conventions.
  - Sign-off requirement.
- `CODE_OF_CONDUCT.md` based on the Contributor Covenant.

### 7.6 Security Disclosure

- `SECURITY.md` documents:
  - Email address for security reports (security@legalquants.com or similar).
  - GPG key for encrypted disclosures.
  - Response time commitments (acknowledge within 72h, fix critical issues within 30d).
  - Public disclosure policy after fix.
  - **Explicit scope** — what is in-scope versus out-of-scope for security reports (added in v0.2).
  - **Safe-harbor language** — clear good-faith research protections for reporters (added in v0.2).
  - **Published list of past disclosures** with credit attribution to reporters (added in v0.2).
- GitHub Security Advisories used for coordinated disclosure.
- A formal Vulnerability Disclosure Program (VDP) on a recognized platform (HackerOne, Intigriti, or self-hosted) is a deferred enhancement (per §9 Security and Compliance).

### 7.7 Project Channels

- **GitHub Issues** for bugs and feature requests.
- **GitHub Discussions** for community Q&A.
- **Discord** (LegalQuants-hosted) for synchronous community.
- **Blog** at legalquants.com/blog for releases and roadmap updates.

### 7.8 Release Cadence and Supply-Chain Transparency

- Semantic versioning (semver).
- Releases tagged on GitHub with full changelog.
- Targeted cadence: minor release every 6–8 weeks, patch releases as needed.
- Long-term-support (LTS) designation for one minor version per year, with security backports for 12 months.

**Supply-chain transparency commitments (M1, per §1.8 and Appendix E).**

Every release ships with the following artifacts, which an operator's security team can verify before deployment:

- **Software Bill of Materials (SBOM).** Every release container image and Python wheel is accompanied by an SPDX or CycloneDX SBOM, generated automatically by Syft or equivalent and published as a release artifact. Documented at `docs/security/sbom.md`.
- **Signed container images.** Container images are signed with Sigstore/cosign; release tags are GPG-signed; signing keys and verification commands are documented at `docs/security/verifying-releases.md`.
- **SLSA-3 build provenance.** GitHub Actions workflows produce SLSA-3-aligned provenance attestations for each release, linking each image to the specific GitHub commit and Actions run that produced it. Documented at `docs/security/build-provenance.md`.
- **Public threat model.** A `docs/security/threat-model.md` document covering principal data flows: a user prompt → backend → inference gateway → provider → response → citation render. Identifies trust boundaries, threats, and mitigations. Reviewed annually; updated when major architecture changes land.
- **Continuous dependency security.** Trivy / Grype scan every container image; Dependabot or Renovate watches all dependency manifests; CodeQL or similar SAST runs on every PR; results are visible in GitHub Security tab. Documented at `docs/security/dependency-security.md`.
- **Reproducible builds.** A v1.x deferred enhancement (see §9 Security and Compliance); the v1 commitment is the SLSA-3 provenance, with reproducibility as a follow-on hardening step.

These commitments collectively answer the procurement objection "but it's open source — how do we know what's in it?" Closed-source vendors typically cannot provide SBOMs for their internal builds because their dependency surface is opaque; an open-source project's supply-chain story is structurally stronger.

---

## 8. Roadmap

Milestone-based delivery. Each milestone is a public release.

### M1 — Foundation (~6 weeks)

**Theme:** Working open-source release that operators can deploy and use for everyday legal Q&A, with the matter-context substrate (Projects + Organization Profile) and procurement-defense apparatus that distinguish InHouse AI from a generic OSS chat-with-skills product.

**Deliverables:**
- OpenWebUI fork with InHouse AI customization (logo, colors, default skills loaded).
- FastAPI backend with full OpenAPI 3.1 surface.
- Inference Gateway (cloud + Ollama, fallback, rate limiting, cost tracking).
- **Inference Tier derivation in the Gateway and Tier Awareness UI** (per §3.13 and §1.5.2). Tier badge in chat header and Word task pane; Skills/Projects can require minimum tiers; deployment can disallow tiers globally.
- RBAC with three default roles.
- **MFA-mandatory option and session-timeout defaults** documented (per §5.1).
- Files / Knowledge Bases.
- Hybrid retrieval (pgvector + FTS).
- Chat with persistent history.
- **Projects** as matter-scoped containers (per §3.11), including the optional `privileged` flag and `minimum_inference_tier` field.
- **Organization Profile** as a singleton skill (per §3.12); first-run onboarding prompts the operator to create or skip.
- **Privilege-aware audit log fields** (`privilege_marked`, `privilege_basis`, `routed_inference_tier`) per §5.3.
- **Per-user data export and deletion** (`POST /api/v1/users/{id}/export`, `DELETE /api/v1/users/{id}`) per §5.3 — GDPR Article 17 baseline.
- **Work-product attribution metadata** on every model-generated artifact (per §3.3).
- Enhance Prompt.
- Skill Library framework (with `inhouse:` namespace including `minimum_inference_tier`, `output_format`, `is_organization_profile`).
- 10 starter skills (drafted in parallel; see skill list below).
- Docker Compose deployment for both modes.
- Quickstart, configuration, and contribution documentation.
- Apache 2.0 license, CONTRIBUTING.md, SECURITY.md (with safe-harbor language and explicit scope, per §7.6), CODE_OF_CONDUCT.md.

**Compliance Alignment Pack documentation deliverables (M1, per §1.8 and Appendix E).** The following documents ship in `docs/compliance/` with the M1 release; they are documentation deliverables, not code:

- `docs/compliance/soc2-alignment.md` — SOC 2 Type II Trust Services Criteria mapped to InHouse AI design choices, identifying project-provided / operator-provided / joint controls (Customer Responsibility Matrix style).
- `docs/compliance/iso-27001-alignment.md` — ISO 27001 Annex A controls mapped to InHouse AI design choices.
- `docs/compliance/iso-42001-alignment.md` — ISO 42001 (AI management system) controls mapped to InHouse AI design (competitive parity with Legora and Legalfly).
- `docs/compliance/gdpr-readiness.md` — Article-by-article readiness analysis (Articles 6, 25, 28, 30, 32, 35, 15–22).
- `docs/compliance/hipaa-readiness.md` — Walks the operator through deploying InHouse AI in a HIPAA-eligible configuration: BAA with the inference provider, Tier 1–3 only, Citation Engine PHI handling, audit logging guidance.
- `docs/compliance/provider-compliance-matrix.md` — Per-provider table of compliance facts (ZDR availability, training-on-data policy, retention windows, certifications, data residency, government cloud). Updated each release. *This is the document users see when they click the tier badge in the UI.*

**Code & Supply-Chain Transparency deliverables (M1, per §7.8 and §1.8).** Documented above in §7.8: SBOM in CI, signed container images, SLSA-3 build provenance, public threat model, dependency security scanning.

**Not in M1, despite earlier drafts:** the MCP-client subsystem architectural slot. Originally targeted for M1; moved to M2 during M1 planning. M2 is the natural landing spot — it overlaps with the Citation Engine and Anonymization Layer work, which is when the gateway/backend extensibility surfaces are already being shaped.

**Starter skills shipped in M1:**
1. NDA Review (mutual + unilateral variants)
2. MSA Review — SaaS
3. MSA Review — Commercial Purchase
4. DPA Checklist Review
5. Vendor Privacy Policy First Pass
6. Contract QA
7. Action Items from Client Alert
8. Comms Improver (plain-language rewriter)
9. Enhance Prompt (the prompt-rewriter)
10. Skill Creator (meta-skill for building skills via conversation)

**MCP-client subsystem (architectural slot, M2).** A pluggable MCP-client module lands in the FastAPI backend in M2 — even though no MCP servers ship and no connectors land in M1–M4. The cost is ~2 weeks of architectural work and documentation; the value is that the M5+ Forward-Looking Roadmap (§8.5) does not require retrofitting MCP into a v1 architecture that did not anticipate it. **Originally targeted for M1; deferred to M2 during M1 planning** — M1 is already fully scoped at ~210 hours with the things that ship in the quickstart, and the architectural slot is small enough that landing it during M2 alongside the Citation Engine work creates no retrofit risk. Per §8.5 / I.5.

**Acceptance criteria:** A new operator can `docker compose up`, sign in, optionally create an Organization Profile and a Project, attach the NDA Review skill, upload an NDA, get a useful review with citations to the right tier-aware provider, and search prior chats — all within 15 minutes of starting from `git clone`.

### M2 — Citation Engine and Anonymization (~6 weeks after M1)

**Theme:** Verifiable citations with character-level fidelity, plus the privacy fallback for cloud-LLM use.

**Deliverables:**
- Document Pipeline (Docling + PyMuPDF + Mistral OCR / PaddleOCR-VL).
- Citable Chunk schema and storage.
- Citation Engine: structured generation, deterministic verification, LLM-judge verification.
- Side-panel PDF.js viewer with bbox highlighting.
- Skill Creator UI (graphical wizard built on the Skill Creator skill from M1).
- Skill chaining UI.
- Skill self-improvement instructions.
- Research feature (web search + legal source connectors: CourtListener, GovInfo, Federal Register, EUR-Lex, SEC EDGAR).
- Multi-Model Ensemble Verification (configurable, off by default except for Citation Engine verification).
- **Anonymization Layer** in the Inference Gateway (per §4.7). Hybrid spaCy + small-LLM NER backend; configurable entity types and custom regex patterns; rehydration in responses and citations; fail-closed when required and tier > 2.
- **MCP-client subsystem (architectural slot).** Pluggable MCP-client module in the FastAPI backend; no MCP servers ship and no connectors land in M2–M4. The slot exists so the M5+ Forward-Looking Roadmap (§8.5) can extend without retrofitting. Originally targeted for M1; deferred to M2 during M1 planning to keep the M1 scope focused on what ships in the quickstart.

### M3 — Playbooks, Word Add-In, Tabular Review, and Slack/Teams (~8 weeks after M2)

**Theme:** Feature parity with commercial in-house legal AI; surface coverage beyond the web.

**Deliverables:**
- Playbook schema and execution engine (LangGraph workflow).
- Easy Playbook auto-generation wizard.
- 4 built-in playbooks: Generic SaaS MSA, NDA, DPA (GDPR-aligned), Commercial MSA.
- Playbook execution UI in web app.
- Word Add-In (Office.js):
  - Chat against the open document
  - Apply skills to selection or whole document
  - Execute Playbooks against the document
  - Generate redlines as Word tracked changes
  - Generate comments as Word comments
  - **Inference Tier badge** in the task pane (per §3.13).
- Enterprise sideload distribution package for the add-in.
- **Tabular / Multi-Document Review** (per §3.14). New `output_format: table` skill mode; tabular UI surface; bulk operations; XLSX/CSV export; cost preview before execution.
- **Slack / Teams Light Intake Bridge** (per §3.15). OAuth install on Slack and Teams; `/inhouse` slash command (forward-as-chat) and `/inhouse ask` quick-skill flows; bot configuration in InHouse AI admin UI.

### M4 — Autonomous Layer and Contract Repository (~8 weeks after M3)

**Theme:** Beyond GC.AI; the analytical layer maturing into temporal and relational awareness.

**Deliverables:**
- OpenWebUI Pipelines integration for background agents.
- Per-user persistent memory store with user-curation UI.
- Cron-scheduled tasks.
- Watch mechanism (trigger on KB changes, document arrivals, calendar events).
- Autonomous skill suggestion ("you've reviewed five SaaS DPAs; want a custom DPA Playbook?").
- Notification system (email, Slack, in-app).
- **Contract Repository — Auto-Relationship Detection** (per §3.16). Pipeline produces relationship graph (amendments, restatements, references, master/sub) over a Knowledge Base; user-confirmable edges; operative-document-chain reasoning when answering scoped questions.
- **M5+ readiness.** M4 design explicitly accommodates multi-step agents that take external-side-effecting actions with human approval gates, since the M5+ Workflow Intelligence direction (§8.5) extends this substrate.

**After M4:** community-driven roadmap. The M5+ Forward-Looking Roadmap below names the trajectory.

### M5–M7 — Forward-Looking Workflow Intelligence (community-driven; not committed) {#section-8.5}

> **Status: forward-looking.** This section names the project's longer-term ambition. It is not a v1–v4 commitment. The maintainer team's bandwidth is the M1–M4 critical path; M5+ is the right scope for a maturing community to contribute to, with the maintainer team coordinating direction. The architectural slots needed to support M5+ (the MCP-client subsystem; the autonomous-layer extensibility) are committed in M1–M4 so that this work is community-extensible rather than requiring core refactoring.

The M5+ direction extends InHouse AI from a tool the user reaches for into a workflow-aware context layer. The core capability sketch: signal aggregation across email, calendar, task systems, and document stores; a Workspace Concierge that produces a ranked Today view with rationales; agent dispatch with human-in-the-loop guardrails; voice and ambient modes. Privacy and security implications are dominant — most of M5+ benefits from Tier 1 / Tier 2 inference and the Anonymization Layer; granular consent per signal source and per scope is a hard requirement. The full sketch is captured in §9 (Workflow Intelligence subsection).

**M5 — Workflow Intelligence Foundation (~10 weeks after M4).**
- MCP-client subsystem operationalized; Signal Aggregation Service skeleton.
- Read-only connectors via MCP for: Gmail / Outlook / IMAP email; Google Calendar / Outlook Calendar; one task system (Linear or Asana, community-driven choice).
- Today view (basic): chronologically-ordered list of pending items from connected sources; no prioritization yet.
- Email Triage Skill: reads incoming, classifies (legal-relevant / not), proposes folder routing or task creation. No auto-actions; user approves.
- Calendar Prep Skill: each morning, surfaces upcoming meetings with relevant Project context.

**M6 — Workflow Intelligence Active (~10 weeks after M5).**
- Prioritization Engine (LangGraph workflow with rule + LLM + autonomous-memory hybrid scoring; the engine itself is an inspectable skill).
- Today view advanced: ranked priorities with rationales; groupings; one-click actions.
- Agent Execution Framework: multi-step background agents with approval gates; agent run history; intervention UI.
- Email Triage Agent (background mode with hourly digests).
- Negotiation Tracker Agent.
- Voice mode for the Today view.

**M7 — Workflow Intelligence Mature (community-driven post-M6).**
- Cross-matter pattern recognition and proactive skill suggestion.
- Counterparty intelligence (aggregate prior interactions across emails, contracts, calls).
- Negotiation-state tracking as a first-class entity (drafting → out-for-review → counter-received → in-progress → executed → terminated).
- Personal decision history view ("you decided X about counterparty Y last June; the same question is being asked now").
- Time-blocked work mode ("you have 90 minutes open at 2 PM; tackle these three items?").
- Async team handoff briefs (one-click "prepare a coverage brief for my deputy while I'm OOO").

**Boundary with Tucuxi proprietary work.** This M5+ direction overlaps conceptually with Kevin's Tucuxi research (Director RNN, Cognitive Compilation Engine, RSH framework, Wisdom Database / GUD). Per §1.6, Tucuxi internals are excluded from the OSS release; the M5+ descriptions deliberately use prosaic OSS-implementable techniques (LLM-based scoring, LangGraph workflows, simple ML for pattern detection) so the OSS version stands fully on its own. Tucuxi-flavored implementations of the same capabilities can layer on for the proprietary product without affecting the OSS implementation.

### Cross-Milestone Workstreams

These run in parallel with all milestones:

- **Documentation.** Every release ships with documentation parity. Quickstart, configuration reference, capability guides, skill-authoring guide, playbook-authoring guide, deployment recipes, troubleshooting, FAQ.
- **Testing.** Pytest coverage target 80%, integration tests for every API endpoint, end-to-end tests for happy paths in every capability, fuzzing for the Inference Gateway's OpenAI compatibility.
- **CI/CD.** GitHub Actions for testing, linting, container builds, multi-arch (amd64 + arm64), nightly integration tests, automated releases.
- **Community.** Triage GitHub issues weekly, monthly community call, blog posts at each milestone release.

---

## 9. Deferred Enhancements and Identified Future Work

This section captures features, refinements, and enhancements that have been identified during PRD authoring and skill drafting but were intentionally deferred from the v1 release in order to ship a focused MVP. Each entry is structured for community pickup: a contributor can read an entry, understand the scope, and propose an implementation without recovering the original context.

The intent is twofold. First, future maintainers (including ourselves at v1.5 or v2) have a record of what was deliberately scoped out and why. Second, community contributors have a pre-populated backlog of meaningful work — these are not "good first issues" in the trivial sense, but they are well-defined enhancements where the architectural slot exists and the implementation is bounded.

Entries are tagged with priority (P1 = should be addressed in v1.5; P2 = good for community contribution any time; P3 = nice-to-have, may never happen) and effort estimate (S = days; M = weeks; L = months).

### Skill ecosystem expansions

#### DE-001 — Additional starter skills beyond the M1 set

**Priority:** P1 · **Effort:** M (one skill at a time)

**Context:** M1 ships with 10 starter skills. Many other recurring in-house legal workflows would benefit from purpose-built skills.

**Specific candidates identified during skill authoring:**
- **Board Minutes Generator** — produced as the example skill in `skill-creator/examples/example_session.md`; could be shipped as an actual skill given the example is essentially a complete v1.0.0.
- **HIPAA BAA Review** as a separate skill from DPA Checklist Review's HIPAA mode (some users prefer single-purpose skills).
- **Multi-state US Privacy DPA Review** — a harmonized multi-state skill versus the single-regime selection in DPA Checklist Review.
- **Settlement Agreement Review.**
- **Employment Offer Letter Review** (in-house counsel reviewing for the company).
- **SOC 2 / Audit Response Drafter.**
- **Regulatory Filing Drafter** (state-by-state corporate filings).
- **Patent License Review.**
- **Trademark License Review.**
- **Open Source License Compatibility Checker** (which OSS licenses can coexist in this project given dependencies?).

**Acceptance criteria:** Each candidate skill follows the established skill format, has frontmatter with all `inhouse:` fields, includes at least one worked example, and is reviewed by at least one practicing attorney before merge.

#### DE-002 — Additional regimes for DPA Checklist Review

**Priority:** P2 · **Effort:** M

**Context:** DPA Checklist Review v1.0.0 covers GDPR, US state privacy, HIPAA BAA, and general commercial. Several other regimes were identified as in-scope for the skill's structure but out-of-scope for v1 substantive coverage.

**Specific regimes to add as reference files:**
- Canada PIPEDA / provincial laws (Quebec Bill 64 / Law 25, BC PIPA, Alberta PIPA).
- Brazil LGPD.
- China PIPL.
- Singapore PDPA.
- Australia Privacy Act.
- India DPDP Act.
- South Korea PIPA.

**Acceptance criteria:** Each regime added as `reference/<regime>_requirements.md`, the `regulatory_regime` input expanded to accept the new value, the SKILL.md workflow's Pass 2 references the new file, and at least one worked example added under that regime.

#### DE-003 — Additional worked examples for DPA Checklist Review

**Priority:** P3 · **Effort:** S

**Context:** v1.0.0 ships with two worked examples (GDPR controller, US state privacy processor). HIPAA BAA, general commercial, and multi-state scenarios are not exemplified.

**Acceptance criteria:** Each new example follows the established output format, demonstrates a different combination of perspective and regime, and shows the skill's calibration on a clean vs. non-compliant document.

#### DE-004 — NDA Review redlined-document output mode

**Priority:** P2 · **Effort:** M

**Context:** NDA Review v1.0.x produces suggested redline language inside its markdown report. A redlined-document output mode (producing actual tracked-changes DOCX or structured diff) was deliberately scoped out and assigned to the Word add-in workflow (M3).

**Open question for resolution:** Does the redline-document output belong in the chat workflow or only the Word add-in workflow? The chat workflow currently surfaces redline language as text; users wanting a redlined document open it in Word and apply the suggestions manually. A direct redlined-document output from chat is feasible but adds complexity.

**Acceptance criteria:** Decide whether to add to chat workflow; if yes, define the output format (structured diff vs. tracked-changes DOCX vs. markdown comparison) and update the SKILL.md `output_format` and workflow.

#### DE-005 — Defined-Terms Consistency Check (skill)

**Priority:** P2 · **Effort:** S

**Context:** Across the in-house contract review category (Ivo, Spellbook, Robin AI, Luminance), checking that defined terms are used consistently — defined in one place, used as defined, no shadow definitions, no orphan capitalizations — is a recurring feature. Well-shaped as a skill rather than a capability; it ships once, anyone can fork.

**Specific scope:** A skill that takes a contract, identifies defined terms (capitalized terms in quotes, "(the X)" patterns), extracts their definitions, and reports inconsistencies, undefined uses, and unused definitions.

**Acceptance criteria:** Skill follows the established format, has a worked example demonstrating each failure mode, and produces an inspectable report referencing each finding with citations.

#### DE-006 — Cross-Document Comparison (skill)

**Priority:** P2 · **Effort:** S

**Context:** Common in-house request: "compare this draft NDA to the prior 5 we have signed with similar counterparties; flag where it diverges." The Files / Knowledge Bases capability (§3.5) and Citation Engine support this; a packaged skill makes the pattern discoverable.

**Specific scope:** Skill takes one target document and a set of comparison documents (or a Knowledge Base), produces a structured diff focused on key clauses, and surfaces unusual deviations.

**Acceptance criteria:** Skill produces a readable diff report with citations into both target and comparison documents.

#### DE-007 — Issue List Generator (skill output mode)

**Priority:** P2 · **Effort:** S

**Context:** Many commercial competitors produce an explicit "issues list" output type — structured rows with severity, recommendation, and citation. The NDA Review starter skill produces a markdown report; a structured-output variant suitable for piping into a tracker (Jira, Linear, GitHub Issues) is a different use case.

**Specific scope:** Skill produces JSON output following an `issues_list` schema (issue, severity, recommendation, source citation). The web UI renders it as a sortable table with bulk export.

**Acceptance criteria:** Schema documented in the skill-authoring guide; at least one starter skill has an `issue_list` output mode in addition to its default markdown.

#### DE-008 — Self-serve business-user contract generation (skill family)

**Priority:** P3 · **Effort:** M

**Context:** Robin AI and others let business users (sales, procurement) self-serve standard agreements (NDAs, sales-side order forms) from templates with bounded customization. For an in-house team, this offloads routine work without legal having to draft each one.

**Specific scope:** A pattern (not a single skill) where a templated skill walks a non-attorney user through structured inputs (counterparty name, term, jurisdiction, etc.) and produces a draft agreement plus a "request legal review" affordance. Requires the skill-input-form pattern (DE-010) implemented first.

**Acceptance criteria:** Reference business-user NDA generator skill, with documentation for skill authors on how to build similar.

### Application UI enhancements

#### DE-010 — Skill input form rendering for any skill

**Priority:** P1 · **Effort:** M

**Context:** PRD §3.4 defines the skill-input-form pattern: when a skill is attached and required inputs are missing, the application surfaces them as form elements rather than letting the model ask conversationally. Enhance Prompt's third example demonstrates the pattern. The pattern is not yet implemented for skills generally — only specified.

**Specific scope:**
- Read `inhouse.inputs.required` and `inhouse.inputs.optional` from any attached skill's frontmatter.
- Render single-select inputs as radio buttons or dropdowns, free-text as input fields, document inputs as file pickers.
- When the user submits, populate the prompt with structured input values before the model call.

**Acceptance criteria:** Any skill in M1 with required inputs (NDA Review, DPA Checklist Review, etc.) shows the form on attachment; the form appears in both the standalone chat input and the Enhance Prompt review screen.

#### DE-011 — Reasoning visibility configuration for Enhance Prompt

**Priority:** P2 · **Effort:** S

**Context:** PRD §3.2 specifies three reasoning-visibility modes (`always_show`, `disclosure`, `on_request`). Implementation deferred to OpenWebUI fork integration.

**Specific scope:** Account-level setting; UI surface in OpenWebUI settings panel; cookie/preference persistence; reasoning-section rendering responsive to the setting.

**Acceptance criteria:** All three modes function on the Enhance Prompt review screen; the default is `disclosure`.

#### DE-012 — Skill inspector side panel

**Priority:** P1 · **Effort:** M

**Context:** PRD §3.4 specifies skill inspectability as a cross-cutting transparency principle. The side-panel UI is specified but not implemented in v1 backend scope.

**Specific scope:**
- Side panel triggered by "view this skill" button on any active skill or Enhance Prompt review screen.
- Renders SKILL.md (with frontmatter formatted readably) and supporting files as tabs.
- Shows provenance line (built-in / authored by / shared by / forked from).
- "Fork this skill" affordance creates a copy under the user's scope.

**Acceptance criteria:** Side panel opens in <500ms; all attached skills are inspectable; fork creates editable copy.

#### DE-013 — Saved Prompts Library

**Priority:** P3 · **Effort:** S

**Context:** Skills are heavyweight (folder, frontmatter, supporting files, semver). For quick personal reuse — "the way I always ask for an executive summary" — a lighter-weight saved-prompt list complements skills the way browser bookmarks complement OpenWebUI's Knowledge Bases. GC.AI ships both; the gap is real.

**Specific scope:** Per-user saved prompts (text + name + optional tags), accessible from a sidebar in the chat input. Prompts can be promoted to skills via "save as skill."

**Acceptance criteria:** Saved-prompt CRUD; sidebar quick-insert; promote-to-skill flow tested.

#### DE-014 — Tone / Audience Settings on Skills

**Priority:** P3 · **Effort:** S

**Context:** Audience-calibrated outputs (peer attorney vs CRO vs board) is a recurring competitor feature. The Comms Improver starter skill addresses one direction post-hoc; making `audience` a standard optional input on skills (per DE-020) propagates the pattern across the skill library.

**Specific scope:** Standardize an `audience: peer_attorney | business_executive | board | client | non_legal_layperson` optional input across skills that produce written output. Skill-authoring guide documents the pattern.

**Acceptance criteria:** Pattern documented; M1 starter skills retrofit where applicable.

#### DE-015 — Voice / Dictation Input

**Priority:** P3 · **Effort:** S

**Context:** GC.AI offers built-in dictation. Modern browsers expose Web Speech API; this is mostly a UI addition.

**Specific scope:** Dictation toggle on the chat input, visible per-prompt waveform, accuracy disclaimer. No server-side STT in v1; rely on browser API.

**Acceptance criteria:** Dictation works in Chrome and Safari; clearly disclaimed as browser-side.

### PRD-process and capability refinements

#### DE-020 — Standardize the optional-input pattern across skills

**Priority:** P1 · **Effort:** S

**Context:** During skill authoring (NDA Review v1.0.0 → v1.0.1, DPA Checklist Review v1.0.0), a pattern emerged: optional inputs that change *analytical depth* not just *report format* are particularly valuable. NDA Review uses `deal_type` and `prior_agreements`; DPA Checklist Review uses `party_role`, `data_categories`, `international_transfer_context`, `prior_agreements`.

**Recommendation:** Document this pattern in the skill-authoring guide so future skills (community-contributed and otherwise) follow it deliberately. Optional inputs should be evaluated against the test: "does providing this input change the substance of the analysis, not just the presentation?"

**Acceptance criteria:** Skill-authoring guide section "Designing optional inputs" is added; existing skills are reviewed against the pattern.

#### DE-021 — Skill versioning and publishing flow

**Priority:** P1 · **Effort:** M

**Context:** Skills carry version numbers in frontmatter (semver). The mechanics of skill versioning across community use (forks, upstream updates, conflict resolution when a community version diverges from the maintained version) are not specified.

**Specific questions:**
- What happens when a community-curated skill (e.g., a jurisdiction-specific NDA Review variant) is updated upstream? Does the user's fork inherit changes? Is there a merge mechanism?
- How are breaking changes (major-version bumps) communicated to users with the skill attached?
- Is there a `skills.legalquants.com` registry for discovering community-published skills?

**Acceptance criteria:** Versioning policy documented; if a registry is built, it follows the same open-source posture as the rest of the project (no telemetry, optional, federated).

#### DE-022 — Skill performance and quality measurement

**Priority:** P2 · **Effort:** L

**Context:** Skills are the unit of value in InHouse AI. There is no current mechanism for measuring how well a skill performs against its intended use, comparing skill versions, or evaluating community contributions.

**Specific scope:**
- Eval harness that runs a skill against a held-out set of representative inputs and grades outputs against expected behavior.
- Per-skill metrics dashboard (when telemetry is enabled with operator opt-in).
- Skill-comparison tool for evaluating proposed updates.

**Acceptance criteria:** Eval harness can execute against any skill; the m1 starter skills have eval suites; community contributions can include eval suites alongside skill content.

#### DE-023 — External-Counsel Collaboration Boundary

**Priority:** P3 · **Effort:** L

**Context:** Many in-house teams' real workflow includes a law firm partner. Legora's Portal addresses this. The PRD's positioning is "open-source AI for in-house legal teams" — explicitly not firm-side — but the firm/in-house collaboration boundary is a real workflow.

**Specific recommendation:** Treat as an open question for the project's future direction, not a v1 commitment. The simplest path is per-user external-collaborator licensing within an InHouse AI deployment (the firm's lawyer is granted scoped access to a Project, per §3.11). The harder path is a federation protocol between two InHouse AI deployments.

**Acceptance criteria:** Decision captured in a future PRD revision; no v1 implementation expected; community demand observed before commitment.

#### DE-024 — ISO 42001 (AI Management System) Alignment Documentation

**Priority:** P3 · **Effort:** M

**Context:** Legora and Legalfly hold or are pursuing ISO 42001 certification (AI governance). For an open-source project, certification is the operator's responsibility, but *alignment* (publishing a mapping of how InHouse AI's design choices satisfy ISO 42001 controls) helps operators argue for adoption inside ISO-aligned organizations. The Compliance Alignment Pack (per §1.8 / M1) commits to shipping `docs/compliance/iso-42001-alignment.md`; this DE captures the ongoing maintenance and refinement of that document beyond M1.

**Specific scope:** Maintain `docs/compliance/iso-42001-alignment.md` mapping each control to relevant PRD sections and configuration choices; update each release; reviewed by an information-security professional.

**Acceptance criteria:** Document published with first GA release; reviewed by an information-security professional; updated each minor release.

### Deployment and infrastructure

#### DE-030 — Helm chart for Kubernetes deployment

**Priority:** P1 · **Effort:** M

**Context:** PRD §6.3 specifies a Helm chart for production K8s deployment. Reference docker-compose is in M1; Helm chart is a follow-on.

**Acceptance criteria:** `helm install inhouse-ai legalquants/inhouse-ai -f values.yaml` produces a working deployment; HA Postgres reference architecture documented; horizontal API scaling tested.

#### DE-031 — Reverse proxy / TLS recipes

**Priority:** P2 · **Effort:** S

**Context:** PRD §6.3 mentions Caddy/Traefik/nginx recipes. Concrete configurations not yet written.

**Acceptance criteria:** Each recipe is a documented `docker-compose` overlay or standalone configuration; Let's Encrypt automation works; recipes tested end-to-end.

#### DE-032 — Air-gap install verification

**Priority:** P2 · **Effort:** S

**Context:** PRD §6.4 specifies air-gapped deployment is supported and that Mode 2 has no outbound calls. Verified by integration test mentioned but not detailed.

**Acceptance criteria:** CI test confirms zero outbound network calls in Mode 2 across all v1 capabilities; documented air-gap install guide tested by external user.

#### DE-033 — Backup and restore tooling

**Priority:** P2 · **Effort:** M

**Context:** PRD §6.5 references documented backup recipe and tested restore. Tooling not yet provided.

**Specific scope:** CLI tool that runs `pg_dump` plus MinIO snapshot, generates a versioned backup bundle, and a corresponding restore tool that handles version migration if needed.

**Acceptance criteria:** Backup-restore round-trip tested in CI; documented procedure for upgrade-with-restore.

### Capability extensions

#### DE-060 — Multi-document Q&A for Contract QA

**Priority:** P2 · **Effort:** L

**Context:** Contract QA v1.0.0 operates against a single document. Multi-document Q&A — questions across a knowledge base of contracts ("which of our SaaS agreements have unlimited liability carve-outs?", "compare this MSA against our standard form") — was identified as genuinely useful but deliberately scoped out of v1 because it raises distinct issues around retrieval scoring, cross-document scope ambiguity, and citation rendering when the answer spans multiple documents.

**Specific scope:**
- Extend Contract QA's `document` input to accept either a single document or a knowledge base reference.
- When operating across multiple documents, retrieval pulls candidate chunks across all in-scope documents.
- Citation format adds a document identifier prefix (e.g., `[MSA-Acme §4.2]` rather than `[§4.2]`).
- The answer rendering shows results grouped by document where applicable.
- The skill needs to handle "scope ambiguity" cases — when the user asks a question that has different answers in different documents, the answer surfaces the variance rather than picking one.

**Open questions for resolution:**
- How does the skill scope a multi-document question? Knowledge-base reference is one mechanism; user-selected document set is another.
- How does the user verify answers when the citation engine is rendering multiple documents in the side panel?
- Does this become a separate skill (`contract-qa-multi`) or stay in Contract QA with a mode flag?

**Acceptance criteria:** Multi-document Q&A produces accurate answers grouped by document; the side-panel viewer handles multi-document citations; the skill correctly identifies and surfaces scope-ambiguous cases.

#### DE-061 — Contract QA acceptance testing

**Priority:** P1 · **Effort:** S

**Context:** Contract QA v1.0.0 includes worked examples but has not been stress-tested against real-world contracts and the full range of question shapes in the wild. Acceptance testing should validate behavior across the six question types and a representative document corpus.

**Specific scope:** Test corpus of 5–10 anonymized real contracts (mix of NDAs, MSAs, employment agreements, vendor agreements). For each, a set of representative questions across all six types (A, B, C, D, E, F). Run Contract QA against each question and grade outputs against expected behavior.

**Acceptance criteria:** Test corpus exists; each starter document has acceptance results documented; identified issues addressed before public release.

#### DE-070 — Dedicated Order Form / SOW Review skill

**Priority:** P2 · **Effort:** M

**Context:** MSA Review — SaaS v1.0.0 accepts an Order Form as optional input and surfaces MSA-vs-Order-Form conflicts (Pass 6 of the workflow). A dedicated Order Form Review skill — focused entirely on Order Form review and its relationship to a referenced MSA — was scoped out of v1.

**Specific scope:**
- Order Form Review skill that reviews Order Form / SOW / Service Schedule documents on their own terms.
- Pricing analysis (rate sheet sanity, term-pricing alignment, discount transparency).
- Service-scope analysis (commitments specific to the order, customer-specific service levels, in-scope vs. out-of-scope features).
- MSA conflict analysis when the user provides both Order Form and MSA.
- Calibration to common Order Form templates (vendor-prepared, customer-prepared, intermediary forms).

**Acceptance criteria:** new skill `order-form-review` follows the established skill format; produces structured findings; works alongside (not duplicating) MSA Review.

#### DE-071 — Additional MSA review variants

**Priority:** P2 · **Effort:** L (multiple skills, one at a time)

**Context:** MSA Review — SaaS covers software-as-a-service master agreements specifically. Other MSA categories share structural similarities but have distinct substantive considerations.

**Specific candidates:**
- **MSA Review — Professional Services:** for consulting, implementation, integration, and managed-services agreements without a SaaS substrate.
- **MSA Review — Hardware-as-a-Service:** for IoT-platform agreements, equipment-bundled-with-service models.
- **MSA Review — AI / ML Services:** for agreements where the service is access to a model provider's offering, with distinct issues around training data, output IP, model versioning, and inference confidentiality.
- **MSA Review — Government Services:** SaaS for federal or state procurement, with FedRAMP, FAR, and procurement-statute overlays.
- **Channel Partner / Reseller Agreement Review:** distinct from MSA but adjacent.

**Acceptance criteria:** each new skill follows the established format and references shared infrastructure (severity rubric structure, perspective-lens approach) for consistency across the contract-review skill family.

#### DE-072 — MSA Review acceptance testing against real document corpus

**Priority:** P1 · **Effort:** M

**Context:** MSA Review — SaaS is the largest contract-review skill in the M1 set. Acceptance testing against a corpus of real-world MSAs (vendor-favorable, customer-favorable, balanced; SMB and enterprise; various industries) is essential before relying on the skill's output for actual deals.

**Specific scope:** anonymized corpus of 10-15 real SaaS MSAs across the dimensions above. For each, expected behavior documented (which issues should be flagged at which severity from each perspective). Run MSA Review against each in `comprehensive` and `quick_triage` modes; grade outputs.

**Acceptance criteria:** corpus exists and is reviewed by external counsel for accuracy of expected behavior; MSA Review acceptance results documented; identified issues addressed before public release.

#### DE-080 — Shared infrastructure for contract-review skill family

**Priority:** P2 · **Effort:** M

**Context:** During authoring of NDA Review, DPA Checklist Review, MSA Review — SaaS, and MSA Review — Commercial Purchase, a recurring pattern emerged: the *infrastructure* of contract review (severity rubric, perspective-lens approach, report structure, recommended-language conventions) is consistent across skills, while the *substance* (issue checklist, red flags, regime-specific requirements) is fresh per skill.

In v1, each contract-review skill carries its own copy of the shared infrastructure. This is duplicative — when we update the severity rubric or report structure, we must update every contract-review skill independently — but acceptable for the M1 release because the duplication is explicit and reviewable.

**Specific scope for v1.5 or later:**
- Hoist shared infrastructure to a project-level reference: `skills/_shared/contract_review/{severity_rubric.md, report_structure.md, perspective_lens_pattern.md, recommended_language_conventions.md}`.
- Update each contract-review skill's `SKILL.md` to reference the shared infrastructure rather than duplicating it.
- Each skill retains its own `issue_checklist.md` and `red_flags.md` (the substantive content) plus a thin local extension to the shared infrastructure where the skill needs calibrations specific to its document type.
- Document the pattern in the skill-authoring guide so future contract-review skills (and community contributions) follow it.

**Why deferred:** doing this in v1 would have required the pattern to be designed *before* it was discovered. By authoring four contract-review skills with the duplication in place, the actual shape of the shared infrastructure becomes visible and the abstraction is grounded rather than speculative. This is the right time to extract the pattern, but only after enough skills exist to verify it.

**Acceptance criteria:** shared infrastructure files exist; existing contract-review skills updated to reference rather than duplicate; skill-authoring guide documents the pattern; one new community-contributed contract-review skill demonstrates the pattern works.

**Generalizes beyond contract review.** The same pattern likely applies to any skill family — research skills will share research-process infrastructure; drafting skills will share voice-and-style conventions; review skills generally will share severity calibration. Document the meta-pattern in the skill-authoring guide.

#### DE-081 — Obligation Tracking / Renewal Calendar

**Priority:** P3 · **Effort:** L

**Context:** Robin AI and CLM-with-AI products (Ironclad, Evisort) provide obligation tracking — auto-renewal dates, deadline alerts, milestone notifications. The PRD does not address the post-signature life of contracts, which is correct for a v1 focus on the analytical work, but worth flagging for a future direction.

**Specific recommendation:** Probably a separate capability (or a sister project) rather than a core feature; obligation tracking is a fundamentally different shape of work (temporal, calendar-driven, notification-heavy) than analytical AI. The autonomous layer (§3.10) could host the underlying mechanism (cron schedules, watches) with a domain-specific UI on top.

**Acceptance criteria:** Decision captured (in-scope for InHouse AI vs. sister project); if in-scope, reference implementation ships in a later milestone.

#### DE-082 — Regulatory Monitoring with Proactive Alerts

**Priority:** P3 · **Effort:** L

**Context:** Legalfly's "Legal Radar" continuously monitors regulatory feeds across 60+ jurisdictions and flags items relevant to the user's industry/business. This is a watch-on-the-Research-feed analog of the autonomous-layer KB watches (§3.10).

**Specific scope:** An autonomous-layer pattern where the user subscribes a Project to relevant regulatory feeds (Federal Register, SEC EDGAR releases, EUR-Lex publications, state AG announcements), the autonomous agent runs daily, and notifies on items that match the Project's defined relevance criteria.

**Acceptance criteria:** Reference subscription pattern documented; first regulatory-watch skill ships demonstrating it.

#### DE-083 — Google Docs Add-On (M3 sister to the Word Add-In)

**Priority:** P3 · **Effort:** L

**Context:** PRD §3.9 specifies a Word add-in via Office.js. Many startups, smaller in-house teams, and increasingly some larger ones draft in Google Docs. Several competitors (Ivo, Spellbook for Docs) cover both surfaces.

**Specific recommendation:** Defer to M5 or community. A Google Workspace add-on using the same backend OpenAPI surface is feasible but adds significant engineering and OAuth-flow complexity. Worth flagging as a deferred capability rather than ignoring.

**Acceptance criteria:** Decision captured in a future PRD revision; community demand observed before commitment.

#### DE-084 — Email-as-Intake Bridge

**Priority:** P3 · **Effort:** M

**Context:** Forwarding `legal@company.com` emails into a system that creates structured chats is the front-door pattern most in-house teams actually adopt. Streamline AI builds this; an OSS InHouse AI without it leaves a real gap. Sister to the Slack/Teams Light Intake Bridge (§3.15).

**Specific scope:** A configured incoming email address (per deployment) that creates a chat from the email body, attaches any documents, and assigns to a configured user or group based on rules. Deliberately *not* full triage/SLA/approval workflow — that is Streamline AI's category (per §1.6).

**Acceptance criteria:** Email-to-chat flow works end-to-end; documented IMAP / SMTP / Postfix configuration recipe.

#### DE-085 — Operational Analytics for Legal Ops

**Priority:** P3 · **Effort:** M

**Context:** Streamline AI, Checkbox, and others surface metrics on legal-team throughput, SLA hit rate, request volume by team, and time-at-stage. The PRD has cost tracking (§5.5) but not legal-work analytics.

**Specific scope:** A dashboard surface (admin role) showing chat volume by user/team, time-to-first-token, time-to-final-answer, skills usage, and Project activity. Builds on existing OpenTelemetry instrumentation (§5.4).

**Acceptance criteria:** Dashboard ships with at least 5 default metrics; metrics exportable; documented for operators.

#### DE-086 — Procurement-Readiness Pack

**Priority:** P2 · **Effort:** S

**Context:** Operators deploying InHouse AI inside an enterprise will face an internal procurement / security review. Commercial competitors ship pre-filled SIG, CAIQ, and security-questionnaire responses to short-cut this. For an open-source self-hosted product, the operator owns the answers, but a starter pack would dramatically lower the friction. The Compliance Alignment Pack (per §1.8 / M1) plus Pre-Empted Procurement Objections appendix (Appendix E) cover much of this; the Procurement-Readiness Pack adds the questionnaire templates.

**Specific scope:** Templates in `docs/procurement/` covering: SIG Lite responses, CAIQ responses, security architecture summary, data-flow diagram, supported deployment topologies for various enterprise constraints, third-party dependencies and their licenses (already partially covered in Appendix B).

**Acceptance criteria:** Templates ship with the M1 release; reviewed by an enterprise-buyer sample before publishing.

#### DE-040 — Direct CLM integration

**Priority:** P3 · **Effort:** L

**Context:** PRD §1.6 lists "direct integrations with CLM systems (Ironclad, Concord, etc.)" as out of scope for v1.

**Specific scope:** API integrations or MCP tool adapters for the major CLMs, allowing InHouse AI to read contracts from CLMs, post review reports back, and trigger workflow updates.

**Acceptance criteria:** At least one CLM integration shipped with documentation; pattern for adding others.

#### DE-041 — E-discovery capabilities

**Priority:** P3 · **Effort:** L

**Context:** PRD §1.6 lists e-discovery as out of scope. Some users will request it; structurally distinct from in-house work.

**Recommendation:** Probably should remain a separate project rather than merging into InHouse AI. Track community demand and revisit if a fork or sister project is warranted.

#### DE-042 — Mobile applications

**Priority:** P3 · **Effort:** L

**Context:** PRD §1.6 lists mobile native apps as out of scope; web UI is responsive.

**Recommendation:** Wait for community demand. If demand materializes, consider PWA before native.

### Process and project management

#### DE-050 — Skill quality bar / review process for community contributions

**Priority:** P1 · **Effort:** S

**Context:** The repository will accept community-contributed skills. The quality bar — what makes a skill mergeable, who reviews, how legal-substance accuracy is verified — is not yet documented.

**Specific scope:**
- Skill contribution guide.
- Required elements (SKILL.md, at least one worked example, frontmatter completeness).
- Required attestation that the skill's substantive content is accurate to the contributor's knowledge.
- Review process (at least one practicing attorney + one engineer reviewer for skills containing legal substance).
- Versioning and conflict-resolution rules.

**Acceptance criteria:** Process documented in `CONTRIBUTING.md` and `skills/CONTRIBUTING.md`; first community-contributed skill merged following the process.

#### DE-051 — Acceptance testing for the M1 skill set against real documents

**Priority:** P1 · **Effort:** M

**Context:** The 10 starter skills shipping in M1 have been authored but not extensively tested against real-world documents. Pre-launch acceptance testing should validate behavior on a corpus of real contracts.

**Specific scope:** Curated test corpus (anonymized real NDAs, MSAs, DPAs, etc.) with expected behavior documented. Run each skill against each relevant document in the corpus; compare actual output to expected.

**Acceptance criteria:** Test corpus exists; each starter skill has acceptance results documented; identified issues filed as bugs and addressed before public release.

### Security and compliance

This subsection consolidates security and compliance enhancements deferred from v1. Most are operationally important for specific verticals (federal contractors, regulated industries, high-assurance deployments) and were deliberately scoped out of v1 to keep the M1 release focused. The §1.8 Security Posture and Appendix E Pre-Empted Procurement Objections describe how the v1 baseline plus the Compliance Alignment Pack already match what closed-source commercial competitors offer; the items below are the next layer of hardening.

#### DE-100 — Tamper-evident audit log

**Priority:** P2 · **Effort:** M

**Context:** PRD §5.3 specifies a comprehensive audit log. For high-assurance deployments and litigation-readiness, the audit log should be tamper-evident: each entry is hash-chained to the prior entry (Merkle structure or signed-chain), and the chain root is published or anchored periodically.

**Specific scope:** Per-entry SHA-256 chain; periodic chain-root signing with a deployment key; verifier tool; documentation for incorporating the chain root into the operator's broader audit trail (e.g., publish to an internal blockchain, RFC 3161 timestamp, or public transparency log).

**Acceptance criteria:** Verifier confirms an unbroken chain across a sample audit log of >1M entries; documented procedure for the operator to detect and respond to a chain break.

#### DE-101 — Cryptographic timestamping of work product

**Priority:** P2 · **Effort:** M

**Context:** Legal work product has temporal significance: when did the analysis exist? When was the redline drafted? Cryptographic timestamping creates evidence that is admissible in litigation. Builds on the WorkProductAttribution metadata already captured in v1 (per §3.3).

**Specific scope:** Each model-generated artifact (chat response, redline, Playbook execution) is signed with a deployment key and accompanied by an RFC 3161 timestamp (or alternative — a signed entry in a transparency log such as Sigstore Rekor). Verifier confirms timestamp.

**Acceptance criteria:** Each artifact in the export bundle includes a verifiable timestamp; verifier tool ships with the project; documented procedure for using timestamps as evidence.

#### DE-102 — Hardware Security Module (HSM) and Vault integration

**Priority:** P2 · **Effort:** M

**Context:** PRD §5.6 specifies pgcrypto column-level encryption for sensitive fields including API keys. High-assurance deployments will require keys stored in an HSM or external secrets manager (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager).

**Specific scope:** Pluggable secrets backend in the Inference Gateway and main backend; reference adapters for HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager. Documented key-rotation procedure.

**Acceptance criteria:** Reference deployments documented for each major secrets backend; key rotation tested in CI without service interruption.

#### DE-103 — IP allowlisting and geo-restriction

**Priority:** P2 · **Effort:** S

**Context:** Many enterprise deployments require IP-based access controls and geographic restrictions on user access.

**Specific scope:** Configurable IP allowlist applied at the web app and Word add-in entry points; configurable geo-IP-based restrictions with an integrated geo database (MaxMind or alternative). Operator chooses backend.

**Acceptance criteria:** Documented configuration; tested in CI; admin UI surfaces current rules.

#### DE-104 — Just-in-time admin elevation

**Priority:** P3 · **Effort:** M

**Context:** Modern privileged-access management practice requires admin elevation be explicit, time-bounded, and audited rather than persistent.

**Specific scope:** Admin role with short-lived elevation tokens; users with admin permissions must request elevation; elevations are logged with reason; auto-expiry after configurable period (default 60 minutes).

**Acceptance criteria:** Elevation flow tested; audit log captures elevations; no admin action permitted without active elevation.

#### DE-105 — Outbound proxy support

**Priority:** P2 · **Effort:** S

**Context:** Many enterprise networks require outbound traffic to traverse a corporate inspection proxy.

**Specific scope:** Inference Gateway supports `HTTPS_PROXY` / `NO_PROXY` configuration; documented integration with common corporate proxies (Zscaler, Palo Alto Networks, etc.); TLS interception trust handled gracefully.

**Acceptance criteria:** Documented configuration; tested against at least one corporate proxy implementation.

#### DE-106 — Configurable retention policies

**Priority:** P1 · **Effort:** M

**Context:** Operator should configure auto-purge schedules per resource type to satisfy data-minimization principles and storage management.

**Specific scope:** Configuration UI for retention by resource type (chats, files, audit log, autonomous-layer memory) and scope (personal, group, org). Background job applies policies. Litigation-hold flag suspends auto-purge for specified resources (see DE-109).

**Acceptance criteria:** Default policies documented; admin UI shows current policies and pending purges; litigation hold tested.

#### DE-107 — Operator-side data subject rights tooling

**Priority:** P1 · **Effort:** L

**Context:** A GDPR Article 15 (access) or Article 17 (deletion) request from a data subject who is *referenced* in chats, files, or audit entries (rather than being an InHouse AI user) requires the operator to find and produce or delete that subject's data across resources. Per-user export/delete (in v1, §5.3) handles users; this DE handles the harder case.

**Specific scope:** Admin tool that takes an entity (name, email, identifier) and surfaces all resources mentioning that entity, with options to redact (replace with pseudonym), delete (remove the resources), or export (produce as a bundle).

**Acceptance criteria:** Tool finds references at recall >95% on a test corpus; redaction does not break audit log integrity; export bundle is GDPR-compliant.

#### DE-108 — Backup encryption with rotation

**Priority:** P1 · **Effort:** M

**Context:** PRD §6.5 specifies pg_dump + MinIO snapshot backups. Production-grade backup requires encryption at rest with separate keys from the live deployment, key rotation, and restore-with-key-rotation testing.

**Specific scope:** Backup CLI tool encrypts bundles with operator-provided KMS key; restore tool handles key-rotation scenarios; documented key-management procedure.

**Acceptance criteria:** Backup-restore round-trip tested in CI with key rotation; documented procedure.

#### DE-109 — Litigation hold support

**Priority:** P2 · **Effort:** S

**Context:** When a matter is on litigation hold, auto-purge and certain user-deletion actions must be suspended to preserve evidence.

**Specific scope:** Admin-set litigation-hold flag at the resource or matter level; suspends auto-purge; warns users attempting to delete held resources; logged and audited.

**Acceptance criteria:** Held resources cannot be auto-purged; user-deletion attempts produce explicit blocked-by-hold messages with audit log entries.

#### DE-110 — Prompt-injection pattern library

**Priority:** P2 · **Effort:** M

**Context:** Documents from counterparties or external sources may contain prompt-injection attacks intended to manipulate the model. A community-maintained library of known patterns, scanned by the Inference Gateway, raises the bar.

**Specific scope:** Pattern library shipped as an inspectable skill; Inference Gateway middleware scans incoming context for matching patterns; matches are flagged in the response with a "potential injection detected" banner; severe matches can be configured to refuse.

**Acceptance criteria:** Library covers a baseline of published prompt-injection patterns; scanner adds <100ms latency; community contribution process documented.

#### DE-111 — Output-validation guardrails (generalized)

**Priority:** P2 · **Effort:** S

**Context:** Skills with structured output schemas (PRD §3.3 Citation Engine, JSON outputs in §3.7 Playbooks) already validate against schema. Generalize so any skill can declare an output schema and the application validates / refuses out-of-schema outputs.

**Specific scope:** Skill frontmatter `output_schema` field; runtime validator; failure modes (refuse, retry, surface partial).

**Acceptance criteria:** Pattern documented in skill-authoring guide; reference implementations on starter skills.

#### DE-112 — Model checksum verification for local models

**Priority:** P2 · **Effort:** S

**Context:** When Ollama pulls a model, supply-chain integrity for the model itself matters. Verify checksums against a known-good registry.

**Specific scope:** Configurable model-checksum allowlist; the deployment refuses to use models whose checksum is not on the list; documented procedure for adding new models to the allowlist with attestation.

**Acceptance criteria:** Reference allowlist provided; checksum verification adds <5s to first model-load; documented procedure.

#### DE-113 — FedRAMP-aligned deployment recipe

**Priority:** P2 · **Effort:** L

**Context:** Federal users (and federal contractors) require FedRAMP authorization. While the project itself does not pursue authorization, an alignment document and reference deployment recipe support operators pursuing FedRAMP Moderate (or aspirationally High) for their environment.

**Specific scope:** `docs/compliance/fedramp-alignment.md`; reference deployment recipe targeting FedRAMP Moderate baseline (Tier 1 or Tier 2 inference required, FedRAMP-authorized cloud provider, specific configuration of audit log, encryption, and access controls); SCAP / OSCAL artifacts where applicable.

**Acceptance criteria:** Document published; reference recipe deployable; gap analysis identifies items requiring operator implementation.

#### DE-114 — Reproducible builds

**Priority:** P2 · **Effort:** M

**Context:** Verifying that a deployed image matches the source requires reproducible builds: any party rebuilding from the release tag produces a bit-identical image. Builds on the SLSA-3 build provenance committed in v1 (§7.8); reproducibility is the next layer.

**Specific scope:** Container build configuration deterministic (pinned base images, deterministic timestamps, deterministic dependency installation); CI verifies reproducibility on each release.

**Acceptance criteria:** Two independent builds at the same release tag produce identical image digests; verification tool ships with the project.

#### DE-115 — Formal Vulnerability Disclosure Program (VDP)

**Priority:** P3 · **Effort:** S

**Context:** PRD §7.6 specifies coordinated disclosure via SECURITY.md. A formal bug bounty or VDP with published scope, safe-harbor language, and (optionally) monetary rewards encourages security research.

**Specific scope:** Published VDP under a recognized framework (HackerOne, Intigriti, or self-hosted); safe-harbor language; published past disclosures with attribution; optional rewards for critical findings.

**Acceptance criteria:** VDP published; safe-harbor reviewed by counsel; first reported and fixed disclosure referenced.

### Workflow intelligence

This subsection captures the bounded items that operationalize the M5+ Forward-Looking Workflow Intelligence direction (§8.5). The items are bounded enough to be picked up by community contributors as the M5+ roadmap matures. The architectural slot for the MCP-client subsystem is already committed for M1–M2 (§8 M1) so this subsection's items can be implemented incrementally without core refactoring.

Privacy and security implications dominate this entire subsection. Most items benefit from Tier 1 / Tier 2 inference (§1.5.2) and from the Anonymization Layer (§4.7); granular consent per signal source and per scope is a hard requirement, not an optional refinement. The §I.6 framing in the source recommendations (preserved here in spirit): "the privacy implications of workflow-aware context are the dominant constraint on the entire capability set; they cannot be appended as an afterthought; they have to be designed in from the start."

#### DE-200 — MCP-client subsystem in the InHouse AI backend

**Priority:** P1 · **Effort:** M

**Context:** The MCP integration substrate is the foundational piece on which all workflow-context capabilities depend. The architectural slot is committed in M1 or M2 (§8 M1) even though no connectors ship until M5; this DE captures the operationalization beyond the slot.

**Specific scope:** A pluggable MCP-client module in the FastAPI backend; configuration via the operator's `mcp.yaml`; per-server credential management; request routing; rate limiting; OpenTelemetry instrumentation matching the rest of the stack.

**Acceptance criteria:** Operator can register an MCP server in configuration; backend lists discovered tools; tools are callable from skills via a documented invocation pattern; community skill demonstrates calling at least one MCP server.

#### DE-201 — Signal Aggregation Service

**Priority:** P1 · **Effort:** L

**Context:** The persistent workspace-state layer that consumes signals from connected sources and exposes a unified query API. Foundation for the Today view, Prioritization Engine, and agent dispatch.

**Specific scope:** New backend service; consumes events via MCP-client subsystem; normalizes to Workspace Event schema (event_type, source, subject, timestamp, payload, metadata); persists in Postgres; exposes query API by user, time range, source, and event type; emits internal events for downstream consumers (Prioritization Engine, agents).

**Acceptance criteria:** Service ingests events from at least three signal sources; query API is documented and tested; event schema is documented and stable.

#### DE-202 — Email connector via MCP

**Priority:** P1 · **Effort:** M

**Context:** First and most important signal source. Ideally implemented as a community-contributed MCP server consumed by InHouse AI rather than baked in.

**Specific scope:** Reference MCP server for Gmail and Microsoft 365 (Exchange Online); read-only by default; granular permission scoping (specific labels/folders only); rate-limit-aware.

**Acceptance criteria:** Operator can configure email access; signals appear in Signal Aggregation Service; consent revocation is instantaneous.

#### DE-203 — Calendar connector via MCP

**Priority:** P1 · **Effort:** M

**Context:** Second signal source. Same pattern as DE-202.

**Specific scope:** Reference MCP server for Google Calendar and Microsoft 365 calendar; read-only by default; per-calendar permission scoping.

**Acceptance criteria:** As above for email.

#### DE-204 — Task system connectors via MCP

**Priority:** P1 · **Effort:** M each

**Context:** Asana, Linear, Jira, GitHub Issues, Monday, ClickUp — each a separate MCP server. Many already exist in the Anthropic MCP ecosystem; the InHouse AI project can leverage rather than duplicate.

**Specific scope:** Documented procedure for connecting community-maintained MCP servers to InHouse AI; reference deployment recipes for the most common task systems.

**Acceptance criteria:** Operator can configure at least three task systems via MCP; signals surface in Signal Aggregation Service.

#### DE-205 — CRM connector via MCP

**Priority:** P2 · **Effort:** M

**Context:** Salesforce above all; HubSpot, Microsoft Dynamics secondarily. CRM signal awareness is meaningful for in-house teams that handle deal-flow legal review.

**Specific scope:** Reference MCP server (or documentation for connecting community-maintained servers); granular access scoping (specific opportunities or accounts only).

**Acceptance criteria:** Operator can configure CRM access; signals (new opportunities matching legal-review criteria) surface in Signal Aggregation Service.

#### DE-206 — Document store connectors via MCP

**Priority:** P2 · **Effort:** M

**Context:** SharePoint, Google Drive, OneDrive, Dropbox, Box. Several have existing MCP servers in the ecosystem.

**Specific scope:** Documentation for connecting common document store MCP servers; pattern for auto-discovery of new documents in legal-team folders; auto-ingestion into Knowledge Bases.

**Acceptance criteria:** Operator can configure at least two document stores via MCP; new-document arrival triggers configurable workflow (auto-ingest, auto-Playbook-run, etc.).

#### DE-207 — Prioritization Engine

**Priority:** P1 · **Effort:** L

**Context:** The Workspace Concierge's core analytical capability. Open source, inspectable, forkable — true to the project's transparency philosophy (§1.3).

**Specific scope:** LangGraph workflow that aggregates signals + Project context + Org Profile + autonomous-layer memory; applies rule + LLM + learned-preference scoring; outputs ranked priority list with rationales. Implementation as a skill (the prioritization skill is open source like all other skills).

**Acceptance criteria:** Engine produces ranked priorities for a representative test workspace; rationales are coherent and traceable to inputs; performance: full re-prioritization completes in <30s for a workspace with 200 pending signals.

#### DE-208 — Today View UI surface

**Priority:** P1 · **Effort:** M

**Context:** The user-facing rendering of the prioritization output.

**Specific scope:** Web app surface (single-page, focused, opinionated); Word add-in equivalent (compact panel); responsive design for mobile browsers; one-click actions on each priority; drill-in to underlying Project or chat.

**Acceptance criteria:** Surface ships with M5; renders in <1s; mobile-responsive; tested on web, Word desktop, Word Online.

#### DE-209 — Email Triage Skill

**Priority:** P1 · **Effort:** S (once email connector exists)

**Context:** First and most-used skill operating on workspace signals.

**Specific scope:** Skill consumes incoming email signals; classifies (legal-relevant / not, contract / question / regulatory / internal / other); proposes routing or task creation; drafts responses for routine items.

**Acceptance criteria:** Skill ships with M5; reviewed by practicing attorney; produces useful classifications on real inbox samples.

#### DE-210 — Calendar Prep Skill

**Priority:** P1 · **Effort:** S (once calendar connector exists)

**Context:** Pre-meeting briefs based on calendar awareness and Project context.

**Specific scope:** Skill runs each evening (or on-demand); identifies meetings in the next 24 hours; for each meeting, finds related Project / matter context; produces a structured brief.

**Acceptance criteria:** Skill ships with M5; produces briefs of consistent quality on a representative calendar test set.

#### DE-211 — Agent Execution Framework

**Priority:** P1 · **Effort:** L

**Context:** Multi-step background agents with approval gates. Builds on M4 autonomous layer; the M4 design explicitly accommodates this extension (§3.10, §8 M4).

**Specific scope:** Agent definition format (extension of skill format); agent runtime in OpenWebUI Pipelines; agent run history; intervention UI; approval workflow for external-side-effecting actions; audit logging integration.

**Acceptance criteria:** Framework ships with M6; reference Email Triage Agent and Calendar Prep Agent demonstrate the pattern; documented contributor guide for agent authors.

#### DE-212 — Voice mode for the Today View

**Priority:** P2 · **Effort:** M

**Context:** Conversational interface to the prioritization output.

**Specific scope:** Voice input via Web Speech API (or browser-side equivalent); audio playback of priorities and rationales; "skip," "drill in," "defer to tomorrow" voice commands.

**Acceptance criteria:** Voice mode functional in Chrome and Safari; tested on common command patterns.

#### DE-213 — Cross-matter pattern recognition

**Priority:** P2 · **Effort:** L

**Context:** When the user has reviewed N similar contracts or matters, the system proactively suggests creating a Playbook, a saved skill, or a reusable position. Mentioned in PRD §3.10 user stories; this elevates it from autonomous-layer note to first-class capability.

**Specific scope:** Background analysis over the user's chat history and Project content; clusters similar matters; surfaces proposals for Playbook creation, skill creation, or Org Profile additions.

**Acceptance criteria:** Reference implementation surfaces meaningful patterns on a test corpus; suggestions are dismissable; user can accept and the system creates the proposed artifact.

#### DE-214 — Counterparty intelligence

**Priority:** P2 · **Effort:** L

**Context:** Aggregate prior interactions with a specific counterparty across emails, contracts, calls (transcribed), and decisions. Surface as context when the counterparty appears in a new matter.

**Specific scope:** Counterparty as a first-class entity (opposed to mentions in scattered places); per-counterparty knowledge graph; context surface in chats where a counterparty is implicated.

**Acceptance criteria:** Counterparty entity reliably resolves across mentions; knowledge surface accessible in chat sidebar; performance: counterparty resolution adds <200ms to chat creation.

#### DE-215 — Negotiation-state tracking

**Priority:** P2 · **Effort:** L

**Context:** A live contract negotiation has state: which side has the redline, what is open, what is converged. The system tracks the state and surfaces it.

**Specific scope:** Negotiation as a first-class entity attached to a Project (§3.11); state machine (drafting → out-for-review → counter-received → in-progress → executed → terminated); per-clause state (open, converged, agreed); visualization.

**Acceptance criteria:** State machine documented and consistent; state surfaces in Project view; supports stalled-negotiation detection (no movement in N days).

#### DE-216 — Personal decision history

**Priority:** P2 · **Effort:** L

**Context:** Captures user decisions with provenance and surfaces them when similar questions arise. "You decided X about counterparty Y in June; this looks like the same question."

**Specific scope:** Decision capture (explicit or inferred from chat content); decision retrieval on similar questions; explicit decision-recording skill.

**Acceptance criteria:** Decision retrieval surfaces relevant prior decisions on a test corpus; user can dismiss surfacing; decisions can be explicitly captured or reformed.

#### DE-217 — Time-blocked work mode

**Priority:** P3 · **Effort:** M

**Context:** "You have 90 minutes open at 2 PM. Tackle these three items?"

**Specific scope:** Calendar-aware availability detection; estimated-time tagging on priorities; bundled "work session" view with the items the user can plausibly complete in the available window.

**Acceptance criteria:** Estimation is calibrated against historical actuals; work session UI ships with M7 or community contribution.

#### DE-218 — Async team handoff briefs

**Priority:** P3 · **Effort:** M

**Context:** When a user goes OOO, hands off to a deputy, or departs the team, the system can prepare a structured handoff brief covering active matters, pending decisions, and key context.

**Specific scope:** Handoff brief generation skill that operates on a Project (or all the user's Projects); produces a structured document optimized for someone unfamiliar with the matters.

**Acceptance criteria:** Brief is useful for an unfamiliar reviewer; reviewed by practicing attorneys for completeness; tested on real OOO scenarios.

### How to add to this list

When new deferred items are identified during development, ongoing skill authoring, or community feedback:

1. Add an entry to the appropriate subsection (or create a new subsection if needed).
2. Use a unique DE-### identifier; do not reuse retired numbers.
3. Include priority, effort, context, specific scope, and acceptance criteria.
4. Link from the relevant section of the PRD or skill where the decision was made.

This section is mutable across PRD versions; updates do not require a PRD version bump unless they change priority on P1 items.

---

## 10. Appendices

### Appendix A — Glossary

- **agentskills.io format** — open standard for portable AI skills, compatible with Anthropic Claude Skills and Hermes Agent.
- **Anonymization Layer** — Inference Gateway middleware (§4.7) that pseudonymizes sensitive entities before the model call and rehydrates them after; the privacy fallback for Tier 3+ inference.
- **Citation Engine** — InHouse AI's character-fidelity citation pipeline.
- **Citable Chunk** — atomic unit of indexed content with full positional metadata for citation.
- **Compliance Alignment Pack** — `docs/compliance/` documents mapping InHouse AI's design choices to SOC 2, ISO 27001, ISO 42001, GDPR, HIPAA, FedRAMP controls; ships with M1 (§1.8 / §8 M1).
- **Easy Playbook** — auto-generation wizard that drafts a Playbook from prior agreements.
- **Enhance Prompt** — front-running agent that rewrites user input into a structured legal prompt.
- **Inference Choice Spectrum** — five-tier security spectrum (§1.5.2) from local-only (Tier 1) to consumer/free (Tier 5); the central organizing concept of §1.8.
- **Inference Tier** — operator-and-skill-aware classification (1–5) of where customer data goes during inference; surfaced to the user in real time via the Tier badge (§3.13).
- **InHouse AI** — this project.
- **LegalQuants** — the organization stewarding InHouse AI.
- **MCP / MCP server** — Model Context Protocol; an open standard for connecting AI assistants to external systems. The MCP-client subsystem is the integration substrate for the M5+ workflow-intelligence direction (§8.5); the architectural slot is committed in M1–M2.
- **Mode 1 / Mode 2** — self-hosted with cloud LLM keys / self-hosted with local inference.
- **Organization Profile** — singleton skill at the deployment level (§3.12) capturing org-wide voice, jurisdiction, industry, and standard positions; prepended to skill prompts unless declined.
- **Playbook** — codified legal positions for automated contract review.
- **Pre-Empted Procurement Objections** — Appendix E; structured responses to common procurement-team objections, intended to short-cut enterprise procurement review.
- **Project** — user-curated matter-scoped container (§3.11) bundling chats, files, skills, playbooks, and a free-form context document around a single deal, counterparty, or matter.
- **Provider Compliance Matrix** — `docs/compliance/provider-compliance-matrix.md`; per-provider table of compliance facts surfaced to users when they click the Inference Tier badge.
- **Signal Aggregation Service** — proposed M5 backend service consuming workspace signals via MCP, normalizing to a unified Workspace Event schema (§8.5, §9 Workflow Intelligence).
- **Skill** — reusable structured prompt artifact in agentskills.io format.
- **Skill chaining** — composing multiple skills in a single chat.
- **Tabular Review** — M3 capability (§3.14) for structured grid output across N documents; bulk document analysis with citation-grounded cells.
- **Workspace Concierge** — proposed M6 capability (§8.5) layering prioritization and proactive surfacing on top of Signal Aggregation; not a v1 commitment.
- **Work-Product Attribution metadata** — chain-of-custody metadata (§3.3) attached to every model-generated artifact: user, chat/Project, inference tier, provider, model, skills applied, timestamp, content hash.

### Appendix B — License Summary Matrix

| Component | License | Usage |
|---|---|---|
| InHouse AI core (this repo) | Apache 2.0 | Project license |
| OpenWebUI fork (web) | OpenWebUI License | Customized, branding clause respected |
| FastAPI | MIT | Backend framework |
| LangGraph | MIT | Agent runtime |
| pgvector | PostgreSQL License | Vector store |
| Docling | MIT | Document parsing |
| PyMuPDF | AGPL-3.0 | Server-side only, not redistributed |
| Mistral OCR | Paid API | Optional, fallback |
| PaddleOCR-VL | Apache 2.0 | Local-mode OCR alternative |
| Ollama | MIT | Local inference (Mode 2) |
| Langfuse | MIT | Optional LLM observability |
| OpenTelemetry | Apache 2.0 | Standard observability |
| Office.js | Microsoft (free) | Word add-in platform |
| agentskills.io format | Open standard | Skill format |

### Appendix C — Known Risks

1. **OpenWebUI license drift.** OpenWebUI could further restrict their license. Mitigation: pin to a specific version, monitor upstream, maintain a fork-from-BSD-3 plan as fallback.
2. **Foundation model API breaking changes.** Cloud providers occasionally change API behavior. Mitigation: comprehensive provider integration tests in CI, fallback chains in the Gateway.
3. **PyMuPDF AGPL boundary clarification.** Some legal interpretations of AGPL are aggressive. Mitigation: keep PyMuPDF strictly server-side, document the boundary, offer a PyMuPDF-free build configuration as a fallback (using only Docling for offsets, accepting reduced precision).
4. **Office.js platform changes.** Microsoft occasionally deprecates add-in APIs. Mitigation: stick to the documented stable API surface, monitor Microsoft announcements.
5. **Contract law variation across jurisdictions.** Skills and Playbooks default to US-law assumptions; non-US users may need customization. Mitigation: skill metadata supports jurisdiction parameters, community-contributed skills for other jurisdictions.
6. **Hallucinated citations from misuse.** If users disable verification, hallucinated citations could slip through. Mitigation: verification on by default, prominent UI when off, clear disclaimers.
7. **Maintainer bandwidth.** Open-source projects can stall when maintainers get busy. Mitigation: clear governance, multiple committers as community grows, documented release process so others can drive releases.
8. **Weak-tier inference choice by operator.** An operator may configure the deployment to allow Tier 4 or Tier 5 inference for client-confidential work, exposing the deployment to data-retention or training risk. Mitigation: the Inference Tier badge (§3.13) makes the choice transparent to the user; skills can declare `minimum_inference_tier`; deployments can disallow tiers globally; warnings surface when routing at Tier 4 and below; the Compliance Alignment Pack and Pre-Empted Procurement Objections (Appendix E) make the operator-side responsibility explicit.
9. **Workflow-context privacy risk.** If the M5+ Workflow Intelligence direction (§8.5) ships, signals from email, calendar, task systems, and document stores create a much larger sensitive-data surface than v1. Mitigation: granular consent per signal source and per scope; tier defaults that require Tier 1 / Tier 2 inference for these features; opt-in by default for every signal source; skill inspectability extends to workflow skills; relevant only if §I capabilities ship in M5+.
10. **Supply-chain compromise.** A compromised dependency could expose deployments to backdoors, data exfiltration, or remote-code-execution risk. Mitigation: SBOM published per release (§7.8); signed container images with cosign; SLSA-3 build provenance; pinned dependencies enforced in CI; continuous SCA via Trivy / Grype / Dependabot; CodeQL SAST; reproducible builds (deferred to DE-114); coordinated disclosure of supply-chain vulnerabilities per `SECURITY.md`.
11. **Privilege analysis complexity with Anonymization Layer.** When the Anonymization Layer (§4.7) is active and inference routes to Tier 3+, the rehydration step adds a process layer that complicates an attorney-client privilege analysis. Mitigation: privileged Projects (§3.11) disable anonymization by default; Tier 1 inference is the recommended posture for privileged matters; the audit log records the rehydration step explicitly; the privilege banner in the UI warns when anonymization is active in a privileged Project.

### Appendix D — Companion Documents to Produce

The following deliverables are referenced by this PRD and should be produced as separate documents:

1. **InHouse AI Inference Gateway Specification** — full technical spec for the gateway, suitable for an engineer to implement against.
2. **InHouse AI OpenAPI Surface** — complete OpenAPI 3.1 YAML covering every endpoint in §3 and §4.
3. **Skill-Authoring Guide** — how to write a high-quality skill in agentskills.io format.
4. **Playbook-Authoring Guide** — how to write a Playbook.
5. **Deployment Cookbook** — recipes for common production deployments (single-node Docker, K8s with HA Postgres, air-gapped, multi-region).
6. **Skill Drafts (Track 2)** — actual content for the 10 starter skills shipped in M1.
7. **Compliance Alignment Pack** (`docs/compliance/`, M1; per §1.8 and §8 M1 deliverables) — the document set mapping InHouse AI's design choices to SOC 2, ISO 27001, ISO 42001, GDPR, HIPAA, FedRAMP controls. Component documents: `soc2-alignment.md`, `iso-27001-alignment.md`, `iso-42001-alignment.md`, `gdpr-readiness.md`, `hipaa-readiness.md`, `provider-compliance-matrix.md`. FedRAMP and state-privacy alignment documents follow in v1.x or M2.
8. **Code & Supply-Chain Transparency Documentation** (`docs/security/`, M1; per §7.8) — `sbom.md` (SBOM generation and verification), `verifying-releases.md` (cosign signature verification commands), `build-provenance.md` (SLSA-3 attestations), `threat-model.md` (STRIDE-format threat model covering principal data flows), `dependency-security.md` (continuous SCA configuration).
9. **Pre-Empted Procurement Objections** (Appendix E of this PRD; M1) — structured responses to 17 common procurement-team objections, intended to short-cut enterprise procurement review. Updated each release.
10. **Skill-Authoring Guide — Designing Optional Inputs** (companion section of #3 above) — documents the pattern from DE-020: optional inputs that change analytical depth, not just report format.
11. **Procurement-Readiness Pack** (`docs/procurement/`, M1 stretch or v1.x; per DE-086) — SIG Lite responses, CAIQ responses, security architecture summary, data-flow diagram templates.

### Appendix E — Pre-Empted Procurement Objections

This appendix addresses common objections an information-security or legal-operations team will raise during procurement review, paired with InHouse AI's response. Each response either points to an existing artifact (a Compliance Alignment Pack document, an SBOM, the source code), names a roadmap item where parity is being approached, or explains why the objection is misframed for an OSS self-hosted product. The point is to address every plausible objection in writing, in advance, in one place. Operators evaluating InHouse AI internally can adapt these responses to their organization's procurement vocabulary; the underlying answers are stable.

#### Objection: "Is InHouse AI SOC 2 Type II certified?"

**Response.** SOC 2 Type II is an attestation issued to an operating organization, not to a software product. InHouse AI is software you run; the operator (your organization, or a hosting provider you select) is the entity that would receive a SOC 2 attestation for its operating environment. We provide a SOC 2 alignment document (`docs/compliance/soc2-alignment.md`) that maps each Trust Services Criterion to InHouse AI's design choices and configuration options, identifying which controls are project-provided, operator-provided, or joint. An operator following the alignment document's recommendations and operating the deployment in a SOC 2-compliant environment can pursue SOC 2 Type II certification of *that* environment with significantly reduced documentation effort. Closed-source vendors who claim SOC 2 are certifying their own SaaS environment, which is a different question than whether the software is suitable for your environment.

#### Objection: "Has InHouse AI been pen-tested?"

**Response.** As an open-source project, the InHouse AI codebase is continuously reviewed by anyone who wants to read it, including the project's own maintainers, contributors, and any operator's security team before deployment. The project publishes a threat model (`docs/security/threat-model.md`) identifying trust boundaries and mitigations and runs SAST (CodeQL), dependency scanning (Trivy, Dependabot), and fuzzing (for the Inference Gateway's OpenAI compatibility) on every commit. Specific operating deployments are pen-tested by the operator or their chosen security firm against their specific configuration; the project welcomes and credits responsible disclosure of findings. The project does not commission and publish a single project-wide pen test because the result would not be representative of any specific operator's deployment configuration; instead, we ship the threat model and the tooling for the operator's pen-tester to use.

#### Objection: "Where is InHouse AI's data residency?"

**Response.** InHouse AI does not have a data residency, because InHouse AI does not have data. The operator chooses where to deploy InHouse AI; the data lives in the operator's environment (the Postgres database, MinIO/S3, audit log volumes the operator provisions). The only data that potentially leaves the operator's environment is the inference request to the configured cloud LLM provider, and the operator chooses that provider and the provider's region. The Provider Compliance Matrix (`docs/compliance/provider-compliance-matrix.md`) documents each supported provider's data-residency options. For an EU-only deployment, the operator deploys to EU infrastructure, configures the Inference Gateway to route only to EU-resident provider endpoints (Anthropic EU, AWS Bedrock eu-west-X, Azure OpenAI EU regions, Google Vertex AI EU regions), or runs Tier 1 / Tier 2 inference where no provider call leaves the operator's environment.

#### Objection: "Does the AI provider train on our data?"

**Response.** This is the operator's choice, not the project's. The Inference Tier model (§1.5.2 / §1.8) makes the consequences of the choice explicit. Tier 3 (enterprise managed inference with ZDR / no-training commitments) is the recommended tier for client-confidential work; under Tier 3, no major provider trains on customer data per their commercial terms (Anthropic Commercial Terms, OpenAI Enterprise / API Commercial Terms, AWS Bedrock, Azure OpenAI, Google Vertex AI). The application surfaces the routed tier in the chat UI in real time. Skills can require a minimum tier; deployments can disallow tiers globally. If the operator routes to Tier 5 (consumer endpoints, where some providers train by default), the application warns prominently. Closed-source competitors who offer the same enterprise providers are bound by the same provider terms; the difference is that with InHouse AI, the operator can verify the routing, choose the tier, and even run Tier 1 with no provider involvement.

#### Objection: "What happens to our prompts and outputs?"

**Response.** They are stored in the operator's deployment's Postgres database under the user's chat history, governed by RBAC and the operator's retention configuration. They are sent to the configured inference provider per the routed tier (see prior objection). They are not sent to LegalQuants, the project maintainers, or any third party. The deployment emits no telemetry to LegalQuants by default (§5.7); optional opt-in anonymous usage statistics are clearly flagged and contain no content. The audit log (§5.3) provides a complete record of every prompt, response, and routing decision, which the operator can stream to their SIEM via syslog or webhook.

#### Objection: "Is the AI model audited or certified?"

**Response.** InHouse AI does not train or fine-tune its own foundation model; it uses configured cloud or local models. The model's safety and accuracy properties are inherited from the chosen provider (or, for local models, the model's authors). The project does not endorse a single model; it supports the major providers' models and any OpenAI-compatible local model. We document each major provider's model-evaluation evidence in the Provider Compliance Matrix. Where InHouse AI adds value over the bare model — through skills, playbooks, the Citation Engine, and ensemble verification — those mechanisms are open source and inspectable.

#### Objection: "What is your software supply chain story?"

**Response.** Each release ships with: a Software Bill of Materials (SBOM) in SPDX or CycloneDX format generated by Syft; signed container images (Sigstore/cosign); GPG-signed release tags; SLSA-3-aligned build provenance attestations from GitHub Actions; pinned and audited dependencies (lockfiles enforced in CI); continuous SCA via Trivy / Grype / Dependabot; SAST via CodeQL. Verification commands are documented at `docs/security/verifying-releases.md`. The full build is reproducible from a clean checkout at the release tag (reproducible builds is on the deferred-enhancements list as DE-114; the v1 commitment is the SLSA-3 provenance). We commit to coordinated disclosure of supply-chain vulnerabilities per `SECURITY.md`. Closed-source vendors typically do not provide SBOMs for their internal builds because they cannot — their dependency surface is opaque; an open-source project's supply-chain story is structurally stronger.

#### Objection: "How do you handle privileged communications?"

**Response.** Projects (§3.11) carry an optional `privileged: true` flag that forces a minimum inference tier (default Tier 2; configurable to Tier 1), disables anonymization (which adds processing steps that complicate privilege analysis), and marks every chat and audit-log entry in the Project as privileged. Audit logs include `privilege_marked` and `privilege_basis` fields (§5.3) that support filtering during e-discovery review. Work-product attribution metadata (§3.3) is stored on every model-generated artifact, establishing the chain of custody. The operator can configure the deployment to retain privileged entries on a different schedule than non-privileged entries (see DE-106). For the most sensitive privileged work, run the Project at Tier 1 (local inference) — the prompt never leaves the deployment, eliminating any third-party processor question.

#### Objection: "Is InHouse AI HIPAA-eligible?"

**Response.** A deployment can be configured to be HIPAA-eligible. The HIPAA readiness document (`docs/compliance/hipaa-readiness.md`) walks through the configuration: limit to Tier 1–3 inference; the operator signs a BAA with the chosen inference provider (Anthropic offers BAA on eligible APIs; OpenAI Enterprise supports BAA; AWS Bedrock under HIPAA-eligible services; Azure OpenAI under Azure's BAA); configure the Citation Engine and audit log per the document's PHI-handling guidance; the operator's organization receives the BAA from the provider directly. The project itself does not enter into BAAs because the project is software, not a service. This is the same structure HIPAA-aware OSS products use.

#### Objection: "How do we handle a GDPR data subject request?"

**Response.** The deployment provides per-user data export and deletion in v1 (`POST /api/v1/users/{id}/export`, `DELETE /api/v1/users/{id}`; per §5.3). Operator-side data-subject-rights tooling — for the harder case where the subject is *referenced* in some other user's chats and files rather than being a user themselves — is on the roadmap (DE-107, P1 priority for EU operators). The GDPR readiness document (`docs/compliance/gdpr-readiness.md`) covers Articles 15–22 (data subject rights), Article 28 (processor relationships), Article 30 (records of processing — exposed via audit log), Article 32 (security of processing), and Article 35 (DPIA, with template). For EU operators, route inference to EU-resident providers per the Provider Compliance Matrix.

#### Objection: "What if the model hallucinates a citation?"

**Response.** The Citation Engine (§3.3) is structurally defended against this. Every citation must reference a specific chunk of a specific document by ID; the model is constrained at generation time to cite only chunks from the retrieved set; verification compares verbatim quotes against the cited chunks at the byte level; and the LLM-judge verification step catches paraphrased claims unsupported by the source. A failed citation renders as "unverified" in the UI, never as a confident wrong citation. An operator can configure ensemble verification (§3.8) to require multi-model agreement on citations for the highest-stakes operations.

#### Objection: "Can we audit what the AI is actually doing?"

**Response.** Yes. Every state-changing API call writes to the audit log (§5.3); every inference request through the Inference Gateway is traced with provider, model, tier, token counts, and cost; every skill that runs is inspectable in source via the Skill Library UI (§3.4); every prompt and response is stored in the chat history. OpenTelemetry instrumentation feeds traces, metrics, and logs to the operator's chosen sink (Grafana, Honeycomb, Datadog, etc.); Langfuse (optional) provides LLM-specific tracing. The audit log can be streamed to the operator's SIEM. Closed-source competitors typically expose audit logs of *user actions*; InHouse AI exposes the same plus the actual prompts, responses, skills, and routing decisions, because there is no proprietary layer to hide.

#### Objection: "What about prompt injection from a malicious counterparty's document?"

**Response.** This is the genuinely-hard problem in the AI-security space; no commercial competitor has a complete answer either. InHouse AI's defenses are: skill-prompt isolation conventions in the skill-authoring guide (delimited blocks instructing the model not to interpret document content as instructions); structured-output schemas that constrain what the model can produce (DE-111); ensemble verification (§3.8) for high-stakes operations; the prompt-injection pattern library (DE-110) once it ships; and the Citation Engine's verification step which would catch a successful injection that produced an unsupported citation. The honest answer is that a sophisticated injection might still affect outputs in ways the verification does not catch; the operator's defense is the human-in-the-loop review the legal profession already requires. We do not claim to be immune.

#### Objection: "How do we know the open-source code matches what's running?"

**Response.** Container images are signed with Sigstore/cosign and accompanied by SLSA-3 build provenance attestations linking each image to the specific GitHub commit and Actions run that produced it. The operator can verify a deployed image's signature and trace it back to the source commit. Build is reproducible from the release tag (DE-114 strengthens this further). Dependencies are pinned at lockfile level; SBOMs are published per release. This is a stronger story than closed-source SaaS, where the operator has no way to verify what code is running.

#### Objection: "What's your incident response process?"

**Response.** SECURITY.md documents the disclosure email and GPG key, response-time commitments (acknowledge within 72h, fix critical issues within 30d), and public disclosure timing after fix. Past disclosures and fixes are published as security advisories on GitHub. For incidents in a specific operating deployment, the operator owns incident response in their environment; the audit log and OpenTelemetry traces provide the forensics surface, and the project supports the operator's investigation through the same disclosure channel.

#### Objection: "Is this under support?"

**Response.** The open-source project is supported by the LegalQuants-led maintainer team and the broader community. Support cadence: minor releases every 6–8 weeks; LTS designation for one minor version per year with security backports for 12 months; coordinated disclosure with response-time commitments. For organizations that require commercial support, LegalQuants offers managed services (hosted deployments, custom skill authoring, training, support) — the software remains open source and self-hostable; the services are paid (§7.1).

#### Objection: "What if LegalQuants disappears?"

**Response.** The Apache 2.0 license guarantees that the codebase, the documentation, and the rights to use and modify them survive any change in maintainer. The project's governance (§7.4) commits to a path toward a maintainer team and formal governance as the project matures. The skills are agentskills.io-compatible and run in any compatible runtime; the inference gateway is a focused 3,000 LOC piece of code that any competent engineering team can take over. The fork-able-and-deployable structure of the project is the single strongest answer to vendor-continuity risk; closed-source vendors cannot match it.

---

*End of InHouse AI PRD v0.2.*

*Drafted by Kevin Keller for contribution to LegalQuants. Comments, corrections, and contributions welcomed via GitHub once the repository is published.*
