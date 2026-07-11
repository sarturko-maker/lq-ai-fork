# B-2c — deep security review of the B-2 org-skill harness (2026-07-11)

Fresh-context adversarial review (ADR-F005), 4 security lenses over the whole propose→approve→
snapshot→compose path (B-2a #238, B-2b #246, PUBLISH #255), each finding independently
adversarially verified. Scope files: `app/skills/org_proposal.py`, `app/api/user_skills.py`,
`app/api/admin.py`, `app/agents/capabilities.py`, `app/agents/skill_backend.py`,
`app/models/org_skill.py`, migration 0091.

## Result: zero confirmed vulnerabilities in the harness

All four lenses — **authority-seam** (can content grant more than prompt text?), **authz-fences**
(owner-scope 404s, the operator fence, role gates, the publish fast-path), **injection-integrity**
(immutable snapshot, provenance-banner spoofing, YAML/config confusion, the size cap), and
**audit-contract** (no content in audit rows) — found no attacker scenario that survived
verification. The frontmatter allowlist is genuinely the only authority seam; org content reaches
the model only as untrusted read-only skill text; the operator fence and owner-scope 404s hold; the
content-hash snapshot is immutable after approval.

## Three test-soundness critiques — all fixed in this slice

The review's only surviving findings were against the **B-2c tests' own soundness** (not the
harness — which is why they verified as "not a system vulnerability"). All three were applied so the
evidence is sound rather than merely green:

1. **Grant-vocabulary too narrow.** The pure containment check equated the runtime grant vocabulary
   with `union(GROUP_TOOL_NAMES)` alone, omitting the matter-scope read tools. → Broadened to
   `hitl_eligible_tool_names()` (groups ∪ matter-scope), reframed honestly as a corpus-validity
   check, and the docstring now names the REAL-guard refusal test as the load-bearing proof (with a
   note that deepagents builtins are also grant-fixed and content-blind).
2. **Docstring referenced a nonexistent live-scenario file.** → Removed; the live masked-judge leg
   is stated as deferred-on-record (pointing at this evidence dir), because R6 is a code invariant
   proven deterministically, not a model behaviour.
3. **`assert not hasattr(wiring, "tools")` was a tautology** (SkillWiring is a frozen dataclass, so
   the field never exists regardless of input). → Replaced with a real delivery assertion (read the
   hostile body back out of the backend via `ls`/`read` — the exact SkillsMiddleware path) plus a
   structural pin that the wiring's entire output surface is `{backend, main_sources, subagents}`,
   which would fail if a tool-bearing field were ever added.

Post-fix: `test_org_skill_redteam.py` 15/15; combined with the B-2a/B-2b harness suites 76/76.
