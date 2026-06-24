"""Commercial redline schemas + the measurable surgical gate — C4 (ADR-F031).

The Commercial Deep Agent's ``apply_redline`` tool is a **code-validated write**
(ADR-F018): the model PROPOSES a batch of narrow find/replace edits, code
DISPOSES against a measurable *surgical* gate, then Adeu renders the surviving
edits as native tracked changes. This module is the **model-free** half of that
loop — the Pydantic ``*Input`` schemas (mirroring ``app.schemas.ropa``) plus the
D1-D6 gate from the C-R0 doctrine (``commercial-lawyer-method.md`` §6.2). It
imports nothing from the agent/runtime layers and touches no I/O, so every rule
is unit-testable with no model and no document store.

The gate splits by what each rule can see:

* **Per-edit, document-free** (in the ``*Input`` validators): D2 (a substantive
  edit needs a rationale) and D3 (a bare substantive deletion must supply
  replacement language — the asking-party-drafts rule). Computable from
  ``target_text``/``new_text``/``rationale`` alone.
* **Document-relative** (in :func:`evaluate_gate`, called by the tool once the
  matter ``.docx`` text is in hand): D1 (tiered change size, ``ratio =
  changed_tokens / clause_tokens``), D4 (unique anchor — ``target_text`` matches
  exactly one span), D5 (whole-batch ceiling). D6 (mandatory ``dry_run`` before
  any write) is enforced by the tool's call sequence, not here.

"Surgical" is measured on the **minimal token diff** of ``target_text`` vs
``new_text`` (§6.1), not raw span lengths — a one-word swap expressed over a long
matched sentence has a tiny real change. Reject, never sanitize (ADR-F018): a
failing proposal comes back with the reason so the model can fix and re-propose.

ALL numeric thresholds are **calibration starting values** (C-R0 §11), named at
module level so calibration against the golden-redline corpus is a one-line edit.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# --------------------------------------------------------------------------- #
# Gate thresholds — CALIBRATION STARTING VALUES (C-R0 §6.2/§11), not sourced.
# Calibrate against the golden-redline corpus before merge.
# --------------------------------------------------------------------------- #
SURGICAL_MAX = 0.15  # D1: ratio ≤ this (or changed ≤ ABS_FLOOR) → auto-allow
ABS_FLOOR = 3  # D1: changed_tokens ≤ this → auto-allow regardless of ratio
REWRITE_MAX = 0.50  # D1: ratio > this → BLOCK unless rewrite_justified + reason
MINOR_FLOOR = 0.05  # D2: ratio > this ⇒ substantive (rationale required)
RATIONALE_MIN_WORDS = 15  # D2: min non-placeholder words in a substantive rationale
DOC_CEILING = 0.25  # D5: Σ changed / total doc tokens > this → over-redline escalate
MAX_EDITS_PER_BATCH = 50  # sane batch cap (a deal redline is dozens, not thousands)

# D2 substantive-token set (§6.2): modal verbs, negations, and (heuristically)
# numbers / percentages / currency / periods / defined-terms. An edit that adds
# or removes any of these is substantive and must carry a rationale. The
# defined-term / party-name heuristic (Capitalised or ALL-CAPS tokens) errs
# toward REQUIRING a rationale — a safe direction (asking the agent to explain),
# never toward silently allowing. Finer counterparty-interest / defined-term
# classification is the model-in-the-loop layer (§6.3), out of this pure gate.
_MODAL_NEGATION = frozenset({"shall", "must", "may", "will", "not", "no", "none", "nor"})
_PERIOD_WORDS = frozenset(
    {
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
        "quarter",
        "quarters",
        "annum",
        "business",
    }
)
_CURRENCY = ("%", "$", "£", "€")
_DEFINED_TERM = re.compile(r"^(?:[A-Z][a-z]{2,}|[A-Z]{2,})$")
_WORD = re.compile(r"\S+")
# Sentence/clause boundary terminators for the smallest-enclosing-clause span.
_CLAUSE_BOUNDARY = re.compile(r"[.;:!?\n]")
_PLACEHOLDER = re.compile(r"^(?:please\s+revise|tbd|fix|n/?a|todo|\W*)$", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    """Whitespace-delimited tokens — deterministic, model-free."""
    return _WORD.findall(text)


def _strip_token(tok: str) -> str:
    """A token with surrounding punctuation stripped, for substantive testing."""
    return tok.strip(".,;:!?()[]{}\"'`")


def is_substantive_token(tok: str) -> bool:
    """True if a single token carries legal weight (§6.2 substantive set)."""
    bare = _strip_token(tok)
    if not bare:
        return False
    if bare.lower() in _MODAL_NEGATION:
        return True
    if bare.lower() in _PERIOD_WORDS:
        return True
    if any(sym in bare for sym in _CURRENCY):
        return True
    if any(ch.isdigit() for ch in bare):
        return True
    return bool(_DEFINED_TERM.match(bare))


def _diff_opcodes(target: str, new: str) -> Sequence[tuple[str, int, int, int, int]]:
    return SequenceMatcher(a=_tokens(target), b=_tokens(new), autojunk=False).get_opcodes()


def deleted_tokens(target: str, new: str) -> int:
    """Tokens STRUCK from the existing text (replace + delete, a-side).

    This is the load-bearing surgical metric (refines C-R0 §6.1): "surgical"
    is about how much of the EXISTING clause you strike, not how much you add.
    Striking large swaths of existing language is the "redline the whole
    sentence" anti-pattern; *adding* protective language (a carve-out, a
    super-cap — the §5.1 doctrine) is inherently surgical and is governed by the
    rationale requirement (D2) + the substantive judge, not by this ratio.
    """
    return sum(
        (i2 - i1)
        for op, i1, i2, j1, j2 in _diff_opcodes(target, new)
        if op in ("replace", "delete")
    )


def inserted_tokens(target: str, new: str) -> int:
    """Tokens ADDED to the text (replace + insert, b-side)."""
    return sum(
        (j2 - j1)
        for op, i1, i2, j1, j2 in _diff_opcodes(target, new)
        if op in ("replace", "insert")
    )


def changed_tokens(target: str, new: str) -> int:
    """Total minimal-diff size (struck + added) — used for the ABS_FLOOR
    tiny-edit auto-allow and the no-op guard; the *ratio* gate keys on
    :func:`deleted_tokens` (struck text), not this total."""
    return deleted_tokens(target, new) + inserted_tokens(target, new)


def is_substantive_change(target: str, new: str) -> bool:
    """True if any added/removed token in the minimal diff is substantive."""
    a, b = _tokens(target), _tokens(new)
    for op, i1, i2, j1, j2 in _diff_opcodes(target, new):
        if op == "equal":
            continue
        if any(is_substantive_token(t) for t in a[i1:i2]):
            return True
        if any(is_substantive_token(t) for t in b[j1:j2]):
            return True
    return False


def _rationale_word_count(rationale: str) -> int:
    """Non-placeholder word count — a 'please revise' filler scores 0."""
    if _PLACEHOLDER.match(rationale.strip()):
        return 0
    return len(_tokens(rationale))


def count_occurrences(document_text: str, target: str) -> int:
    """How many times ``target`` appears in the document (D4 unique-anchor).

    Whitespace-normalised on both sides so a quote that differs only in run/
    line wrapping still anchors; this mirrors how Adeu locates the span.
    """
    doc = re.sub(r"\s+", " ", document_text)
    needle = re.sub(r"\s+", " ", target).strip()
    if not needle:
        return 0
    return doc.count(needle)


def clause_token_count(document_text: str, target: str) -> int | None:
    """Token count of ``target``'s smallest enclosing clause/sentence.

    Returns ``None`` (fail-closed, route to human — §6.4) when the span is
    unresolvable: the target is not found, appears more than once, or itself
    straddles a clause boundary (so "the clause" is ambiguous).
    """
    doc = re.sub(r"\s+", " ", document_text)
    needle = re.sub(r"\s+", " ", target).strip()
    if not needle or doc.count(needle) != 1:
        return None
    start = doc.index(needle)
    end = start + len(needle)
    # A boundary INSIDE the matched span (not at its very end) → straddle.
    interior = doc[start : end - 1]
    if _CLAUSE_BOUNDARY.search(interior):
        return None
    left = max((m.end() for m in _CLAUSE_BOUNDARY.finditer(doc, 0, start)), default=0)
    # Search from end-1 so a target that ENDS at the clause's terminator (".") is
    # bounded by that terminator, not the next clause's (which would inflate the
    # clause and deflate the strike ratio).
    right_match = _CLAUSE_BOUNDARY.search(doc, end - 1)
    right = right_match.start() if right_match else len(doc)
    clause = doc[left:right].strip()
    count = len(_tokens(clause))
    return count or None


# --------------------------------------------------------------------------- #
# Input schemas (the per-edit, document-free gate: D2 + D3)
# --------------------------------------------------------------------------- #


class RedlineEditInput(BaseModel):
    """One proposed find/replace edit. Reject, don't sanitize (ADR-F018).

    ``target_text`` is the exact existing text to change (the unique anchor);
    ``new_text`` is the replacement (empty ⇒ a pure deletion). ``rationale`` is
    the lawyer's reason for a substantive change (rendered as a Word comment).
    ``rewrite_justified`` is the explicit override the agent must set to clear
    D1's hard ceiling for a genuinely necessary full-clause rewrite.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_text: str
    new_text: str = ""
    rationale: str = ""
    rewrite_justified: bool = False

    @field_validator("target_text")
    @classmethod
    def _target_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("target_text must be the exact existing text to change (non-blank)")
        return v

    @model_validator(mode="after")
    def _surgical_per_edit(self) -> Self:
        if changed_tokens(self.target_text, self.new_text) == 0:
            raise ValueError("edit makes no change — target_text and new_text are identical")
        substantive = is_substantive_change(self.target_text, self.new_text)
        bare_deletion = not self.new_text.strip()
        # D3: a bare deletion of substantive text must supply replacement
        # language — never delete-and-leave-a-gap (asking-party-drafts, §5).
        if bare_deletion and substantive:
            raise ValueError(
                "D3: a bare deletion of substantive text must supply replacement "
                "language in new_text (don't delete-and-leave-a-gap — you propose "
                "the redrafted text)"
            )
        # D2: every substantive edit needs a real rationale.
        if substantive and _rationale_word_count(self.rationale) < RATIONALE_MIN_WORDS:
            raise ValueError(
                f"D2: this is a substantive edit (it changes a modal/negation, a "
                f"number/amount/period, or a defined term) — supply a rationale of "
                f"≥{RATIONALE_MIN_WORDS} words explaining the change and why it "
                f"protects the client"
            )
        return self


