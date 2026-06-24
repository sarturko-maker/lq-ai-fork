"""Adeu negotiation adapter — C5a (ADR-F032): the SDK-only seam for the *second
round* of a deal, where the counterparty returns a marked-up ``.docx``.

Two halves:

* :func:`read_state_of_play` — read the counterparty's tracked changes + Word
  comments into a :class:`StateOfPlay` (a flat, document-order checklist of every
  ``Chg`` region and every ``Com`` thread, each with a stable in-read ref). This is
  the **coverage checklist** the response must cover exactly.
* :func:`apply_decisions` — apply the agent's per-ref decisions (accept / reject /
  counter / reply) as native tracked changes + threaded comments on one engine, then
  **reconcile**: prove every decision landed (``applied`` with no ``skipped``) and the
  output re-reads cleanly. ``leave_open`` / ``escalate`` are recorded decisions with no
  document mutation (their receipt is the audit + matter-memory fact at the tool layer).

**The no-silent-action guarantee** is two-phase and lives in *code*, not the prompt:
the tool layer's coverage gate requires exactly one decision per ref (a silent omission
fails), and :class:`Reconciliation` here proves each decision provably took effect
(silent-accept can't happen — no decision is a failure; silent-reject can't happen — a
reject is a recorded ``RejectChange``). The agent reasons; code disposes (ADR-F018).

The guarantee holds at the **document** level too, not just the decision level (C5b-1):
the reconciliation re-reads the output and proves every reply we made still survives.
Adeu *deletes* the comment thread anchored to a change when that change is accepted or
rejected (it reports the action as ``applied`` — count-based checks miss the loss), so a
reply placed on such a change would silently vanish. Two layers close this: the tool's
upfront ``evaluate_anchoring`` gate keeps a reply off an accept/reject change
(``StateOfPlay.comment_anchors`` is the anchor map), and the reply-survival check here is
the backstop. ``leave_open`` / ``escalate`` make no document mutation.

**Import boundary (STRICT).** Only ``adeu`` SDK surface — ``RedlineEngine``,
``extract_text_from_stream``, ``adeu.models`` review actions, and the engine's
``comments_manager``. NEVER ``adeu.server`` / ``adeu.mcp_components`` (enforced by
``tests/agents/test_redline_service.py``). Adeu makes zero network calls.

**Adeu facts this adapter relies on** (verified live on the pin ``adeu==1.12.1``):
``extract_text_from_stream(stream, clean_view=False)`` renders CriticMarkup —
``{--del--}{++ins++}{>>[Chg:N delete] Author⏎[Chg:N insert] Author⏎[Com:N] …<<}`` — so a
single logical *modify* is a ``del``+``ins`` pair with two ``Chg`` ids; accept/reject of
that change acts on **both** ids. ``apply_review_actions`` accepts only
``AcceptChange`` / ``RejectChange`` / ``ReplyComment`` and returns ``(applied, skipped)``
with failures in ``engine.skipped_details``. Replies are applied **before** accepts/rejects
(an accept/reject of a change deletes the comment thread anchored to it — including any
reply on it). ``comments_manager.extract_comments_data()`` keys comments by RAW, unprefixed
ids (``"1"``) for both the id and ``parent_id``; there is no public API to place a comment
on a text range with no edit (so a reply cannot be re-homed off a wiped change — verified
on the pin, ``add_comment(author, text, parent_id=None)`` has no range anchor).
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.redline_service import (
    DEFAULT_AUTHOR,
    ProposedEdit,
    _engine_bytes,
    word_diff_edits,
)

logger = logging.getLogger(__name__)

# Closed action taxonomy + ref grammar live in ``app.schemas.commercial`` (the
# model-free layer the tool validates against); this adapter trusts already-validated
# :class:`Decision`s. Refs: a logical change is "C1".."Cn" in document order; a comment
# keeps its native Adeu "Com:N" id (so a ``ReplyComment`` targets it directly).

# CriticMarkup region: optional deletion + optional insertion, then a {>>meta<<} block.
_REGION = re.compile(
    r"(?:\{--(?P<del>.*?)--\})?(?:\{\+\+(?P<ins>.*?)\+\+\})?\{>>(?P<meta>.*?)<<\}",
    re.DOTALL,
)
_CHG_LINE = re.compile(r"\[Chg:(\d+)\s+(delete|insert|format)\]\s*(.*)")
# A comment anchored to a change shares the change's {>>…<<} meta block (verified live):
# `[Chg:3 delete] … [Chg:4 insert] … [Com:1] …`. So a `[Com:N]` co-occurring with a
# `[Chg:…]` line marks Com:N as anchored to that region's logical change.
_COM_LINE = re.compile(r"\[Com:(\d+)\]")

# Bounds: keep the model-facing projection and the stored context snippets small.
_CONTEXT_PAD = 90
_MAX_SNIPPET = 240


@dataclass(frozen=True)
class TrackedChange:
    """One logical counterparty change (a del+ins modify, or a pure insert/delete)."""

    ref: str  # "C1".. — stable within one read (document order)
    kind: str  # "modify" | "insert" | "delete" | "format"
    deleted_text: str
    inserted_text: str
    author: str
    context: str  # surrounding clause text (markers stripped), bounded
    adeu_ids: tuple[str, ...]  # ("Chg:5", "Chg:6") — what the review actions consume


@dataclass(frozen=True)
class CounterpartyComment:
    ref: str  # "Com:N"
    author: str
    text: str
    resolved: bool
    parent_id: str | None  # None = a thread root (the unit that needs a reply)
    is_ours: bool  # authored by us (a prior round's reply) — not part of the checklist


@dataclass(frozen=True)
class StateOfPlay:
    changes: list[TrackedChange]
    comments: list[CounterpartyComment]
    clean_view: str  # the counterparty's accept-all "final ask" (bounded, model-facing)
    marked_view: str  # the full CriticMarkup (bounded, model-facing)
    clean_text_full: str  # the UNTRUNCATED accept-all text — for the counter gate (D4/D5)
    # "Com:N" -> "Cn": a comment anchored to a tracked change. Accepting/rejecting that
    # change deletes the anchored thread (incl. a reply), so a reply here can't survive an
    # accept/reject of its change (the comment-wipe gate keys on this — C5b-1). A comment
    # absent from this map is anchored to plain text and is wipe-safe.
    comment_anchors: dict[str, str] = field(default_factory=dict)

    @property
    def change_refs(self) -> set[str]:
        return {c.ref for c in self.changes}

    @property
    def open_comment_refs(self) -> set[str]:
        """Counterparty thread-root comments still OPEN — each needs a decision.

        Excludes our own prior-round replies (``is_ours``) and threads the counterparty
        already marked resolved (no need to force a reply on a closed thread)."""
        return {
            c.ref for c in self.comments if c.parent_id is None and not c.is_ours and not c.resolved
        }


@dataclass(frozen=True)
class Decision:
    """A validated per-ref decision handed to :func:`apply_decisions`."""

    ref: str
    verdict: str
    target_text: str = ""  # counter
    new_text: str = ""  # counter
    rationale: str = ""  # counter / reject / leave_open / escalate
    reply_text: str = ""  # reply


@dataclass(frozen=True)
class Reconciliation:
    ok: bool
    review_applied: int
    review_skipped: int
    counters_applied: int
    counters_skipped: int
    issues: tuple[str, ...] = field(default_factory=tuple)


def _strip_markup(text: str) -> str:
    """Render CriticMarkup as plain accepted-all-ish text for a context snippet.

    Robust to *windowed* input (a slice may start/end mid-marker): orphaned partial
    meta blocks from the window edges are trimmed first.
    """
    text = re.sub(r"^[^{]*?<<\}", "", text)  # leading orphaned meta-close
    text = re.sub(r"\{>>[^}]*$", "", text)  # trailing orphaned meta-open
    text = re.sub(r"\{>>.*?<<\}", "", text, flags=re.DOTALL)  # whole meta blocks
    text = re.sub(r"\{--(.*?)--\}", "", text, flags=re.DOTALL)  # drop deletions
    text = re.sub(r"\{\+\+(.*?)\+\+\}", r"\1", text, flags=re.DOTALL)  # keep insertions
    text = re.sub(r"\{==(.*?)==\}", r"\1", text, flags=re.DOTALL)  # unwrap format/comment
    text = re.sub(r"[{}]", "", text)  # any residual partial braces from windowing
    return re.sub(r"\s+", " ", text).strip()


def _bounded(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def read_state_of_play(docx_bytes: bytes, *, our_author: str = DEFAULT_AUTHOR) -> StateOfPlay:
    """Parse the counterparty's tracked changes + comments into the coverage checklist.

    Changes come from the CriticMarkup regions (Adeu's ``Chg`` ids); comments come
    structurally from ``engine.comments_manager.extract_comments_data()`` (id → author,
    text, date, resolved, parent_id). A comment authored by ``our_author`` (a prior
    round's reply) is flagged ``is_ours`` and excluded from the checklist.
    """
    from adeu import RedlineEngine, extract_text_from_stream

    marked = extract_text_from_stream(
        io.BytesIO(docx_bytes), filename="counterparty.docx", clean_view=False
    )
    clean = extract_text_from_stream(
        io.BytesIO(docx_bytes), filename="counterparty.docx", clean_view=True
    )

    changes: list[TrackedChange] = []
    comment_anchors: dict[str, str] = {}
    n = 0
    for m in _REGION.finditer(marked):
        meta = m.group("meta") or ""
        chg = _CHG_LINE.findall(meta)
        if not chg:
            continue  # a comment-only region (no tracked change) — handled below
        n += 1
        ids = tuple(f"Chg:{cid}" for cid, _typ, _auth in chg)
        # Any comment in this same meta block is anchored to this logical change (Cn).
        for com_cid in _COM_LINE.findall(meta):
            comment_anchors[f"Com:{com_cid}"] = f"C{n}"
        types = {typ for _cid, typ, _auth in chg}
        author = next((auth.strip() for _cid, _typ, auth in chg if auth.strip()), "unknown")
        deleted = (m.group("del") or "").strip()
        inserted = (m.group("ins") or "").strip()
        if "format" in types and not deleted and not inserted:
            kind = "format"
        elif deleted and inserted:
            kind = "modify"
        elif inserted:
            kind = "insert"
        else:
            kind = "delete"
        start, end = m.span()
        context = _strip_markup(
            marked[max(0, start - _CONTEXT_PAD) : min(len(marked), end + _CONTEXT_PAD)]
        )
        changes.append(
            TrackedChange(
                ref=f"C{n}",
                kind=kind,
                deleted_text=_bounded(deleted, _MAX_SNIPPET),
                inserted_text=_bounded(inserted, _MAX_SNIPPET),
                author=author,
                context=_bounded(context, _MAX_SNIPPET),
                adeu_ids=ids,
            )
        )

    comments: list[CounterpartyComment] = []
    engine = RedlineEngine(io.BytesIO(docx_bytes), author=our_author)
    raw = engine.comments_manager.extract_comments_data() or {}
    for cid, data in raw.items():
        author = str(data.get("author", "unknown"))
        comments.append(
            CounterpartyComment(
                ref=f"Com:{cid}",
                author=author,
                text=_bounded(str(data.get("text", "")), _MAX_SNIPPET),
                resolved=bool(data.get("resolved", False)),
                parent_id=data.get("parent_id"),
                is_ours=author == our_author,
            )
        )

    return StateOfPlay(
        changes=changes,
        comments=comments,
        clean_view=_bounded(clean, 8000),
        marked_view=_bounded(marked, 12000),
        clean_text_full=clean,  # untruncated — the counter gate (D4 anchor / D5 ratio) keys on this
        comment_anchors=comment_anchors,
    )


def apply_decisions(
    docx_bytes: bytes,
    state: StateOfPlay,
    decisions: list[Decision],
    *,
    our_author: str = DEFAULT_AUTHOR,
) -> tuple[bytes, Reconciliation]:
    """Apply the validated decisions on one engine and reconcile.

    Order matters (verified live): apply **replies first**, then **rejects**, then
    **accepts** (an accept on a region unanchors a reply sitting on it; accepts/rejects
    are sorted by descending ``Chg`` id so an earlier accept doesn't renumber a
    not-yet-processed id). Counters are surgical ``ModifyText`` edits via the shared
    word-diff, applied last. Then re-read the output to confirm every action landed.

    Returns ``(output_bytes, reconciliation)``. The caller persists ``output_bytes``
    **only if** ``reconciliation.ok``.
    """
    from adeu import RedlineEngine
    from adeu.models import AcceptChange, RejectChange, ReplyComment

    by_change = {c.ref: c for c in state.changes}
    issues: list[str] = []

    replies: list[Any] = []
    rejects: list[tuple[int, Any]] = []
    accepts: list[tuple[int, Any]] = []
    counters: list[ProposedEdit] = []
    # RAW comment ids ("1", not "Com:1") we reply to — the survival check matches these
    # against extract_comments_data's raw parent_id. split(":")[-1] is robust to a ref that
    # is already raw (a hand-built Decision), so a malformed reply ref fails the check
    # (persist nothing) rather than crashing.
    intended_reply_raw_ids: set[str] = set()

    def _chg_sort_key(adeu_id: str) -> int:
        try:
            return int(adeu_id.split(":", 1)[1])
        except (IndexError, ValueError):
            return 0

    for d in decisions:
        if d.verdict == "reply":
            replies.append(ReplyComment(target_id=d.ref, text=d.reply_text))
            intended_reply_raw_ids.add(d.ref.split(":", 1)[-1])
        elif d.verdict in ("accept", "reject"):
            change = by_change.get(d.ref)
            if change is None:
                issues.append(f"{d.ref}: no such change at apply time")
                continue
            for adeu_id in change.adeu_ids:
                key = _chg_sort_key(adeu_id)
                if d.verdict == "accept":
                    accepts.append((key, AcceptChange(target_id=adeu_id)))
                else:
                    rejects.append((key, RejectChange(target_id=adeu_id)))
        elif d.verdict == "counter":
            counters.append(
                ProposedEdit(
                    target_text=d.target_text, new_text=d.new_text, comment=d.rationale or None
                )
            )
        # leave_open / escalate: recorded by the tool layer; no document mutation.

    # Descending Chg id so an accept/reject doesn't renumber a not-yet-applied id.
    rejects.sort(key=lambda t: t[0], reverse=True)
    accepts.sort(key=lambda t: t[0], reverse=True)
    review_actions = replies + [a for _k, a in rejects] + [a for _k, a in accepts]

    engine = RedlineEngine(io.BytesIO(docx_bytes), author=our_author)

    review_applied = review_skipped = 0
    if review_actions:
        review_applied, review_skipped = engine.apply_review_actions(review_actions)
        if review_skipped:
            details = getattr(engine, "skipped_details", []) or []
            issues.append(f"{review_skipped} review action(s) skipped: {len(details)} detail(s)")

    counters_applied = counters_skipped = 0
    if counters:
        sub_edits = word_diff_edits(engine, counters)
        counters_applied, counters_skipped = engine.apply_edits(sub_edits)
        if counters_skipped:
            issues.append(f"{counters_skipped} counter sub-edit(s) skipped")
        if counters_applied < len(counters):
            issues.append(
                f"counter under-applied: {counters_applied} region(s) for {len(counters)} counter(s)"
            )

    out_bytes = _engine_bytes(engine)

    # Post-write reconciliation, two proofs (C5b-1):
    #  1) the output must re-read cleanly (corruption guard);
    #  2) every reply we made must STILL be present in the output. Adeu's
    #     (applied, skipped) above only says an action was *attempted* successfully —
    #     but accepting/rejecting a change DELETES the comment thread anchored to it,
    #     wiping any reply we placed there (verified live: applied=3/skipped=0, yet the
    #     reply is gone). The upfront anchoring gate keeps a reply off an accept/reject
    #     change, so a reply that is nonetheless absent here is a real, otherwise-silent
    #     document-level loss → fail and persist nothing. We assert survival ONLY for the
    #     replies we made, so a thread that legitimately vanished (its change accepted,
    #     no reply) is never checked — no false-fail (the bug the old code avoided).
    try:
        out_state = read_state_of_play(out_bytes, our_author=our_author)
    except Exception as exc:  # pragma: no cover - corrupt output is itself a failure
        issues.append(f"output failed to re-read: {type(exc).__name__}")
    else:
        if intended_reply_raw_ids:
            # extract_comments_data keys (and parent_id) are RAW, unprefixed ids; our
            # reply is a comment authored by us whose parent is the thread we replied to.
            surviving = {
                str(cm.parent_id)
                for cm in out_state.comments
                if cm.is_ours and cm.parent_id is not None
            }
            wiped = intended_reply_raw_ids - surviving
            if wiped:
                issues.append(
                    f"{len(wiped)} comment repl(y/ies) did not survive in the output "
                    "(an anchored change was accepted/rejected)"
                )

    return out_bytes, Reconciliation(
        ok=not issues,
        review_applied=review_applied,
        review_skipped=review_skipped,
        counters_applied=counters_applied,
        counters_skipped=counters_skipped,
        issues=tuple(issues),
    )
