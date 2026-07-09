"""Practice Playbook tier renderer — ADR-F054 (capability panel) + ADR-F067 B-4 (org playbooks).

Renders the company's enabled playbooks (the ``playbooks`` / ``playbook_positions``
DATA — the preferred-positions wish-list) into the inner text of the read-only
"Practice Playbook" memory tier. The legacy linear executor is FROZEN (CLAUDE.md);
this REUSES only the data, injected as standing context the agent weighs each turn
(like the four read-only DATA tiers), never as instructions.

Pure: takes a mixed sequence of renderable playbooks and returns text. Two shapes flow in
(B-4): live built-in ``Playbook`` rows (``created_by IS NULL`` — shipped, trusted) and
:class:`~app.agents.playbook_proposal.FrozenPlaybook` snapshots (org-authored, untrusted). An
org snapshot carries a ``provenance_banner`` (the F067 D3.5 line, emitted under its header) and
has its every rendered field DEFANGED so an author cannot spoof the tier's dash-fence markers
(``----- END PRACTICE PLAYBOOK -----``) or inject instructions across a line break. Built-in
rows carry no banner and are rendered exactly as before — byte-identical (they are shipped/
trusted; defang would change their output).

The caller (``compose_and_execute_run`` → ``render_memory_tiers``) wraps the result in the
data-only fence. Length-capped so a large playbook can't blow the context window; the
ADR-F051/F053 token-budget brake is the backstop.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Protocol

# Caps (chars) — keep the standing block bounded. A position's preferred language is
# the bulk; fallbacks are summarised; the whole block is hard-capped last.
_MAX_STD_CHARS = 400
_MAX_FALLBACK_CHARS = 200
_MAX_FALLBACK_TIERS = 3
_MAX_TOTAL_CHARS = 6_000

# Fence-defang (ADR-F067 B-4): collapse all whitespace (so no embedded newline can START a
# ``----- END PRACTICE PLAYBOOK -----`` marker line) and shorten any 3+ hyphen run (so no run can
# FORM a marker rule). Applied ONLY to org-authored (untrusted) fields — B-4 is the first slice
# routing an authenticated author's text through this fence.
_DASH_RUN_RE = re.compile(r"-{3,}")
_WS_RUN_RE = re.compile(r"\s+")


class _PlaybookRenderable(Protocol):
    name: str
    contract_type: str
    positions: Any


def _defang(value: str) -> str:
    return _DASH_RUN_RE.sub("-", _WS_RUN_RE.sub(" ", value).strip())


def _truncate(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _summarise_fallbacks(tiers: object, *, defang: bool) -> str:
    """A short, ranked summary of a position's fallback tiers (defensive over JSONB).

    ``fallback_tiers`` is a JSONB list of ``{rank, description, language}`` shapes;
    treat it as untrusted-shaped data — skip anything not a dict / without text. When
    ``defang`` (an org-authored snapshot) each tier's text is fence-neutralized.
    """
    if not isinstance(tiers, list):
        return ""
    out: list[str] = []
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        raw: Any = tier.get("description") or tier.get("language") or ""
        text = _defang(str(raw)) if defang else str(raw).strip()
        if not text:
            continue
        out.append(_truncate(text, _MAX_FALLBACK_CHARS))
        if len(out) >= _MAX_FALLBACK_TIERS:
            break
    return "; ".join(out)


def render_practice_playbook(playbooks: Sequence[_PlaybookRenderable]) -> str:
    """Render the enabled playbooks' preferred positions as the tier's inner text.

    Returns ``""`` when there is nothing to show (no playbooks / no positions), so
    the caller's fence degrades cleanly to silence. Each position lists the preferred
    (standard) language, a short fallback summary, and the severity if the clause is
    missing — ordered by ``position_order`` (the relationship's order_by). An org-authored
    snapshot (carrying ``provenance_banner``) emits a ``> Provenance: …`` line under its header
    and has its fields defanged; built-in rows render byte-identically to before B-4.
    """
    if not playbooks:
        return ""
    blocks: list[str] = []
    for playbook in playbooks:
        banner = getattr(playbook, "provenance_banner", None)
        untrusted = banner is not None

        def clean(value: str | None, *, _untrusted: bool = untrusted) -> str:
            return _defang(value or "") if _untrusted else (value or "")

        name = clean(playbook.name)
        contract_type = clean(playbook.contract_type)
        header = f"{name} ({contract_type})" if contract_type else name
        lines = [f"### {header}"]
        if banner:
            lines.append(f"> {banner}")
        positions = list(playbook.positions or [])
        if not positions:
            lines.append("(no positions recorded)")
            blocks.append("\n".join(lines))
            continue
        for pos in positions:
            issue = clean(pos.issue).strip() or "(unnamed issue)"
            entry = [f"- {issue}"]
            std = _truncate(clean(pos.standard_language), _MAX_STD_CHARS)
            if std:
                entry.append(f"  - Preferred: {std}")
            fallback = _summarise_fallbacks(pos.fallback_tiers, defang=untrusted)
            if fallback:
                entry.append(f"  - Fallback: {fallback}")
            severity = clean(pos.severity_if_missing).strip()
            if severity:
                entry.append(f"  - Severity if missing: {severity}")
            lines.append("\n".join(entry))
        blocks.append("\n".join(lines))
    return _truncate("\n\n".join(blocks), _MAX_TOTAL_CHARS)
