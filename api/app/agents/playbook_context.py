"""Practice Playbook tier renderer — ADR-F054 (capability panel).

Renders the company's enabled playbooks (the ``playbooks`` / ``playbook_positions``
DATA — the preferred-positions wish-list) into the inner text of the read-only
"Practice Playbook" memory tier. The legacy linear executor is FROZEN (CLAUDE.md);
this REUSES only the data, injected as standing context the agent weighs each turn
(like the four read-only DATA tiers), never as instructions.

Pure: takes loaded ``Playbook`` rows (with ``positions`` loaded) and returns text.
The caller (``compose_and_execute_run`` → ``render_memory_tiers``) wraps the result
in the data-only fence. Length-capped so a large playbook can't blow the context
window; the ADR-F051/F053 token-budget brake is the backstop.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.models.playbook import Playbook

# Caps (chars) — keep the standing block bounded. A position's preferred language is
# the bulk; fallbacks are summarised; the whole block is hard-capped last.
_MAX_STD_CHARS = 400
_MAX_FALLBACK_CHARS = 200
_MAX_FALLBACK_TIERS = 3
_MAX_TOTAL_CHARS = 6_000


def _truncate(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _summarise_fallbacks(tiers: object) -> str:
    """A short, ranked summary of a position's fallback tiers (defensive over JSONB).

    ``fallback_tiers`` is a JSONB list of ``{rank, description, language}`` shapes;
    treat it as untrusted-shaped data — skip anything not a dict / without text.
    """
    if not isinstance(tiers, list):
        return ""
    out: list[str] = []
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        raw: Any = tier.get("description") or tier.get("language") or ""
        text = str(raw).strip()
        if not text:
            continue
        out.append(_truncate(text, _MAX_FALLBACK_CHARS))
        if len(out) >= _MAX_FALLBACK_TIERS:
            break
    return "; ".join(out)


def render_practice_playbook(playbooks: Sequence[Playbook]) -> str:
    """Render the enabled playbooks' preferred positions as the tier's inner text.

    Returns ``""`` when there is nothing to show (no playbooks / no positions), so
    the caller's fence degrades cleanly to silence. Each position lists the preferred
    (standard) language, a short fallback summary, and the severity if the clause is
    missing — ordered by ``position_order`` (the relationship's order_by).
    """
    if not playbooks:
        return ""
    blocks: list[str] = []
    for playbook in playbooks:
        header = (
            f"{playbook.name} ({playbook.contract_type})"
            if playbook.contract_type
            else playbook.name
        )
        lines = [f"### {header}"]
        positions = list(playbook.positions or [])
        if not positions:
            lines.append("(no positions recorded)")
            blocks.append("\n".join(lines))
            continue
        for pos in positions:
            issue = (pos.issue or "").strip() or "(unnamed issue)"
            entry = [f"- {issue}"]
            std = _truncate(pos.standard_language or "", _MAX_STD_CHARS)
            if std:
                entry.append(f"  - Preferred: {std}")
            fallback = _summarise_fallbacks(pos.fallback_tiers)
            if fallback:
                entry.append(f"  - Fallback: {fallback}")
            severity = (pos.severity_if_missing or "").strip()
            if severity:
                entry.append(f"  - Severity if missing: {severity}")
            lines.append("\n".join(entry))
        blocks.append("\n".join(lines))
    return _truncate("\n\n".join(blocks), _MAX_TOTAL_CHARS)
