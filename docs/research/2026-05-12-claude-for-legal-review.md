# `claude-for-legal` — review for M1 incorporation analysis

> **Status:** Research-only deliverable per Kevin 2026-05-12. No code
> changes; sets the table for an incorporation decision in v1.1+ or a
> later M1 amendment.
>
> **Upstream:** [`anthropics/claude-for-legal`](https://github.com/anthropics/claude-for-legal) (main, surveyed 2026-05-12)
> **License:** Apache 2.0 (Copyright 2026 Anthropic PBC)
> **Branch this doc lives on:** `kk/main/Frontend_Design`

---

## 1. Summary

`claude-for-legal` is Anthropic's reference plugin marketplace for legal-practice AI agents. It ships **13 plugins** (12 practice-area plugins + 1 community-skill hub), totalling **~163 skills** (frontmatter-bearing `SKILL.md` files) plus **~10 scheduled "agent" markdown files** and **5 Managed-Agents-API "cookbooks"** under `managed-agent-cookbooks/`. The runtime targets are Claude Code, Claude Cowork (desktop), and the Anthropic Managed Agents API (`/v1/agents`) — invocation is via slash-command (`/<plugin>:<skill-name>`) or auto-trigger on the `description` field. The plugin model is filesystem-canonical, attorney-attested in spirit (the README is explicit that outputs are drafts for attorney review), and configured per practice via a `CLAUDE.md` "practice profile" populated by a `cold-start-interview` skill that every plugin ships.

The skill format is **deliberately thin**. Frontmatter is typically four fields (`name`, `description`, `argument-hint`, and an optional `user-invocable: false` for skills loaded by other skills); no jurisdiction tag, no severity rubric pointer, no input schema, no version. The substance lives in the body (often 1,000-3,000 lines) and in sibling references / playbooks. This is **the opposite of LQ.AI's `lq_ai:` namespaced schema** (per `docs/skill-authoring-guide.md`), where structured frontmatter is the contract surface and the body is operational prose. The bodies themselves, however, are highly portable — they are markdown describing workflow, reference materials, output structure, and refusal conditions, which is exactly LQ.AI's body convention.

The recommendation is **selective port, not bulk fold-in**. Roughly 25-35 of the 163 skills map cleanly onto LQ.AI's in-house-legal-team scope; the rest are either (a) infrastructure scaffolding that LQ.AI already solves differently (`cold-start-interview`, `customize`, `matter-workspace`), (b) audiences out of scope (law-student, legal-clinic), or (c) backed by Anthropic-hosted runtimes (Managed Agents API cookbooks) that LQ.AI does not yet have an equivalent of. The `legal-builder-hub` security-and-trust pattern (allowlist + raw-source display + heuristic scan + license gate + human approval) is **the most architecturally interesting artifact in the repo** for LQ.AI; it deserves a Wave of its own if/when LQ.AI exposes a community skill installer surface (DE-XXX candidate).

---

## 2. Repository overview

**License.** Apache License 2.0, Copyright 2026 Anthropic PBC. Compatible with LQ.AI's open-source posture. Per PRD §7.1 (skills as canonical artifact), incorporation requires upstream attribution; relicensing downstream is permitted under Apache 2.0 §4 but conflicts with LQ.AI's transparency-first commitment (skills are visible work product — derived works should preserve the upstream provenance).

**Maintenance.** First-party Anthropic. Active. README explicitly states "outputs are drafts for attorney review, not legal advice or conclusions … plugins are not Anthropic legal positions."

**Structure.** Top-level directories:

```
claude-for-legal/
├── .claude-plugin/marketplace.json     # 13-plugin marketplace manifest
├── ai-governance-legal/                # 10 skills + 1 plugin.json + CLAUDE.md
├── commercial-legal/                   # 12 skills + 3 agents + hooks
├── corporate-legal/                    # 13 skills + 1 agent + hooks
├── employment-legal/                   # 20 skills + 1 agent + hooks
├── ip-legal/                           # 12 skills + 1 agent + hooks
├── law-student/                        # 13 skills + hooks (academic audience)
├── legal-builder-hub/                  # 10 skills + 1 agent (community-skill marketplace)
├── legal-clinic/                       # 16 skills + hooks (academic-clinic audience)
├── litigation-legal/                   # 19 skills + 1 agent
├── privacy-legal/                      # 9 skills + hooks
├── product-legal/                      # 7 skills + 1 agent + hooks
├── regulatory-legal/                   # 9 skills + 1 agent + hooks
├── external_plugins/cocounsel-legal/   # 13th plugin — Thomson Reuters CoCounsel bridge
├── managed-agent-cookbooks/            # 5 cookbooks for Managed Agents API deployment
├── references/                         # Cross-plugin reference templates
└── scripts/                            # deploy-managed-agent.sh, validate.py, etc.
```

**Plugin shape.** Each first-party plugin contains:

- `.claude-plugin/plugin.json` — `{name, version, description, author}` (4 fields, ~10 lines).
- `CLAUDE.md` — practice profile (team playbook, escalation rules, house style); populated by `cold-start-interview`.
- `.mcp.json` — MCP connector configuration (Slack, Google Drive baseline; plus practice-specific connectors).
- `skills/<skill-name>/SKILL.md` — the operational skill files.
- `agents/<agent-name>.md` — scheduled-agent markdown files with `model:` and `tools:` frontmatter.
- `hooks/hooks.json` — pre/post hooks (mostly logging).

**Scale (from the git tree at HEAD on 2026-05-12).** 13 first-party plugins; 163 `SKILL.md` files; 10 `agents/*.md` files; 5 cookbooks; ~564 total tree entries. Skill bodies are large (the `commercial-legal/skills/nda-review/SKILL.md` body is ~2,800 lines, an order of magnitude larger than LQ.AI's M1 NDA-review skill body).

---

## 3. Per-plugin assessment

| # | Plugin | Focus | Skills | Standout skills | Fold-in | Effort | Rationale |
|---|---|---|---|---|---|---|---|
| 1 | `ai-governance-legal` | AI-system governance (AIA, vendor AI review, AI inventory, reg-gap analysis) | 10 | `aia-generation` (AI Impact Assessment intake → memo); `vendor-ai-review` (vendor AI system review); `policy-monitor` (AI-policy change tracking) | **HIGH** | MEDIUM | High strategic fit — LQ.AI has no AI-governance content; the EU AI Act / NIST AI RMF / Colorado AI Act maturity makes this a v1.1+ category with real demand. Bodies are portable; frontmatter is trivial to retrofit. |
| 2 | `commercial-legal` | Vendor agreements, NDAs, SaaS MSAs, renewals, escalation routing | 12 | `nda-review` (GREEN/YELLOW/RED triage); `saas-msa-review` (SaaS overlay on vendor playbook); `vendor-agreement-review`; `escalation-flagger` | **MEDIUM** | MEDIUM | LQ.AI's M1 already ships `nda-review`, `msa-review-saas`, `msa-review-commercial-purchase`. Anthropic's variants are calibrated differently (triage-first vs deep-review-first). Port `escalation-flagger` and `renewal-tracker`; treat the contract-review skills as **comparators** for our own calibration, not replacements. |
| 3 | `corporate-legal` | M&A, board governance, diligence | 13 | `tabular-review` (200-doc batch review); `diligence-issue-extraction` (VDR review); `closing-checklist`; `board-minutes` | **HIGH** | MEDIUM | `tabular-review` is a near-direct analog to LQ.AI's Tabular Review capability (PRD §3.X). Port `tabular-review` and `diligence-issue-extraction` carefully — they map to capabilities Kevin has flagged as M1-or-v1.1+ scope. M&A diligence is a meaningful in-house category. |
| 4 | `employment-legal` | Hiring, termination, investigations, leave, handbook updates | 20 | `internal-investigation` (privileged-log + memo workflow); `worker-classification`; `hiring-review`; `termination-review` | **HIGH** | HEAVY | Highest-skill-count plugin (20). `internal-investigation` is a substantial multi-stage workflow that has no LQ.AI analog and would be a flagship v1.1+ skill. Worker-classification and termination-review are high-frequency in-house tasks. Effort is HEAVY because employment law has jurisdiction-heavy calibration. |
| 5 | `ip-legal` | OSS review, patent FTO, trademark clearance, IP renewals | 12 | `oss-review` (license compliance / SBOM gating); `clearance` (trademark/copyright clearance); `ip-clause-review`; `fto-triage` (patent freedom-to-operate) | **HIGH** | MEDIUM | `oss-review` is directly aligned with LQ.AI's own supply-chain-transparency story (PRD §7.5). `ip-clause-review` complements LQ.AI's contract-review skills. Plus IP is a recurring in-house need not yet covered by LQ.AI's M1 starter bundle. |
| 6 | `law-student` | Case briefs, IRAC practice, bar prep, exam forecast | 13 | (all academic-audience) | **SKIP** | n/a | Audience mismatch. LQ.AI's M1 scope is in-house legal teams; law-student is for 1L–3L students. Skills are well-designed but out of scope. |
| 7 | `legal-builder-hub` | Community-skill marketplace, install/QA gates | 10 | `skill-installer` (raw-source display + allowlist + license + heuristic scan + human approval); `skills-qa` (Legal Skill Design Framework, 9 design parameters + 3 failure modes); `auto-updater` | **MEDIUM** | HEAVY | Architecturally important — see §6 below. Fold-in is a separate Wave (probably v1.1+, possibly an M1 amendment if Kevin opens a community-skills surface earlier than planned). Most relevant for LQ.AI is the trust-model and the QA framework, not the skill code itself. |
| 8 | `legal-clinic` | Pro bono / academic-clinic workflows (intake, deadlines, supervisor review queue) | 16 | (clinic-flow-specific) | **SKIP** (with one carve-out) | n/a | Audience mismatch: academic clinic operations. **Carve-out:** `plain-language-letters` and `client-letter` could be useful as audience-transformation skills for LQ.AI's `comms-improver` family. |
| 9 | `litigation-legal` | Litigation matter management, demand letters, privilege log, deposition prep | 19 | `privilege-log-review` (✅/❌/⚠️ triage with attorney-decision gates); `chronology`; `claim-chart`; `deposition-prep`; `legal-hold` | **MEDIUM** | MEDIUM | Litigation is **explicitly out of scope for v1** per LQ.AI's `docs/skill-authoring-guide.md` ("`litigation` (rarely; out of scope for v1)"). Defer the plugin. `privilege-log-review` and `legal-hold` are the two most likely v1.1+ pickups if Kevin opens litigation to in-house scope. |
| 10 | `privacy-legal` | DPA review, DSAR response, PIA generation, privacy-reg monitoring | 9 | `dpa-review` (regime-aware processor/controller routing); `dsar-response`; `pia-generation`; `reg-gap-analysis` | **HIGH** | MEDIUM | LQ.AI's M1 ships `dpa-checklist-review` and `vendor-privacy-policy-first-pass`. Anthropic's `dpa-review` is **direct overlap** but calibrated differently (auto-detects processor/controller); a useful comparator. `dsar-response` and `pia-generation` are clean additions with no LQ.AI duplication. |
| 11 | `product-legal` | Product-counsel work — launch review, feature risk, marketing claims | 7 | `marketing-claims-review` (claim-by-claim audit with revised copy out); `feature-risk-assessment`; `launch-review`; `is-this-a-problem` (triage skill) | **HIGH** | LIGHT | Small plugin, high-quality skills, clean audience match (in-house product counsel is a core LQ.AI persona). `marketing-claims-review` and `is-this-a-problem` are particularly portable. |
| 12 | `regulatory-legal` | Reg-change monitoring, policy diff, comment drafting | 9 | `policy-diff` (reg-change → indexed-policy gap analysis); `gap-surfacer`; `policy-redraft`; `reg-feed-watcher` | **MEDIUM** | MEDIUM | Useful but requires an indexed policy library (out of M1 scope per PRD §3). Port `policy-diff` as a v1.1+ skill once knowledge-management infrastructure (Wave D) lands. `reg-feed-watcher` requires the Managed Agents API equivalent. |
| 13 | `cocounsel-legal` (external) | Thomson Reuters CoCounsel bridge | n/a | (commercial third-party) | **SKIP** | n/a | Third-party-vendor-owned external plugin. Not Anthropic-maintained. Out of scope. |

**Summary of recommendations:** 5 HIGH (`ai-governance-legal`, `corporate-legal`, `employment-legal`, `ip-legal`, `privacy-legal`, `product-legal`); 3 MEDIUM (`commercial-legal`, `legal-builder-hub`, `regulatory-legal`); 1 LOW; 3 SKIP (`law-student`, `legal-clinic`, `cocounsel-legal`). Litigation is MEDIUM-but-deferred per LQ.AI's existing v1 scoping decision.

---

## 4. Format-compatibility analysis

### 4.1 Frontmatter shape — fundamentally different contracts

**Anthropic's `SKILL.md` frontmatter** (representative, from `commercial-legal/skills/nda-review/SKILL.md`):

```yaml
---
name: nda-review
description: >
  Reference: fast triage of inbound NDAs into GREEN / YELLOW / RED so the team only
  spends lawyer time on the ones that need it. Built for sales and BD to self-serve
  before pinging legal. Loaded by /commercial-legal:review when an NDA is detected.
user-invocable: false
---
```

Four fields, all string-or-bool: `name`, `description` (1024-char-soft-cap, doubles as auto-invocation trigger signal), `argument-hint` (user-facing param guidance, optional), `user-invocable` (true|false; false means the skill is loaded by other skills, not directly invoked). Agent files add `model:` and `tools:`. Cookbooks (managed-agent-cookbooks/) add `model:`, `system:`, `tools:` (with `type: agent_toolset_20260401`), `mcp_servers:`, `skills:`, `callable_agents:`.

**LQ.AI's `SKILL.md` frontmatter** (representative, from `skills/nda-review/SKILL.md`, abbreviated):

```yaml
---
name: nda-review
description: Use when the user uploads or pastes a non-disclosure agreement…
lq_ai:
  title: NDA Review
  version: 1.0.1
  author: LegalQuants
  tags: [contracts, nda, confidentiality, review]
  jurisdiction: US-default
  trigger_examples: ["…", "…", "…"]
  inputs:
    required:
      - name: document
        type: document
        description: …
      - name: perspective
        type: text
        description: …
    optional:
      - name: jurisdiction
        type: text
      - name: deal_type
        type: text
      - …
  output_format: markdown
  self_improvement: false
---
```

The `lq_ai:` namespaced block (per ADR 0007 §2 and `docs/skill-authoring-guide.md`) carries structured input declarations, semver, jurisdiction, output-format hints, and tags — the **contract surface that the gateway's prompt assembler and the backend's `SkillRegistry` enforce at request time** (per ADR 0004).

| Concept | Anthropic | LQ.AI | Compatibility |
|---|---|---|---|
| Skill ID | `name` | `name` | Direct |
| Trigger signal for auto-invocation | `description` (1024-char trigger blurb) | `description` + `lq_ai.trigger_examples[]` | Different surface; map `description` content to both LQ.AI fields |
| Input declarations | (none — described in body prose only) | `lq_ai.inputs.{required,optional}` (typed) | **Mismatch.** Anthropic skills declare inputs informally in body; LQ.AI's gateway enforces them at request time per ADR 0007 §2. Porting requires extracting input schema from body. |
| Jurisdiction | (in body) | `lq_ai.jurisdiction` (enum) | **Mismatch.** Extract during port. |
| Output format | (in body) | `lq_ai.output_format` (`report`/`table`/`issues_list`/`redline`) | **Mismatch.** Extract during port. |
| Version | (in `plugin.json` at plugin scope) | `lq_ai.version` (per-skill semver) | **Mismatch.** Granularity differs — Anthropic versions the plugin; LQ.AI versions each skill. |
| Author | (in `plugin.json`) | `lq_ai.author` (per-skill) | **Mismatch.** Same granularity issue. |
| Invocation model | Slash-command (`/<plugin>:<skill>`) + auto-trigger on description | Attach-via-UI + match-on-trigger (gateway-side per ADR 0007 §3) | **Mismatch.** See §7 question Q1. |
| Reference files | Loose convention — `references/`, sibling files | `reference/`, `examples/`, `scripts/` (per skill-authoring-guide) | Largely compatible; folder names differ |
| Multi-skill composition | `user-invocable: false` skills loaded by parent skills | Skill chaining via `lq_ai_skills: [string, …]` request body field (ADR 0007 §3) | **Different mechanism.** Anthropic skills compose at author-time (parent SKILL.md references child SKILL.md); LQ.AI composes at request-time (multiple skills attached to one chat). |

### 4.2 Body conventions — largely compatible

Both projects put the operational substance in markdown prose with section headings, reference-file pointers, and explicit "what this does not do" sections. The structural sections are very similar:

| Section | Anthropic convention | LQ.AI convention |
|---|---|---|
| Opening | Short purpose paragraph | Short purpose paragraph |
| When applies | "When this skill applies" + trigger phrases in body | "When this skill applies" |
| When NOT applies | Sometimes; varies | **Required** ("When this skill does NOT apply") |
| Inputs (prose) | Inline in workflow steps | Dedicated "Inputs" section |
| Workflow | Numbered or named steps; sometimes "passes" | Numbered "Passes" or "Steps" |
| Output structure | Explicit markdown template | Explicit markdown template (often "Bottom line" first) |
| Refusals / edge cases | Sometimes inline, sometimes a dedicated section | **Required** dedicated section |
| What this does not do | Often present | **Required** dedicated section |
| Reference pointers | Sibling `references/` files + `~/.claude/plugins/config/.../CLAUDE.md` | `reference/` subdirectory |

Both projects share the **"bottom line first" output convention**, the **severity-tagged findings convention** (though Anthropic uses GREEN/YELLOW/RED triage tiers while LQ.AI uses Critical/Material/Minor), and the **explicit refusal posture**. Body-level porting is largely a copy-and-restructure exercise, not a rewrite.

### 4.3 Runtime / dependency surface — incompatible without adapter work

Anthropic's skills depend on:

- A `~/.claude/plugins/config/claude-for-legal/<plugin>/CLAUDE.md` filesystem path for the practice profile. **LQ.AI has no analog at the M1 filesystem level** — closest is the (deferred) Organization Profile (per `docs/skill-authoring-guide.md`'s `is_organization_profile: true` singleton flag). To run an Anthropic skill on LQ.AI, the body's `~/.claude/plugins/config/...` references need to be rewritten to reference LQ.AI's Organization Profile skill.
- Slash-command invocation (`/commercial-legal:nda-review`) — LQ.AI uses attach-on-chat invocation per ADR 0007 §3. Skills with `user-invocable: false` that are loaded by parent skills via a `/commercial-legal:review` orchestrator need a different composition mechanism on LQ.AI (probably `lq_ai_skills:` request body, possibly with a wrapping orchestrator skill).
- MCP servers (`mcp__ironclad__*`, `mcp__*__slack_send_message`, etc.) — LQ.AI does not yet have first-class MCP-connector configuration at the skill level. Tool-using skills require translation from `tools:` frontmatter to LQ.AI's deferred tool-call surface (per ADR 0007 §3 "tool-use translation is not exercised").
- Managed Agents API (`/v1/agents`) for scheduled-agent cookbooks. **LQ.AI has no scheduled-agent runtime in M1.** Importing Anthropic's `renewal-watcher` or `docket-watcher` cookbooks is a Managed-Agents-equivalent capability question for LQ.AI, not a skill question — see §7 Q3.

### 4.4 Porting effort matrix

| Porting target | Effort | Notes |
|---|---|---|
| Body prose (markdown content) | **LIGHT** | Restructure section ordering; map GREEN/YELLOW/RED → Critical/Material/Minor where needed; preserve the substantive checklists verbatim with attribution. |
| Frontmatter schema rewrite | **MEDIUM** | Extract inputs, jurisdiction, output_format from body to `lq_ai:` block. Add `trigger_examples`. Per-skill versioning starts at 1.0.0. |
| Sibling `reference/` files | **LIGHT** | Anthropic puts references in plugin-scoped `references/` or sibling-of-skill `references/`; LQ.AI puts them in per-skill `reference/`. Move and adjust pointers. |
| `examples/` directory | **MEDIUM** | Anthropic does not have a consistent `examples/` convention. LQ.AI requires examples per `docs/skill-authoring-guide.md` §Worked examples. Authoring examples is the substantive lift. |
| Practice profile references | **MEDIUM** | Rewrite `~/.claude/plugins/config/.../CLAUDE.md` references to LQ.AI's Organization Profile mechanism (currently deferred — see PRD §3). |
| Tool-use translation | **HEAVY** | Anthropic's `tools:` and MCP-connector references require LQ.AI's tool-call infrastructure, which ADR 0007 explicitly defers. Tool-using skills are not portable until that infrastructure lands. |
| Scheduled-agent cookbooks | **HEAVY** | Requires a Managed-Agents-equivalent in LQ.AI (does not exist). Defer. |
| Practice-attorney attestation | **MEDIUM** | LQ.AI requires practicing-attorney attestation per `skills/CONTRIBUTING.md` and `CLAUDE.md`. Anthropic's skills do not. Each ported skill needs an attestation pass. |

---

## 5. Top fold-in candidates (10 skills)

Picked by: (a) maps to in-house legal teams; (b) no direct duplication with LQ.AI's 10 M1 starter skills; (c) reasonable porting effort; (d) high practical-value-per-port. Listed in rough priority order.

| # | Skill | Source plugin | Effort | Rationale |
|---|---|---|---|---|
| 1 | `tabular-review` | `corporate-legal` | MEDIUM | Direct analog to LQ.AI's Tabular Review capability (PRD §3.X). One row per document × one column per question with citations per cell. **Highest leverage** for the M&A diligence persona. |
| 2 | `marketing-claims-review` | `product-legal` | LIGHT | Six-claim-type taxonomy + claim-by-claim audit with revised copy out. Clean audience match (product counsel). No LQ.AI duplication. Body is portable; inputs are minimal. |
| 3 | `oss-review` | `ip-legal` | LIGHT-to-MEDIUM | Open-source license compliance against a dependency list / SBOM. Maps directly to LQ.AI's PRD §7.5 supply-chain-transparency commitment. Critical for engineering-org in-house teams. |
| 4 | `aia-generation` | `ai-governance-legal` | MEDIUM | AI Impact Assessment intake → memo workflow. AI Act / NIST AI RMF / Colorado AI Act maturity is making this a high-frequency in-house task. **No LQ.AI analog.** |
| 5 | `vendor-ai-review` | `ai-governance-legal` | MEDIUM | Vendor-AI-system review (data, risk, compliance posture). Complements LQ.AI's `vendor-privacy-policy-first-pass` cleanly. |
| 6 | `dsar-response` | `privacy-legal` | LIGHT | Data Subject Access Request response workflow. High in-house frequency for any team subject to GDPR / CCPA. No LQ.AI duplication. |
| 7 | `internal-investigation` | `employment-legal` | HEAVY | Multi-stage workflow (intake → log → memo) with privilege handling. Flagship candidate but substantial port — privilege rules are jurisdiction-heavy. Recommend M2, not M1. |
| 8 | `worker-classification` | `employment-legal` | MEDIUM | W-2 / 1099 / contractor classification — high in-house frequency, jurisdiction-aware. No LQ.AI analog. |
| 9 | `closing-checklist` | `corporate-legal` | LIGHT | M&A closing-checklist workflow. Useful for the M&A diligence persona. Pairs with `tabular-review`. |
| 10 | `policy-diff` | `regulatory-legal` | MEDIUM | Reg-change → indexed-policy gap analysis. Requires an indexed policy library (out of M1 scope); defer to post-Wave-D when knowledge-management infrastructure lands. |

**Honorable mentions (not ranked):** `escalation-flagger` (commercial-legal, light, useful as a chained skill), `feature-risk-assessment` (product-legal), `pia-generation` (privacy-legal), `legal-hold` (litigation-legal — only if Kevin opens litigation to in-house scope), `plain-language-letters` (legal-clinic, useful for audience-transformation), `ip-clause-review` (ip-legal, complements MSA-review).

**Not recommended for fold-in even though they exist as comparators:** Anthropic's `nda-review`, `saas-msa-review`, `dpa-review` — LQ.AI ships its own and the calibration differs. Treat as **comparators against which to validate LQ.AI's calibration**, not replacements.

---

## 6. `legal-builder-hub` pattern assessment

### 6.1 What it is

`legal-builder-hub` is Anthropic's reference implementation of a **community-skill marketplace** with a multi-gate trust pipeline. The 10 skills break into three groups:

- **Discovery:** `registry-browser`, `related-skills-surfacer`, `cold-start-interview` (recommend starter pack).
- **Lifecycle:** `skill-installer`, `auto-updater`, `disable`, `uninstall`, `skill-manager` (reference for the workflows).
- **Trust:** `skills-qa` (Legal Skill Design Framework evaluator), `customize` (post-install tuning).

The **install pipeline** in `skills/skill-installer/SKILL.md` enforces seven sequential gates before writing any files (per its README):

1. **Allowlist check** against `allowlist.yaml` (registries, publishers, MCP connectors). Permissive mode warns; restrictive mode refuses unlisted sources.
2. **License gate** — SPDX identifier extracted from skill metadata; restrictive mode refuses unrecognized or non-compliant licenses.
3. **Fetch in read-only context** — restrictive mode runs analysis in a subagent with no write access.
4. **Raw `SKILL.md` display** — full file shown to user (not summarized); flags injection patterns, external URLs, file-write scope violations.
5. **Structural trust check** — inspect hooks, MCP connectors (cross-check allowlist), tool permissions, network calls.
6. **`skills-qa` heuristic scan** — REFUSE verdict blocks install; non-lawyer users routed to attorney on MATERIAL CONCERNS+.
7. **Explicit human approval** — typed "yes" required; no install without fresh confirmation.

Followed by an 8th step: **freshness validation** — installed skill gets a freshness-gate preamble injected; install is logged to `install-log.yaml`.

The `skills-qa` skill itself is a **Legal Skill Design Framework** evaluator covering 9 design parameters (audience fit, work-shape consistency, delegation thresholds, input handling, versioning, confidence calibration, failure-mode identification, scope boundaries, escalation triggers), 3 trust-surface checks (prompt-injection heuristics, permission auditing, authority-claim detection), 3 legal-specific failure modes (advice vs. support, privilege handling, attorney-decision-making preservation), and a 4-band verdict (Ready / Some Concern / Material Concerns / Refuse).

### 6.2 Relevance to LQ.AI

The trust-check model is **directly relevant** to LQ.AI's posture. LQ.AI's `docs/PRD.md §7.1` makes skills the canonical artifact of value, and §7.5 commits to supply-chain transparency for the platform's own dependencies. A community-skill installer with first-class trust gates is a natural extension — and LQ.AI's existing skill-authoring pipeline (claim → draft → **attest** → review → merge per `skills/CONTRIBUTING.md`) is already half of the answer. Anthropic's pipeline is the **runtime** half (what happens when an end user installs a skill from a registry); LQ.AI's pipeline is the **authoring** half (what happens before the skill enters the registry). Both halves are needed; they don't overlap.

### 6.3 Specific fold-in concerns and adaptations

| Anthropic gate | LQ.AI fit | Adaptation |
|---|---|---|
| Allowlist (`allowlist.yaml`) | High fit | LQ.AI's gateway is the natural enforcement point. Extend `gateway.yaml` (already hot-reloadable per ADR 0010) with `skill_sources:` allowlist. |
| Raw `SKILL.md` display | **Direct fit, transparency-aligned** | Per PRD §1.3, transparency is the founding principle. Raw skill display before install matches LQ.AI's posture exactly. UI surface lives in `web/`. |
| License gate (SPDX) | High fit | LQ.AI's PRD §7.5 already references SBOM. Extending to skill licenses is a small lift. |
| Heuristic injection scan | Medium fit | LQ.AI does not currently scan skills at install. Worth considering; but a skill that an attorney has attested and a reviewer has approved is already a higher trust tier than a community-registry skill. Two-tier model (attested-and-reviewed vs. registry-installed) is the right shape. |
| Human approval | Direct fit | Already implicit in LQ.AI's review process; needs an end-user-facing analog for installer flow. |
| `skills-qa` framework | **High fit, partially redundant** | LQ.AI's `docs/skill-authoring-guide.md` already encodes most of these checks at authoring time. Anthropic's contribution is the **runtime evaluator** that runs the checks programmatically. Worth adopting the evaluator pattern; the substantive checks may be duplicated. |
| Freshness validation | Medium fit | LQ.AI does not currently track skill freshness as a first-class concept. Relevant for KB-grounded skills (per `reference_openloris_repo.md` "Good Until Date" pattern); add to the v1.1+ knowledge-management Wave. |

### 6.4 Effort and sequencing

**Effort to port the discovery+install pattern: MEDIUM-to-HEAVY.** The conceptual lift is medium (the gates are well-defined); the integration with LQ.AI's existing skill registry (ADR 0004), gateway prompt assembly (ADR 0007), and DB-backed user-skill model (ADR 0012) is heavy. The pattern intersects three ADRs and a forthcoming knowledge-management Wave.

**Sequencing recommendation: dedicated Wave, not a fold-in to Wave D/F.** A community-skill installer is a substantial product surface that crosses backend/gateway/frontend boundaries. Folding it into an existing Wave dilutes both. The cleaner shape is:

- **M1 deliverable status:** Defer. M1 should ship with the 10 starter skills filesystem-canonical and the DB-backed user-skill model from ADR 0012; community installation is a v1.1+ Wave.
- **As a v1.1+ Wave (probably named "Wave G — Community skills"):** Allowlist + raw-display + license gate + skills-qa evaluator + install log. Skips the heuristic injection scan in v1.1 (defer to v1.2) — the attested-and-reviewed tier is the trust ceiling for v1.1.
- **DE-XXX candidate:** "Community-skill installer with trust gates (per `claude-for-legal/legal-builder-hub` reference pattern)." File in PRD §9.

---

## 7. Architectural questions for Kevin

These are decisions Kevin needs to make before any port lands. Each is a "stop and ask" per `CLAUDE.md` decision routing.

**Q1. Invocation model — slash-command vs. attach-on-chat.** Anthropic's skills are invoked via slash-command (`/<plugin>:<skill-name>`) or auto-triggered on the `description` field. LQ.AI's M1 uses attach-on-chat with match-on-trigger via `lq_ai.trigger_examples[]` (per ADR 0007 §3). Should LQ.AI support **both** invocation models, or commit fully to attach-on-chat? Slash-command syntax has a UX advantage for power users; attach-on-chat is cleaner for the "skill as work product" framing. **Recommendation:** stay with attach-on-chat for M1; revisit if multiple users request slash-command surface.

**Q2. Per-skill versioning vs. per-plugin versioning.** Anthropic versions at the plugin level (`plugin.json`'s `version`); LQ.AI versions at the skill level (`lq_ai.version`). Per-skill is more granular and aligns with `docs/skill-authoring-guide.md`'s semver discipline. Should LQ.AI adopt any plugin-grouping concept (a "starter bundle" version) alongside per-skill semver, or stay flat? **Recommendation:** stay flat for M1; the "starter bundle" concept can live in the DB-backed user-skill model from ADR 0012 if needed later.

**Q3. Managed-Agents-equivalent / scheduled agents in M1?** Anthropic's `managed-agent-cookbooks/` deploy headless agents to `/v1/agents`; the cookbook shape is `agent.yaml` + `subagents/*.yaml` + `steering-examples.json`. **LQ.AI has no scheduled-agent runtime.** Several plugins (renewal-watcher, docket-watcher, reg-feed-watcher, dataroom-watcher, launch-watcher) presuppose this runtime. Should LQ.AI scope a Managed-Agents-equivalent into M1 (probably no — out of scope), v1.1+ (likely yes — high in-house demand), or defer indefinitely (unlikely — too high-value)? **Recommendation:** out of scope for M1; file as v1.1+ candidate. Frame: "LQ.AI's gateway already routes inference; a scheduled-agent surface is a cron + recurrence + handoff layer on top of that. Reference design exists in `managed-agent-cookbooks/`."

**Q4. Verbatim port + attribution vs. LegalQuants-authored variant.** Apache 2.0 §4 permits both. Verbatim-with-attribution gets us the bodies cheaply; LegalQuants-authored gets us calibrated-for-our-customer-base substance and matches the **practicing-attorney-attestation** requirement at `skills/CONTRIBUTING.md`. Anthropic's bodies are large (often 2,000+ lines) and would be expensive to re-author from scratch. **Recommendation:** verbatim-with-attribution as the **starting commit**, then iterate via the normal LQ.AI skill-authoring pipeline (claim → draft → **attest** → review → merge) where the attestation paragraph reflects "Reviewed and adapted the upstream `<path>` from `anthropics/claude-for-legal` at commit `<sha>`." Practicing-attorney attestation per LQ.AI's process is binding regardless of upstream provenance.

**Q5. `CLAUDE.md` practice-profile equivalent.** Anthropic's skills heavily reference `~/.claude/plugins/config/claude-for-legal/<plugin>/CLAUDE.md` as the team-specific playbook (GREEN/YELLOW/RED thresholds, escalation rules, house style). LQ.AI's nearest analog is the deferred **Organization Profile** singleton skill. Should the Organization Profile move from "deferred enhancement" to M1 scope to support fold-in of contract-review skills like `nda-review` (which is fundamentally a playbook-driven triage)? **Recommendation:** move Organization Profile authoring into v1.1+, not M1; in the meantime, ported skills get a "house-style not yet configured; using sensible defaults" path consistent with the input-default convention in `docs/skill-authoring-guide.md`.

**Q6. `legal-builder-hub`-style community installer — M1, v1.1+, or v2?** Per §6 above. **Recommendation:** v1.1+ as its own Wave (provisionally "Wave G"). File as DE-XXX candidate in PRD §9.

**Q7. License posture — Apache 2.0 NOTICE handling.** Apache 2.0 §4(c) requires a NOTICE file when one is provided upstream. Anthropic's repo does not appear to ship a NOTICE file (license has placeholder copyright text only), but the practice is to preserve attribution in the ported files' frontmatter or in a top-level `NOTICES.md`. **Recommendation:** add a `NOTICES.md` at repo root tracking upstream provenance per ported file. The skill's frontmatter `lq_ai.author` should reflect "Anthropic PBC (upstream) and LegalQuants (adaptation)" for ported skills, in line with the author-pair convention.

**Q8. Tool-use / MCP-connector parity.** Several Anthropic skills declare `tools:` and reference MCP servers (Ironclad, DocuSign, iManage, etc.). LQ.AI's gateway defers tool-use translation per ADR 0007 §"What this ADR does not commit to." Ported skills that depend on these connectors are not runnable on LQ.AI until tool-use lands. Should the tool-use deferral be revisited as part of fold-in scoping, or do we accept that tool-using skills stay on the bench until the broader tool-call infrastructure ships? **Recommendation:** accept the deferral; fold-in scope is **non-tool-using skills only** for M1 / v1.1+; tool-using skills are pinned to the deferral list and unblocked alongside the broader tool-call ADR work.

---

## 8. Recommendation

**Fold in selectively, on a v1.1+ schedule, with M1 deferred.** Specifically:

1. **M1 (no upstream incorporation):** Ship the 10 starter skills as-is. Do not fold in upstream skills before M1 close. The M1 starter bundle is already a coherent product; mixing in Anthropic-authored bodies before the LQ.AI skill-authoring pipeline has shipped its first end-to-end review cycle muddies the attestation surface.

2. **v1.1+ Wave (skill expansion, ~10 ported skills):** Target the §5 top-10 list, prioritizing `tabular-review` and `marketing-claims-review` (LIGHT effort, no infrastructure dependencies) and `oss-review` (LIGHT effort, supply-chain story alignment). Then `aia-generation`, `vendor-ai-review`, `dsar-response`. The two HEAVY-effort skills (`internal-investigation`, `worker-classification`) move to v1.2+.

3. **v1.1+ Wave G (community-skill installer):** Adapt the `legal-builder-hub` pattern to LQ.AI's architecture (allowlist via `gateway.yaml`; raw-display in `web/`; license gate; `skills-qa`-style evaluator). Skips the heuristic injection scan (defer to v1.2).

4. **v2+ (Managed-Agents-equivalent):** Reference Anthropic's `managed-agent-cookbooks/` design for scope-shaping. A scheduled-agent surface in LQ.AI is a multi-Wave investment, not a fold-in.

5. **Skip permanently:** `law-student`, `legal-clinic` (audience mismatch — except the `plain-language-letters` carve-out), `cocounsel-legal` (third-party).

6. **Action items immediately following Kevin's review of this doc:**
   - Decide on Q4 (verbatim vs. authored) — sets the contribution-pipeline shape for the v1.1+ Wave.
   - Decide on Q5 (Organization Profile scoping) — gates calibration-driven skills.
   - File DE-XXX entries for Q3 (Managed-Agents-equivalent) and Q6 (community installer) in PRD §9.
   - File a CONTRIBUTING.md adjustment item: ported-skill attestation paragraph template that handles upstream provenance.

The strongest argument for delay (versus aggressive fold-in) is that LQ.AI's skill-authoring pipeline is itself the artifact of value (PRD §7.1). Folding in 10-20 upstream-authored skills before the pipeline has shipped its first end-to-end attested cycle would invert the dependency. The fold-in is a faster path to skill-library breadth; the pipeline is the moat. Ship the pipeline first; expand the library second.

---

*Research conducted 2026-05-12 against `anthropics/claude-for-legal` main branch. Skill counts and structure verified via the GitHub git-trees API (`/repos/anthropics/claude-for-legal/git/trees/main?recursive=1`, 564 entries, not truncated). Skill bodies sampled across all 13 first-party plugins.*