class ApplyRedlineInput(BaseModel):
    """A batch of narrow edits against one matter document."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_name: str
    edits: list[RedlineEditInput]

    @field_validator("document_name")
    @classmethod
    def _doc_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("document_name must name a document attached to this matter")
        return v

    @field_validator("edits")
    @classmethod
    def _edits_bounded(cls, v: list[RedlineEditInput]) -> list[RedlineEditInput]:
        if not v:
            raise ValueError("propose at least one edit")
        if len(v) > MAX_EDITS_PER_BATCH:
            raise ValueError(
                f"too many edits in one batch ({len(v)} > {MAX_EDITS_PER_BATCH}); "
                f"split into focused passes"
            )
        return v


# --------------------------------------------------------------------------- #
# Document-relative gate (D1 / D4 / D5) — runs once the .docx text is in hand
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EditVerdict:
    """Per-edit gate outcome — counts/types only, no raw clause text in audit."""

    index: int
    ok: bool
    reasons: list[str]
    deleted_tokens: int  # existing text struck (the surgical metric)
    changed_tokens: int  # struck + added (for ABS_FLOOR / reporting)
    clause_tokens: int | None
    ratio: float | None  # strike_ratio = deleted_tokens / clause_tokens
    substantive: bool
    occurrences: int


@dataclass(frozen=True)
class GateReport:
    """Whole-batch gate outcome."""

    ok: bool
    edits: list[EditVerdict]
    batch_reasons: list[str] = field(default_factory=list)
    doc_struck_ratio: float | None = None

    def rejection_text(self) -> str:
        """A fix-and-retry message (reasons only; never echoes clause text)."""
        lines: list[str] = []
        for v in self.edits:
            if not v.ok:
                lines.append(f"- edit #{v.index + 1}: " + "; ".join(v.reasons))
        for r in self.batch_reasons:
            lines.append(f"- batch: {r}")
        return (
            "Redline rejected by the surgical gate — nothing was written. Fix the "
            "following and call apply_redline again:\n" + "\n".join(lines)
        )


def _evaluate_edit(index: int, edit: RedlineEditInput, document_text: str) -> EditVerdict:
    reasons: list[str] = []
    occ = count_occurrences(document_text, edit.target_text)
    struck = deleted_tokens(edit.target_text, edit.new_text)
    changed = changed_tokens(edit.target_text, edit.new_text)
    clause_tk = clause_token_count(document_text, edit.target_text)
    # The surgical ratio is how much of the EXISTING clause is struck.
    ratio = (struck / clause_tk) if clause_tk else None
    substantive = is_substantive_change(edit.target_text, edit.new_text) or (
        ratio is not None and ratio > MINOR_FLOOR
    )

    # D4: unique anchor (silent-corruption guard for any find/replace tool).
    if occ != 1:
        reasons.append(
            f"D4: target_text matches {occ} spans in the document — it must match "
            f"exactly one; quote a longer, unique anchor"
        )

    # Fail-closed when the enclosing clause is unresolvable (§6.4).
    if clause_tk is None:
        reasons.append(
            "D1: could not resolve the enclosing clause (target not unique or it "
            "straddles a sentence boundary) — tighten target_text to one clause"
        )
    else:
        # D1: tiered STRIKE size — a pure insertion (struck 0) is always surgical.
        assert ratio is not None
        if ratio <= SURGICAL_MAX or changed <= ABS_FLOOR:
            pass  # surgical — auto-allow
        elif ratio <= REWRITE_MAX:
            if _rationale_word_count(edit.rationale) < RATIONALE_MIN_WORDS:
                reasons.append(
                    f"D1: this strikes {ratio:.0%} of the existing clause "
                    f"(> {SURGICAL_MAX:.0%}) — allowed only with a "
                    f"≥{RATIONALE_MIN_WORDS}-word rationale"
                )
        else:  # ratio > REWRITE_MAX
            if not (edit.rewrite_justified and _rationale_word_count(edit.rationale) >= 1):
                reasons.append(
                    f"D1: this strikes {ratio:.0%} of the existing clause "
                    f"(> {REWRITE_MAX:.0%}) — a full rewrite. Prefer a surgical "
                    f"carve-out/requalification that ADDS protection; if a rewrite is "
                    f"genuinely necessary set rewrite_justified=true and give the reason"
                )

    # D2 (ratio-substantive branch): a large change with no substantive token
    # still needs a rationale.
    if substantive and _rationale_word_count(edit.rationale) < RATIONALE_MIN_WORDS:
        reasons.append(f"D2: substantive edit needs a ≥{RATIONALE_MIN_WORDS}-word rationale")

    return EditVerdict(
        index=index,
        ok=not reasons,
        reasons=reasons,
        deleted_tokens=struck,
        changed_tokens=changed,
        clause_tokens=clause_tk,
        ratio=ratio,
        substantive=substantive,
        occurrences=occ,
    )


def evaluate_gate(document_text: str, edits: list[RedlineEditInput]) -> GateReport:
    """Run the document-relative gate (D1/D4/D5) over a validated batch.

    ``edits`` have already passed the per-edit ``*Input`` validators (D2/D3);
    this adds the rules that need the document. Returns a structured report —
    the tool turns ``not ok`` into a rejection and never reaches Adeu.
    """
    verdicts = [_evaluate_edit(i, e, document_text) for i, e in enumerate(edits)]
    batch_reasons: list[str] = []

    total_doc_tokens = len(_tokens(document_text))
    sum_struck = sum(v.deleted_tokens for v in verdicts)
    # D5 keys on STRUCK text (gutting the document), not additions — a heavy but
    # additive carve-out batch is not "over-redlining".
    doc_ratio = (sum_struck / total_doc_tokens) if total_doc_tokens else None
    if doc_ratio is not None and doc_ratio > DOC_CEILING:
        batch_reasons.append(
            f"D5: this batch strikes {doc_ratio:.0%} of the document "
            f"(> {DOC_CEILING:.0%}) — that is gutting it, not redlining; narrow to "
            f"the material clauses or escalate to the supervisor"
        )

    ok = all(v.ok for v in verdicts) and not batch_reasons
    return GateReport(
        ok=ok, edits=verdicts, batch_reasons=batch_reasons, doc_struck_ratio=doc_ratio
    )


# --------------------------------------------------------------------------- #
# C5a — negotiation rounds: counterparty-position decisions + the COVERAGE gate
# (ADR-F032). The model reads the counterparty's tracked changes + comments (the
# StateOfPlay, enumerated by ``negotiation_service.read_state_of_play``) and emits
# one decision per item; this model-free layer enforces the **no-silent-action**
# guarantee — exactly one decision per change/comment ref, nothing omitted — before
# the agent layer touches Adeu. Counter edits are gated by the same D1-D6 surgical
# gate above (the tool builds a ``RedlineEditInput`` and calls ``evaluate_gate``).
# --------------------------------------------------------------------------- #

# Closed action taxonomy (the Adeu-1.12.1 review-action surface + two recorded-only
# verdicts). A counterparty CHANGE can be accepted, rejected, countered (a layered
# surgical edit), left open, or escalated; a COMMENT can be replied to, left open, or
# escalated. "leave_open"/"escalate" make no document mutation — their receipt is the
# audit row + the matter-memory fact at the tool layer (they are still *recorded*
# decisions, so the item is never silently dropped).
CHANGE_VERDICTS = frozenset({"accept", "reject", "counter", "leave_open", "escalate"})
COMMENT_VERDICTS = frozenset({"reply", "leave_open", "escalate"})
REASON_VERDICTS = frozenset({"reject", "counter", "leave_open", "escalate"})

# Ref grammar: a logical change is "C<n>" (document order); a comment is its native
# Adeu "Com:<n>" id (so a reply targets it directly).
_CHANGE_REF = re.compile(r"^C\d+$")
_COMMENT_REF = re.compile(r"^Com:\d+$")
MAX_DECISIONS_PER_BATCH = 200  # a round addresses dozens-to-low-hundreds of items


class CounterpartyDecision(BaseModel):
    """The agent's verdict on one counterparty change or comment. Reject, don't
    sanitize (ADR-F018) — a malformed decision comes back for the model to fix."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ref: str  # "C<n>" (a change) or "Com:<n>" (a comment)
    verdict: str
    target_text: str = ""  # counter: the exact existing text to change (unique anchor)
    new_text: str = ""  # counter: the replacement
    rationale: str = ""  # counter/reject/leave_open/escalate: the recorded reason
    reply_text: str = ""  # reply: the threaded reply body

    @model_validator(mode="after")
    def _shape(self) -> Self:
        is_change = bool(_CHANGE_REF.match(self.ref))
        is_comment = bool(_COMMENT_REF.match(self.ref))
        if not (is_change or is_comment):
            raise ValueError(f"ref {self.ref!r} must be a change 'C<n>' or a comment 'Com:<n>'")
        if is_change and self.verdict not in CHANGE_VERDICTS:
            raise ValueError(f"change {self.ref}: verdict must be one of {sorted(CHANGE_VERDICTS)}")
        if is_comment and self.verdict not in COMMENT_VERDICTS:
            raise ValueError(
                f"comment {self.ref}: verdict must be one of {sorted(COMMENT_VERDICTS)} "
                f"(a comment can't be accepted/rejected/countered — reply, leave_open, or escalate)"
            )
        if self.verdict == "counter" and (
            not self.target_text.strip() or not self.new_text.strip()
        ):
            raise ValueError(
                f"{self.ref}: a counter must supply both target_text (the existing "
                f"wording to change) and new_text (your replacement)"
            )
        if self.verdict == "reply" and not self.reply_text.strip():
            raise ValueError(f"{self.ref}: a reply must supply reply_text")
        if self.verdict in REASON_VERDICTS and not self.rationale.strip():
            raise ValueError(
                f"{self.ref}: a {self.verdict} must supply a rationale (the recorded reason)"
            )
        return self


