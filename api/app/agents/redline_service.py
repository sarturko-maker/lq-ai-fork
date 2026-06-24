"""Adeu redline adapter — C4 (ADR-F031/F045): the SDK-only, in-process,
zero-network seam between the agent's proposed edits and a native tracked-changes
``.docx``.

**Import boundary (STRICT).** Only ``adeu.RedlineEngine`` / ``adeu.ModifyText`` /
``adeu.diff.generate_edits_from_text``. NEVER ``adeu.server`` /
``adeu.mcp_components`` (a second network egress) — enforced by
``tests/agents/test_redline_service.py::test_app_never_imports_adeu_server``.
Adeu makes zero provider/network calls (verified offline at C-R0), so wrapping it
in a guarded tool does not breach gateway-only egress.

**The TOOL makes the redline surgical, not the model (ADR-F045).** Each logical
edit the model proposes is ``(target_text, new_text)`` — a whole-clause find/replace
where ``new_text`` repeats the unchanged wording verbatim and changes only the words
that need changing. We render it surgically by routing it through Adeu's **native
word-level diff**, ``adeu.diff.generate_edits_from_text(original, modified)``:

* We diff the **full document text** against the document with this one edit applied
  (``full_text.replace(target_text, new_text)``), so the ``ModifyText`` sub-edits
  Adeu returns carry ``_match_start_index`` offsets in **full-document coordinates**
  (correct positioning — the canonical pattern in ``adeu.sanitize.core``).
* We apply the sub-edits with ``engine.apply_edits(...)`` **directly** — not
  ``process_batch`` — because ``process_batch`` re-validates each sub-edit's
  ``target_text`` for uniqueness and would reject a short region (``"the Customer"``
  appears many times); ``apply_edits`` trusts the positional index instead.

This keeps recognisable boilerplate **bare**: a one-sided indemnity mutualisation
renders as ``[-The Customer-][+Each party+] shall indemnify, defend and hold harmless
the [-Vendor-][+other party+] …`` — three minimal regions, the verb phrase untouched —
instead of one struck-and-retyped block. A *genuine* rewrite (every word changed)
still renders as one block, which is correct; the surgical gate (``app.schemas.commercial``)
still guards genuine over-rewording on the minimal token diff.

The earlier "raw ``ModifyText`` per edit, no decompose" approach (rejected at C-R0
for ``generate_edits_from_text`` micro-anchor corruption, e.g. ``"3"`` → ``Ven12or``)
relied on Adeu's prefix/suffix trim, which **swallows unchanged interiors** (the C8/C9
indemnity/grant-clause failure). That corruption does not reproduce on the pin
(``adeu==1.12.1``): the native diff anchors positionally, not by fuzzy micro-match.
When the model's ``target_text`` is **not** uniquely locatable in the engine's text
(a whitespace-normalisation edge case — the gate's D4 already requires uniqueness in
the document text), that edit falls back to a single wholesale ``ModifyText`` (no
worse than the prior behaviour).

**Stateless ⇒ provider-callable DI.** ``RedlineEngine`` is constructed
per-document (it takes the ``.docx`` ``BytesIO``), and this wrapper holds only the
author string, so there is nothing to keep as a startup singleton. It is injected
via :func:`build_redline_service` through the same provider-callable seam as
``model_builder`` / ``checkpointer_provider`` in ``composition.py`` (tests swap a
fake the same way). ``adeu`` is imported lazily inside the methods so importing
this module never pulls Adeu's heavy tree at import time. Each call builds a fresh
``RedlineEngine`` and fresh sub-edits (``generate_edits_from_text`` returns new
objects), so the ``process_batch`` mutation-cycle ``RecursionError`` from reusing
edit objects across calls cannot arise.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

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
    """Outcome of a ``dry_run=True`` preview — the D6 self-review gate input.

    Counts only: the tool gates on ``edits_applied``/``edits_skipped`` and never
    surfaces per-edit detail (Adeu's ``skipped_details`` carries ``target_text``
    snippets — clause text — so it is deliberately not captured here)."""

    edits_applied: int
    edits_skipped: int


class RedlineService:
    """A thin, stateless adapter over the Adeu SDK (one per process is fine).

    ``dry_run`` and ``apply`` each build a fresh ``RedlineEngine`` and fresh
    ``ModifyText`` sub-edits (``generate_edits_from_text`` returns new objects)
    on every call. This is deliberate: Adeu's apply path mutates the edit
    instances it is given into a self-referential graph, so reusing the *same*
    objects for a second apply (preview→apply) would deep-copy a cycle and raise
    ``RecursionError``. Building fresh per call sidesteps that entirely.
    """

    def __init__(self, *, author: str = DEFAULT_AUTHOR) -> None:
        self._author = author

    @property
    def author(self) -> str:
        return self._author

    def _word_diff_edits(self, engine: Any, edits: list[ProposedEdit]) -> list[Any]:
        """Instance shim onto :func:`word_diff_edits` (kept for call-site stability)."""
        return word_diff_edits(engine, edits)

    def dry_run(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlinePreview:
        """D6's mandatory self-review — render on a throwaway engine, save nothing.

        Uses ``apply_edits`` (not ``process_batch``) so the word-diff sub-edits are
        placed positionally without ``process_batch``'s per-sub-edit uniqueness
        re-validation. Counts are **tracked-change regions** (one logical edit may
        produce several); the tool only needs ``applied > 0`` / ``skipped == 0``.
        """
        from adeu import RedlineEngine

        engine = RedlineEngine(io.BytesIO(docx_bytes), author=self._author)
        applied, skipped = engine.apply_edits(self._word_diff_edits(engine, edits))
        return RedlinePreview(edits_applied=applied, edits_skipped=skipped)

    def apply(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlineApplyResult:
        """Render the word-diff sub-edits for real, then serialise the redlined doc."""
        from adeu import RedlineEngine

        engine = RedlineEngine(io.BytesIO(docx_bytes), author=self._author)
        applied, skipped = engine.apply_edits(self._word_diff_edits(engine, edits))
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


def word_diff_edits(engine: Any, edits: list[ProposedEdit]) -> list[Any]:
    """Expand each logical edit into positioned ``ModifyText`` sub-edits via Adeu's
    native word-level diff, in **full-document coordinates** (ADR-F045).

    For each ``(target_text, new_text)``: when ``target_text`` occurs exactly once in
    the engine's text, diff ``full`` against ``full`` with this one edit applied —
    ``generate_edits_from_text`` then returns sub-edits whose ``_match_start_index`` is
    an offset into the full document, so ``apply_edits`` places each changed word region
    exactly (unchanged wording stays bare). The edit's rationale rides as the Word
    comment on the first sub-edit (one comment per logical edit, not per region).

    Fallback: when ``target_text`` is not uniquely locatable in the engine's text (a
    rare whitespace-normalisation mismatch — the gate's D4 already requires uniqueness
    in the document text), emit a single wholesale ``ModifyText`` for that edit;
    ``apply_edits`` resolves it heuristically (prefix/suffix trim — no worse than the
    prior behaviour).

    Module-level so both :class:`RedlineService` (C4 redline) and the C5a negotiation
    adapter can render a counter surgically on the **same** engine. Fresh objects every
    call (see :class:`RedlineService` docstring on the reuse cycle).
    """
    from adeu import ModifyText
    from adeu.diff import generate_edits_from_text

    full = engine.mapper.full_text
    if not full:
        engine.mapper._build_map()
        full = engine.mapper.full_text

    out: list[Any] = []
    fallbacks = 0
    for edit in edits:
        if full and full.count(edit.target_text) == 1:
            modified = full.replace(edit.target_text, edit.new_text)
            sub_edits = generate_edits_from_text(full, modified)
            if sub_edits:
                for i, sub in enumerate(sub_edits):
                    # apply_edits trusts _match_start_index positionally; set
                    # _resolved_start_idx to the same to skip re-resolution.
                    sub._resolved_start_idx = sub._match_start_index
                    sub.comment = edit.comment if i == 0 else None
                out.extend(sub_edits)
                continue
        # Fallback (non-unique anchor, or a diff that produced no sub-edits).
        fallbacks += 1
        out.append(
            ModifyText(
                target_text=edit.target_text,
                new_text=edit.new_text,
                comment=edit.comment,
            )
        )
    if fallbacks:
        # Counts only (no clause text) — keeps the audit/log contract.
        logger.info(
            "redline word-diff fell back to wholesale for %d/%d edit(s)",
            fallbacks,
            len(edits),
            extra={"event": "redline_worddiff_fallback"},
        )
    return out


def build_redline_service() -> RedlineService:
    """Provider-callable default for ``composition.py`` (tests inject a fake)."""
    return RedlineService()


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
