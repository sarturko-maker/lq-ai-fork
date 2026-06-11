# North star — resident colleagues, forward-deployed

Direction, not a decision: this document records where LQ.AI is headed so structural slices can
be sanity-checked against it the way they are checked against accepted ADRs. Nothing here is
current scope. The obligation it creates is narrower and harder: **do not foreclose it.**
(Maintainer direction, 2026-06-11.)

## The end state

Today the practice-area Deep Agents are **embedded workers**: you open the app, you talk to
them, the conversation ends. The end state is **resident colleagues** — persistent agents in the
spirit of OpenClaw (identity, durable memory, proactive heartbeat; we won't use those words in
the product), each one:

- **an identity**: the practice area IS the agent — its profile, its bound skills, playbooks,
  MCP servers, tier floor (ADR-F002's `practice_areas` entity is the identity record);
- **a soul**: memory accumulating at company/client → practice area → user → unit of work,
  curated by humans ("system proposes, user owns" — ADR-0013 D4, F2's memory manager);
- **a heartbeat**: work triggered by schedules and events (a new contract lands in the
  repository, a DSAR opens in OneTrust), not only by a user typing;
- **reachable where the client lives**: Teams, Slack, email — the app is ONE surface, not the
  agent's home.

## The business shape

- **LQ.AI is the chassis: a community-maintained open repo** (the ADR-F001 rename + Apache-2.0
  path, unlocked by S6's shell shed and the provenance pass).
- **Revenue is forward deployment**: bespoke per-client implementations of that repo, where the
  agents are wired into the client's own infrastructure. The Commercial agent connects to the
  client's contract repository (eventually possibly shipping its own); the Privacy agent
  connects to TrustArc or OneTrust; every agent is contactable through the client's chosen
  channel. Bespoke means **configuration, not forks** — ADR-F004's declarative shapes are what
  make a client implementation a config exercise.

## The differentiator

OpenClaw's weakness is its trust model: a single-user personal agent on the operator's own
machine, with the security record that implies. Ours is the same ergonomics **with the trust
stack as the product**: every LLM call through the gateway, every action through
`guarded_tool_call` (R4/R5/R6), privilege tiers, audit rows, citations, receipts. Nobody
forward-deploys an unaudited autonomous agent into a privileged contracts repository — the
brakes are not overhead, they are why a legal client buys it.

## Keep-possible invariants

Standing rules (gateway-only egress, chokepoint, declarative config, transparency) already point
this way. Four gaps no current ADR answers — slices must not make them harder:

1. **System-initiated conversations.** Every `agent_threads` row today is born from a user POST
   and owned by a `user_id`. Heartbeat/event-triggered runs need an origin other than "user
   typed something" and an owner-identity answer — and triggered work still binds to a unit of
   work (ADR-F002's no-free-floating rule survives via auto-filing, not exemption). Don't bake
   "thread ⇔ interactive user request" into anything load-bearing.
2. **Inbound channel routing.** A Teams/Slack/email message addressed to an agent must resolve
   to (practice area, unit of work, thread). F1's auto-titling/auto-filing is the embryo of that
   resolver; the upstream Slack/Teams intake bridges are the substrate. Don't design intake
   surfaces that assume the web app is the only entry.
3. **Credential custody for client infrastructure.** Gateway-as-only-key-holder covers LLM
   providers. MCP/integration credentials (OneTrust keys, repository OAuth) need an equivalent
   custody decision — its own ADR when the first real connector lands. Until then: NO
   integration credentials ad hoc in `api/` config, ever.
4. **Deployment unit = one stack per client.** Forward deployment means a dedicated instance
   per client, which the current single-org model already fits. Do not "fix" the architecture
   toward SaaS multi-tenancy; that would trade the model we want for one we don't.

## What already lines up (for orientation, not celebration)

Practice areas as identity (ADR-F002, F1) · 4-level memory + memory manager (F2) · durable
conversation state on the checkpointer (ADR-F008) · per-area MCP servers (F3) · Slack/Teams
intake bridges + email entry points (upstream / Backlog) · autonomous watches + arq as the
heartbeat seam (M4 substrate) · "long tasks keep running when the laptop closes" (F3) ·
the rename/licensing path to a public repo (ADR-F001, S6).
