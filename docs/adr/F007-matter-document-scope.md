# F007 — Matter document scope for agent tools: attach join ∪ upload-time column

Status: proposed
Date: 2026-06-10

## Context

Upstream has TWO file↔project relationships, created by different affordances and read by
different surfaces:

1. **`project_files` join rows** — created by `POST /projects/{id}/files` (attach). The Projects
   API's `attached_file_ids` — what the Matter page shows — reads ONLY this.
2. **`files.project_id` column** — set by `POST /files` when the upload carries a `project_id`
   form field. No join row is created. No FK constraint. Nothing upstream reads it back for
   scoping.

F0-S4's matter document tools (`search_documents`/`read_document`) define, for the first time,
what "the matter's documents" means to an AGENT. Live verification caught the divergence: a file
uploaded into a matter (column set, no join row) was invisible to a join-only tool query — the
agent honestly reported an empty matter that the user had just put a document into. This decision
is security-relevant (it scopes agent document access) and will shape F1's file UX.

## Considered options

1. **Join-only.** Matches the Matter page exactly — but uploads into a matter (the primary upload
   affordance) are invisible to the agent. The user's mental model ("I put the file on the
   matter") breaks at the agent boundary.
2. **Column-only.** Matches uploads but drops every explicitly attached file; the attach endpoint
   is the deliberate, documented affordance. Worse on every axis.
3. **Union of both (chosen).** Every document the user put on the matter — through either
   affordance — is the matter's. Owner re-assertion + `deleted_at IS NULL` still gate every row
   through BOTH paths (a foreign-owned file joined or column-spoofed into a matter stays
   invisible; attack-tested).
4. **Unify the storage first** (backfill join rows from columns, make upload create joins, drop
   the column). The right end state, but an upstream-schema surgery slice of its own — wrong to
   couple to the first agent-tools slice.

## Decision outcome

Option 3 for F0: `api/app/agents/tools.py` scopes matter documents as
`project_files(pid) ∪ files.project_id = pid`, always intersected with
`files.owner_id = run.user_id AND deleted_at IS NULL`.

Consequence to resolve by F1 (tracked in MILESTONES § Backlog): the Matter page lists only the
join, so an agent can ground on a document the Matter page does not display. F1's file UX must
either render the union too, or land option 4's unification — at which point this ADR is
superseded.

## Consequences

- (+) The agent sees exactly what the user put on the matter; no silent scope gaps by affordance.
- (+) Scoping is defined in ONE place (`_matter_files_query` / `_FTS_SQL`) with the security
  predicates inseparable from membership.
- (−) Agent-visible scope ⊃ Matter-page-visible scope until F1 reconciles the surfaces.
- (−) `files.project_id` has no FK; a stale column value could bind a file to a deleted project id
  — harmless today (no project row ⇒ no run can bind to it) but one more reason for option 4.
