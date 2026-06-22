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
    """A multi-token replace marks only the changed span; the rest of the document
    stays byte-intact (the regression guard against decompose's micro-anchor
    corruption, e.g. 'Ven12or')."""
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
