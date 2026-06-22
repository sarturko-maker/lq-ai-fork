# Verdict — Northwind DPA (moderate)

**Judge:** Claude (Opus 4.8). Acting-for: Controller. Run: flash (`boilerplate_bare`=True, 18 turns / 14 previews).

**VERDICT: STRONG (with minor completeness gaps)** · **SURGICAL: yes**

- **§3 Use of Data** — the surgical ideal: a two-word edit `[-may-][+shall not+]` flips the entire own-purpose/model-training clause; everything else **bare**.
- **§2 Instructions / §5 Security / §6 Breach** — narrow in-clause edits, recognisable stems ("The Processor shall process the Personal Data", "The Processor shall implement", "The Processor shall notify the Controller") left **bare**.
- **§8 Audit** — converted "no right to audit … or" → "the right … to audit …", keeping "The Controller shall have" and "records" bare.
- **§9 Transfers** — appended an SCC-safeguards requirement.
- §4 sub-processing and §10 return/deletion are fuller rewrites — justified (both needed substantial additions: flow-down + liability; return-or-destroy + legal-retention).

**Completeness gaps a partner would flag (not craft defects):** §7 (sub-processor liability) left untouched, and §8's "*which the Controller agrees to accept as sufficient*" tail left bare — it undercuts the audit right just added. §11's one-month cap was out of scope of the instruction (not listed). The §9 boundary edit leaves a small "discretion and , and" artifact.

Net: strong, surgical craft; a couple of missed limbs. Took the most previews (14) of any moderate run — laborious but converged.
