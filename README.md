# LQ.AI

> **Open-source AI for in-house legal teams. Bring your own keys, run it where you want, own your data.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![PRD](https://img.shields.io/badge/PRD-v0.2-green.svg)](docs/PRD.md)
[![Status](https://img.shields.io/badge/Status-Pre--Release-orange.svg)](#project-status)

LQ.AI is a self-hosted AI platform purpose-built for in-house legal teams. It delivers fast contract drafting and review, verifiable citations, reusable workflow skills, playbook-driven contract analysis, a Microsoft Word integration, and a curated library of starter skills for the everyday work in-house counsel actually do — running on a laptop, an internal server, or a cloud VM, against the customer's choice of model, with zero license fees.

The project's reason for existing is simple: **in-house legal teams should not have to choose between AI assistance and data sovereignty.** Every other capable tool in this category is a closed-source SaaS that requires sending privileged information to a third-party vendor. LQ.AI runs in your environment, with your keys, against your choice of model — including fully air-gapped deployments using local inference.

---

## Why this project exists

Commercial in-house legal AI products treat their prompt engineering as proprietary moat. The skills, playbooks, citation logic, and verification heuristics that shape what the user sees are hidden inside closed-source applications, presented as "AI" but functionally indistinguishable from "a system prompt the vendor refuses to show you." Customers pay significant per-seat fees for software whose only real innovation is a hidden prompt — without any way to see, debug, or improve it.

LQ.AI inverts this. **Every artifact that shapes the user's experience is visible work product.** The skills are open source. The playbooks are open source. The citation engine's verification logic is open source. The Enhance Prompt rewriter is open source. The Organization Profile that captures org-wide voice is open source. When a user clicks "view this skill" on any active skill, they see the actual `SKILL.md` and supporting files, formatted for human reading, with provenance and the ability to fork.

The position implied by all of this is uncomfortable for the rest of the legal-AI category, and that is intentional. Customers who have been paying for software whose only real innovation is a hidden system prompt are entitled to see what they have actually been buying. When the curtain is pulled back, some products will hold up. Many will not. LQ.AI's bet is that an open, transparent product built on community-curated skills is better than a closed, opaque product built on the assumption that the user cannot see what is happening — and that the resulting trust is worth more than the marketing.

For more on this philosophy, see [PRD §1.3 Transparency as a Founding Principle](docs/PRD.md#13-transparency-as-a-founding-principle) and [§7.1 Project Philosophy](docs/PRD.md#71-project-philosophy).

---

## What it does

LQ.AI ships with a curated set of capabilities calibrated to in-house counsel work. The capability set in v1 (M1–M4):

**Conversational core with persistent history.** Multi-turn chat organized in a sidebar, with skills and files attached per chat. Search across all chat history. Streaming responses with markdown rendering. Export to Markdown, plain text, or DOCX.

**Skill Library.** Reusable structured prompt artifacts in the [agentskills.io / Anthropic Claude Skills format](https://github.com/anthropics/skills) — a folder containing `SKILL.md` (with YAML frontmatter) and optional supporting files. Three tiers: built-in skills (ship with the product), user skills (you create), and shared skills (your team or org shares). Every active skill is one click away from being readable, debuggable, and forkable. The Skill Creator is itself a skill — a meta-skill you invoke to build new skills via conversation.

**Citation Engine with character-level fidelity.** End-to-end pipeline that guarantees character-fidelity from document → model context → cited output → rendered viewer. When the model produces a claim with a citation, the system can highlight the exact substring in the source document, in the original page, with character precision — and verifies that the cited substring appears verbatim in the source before showing it. Failed citations render as "unverified" rather than as confident wrong citations.

**Projects (matter-scoped containers).** A user-curated container that scopes a set of chats, files, skills, playbooks, and a free-form context document around a single matter — a deal, a counterparty, a regulatory question, a policy refresh. Chats inside a Project automatically inherit the Project's attached files, skills, and context. Projects carry an optional `privileged: true` flag that forces minimum inference tier and marks every chat and audit-log entry as privileged.

**Organization Profile.** A singleton skill at the deployment level capturing your team's voice, jurisdiction, industry, standard positions, and escalation thresholds. Skills draw on it as context. Without it, every skill has to relearn the org from scratch every time. Like every other skill, it is open source and inspectable.

**Inference Tier Awareness.** A persistent badge in the chat UI shows which Inference Tier (1–5) your current chat is running on — from local-only inference (Tier 1) through enterprise managed inference with ZDR (Tier 3) to consumer/free endpoints (Tier 5). Click the badge for what the tier implies: where the data is going, what the provider's retention policy is, whether anonymization is on. Skills can require a minimum tier; deployments can disallow tiers globally.

**Files / Knowledge Bases.** Persistent collections of documents accessible across chats. Hybrid retrieval (vector similarity + full-text search). Files are uploaded once, ingested into the citation pipeline, and made available for retrieval.

**Enhance Prompt.** A prompt-rewriting skill that runs as an optional pre-step. You type a short, natural-language question; Enhance Prompt expands it into a structured legal prompt (role, jurisdiction, audience, scope, output format, constraints, citation expectations) and shows you the expanded version before submission. The skill itself is inspectable — you can read the SKILL.md driving the enhancement at any time.

**Playbooks (M3).** Codified legal positions for automated contract review. Easy Playbook auto-generation wizard drafts a Playbook from prior agreements. Four built-in playbooks ship in M3: Generic SaaS MSA, NDA, DPA (GDPR-aligned), Commercial MSA.

**Word Add-In (M3).** Microsoft Office.js add-in that brings LQ.AI capabilities directly into Word. Run skills, execute Playbooks, get redlines as Word tracked changes, get comments as Word comments, and ask questions about the document with citations to specific clauses — without leaving Word.

**Tabular / Multi-Document Review (M3).** Structured grid output across N documents — bulk document analysis with citation-grounded cells. "Show me the term length, survival period, carveouts, and governing law for each of these 30 NDAs."

**Slack / Teams Light Intake Bridge (M3).** A `/lq` slash command lets a Slack or Teams user forward a thread to an LQ.AI chat or run a quick skill in-thread. Light intake, deliberately not full triage/SLA/approvals — that is Streamline AI's category.

**Anonymization Layer (M2).** Pre-processing step in the Inference Gateway that pseudonymizes sensitive entities before the model call and rehydrates them after. The privacy fallback for Tier 3+ inference when local (Tier 1) is impractical but you still want defensible privacy posture.

**Autonomous Layer (M4).** Long-running per-user agents that observe activity, learn patterns, take proactive actions. Cron-scheduled tasks; watches that trigger on KB changes or document arrivals; per-user persistent memory store with user-curation UI.

**Contract Repository — Auto-Relationship Detection (M4).** Pipeline that produces a relationship graph over a Knowledge Base of contracts: amendments, restatements, references, master/sub. When you ask "which liability cap actually governs?", the system uses the graph to determine the operative document chain.

**Forward-looking (M5–M7, community-driven).** Workflow-aware context layer that integrates email, calendar, task systems, and document stores via [MCP (Model Context Protocol)](https://modelcontextprotocol.io); a Workspace Concierge that produces ranked Today views with rationales; agent dispatch with human-in-the-loop guardrails. See [PRD §8.5](docs/PRD.md#m5m7--forward-looking-workflow-intelligence-community-driven-not-committed) for the trajectory.

The full capability specification is in [PRD §3](docs/PRD.md#3-capability-specifications).

---

## Starter skills (ship with M1)

Ten starter skills ship with the M1 release, calibrated to the everyday work an in-house lawyer actually does:

| # | Skill | What it does |
|---|---|---|
| 1 | **NDA Review** | Reviews mutual or unilateral NDAs for unusual provisions, calibrated by perspective (discloser / recipient / mutual) and deal context. |
| 2 | **MSA Review — SaaS** | Reviews SaaS Master Services Agreements from the customer or vendor perspective, with severity rubric and Playbook-aligned position. |
| 3 | **MSA Review — Commercial Purchase** | Same shape as SaaS MSA but calibrated to commercial purchase agreements (goods, services, professional services). |
| 4 | **DPA Checklist Review** | Reviews Data Processing Agreements against multiple regulatory regimes (GDPR, US state privacy, HIPAA BAA, general commercial). |
| 5 | **Vendor Privacy Policy First Pass** | Triage assessment of a vendor's privacy policy — structured summary plus red-flag identification. |
| 6 | **Contract QA** | Adaptive Q&A against a single contract, with citation-grounded answers. |
| 7 | **Action Items from Client Alert** | Extracts time-sensitive action items, deadlines, and obligations from a regulatory bulletin or law firm memo into a deadline-organized checklist. |
| 8 | **Comms Improver** | Rewrites legal-jargon-heavy text in plain language for a specified non-legal audience (executive, sales team, customer-facing, etc.). |
| 9 | **Enhance Prompt** | The prompt-rewriting skill that runs as an optional pre-step on any chat. |
| 10 | **Skill Creator** | Meta-skill for building new skills via conversation. |

Each starter skill is **open source**, **inspectable in the application**, and **forkable**. If a skill produces output you disagree with, you can read the `SKILL.md`, change it, save your fork, and use the version that reflects your team's actual practice.

The next layer of skills is on the deferred-enhancement list and welcomes community contribution. See [PRD §9](docs/PRD.md#9-deferred-enhancements-and-identified-future-work) for the backlog.

---

## Quickstart

```bash
git clone https://github.com/legalquants/lq-ai.git
cd lq-ai
cp .env.example .env
# Edit .env with at least one LLM provider API key (or use local profile)
docker compose up -d              # Mode 1 (cloud LLM keys)
# OR
docker compose --profile local up -d   # Mode 2 (Ollama, air-gap-capable)
```

After ~2 minutes:

```
✓ LQ.AI shell:           http://localhost:3000/lq-ai
✓ OpenWebUI shell:       http://localhost:3000        (rebase-friendly chat, ADR 0009)
✓ Backend API docs:      http://localhost:8000/docs   (Swagger UI)
✓ Backend API docs:      http://localhost:8000/redoc  (ReDoc)
✓ Inference Gateway:     http://localhost:8001/docs
```

### First-run admin login

On first boot, the API auto-creates a first-run admin user and prints a 24-character random password **once** to the API logs at `WARNING` level. Grab it before it scrolls off:

```bash
# Default email — override with LQ_AI_FIRST_RUN_ADMIN_EMAIL in .env
docker compose logs api 2>&1 | grep "First-run admin password"
# →  WARNING:app.main:First-run admin password (record it now and rotate on first login): <24-char password>
```

Then log in:

- **URL:** `http://localhost:3000/lq-ai/login`
- **Email:** `admin@lq.ai` (or whatever you set in `LQ_AI_FIRST_RUN_ADMIN_EMAIL`)
- **Password:** the value from the log line above

The first login forces a password change (the must-change-password gate). Pick a new password ≥ 12 characters, different from the printed one.

**If you lose the admin password**, reset it from the host:

```bash
docker compose exec api python -m app.cli reset-admin-password
# →  prints a fresh random password, sets must-change-password=true, revokes active sessions
```

The shipped admin account is fine for evaluating the stack. For a production deployment, create per-user accounts via the admin UI and disable the bootstrap admin once your team is set up.

> Full pull-and-stand-up walkthrough (Helm chart, reverse-proxy recipes, reference architectures, air-gap install) is in [PRD §6 Deployment](docs/PRD.md#6-deployment); a self-contained Operator Quickstart guide lands as part of M1 Phase E (release-readiness).

The first-run setup checklist in the web UI guides you through:

1. **Create your Organization Profile** — your team's voice, jurisdiction, industry, standard positions. Or skip and create later.
2. **Configure Inference Tier policy** — which tiers are allowed for your deployment; what is the minimum for privileged work.
3. **Optionally enable MFA** and review session-timeout settings.
4. **Create your first Project** and try the starter skills against a sample document.

For production deployment, see [PRD §6 Deployment](docs/PRD.md#6-deployment) — Helm chart for Kubernetes, reverse proxy recipes (Caddy, Traefik, nginx), reference architectures (small / medium / large), and the air-gap install guide.

---

## Architecture

LQ.AI is a fork of [OpenWebUI](https://github.com/open-webui/open-webui) for the chat UI, plus a FastAPI backend, a custom-built Inference Gateway (~3,000 lines of Python that we own end-to-end for security reasons), [LangGraph](https://github.com/langchain-ai/langgraph) for stateful agent workflows, [Docling](https://github.com/DS4SD/docling) + [PyMuPDF](https://github.com/pymupdf/PyMuPDF) for document parsing with character-level offsets, and PostgreSQL with [pgvector](https://github.com/pgvector/pgvector) for unified storage of application data, vectors, and full-text indexes. Optional [Langfuse](https://github.com/langfuse/langfuse) for LLM-specific observability; OpenTelemetry throughout.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLIENT SURFACES                              │
│   Web App (OpenWebUI fork)    │    Word Add-In (Office.js)           │
└──────────────────┬─────────────┴────────────────┬────────────────────┘
                   │                              │
                   │  OpenAPI 3.1 over HTTPS      │
                   ▼                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  LQ.AI Backend (FastAPI)                        │
│   Authn/Authz │ Audit Log │ RBAC │ Projects │ Org Profile │ ...      │
└──────┬───────────────┬─────────────┬────────────┬────────────────────┘
       ▼               ▼             ▼            ▼
┌─────────────┐ ┌─────────────┐ ┌───────────┐ ┌────────────┐
│ Inference   │ │   Skill     │ │  Document │ │ Knowledge  │
│  Gateway    │ │  Service    │ │  Pipeline │ │  Service   │
│ (multi-     │ │  (skills,   │ │ (Docling+ │ │  (pgvector │
│  provider,  │ │  Org Profile│ │  PyMuPDF, │ │  + FTS)    │
│  tier-aware,│ │  singleton) │ │  Citation │ │            │
│  anonym.    │ │             │ │  Engine)  │ │            │
│  middleware)│ │             │ │           │ │            │
└──────┬──────┘ └──────┬──────┘ └─────┬─────┘ └────┬───────┘
       │               │              │            │
       └───────────────┴──────────────┴────────────┘
                              │
       ┌──────────────────────┼─────────────────────┐
       ▼                      ▼                     ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ PostgreSQL   │      │    Redis     │      │   MinIO /    │
│ + pgvector   │      │  (sessions,  │      │   S3-compat  │
│              │      │   queues)    │      │   (files)    │
└──────────────┘      └──────────────┘      └──────────────┘

LLM PROVIDERS (any combination, configured by operator):
  Cloud:  Anthropic │ OpenAI │ Google Vertex │ Cohere │ Azure │ Bedrock
  Local:  Ollama │ vLLM │ llama.cpp │ any OpenAI-compatible endpoint
```

Two deployment modes, five inference tiers:

- **Mode 1 — Self-hosted with cloud LLM keys.** Inference happens at the configured cloud provider; the rest of the system stays in your environment. Spans Tiers 2–5 depending on which provider/account you use.
- **Mode 2 — Self-hosted with local inference.** Inference runs locally via Ollama, vLLM, llama.cpp, or any OpenAI-compatible local endpoint. Air-gap-capable. Tier 1 by definition.

For more, see [PRD §1.5 Deployment Modes and the Inference Choice Spectrum](docs/PRD.md#15-deployment-modes-and-the-inference-choice-spectrum), [§2 Architecture](docs/PRD.md#2-architecture), and [§4 The LQ.AI Inference Gateway](docs/PRD.md#4-the-lq-ai-inference-gateway).

---

## Security and procurement

LQ.AI's security posture is structurally different from closed-source commercial alternatives. Three principles:

- **The operator chooses the deployment's posture.** LQ.AI does not run a SaaS that holds your data on our infrastructure; you run it on yours. The most consequential security decisions — where the deployment lives, what inference provider it routes to, how the audit log is retained, who has access — are yours, and the application makes the implications of each decision explicit.
- **The Inference Choice Spectrum is the central security trade-off.** Inference is where customer data leaves the deployment, if it does. The five-tier spectrum maps the choice across local-only inference (Tier 1), customer-hosted cloud inference (Tier 2), enterprise managed inference with ZDR / no-training commitments (Tier 3), standard cloud API (Tier 4), and consumer or free tier (Tier 5). Tier 3 is recommended for most pragmatic enterprise deployments. Tier 1 is recommended for the most sensitive privileged work.
- **Transparency replaces opacity.** Every release ships with an SBOM (Software Bill of Materials), signed container images (Sigstore/cosign), SLSA-3 build provenance attestations, a published threat model, and alignment documentation for SOC 2, ISO 27001, ISO 42001, GDPR, HIPAA, and FedRAMP — mapping our design choices to each framework's controls. Where LQ.AI does not yet match a specific commercial competitor's control, it is named on the public deferred-enhancements list with a roadmap.

For procurement reviews, see:

- [PRD §1.8 Security Posture](docs/PRD.md#18-security-posture) — the full security philosophy and tier model.
- [PRD Appendix E — Pre-Empted Procurement Objections](docs/PRD.md#appendix-e--pre-empted-procurement-objections) — 17 common procurement-team objections with direct responses.
- [docs/compliance/](docs/compliance/) — Compliance Alignment Pack (SOC 2, ISO 27001, ISO 42001, GDPR, HIPAA, FedRAMP).
- [docs/security/](docs/security/) — SBOM, signed-release verification, build provenance, threat model, dependency security.

---

## Accessibility

LQ.AI is built to be **usable by every attorney on a team — including those who rely on assistive technology, keyboard navigation, or low-vision modes**. Most legal-tech products treat accessibility as a compliance afterthought; we treat it as a quality bar that ships from M1.

Concretely, this means:

- **WCAG 2.1 AA as the design target** for every shipped surface — color contrast, focus indication, keyboard reachability, semantic structure.
- **Semantic HTML + ARIA patterns by default** — every tab, dialog, button, and form control uses the correct role, label, and state attributes (the top-tab nav implements the WAI-ARIA tablist pattern with roving arrow-key focus; modals use `role="dialog"` + `aria-modal="true"` + escape-to-close).
- **Keyboard parity with mouse** for every power feature — Enhance Prompt (`⌘E`), Skill Creator, knowledge-base attach, and the launcher all reachable without a pointing device.
- **Tested both ways** — automated `axe-cli` scans across primary surfaces (target: 0 critical/serious findings), plus Cypress E2E coverage of the chrome's keyboard and screen-reader-relevant assertions, plus a manual keyboard pass before each release.
- **Theming respects user-agent preferences** — the Practice palette ships with light-mode defaults; downstream forks and operator deployments can override the semantic CSS variables (see [§10 of the M1 frontend design](docs/superpowers/specs/2026-05-10-m1-frontend-design.md#10-theming-customization-and-developer-extensibility-open-source-posture)) to match their own contrast and color-blindness needs.

Accessibility findings are treated as defects, not nice-to-haves. If you find one, [open an issue](https://github.com/LegalQuants/lq-ai/issues) — we'll prioritize it alongside functional bugs.

---

## Project status

**Pre-release.** The PRD is at v0.2 and ten starter skills are authored. Active work toward M1.

**Roadmap:**

| Milestone | Theme | Timeline |
|---|---|---|
| M1 — Foundation | Working self-hostable release with 10 starter skills, Projects, Organization Profile, Inference Tier Awareness, Compliance Alignment Pack, Code & Supply-Chain Transparency, MFA option, per-user export/delete | ~6 weeks |
| M2 — Citation Engine and Anonymization | Verifiable citations with character-level fidelity; Anonymization Layer in the Gateway | ~6 weeks after M1 |
| M3 — Playbooks, Word Add-In, Tabular Review, Slack/Teams | Feature parity with commercial in-house legal AI; surface coverage beyond the web | ~8 weeks after M2 |
| M4 — Autonomous Layer and Contract Repository | Background agents, watches, scheduled tasks; contract relationship graph | ~8 weeks after M3 |
| M5–M7 — Forward-Looking Workflow Intelligence | Community-driven; not committed. MCP-client subsystem operationalized; Signal Aggregation Service; Today view with prioritization; agent execution framework with human-in-the-loop guardrails. | TBD |

For the full roadmap and the ~50+ deferred enhancements ready for community contribution, see [PRD §8 Roadmap](docs/PRD.md#8-roadmap) and [§9 Deferred Enhancements](docs/PRD.md#9-deferred-enhancements-and-identified-future-work).

---

## Contributing

Substantive contributions are welcome and credited. **Skills, playbooks, jurisdictional adaptations, and verification heuristics contributed by practicing lawyers carry the same weight in the project as code contributed by engineers.** Both are work product. Both deserve attribution.

Two contribution paths, with separate contribution guides:

- **Code, infrastructure, deployment recipes, documentation:** see [`CONTRIBUTING.md`](CONTRIBUTING.md). DCO sign-off required (no CLA), code style enforced by `ruff` + `mypy` (Python) and Prettier + ESLint (JS), pytest coverage target 80%.
- **Skills (the canonical artifact of value in this project):** see [`skills/CONTRIBUTING.md`](skills/CONTRIBUTING.md). Skills containing legal substance require attestation that the substantive content is accurate to the contributor's knowledge and review by at least one practicing attorney plus one engineer. The skill-authoring guide ([`docs/skill-authoring-guide.md`](docs/skill-authoring-guide.md)) documents the patterns established by the M1 starter skills — perspective branching, severity rubrics, optional-input design, output-format conventions.

A few things that are easy and meaningful for first contributions:

- **Author a new starter skill** — pick one from [PRD DE-001 candidates](docs/PRD.md#de-001--additional-starter-skills-beyond-the-m1-set) (Settlement Agreement Review, Employment Offer Letter Review, Open Source License Compatibility Checker, etc.).
- **Add a regulatory regime to DPA Checklist Review** — Brazil LGPD, China PIPL, Singapore PDPA, India DPDP Act ([PRD DE-002](docs/PRD.md#de-002--additional-regimes-for-dpa-checklist-review)).
- **Translate a starter skill** — non-English jurisdictional adaptations.
- **File or fix a Compliance Alignment Pack control mapping** in `docs/compliance/`.
- **Write a deployment recipe** for your environment (Kubernetes flavor, reverse proxy, OAuth IdP integration).

The full backlog is in [PRD §9 Deferred Enhancements](docs/PRD.md#9-deferred-enhancements-and-identified-future-work) — bounded enhancements that have been deliberately scoped out of the v1 release and where the architectural slot exists. Pick one and propose a PR.

---

## License

[Apache License 2.0](LICENSE) for the LQ.AI codebase. The patent-grant clause is important given LegalQuants' broader ecosystem; the explicit trademark protection is enterprise-friendly; the license is compatible with most other OSS licenses for ecosystem integration.

The OpenWebUI fork (the `web` component) inherits OpenWebUI's license. We follow OpenWebUI's branding requirements and document the relationship clearly.

PyMuPDF (AGPL-3.0) is used server-side only and not redistributed as a library; the AGPL boundary is the HTTP API. Documented in [PRD Appendix B](docs/PRD.md#appendix-b--license-summary-matrix) and the [PyMuPDF AGPL boundary risk](docs/PRD.md#appendix-c--known-risks).

---

## Governance

**Initial model: BDFL.** Kevin Keller is the initial maintainer. LegalQuants stewards the project: owns the GitHub org, controls the trademark, employs the maintainer.

The project's commitment to community contribution: *"LQ.AI welcomes contributions from any in-house counsel, legal-ops practitioner, or engineer who wants to advance open legal AI."*

Path to broader governance is documented but not implemented in v1: as the project matures, transition to a maintainer team and formal governance (CNCF or Apache Software Foundation models). See [PRD §7.4 Governance](docs/PRD.md#74-governance).

**No "open core" gating.** Features useful to in-house legal teams are in the open-source release. We will not move features behind a paid offering as the project matures. (LegalQuants may build commercial *services* — hosted deployments, custom skill authoring, training, support — but the software itself stays whole. See [PRD §7.1 Project Philosophy](docs/PRD.md#71-project-philosophy).)

---

## Project channels

- **GitHub Issues** for bugs and feature requests.
- **GitHub Discussions** for community Q&A.
- **Discord** (LegalQuants-hosted) for synchronous community.
- **Blog** at [legalquants.com/blog](https://legalquants.com/blog) for releases and roadmap updates.

For security disclosures, see [`SECURITY.md`](SECURITY.md). The disclosure process includes safe-harbor language for good-faith security researchers, response-time commitments (acknowledge within 72h, fix critical issues within 30d), and credit attribution for reporters.

---

## Documentation

- [Product Requirements Document](docs/PRD.md) — the canonical specification (v0.2).
- [`docs/skill-authoring-guide.md`](docs/skill-authoring-guide.md) — how to write a high-quality skill.
- [`docs/playbook-authoring-guide.md`](docs/playbook-authoring-guide.md) — how to write a Playbook.
- [`docs/deployment-cookbook.md`](docs/deployment-cookbook.md) — recipes for production deployments.
- [`docs/compliance/`](docs/compliance/) — Compliance Alignment Pack.
- [`docs/security/`](docs/security/) — security artifacts (SBOM, threat model, supply-chain transparency).
- [`docs/procurement/`](docs/procurement/) — procurement-readiness templates (SIG Lite, CAIQ).

---

## Acknowledgments

LQ.AI builds on substantial open-source work. The most consequential dependencies:

- [OpenWebUI](https://github.com/open-webui/open-webui) — chat UI shell.
- [LangGraph](https://github.com/langchain-ai/langgraph) — agent runtime.
- [Docling](https://github.com/DS4SD/docling) and [PyMuPDF](https://github.com/pymupdf/PyMuPDF) — document parsing.
- [pgvector](https://github.com/pgvector/pgvector) — vector storage in PostgreSQL.
- [Anthropic Claude Skills](https://github.com/anthropics/skills) — the agentskills.io format the project adopts as its skill substrate.
- [OpenTelemetry](https://opentelemetry.io/) — observability.
- [Langfuse](https://github.com/langfuse/langfuse) — LLM-specific observability.

Each is acknowledged in the [License Summary Matrix](docs/PRD.md#appendix-b--license-summary-matrix). Contributions from these ecosystems are how LQ.AI exists at all.

---

*LQ.AI is authored by Kevin Keller and contributed to LegalQuants. Comments, corrections, and contributions welcomed via GitHub.*
