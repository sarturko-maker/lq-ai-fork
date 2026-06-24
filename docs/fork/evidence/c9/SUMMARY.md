# C9 — redline craft, v3 (Adeu native WORD-DIFF render, ADR-F045)

**What changed since v2.** v2 proved the residual weakness was real with the `surgical-redline` skill loaded:
on dense clauses the model still struck-and-retyped wholesale (indemnity/grant/NDA), plus "seam" defects
(duplicated inserted text). Root-causing it (see ADR-F045) showed the cause was **our renderer**, not only
model craft: we sent one wholesale `ModifyText` per edit and Adeu trimmed only the common prefix/suffix —
**swallowing unchanged interiors**. v3 re-enables Adeu's **native word-level diff**
(`generate_edits_from_text`, applied via `apply_edits`), so the tool keeps unchanged wording bare, and
**simplifies the skill** to "quote the clause, change only the necessary words — the tool diffs it."

**Judge:** Claude (Opus 4.8), the **same** sharp/sceptical panel as v2 (`surgical=false` if **any** material
clause is struck-and-retyped wholesale) + the **adversarial refuter** on the mutualisation cases. One run per
instrument (**n=1**). The v2 matrix below is the archived `v2-wholesale-render/` re-judged figure.

## Headline: the renderer fix resolves the two prior-slice residuals

The word-diff renderer is a **deterministic** change (unit-tested — `test_redline_service.py`), so its
interior-bare property is *verifiable*, not n=1-bound; the live eval then shows the model producing surgical
redlines *through* it.

1. **Pervasive mutualisation — RESOLVED.** The Aegis "mutual" NDA — the headline weakness that failed in v1
   flash, v2 flash **and** v2 pro — is now **STRONG·surgical** and **survived the adversarial refuter**: every
   clause mutualised by a `Recipient/Discloser → each Party/other Party` term-swap with `shall hold in strict
   confidence` / `shall indemnify, defend and hold harmless` left **bare**. No clause struck-and-retyped.
2. **Editor "seam" defects — ELIMINATED (deterministic).** v2's duplicated inserted text (`In no event In no
   event`, SecureScan §9, from overlapping anchors) is **gone** in v3; a repeated-phrase scan finds zero across
   all 7 instruments. One clean diff per clause + Adeu's overlap detection removes the whole class.
3. **Dense single-party GRANT clauses — now surgical.** The v2 #1 residual (IP/data/content licences struck
   wholesale: SecureScan §5/§6, DataBridge §4/§5, Northwind §4 sub-processing) is now in-sentence
   term/verb swaps with grant stems bare.

**Deterministic signals:** redlined **7/7**, boilerplate-bare **7/7** (v2: 6/7), 5/7 with zero
long-strike-blocks (the 2 exceptions are *legitimate* deletions of adverse clauses, below).

## Result matrix (identical sharp panel; flash)

| tier | instrument | v1 flash (skill absent) | v2 flash (wholesale render) | **v3 flash (word-diff)** |
|---|---|---|---|---|
| moderate | SecureScan MSA | STRONG·surgical | ADEQUATE·not-surgical | **STRONG·surgical** |
| moderate | DataBridge licence | STRONG·surgical | STRONG·not-surgical | **STRONG·surgical** |
| moderate | Aegis NDA *(mutualisation)* | ADEQUATE·not-surgical | ADEQUATE·not-surgical | **STRONG·surgical** *(refuter: not refuted)* |
| moderate | Northwind DPA | ADEQUATE·surgical | ADEQUATE·not-surgical *(garbled seams)* | **STRONG·surgical** |
| moderate | Meridian SOW *(mutualisation)* | NONE — no redline | STRONG·surgical | ADEQUATE·not-surgical |
| **complex** | **Helios master agreement** | STRONG·surgical | STRONG·surgical | **STRONG·surgical** |
| **complex** | **Orion dev + licence** | STRONG·surgical | STRONG·surgical | **STRONG·surgical** |
| | **surgical-pass** | 5 / 7 | **3 / 7** | **6 / 7** |
| | **STRONG** | — | 4 / 7 | **6 / 7** |
| | **redlined (robustness)** | 6 / 7 | 7 / 7 | **7 / 7** |
| | **boilerplate-bare (deterministic)** | 5 / 7 | 6 / 7 | **7 / 7** |

## The one non-surgical case is the model's choice, not the renderer's

**Meridian SOW flipped STRONG→ADEQUATE.** Its mutualisation heads (§7 indemnity, §8 cap) are "gold-standard
surgical" (defined-term swap, verb phrase bare, appended carve-out). It is marked not-surgical only because the
model chose to **strike-and-retype** the §5 warranty disclaimer and the §6 personnel tail as long blocks. The
judge notes the AS-IS→affirmative-warranty flip "excuses it but it is still wholesale." This is a **genuine
rewrite** (the new wording differs throughout) that the word-diff renderer **correctly** preserves as a block —
exactly the design (a true rewrite is not fabricated into false surgery; the **gate**, not the renderer, guards
genuine over-rewording). It is **not** an interior-swallow defect. So Meridian's flip is model stochasticity on
*which* clauses to wholesale-replace (n=1), not a v3 regression.

## Honesty / limits

- **n=1, stochastic.** 4 instruments improved (SecureScan, DataBridge, Aegis, Northwind), 1 flipped down
  (Meridian), 2 unchanged (Helios, Orion). The surgical-pass jump 3/7→6/7 is directionally strong and is
  **corroborated** by the deterministic signals (bare 6→7, seam defects eliminated, grant swallows resolved)
  and by the understood mechanism — but the per-instrument boolean remains noisy at one run each. The reliable
  evidence is: the renderer's interior-bare behaviour is **unit-test-proven** and visible in every v3
  reconstruction; the model now feeds it whole-clause edits.
- **Pro not run this round.** Flash has **no hard failure** (no NONE, no boilerplate swallow); the lone
  ADEQUATE is a defensible wholesale replacement of an adverse disclaimer, not a renderer defect. The v2 finding
  established pro does not improve craft and is *less* robust, so a pro re-run would not bear on the renderer
  thesis. (Re-runnable via `LQ_AI_SCENARIO_MODEL=deepseek-pro` if a specific case needs the control.)
- **Gate unchanged.** D1–D5 still key on the minimal token diff (renderer-agnostic) and still guard genuine
  over-rewording; no threshold change shipped (unverifiable at n=1 — ADR-F045).

## Evidence

- `flash/<id>/` — original + `* (redlined).docx`, `reconstruction.txt`, `accepted-clean.txt`; `flash/manifest.json`.
- `verdicts/<id>.md` — the v3 Claude verdicts (+ Aegis refuter).
- `v2-wholesale-render/` — the archived v2 (skill loaded, pre-word-diff) run + its SUMMARY/verdicts.
- `v1-skill-absent/` — the original confounded run (skill silently dropped).
