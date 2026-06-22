"""Adeu redline adapter — C4 (ADR-F031): the SDK-only, in-process, zero-network
seam between the agent's proposed edits and a native tracked-changes ``.docx``.

**Import boundary (STRICT).** Only ``adeu.RedlineEngine`` / ``adeu.ModifyText`` /
``adeu.diff.generate_edits_from_text``. NEVER ``adeu.server`` /
``adeu.mcp_components`` (a second network egress) — enforced by
``tests/agents/test_redline_service.py::test_app_never_imports_adeu_server``.
Adeu makes zero provider/network calls (verified offline at C-R0), so wrapping it
in a guarded tool does not breach gateway-only egress.

**Raw ``ModifyText`` per edit — NOT decomposed (correctness over micro-surgery).**
The C-R0 §6.1 plan preferred routing each edit through
``generate_edits_from_text`` to split it into minimal regions. We tried that and
**rejected it**: decomposition produces micro-anchors (a region with
``target_text="3"``) that Adeu *fuzzy-matches to the wrong span* (observed: ``"3"``
landed on the ``d`` in "Vendor" → ``Ven12or`` — silent corruption) and bypasses the
gate's D4 unique-anchor check. Instead we send the agent's edit as ONE
``ModifyText(target_text, new_text)``: the anchor is the full, gate-validated
(unique) ``target_text``, and Adeu's prefix/suffix trim still renders it surgically
(``"three (3) months" → "twelve (12) months"`` marks only ``[-three (3)-][+twelve
(12)+]``, the rest bare). The rationale rides as the edit's Word comment.

**Stateless ⇒ provider-callable DI.** ``RedlineEngine`` is constructed
per-document (it takes the ``.docx`` ``BytesIO``), and this wrapper holds only the
author string, so there is nothing to keep as a startup singleton. It is injected
via :func:`build_redline_service` through the same provider-callable seam as
``model_builder`` / ``checkpointer_provider`` in ``composition.py`` (tests swap a
fake the same way). ``adeu`` is imported lazily inside the methods so importing
this module never pulls Adeu's heavy tree at import time.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

# Author stamped on every tracked change + comment (visible in Word's review pane).
DEFAULT_AUTHOR = "LQ.AI Commercial counsel"


@dataclass(frozen=True)
class ProposedEdit:
    """One logical edit the agent proposes (pre-decomposition)."""

    target_text: str
    new_text: str
    comment: str | None = None


@dataclass(frozen=True)
class RedlineApplyResult:
    """Outcome of a real (``dry_run=False``) apply — counts only (no clause text)."""

    docx_bytes: bytes
    edits_applied: int
    edits_skipped: int


@dataclass(frozen=True)
class RedlinePreview:
    """Outcome of a ``dry_run=True`` preview — the D6 self-review gate input."""

    edits_applied: int
    edits_skipped: int
    skipped_details: list[Any]


class RedlineService:
    """A thin, stateless adapter over the Adeu SDK (one per process is fine).

    ``dry_run`` and ``apply`` take the **logical** edits and build fresh
    ``ModifyText`` objects on every call. This is deliberate: Adeu's
    ``process_batch`` mutates the ``ModifyText`` instances it is given into a
    self-referential graph, so reusing the *same* objects for a second
    ``process_batch`` (preview→apply) deep-copies a cycle and raises
    ``RecursionError``. Building fresh per call sidesteps that entirely.
    """

    def __init__(self, *, author: str = DEFAULT_AUTHOR) -> None:
        self._author = author

    @property
    def author(self) -> str:
        return self._author

    def _build_modifytexts(self, edits: list[ProposedEdit]) -> list[Any]:
        """One raw ``ModifyText`` per logical edit (no decompose — see module
        docstring on why micro-anchors are unsafe). Fresh objects each call."""
        from adeu import ModifyText

        return [
            ModifyText(
                target_text=edit.target_text,
                new_text=edit.new_text,
                comment=edit.comment,
            )
            for edit in edits
        ]

    def dry_run(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlinePreview:
        """``process_batch(dry_run=True)`` — D6's mandatory self-review (fresh objects)."""
        from adeu import RedlineEngine

        engine = RedlineEngine(io.BytesIO(docx_bytes), author=self._author)
        result = engine.process_batch(self._build_modifytexts(edits), dry_run=True)
        applied, skipped = _counts(result)
        details = result.get("skipped_details", []) if isinstance(result, dict) else []
        return RedlinePreview(
            edits_applied=applied,
            edits_skipped=skipped,
            skipped_details=list(details) if isinstance(details, list) else [],
        )

    def apply(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlineApplyResult:
        """``process_batch(dry_run=False)`` then serialise the redlined doc (fresh objects)."""
        from adeu import RedlineEngine

        engine = RedlineEngine(io.BytesIO(docx_bytes), author=self._author)
        result = engine.process_batch(self._build_modifytexts(edits), dry_run=False)
        applied, skipped = _counts(result)
        return RedlineApplyResult(
            docx_bytes=_engine_bytes(engine),
            edits_applied=applied,
            edits_skipped=skipped,
        )

    def accept_all(self, docx_bytes: bytes) -> bytes:
        """Accept every tracked change → the clean final ``.docx`` (round-trip tests)."""
        from adeu import RedlineEngine

        engine = RedlineEngine(io.BytesIO(docx_bytes), author=self._author)
        accept = getattr(engine, "accept_all_revisions", None)
        if accept is not None:
            accept()
        return _engine_bytes(engine)


def build_redline_service() -> RedlineService:
    """Provider-callable default for ``composition.py`` (tests inject a fake)."""
    return RedlineService()


def _counts(result: Any) -> tuple[int, int]:
    """``(edits_applied, edits_skipped)`` from a ``process_batch`` dict (verified
    keys: ``edits_applied`` / ``edits_skipped`` on ``adeu==1.12.1``)."""
    if not isinstance(result, dict):
        return (0, 0)

    def _n(*keys: str) -> int:
        for k in keys:
            v = result.get(k)
            if isinstance(v, int):
                return v
            if isinstance(v, list):
                return len(v)
        return 0

    return (_n("edits_applied", "actions_applied"), _n("edits_skipped", "actions_skipped"))


def _engine_bytes(engine: Any) -> bytes:
    """Serialise the engine's document. ``save_to_stream()`` returns a ``BytesIO``
    on the pin; the fallbacks mirror the proven c4-prep recipe for resilience to a
    future Adeu bump."""
    save = getattr(engine, "save_to_stream", None)
    if save is not None:
        try:
            out = save()
        except TypeError:
            buf = io.BytesIO()
            save(buf)
            return buf.getvalue()
        if isinstance(out, (bytes, bytearray)):
            return bytes(out)
        if hasattr(out, "getvalue"):
            value = out.getvalue()
            return value if isinstance(value, bytes) else bytes(value)
        if hasattr(out, "read"):
            data = out.read()
            return data if isinstance(data, bytes) else bytes(data)
    for attr in ("get_document_bytes", "to_bytes", "get_bytes", "save_to_bytes"):
        fn = getattr(engine, attr, None)
        if fn is not None:
            b = fn()
            if isinstance(b, (bytes, bytearray)):
                return bytes(b)
            if hasattr(b, "getvalue"):
                return b.getvalue()
    for docattr in ("doc", "document", "_doc"):
        doc = getattr(engine, docattr, None)
        if doc is not None and hasattr(doc, "save"):
            buf = io.BytesIO()
            doc.save(buf)
            return buf.getvalue()
    raise RuntimeError("RedlineEngine produced no extractable .docx bytes")
