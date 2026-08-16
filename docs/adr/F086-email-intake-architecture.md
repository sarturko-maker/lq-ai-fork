# F086 — Email legal-intake: one agent run per thread, bridge-held mail credentials, candidate matters as projects

- Status: proposed (substance maintainer-ruled 2026-08-16 in the INTAKE plan review — decisions
  1–6 in `docs/fork/plans/INTAKE-INBOX-plan.md` § Maintainer decisions; formal flip on the
  maintainer's read of this ADR)
- Date: 2026-08-16
- Research: `docs/fork/plans/research/INTAKE-*.md` (5 reports, 2026-08-16)

## Context

In-house legal teams run a "front door" mailbox (legal-intake@…). The INTAKE milestone puts a
practice-area Deep Agent on that mailbox: every inbound email thread is read by an agent which
either handles it, pauses for human approval, or opens a candidate matter. Test rig = AgentMail
(dev ingress via its websocket — the dev box has no public endpoint); production email
(M365/Gmail) arrives later behind the same seam. Binding constraints: gateway-only LLM egress;
`guarded_tool_call` + brakes on every action; audit carries counts/types/IDs only; authz
owner-scoped with cross-user 404; email bodies and attachments are untrusted model input
(prompt injection); self-host-first (no third-party SaaS in the approval path); Svelte web
client; langgraph 1.x + deepagents embedded in-process (no LangGraph Server).

## Considered options

1. **Adopt the OSS Agent Inbox app + a LangGraph Server topology.** Rejected: the app is
   de-invested (last feature work Jan 2026; the inbox concept re-shipped as the paid LangSmith
   Fleet "Agent Inbox"), parses the legacy interrupt schema (its merged shim is inbound-only
   and partial), has no auth story, and requires the LangGraph Platform API surface we
   deliberately don't run. A survey of every credible alternative (agent-chat-ui,
   CopilotKit/AG-UI, assistant-ui, HumanLayer, gotoHuman, Portia, Permit.io, Inngest, the
   Svelte ecosystem) found nothing that beats a native surface —
   `docs/fork/plans/research/INTAKE-inbox-ui-alternatives.md`.
2. **A neutral "intake monitor" agent fronting all areas.** Rejected: it would have no
   Practice Playbook, skills or tools, so it must hand off to the area agent anyway (double
   cost), and it would mint a new org-tier module kind against the authoring boundary for
   zero capability gain.
3. **Deterministic two-stage triage** — a cheap schema-constrained classifier plus a fixed
   category taxonomy driving per-category action ladders in config. Rejected by the
   maintainer: classification cannot be deterministic, legal inboxes are messy, and a fixed
   taxonomy fits ~30% of one org — "if you have structured intake you don't need this."
4. **One deep-agent run per email thread on the admin-bound area agent** — chosen.

## Decision outcome

Option 4, concretely:

- **Binding.** An `intake_mailboxes` row binds one mailbox to one practice area (v1:
  Commercial) and one owner user, who owns every candidate matter and run and gives every
  approval (maintainer: "there is no Team who can own intake with agents").
- **One run per thread.** Every inbound email thread triggers ONE normal agent run — separate
  inference, separate context — on the bound area agent, composed by the existing composition
  root (Practice Playbook, skills, tools, HITL policy, tier floor). Budget = lean profile +
  low step cap: cost control is "run briefly", never "don't run" (per-thread inference cost
  explicitly accepted in exchange for judgment). Follow-up emails continue the SAME agent
  thread (conversation memory carries); each new inbound message = a new run on it. No new
  gateway purpose — these are ordinary `agent_loop` runs.
- **Structural outcome.** The run concludes via a `record_intake_outcome` tool call (closed
  outcome enum + free-text label + note — never prose): *dealt-with* (filed with a note,
  nothing external happens) / *paused for HITL* (run settles `awaiting_input`) / *candidate
  matter*. The project row is created EAGERLY at ingest — runs and files are project-scoped,
  that is substrate, not policy — and the outcome dismisses it or keeps it
  (`projects.intake_state`: `candidate` / `promoted` / `dismissed`; NULL = normal matter).
  Candidate matters are REAL projects: ingest, dedup, memory tiers, HITL and cockpit panels
  reuse wholesale; dealt-with outcomes auto-dismiss, so no clutter survives.
- **Doctrine, not config.** Intake behaviour lives in a transparent, admin-editable intake
  SKILL. The agent tags threads with free-form labels (`intake_threads.label`) — display and
  grouping only, nothing branches on them. An org-specific taxonomy EMERGES post-v1 via a
  propose→approve consolidation slice ("system proposes, user owns"; ADR-F050-shaped). The
  research taxonomy (`research/INTAKE-taxonomy-policy.md`) survives only as illustrative
  examples inside the doctrine.
- **The safety line is structural.** `draft_email_reply` — and every outbound tool — is
  interrupt-gated in `hitl_policy` unconditionally: the prompt-injection backstop is F071
  mechanics, not prompt language, and no category mechanism exists that could unlock
  auto-send. v1 sends NOTHING automatically, acknowledgements included (kills the mail-loop
  class). HITL decisions widen from approve/reject to +edit/+respond in ADR-F087 (amends
  F071).
- **mail-bridge = the sole holder of mailbox credentials** (the gateway key-holder pattern),
  a separate microservice mirroring slack-/teams-bridge: it verifies the provider's own
  signatures (Svix webhook, prod) or dials out (AgentMail websocket, dev — no tunnel needed),
  normalizes everything to a provider-agnostic InboundEmail envelope, and calls `api` behind
  `require_bridge_auth`. Approved outbound replies go api → bridge `/send`. Provider swap
  (M365 Graph, Gmail) = a new bridge; `api` unchanged and never holding mail credentials.
- **The inbox surface is native Svelte** on the F071 substrate — which already speaks the
  current deepagents `HITLRequest`/decisions schema. Ecosystem component taxonomy (Approval
  Card / Permission Grant / Reviewable Diff; decision-type-driven rendering) is adopted as
  design reference only, never as code.

## Consequences

- Positive: maximum substrate reuse (headless runs, ingest, matter memory, HITL, cockpit);
  the email provider is swappable at one seam; injection risk is bounded structurally; misfiled
  threads stay visible (every thread keeps its label + note in the Intake list — nothing
  disappears silently).
- Negative / accepted: per-thread inference cost (bounded by lean budget + step cap, tracked
  by existing token persistence; a cheap spam pre-filter may return later as a pure cost
  valve, maintainer's call); one new microservice; one migration; `ingest_bytes()` must be
  extracted from the HTTP upload route into a packaged service function.
- Mandated follow-ups: ADR-F087 (HITL decision widening); the emergent-taxonomy consolidation
  slice; Teams/Slack approval surface over the existing bridges (the dominant production
  approval pattern); M365/Gmail production bridge at the enterprise phase.
- Seam comments referencing this ADR belong at: the internal intake router + worker,
  `record_intake_outcome`, the bridge envelope contract, and the `projects.intake_state`
  lifecycle.
