# CUAD FTS-only retrieval baseline (Track B, ADR-F049 / E0)

> slice: D · git_sha: slice-d · generated_at: 2026-06-29T23:15:22+00:00 · subset_requested: 30 · subset_loaded: 30 · candidate_base: fts · embedder: None · reranker: local:Xenova/ms-marco-MiniLM-L-6-v2 · alpha: None · rerank_candidates: 30 · selection: deterministic (contracts sorted by id, first N) · dataset: CUAD v1 (CC-BY-4.0, theatticusproject)

Corpus: **30 contracts**, 876 chunks (~29.2/contract), 39 categories. **388 present** + 842 absent questions. Gold-span drift dropped: 0.

Retriever: matter FTS (websearch_to_tsquery 'english' + ts_rank_cd), embeddings NULL + cross-encoder rerank (local:Xenova/ms-marco-MiniLM-L-6-v2, candidates=30). Query: clause category name. Chunker: target=2000, overlap=200.


## Hit rate @k (any gold span retrieved)

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.268 | 0.317 | 0.345 | 0.356 | 0.366 | 0.376 |
| cross_doc | 0.044 | 0.090 | 0.126 | 0.149 | 0.162 | 0.209 |

## Recall @k (gold-span coverage)

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.233 | 0.291 | 0.322 | 0.332 | 0.345 | 0.354 |
| cross_doc | 0.034 | 0.075 | 0.106 | 0.129 | 0.143 | 0.184 |

## Precision @k

| arm | @1 | @3 | @5 | @8 | @10 | @20 |
|---|---|---|---|---|---|---|
| within_doc | 0.268 | 0.199 | 0.190 | 0.185 | 0.186 | 0.185 |
| cross_doc | 0.044 | 0.038 | 0.037 | 0.033 | 0.033 | 0.029 |

## Mean average precision

| arm | MAP |
|---|---|
| within_doc | 0.281 |
| cross_doc | 0.067 |

## Absent-clause control (within-doc)

Spurious-retrieval rate: 0.075 over 842 absent questions. Fraction of absent-clause questions for which within-doc FTS still returned >=1 chunk. The FTS retriever cannot abstain; true abstention is an agent-mode/QA property measured in E1.


## Per-category recall@8 (within-doc, sorted worst→best)

| category | n | recall@8 |
|---|---|---|
| Affiliate License-Licensee | 2 | 0.000 |
| Affiliate License-Licensor | 1 | 0.000 |
| Anti-Assignment | 19 | 0.000 |
| Change Of Control | 3 | 0.000 |
| Competitive Restriction Exception | 5 | 0.000 |
| Covenant Not To Sue | 7 | 0.000 |
| No-Solicit Of Customers | 2 | 0.000 |
| No-Solicit Of Employees | 3 | 0.000 |
| Non-Compete | 8 | 0.000 |
| Non-Disparagement | 2 | 0.000 |
| Post-Termination Services | 15 | 0.000 |
| Revenue/Profit Sharing | 10 | 0.000 |
| Rofr/Rofo/Rofn | 4 | 0.000 |
| Third Party Beneficiary | 1 | 0.000 |
| Uncapped Liability | 4 | 0.000 |
| Unlimited/All-You-Can-Eat-License | 1 | 0.000 |
| Volume Restriction | 7 | 0.000 |
| Warranty Duration | 4 | 0.000 |
| Ip Ownership Assignment | 6 | 0.033 |
| Cap On Liability | 14 | 0.044 |
| Document Name | 30 | 0.067 |
| Termination For Convenience | 11 | 0.091 |
| Joint Ip Ownership | 2 | 0.100 |
| Audit Rights | 13 | 0.167 |
| Minimum Commitment | 13 | 0.192 |
| Most Favored Nation | 3 | 0.222 |
| Expiration Date | 23 | 0.239 |
| Liquidated Damages | 3 | 0.333 |
| Notice Period To Terminate Renewal | 6 | 0.333 |
| Parties | 30 | 0.431 |
| Agreement Date | 29 | 0.552 |
| Non-Transferable License | 7 | 0.571 |
| Governing Law | 27 | 0.648 |
| Effective Date | 25 | 0.713 |
| Renewal Term | 7 | 0.714 |
| Exclusivity | 12 | 0.840 |
| License Grant | 15 | 0.900 |
| Insurance | 11 | 1.000 |
| Irrevocable Or Perpetual License | 3 | 1.000 |

---
*FTS-only floor — every later retrieval slice (local embeddings, rerank, PageIndex) is gated on a pre-registered delta vs these numbers (ADR-F049). Metrics are recorded findings, not pass/fail gates (ADR-F015).*
