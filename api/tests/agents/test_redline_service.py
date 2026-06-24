"""C4 RedlineService + import-boundary tests (ADR-F031).

Exercises the Adeu SDK adapter on the pin (decompose → preview → apply →
accept-all) and enforces the STRICT import boundary: app code must never import
``adeu.server`` / ``adeu.mcp_components`` (a second network egress) — the C4
analogue of the C1 fitz import-guard.
"""

from __future__ import annotations

import ast
import io
import pathlib
import re

from app.agents.redline_render import reconstruct_redline_text
from app.agents.redline_service import ProposedEdit, RedlineService

CAP = (
    "The Vendor's aggregate liability arising out of or in connection with this "
    "Agreement shall not exceed the total fees paid by the Customer in the three "
    "(3) months preceding the claim."
)


def _build_docx(paragraphs: list[str]) -> bytes:
    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _docx_text(data: bytes) -> str:
    from docx import Document

    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


def _strip_markers(redline: str) -> str:
    """Drop tracked-change spans, leaving only the unchanged (bare) text."""
    no_ins = re.sub(r"\[\+.*?\+\]", "", redline, flags=re.DOTALL)
    return re.sub(r"\[-.*?-\]", "", no_ins, flags=re.DOTALL)


# --------------------------------------------------------------------------- #
# Import boundary — the load-bearing security guard
# --------------------------------------------------------------------------- #


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def test_app_never_imports_adeu_server() -> None:
    """No app module may import or reference Adeu's bundled FastMCP server
    (a second egress). Adeu is SDK-only (ADR-F031)."""
    app_dir = pathlib.Path(__file__).resolve().parents[1].parent / "app"
    banned = ("adeu.server", "adeu.mcp_components")
    offenders: list[tuple[str, str]] = []
    for py in sorted(app_dir.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == b or alias.name.startswith(b + ".") for b in banned):
                        offenders.append((py.name, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == b or node.module.startswith(b + ".") for b in banned):
                    offenders.append((py.name, node.module))
            elif isinstance(node, ast.Attribute):
                dotted = _dotted(node)
                if dotted and any(dotted == b or dotted.startswith(b + ".") for b in banned):
                    offenders.append((py.name, dotted))
    assert offenders == [], (
        "app code must not import/reference adeu.server / adeu.mcp_components — Adeu "
        f"is SDK-only (ADR-F031). Offenders: {offenders}"
    )


# --------------------------------------------------------------------------- #
# SDK adapter behaviour (needs adeu + python-docx)
# --------------------------------------------------------------------------- #


def test_raw_edit_is_surgical_and_does_not_corrupt() -> None:
    """A multi-token replace marks only the changed words; the rest of the clause
    stays bare and uncorrupted (the regression guard against the historical
    micro-anchor corruption, e.g. 'Ven12or' — ADR-F045 word-diff renders
    positionally, not by fuzzy micro-match)."""
    svc = RedlineService()
    docx = _build_docx([CAP])
    res = svc.apply(docx, [ProposedEdit("three (3) months", "twelve (12) months", None)])
    redline = reconstruct_redline_text(res.docx_bytes)
    assert "The Vendor's aggregate liability arising out of or in connection" in redline
    assert "Ven12or" not in redline and "Ven[" not in redline
    clean = _docx_text(svc.accept_all(res.docx_bytes))
    assert clean.startswith("The Vendor's aggregate liability")
    assert "twelve (12) months" in clean and "three (3) months" not in clean


def test_carveout_append_renders_surgically() -> None:
    svc = RedlineService()
    docx = _build_docx([CAP])
    res = svc.apply(
        docx,
        [
            ProposedEdit(
                "preceding the claim.",
                "preceding the claim, save that data-protection liability shall be unlimited.",
                "carve data protection out of the cap",
            )
        ],
    )
    redline = reconstruct_redline_text(res.docx_bytes)
    assert "[+" in redline  # protective language inserted
    # the clause body stays bare; only the boundary token + addition are tracked
    assert "Customer in the three (3) months preceding the" in _strip_markers(redline)
    clean = _docx_text(svc.accept_all(res.docx_bytes))
    assert "save that data-protection liability shall be unlimited" in clean


def test_preview_apply_and_accept_roundtrip() -> None:
    svc = RedlineService()
    docx = _build_docx([CAP])
    edits = [ProposedEdit("three (3) months", "twelve (12) months", "align to house floor")]

    preview = svc.dry_run(docx, edits)
    assert preview.edits_applied >= 1
    assert preview.edits_skipped == 0

    result = svc.apply(docx, edits)
    redline = reconstruct_redline_text(result.docx_bytes)
    assert "[+twelve" in redline and "[-three" in redline  # native tracked changes
    # unchanged head stays bare (surgical)
    assert "shall not exceed the total fees paid by the Customer" in redline

    clean = _docx_text(svc.accept_all(result.docx_bytes))
    assert "twelve (12) months" in clean
    assert "three (3) months" not in clean


def test_apply_skips_unanchored_edit() -> None:
    """An edit whose target isn't in the document is reported skipped, not applied."""
    svc = RedlineService()
    docx = _build_docx([CAP])
    preview = svc.dry_run(docx, [ProposedEdit("this phrase is absent here", "x y z")])
    assert preview.edits_skipped >= 1


# --------------------------------------------------------------------------- #
# Word-level diff rendering (ADR-F045) — the TOOL keeps unchanged wording bare,
# even when the model quotes a whole clause as one edit.
# --------------------------------------------------------------------------- #

# A realistic multi-paragraph contract: the indemnity is NOT at offset 0, and
# "Customer"/"Vendor" recur — so a positional misplacement would be visible.
_MSA = [
    "MASTER SERVICES AGREEMENT",
    '1. Definitions. "Customer" means the entity identified above; "Vendor" means the supplier.',
    "2. Services. The Vendor shall provide the Services to the Customer in accordance with the Order.",
    (
        "8. Indemnity. The Customer shall indemnify, defend and hold harmless the Vendor and its "
        "affiliates against any and all claims, losses, damages, liabilities and expenses arising "
        "from or in connection with the Customer use of the Services or the Customer Data."
    ),
    "9. Fees. The Customer shall pay the Vendor within thirty (30) days.",
    "10. Term. This Agreement runs for one (1) year from the Effective Date.",
]
_INDEMNITY = _MSA[3].split("Indemnity. ", 1)[1]  # the clause text after the heading
_INDEMNITY_MUTUAL = (
    "Each party shall indemnify, defend and hold harmless the other party and its "
    "affiliates against any and all claims, losses, damages, liabilities and expenses arising "
    "from or in connection with a party breach of this Agreement."
)


def _bare(redline: str) -> str:
    """The untouched (neither struck nor inserted) text of a reconstruction."""
    return _strip_markers(redline)


def test_worddiff_keeps_clause_interior_bare() -> None:
    """A whole-clause mutualisation quoted as ONE edit renders as several minimal
    regions — the indemnity verb phrase stays bare, every other paragraph intact
    (the C8/C9 swallow fix)."""
    svc = RedlineService()
    docx = _build_docx(_MSA)
    res = svc.apply(
        docx, [ProposedEdit(_INDEMNITY, _INDEMNITY_MUTUAL, "Mutualise indemnity; narrow trigger.")]
    )
    redline = reconstruct_redline_text(res.docx_bytes)
    bare = _bare(redline)

    # the recognisable boilerplate is never touched …
    assert "shall indemnify, defend and hold harmless" in bare
    assert "any and all claims, losses, damages, liabilities and expenses" in bare
    # … only the party/trigger words are struck (several regions, not one block) …
    assert redline.count("[-") >= 3
    assert "[+other party+]" in redline  # protected party mutualised
    assert re.search(r"\[\+Each", redline)  # indemnifying party mutualised
    # … no micro-anchor corruption …
    assert not re.search(r"[A-Za-z]\d[A-Za-z]", redline)
    # … and the untouched paragraphs survive verbatim.
    assert "The Vendor shall provide the Services to the Customer" in bare
    assert "within thirty (30) days" in bare
    assert "one (1) year from the Effective Date" in bare

    clean = _docx_text(svc.accept_all(res.docx_bytes))
    assert "Each party shall indemnify, defend and hold harmless the other party" in clean
    assert "The Customer shall indemnify" not in clean


def test_worddiff_multi_edit_batch_no_cross_contamination() -> None:
    """Two whole-clause edits in one batch each render surgically and land in their
    own clause (positional, full-document coordinates)."""
    svc = RedlineService()
    docx = _build_docx(_MSA)
    res = svc.apply(
        docx,
        [
            ProposedEdit(_INDEMNITY, _INDEMNITY_MUTUAL, "Mutualise indemnity."),
            ProposedEdit(
                "The Customer shall pay the Vendor within thirty (30) days.",
                "The Customer shall pay the Vendor within sixty (60) days.",
                "Extend the payment period to 60 days.",
            ),
        ],
    )
    redline = reconstruct_redline_text(res.docx_bytes)
    bare = _bare(redline)
    assert "shall indemnify, defend and hold harmless" in bare  # boilerplate bare
    assert "shall pay the Vendor within" in bare  # fee-clause stem bare
    assert "[-thirty-]" in redline and "[+sixty+]" in redline
    assert "one (1) year from the Effective Date" in bare  # term clause untouched

    clean = _docx_text(svc.accept_all(res.docx_bytes))
    assert "within sixty (60) days" in clean
    assert "Each party shall indemnify" in clean


def test_worddiff_genuine_rewrite_still_renders_as_block() -> None:
    """Word-diff does NOT fabricate surgery: a true rewrite (every word changed)
    legitimately renders as one struck-and-retyped block — so the gate, not the
    renderer, is what guards genuine over-rewording."""
    svc = RedlineService()
    docx = _build_docx(_MSA)
    res = svc.apply(
        docx,
        [
            ProposedEdit(
                "The Vendor shall provide the Services to the Customer in accordance with the Order.",
                "Supplier will deliver outputs per each statement of work executed hereunder.",
                "Full rewrite of the services clause.",
            )
        ],
    )
    redline = reconstruct_redline_text(res.docx_bytes)
    # one contiguous struck region + one inserted region (a real rewrite)
    assert redline.count("[-") == 1 and redline.count("[+") == 1
    assert not re.search(r"[A-Za-z]\d[A-Za-z]", redline)  # still no corruption


def test_worddiff_hyphenated_terms_do_not_corrupt() -> None:
    """Hyphenated/compound replacements render cleanly (the historical
    '-'/'_' mid-word-split corruption does not reproduce on the pin)."""
    svc = RedlineService()
    docx = _build_docx(_MSA)
    res = svc.apply(
        docx,
        [
            ProposedEdit(
                '"Vendor" means the supplier.',
                '"Supplier" means the service-provider.',
                "Rename the defined term and use a hyphenated description.",
            )
        ],
    )
    redline = reconstruct_redline_text(res.docx_bytes)
    assert not re.search(r"[A-Za-z]\d[A-Za-z]", redline)
    clean = _docx_text(svc.accept_all(res.docx_bytes))
    assert "the service-provider" in clean


def test_worddiff_falls_back_for_nonunique_anchor() -> None:
    """When the anchor is not uniquely locatable the edit still applies (wholesale
    fallback) rather than crashing — the gate's D4 normally forbids this, so it is
    the rare whitespace-mismatch safety net."""
    svc = RedlineService()
    # "The Customer" appears in several paragraphs → not unique → fallback path.
    docx = _build_docx(_MSA)
    preview = svc.dry_run(docx, [ProposedEdit("The Customer", "Each party")])
    assert preview.edits_applied >= 1
    assert preview.edits_skipped == 0