class RespondToCounterpartyInput(BaseModel):
    """A full round's response — one decision per counterparty change and comment."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_name: str
    decisions: list[CounterpartyDecision]

    @field_validator("document_name")
    @classmethod
    def _doc_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("document_name must name the counterparty's marked-up document")
        return v

    @field_validator("decisions")
    @classmethod
    def _decisions_bounded(cls, v: list[CounterpartyDecision]) -> list[CounterpartyDecision]:
        if not v:
            raise ValueError("respond to at least one item")
        if len(v) > MAX_DECISIONS_PER_BATCH:
            raise ValueError(
                f"too many decisions ({len(v)} > {MAX_DECISIONS_PER_BATCH}) in one call"
            )
        return v


@dataclass(frozen=True)
class CoverageReport:
    """The no-silent-action gate outcome — counts/refs only (no clause text)."""

    ok: bool
    missing: list[str] = field(default_factory=list)  # refs with no decision
    unknown: list[str] = field(default_factory=list)  # decisions for a non-existent ref
    duplicate: list[str] = field(default_factory=list)  # refs decided more than once

    def rejection_text(self) -> str:
        lines: list[str] = []
        if self.missing:
            lines.append(
                "- UNADDRESSED (every counterparty change/comment must get exactly one "
                f"decision — nothing silent): {', '.join(sorted(self.missing))}"
            )
        if self.unknown:
            lines.append(
                f"- unknown ref(s) (not in this document): {', '.join(sorted(self.unknown))}"
            )
        if self.duplicate:
            lines.append(f"- decided more than once: {', '.join(sorted(self.duplicate))}")
        return (
            "Response rejected — nothing was written. Every counterparty change and "
            "comment must be addressed exactly once. Fix the following and call "
            "respond_to_counterparty again:\n" + "\n".join(lines)
        )


def evaluate_coverage(
    change_refs: set[str],
    comment_refs: set[str],
    decisions: list[CounterpartyDecision],
) -> CoverageReport:
    """The completeness gate: exactly one decision per known ref, none missing, none
    unknown, none duplicated. Collect-all-errors (the model fixes in one pass)."""
    required = set(change_refs) | set(comment_refs)
    seen: dict[str, int] = {}
    for d in decisions:
        seen[d.ref] = seen.get(d.ref, 0) + 1
    decided = set(seen)
    missing = sorted(required - decided)
    unknown = sorted(decided - required)
    duplicate = sorted(r for r, n in seen.items() if n > 1)
    return CoverageReport(
        ok=not (missing or unknown or duplicate),
        missing=missing,
        unknown=unknown,
        duplicate=duplicate,
    )


@dataclass(frozen=True)
class AnchorReport:
    """The comment-wipe gate outcome — refs only, never clause text (ADR-F018).

    A reply written under a comment anchored to a tracked change is DELETED by Adeu when
    that change is accepted or rejected (the accept/reject resolves the thread, taking our
    reply with it — verified live). So a ``reply`` must not co-occur with ``accept``/
    ``reject`` on its anchored change, or the reply silently vanishes from the delivered
    document. A ``counter`` (layers a new edit, leaves the original change + its comment
    thread intact) and ``leave_open`` (writes nothing) are safe."""

    ok: bool
    # (comment_ref, change_ref, change_verdict) per reply that would be wiped
    wiped: list[tuple[str, str, str]] = field(default_factory=list)

    def rejection_text(self) -> str:
        lines = [
            f"- {com} (your reply) is anchored to {chg}, which you set to '{verdict}' — Word "
            f"deletes the comment thread (and your reply) when an anchored change is "
            f"accepted or rejected, so your reply would silently vanish."
            for com, chg, verdict in sorted(self.wiped)
        ]
        return (
            "Response rejected — nothing was written. A comment reply cannot survive on a "
            "change you accept or reject. For each item below, either counter the change "
            "instead (a counter layers a new edit and keeps the original change + its "
            "comment thread, so your reply survives), or leave_open the comment instead of "
            "replying (a recorded decision that writes nothing). Then call "
            "respond_to_counterparty again:\n" + "\n".join(lines)
        )


# A reply cannot survive these verdicts on its anchored change (the thread is deleted).
_WIPING_CHANGE_VERDICTS = frozenset({"accept", "reject"})


def evaluate_anchoring(
    comment_anchors: dict[str, str],
    decisions: list[CounterpartyDecision],
) -> AnchorReport:
    """The comment-wipe gate: a ``reply`` cannot survive accept/reject of the change its
    comment is anchored to. Collect-all-errors (the model fixes in one pass). Assumes
    coverage already holds (exactly one decision per ref)."""
    verdict_by_ref = {d.ref: d.verdict for d in decisions}
    wiped: list[tuple[str, str, str]] = []
    for d in decisions:
        if d.verdict != "reply":
            continue
        change_ref = comment_anchors.get(d.ref)
        if change_ref is None:
            continue  # anchored to plain text / standalone — wipe-safe
        chg_verdict = verdict_by_ref.get(change_ref)
        if chg_verdict in _WIPING_CHANGE_VERDICTS:
            wiped.append((d.ref, change_ref, chg_verdict))
    return AnchorReport(ok=not wiped, wiped=wiped)
