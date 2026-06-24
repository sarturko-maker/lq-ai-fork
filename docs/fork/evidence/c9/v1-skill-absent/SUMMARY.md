# C9 — Claude-judged redline craft: cross-cutting finding

**Judge:** Claude (Opus 4.8) — a *stronger* judge than C8's DeepSeek-judging-itself. Each redline was read
against its original at the edit level; verdicts are in `verdicts/<id>.md`, the reviewable `.docx` in
`flash/<id>/` and `pro/<id>/`.

## Result matrix

| tier | instrument | flash (deepseek-v4-flash) | pro (deepseek-v4-pro) |
|---|---|---|---|
| moderate | SecureScan MSA | **STRONG · surgical** | — |
| moderate | DataBridge licence | **STRONG · surgical** | — |
| moderate | Northwind DPA | **STRONG · surgical** (minor gaps) | — |
| moderate | Aegis NDA | substance STRONG, **craft WEAK** (rip-and-replace) | **FAIL** — cap_exceeded, no redline |
| moderate | Meridian SOW | **FAIL** — no redline produced | substance STRONG, **craft ADEQUATE** (§7 rewrite) |
| **complex** | **Helios master agreement** | **STRONG · surgical** | **STRONG · surgical** |
| **complex** | **Orion dev + licence** | **STRONG · surgical** | **STRONG · surgical** |

**Flash surgical-craft pass (strong judge): 5/7** — materially above C8's DeepSeek-self-judged 2/6, both
because the purposive prompts help and because a strong judge correctly credits the genuinely surgical work
the self-judge undersold.

## The headline (answers the maintainer's steer directly)

**1. Complexity is NOT the predictor of craft — clause *structure* is.** The two hardest, densest documents
(Helios, Orion) scored *among the best* on both models: precise narrow edits inside long multi-limb clauses,
with the express warranties, indemnification procedures, SLA mechanics and existing carve-outs left **bare**.
The earlier worry ("can it surgically redline complex agreements without striking language that could be left
alone?") is answered **yes** — when the one-sided terms are **localized limbs**.

**2. The one consistent craft weakness is *pervasive mutualisation*.** Where a clause is one-directional
*throughout* (the NDA, where every clause must flip Discloser/Recipient → mutual; the SOW §7 indemnity),
the model strikes-and-retypes the whole clause instead of swapping the defined term and keeping the verb
phrase bare. This is a **method** gap, not a complexity gap.

**3. "If it fails, is it the model?" — mostly NO.** The pro re-run of the two flash failures shows upgrading
the tier does **not** reliably fix craft:
- **NDA:** flash rip-and-replaced; pro did **worse** — it looped through 7 `apply_redline` attempts and hit
  the 100-step cap with no output. The stronger model is not a fix for pervasive mutualisation; it timed out.
- **SOW:** flash produced **no** redline; pro **did** (strong substance, one §7 rewrite). Here pro is the
  better tool — but on **robustness** (producing any redline), not on a craft ceiling.
- **Complex pair:** flash and pro tie (both STRONG/surgical); pro's provisos are marginally more polished.

So the lever for the remaining weakness is the **`surgical-redline` skill / method**, not the model tier:
teach the mutualisation move explicitly (`The [-Customer-][+Each party+] shall indemnify…` — swap the defined
term, keep the verb phrase bare), and give a fully-mutual document more step headroom so the stronger model
does not exhaust its budget re-deriving anchors.

## Honest limitations / follow-ups

- **Robustness:** flash ~1/6 produced no redline (the SOW); pro can exhaust the step budget on a
  pervasive-change document (the NDA). Both are reliability gaps to track, not solved here.
- **Single run per (instrument, model):** these are manual, judged artifacts, not a rate over many reps
  (that is C8's eval). Treat each as one strong-judged data point.
- **C9 follow-up for the skill (C8/F041 track):** add a worked *mutualisation* example to
  `skills/surgical-redline/SKILL.md` (defined-term swap, verb phrase bare) and consider a redline step-budget
  tier for fully-mutual instruments. Re-judge the NDA/SOW after.
- A substrate bug was found and fixed en route: the builtin `grep`/`glob` crashed any run that called them
  (`RegistrySkillBackend` inherited the protocol's `raise NotImplementedError`, which deepagents' async
  wrappers don't catch). Now a graceful unsupported result. See the C9 plan + `app/agents/skill_backend.py`.
