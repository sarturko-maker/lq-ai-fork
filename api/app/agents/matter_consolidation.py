"""Matter-memory consolidation/Lint — C3b-2 (fork, ADR-F043): the egress slice.

The third matter-memory agent surface, and the **first that calls a model**. Where
C3a's ``update_matter_memory`` keeps the prose wiki and C3b-1's ``record_matter_fact``
records dated facts (both zero model calls), this module's ONE tool —
:func:`consolidate_matter_memory` — runs an **in-run, gateway-routed** consolidation/Lint
pass over the matter's live fact ledger + wiki: it loads them whole (no embeddings — the
gateway ``/v1/embeddings`` is 501 until B6), routes a mem0-style extract→judge +
Karpathy/OpenClaw Lint through the **Inference Gateway** (the ADR-F010 egress obligation
lands here — every model call through ``GatewayClient``; no direct provider), then applies
the proposal **supersede-only** (close a stale/duplicate/contradicted fact's window;
never delete, never edit a fact body in place) and **rewrites the wiki**.

Decisions (ADR-F043, maintainer-chosen):

* **Facts + wiki** — the pass consolidates the ledger AND rewrites the one-pager.
* **Supersede-only** — a corrected statement is a NEW superseding fact (``replace``),
  not an in-place edit, so the bi-temporal "what did we believe at signing" history
  stays intact.
* **Cost = match the R4-no-op posture + gateway audit** — exactly ONE gateway call per
  invocation + a hard ``max_tokens`` cap; the spend is recorded in the gateway
  routing-log under ``lq_ai_purpose="consolidate_matter_memory"``. Per-run $ budgets are
  F1's job (R4 is a documented no-op for every agent tool today).

**Structural guarantees (the isolated egress review's core).** Pinned corrections are
passed to the model as *read-only ground truth* and are **never** in the op space: the
apply step validates that every op id is a **live ``kind='fact'`` row of THIS matter**
before any write, so a correction id (or a hallucinated / cross-matter / already-superseded
id) is unreachable — no-fabrication + no-overwrite (B2) both hold structurally. Untrusted
model output is code-validated (``ConsolidationResult``) and a second pure pass checks the
ids BEFORE mutating; the apply is **all-or-nothing** (any reject ⇒ zero writes). A gateway
failure becomes a reject-and-retry string, never a crash. The tool's only model access is
the injected ``GatewayClient`` (no provider SDK, no ``api.openai.com``).

**Area-agnostic** (every practice area's matter); the grant set is DISJOINT from the
matter-memory wiki / fact-ledger grants and the ROPA/assessment/commercial domain grants.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.matter_fact_tools import live_facts
from app.agents.matter_memory_tools import (
    format_corrections_block,
    load_pinned_corrections,
    snapshot_and_rewrite_wiki,
)
from app.agents.tools import MatterBinding
from app.clients.gateway import GatewayClient, get_gateway_client
from app.models.project import MatterMemoryEntry, Project
from app.schemas.gateway import ChatCompletionMessage, ChatCompletionRequest
from app.schemas.matter_memory import ConsolidationResult

logger = logging.getLogger(__name__)

MATTER_CONSOLIDATION_TOOL_NAMES = frozenset({"consolidate_matter_memory"})

# The default gateway alias for the consolidation judgement. "smart" is the top
# qualified tier (the deep-agent loop's alias); on the dev stack the smart/fast/budget
# aliases are repointed to DeepSeek (HANDOFF). Override per-deployment / per-scenario
# with LQ_AI_MATTER_CONSOLIDATION_MODEL.
_DEFAULT_CONSOLIDATION_MODEL = "smart"
# Output bound (the "structural" half of the cost posture): one call, capped tokens.
# The rewritten wiki can approach the 16 KiB budget (~5k tokens) plus the ops batch.
_CONSOLIDATION_MAX_TOKENS = 8_000

_SYSTEM_PROMPT = (
    "You are a careful keeper of a legal matter's working memory. You are given the "
    "matter's CURRENT fact ledger (individual dated facts), its working wiki (a brief "
    "one-pager), and the supervising lawyer's pinned corrections (ground truth). Your "
    "job is to CONSOLIDATE the memory: remove duplication, resolve contradictions, "
    "retire stale facts, and produce a clean rewritten wiki — without losing real "
    "information and without ever contradicting a pinned correction.\n\n"
    "Rules:\n"
    "- NEVER contradict, modify, retire, or reference a pinned correction. The pinned "
    "corrections are ground truth set by the supervising lawyer; keep the wiki "
    "consistent with them.\n"
    "- You may change facts in only two ways:\n"
    '  - "retire" a fact (give its id) — when it is stale, an orphan, the loser of a '
    "contradiction, OR a redundant DUPLICATE. To dedupe two facts that say the same "
    "thing, retire the redundant copy/copies and KEEP the single clearest one — this "
    "is the simplest and preferred way to remove duplication.\n"
    '  - "replace" one or more facts (give their ids in "supersedes") with ONE new '
    "consolidated fact — to merge genuinely-different facts into one statement, or to "
    "record a fact whose VALUE CHANGED. Give the new fact's text, its fact_type (one "
    "of: party, term, date, decision, open_point, fact), and an optional source. Set "
    '"valid_from" ONLY when the new value became true on a specific LATER date than '
    "the fact(s) it supersedes (e.g. a liability cap renegotiated on 2026-05-01) — it "
    "MUST be later than those facts' dates. OMIT valid_from for a merge with no date "
    "change (the consolidated fact is recorded as of now). When unsure, prefer retire.\n"
    "- Do NOT list a fact you are keeping unchanged — facts you do not mention are "
    "kept as-is.\n"
    "- Each fact id may appear in at most ONE op. Only reference fact ids from the "
    "LIVE FACTS list. Never reference a correction or invent an id.\n"
    "- Rewrite the wiki: a brief, current one-pager that reflects the consolidated "
    "facts and is consistent with the pinned corrections.\n\n"
    "Output STRICT JSON only — no prose, no code fence — with this shape:\n"
    '{"operations": [ ... ], "new_wiki": "...", "lint_notes": "..."}\n'
    'where each op is {"op":"retire","fact_id":"<uuid>","reason":"..."} or '
    '{"op":"replace","supersedes":["<uuid>", ...],"fact":"...","fact_type":"term",'
    '"source":"...","valid_from":"YYYY-MM-DD","reason":"..."}. "lint_notes" briefly '
    "summarises what you found (duplicates, contradictions, stale facts). If nothing "
    'needs changing, return "operations": [] and the wiki cleaned or unchanged.'
)


def build_matter_consolidation_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
    gateway_factory: Callable[[], GatewayClient] = get_gateway_client,
) -> list[Callable[..., Any]]:
    """Build the in-run matter-memory consolidation tool for one matter-bound run.

    ``gateway_factory`` is the DI seam (tests inject a stub); it is resolved lazily
    inside the tool so composition never builds a client it may not use. The model
    alias is read from ``LQ_AI_MATTER_CONSOLIDATION_MODEL`` then
    :data:`_DEFAULT_CONSOLIDATION_MODEL` (one override path — env). The guard grants
    exactly :data:`MATTER_CONSOLIDATION_TOOL_NAMES`; the matter scopes every write
    (ADR-F042).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=MATTER_CONSOLIDATION_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )
    resolved_alias = (
        os.environ.get("LQ_AI_MATTER_CONSOLIDATION_MODEL") or _DEFAULT_CONSOLIDATION_MODEL
    )

    async def consolidate_matter_memory() -> str:
        """Consolidate THIS matter's memory: dedupe/supersede stale facts + tidy the wiki.

        Call this to reconcile the matter's memory when the fact ledger has grown, when
        facts duplicate or contradict each other, or before handing the matter on. It
        reviews the matter's live facts and wiki together and, in one pass:

        - supersedes facts that are stale, duplicated, or the losing side of a
          contradiction (the old fact is kept and marked no-longer-current — the dated
          history is never lost), and
        - rewrites the matter wiki into a clean, current one-pager.

        It never changes a correction the supervising lawyer has recorded — those are
        ground truth. You do not pass anything; it reads the matter's own memory. Use it
        sparingly (it reviews the whole ledger), not after every small change.
        """
        gateway = gateway_factory()
        return await guarded_dispatch(
            "consolidate_matter_memory",
            lambda db: _consolidate_matter_memory(
                db, binding, run_id=run_id, gateway=gateway, model_alias=resolved_alias
            ),
            ctx,
        )

    return [consolidate_matter_memory]


