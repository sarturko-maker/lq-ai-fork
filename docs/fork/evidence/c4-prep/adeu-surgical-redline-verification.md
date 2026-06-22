# Adeu surgical-redline verification — read straight from `word/document.xml`

**Slice:** C4-prep (review spike requested 2026-06-21). **Gates:** C4 (`apply_redline`), ADR-F018 (proposed).
**Question (maintainer):** a lawyer makes a *multi-word change inside a sentence without redlining the whole
sentence* — can Adeu actually do this? *Verify by reading the XML; don't assume it can't if it fails first.*

**Verdict: yes, proven.** `adeu==1.12.1` emits **surgical sub-sentence** tracked changes. It uses
`diff-match-patch` internally (a direct Adeu runtime dep, Apache-2.0 — see `adeu-pinning.md` §5) and, when it
applies a `ModifyText(target_text, new_text)`, character-trims the **common prefix/suffix** so the sentence's
unchanged head/tail stay as **bare runs**; only the changed span becomes `<w:ins>`/`<w:del>`
(engine `_apply_single_edit_heuristic` → `_trim_common_context`). The separate `adeu.diff.generate_edits_from_text`
path does a full **word-level** diff (`_words_to_chars` token encoding → `diff_main` → `diff_cleanupSemantic`)
that decomposes a rewrite into discrete minimal edits.

## Method

Throwaway `python:3.12-slim` container, `pip install adeu==1.12.1` (the C-R0 reproduction recipe), build a
realistic vendor-favoured liability sentence with `python-docx`, apply edits via
`RedlineEngine.process_batch(..., dry_run=False)`, then unzip `word/document.xml` and reconstruct each
paragraph with the tracked-change boundaries made visible. Script: `adeu_surgical_smoke.py` (this dir). Run:

```bash
docker run --rm -v "$PWD/docs/fork/evidence/c4-prep/adeu_surgical_smoke.py:/s.py:ro" \
  python:3.12-slim bash -c "pip install -q 'adeu==1.12.1' && python /s.py"
```

Reconstruction legend: bare text = untouched `<w:r>`; `[-x-]` = `<w:del>` (deleted); `[+y+]` = `<w:ins>` (inserted).
Source clause:
> The Vendor's aggregate liability arising out of or in connection with this Agreement shall not exceed the
> total fees paid by the Customer in the three (3) months preceding the claim.

## Results (verbatim from the emitted XML)

**Case 1 — one contiguous change as a *whole-sentence* `ModifyText`.** Head stays bare; only the tail is marked:
> … shall not exceed the `[-total fees paid by the Customer in the three (3) months preceding the claim.-]``[+greater of the total fees paid by the Customer in the twelve (12) months preceding the claim or two times the annual fees.+]`

**Case 2 — two *narrow* `ModifyText` edits (one per change). The textbook surgical result** — unchanged middle bare:
> … in the `[-three (3)-]``[+twelve (12)+]` months preceding the `[-claim.-]``[+claim, save that liability for breach of confidentiality, data protection obligations or infringement of intellectual property rights shall be unlimited.+]`

**Case 3 — two changes crammed into *one* whole-sentence `ModifyText` (the anti-pattern). Over-marks the middle:**
> … in the `[-three (3) months preceding the claim.-]``[+twelve (12) months preceding the claim, save that data-protection liability shall be unlimited.+]`

(`process_batch` reported `edits_applied: 1 / 1 / 1`, `edits_skipped: 0` for the three cases respectively;
Case 2 = 2 edits applied.)

## The load-bearing finding for C4's gate (multi-region divergence)

Adeu's **rendering** trims only the common *prefix/suffix* of each `ModifyText` — it does **not** keep an
unchanged *interior* run bare. So a single `ModifyText` covering **two separated changes** renders as **one**
contiguous `<w:del>`/`<w:ins>` block that swallows the unchanged words between them (Case 3). This **diverges**
from the §6.1 minimal-token-diff metric, which would see Case 3's *real* change as small (equal-middle) and
**pass** D1 — yet the document reads as an aggressive whole-sentence rewrite. The gate must therefore not score
the abstract minimal diff alone; it must enforce a **surgical rendering**. Two ways, in order of preference:

1. **Decompose before apply.** Route every proposed `ModifyText` through Adeu's bundled word-level
   `generate_edits_from_text(target_text, new_text)` (or our own dmp pass) to split a multi-region rewrite into
   the discrete minimal edits Adeu renders cleanly (turns a Case-3 input into Case-2 output). Confirm the symbol
   exists on the pin before relying on it (`adeu.diff` is exported on 1.12.1; the function shape is from 0.7.0
   source — re-verify at C4 under the §8 signature check). **Recommended.**
2. **Gate rule: one contiguous change region per edit.** Reject a `ModifyText` whose minimal token-diff has
   `>1` changed region separated by `≥ N` equal tokens (force the agent to emit narrow Case-2 edits). Cheaper,
   no dependence on `generate_edits_from_text`; the cost is more model effort decomposing edits.

Either way, the **surgical bias the user described is achievable today** — the agent (or our pre-processing)
must propose **one narrow edit per discrete change**, never one sentence-level rewrite. Captured into
`commercial-lawyer-method.md` §5 (substantive strategy) + §6.1 (the rendering nuance); C4 implements it.
