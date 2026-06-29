# CUAD FTS-only retrieval baseline (Track B, ADR-F049 / E0)

> slice: C1 · git_sha: fdc096a8-slice-d · generated_at: 2026-06-29T22:11:06+00:00 · subset_requested: 30 · subset_loaded: 30 · embedder: local:BAAI/bge-base-en-v1.5 · alpha: 0.5 · selection: deterministic (contracts sorted by id, first N) · dataset: CUAD v1 (CC-BY-4.0, theatticusproject)

Corpus: **30 contracts**, 876 chunks (~29.2/contract), 39 categories. **388 present** + 842 absent questions. Gold-span drift dropped: 0.

Retriever: matter hybrid (FTS websearch_to_tsquery + pgvector cosine, alpha=0.5, embedder=local:BAAI/bge-base-en-v1.5). Query: clause category name. Chunker: target=2000, overlap=200.


## Hit rate @k (any gold span retrieved)

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.384 | 0.580 | 0.670 | 0.812 | 0.845 | 0.920 |
| cross_doc | 0.041 | 0.082 | 0.113 | 0.144 | 0.162 | 0.253 |

## Recall @k (gold-span coverage)

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.318 | 0.527 | 0.629 | 0.769 | 0.807 | 0.905 |
| cross_doc | 0.029 | 0.073 | 0.100 | 0.125 | 0.143 | 0.222 |

## Precision @k

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.384 | 0.238 | 0.175 | 0.140 | 0.123 | 0.089 |
| cross_doc | 0.041 | 0.034 | 0.028 | 0.024 | 0.022 | 0.017 |

## Mean average precision

| arm | MAP |
|---|---|
| within_doc | 0.489 |
| cross_doc | 0.069 |

## Absent-clause control (within-doc)

Spurious-retrieval rate: 1.000 over 842 absent questions. Fraction of absent-clause questions for which within-doc FTS still returned >=1 chunk. The FTS retriever cannot abstain; true abstention is an agent-mode/QA property measured in E1.


## Per-category recall@8 (within-doc, sorted worst→best)

| category | n | recall@8 |
|---|---|---|
| Third Party Beneficiary | 1 | 0.000 |
| Non-Disparagement | 2 | 0.250 |
| Rofr/Rofo/Rofn | 4 | 0.250 |
| Covenant Not To Sue | 7 | 0.321 |
| Competitive Restriction Exception | 5 | 0.400 |
| Volume Restriction | 7 | 0.429 |
| Parties | 30 | 0.433 |
| Unlimited/All-You-Can-Eat-License | 1 | 0.500 |
| Most Favored Nation | 3 | 0.556 |
| Document Name | 30 | 0.567 |
| Minimum Commitment | 13 | 0.644 |
| Liquidated Damages | 3 | 0.667 |
| Audit Rights | 13 | 0.731 |
| Agreement Date | 29 | 0.759 |
| Cap On Liability | 14 | 0.785 |
| Joint Ip Ownership | 2 | 0.800 |
| Revenue/Profit Sharing | 10 | 0.800 |
| Expiration Date | 23 | 0.826 |
| Ip Ownership Assignment | 6 | 0.833 |
| Post-Termination Services | 15 | 0.844 |
| Effective Date | 25 | 0.860 |
| Governing Law | 27 | 0.870 |
| Termination For Convenience | 11 | 0.909 |
| Anti-Assignment | 19 | 0.912 |
| Warranty Duration | 4 | 0.917 |
| Exclusivity | 12 | 0.944 |
| Insurance | 11 | 0.955 |
| License Grant | 15 | 0.978 |
| Affiliate License-Licensee | 2 | 1.000 |
| Affiliate License-Licensor | 1 | 1.000 |
| Change Of Control | 3 | 1.000 |
| Irrevocable Or Perpetual License | 3 | 1.000 |
| No-Solicit Of Customers | 2 | 1.000 |
| No-Solicit Of Employees | 3 | 1.000 |
| Non-Compete | 8 | 1.000 |
| Non-Transferable License | 7 | 1.000 |
| Notice Period To Terminate Renewal | 6 | 1.000 |
| Renewal Term | 7 | 1.000 |
| Uncapped Liability | 4 | 1.000 |

---
*FTS-only floor — every later retrieval slice (local embeddings, rerank, PageIndex) is gated on a pre-registered delta vs these numbers (ADR-F049). Metrics are recorded findings, not pass/fail gates (ADR-F015).*
