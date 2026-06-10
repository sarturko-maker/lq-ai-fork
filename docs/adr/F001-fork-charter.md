# F001 — Fork charter: pivot from tool surfaces to practice-area Deep Agents

Status: accepted (2026-06-10, maintainer agreement in session)
Date: 2026-06-10

## Context and problem statement

Upstream LQ.AI (LegalQuants/lq-ai, baseline `f91149a`, post-v0.4.0) organises the product around tool
surfaces: 11 flat tabs (Skills, Playbooks, Tabular Review, Matters, …) where the user picks the tool and
attaches it to a chat. Its three "agentic" executors (playbooks, tabular, autonomous) are linear LangGraph
pipelines — Python decides every transition and tool call; the model fills JSON slots; no model-driven
tool call exists anywhere in the codebase (the Anthropic gateway adapter ships text-only and drops
`tools`). We believe the right unit of organisation for an in-house lawyer is the **unit of work** within
a **practice area**, served by a genuine agent — not a menu of tools. This is a structural inversion of
the upstream UX and orchestration layer, while the substrate (gateway security boundary, brakes, audit,
citation engine, SKILL.md format) remains sound and worth keeping.

We must decide how to relate to upstream while making that inversion.

## Considered options

1. **Contribute the pivot upstream.** Rejected: the inversion contradicts upstream's shipped product
   thesis and roadmap (M5–M7 stays tool/workflow-centric); a PR of this scope would not land.
2. **Friendly fork tracking upstream** (regular merges from upstream tags). Rejected: the orchestration
   layer, frontend IA, and schema diverge structurally from day one; recurring merges would mostly
   conflict in code we are replacing. Pretending to track upstream while diverging structurally is the
   documented fork failure mode.
3. **Hard fork, upstream frozen.** Cut loose from upstream `main` entirely. No merges and no
   cherry-picks from upstream, and no proposals/PRs to upstream, without the maintainer's explicit
   per-case approval — upstream is not ours, and we show our own progress first before any upstream
   interaction. If approval is given for a specific sync, log it in `UPSTREAM.md`.

## Decision outcome

Option 3 — hard fork, upstream frozen pending explicit maintainer approval per interaction.

The fork pivots to: one LangChain `deepagents` Deep Agent per configurable practice area; a configurable
unit of work per area that loads tools/skills/playbooks/MCPs; 4-level memory (company/client profile →
practice area → user → unit of work); agent-driven tool and skill selection through the existing
`guarded_tool_call` brake chokepoint; a Claude-Code-like visible-work UX.

Kept unchanged from upstream: the Inference Gateway as sole egress and key-holder; R4/R5/R6 brakes and
the single-chokepoint pattern; the audit/receipt privacy contract; the Citation Engine; the SKILL.md
format and three-tier skill loading; the docker-compose deployment shape; ADRs 0001–0013 as historical
record (superseded individually as the pivot lands, never deleted).

## Consequences

- Good: freedom to replace the orchestration layer, frontend IA, and schema without merge debt;
  upstream's battle-tested substrate is retained; divergence is explicit and auditable.
- Bad: we forgo upstream feature and fix flow entirely while the freeze holds — including security
  fixes in kept components, which must be watched for and raised to the maintainer for a decision.
- Obligations: Apache-2.0 LICENSE and NOTICES.md retained and extended (never edited); OpenWebUI
  branding clause (`web/LICENSE` §4) honoured for >50-user deployments; PyMuPDF stays server-side-only
  (AGPL boundary). The project should be renamed before any public release to respect upstream's
  identity; revisit at the first public milestone.
- The langgraph `<0.3` pin must be lifted (langgraph 1.x + langchain + checkpointer/BaseStore) as an
  explicit early phase; the three legacy executors are frozen (bugfix only) until replaced.