class _ConsolidationParseError(ValueError):
    """The model's output was not a usable :class:`ConsolidationResult` proposal."""


async def _consolidate_matter_memory(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    run_id: uuid.UUID,
    gateway: GatewayClient,
    model_alias: str,
) -> str:
    """Load → one gateway call → validate → supersede-only apply + wiki rewrite.

    Reject (return a fix-and-retry string), never sanitize/truncate. All-or-nothing:
    every reject path leaves the matter untouched (no flush happens before the full
    validation pass succeeds). Pinned corrections are read-only input and are never in
    the op space (the id validation below makes a correction id unreachable).
    """
    # Reload the matter under owner scope in THIS guarded session (defense in depth —
    # mirrors the other matter tools). Absent ⇒ the matter vanished underneath us.
    project = (
        await db.execute(
            select(Project).where(
                Project.id == binding.project_id,
                Project.owner_id == binding.user_id,
                Project.archived_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if project is None:
        return "This matter is no longer available; nothing was changed."

    facts = await live_facts(db, project.id)
    if not facts:
        # No live facts ⇒ nothing to consolidate, and no reason to spend an egress call.
        return (
            "This matter has no recorded facts yet, so there is nothing to consolidate. "
            "Record facts with record_matter_fact first."
        )

    wiki = (project.context_md or "").strip()
    corrections_block = format_corrections_block(await load_pinned_corrections(db, project.id))

    user_content = _build_user_prompt(facts, wiki, corrections_block)
    request = ChatCompletionRequest(
        model=model_alias,
        messages=[
            ChatCompletionMessage(role="system", content=_SYSTEM_PROMPT),
            ChatCompletionMessage(role="user", content=user_content),
        ],
        max_tokens=_CONSOLIDATION_MAX_TOKENS,
        # The consolidation must judge the REAL fact text (equivalence/contradiction over
        # masked text is impossible) — same posture as the playbook extractor. The
        # gateway is still the sole egress and key-holder (ADR-F010 / ADR 0002).
        anonymize=False,
        lq_ai_purpose="consolidate_matter_memory",
    )

    try:
        response = await gateway.chat_completion(request)
    except Exception as exc:  # transport/gateway failure → reject-and-retry, never a crash
        # asyncio.CancelledError is a BaseException, so a wall-clock cancel still
        # propagates (the guard records the timeout); only real errors land here.
        logger.warning(
            "matter consolidation gateway call failed",
            extra={
                "event": "matter_consolidation_gateway_error",
                "run_id": str(run_id),
                "error_type": type(exc).__name__,
            },
        )
        return (
            "The consolidation could not be completed because the model service was "
            "unavailable. Nothing was changed; try again."
        )

    content = _response_text(response)
    if content is None:
        return "The consolidation model returned no usable output. Nothing was changed."
    if _was_truncated(response):
        # finish_reason='length' ⇒ the JSON is cut off; surface a diagnosable reject
        # (the generic parse error below would otherwise hide the real cause).
        return (
            "The consolidation output was too large to complete in one pass (this "
            "matter's ledger may have too many facts to consolidate at once). Nothing "
            "was changed."
        )

    try:
        result = _parse_consolidation_result(content)
    except _ConsolidationParseError as exc:
        # Bound the reflected reason: it is derived from untrusted model output (a bad
        # op tag/key is echoed verbatim by Pydantic), so cap what re-enters the prompt.
        return f"The consolidation proposal was rejected ({str(exc)[:200]}). Nothing was changed."

    # --- Pure validation pass (NO mutation): every id must be a live fact of THIS
    # matter; no id may appear twice; the new window-start must be temporally coherent
    # with what it closes. A correction id is unreachable here (live_facts is
    # kind='fact' only). `now` is captured ONCE and is the single clock for the whole
    # pass; each op's effective world-time is resolved here into `resolved_valid_at` and
    # REUSED in apply, so the validated value IS the persisted value (no drift).
    now = datetime.now(UTC)
    live_by_id: dict[uuid.UUID, MatterMemoryEntry] = {f.id: f for f in facts}
    referenced: list[uuid.UUID] = []
    resolved_valid_at: list[datetime] = []
    for op in result.operations:
        ids = [op.fact_id] if op.op == "retire" else list(op.supersedes)
        referenced.extend(ids)
        for fid in ids:
            if fid not in live_by_id:
                return (
                    "The consolidation proposal referenced a fact that is not a live "
                    f"fact of this matter (id {fid}); it may be a correction, already "
                    "superseded, or invented. Nothing was changed."
                )
        if op.op == "retire":
            # Retire closes the window at `now`. A future-dated fact (valid_at > now)
            # cannot be retired yet — invalid_at <= valid_at would violate the
            # bi-temporal CHECK and crash the flush; reject-and-retry instead (the
            # no-crash contract).
            resolved_valid_at.append(now)
            prior = live_by_id[op.fact_id]
            if prior.valid_at is not None and now <= prior.valid_at:
                return (
                    "A fact cannot be retired before its validity start "
                    f"(id {op.fact_id}); it is not yet in effect. Nothing was changed."
                )
        else:  # replace
            new_valid_at = op.valid_from or now
            resolved_valid_at.append(new_valid_at)
            for fid in op.supersedes:
                prior = live_by_id[fid]
                if prior.valid_at is not None and new_valid_at <= prior.valid_at:
                    return (
                        "A replacement fact's valid_from must be later than the fact it "
                        f"supersedes (id {fid}). Nothing was changed."
                    )
    if len(referenced) != len(set(referenced)):
        return (
            "The consolidation proposal referenced the same fact in more than one "
            "operation. Nothing was changed."
        )

    # --- Apply (all-or-nothing; validation has passed) ------------------------------
    retired = 0
    merged_in = 0
    merged_into = 0
    for op, op_valid_at in zip(result.operations, resolved_valid_at, strict=True):
        if op.op == "retire":
            prior = live_by_id[op.fact_id]
            prior.invalid_at = op_valid_at  # == now; no replacement (superseded_by NULL)
            retired += 1
            continue
        # replace: insert the consolidated fact, then close each superseded prior.
        new_fact = MatterMemoryEntry(
            project_id=project.id,
            user_id=binding.user_id,
            kind="fact",
            body_md=op.fact,
            trust="normal",
            author="agent",
            source_citation=op.source,
            fact_type=op.fact_type.value,
            valid_at=op_valid_at,
            run_id=run_id,
        )
        db.add(new_fact)
        await db.flush()  # assign new_fact.id for the forward link
        for fid in op.supersedes:
            prior = live_by_id[fid]
            prior.invalid_at = op_valid_at
            prior.superseded_by = new_fact.id
        merged_in += len(op.supersedes)
        merged_into += 1

    wiki_changed = result.new_wiki.strip() != wiki
    if wiki_changed:
        await snapshot_and_rewrite_wiki(
            db, project, run_id=run_id, user_id=binding.user_id, new_content=result.new_wiki
        )
    await db.flush()

    parts: list[str] = []
    if retired:
        parts.append(f"retired {retired} stale fact(s)")
    if merged_into:
        parts.append(f"merged {merged_in} fact(s) into {merged_into} consolidated fact(s)")
    if wiki_changed:
        parts.append(f"rewrote the wiki ({len(result.new_wiki)} characters)")
    summary = "; ".join(parts) if parts else "reviewed the ledger — no changes were needed"
    notes = f" Notes: {result.lint_notes}" if result.lint_notes else ""
    return f"Consolidated this matter's memory: {summary}.{notes}"


def _build_user_prompt(
    facts: list[MatterMemoryEntry], wiki: str, corrections_block: str | None
) -> str:
    """Render the live facts + wiki + pinned corrections for the consolidation prompt."""
    fact_lines = [
        "- id {id} | type {type} | {body} | source: {src} | valid_from: {vf}".format(
            id=f.id,
            type=f.fact_type or "fact",
            body=(f.body_md or "").replace("\n", " ").strip(),
            src=f.source_citation or "—",
            vf=f.valid_at.date().isoformat() if f.valid_at else "—",
        )
        for f in facts
    ]
    corrections = corrections_block or "(none)"
    return (
        "LIVE FACTS (each: id | type | statement | source | valid_from):\n"
        + "\n".join(fact_lines)
        + "\n\nCURRENT WIKI:\n"
        + (wiki or "(empty)")
        + "\n\nPINNED CORRECTIONS (ground truth — never contradict, modify, or "
        "reference these):\n"
        + corrections
        + "\n\nConsolidate per the rules. Output strict JSON only."
    )


def _response_text(response: Any) -> str | None:
    """Pull the text content out of a ChatCompletion response (None if absent/blank)."""
    try:
        choices = response.choices
        content = choices[0].message.content if choices else None
    except (AttributeError, IndexError):
        return None
    if not isinstance(content, str) or not content.strip():
        return None
    return content


def _was_truncated(response: Any) -> bool:
    """True if the model stopped on the token cap (``finish_reason='length'``).

    A truncated body is cut-off JSON; detecting it lets the tool return a diagnosable
    reject instead of a generic parse error. Best-effort — a response shape without a
    finish_reason simply reads as not-truncated.
    """
    try:
        return bool(response.choices) and response.choices[0].finish_reason == "length"
    except (AttributeError, IndexError):
        return False


def _parse_consolidation_result(content: str) -> ConsolidationResult:
    """Lenient JSON parse (tolerate a code fence) → validated ``ConsolidationResult``.

    Raise :class:`_ConsolidationParseError` (a concise, body-free reason) on malformed
    JSON, a non-object top level, or a schema violation — the caller turns it into a
    reject-and-retry string. No partial acceptance.
    """
    stripped = content.strip()
    if stripped.startswith("```"):
        parts = stripped.split("```", 2)
        if len(parts) >= 2:
            stripped = parts[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.rstrip("`").strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise _ConsolidationParseError(f"output was not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise _ConsolidationParseError("output was not a JSON object")

    try:
        return ConsolidationResult.model_validate(parsed)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()[:5]
        )
        raise _ConsolidationParseError(problems) from exc
