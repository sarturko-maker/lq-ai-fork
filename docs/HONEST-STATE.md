# Honest State

> Catalog of what LQ.AI ships today, what is deferred, and how to verify each. Maintained per release.

## What this doc is

This document catalogs what LQ.AI ships today, what is deferred, and how an operator can verify each. We publish it in source because the verification path for an open-source project terminates in code, not in a vendor's marketing claims. If you find a discrepancy between this doc and the codebase, the codebase is canonical; please [open an issue](https://github.com/LegalQuants/lq-ai/issues).

## How to read this

Each table has three columns:

- **Capability** — what the operator gets.
- **Status** — `M1` (shipped today), `partial` (architectural slot exists; full pipeline is deferred), or `deferred-Mx` (named in the roadmap; not running yet).
- **Verification** — the file path, test command, or doc the operator can read to confirm the claim.

Status markers reference the roadmap milestones (M1 → M4) documented in [README.md](../README.md#project-status) and [PRD §8](PRD.md#8-roadmap).

## Where M1 sits

M1 is the foundation milestone: a self-hostable release that delivers conversational legal AI on top of the ten starter skills, with the engineering surfaces (audit, tier enforcement, projects, knowledge bases, saved prompts, receipts, the skill-creator pipeline) that the M2–M4 capability work builds on. M1 explicitly does not include the Citation Engine verification pipeline or the Anonymization Layer middleware; those land in M2. M1 ships three provider adapters (Anthropic, OpenAI, Ollama); Vertex AI and AWS Bedrock land in M2 and are fully spec'd in [PRD §9](PRD.md#9-deferred-enhancements-and-identified-future-work) ready for contribution.

The honest reading is that an operator can deploy LQ.AI in M1 for the everyday in-house work that the ten starter skills cover, with the knowledge that some PRD-described capabilities (Citation Engine, Anonymization Layer, Playbooks, Word add-in, Tabular Review, Slack/Teams bridge, Autonomous Layer, Contract Relationship graph) are deferred to later milestones. The sections below catalog each capability so the operator can make that assessment with the same information the maintainer team has.

---

## 1. Conversational and workspace surface

This is the surface an in-house counsel touches every day: chat, matter workspaces, skills, knowledge bases, saved prompts, receipts. Every row below is wired end-to-end in M1 and covered by at least one Cypress E2E spec.

| Capability | Status | Verification |
|---|---|---|
| Multi-turn chat with persistent history | M1 | `api/app/api/chats.py`; `web/cypress/e2e/chat.cy.ts` |
| Matter (project) workspace with attached files / skills / KBs | M1 | `api/app/api/projects.py`; `web/src/routes/lq-ai/matters/[id]/+page.svelte` |
| Slash-invoked skills with provenance pill | M1 | `web/cypress/e2e/wave-d2-skill-creator.cy.ts` Test 4 |
| Community skill catalog via [`LegalQuants/lq-skills`](https://github.com/LegalQuants/lq-skills) submodule | M1 | `skills/community/` (30+ skills); loader walks both built-in + community paths with built-in winning on slug collision (`api/app/skills/loader.py`); operator refreshes via `git submodule update --remote skills/community` |
| Skill capture from a chat reply | M1 | `web/cypress/e2e/wave-d2-skill-creator.cy.ts` Test 1 |
| Wizard-based skill authoring (from scratch) | M1 | `web/cypress/e2e/wave-d2-skill-creator.cy.ts` Test 2 |
| Fork built-in or team skills | M1 | `web/cypress/e2e/wave-d2-skill-creator.cy.ts` Test 3 |
| Skill versions tab + per-version audit log | M1 | `web/cypress/e2e/wave-d2-skill-creator.cy.ts` Test 6 |
| Try-it sandbox per skill (component-state) | M1 | `web/cypress/e2e/wave-d2-skill-creator.cy.ts` Test 5; cross-tab conversation persistence in the sandbox is deferred (read the M1 limitation in `web/src/lib/lq-ai/components/SkillTryItPane.svelte`) |
| Saved Prompts library with one-click "Use in chat" | M1 | `web/cypress/e2e/wave-m1-final-surfaces.cy.ts` Test 1; `api/app/api/saved_prompts.py` |
| Knowledge bases — create, attach documents, ingest to `ready` | M1 | `web/cypress/e2e/wave-m1-final-surfaces.cy.ts` Test 2; `api/app/api/knowledge_bases.py`; `api/app/pipeline/ingest.py`; `api/app/workers/document_pipeline.py` |
| Receipts drawer with per-event provenance | M1 | `web/cypress/e2e/wave-d1-power-features.cy.ts` Test 4 + `wave-m1-final-surfaces.cy.ts` Test 3; `api/app/api/chat_receipts.py` |
| Tier-floor refusal with admin override | M1 | `web/cypress/e2e/wave-d1-power-features.cy.ts` Test 3 + Test 5; `gateway/app/tier_floor.py` |
| Admin model-alias CRUD (create / edit / delete) | M1 with one known UX gap | `web/src/routes/lq-ai/admin/models/+page.svelte` + `AliasForm.svelte`; **known issue in M1:** the edit modal's Model dropdown shows only the currently-saved model (the autocomplete prop `providerModels` is not populated by the parent — the field remains free-text-editable but autocomplete is missing). Tracked as [DE-272](PRD.md#de-272--admin-aliasform-model-dropdown-autocomplete-population). The light/dark color-contrast issue originally reported alongside this was fixed pre-tag — the `dark:` Tailwind variants were removed so the form matches the surrounding admin chrome |
| Enhance Prompt (⌘E) | M1 | `web/cypress/e2e/wave-d1-power-features.cy.ts` Test 1; `api/app/api/enhance_prompt.py` |
| KB attach modal from the composer | M1 | `web/cypress/e2e/wave-d1-power-features.cy.ts` Test 2 |
| Audit log of all sensitive actions | M1 | `api/app/audit.py`; admin reads at `/lq-ai/admin/audit-log` |
| FTS over chat history | M1 | `api/app/api/chats.py` (search route); migration `0016_chat_messages_fts.py` |
| GDPR-aligned export and account deletion | M1 | `api/app/workers/user_export.py`; `api/app/workers/user_deletion.py`; `api/app/api/users.py` |

---

## 2. Inference gateway and providers

The Inference Gateway is the security boundary — the only component holding privileged provider API keys, the only component making outbound calls to inference providers. Three provider adapters ship in M1: Anthropic, OpenAI, and Ollama (local Tier 1). Vertex AI and AWS Bedrock are spec'd in PRD §9 with wire-format detail and acceptance criteria; they are contributor-friendly work units.

| Capability | Status | Verification |
|---|---|---|
| Inference gateway with provider routing | M1 | `gateway/app/router.py` |
| Anthropic provider adapter | M1 | `gateway/app/providers/anthropic.py` |
| OpenAI provider adapter | M1 | `gateway/app/providers/openai.py` |
| Ollama provider adapter (local, Tier 1) | M1 | `gateway/app/providers/ollama.py`; `docker-compose.yml` `--profile local` |
| Google Vertex AI provider adapter | deferred-M2 | Wire-format spec is in [PRD §9](PRD.md#9-deferred-enhancements-and-identified-future-work) ready for a contributor to pick up |
| AWS Bedrock provider adapter | deferred-M2 | Same — fully spec'd in PRD §9 with AWS Event Stream parser + SigV4 acceptance criteria |
| Tier enforcement (Tiers 1 – 5) | M1 | `gateway/app/tier_floor.py` (124 LOC) |
| Privileged-matter tier floor override (admin only) | M1 | `web/cypress/e2e/wave-d1-power-features.cy.ts` Test 3 + Test 5 |
| Routing log (per-inference) | M1 | `gateway/app/routing_log.py` |
| Provider-key encryption at rest (Fernet-wrapped master-key path) | M1 | `gateway/app/secrets.py`; `docs/security/encrypted-keys.md` |
| Hot-reload of gateway config via SIGHUP | M1 | `gateway/app/config_holder.py`; `gateway/app/config_loader.py`; `docs/adr/0010-gateway-config-hot-reload.md` |
| Per-skill prompt-injection detection rates published | not yet | No published numbers in M1; see §6 below for the engineering-discipline plan |

---

## 3. Capabilities described in the PRD that are not yet wired

These are the two flagship M1-described capabilities where the architectural slot exists in the codebase but the underlying pipeline is not yet running. They are called out individually rather than in tables because they shape what an M1 deployment can and cannot promise to its users.

### 3.1 Citation Engine — architectural slot, not wired

The PRD ([§3.3](PRD.md#33-citation-engine-exact-quote)) describes a Citation Engine with character-level verification of every claim against source documents — a pipeline that guarantees character-fidelity from document → model context → cited output → rendered viewer, and that renders failed citations as "unverified" rather than as confident wrong citations. **In M1, the architectural slot exists but the verification pipeline is not running.**

The endpoint at `GET /api/v1/chats/{chat_id}/messages/{message_id}/citations` returns whatever the message row stores; M1 stores `[]`. The chunk-level provenance the engine will draw on is partially in place: `api/app/pipeline/ingest.py` captures page and character offsets per chunk into `document_chunks` (migration `0005_documents_and_chunks.py`), and hybrid retrieval (`api/app/knowledge/retrieval.py`) returns the chunks. What is not in place is the verification step that re-reads the cited substring from the source document and confirms it appears verbatim before showing it in the rendered output.

**What an operator can verify today:**

- Read the endpoint: `api/app/api/chats.py:1174-1212`. The docstring is explicit — "M1 stores `[]`; M2 populates the structured shape. C3 returns whatever the row carries so this endpoint is forward-compatible without an additional task."
- Read the chunk-level provenance schema: `api/alembic/versions/0005_documents_and_chunks.py`.
- Read the retrieval path: `api/app/knowledge/retrieval.py`.
- Read the PRD's described architecture: [PRD §3.3 Citation Engine](PRD.md#33-citation-engine-exact-quote).

**What this means for an M1 deployment:**

- Claims rendered in chat are not independently verified against source documents.
- The model's apparent citations should be treated as suggestions, not as verified provenance, until M2.
- The audit log captures the model's output verbatim (`api/app/audit.py`), so an operator can review what was claimed and reconstruct verification manually if the matter requires it.
- A user-curated knowledge base attached to a chat does provide retrieval-grounded context (vector similarity + full-text search per `api/app/knowledge/`), but the model's use of that context is not itself byte-level verified at the citation step in M1.

The path forward is in PRD §3.3 plus the deferred enhancements that block on the Citation Engine. A contributor who wants to land the engine should open a discussion before starting — this requires maintainer context, not a mini-PRD. The reason it is called out individually rather than listed in the deferred table is that the user-facing language in M1 (chat messages may render text that resembles citations) needs to be interpreted with this gap in mind.

### 3.2 Anonymization Layer — config slot, not running

The PRD ([§4.7](PRD.md#47-anonymization-layer-m2)) describes an Anonymization Layer that swaps named entities for stable placeholders on the request path and rehydrates them on the response path — the privacy fallback for Tier 3+ inference paths when local (Tier 1) inference is impractical but defensible privacy posture is still required. **In M1, the configuration schema loads but the middleware does not run.**

The gateway accepts an `anonymization:` block in `gateway.yaml` (the schema is defined at `gateway/app/config.py:250` and instantiated at `gateway/app/config.py:329`), and the admin surface that will let operators inspect that configuration at runtime is wired through — but it returns 501 with an explicit message rather than data, because the underlying middleware is not in the request pipeline yet.

**What an operator can verify today:**

- Read the 501: `gateway/app/api/admin.py:270-282`. The next-task field is named explicitly ("M2 — anonymization middleware (PRD §4.7)").
- Read the config schema that accepts the block but does not act on it: `gateway/app/config.py:250-251` ("`anonymization:` block. M2 feature; A3 just loads it.").
- Read the request path to confirm anonymization is not in it: `gateway/app/api/inference.py` (the chat-completions handler) — there is no `anonymize_request` call before the provider dispatch and no `rehydrate_response` call after.
- Read the PRD's described architecture: [PRD §4.7 Anonymization Layer](PRD.md#47-anonymization-layer-m2).

**What this means for an M1 deployment:**

- Documents and entities are sent to the configured inference provider in full, with no entity substitution at the gateway boundary.
- This is the same posture as every other M1 inference path: the provider receives the operator's content per the operator's provider choice (the operator's bring-your-own-keys control). M1 does not introduce a hidden transformation step.
- For deployments where entity substitution is a hard requirement, M1 is not the right milestone — wait for M2, or self-host on Tier 1 (Ollama) only so the data never leaves the operator's environment regardless of substitution.
- Operators on Tier 3 cloud paths (enterprise managed inference with ZDR / no-training commitments) get the contractual privacy posture of that tier in M1; the anonymization layer is an additional defense-in-depth control that lands in M2.

The verification path is itself the signal: an operator can read the code that does not run yet, the configuration schema that loads without enforcement, and the request path that confirms the absence of the middleware. A closed-source vendor cannot show an operator a code path that is not running; an open-source project can.

---

## 4. Capabilities not yet started in source

These are PRD-committed capabilities where the directory or subsystem does not yet exist in the codebase. They are honest milestone deferrals, not partial implementations — the milestone target is firm, and the architectural slot will land when the milestone work starts.

| Capability | Status | Verification |
|---|---|---|
| Word add-in (Office.js) | deferred-M3 | `ls word-addin/` — directory absent. Spec in [PRD §3.9](PRD.md#39-word-add-in-m3) |
| Playbooks (codified legal positions, auto-generation wizard) | deferred-M3 | No `playbooks` table in `api/alembic/versions/` (M1 head is 0023). Spec in [PRD §3.7](PRD.md#37-playbooks-m3) |
| Tabular / multi-document review (M3) | deferred-M3 | No grid surface; spec in [PRD §3.8](PRD.md#38-tabular-multi-document-review-m3) |
| Slack / Teams light intake bridge (M3) | deferred-M3 | No `/lq` slash command surface; spec in [PRD §3.10](PRD.md#310-slack--teams-light-intake-bridge-m3) |
| Autonomous Layer (cron tasks, watches, per-user memory) | deferred-M4 | No `autonomous_tasks` table; spec in [PRD §3.11](PRD.md#311-autonomous-layer-m4) |
| Contract Repository auto-relationship detection (M4) | deferred-M4 | No `contract_relationships` table; spec in [PRD §3.12](PRD.md#312-contract-repository--auto-relationship-detection-m4) |
| MCP-client subsystem (M5+) | deferred-M5 | `grep -r "mcp" api/app gateway/app` is empty; spec in [PRD §8.5](PRD.md#m5m7--forward-looking-workflow-intelligence-community-driven-not-committed) |

---

## 5. Compliance and procurement state

The Compliance Alignment Pack at [`docs/compliance/`](compliance/) is a documented commitment whose individual framework documents are stubs at v1 launch. The pack format is documented in [`docs/compliance/README.md`](compliance/README.md); per-framework alignment docs land as M1 and M2 ship. The pack is not a certification — LQ.AI is open-source software the operator deploys and operates, and the operator's deployment is what gets certified, not the project itself. The pack is the project's contribution to the operator's certification work: pre-mapped control responses with citations into source so the operator's compliance team has a substantive starting point.

Some of the highest-value compliance documents (OWASP LLM Top 10 mapping, NIST AI RMF 1.0 Profile, the procurement-readiness pack itself) are scoped as contributor-friendly work and have mini-PRDs published at [`docs/contribute/mini-prds/`](contribute/mini-prds/). They are off the maintainer's critical path because the foundation is in source and the work is reading the foundation and producing the framework-mapped document on top of it.

| Document | Status | Verification |
|---|---|---|
| SOC 2 Type II alignment | stub (target M1) | `docs/compliance/README.md` describes the format; `soc2-alignment.md` not yet authored |
| ISO/IEC 27001:2022 alignment | stub (target M1) | Same |
| ISO/IEC 42001:2023 alignment | stub (target M2) | Same |
| GDPR readiness | stub (target M1) | Same |
| HIPAA Security + Privacy Rule alignment | stub (target M2) | Same |
| FedRAMP Moderate alignment | stub (target M2) | Same |
| OWASP LLM Top 10 mapping | not yet | [Mini-PRD open](contribute/mini-prds/owasp-llm-top10-mapping.md) — contributor-friendly |
| NIST AI RMF 1.0 Profile | not yet | [Mini-PRD open](contribute/mini-prds/nist-ai-rmf-profile.md) |
| Procurement Pack (SIG Lite + CAIQ pre-fills) | not yet | [Mini-PRD open](contribute/mini-prds/procurement-readiness-pack.md); structure stubbed at [`docs/procurement/`](procurement/) |
| Threat model (STRIDE) | M1 | [`docs/security/threat-model.md`](security/threat-model.md) |
| Architecture document | M1 | [`docs/architecture.md`](architecture.md) |
| Cryptography reference | M1 | [`docs/security/cryptography.md`](security/cryptography.md) |
| Dependency-management posture | M1 | [`docs/security/dependencies.md`](security/dependencies.md) |
| Audit-logging policy | M1 | [`docs/security/audit-logging.md`](security/audit-logging.md) |
| Encrypted-keys ADR (master-key workflow) | M1 | [`docs/security/encrypted-keys.md`](security/encrypted-keys.md) |
| Security policy + coordinated disclosure | M1 | [`SECURITY.md`](../SECURITY.md) |

---

## 6. Engineering-discipline state

The project's commitment is that engineering rigor is measurable, not asserted. The signals below are the M1 snapshot — what is in CI, what is in the test suite, what is in the release pipeline, and which engineering practices are on the roadmap but not yet enforced. Where a discipline is not yet shipped, the path is named so a reviewer can confirm both what is and what is not in place.

| Practice | Status | Verification |
|---|---|---|
| Frontend unit tests (Vitest) | M1 | `cd web && npx vitest run` — 53 spec files; 397 tests passing as of Wave C |
| Backend tests (pytest) | M1 | 70 test files in `api/tests/`; run via `cd api && pytest` |
| Gateway tests (pytest) | M1 | 27 test files in `gateway/tests/`; run via `cd gateway && pytest` |
| Cypress E2E (LQ.AI shell) | M1 | 6 LQ.AI specs in `web/cypress/e2e/` (`wave-a-chrome`, `wave-b-surfaces`, `wave-c-matters`, `wave-d1-power-features`, `wave-d2-skill-creator`, `wave-m1-final-surfaces`) plus 4 upstream OpenWebUI specs |
| Documented E2E coverage matrix per surface (`docs/test-strategy.md`) | not yet | CLAUDE.md notes `docs/test-strategy.md` as an M1 deliverable; the file does not yet exist. The coverage signal today is the spec inventory above and the "tests as documentation" framing in PRD §5.8; the explicit per-surface coverage matrix (smoke / happy path / edge cases) with milestone tags is deferred. Closes the criticism that "tests as documentation" is overstated when 6 specs cover the M1 LQ.AI surfaces without an explicit per-surface contract. |
| Coverage gate (PRD §5.8 target: 80% api / 90% gateway) | not enforced | `.github/workflows/ci.yml` runs pytest but does not fail below threshold; the gap is documented |
| Ruff lint + format (Python) | M1 | `.github/workflows/ci.yml`; configured in each subsystem |
| mypy type-checking (api: standard, gateway: strict) | M1 | Same |
| svelte-check (web, LQ.AI-owned code) | M1 | `cd web && npm run check:lq-ai` — 0 errors on all LQ.AI-owned paths (`src/lib/lq-ai/**`, `src/routes/lq-ai/**`). Full-scope check (`npm run check`) shows ~9,359 inherited errors from upstream OpenWebUI files; see §6.1 below. |
| Mutation testing | not yet | Out of M1 scope; on the engineering-discipline roadmap |
| Property-based tests (Hypothesis) | not yet | Same |
| Eval harness with held-out test sets | not yet | Per-skill `test-plan.md` exists for the 10 starter skills; eval execution is deferred. [Mini-PRD for skill acceptance tests](contribute/mini-prds/skill-acceptance-tests.md) is the contributor-friendly path |
| Cypress in CI | not yet | E2E suite runs locally; CI integration is on the engineering-discipline roadmap |
| OpenSSF Scorecard | not yet | [Mini-PRD open](contribute/mini-prds/openssf-scorecard-and-badges.md) |
| OpenSSF Best Practices Badge | not yet (target Passing at M1, Silver at M2) | Same mini-PRD |
| Accessibility audit (WCAG 2.1 AA + axe-core CI gate) | not yet (axe-cli scans in dev; CI gate deferred) | The design target is WCAG 2.1 AA per [`README.md`](../README.md#accessibility); CI enforcement deferred |
| Air-gap install verification in CI | not yet | [Mini-PRD open](contribute/mini-prds/air-gap-install-verification.md) |
| Per-skill prompt-injection detection rates | not yet | Out of M1 scope; on the engineering-discipline roadmap |
| Per-skill PII leakage measurement | not yet | Depends on Anonymization Layer (§3.2 above) |
| Annual third-party penetration test | committed; not scheduled | First engagement targeted within 90 days of M1 release |
| Annual adversarial-AI red-team engagement | committed; not scheduled | Same posture |
| Signed commits enforced on `main` | not yet | DCO sign-off is required ([CONTRIBUTING.md](../CONTRIBUTING.md)); cryptographic commit signing is on the engineering-discipline roadmap |
| SLSA-3 build provenance | committed | Documented in [`docs/security/releases/README.md`](security/releases/README.md); verified on release builds |
| Sigstore-signed container images | committed | Same |
| SBOM with every release | committed | Same |

### 6.1 OpenWebUI fork — inherited TypeScript-check debt

The LQ.AI web frontend is a fork of OpenWebUI (per ADR 0001). When `svelte-check` runs against the full codebase (`npm run check`), approximately 9,359 TypeScript errors surface — all in upstream OpenWebUI files inherited at fork time. None are in LQ.AI-owned code (`src/lib/lq-ai/**`, `src/routes/lq-ai/**`).

**Why these are not critical bugs:**

- They are TypeScript strict-mode signals (implicit `any`, missing property declarations on legacy `.js` files, narrowing issues in upstream Svelte components) — not runtime errors. The application runs correctly; these are static-analysis warnings about upstream code we did not author.
- None affect the Inference Gateway, which is the security boundary. The gateway is a separate Python service with its own clean typecheck (mypy strict mode, CI-enforced).
- None affect the LQ.AI surfaces an operator interacts with. Those are the `/lq-ai/*` routes and `src/lib/lq-ai/**` components, which pass strict typecheck with 0 errors.
- Vitest unit tests (400 tests, 53 spec files) and Cypress E2E tests exercise the actual runtime behavior and are 100% passing on M1.

**What ships in M1:** CI scopes `svelte-check` to LQ.AI-owned code via `npm run check:lq-ai` (using `tsconfig.lq-ai.json`) so the typecheck signal stays meaningful for new contributions. Operators or auditors who want the full picture can run `npm run check` for the unscoped check, see the upstream errors, and verify they are confined to upstream paths.

**Migration plan (deferred to post-M1):** Tracked as DE-262. Path: clean up the highest-impact upstream files first (auth, chat shell, settings), then long-tail. Target Silver OpenSSF Best Practices Badge tier requires no strict-mode noise; the migration is a stepping stone toward that badge.

---

## 7. Operational state

The deployment story in M1 is Docker Compose plus a drafted Helm chart. The supporting operational artifacts — reverse-proxy + TLS recipes, backup tooling, runbooks, SLOs — are partially shipped or deferred. The operator is the running organization; the project provides the artifacts that make running it tractable, and surfaces honestly where additional operator work is required today.

| Surface | Status | Verification |
|---|---|---|
| Docker Compose reference deployment | M1 | [`docker-compose.yml`](../docker-compose.yml) — 7 services in the default profile |
| Local-only profile (Ollama + PaddleOCR) | M1 | `docker compose --profile local up` |
| Helm chart for Kubernetes | drafted (M1) | [`deploy/helm/lq-ai/`](../deploy/helm/lq-ai/) |
| Reverse-proxy + TLS recipes (Caddy, Traefik, nginx) | not yet | [Mini-PRD open](contribute/mini-prds/reverse-proxy-tls-deployment-recipes.md) |
| Backup + restore tooling (`pg_dump` + MinIO snapshot wrapper) | not yet | `ls scripts/` — no backup tooling |
| Runbooks for operational tasks | not yet | `ls docs/` — no `runbooks/` directory |
| SLO / SLI publication | not yet | OpenTelemetry instrumentation ships at M1; service-level objectives are deferred |
| Public status page (for any LegalQuants-hosted artifacts) | not yet | No hosted service in M1; the project ships as software the operator runs |
| Public postmortem template + commitment | not yet | No incidents in operator-facing infrastructure yet; the publication commitment lands with the engineering-discipline roadmap |
| Quarterly DR test cadence | not yet | Deployment recipes ship at M1; test cadence is operator-side and not yet documented |

---

## 8. How to verify everything in this doc

The general protocol is the same for every row:

1. Clone the repository: `git clone https://github.com/legalquants/lq-ai.git`.
2. Follow the [Quickstart](../README.md#quickstart) in the README to stand the stack up.
3. Browse the file path or run the test command cited in the Verification column.
4. If you want to read the source without standing the stack up, the cited paths are all in the repository and any file viewer (GitHub web UI, `cat`, an editor) is sufficient.

If a claim in this document does not check out — a path does not exist, a test does not pass, a status marker is wrong — the codebase is canonical. Please [open an issue](https://github.com/LegalQuants/lq-ai/issues) and the maintainer team will reconcile the doc. The point of publishing the doc in source is that the verification path runs through readable code, not through a vendor's representation of the code.

---

## 9. What an operator's evaluation can confirm in source

Because LQ.AI is open-source and self-hosted, an operator's evaluation does not terminate in a vendor's representation of the product. The list below is a sample of the verifications that are available in source today and are not available from a closed-source vendor at any price:

- **Read the inference gateway's routing logic** and confirm the operator's tier policy is enforced as documented: `gateway/app/router.py` plus `gateway/app/tier_floor.py`.
- **Read the audit logger** and confirm what is captured: `api/app/audit.py`. Every sensitive action — login, MFA setup, skill execution, tier override, account deletion — produces a structured event.
- **Read every built-in skill** and confirm what each skill instructs the model to do: `skills/*/SKILL.md` plus the supporting reference and example files. There are no hidden prompts.
- **Read the provider adapters** and confirm what is sent to each inference provider and how authentication is handled: `gateway/app/providers/{anthropic,openai,ollama}.py`.
- **Read the routing log writer** and confirm what is recorded per inference: `gateway/app/routing_log.py`.
- **Read the secrets layer** and confirm provider-key encryption at rest: `gateway/app/secrets.py` plus `docs/security/encrypted-keys.md`.
- **Read the threat model** and confirm the STRIDE analysis is current: `docs/security/threat-model.md`.
- **Run the test suite** and read the results: `cd web && npx vitest run`; `cd api && pytest`; `cd gateway && pytest`; `cd web && npx cypress run`.
- **Read the capabilities that are not yet wired** — the Citation Engine endpoint stub at `api/app/api/chats.py:1174-1212` and the Anonymization Layer 501 at `gateway/app/api/admin.py:270-282`. The verification path covers what is shipped and what is deferred symmetrically.

The verification budget is the operator's to set, on a timeline the operator chooses, with a scope the operator defines. None of those properties is true for closed-source attestation.

## 10. Maintenance note

This document is maintained per release. Items leave the deferred lists when they ship; items join when they are scoped. Last updated alongside Wave 9 of the M1 documentation push (2026-05-14).

The substantive content that drives this doc lives in:

- [PRD §3 Capability Specifications](PRD.md#3-capability-specifications) — what each capability is.
- [PRD §8 Roadmap](PRD.md#8-roadmap) — when each milestone lands.
- [PRD §9 Deferred Enhancements](PRD.md#9-deferred-enhancements-and-identified-future-work) — what is deferred and why.
- [`docs/compliance/`](compliance/) and [`docs/security/`](security/) — compliance and security artifacts.
- [`docs/contribute/EASIEST-CONTRIBUTIONS.md`](contribute/EASIEST-CONTRIBUTIONS.md) — the contributor-friendly path for items this doc surfaces as gaps.
