# CUAD FTS-only retrieval baseline (Track B, ADR-F049 / E0)

> slice: E0 · git_sha: 31aca7b7 · generated_at: 2026-06-28T10:27:54+00:00 · subset_requested: 150 · subset_loaded: 150 · selection: deterministic (contracts sorted by id, first N) · dataset: CUAD v1 (CC-BY-4.0, theatticusproject)

Corpus: **150 contracts**, 4911 chunks (~32.7/contract), 41 categories. **2084 present** + 4066 absent questions. Gold-span drift dropped: 0.

Retriever: matter FTS (websearch_to_tsquery 'english' + ts_rank_cd), embeddings NULL. Query: clause category name. Chunker: target=2000, overlap=200.


## Hit rate @k (any gold span retrieved)

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.274 | 0.340 | 0.370 | 0.391 | 0.402 | 0.422 |
| cross_doc | 0.009 | 0.023 | 0.031 | 0.044 | 0.052 | 0.084 |

## Recall @k (gold-span coverage)

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.234 | 0.312 | 0.344 | 0.368 | 0.380 | 0.402 |
| cross_doc | 0.007 | 0.018 | 0.026 | 0.038 | 0.044 | 0.072 |

## Precision @k

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.274 | 0.230 | 0.222 | 0.219 | 0.219 | 0.219 |
| cross_doc | 0.009 | 0.009 | 0.008 | 0.008 | 0.008 | 0.007 |

## Mean average precision

| arm | MAP |
|---|---|
| within_doc | 0.296 |
| cross_doc | 0.018 |

## Absent-clause control (within-doc)

Spurious-retrieval rate: 0.080 over 4066 absent questions. Fraction of absent-clause questions for which within-doc FTS still returned >=1 chunk. The FTS retriever cannot abstain; true abstention is an agent-mode/QA property measured in E1.


## Per-category recall@8 (within-doc, sorted worst→best)

| category | n | recall@8 |
|---|---|---|
| Affiliate License-Licensee | 20 | 0.000 |
| Affiliate License-Licensor | 11 | 0.000 |
| Anti-Assignment | 112 | 0.000 |
| No-Solicit Of Customers | 9 | 0.000 |
| No-Solicit Of Employees | 17 | 0.000 |
| Post-Termination Services | 59 | 0.000 |
| Price Restrictions | 4 | 0.000 |
| Revenue/Profit Sharing | 49 | 0.000 |
| Rofr/Rofo/Rofn | 18 | 0.000 |
| Uncapped Liability | 38 | 0.000 |
| Unlimited/All-You-Can-Eat-License | 8 | 0.000 |
| Volume Restriction | 25 | 0.000 |
| Cap On Liability | 82 | 0.016 |
| Document Name | 150 | 0.033 |
| Non-Compete | 40 | 0.050 |
| Covenant Not To Sue | 31 | 0.054 |
| Joint Ip Ownership | 15 | 0.080 |
| Most Favored Nation | 8 | 0.083 |
| Warranty Duration | 24 | 0.083 |
| Competitive Restriction Exception | 29 | 0.086 |
| Ip Ownership Assignment | 34 | 0.094 |
| Non-Disparagement | 9 | 0.111 |
| Minimum Commitment | 54 | 0.121 |
| Termination For Convenience | 62 | 0.185 |
| Expiration Date | 127 | 0.315 |
| Parties | 150 | 0.376 |
| Liquidated Damages | 21 | 0.381 |
| Notice Period To Terminate Renewal | 36 | 0.417 |
| Audit Rights | 66 | 0.441 |
| Non-Transferable License | 47 | 0.468 |
| Change Of Control | 37 | 0.595 |
| Source Code Escrow | 6 | 0.619 |
| Agreement Date | 145 | 0.624 |
| Renewal Term | 51 | 0.686 |
| Effective Date | 130 | 0.699 |
| License Grant | 81 | 0.769 |
| Third Party Beneficiary | 10 | 0.800 |
| Exclusivity | 57 | 0.849 |
| Irrevocable Or Perpetual License | 25 | 0.872 |
| Governing Law | 134 | 0.914 |
| Insurance | 53 | 0.988 |

---
*FTS-only floor — every later retrieval slice (local embeddings, rerank, PageIndex) is gated on a pre-registered delta vs these numbers (ADR-F049). Metrics are recorded findings, not pass/fail gates (ADR-F015).*
