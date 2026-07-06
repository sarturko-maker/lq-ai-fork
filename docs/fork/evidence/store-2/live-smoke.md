# STORE-2 gate evidence — Store + Library admin pages (ADR-F065)

Lead-run ADR-F005 gate on PR #226 (`fork/store-2-store-library-pages`), 2026-07-06.
All live verification ran on an ISOLATED fresh-org stack (throwaway pgvector + redis +
api-dev on `127.0.0.1:18058`, worktree code mounted, vite dev server on `:5173`) — the
dev stack and its walkthrough data were never touched.

## Deterministic gate

- CI green on the final head (`610ae79d`): API (ruff+mypy+pytest) 17m47s, Gateway, Web —
  run 28808787159.
- Full api suite, containerized, ALONE, worktree-root mount: **3369 passed, 42 skipped**
  in 15:12 (baseline 3347/42 + the slice's 22 new tests; zero failures).
- Web: svelte-check **0 errors**; vitest **106 files / 1169 passed**.
- Adversarial review (4 lenses — correctness, security-deep, UX/plain-language,
  simplification — each finding skeptic-verified): **zero blockers; security lens zero
  findings**; 1 should-fix + 3 nits ALL FIXED in `610ae79d` ("vunversioned" badge
  sentinel; bound-row label regression from the Library-only picker filter; Store
  search-miss copy; dead `patchDeploymentCapabilities` web client). Zero refuted.
- Lead personal reads: `api/app/api/library.py` (ActiveUser surface), the D5
  `derive_summary` diff, and `RECOMMENDED_LIBRARY_SETS` verified name-by-name against
  all six seed migrations (0056/0067/0069/0072/0073/0083 + 0086).

## Live pass — isolated fresh-org stack

curl probes, fresh org (Library EMPTY by the 0088 users-gate): **5/5**

1. whole catalog `in_library=false`;
2. capability entries carry `source/author/version/tags/recommended_for`;
3. `redlining.recommended_for == ["commercial"]`;
4. **D5 live**: a community-corpus skill surfaces top-level `author:`/`version:` on the
   wire (previously silently dropped);
5. `GET /library` (new, member-readable) returns 0 entries on the fresh org.

curl probes, adopt/member leg: **7/7**

6. adopt redlining 204; 7. `GET /library` shows it (label/provenance joined);
8. `adopted_by` ABSENT from the wire; 9. invite → accept-invite creates a member (201);
10. member `GET /library` 200 (transparency, D-B); 11. member `GET /admin/capabilities`
403 (admin fence intact); 12. member skill viewer shows D5 author/version.

Browser pass (Cypress vs vite dev on the worktree bundle): **3/3 specs**

- `store2-fresh.cy.ts` (gate-only, not committed): empty-Library teaching state +
  "Browse the Store" → Store page renders the "Recommended for {area}" rails with
  live "Add all (N remaining)" counts + built-in AND community provenance badges.
  Screenshots: `store2-library-empty-state.png`, `store2-store-rail-fresh.png`.
- `store-library.cy.ts` (committed spec): the full net-zero loop — adopt from Store →
  Library shows it unattached → Remove modal on a BOUND entry lists the area then
  CANCEL → remove the adopted entry → area playbook picker shows the Store empty-state
  link. Pre-state = upgraded-org emulation (every bound entry adopted = 17 entries,
  byte-matching the 0088 seed result); Library returned to exactly 17 after — net-zero
  proven. Spec fix found live: the Store page testids use `kind:key`, the Library
  page's `kind-key` — the spec now translates when crossing pages.
- `store2-member.cy.ts` (gate-only, not committed): member sees the read-only
  `/lq-ai/library` (cards, no Remove anywhere) and is bounced off `/lq-ai/admin/library`.
  Screenshot: `store2-member-readonly-library.png`.

Known transient: the vite dev server's first cold hit fails a spec run in <15s
(pre-mutation, no state impact) — every spec passed on its warm run.

## State impact

Dev stack: untouched. Isolated stack: torn down. Gate-only files (two extra specs,
`vite.config.smoke.ts`): removed from the branch before merge.
