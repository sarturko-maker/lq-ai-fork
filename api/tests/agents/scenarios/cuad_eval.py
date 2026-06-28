"""CUAD-gold retrieval eval — Track B (ADR-F049, slice E0).

The objective half of the retrieval instrument: load the Contract Understanding
Atticus Dataset (CUAD, CC-BY-4.0 — see ``NOTICES.md``), seed each contract as a
matter document through the *real* ingest shape (verbatim text + the production
chunker), then run the *real* matter FTS retriever over the 41 clause-category
questions and score the retrieved chunk spans against CUAD's human ``answer_start``
gold spans with :mod:`tests.agents.scenarios.retrieval_metrics`.

Why this design (the seam map, ADR-F049):

* **Faithful to production.** Contracts are seeded with ``normalized_content`` set
  to the verbatim CUAD ``context`` and chunked by :func:`app.pipeline.chunker.
  chunk_document` — so chunk offsets and CUAD ``answer_start`` share one
  coordinate system, and the FTS path being scored is the one the agent's
  ``search_documents`` tool actually runs.
* **Zero LLM cost.** Retrieval is called directly (the same SQL the guarded
  ``search_documents`` runs); no gateway, no tokens — so the baseline runs
  deterministically and, for a tiny synthetic corpus, in CI. Agent-mode
  answer-quote scoring is deferred to E1 (the agent's retrieved-chunk set is not
  observable from run steps anyway).
* **Two arms.** *within-doc* (retrieval scoped to the gold contract — the classic
  CUAD single-document extraction setting: can the retriever find the clause?)
  and *cross-doc* (retrieval over the whole matter — the at-scale setting that
  motivates F2: can the right clause surface from the right document among many?).

The matter FTS query (``app/agents/tools.py:_FTS_SQL``) projects no character
offsets, so this module runs a parallel query that mirrors its ranking and
scoping exactly but also selects ``char_offset_start/_end`` + ``document_id``.
``test_cuad_retrieval_smoke`` drift-guards the two against each other.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.tools import MatterBinding
from app.models.document import Document
from app.models.file import File
from app.pipeline.chunker import (
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_TARGET_CHARS,
    chunk_document,
)
from app.pipeline.parsers import PageSpan, ParsedDocument
from tests.agents.scenarios.harness import seed_multi_doc_matter
from tests.agents.scenarios.retrieval_metrics import (
    Span,
    any_hit_at_k,
    average_precision,
    precision_at_k,
    recall_at_k,
)
from tests.agents.scenarios.scenarios import DocChunk, FixtureDocument

# Default CUAD corpus location (gitignored — populated by scripts/fetch_cuad.sh).
# Overridable via the LQ_AI_CUAD_DIR env (read by the caller).
DEFAULT_CUAD_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "cuad"
CUAD_JSON_NAME = "CUADv1.json"

# Maintainer ruling (2026-06-28): the frozen baseline covers a deterministic
# 150-contract subset (sorted by contract id), all 41 categories. The runner is
# parameterised so any N can be re-run later.
DEFAULT_SUBSET = 150

# k cut-offs reported. 8 is the production matter retriever's top-k
# (``tools.py:_SEARCH_LIMIT``); the rest bracket it for the baseline curve.
DEFAULT_K_VALUES: tuple[int, ...] = (1, 3, 5, 8, 10, 20)


@dataclass(frozen=True)
class CuadQuestion:
    """One CUAD (contract, clause-category) question and its gold spans."""

    contract_id: str
    category: str
    question_text: str
    is_impossible: bool
    # Half-open char spans into the contract context (== seeded normalized_content).
    gold_spans: list[Span]


@dataclass(frozen=True)
class CuadContract:
    """One CUAD contract: full text + its 41 category questions."""

    contract_id: str
    context: str
    questions: list[CuadQuestion]


@dataclass(frozen=True)
class CuadCorpus:
    """A loaded CUAD subset plus load-time provenance."""

    contracts: list[CuadContract]
    # Gold spans whose (answer_start, len) slice did not match the answer text
    # and could not be relocated — dropped, and counted here for honesty.
    gold_span_drift: int


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk returned by the offset-projecting FTS retriever."""

    filename: str
    document_id: uuid.UUID
    char_offset_start: int
    char_offset_end: int
    rank: float


# ---------------------------------------------------------------------------
# CUAD loading
# ---------------------------------------------------------------------------


