# F2 Tabular T3 — discoverability finding (ADR-F055 / ADR-F041)

The `tabular-review` craft skill (`skills/tabular-review/SKILL.md`, bound to Commercial by
migration 0083) teaches the agent to reach for a grid when the matter holds several
documents and the ask is compare/extract-across, to map natural language onto
`start_tabular_review` columns, and to stay quiet when a grid does not fit. This is the
craft layer (ADR-F041) on top of the always-on `TABULAR_FILL_DOCTRINE`.

## Eval (masked, live DeepSeek, ADR-F015 finding — not a gate)

`api/tests/agents/scenarios/test_tabular_discoverability_eval.py` (provider-marked, CI
skips). Three scenarios whose prompts **never name a grid or a tool** — they state a
lawyer's intent — over a freshly-seeded Commercial matter. The eval records whether the
agent reached for `start_tabular_review`:

| Scenario | Docs | Intent | Should offer? | Result |
|---|---|---|---|---|
| `apt-vague` | 3 NDAs | "get on top of their key terms… what's the best way to see this?" | yes | **builds grid** ✓ |
| `apt-table` | 3 NDAs | "give me a table of the term and governing law for each" | yes | **builds grid** (columns: Term, Governing law) ✓ |
| `quiet-single-doc` | 1 NDA | "what's the term in nda-alpha.txt?" | no | **no grid** (answers directly) ✓ |

**Result after tuning: 3/3.** (N=1 per scenario, model is stochastic — a recorded finding,
not a guarantee.)

### Tuning note (the eval did its job)

The first run was **2/3**: `apt-table` and `quiet-single-doc` were already correct, but on
the **vague** ask ("what's the best way to see this across them?") the agent read all three
documents and answered in **prose** instead of building a grid — precisely the
discoverability case the skill exists for. Strengthening the skill's guidance to **build the
grid on a clear multi-document compare/extract/get-on-top intent** (rather than offer-and-
wait, and rather than answering the across-many-documents question in prose) moved it to
**3/3**. That the edit changed behaviour also confirms the skill is genuinely injected (not
masked by the doctrine alone).

Run:

```
DATABASE_URL=… LQ_AI_GATEWAY_KEY=… LQ_AI_GATEWAY_URL=http://gateway:8001 \
LQ_AI_SKILLS_DIR=/skills \
pytest -m provider -s tests/agents/scenarios/test_tabular_discoverability_eval.py
```

## Deterministic gate (CI)

- The SKILL.md loads cleanly (frontmatter valid) — `test_skill_loader` asserts on-disk ==
  registry names, so a malformed skill fails CI.
- Migration 0083 binds `tabular-review` to Commercial (idempotent, 0056/0072 pattern);
  `test_practice_areas` asserts it is in Commercial's `bound_skills`; up→down→up round-trips
  on throwaway pgvector.
- The skill auto-appears as a toggleable Commercial capability (default-on, ADR-F054) — the
  capability inventory builds a skill entry from the bound name + registry summary.
