# Verdict — Aegis "mutual" NDA (moderate; the hard *pervasive-change* case)

**Judge:** Claude (Opus 4.8). Acting-for: Recipient.

## flash (deepseek-v4-flash)

**VERDICT: WEAK (craft) / STRONG (substance)** · **SURGICAL: no** (`boilerplate_bare`=False, 17 turns)

The *substance* is partner-quality: it mutualised every one-directional clause, added all four standard exclusions (public domain / prior knowledge / independent development / required-by-law) with a protective-order proviso, capped the perpetual term at 3 years + trade-secret survival, allowed backup/legal-retention copies, and narrowed the indemnity to confidentiality breaches.

But the *craft* is **not surgical**: §2, §4, §7, §8 and §9 were struck-and-retyped wholesale. The driver is structural — this NDA is one-directional *throughout*, so mutualising it means touching nearly every word of each clause (Discloser→Disclosing Party, Recipient→Receiving Party, "the Discloser"→"the other party"). Faced with pervasive change, flash rip-and-replaced rather than making defined-term swaps that keep the verb phrases bare.

## pro (deepseek-v4-pro)

**VERDICT: FAIL (no usable output)** · **SURGICAL: n/a** (`cap_exceeded`, 30 turns, **7** apply_redline attempts, no captured redline)

Pro did **not** fix the craft — it did worse on this document: it iterated through 7 apply attempts and exhausted the 100-step budget without producing a final redline (likely re-deriving anchors across a clause it kept rewriting). So upgrading the model traded flash's rip-and-replace for non-termination.

## Read

The maintainer's "if it fails, is it the model?" — **here the answer is no.** The NDA's *pervasive-mutualisation* structure defeats both tiers' surgical craft; the stronger model is not a fix (it timed out). The lever is **method**: the `surgical-redline` skill should teach the mutualisation pattern explicitly ("swap the defined term — `The [-Customer-][+Each party+]` — keep the verb phrase bare"), and a fully-mutual NDA may warrant a longer step budget. Recorded as a C9 follow-up.