def _category_from_id(qa_id: str, question: str) -> str:
    """Recover the clause category from a CUAD qa id (or, failing that, the text).

    Ids are ``<title>__<Category>_<n>`` — split on the DOUBLE underscore, then
    strip the trailing ``_<n>`` (category names contain spaces/hyphens/slashes
    but never ``__``). Fallback: the quoted category in the question template.
    """
    if "__" in qa_id:
        return qa_id.split("__", 1)[1].rsplit("_", 1)[0]
    m = re.search(r'related to "([^"]+)"', question)
    return m.group(1) if m else qa_id


def load_cuad(
    cuad_dir: Path | str = DEFAULT_CUAD_DIR,
    *,
    limit: int | None = DEFAULT_SUBSET,
    categories: set[str] | None = None,
) -> CuadCorpus:
    """Parse the raw ``CUADv1.json`` into a deterministic contract subset.

    Parses the raw SQuAD-2.0 JSON directly (NOT the HuggingFace loader, which
    discards ``is_impossible``). Contracts are sorted by ``title`` and the first
    ``limit`` are kept, so the subset is reproducible. Multi-span answers are
    preserved; absent clauses (``is_impossible``/empty answers) keep empty gold.
    Each gold span is validated against the contract text and relocated (or
    dropped + counted) on mismatch.
    """
    path = Path(cuad_dir)
    if path.is_dir():
        path = path / CUAD_JSON_NAME
    data = json.loads(path.read_text(encoding="utf-8"))["data"]
    entries = sorted(data, key=lambda e: str(e["title"]))

    contracts: list[CuadContract] = []
    drift = 0
    for entry in entries:
        if limit is not None and len(contracts) >= limit:
            break
        title = str(entry["title"])
        paragraph = entry["paragraphs"][0]
        context = str(paragraph["context"])
        questions: list[CuadQuestion] = []
        for qa in paragraph["qas"]:
            category = _category_from_id(str(qa["id"]), str(qa.get("question", "")))
            if categories is not None and category not in categories:
                continue
            answers = qa.get("answers", []) or []
            is_impossible = bool(qa.get("is_impossible", not answers))
            gold: list[Span] = []
            for ans in answers:
                start = int(ans["answer_start"])
                ans_text = str(ans["text"])
                end = start + len(ans_text)
                if context[start:end] != ans_text:
                    found = context.find(ans_text)
                    if found < 0:
                        drift += 1
                        continue
                    start, end = found, found + len(ans_text)
                gold.append((start, end))
            questions.append(
                CuadQuestion(
                    contract_id=title,
                    category=category,
                    question_text=str(qa.get("question", "")),
                    is_impossible=is_impossible,
                    gold_spans=gold,
                )
            )
        contracts.append(CuadContract(contract_id=title, context=context, questions=questions))

    return CuadCorpus(contracts=contracts, gold_span_drift=drift)


# ---------------------------------------------------------------------------
# Seeding: CUAD contract -> matter document (production chunker)
# ---------------------------------------------------------------------------


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "contract"


