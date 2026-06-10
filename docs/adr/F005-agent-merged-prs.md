# F005 — Agent-merged PRs under strengthened verification gates

Status: accepted (2026-06-10, maintainer directive in session)
Date: 2026-06-10

## Context and problem statement

The fork is fully agentically coded: the maintainer directs product and design decisions but does not
review code. PRs blocking on human code review would stall every slice; merging unreviewed code with
only standard CI (lint + types + unit/integration) would let defects compound invisibly. We must
decide who merges, and what replaces human code review as the quality control.

## Considered options

1. **Human merges everything.** Blocks each slice on a reviewer who, by explicit design, will not
   read the diff. Rubber-stamping with extra steps.
2. **Agent merges on standard CI.** Too weak: CI here exercises no behavioral, security, or
   adversarial scrutiny of new code.
3. **Agent merges when a strengthened, evidence-producing gate passes.**

## Decision outcome

Option 3. The merge gate — all five parts, every PR, no exceptions:

1. **CI green** on the final head.
2. **Full containerized suites** for every touched service (api / gateway / web), run against a
   throwaway database, with pass counts quoted in the PR.
3. **Independent adversarial review** by a fresh-context agent that sees only the diff and the
   stated plan (correctness and security, not style). Blockers and should-fixes are fixed before
   merge, or explicitly deferred with the reason recorded in the PR and a HANDOFF/MILESTONES entry.
4. **Live verification** whenever behavior changes: provider-marked tests against the running stack
   for agent/LLM paths (never mocking the model, per ADR-F004), a rendered screenshot for UI
   changes — evidence quoted in the PR description.
5. **HANDOFF.md updated** — a slice is not done without its pickup document (CLAUDE.md §Session
   handoff).

The merging agent squash-merges once the gate passes. Changes touching security-sensitive paths
(gateway, auth, audit logging, crypto, anonymization) additionally get a security-focused review
pass before merge. The maintainer may revert any merge retroactively — cheap reverts are the point
of the evidence trail.

## Consequences

- Velocity is preserved without silent quality decay; every merge carries its own evidence.
- Each slice pays a token/time overhead (adversarial review + containerized suites + live runs) —
  accepted deliberately; it already paid for itself in F0-S1 (a misreported anonymization control
  and a provider-breaking content bug were caught pre-merge).
- The gate is summarized in CLAUDE.md §Merge policy; this ADR is the authority when they diverge.
