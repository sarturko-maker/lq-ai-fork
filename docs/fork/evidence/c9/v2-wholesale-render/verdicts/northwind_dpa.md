# northwind_dpa (moderate) — C9 v2 (surgical-redline skill LOADED)

_Judge: Claude (Opus 4.8), sharp/sceptical panel (surgical=false if ANY material clause is struck-and-retyped wholesale). Single run per (instrument, model) — n=1; read as one strong-judged data point, not a rate._

## flash (deepseek-v4-flash)

**Verdict: ADEQUATE · surgical: no** · boilerplate-bare (deterministic): yes · status: `completed` · model turns: 18

All eight controller-side heads are hit with mostly-good bare-verb discipline, but three clauses (§3, §4, §9) came out garbled in the accepted text and §3/§8 are whole-limb retypes, so the craft is competent-but-flawed rather than clean-surgical.

- SURGICAL (good): §2 documented-instructions and §5 security are clean defined-term/limb swaps — §5 keeps 'The Processor shall implement' bare, flips '[- not be required to-]', and inserts the Art.32 risk formula by mechanism; §6 keeps 'The Processor shall notify the Controller of a personal data breach' bare with two narrow swaps.
- GARBLED OUTPUT (craft fail): §3 accepted reads 'shall not use the Personal Data the Personal Data for any purpose...' — the insert retyped 'the Personal Data' while the original object was left un-struck, a doubled-object bug from a wholesale operative-limb rewrite.
- GARBLED OUTPUT: §4 accepted reads 'shall not engage or replace Sub-processors any Sub-processor without prior written authorisation...' — same doubled-object defect; substance (prior authorisation + flow-down + 'remain fully liable') is correct but the sentence is broken.
- COHERENCE: §9 transfers leaves a dangling original fragment 'implementing any specific transfer safeguard.' after the inserted SCC/IDTA 'prior to any transfer.' sentence — grammatically broken accepted text despite correct substance.
- UNDER-PROTECTION / LEAVE-ALONE miss: §8 created the audit right but left the poison-pill final sentence ('Processor may instead provide a summary certificate... Controller agrees to accept as sufficient') untouched, gutting it; and the §4 'remain fully liable' insert directly contradicts the untouched §7 Sub-processor Liability exclusion.
- boilerplate_bare reported true and the instructed bare phrase 'The Processor shall implement' was honoured, but §3 and §8 effectively struck-and-retyped whole operative limbs, so surgical=false.

## pro (deepseek-v4-pro) — model-vs-method control

**No redline produced** (status: `failed`, model turns: 5). The stronger tier was *less* robust here — it failed to produce any tracked changes. (Any auto-generated verdict for this cell was discarded: with no pro reconstruction on disk the judge harness read a different run's file.)
