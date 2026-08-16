"""Adeu redline adapter — C4 (ADR-F031, ADR-F085 two-pass native recipe,
supersedes the ADR-F045 word-diff shim): the SDK-only, in-process, zero-network
seam between the agent's proposed edits and a native tracked-changes ``.docx``.

**Import boundary (STRICT).** Only the Adeu SDK surface — ``adeu.RedlineEngine``
/ ``adeu.ModifyText`` / ``adeu.redline.engine.BatchValidationError``. NEVER
``adeu.server`` / ``adeu.mcp_components`` (a second network egress) — enforced by
``tests/agents/test_redline_service.py::test_app_never_imports_adeu_server``.
Adeu makes zero provider/network calls (verified offline at C-R0), so wrapping it
in a guarded tool does not breach gateway-only egress.

**The TOOL makes the redline surgical, not the model — via Adeu's own machinery
(the two-pass recipe, verified live on adeu==2.4.0; probe evidence in
``docs/fork/evidence/adeu2-probe/``).** Adeu ≥1.19 applies an UNCOMMENTED
``ModifyText`` with its native word-level fan-out (several minimal tracked
regions, unchanged wording bare) but deliberately keeps a COMMENTED edit as one
atomic del+ins block, so its comment can never orphan when a reviewer rejects a
fragment. Every LQ.AI edit carries a rationale comment, so we split the render:

* **Pass A — annotate, comment-only.** One batch of
  ``ModifyText(target_text, target_text, comment=rationale)`` — Adeu's
  first-class comment-only idiom — anchoring ONE comment across each logical
  edit's original span (the D4-unique anchor, so ambiguity is impossible).
* **Pass B — apply, uncommented, on a fresh engine.** One ``apply_edits`` batch
  of plain ``ModifyText(target_text, new_text)`` per logical edit. Adeu resolves
  each target itself (raw view first, clean-view fallback; text inside a pending
  tracked deletion never matches) and fans the change into minimal word-level
  regions INSIDE the comment ranges. The batch index space is 1:1 with the
  model's edit list, so failures attribute exactly; rejecting one word-region in
  review leaves the rationale intact (the comment spans the range, not one
  tracked change).

This replaces the pre-2.x shim that word-diffed the full document text and
pinned Adeu-private ``_match_start_index`` offsets: on 2.x those pins are
reinterpreted as clean-view offsets (upstream AP-05) and silently land edits in
the wrong clause on any document that already carries tracked changes — the
living-redline case (ADR-F081). The recipe carries no offsets at all.

**Failure contract.** ``validate_edits`` (public, read-only, per-edit) runs
first and turns bad anchors, ambiguity, and structural violations into
actionable per-edit messages for the MODEL (they may quote clause text — fine in
a tool result, never in logs, which carry counts/events only). Adeu 2.x's
``apply_edits`` can also RAISE ``BatchValidationError`` (e.g. a table-cell-count
mismatch) and never rolls back — so ``apply`` serialises bytes ONLY from a fully
clean render and raises :class:`RedlineRenderError` otherwise; a half-applied
engine is always discarded, never persisted.

**Stateless ⇒ provider-callable DI.** ``RedlineEngine`` is constructed
per-document (it takes the ``.docx`` ``BytesIO``), and this wrapper holds only
the author string, so there is nothing to keep as a startup singleton. It is
injected via :func:`build_redline_service` through the same provider-callable
seam as ``model_builder`` / ``checkpointer_provider`` in ``composition.py``
(tests swap a fake the same way). ``adeu`` is imported lazily inside the
functions so importing this module never pulls Adeu's heavy tree at import time.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from typing import Any

from lxml import etree

logger = logging.getLogger(__name__)

# Author stamped on every tracked change + comment (visible in Word's review pane).
DEFAULT_AUTHOR = "LQ.AI Commercial counsel"

# The OOXML settings part + the WordprocessingML namespace (ECMA-376 §17).
_SETTINGS_PART = "word/settings.xml"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_W_NS}}}"
# CT_Settings (§17.15.1.78) is an ORDERED sequence; ``trackChanges`` (§17.15.1.93)
# sits late in it. These local-names all come AFTER ``trackChanges``, so inserting the
# new element before the first one present keeps the sequence schema-valid (a superset
# is safe — we insert before the earliest later element).
_AFTER_TRACK_CHANGES = frozenset(
    {
        "doNotTrackMoves",
        "doNotTrackFormatting",
        "documentProtection",
        "autoFormatOverride",
        "styleLockTheme",
        "styleLockQFSet",
        "defaultTabStop",
        "autoHyphenation",
        "consecutiveHyphenLimit",
        "hyphenationZone",
        "doNotHyphenateCaps",
        "characterSpacingControl",
        "savePreviewPicture",
        "doNotValidateAgainstSchema",
        "saveInvalidXml",
        "ignoreMixedContent",
        "alwaysShowPlaceholderText",
        "updateFields",
        "hdrShapeDefaults",
        "footnotePr",
        "endnotePr",
        "compat",
        "rsids",
        "mathPr",
        "themeFontLang",
        "clrSchemeMapping",
        "shapeDefaults",
        "decimalSymbol",
        "listSeparator",
    }
)
# Hardened parser — settings.xml is derived from an (already guard_ooxml'd) upload, but
# parse it with entity resolution + network access OFF as defense in depth (no XXE).
_SETTINGS_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)


def ensure_track_changes_recording(docx_bytes: bytes) -> bytes:
    """Force document-wide "Record Changes" ON in a redline's ``settings.xml`` so a
    supervising lawyer's edits in the in-app editor are captured as TRACKED changes
    (ADR-F047 Slice 5). Adeu emits tracked *content* (``w:ins``/``w:del``) but not the
    ``<w:trackChanges/>`` recording flag (re-verified on 2.4.0), so without this the
    editor opens with recording OFF and the lawyer's edits would be untracked —
    invisible to ``review_edited_document``.

    Three cases: no ``trackChanges`` element → insert one (schema-ordered); an explicit
    OFF (``w:val`` in {false, 0, off}, as Word writes when a user toggles tracking off) →
    flip it ON by dropping the ``w:val`` (a bare element defaults ON); already ON → no-op.

    Surgical + safe: rewrite ONLY ``settings.xml`` (every other part byte-identical),
    and graceful — any failure returns the original bytes, so the redline still ships and
    the hand-back simply degrades to the clean view."""
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zin:
            names = zin.namelist()
            if _SETTINGS_PART not in names:
                return docx_bytes
            entries = [(name, zin.read(name)) for name in names]
        settings = next(d for n, d in entries if n == _SETTINGS_PART)
        root = etree.fromstring(settings, _SETTINGS_PARSER)
        existing = root.find(f"{_W}trackChanges")
        if existing is not None:
            val = existing.get(f"{_W}val")
            if val is None or val.lower() not in ("false", "0", "off"):
                return docx_bytes  # already recording → byte-identical no-op
            del existing.attrib[f"{_W}val"]  # explicit OFF → flip ON (bare element = on)
        else:
            el = root.makeelement(f"{_W}trackChanges", {})
            insert_at = len(root)
            for i, child in enumerate(root):
                if etree.QName(child).localname in _AFTER_TRACK_CHANGES:
                    insert_at = i
                    break
            root.insert(insert_at, el)
        new_settings = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in entries:
                zout.writestr(name, new_settings if name == _SETTINGS_PART else data)
        return out.getvalue()
    except Exception:
        logger.warning(
            "could not force track-changes recording on the redline",
            extra={"event": "redline_trackchanges_force_failed"},
        )
        return docx_bytes


@dataclass(frozen=True)
class ProposedEdit:
    """One logical edit the agent proposes (pre-decomposition)."""

    target_text: str
    new_text: str
    comment: str | None = None


@dataclass(frozen=True)
class RenderOutcome:
    """Counts + per-edit problems from one two-pass render on an engine.

    ``edits_applied``/``edits_skipped`` count LOGICAL edits (Adeu ≥2.x aggregates
    its internal word-level fan-out back to one count per edit). ``problems``
    carries the per-edit failure messages for the MODEL — they may quote clause
    text (Adeu's own reports are designed to feed LLM context), so they belong in
    the tool result, never in structured logs."""

    edits_applied: int
    edits_skipped: int
    comments_applied: int
    comments_skipped: int
    problems: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.problems and self.edits_skipped == 0 and self.comments_skipped == 0


class RedlineRenderError(Exception):
    """A render could not complete cleanly — the engine may be half-applied and
    MUST be discarded (Adeu's ``apply_edits`` never rolls back). ``problems``
    carries the per-edit reasons for the model."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("; ".join(problems) or "redline render failed")
        self.problems = problems


@dataclass(frozen=True)
class RedlineApplyResult:
    """Outcome of a real apply — bytes are present ONLY for a fully clean render
    (:meth:`RedlineService.apply` raises :class:`RedlineRenderError` otherwise,
    so ``edits_skipped`` is always 0 on a constructed instance; kept for shape
    stability with :class:`RedlinePreview`)."""

    docx_bytes: bytes
    edits_applied: int
    edits_skipped: int
    comments_applied: int = 0


@dataclass(frozen=True)
class RedlinePreview:
    """Outcome of the D6 dry-run self-review — the gate input.

    Counts per LOGICAL edit; ``problems`` carries the per-edit messages destined
    for the tool result (clause text allowed there; logs get counts only)."""

    edits_applied: int
    edits_skipped: int
    comments_applied: int = 0
    comments_skipped: int = 0
    problems: tuple[str, ...] = ()


def _skipped_details(engine: Any) -> list[str]:
    """The engine's per-edit skip messages (each pass runs on a virgin engine,
    so the whole list belongs to that pass's single ``apply_edits`` call)."""
    details = getattr(engine, "skipped_details", None) or []
    return [str(d) for d in details]


def render_edits(
    docx_bytes: bytes,
    edits: list[ProposedEdit],
    *,
    author: str = DEFAULT_AUTHOR,
    validate: bool = True,
) -> tuple[RenderOutcome, bytes]:
    """The two-pass recipe (shared by the C4 redline service and the C5a
    negotiation counter path). Returns ``(outcome, rendered_bytes)`` — the bytes
    are meaningful ONLY when ``outcome.clean``.

    **One fresh engine per pass, serialising between them.** An Adeu engine
    caches its document mappers and only ``process_batch`` refreshes them between
    sequential ``apply_edits`` calls — a second call on the same engine resolves
    against PRE-mutation offsets and silently mis-places edits (verified on
    2.4.0: empty deletions + insertions landing before untouched text). Within a
    single call the engine pre-resolves every edit against the initial state by
    design, so each pass being one call on a virgin engine removes the staleness
    class entirely, at the cost of one extra serialize+parse.

    Pass A anchors each rationale as a comment-only edit
    (``target == target_text``) on the ORIGINAL document — the D4-unique anchor,
    so comment ambiguity is impossible. Pass B re-opens the annotated output and
    applies all edits UNCOMMENTED — Adeu's native word-level fan-out (commented
    edits would render as one atomic block) — inside the comment ranges.
    Rejecting a single word-region in review cannot orphan the rationale.

    ``validate=True`` runs Adeu's public, read-only ``validate_edits`` per edit
    first and rejects the whole batch (all-or-nothing, matching the D6 gate) with
    per-edit messages on any finding — including strict-mode ambiguity, which
    ``apply_edits`` alone would silently resolve to the first match. Negotiation
    counters pass ``validate=False``: countering deliberately edits the
    counterparty's own pending insertions, which validate flags as foreign-author
    overlap; that path keeps its own reconciliation net instead.

    Never raises Adeu errors: ``BatchValidationError`` (Adeu 2.x apply raises it
    for e.g. table-structure violations and does NOT roll back) is folded into
    ``problems`` — a non-clean outcome means "discard the bytes"."""
    from adeu import ModifyText, RedlineEngine
    from adeu.redline.engine import BatchValidationError

    problems: list[str] = []
    engine = RedlineEngine(io.BytesIO(docx_bytes), author=author)

    if validate:
        for i, edit in enumerate(edits):
            try:
                msgs = engine.validate_edits(
                    [ModifyText(target_text=edit.target_text, new_text=edit.new_text)],
                    index_offset=i,
                )
            except Exception as exc:  # e.g. a regex time-budget failure — per-edit, not fatal
                msgs = [f"- Edit {i + 1} Failed: {type(exc).__name__}: {exc}"]
            problems.extend(str(m) for m in msgs)
        if problems:
            return RenderOutcome(0, len(edits), 0, 0, tuple(problems)), docx_bytes

    # Pass A — annotate FIRST on the original bytes: a comment-only edit
    # anchored on the edit's target_text, which the D4 gate has already proven
    # unique — comment-anchor ambiguity is impossible by construction.
    # (Anchoring on new_text AFTER the apply was tried and rejected: a short or
    # repeated new_text is ambiguous in the updated document, skipping the
    # comment with a rejection the model cannot fix by rephrasing.) The range
    # wraps the original span; pass B's tracked regions land inside it, so
    # accept-all leaves the comment on the new wording and rejecting the edit
    # leaves the rationale attached to the restored text.
    commented = [e for e in edits if e.comment]
    comments_applied = comments_skipped = 0
    rendered = docx_bytes
    if commented:
        try:
            comments_applied, comments_skipped = engine.apply_edits(
                [
                    ModifyText(target_text=e.target_text, new_text=e.target_text, comment=e.comment)
                    for e in commented
                ]
            )
        except BatchValidationError as exc:
            return (
                RenderOutcome(0, len(edits), 0, len(commented), tuple(str(e) for e in exc.errors)),
                docx_bytes,
            )
        if comments_skipped:
            problems.extend(_skipped_details(engine))
        rendered = _engine_bytes(engine)

    # Pass B — apply, uncommented (native surgical word-level fan-out), on a
    # FRESH engine over the annotated bytes. The comment bubbles break raw-view
    # contiguity, so resolution lands via the engine's clean-view fallback —
    # which is comment-free.
    applier = RedlineEngine(io.BytesIO(rendered), author=author) if commented else engine
    try:
        applied, skipped = applier.apply_edits(
            [ModifyText(target_text=e.target_text, new_text=e.new_text) for e in edits]
        )
    except BatchValidationError as exc:
        return (
            RenderOutcome(
                0,
                len(edits),
                comments_applied,
                comments_skipped,
                tuple(problems) + tuple(str(e) for e in exc.errors),
            ),
            docx_bytes,
        )
    if skipped:
        problems.extend(_skipped_details(applier))
    rendered = _engine_bytes(applier)

    outcome = RenderOutcome(applied, skipped, comments_applied, comments_skipped, tuple(problems))
    return outcome, rendered


class RedlineService:
    """A thin, stateless adapter over the Adeu SDK (one per process is fine).

    ``dry_run`` and ``apply`` each build a fresh ``RedlineEngine`` and fresh
    ``ModifyText`` objects on every call — Adeu's apply path mutates the edit
    instances it is given, so nothing is ever reused across calls, and a failed
    render's engine is simply dropped (Adeu 2.x ``apply_edits`` never rolls
    back)."""

    def __init__(self, *, author: str = DEFAULT_AUTHOR) -> None:
        self._author = author

    @property
    def author(self) -> str:
        return self._author

    def dry_run(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlinePreview:
        """D6's mandatory self-review — the two-pass recipe on throwaway engines,
        saving nothing. Problems are the per-edit messages for the model."""
        out, _rendered = render_edits(docx_bytes, edits, author=self._author, validate=True)
        return RedlinePreview(
            edits_applied=out.edits_applied,
            edits_skipped=out.edits_skipped,
            comments_applied=out.comments_applied,
            comments_skipped=out.comments_skipped,
            problems=out.problems,
        )

    def apply(self, docx_bytes: bytes, edits: list[ProposedEdit]) -> RedlineApplyResult:
        """Render for real. Returns bytes ONLY from a fully clean render —
        anything less raises :class:`RedlineRenderError` (a half-applied render
        is discarded, never persisted)."""
        out, rendered = render_edits(docx_bytes, edits, author=self._author, validate=True)
        if not out.clean:
            raise RedlineRenderError(
                out.problems
                or (f"{out.edits_skipped} edit(s) and {out.comments_skipped} comment(s) skipped",)
            )
        return RedlineApplyResult(
            # Force "Record Changes" ON so the lawyer's later edits in the editor are
            # captured as tracked changes (ADR-F047 Slice 5 hand-back) — Adeu emits the
            # tracked content but not the recording flag.
            docx_bytes=ensure_track_changes_recording(rendered),
            edits_applied=out.edits_applied,
            edits_skipped=out.edits_skipped,
            comments_applied=out.comments_applied,
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


def _engine_bytes(engine: Any) -> bytes:
    """Serialise the engine's document via ``save_to_stream()`` (returns a
    ``BytesIO`` on 2.4.0, verified — the pre-2.x defensive attr sweep was dead on
    every pin it shipped with and is gone)."""
    save = getattr(engine, "save_to_stream", None)
    if save is not None:
        out = save()
        if isinstance(out, (bytes, bytearray)):
            return bytes(out)
        if hasattr(out, "getvalue"):
            value = out.getvalue()
            return value if isinstance(value, bytes) else bytes(value)
        if hasattr(out, "read"):
            data = out.read()
            return data if isinstance(data, bytes) else bytes(data)
    raise RuntimeError("RedlineEngine produced no extractable .docx bytes")
