# F004 — Logic adopted from oscar-gc (and what we deliberately do not adopt)

Status: accepted (2026-06-10, maintainer agreement in session)
Date: 2026-06-10

## Context and problem statement

oscar-gc (`sarturko-maker/oscar-gc`) is the maintainer's own prior project: a single-user desktop
distribution of Block's Goose with the same product thesis — practice areas → primary unit
(Matter/Programme) → bound session, scoped memory, agent capabilities assembled per area — proven
through 35 sprints of dogfooding. A code-canonical review (2026-06-10, six agents + adversarial
fact-check against SPRINT_LOG.md) identified which of its patterns actually worked, which failed or
never shipped, and which must not transfer to a multi-tenant SaaS. oscar-authored code is
AGPL-3.0-or-later; this fork is Apache-2.0 — we adopt **logic only, never code**.

## Considered options

1. Ignore oscar-gc (clean-room the fork). 2. Port its implementation. 3. Adopt verified logic
patterns and inherit its failures as rules, rejecting what its own history refuted.

## Decision outcome

Option 3. Adopted logic (verified working in oscar-gc):

- **Declarative practice-area shapes**: each area's vocabulary (subject type, counterparty role
  enums, area-specific kind options, conditional extras, privileged defaults) is data consumed by
  one renderer — no per-area code branches. Shapes our `practice_areas` schema (ADR-F002).
- **A/B/C tool-parameter classification**: every LLM-visible parameter is A (model extracts),
  B (runtime-injects — never in the LLM schema: matter id, user id, scope), or C (tight enum).
  B-class from day one; oscar shipped an A-class "stopgap" that never migrated in 35 sprints.
- **Render-deterministic UI**: user-visible state (capability rail, digests, review grids) derives
  from settled state records, never from parsing LLM turns.
- **Resume-on-existing conversation binding** (check-before-create), with capabilities rebound per
  run — oscar's resumed sessions silently kept stale capability sets.
- **Task-scoped fan-out**: subagent dispatch as explicit procedures ("for each document, spawn an
  extractor with this schema"), parent as single writer of merged state — open-ended "delegate when
  useful" failed on MiniMax across four sprints; the task-scoped procedure worked first try.
- **Zero-LLM grounding gate** (char-overlap + section-exists + boilerplate filter) as a
  deterministic pre-stage before any LLM citation judge.
- **Doctrine-as-measurement**: behavior-shaping prompt changes are measured at N≥20 across ≥2 model
  families (masked judge, pre-flight variance gate) before merge; positive imperatives over
  negation lists (the same doctrine scored +35pp on MiniMax and −20pp on Haiku); doctrine placement
  matters — identity/rules before the surfaces they reference; late-flow guidance at the tool surface.
- **Process**: Phase-0 schema probe before architecting on any external tool/MCP; persona dogfood
  (real user, real provider, real build) as a release gate; inverting upstream UX defaults as
  explicit per-decision doctrine.

Inherited lessons-as-rules (from oscar's recorded failures):

- Memory isolation is **runtime-verified**, not design-verified: "fact told in Matter A must not
  surface in Matter B" is an executable F2 acceptance test (oscar deferred this gate and never
  closed it; its headline scoped-memory MCP was never wired into any recipe).
- User-added practice areas must support unit-of-work creation from day one (oscar's user-added
  areas could not host matters — configurability was aspirational).
- F0 acceptance includes measured tool-call + subagent uptake on MiniMax-M3 plus one second family.

Not adopted: **oscar's trust model.** Recipe-time construction (filesystem allowed-directories,
matter folders as the database, working-dir-keyed isolation) suits a single-user desktop binary and
still failed open once there (stale config left shell-write enabled until a build-time hard
exclusion). In this multi-tenant fork, capability composition follows oscar's logic, but enforcement
stays in the gateway + `guarded_tool_call` + Postgres/authz/audit stack (ADR-F001 KEEP list). Also
not adopted: folder-as-database persistence, A-class scoping, oscar's calibrated doctrine texts
(measure our own), and 1:1 matter↔session binding (we run many chats per Matter under ADR-F003).

## Consequences

- ADR-F002/F003 implementation tickets inherit concrete acceptance criteria (MILESTONES.md F0–F2).
- An eval substrate (N≥20, multi-family, masked judge) becomes F0 scope rather than nice-to-have.
- We re-measure all doctrine on our stack; nothing from oscar's prompt corpus is assumed portable.