def cuad_contract_to_fixture(
    contract: CuadContract,
    *,
    index: int,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> FixtureDocument:
    """Build a seedable :class:`FixtureDocument` from a CUAD contract.

    ``normalized_content`` is the verbatim CUAD context (so gold ``answer_start``
    stays valid); chunks come from the production :func:`chunk_document` over a
    single-page :class:`ParsedDocument`, so the baseline reflects the real
    chunker. The Citation-Engine fidelity invariant
    (``normalized_content[start:end] == chunk.content``) is asserted.
    """
    parsed = ParsedDocument(
        canonical_text=contract.context,
        pages=[PageSpan(page_number=1, char_start=0, char_end=len(contract.context))],
        page_count=1,
        parser="cuad-fixture",
        parser_version="cuad-v1",
    )
    chunks = chunk_document(parsed, target_chars=target_chars, overlap_chars=overlap_chars)
    doc_chunks = [
        DocChunk(
            chunk_index=c.chunk_index,
            content=c.content,
            page_start=c.page_start or 1,
            page_end=c.page_end or 1,
            char_offset_start=c.char_offset_start,
            char_offset_end=c.char_offset_end,
        )
        for c in chunks
    ]
    for c in doc_chunks:
        assert contract.context[c.char_offset_start : c.char_offset_end] == c.content
    return FixtureDocument(
        filename=f"{index:04d}-{_slug(contract.contract_id)}.txt",
        normalized_content=contract.context,
        page_count=1,
        chunks=doc_chunks,
    )


# ---------------------------------------------------------------------------
# Offset-projecting FTS retriever (mirrors app/agents/tools.py:_FTS_SQL)
# ---------------------------------------------------------------------------

# Identical ranking + scoping to the production matter retriever
# (``tools.py:_FTS_SQL``: websearch_to_tsquery('english'), ts_rank_cd,
# matter-membership + owner + not-deleted, ORDER BY rank DESC, filename,
# chunk_index) — but ALSO projects the chunk's char offsets + document_id so
# retrieved spans can be scored against CUAD gold. ``test_cuad_retrieval_smoke``
# asserts this returns the same top-k as ``_FTS_SQL`` (drift guard).
_EVAL_FTS_TEMPLATE = (
    "SELECT f.filename, dc.document_id, dc.char_offset_start, dc.char_offset_end, "
    "dc.content, "
    "ts_rank_cd(dc.content_tsv, websearch_to_tsquery('english', :q)) AS rank "
    "FROM document_chunks dc "
    "JOIN documents d ON d.id = dc.document_id "
    "JOIN files f ON f.id = d.file_id "
    "LEFT JOIN project_files pf ON pf.file_id = f.id AND pf.project_id = :pid "
    "WHERE (pf.project_id IS NOT NULL OR f.project_id = :pid) "
    "AND f.owner_id = :uid "
    "AND f.deleted_at IS NULL "
    "AND dc.content_tsv @@ websearch_to_tsquery('english', :q) "
    "{doc_filter}"
    "ORDER BY rank DESC, f.filename ASC, dc.chunk_index ASC "
    "LIMIT :lim"
)


async def fts_retrieve(
    db: AsyncSession,
    binding: MatterBinding,
    query: str,
    *,
    k: int,
    document_id: uuid.UUID | None = None,
) -> list[RetrievedChunk]:
    """Run the offset-projecting matter FTS retriever; top-``k`` chunks.

    ``document_id`` scopes retrieval to one document (the within-doc arm); ``None``
    searches the whole matter (the cross-doc arm).
    """
    doc_filter = "AND dc.document_id = :doc_id " if document_id is not None else ""
    sql = text(_EVAL_FTS_TEMPLATE.format(doc_filter=doc_filter))
    params: dict[str, Any] = {
        "q": query,
        "pid": str(binding.project_id),
        "uid": str(binding.user_id),
        "lim": k,
    }
    if document_id is not None:
        params["doc_id"] = str(document_id)
    rows = (await db.execute(sql, params)).all()
    return [
        RetrievedChunk(
            filename=r.filename,
            document_id=r.document_id
            if isinstance(r.document_id, uuid.UUID)
            else uuid.UUID(str(r.document_id)),
            char_offset_start=r.char_offset_start,
            char_offset_end=r.char_offset_end,
            rank=float(r.rank),
        )
        for r in rows
    ]


async def matter_document_ids(db: AsyncSession, binding: MatterBinding) -> dict[str, uuid.UUID]:
    """Map each seeded filename -> its Document id (for gold-contract scoping)."""
    stmt = (
        select(File.filename, Document.id)
        .join(Document, Document.file_id == File.id)
        .where(
            File.project_id == binding.project_id,
            File.owner_id == binding.user_id,
            File.deleted_at.is_(None),
        )
    )
    rows = (await db.execute(stmt)).all()
    return {r.filename: r.id for r in rows}


# ---------------------------------------------------------------------------
# The baseline run
# ---------------------------------------------------------------------------


def _spans_for_scoring(
    retrieved: Sequence[RetrievedChunk], gold_document_id: uuid.UUID
) -> list[Span]:
    """Spans for the metric, with wrong-document chunks neutralised.

    Char offsets are per-document, so a chunk from another contract whose offsets
    numerically overlap a gold span must not count as a hit. Wrong-doc chunks map
    to a sentinel span disjoint from every real span, preserving the original
    cross-matter rank order for recall@k / AP.
    """
    return [
        (c.char_offset_start, c.char_offset_end) if c.document_id == gold_document_id else (-1, -1)
        for c in retrieved
    ]


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


async def run_cuad_retrieval_baseline(
    factory: async_sessionmaker[AsyncSession],
    contracts: Sequence[CuadContract],
    *,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
    run_cross_doc: bool = True,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    matter_name: str = "CUAD retrieval-eval corpus",
    gold_span_drift: int = 0,
) -> dict[str, Any]:
    """Seed the contracts into one matter, run FTS retrieval, score, clean up.

    Returns a JSON-serialisable results dict (observations only: counts +
    scores + public CUAD category/contract ids — no clause text, no secrets).
    """
    fixtures: list[FixtureDocument] = []
    contract_filename: dict[str, str] = {}
    for i, contract in enumerate(contracts):
        fixture = cuad_contract_to_fixture(
            contract, index=i, target_chars=target_chars, overlap_chars=overlap_chars
        )
        fixtures.append(fixture)
        contract_filename[contract.contract_id] = fixture.filename
    chunk_total = sum(len(f.chunks) for f in fixtures)

    seeded = await seed_multi_doc_matter(
        factory, area_key="commercial", docs=fixtures, matter_name=matter_name
    )
    binding = MatterBinding(
        project_id=seeded.project_id,
        user_id=seeded.user_id,
        name=matter_name,
        privileged=True,
        minimum_inference_tier=4,
        practice_area_id=seeded.practice_area_id,
    )
    max_k = max(k_values)

    # Accumulators: arm -> metric -> list of per-question values.
    present_recall: dict[str, dict[int, list[float]]] = {}
    present_hit: dict[str, dict[int, list[float]]] = {}
    present_precision: dict[str, dict[int, list[float]]] = {}
    present_ap: dict[str, list[float]] = {"within_doc": [], "cross_doc": []}
    # within-doc per-category recall@8 (8 == production top-k).
    per_category_recall8: dict[str, list[float]] = {}
    per_category_count: dict[str, int] = {}
    # Absent-clause control (within-doc): did FTS surface anything spurious?
    absent_spurious = 0
    absent_total = 0
    present_total = 0

    arms = ["within_doc"] + (["cross_doc"] if run_cross_doc else [])
    for arm in arms:
        present_recall[arm] = {k: [] for k in k_values}
        present_hit[arm] = {k: [] for k in k_values}
        present_precision[arm] = {k: [] for k in k_values}

    try:
        async with factory() as db:
            fn_to_docid = await matter_document_ids(db, binding)
            contract_docid = {
                cid: fn_to_docid[fn] for cid, fn in contract_filename.items() if fn in fn_to_docid
            }

            for contract in contracts:
                doc_id = contract_docid[contract.contract_id]
                for q in contract.questions:
                    within = await fts_retrieve(
                        db, binding, q.category, k=max_k, document_id=doc_id
                    )
                    cross = (
                        await fts_retrieve(db, binding, q.category, k=max_k)
                        if run_cross_doc
                        else []
                    )

                    if q.gold_spans:
                        present_total += 1
                        within_spans = [(c.char_offset_start, c.char_offset_end) for c in within]
                        cross_spans = _spans_for_scoring(cross, doc_id)
                        arm_spans = {"within_doc": within_spans, "cross_doc": cross_spans}
                        for arm in arms:
                            spans = arm_spans[arm]
                            for k in k_values:
                                present_recall[arm][k].append(recall_at_k(spans, q.gold_spans, k))
                                present_hit[arm][k].append(
                                    1.0 if any_hit_at_k(spans, q.gold_spans, k) else 0.0
                                )
                                present_precision[arm][k].append(
                                    precision_at_k(spans, q.gold_spans, k)
                                )
                            present_ap[arm].append(average_precision(spans, q.gold_spans))
                        per_category_recall8.setdefault(q.category, []).append(
                            recall_at_k(within_spans, q.gold_spans, 8)
                        )
                        per_category_count[q.category] = per_category_count.get(q.category, 0) + 1
                    else:
                        absent_total += 1
                        if within:
                            absent_spurious += 1
    finally:
        await seeded.cleanup()

    def _arm_block(arm: str) -> dict[str, Any]:
        return {
            "recall_at_k": {str(k): _mean(present_recall[arm][k]) for k in k_values},
            "hit_rate_at_k": {str(k): _mean(present_hit[arm][k]) for k in k_values},
            "precision_at_k": {str(k): _mean(present_precision[arm][k]) for k in k_values},
            "mean_average_precision": _mean(present_ap[arm]),
        }

    per_category = {
        cat: {
            "count": per_category_count[cat],
            "recall_at_8": _mean(per_category_recall8[cat]),
        }
        for cat in sorted(per_category_recall8)
    }

    return {
        "corpus": {
            "contracts": len(contracts),
            "chunks": chunk_total,
            "chunks_per_contract": round(chunk_total / len(contracts), 1) if contracts else 0,
            "present_questions": present_total,
            "absent_questions": absent_total,
            "gold_span_drift": gold_span_drift,
            "categories": len(per_category_count),
        },
        "params": {
            "k_values": list(k_values),
            "target_chars": target_chars,
            "overlap_chars": overlap_chars,
            "query": "clause category name",
            "retriever": "matter FTS (websearch_to_tsquery 'english' + ts_rank_cd), embeddings NULL",
        },
        "within_doc": _arm_block("within_doc"),
        "cross_doc": _arm_block("cross_doc") if run_cross_doc else None,
        "absent_control": {
            "absent_questions": absent_total,
            "within_doc_spurious_retrieval_rate": (
                absent_spurious / absent_total if absent_total else None
            ),
            "note": (
                "Fraction of absent-clause questions for which within-doc FTS still "
                "returned >=1 chunk. The FTS retriever cannot abstain; true "
                "abstention is an agent-mode/QA property measured in E1."
            ),
        },
        "per_category_within_doc": per_category,
    }


# ---------------------------------------------------------------------------
# Reporting (observations only — no clause text, no secrets)
# ---------------------------------------------------------------------------


def write_baseline_report(
    results: dict[str, Any],
    out_dir: Path,
    *,
    manifest: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Freeze the baseline as ``baseline.json`` + a human ``baseline.md``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"manifest": manifest or {}, "results": results}
    json_path = out_dir / "baseline.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out_dir / "baseline.md"
    md_path.write_text(_render_markdown(results, manifest or {}), encoding="utf-8")
    return json_path, md_path


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _render_markdown(results: dict[str, Any], manifest: dict[str, Any]) -> str:
    corpus = results["corpus"]
    params = results["params"]
    k_values = params["k_values"]
    lines: list[str] = []
    lines.append("# CUAD FTS-only retrieval baseline (Track B, ADR-F049 / E0)\n")
    if manifest:
        lines.append("> " + " · ".join(f"{k}: {v}" for k, v in manifest.items()) + "\n")
    lines.append(
        f"Corpus: **{corpus['contracts']} contracts**, {corpus['chunks']} chunks "
        f"(~{corpus['chunks_per_contract']}/contract), {corpus['categories']} categories. "
        f"**{corpus['present_questions']} present** + {corpus['absent_questions']} absent "
        f"questions. Gold-span drift dropped: {corpus['gold_span_drift']}.\n"
    )
    lines.append(
        f"Retriever: {params['retriever']}. Query: {params['query']}. "
        f"Chunker: target={params['target_chars']}, overlap={params['overlap_chars']}.\n"
    )

    def metric_table(title: str, key: str) -> None:
        lines.append(f"\n## {title}\n")
        header = "| arm | " + " | ".join(f"@{k}" for k in k_values) + " |"
        sep = "|" + "---|" * (len(k_values) + 1)
        lines.append(header)
        lines.append(sep)
        for arm in ("within_doc", "cross_doc"):
            block = results.get(arm)
            if not block:
                continue
            cells = " | ".join(_fmt(block[key].get(str(k))) for k in k_values)
            lines.append(f"| {arm} | {cells} |")

    metric_table("Hit rate @k (any gold span retrieved)", "hit_rate_at_k")
    metric_table("Recall @k (gold-span coverage)", "recall_at_k")
    metric_table("Precision @k", "precision_at_k")

    lines.append("\n## Mean average precision\n")
    lines.append("| arm | MAP |")
    lines.append("|---|---|")
    for arm in ("within_doc", "cross_doc"):
        block = results.get(arm)
        if block:
            lines.append(f"| {arm} | {_fmt(block['mean_average_precision'])} |")

    absent = results["absent_control"]
    lines.append("\n## Absent-clause control (within-doc)\n")
    lines.append(
        f"Spurious-retrieval rate: {_fmt(absent['within_doc_spurious_retrieval_rate'])} "
        f"over {absent['absent_questions']} absent questions. {absent['note']}\n"
    )

    lines.append("\n## Per-category recall@8 (within-doc, sorted worst→best)\n")
    lines.append("| category | n | recall@8 |")
    lines.append("|---|---|---|")
    cats = results["per_category_within_doc"]
    for cat in sorted(cats, key=lambda c: (cats[c]["recall_at_8"] is None, cats[c]["recall_at_8"])):
        row = cats[cat]
        lines.append(f"| {cat} | {row['count']} | {_fmt(row['recall_at_8'])} |")

    lines.append(
        "\n---\n*FTS-only floor — every later retrieval slice (local embeddings, "
        "rerank, PageIndex) is gated on a pre-registered delta vs these numbers "
        "(ADR-F049). Metrics are recorded findings, not pass/fail gates (ADR-F015).*\n"
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class _CuadDirResolution:
    """Result of locating the CUAD fixture (present? + the path probed)."""

    path: Path
    present: bool


def resolve_cuad_dir(env_value: str | None) -> _CuadDirResolution:
    """Resolve the CUAD dir from the env (or default) and report presence."""
    base = Path(env_value) if env_value else DEFAULT_CUAD_DIR
    json_path = base / CUAD_JSON_NAME if base.is_dir() else base
    return _CuadDirResolution(path=base, present=json_path.exists())
