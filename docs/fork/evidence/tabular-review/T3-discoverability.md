# F2 Tabular T3 — discoverability finding (ADR-F055 / ADR-F041)

The `tabular-review` craft skill (`skills/tabular-review/SKILL.md`, bound to Commercial by
migration 0083) teaches the agent to reach for a grid when the matter holds several
documents and the ask is compare/extract-across, to map natural language onto
`start_tabular_review` columns, and to stay quiet when a grid does not fit. This is the
craft layer (ADR-F041) on top of the always-on `TABULAR_FILL_DOCTRINE`.

## Eval (masked, live DeepSeek, ADR-F015 finding — not a gate)

`api/tests/agents/scenarios/test_tabular_discoverability_eval.py` (provider-marked, CI
skips). Three scenarios whose prompts **never name a grid or a tool** — they state a
lawyer's intent — over a freshly-seeded Commercial matter with the `tabular-review` skill
**loaded into the registry and injected** (see the methodology note below). "Surfaced a
grid" = the agent **built** one (`start_tabular_review`) **or proposed** one in prose ("I
can build a grid comparing…") — for a vague "what's the best way to see this?" ask, an
offer is a legitimate answer, so the metric measures *discoverability*, not just building.

| Scenario | Docs | Intent | Should surface? | Rep 1 | Rep 2 |
|---|---|---|---|---|---|
| `apt-vague` | 3 NDAs | "get on top of their key terms… what's the best way to see this?" | yes | built ✓ | built ✓ |
| `apt-table` | 3 NDAs | "give me a table of the term and governing law for each" | yes | built + proposed ✓ | built + proposed ✓ |
| `quiet-single-doc` | 1 NDA | "what's the term in nda-alpha.txt?" | no | quiet ✓ | quiet ✓ |

**Result: 3/3 on both reps** (columns chosen on the apt cases: Term, Governing law). The
model is stochastic and N is small — an earlier single run had `apt-vague` answer in prose
instead of building (see below); it is the borderline case, and the metric now credits a
prose offer there too.

## Methodology note — the eval was corrected after a fresh-context review

The first version of this eval called `run_scenario` **without** `skill_registry=`, so the
harness threaded a `None` registry and every bound skill — including `tabular-review` — was
dropped as drift (`composition.py` treats an unknown registry as "no skills"). That run
therefore measured only the always-on doctrine + model stochasticity, **not the skill** —
the [[eval-attribution-confirm-capability]] trap. A fresh-context adversarial review of the
T3 diff caught it. The fix loads the real registry (`load_registry(LQ_AI_SKILLS_DIR)`),
asserts `tabular-review` is present, and passes `skill_registry=registry` (as every sibling
craft eval does). The table above is the **corrected** finding, with the skill genuinely
injected. (In production the registry always loads from `app.state`, so the shipped feature
— bind + inject — was never affected; only the eval's attribution was.)

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
