# Verdict — Meridian professional-services agreement (moderate; flash *robustness* failure)

**Judge:** Claude (Opus 4.8). Acting-for: Customer.

## flash (deepseek-v4-flash)

**VERDICT: FAIL (no output)** · **SURGICAL: n/a** (`completed`, 4 turns, 1 preview, **0** apply, no redline)

Flash read the document, previewed once, and then ended the turn without ever calling `apply_redline` — the ~1/6 no-redline robustness gap also seen in C8. No artifact to judge.

## pro (deepseek-v4-pro)

**VERDICT: STRONG (substance) / ADEQUATE (craft)** · **SURGICAL: mostly** (`boilerplate_bare`=False, 16 turns)

Pro produced a redline where flash produced none — the clearest model-vs-method win for pro: robustness. The substance is strong and most edits are surgical:

- **§2 Acceptance** — narrow edits: `three (3)`→`fifteen (15) business` days, pay-for-all → pay-only-for-accepted, and added supplier-corrects-at-its-cost. Procedure bare.
- **§3 Fees** — capped T&M to the estimate, added a 5%/yr rate-cap with notice, kept the structure.
- **§6 Personnel** — added key-person continuity + substitution-with-consent, narrow.
- **§8 Liability** — kept the cap stem **bare**, `one (1) month`→`twelve (12) months`, made the consequential exclusion mutual, appended carve-outs.
- §4 IP and §5 warranty restructured (defensible — assigning bespoke deliverables and adding a conformance warranty need restructuring).

`boilerplate_bare`=False is driven by **§7**: pro mutualised the indemnity by striking-and-retyping it ("The Customer shall indemnify…" → "Each party shall indemnify…") instead of a defined-term swap that keeps the verb phrase bare — the same pervasive-change reflex as the NDA, but isolated to one clause here.

## Read

Pro is the better tool for this instrument purely on **robustness** (it produced a redline at all). Craft is good but for the §7 indemnity rewrite — again the mutualisation-as-rip-and-replace pattern, the one consistent craft weakness across the corpus.
