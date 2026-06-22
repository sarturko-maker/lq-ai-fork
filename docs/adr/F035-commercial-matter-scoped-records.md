# F035 — Commercial domain records are matter-scoped

- Status: accepted (2026-06-22, with slice C4 — the first Commercial domain records)
- Date: 2026-06-22
- Relates: ADR-F019 (deployment-global ROPA inventory — the rule this *diverges* from),
  ADR-F031 (the Adeu redline tool — the first records under this rule), ADR-F002 (the practice area
  is the agent identity), ADR-F004 (matter binding re-validated at run time)
- Milestone: COMMERCIAL — gate for any structured Commercial record (C4/C5/C7)

## Context

The Privacy area's records (the ROPA register, assessments) are **deployment-global** (ADR-F019): LQ.AI is
single-tenant, the in-house team's one client is its own organisation, and the register is the company's
standing Article 30 record — so the ROPA tools deliberately do **not** filter by `project_id`; the matter
only governs *whether* the tools exist, and the run's matter is stamped on rows as `source_project_id`
**provenance**, never as a scoping filter.

Commercial is the opposite. A deal's documents, redlines, and (later) extracted counterparty positions
belong to **that deal** and must not leak across deals — two matters for the same operator are different
counterparties, different NDAs, different privilege boundaries. A Commercial agent run bound to matter A must
never read or write matter B's documents or work product. This is a **security boundary** (cross-deal
leakage / privilege breach), not a stylistic choice, and it must be stated explicitly because it *contradicts*
the ADR-F019 rule a reader might otherwise assume applies to all area tools.

## Considered Options

- **A. Matter-scoped: every Commercial record is filtered by `binding.project_id` + `binding.user_id`
  (chosen).** Reads resolve only within the bound matter; writes land in the bound matter; a cross-matter or
  cross-user reference is the same 404-conflated absence the rest of the app uses (no existence leak). The
  matter binding is already re-validated at run time against owner + `archived_at` (ADR-F004), so the scope is
  trustworthy at dispatch.
- **B. Deployment-global like ROPA (rejected).** Correct for a company-wide *register*; wrong for *deal* work
  product — it would let one deal's agent read another deal's contract and redlines. A privilege/confidence
  breach by construction.
- **C. A new per-matter tenancy column on shared tables (rejected as premature).** Commercial work product is
  already keyed to a matter through the existing `files.project_id` / `project_files` membership and the
  matter binding; a separate tenancy mechanism adds schema for no capability the binding scope lacks.

## Decision Outcome

Adopt **A**. Commercial domain tools fetch source documents and write work product **only within the bound
matter** (`binding.project_id`) and **owner** (`binding.user_id`), reusing the matter-membership query that
already backs the document tools (the `project_files` join OR `files.project_id`, with the owner
re-assertion). A record outside the bound matter is invisible — resolved as 404-conflated absence, never 403
(no existence leak; CLAUDE.md). The redlined `.docx` C4 produces is written back into the *same* matter as a
new `File` (owner + `project_id` set). This **diverges from ADR-F019 by design**: deployment-global is the
ROPA-register rule; matter-scoped is the Commercial-work-product rule. Audit rows carry counts/types/IDs only
(the source/output file IDs, edit counts) — never clause text.

## Consequences

- **C4** is the first record under this rule: `apply_redline` fetches the source `.docx` via the matter-scoped
  file query and writes the redline back into the matter; a cross-matter/cross-user `document_name` simply
  resolves to "no such document in this matter".
- **C5** (counterparty-position extraction) re-asserts **both** `binding.user_id` **and**
  `binding.project_id` (+ `deleted_at IS NULL`) on every read — no cross-user *and* no cross-matter document
  read. **C7** (redline download) is owner+matter-scoped (404 cross-user) — it reuses the existing
  `GET /files/{id}/content` owner gate, which already returns 404 for another user's file.
- A future multi-tenant deployment inherits the boundary for free (the scope is owner+matter, not a global
  table), unlike the ROPA register which would need a tenancy column at that point.
- The divergence is now on record: a reviewer seeing a Commercial tool filter by `project_id` (unlike the
  ROPA tools) is seeing the intended rule, not a bug.
