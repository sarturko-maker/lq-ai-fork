"""Org-playbook propose synthesis + canonical freezing (ADR-F067 D2/D3, B-4).

The playbook twin of :mod:`app.skills.org_proposal` — the pure, no-HTTP core of the org-playbook
harness. Unlike the skill harness there is **no frontmatter allowlist**: a playbook is a
pre-validated CLOSED Pydantic shape (``PlaybookCreate``/``PositionCreate`` are ``extra='forbid'``)
and is GUIDANCE-DATA rendered behind the already-existing ``PRACTICE_PLAYBOOK_PROMPT`` data-only
fence (``composition.py``), so the D3.3 closed-schema check has no analogue and is deliberately
dropped. Every *other* D3 control still applies — this module is the immutable snapshot + content
hash + size-cap machinery those controls need.

Callers (the propose endpoint, the admin approve/list endpoints, the runtime composition seam) own
all HTTP status codes and audit rows; nothing here raises HTTP-shaped errors. The sole DB
touchpoint is :func:`load_approved_org_playbook_versions` — the one shared reader for "the org's
currently-approved playbook snapshots", so that query cannot drift across the member Library read,
the admin catalog/inventory, the runtime composition seam and the matter-capabilities panel.

Determinism is load-bearing: :func:`canonicalize_positions` produces a byte-stable serialization
(positions ordered by ``position_order`` then by their own canonical JSON — never by ``id``, which
would make semantically-equal inputs hash differently; ``fallback_tiers`` ordered by ``rank``;
keys sorted at dump). Totality is load-bearing too: the canonicalizer never raises on malformed
untrusted ``fallback_tiers`` (it skips non-dict tiers, mirroring
``playbook_context._summarise_fallbacks``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org_playbook_version import OrgPlaybookVersion

# Re-exported so callers import the D3.5 provenance sentence from one place; the banner is
# kind-agnostic (author/approver/date), so B-4 reuses the skill harness's implementation verbatim.
from app.skills.org_proposal import render_provenance_banner

# F067 D3.6 — a hostile or accidental context-flooding playbook is capped before it can tax every
# run's token budget (F051). Enforced by the CALLER (the propose endpoint 422s); this module only
# computes ``size_bytes`` (over the canonical positions+header payload) for the caller to compare.
ORG_PLAYBOOK_MAX_BYTES = 32 * 1024


class _PlaybookLike(Protocol):
    """Duck-typed source playbook — a live ``Playbook`` ORM row (with ``positions`` loaded) at
    freeze time. Only a static annotation on :func:`freeze_playbook_snapshot`; the per-position
    fields are duck-typed in :func:`_canonical_position` (total over ORM rows AND dicts)."""

    name: str
    contract_type: str
    description: str
    version: str
    positions: Any


@dataclass(frozen=True)
class OrgPlaybookContent:
    """The frozen content for one org-playbook proposal — everything a caller needs to populate an
    :class:`~app.models.org_playbook_version.OrgPlaybookVersion` row's content columns."""

    name: str
    contract_type: str
    description: str
    playbook_version: str
    positions: list[dict[str, Any]]
    """The CANONICAL positions list — stored verbatim in ``org_playbook_versions.positions`` so the
    stored bytes are already deterministic and re-hashable."""

    content_hash: str
    """sha256 hexdigest over the canonical positions+header JSON, UTF-8 encoded."""

    size_bytes: int
    """UTF-8 byte size of that same canonical payload — what the caller compares against
    :data:`ORG_PLAYBOOK_MAX_BYTES`."""

    position_count: int


@dataclass(frozen=True)
class FrozenPosition:
    """A rehydrated position for tier rendering — exposes exactly the attributes
    :func:`app.agents.playbook_context.render_practice_playbook` reads."""

    issue: str
    description: str
    standard_language: str
    fallback_tiers: list[dict[str, Any]]
    redline_strategy: str
    severity_if_missing: str


@dataclass(frozen=True)
class FrozenPlaybook:
    """A rehydrated org playbook fed to the SAME ``render_practice_playbook`` as live built-in
    rows. ``provenance_banner`` is the per-playbook D3.5 line the renderer emits under the header;
    live built-in ``Playbook`` rows have no such attribute, so their output stays byte-identical."""

    name: str
    contract_type: str
    positions: list[FrozenPosition]
    provenance_banner: str | None


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _canonical_fallback_tiers(tiers: Any) -> list[dict[str, Any]]:
    """Deterministic, total normalization of a position's untrusted ``fallback_tiers`` JSONB.

    Skips non-dict entries (mirroring the render path), orders by numeric ``rank`` (missing/
    non-numeric ranks sort last, stably tiebroken by the tier's own canonical JSON). Never raises.
    """
    if not isinstance(tiers, list):
        return []
    normalized = [dict(t) for t in tiers if isinstance(t, dict)]

    def _key(tier: dict[str, Any]) -> tuple[float, str]:
        rank = tier.get("rank")
        rank_num = (
            float(rank)
            if isinstance(rank, (int, float)) and not isinstance(rank, bool)
            else float("inf")
        )
        return (rank_num, json.dumps(tier, sort_keys=True, ensure_ascii=False, default=str))

    return sorted(normalized, key=_key)


def _canonical_position(pos: Any) -> dict[str, Any]:
    """One position → its canonical dict (full fidelity, ``id`` deliberately excluded)."""

    def g(name: str, default: Any) -> Any:
        if isinstance(pos, dict):
            return pos.get(name, default)
        return getattr(pos, name, default)

    def _str_list(value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return [_s(x) for x in value]

    order = g("position_order", 0)
    try:
        order_int = int(order)
    except (TypeError, ValueError):
        order_int = 0

    return {
        "issue": _s(g("issue", "")),
        "description": _s(g("description", "")),
        "standard_language": _s(g("standard_language", "")),
        "fallback_tiers": _canonical_fallback_tiers(g("fallback_tiers", [])),
        "redline_strategy": _s(g("redline_strategy", "")),
        "severity_if_missing": _s(g("severity_if_missing", "")),
        "detection_keywords": _str_list(g("detection_keywords", [])),
        "detection_examples": _str_list(g("detection_examples", [])),
        "position_order": order_int,
    }


def canonicalize_positions(positions: Any) -> list[dict[str, Any]]:
    """The canonical, deterministic positions list for hashing + storage.

    Ordered by ``(position_order, canonical-JSON-of-the-position)`` — a TOTAL order over CONTENT
    only, so re-proposing unchanged content (or semantically-equal-but-reordered input) yields
    byte-identical output regardless of row ``id`` or Postgres return order.
    """
    canon = [_canonical_position(p) for p in (positions or [])]
    canon.sort(
        key=lambda c: (c["position_order"], json.dumps(c, sort_keys=True, ensure_ascii=False))
    )
    return canon


def _canonical_payload(
    *,
    name: str,
    contract_type: str,
    description: str,
    playbook_version: str,
    positions: list[dict[str, Any]],
) -> str:
    """The exact bytes ``content_hash`` covers and ``size_bytes`` measures."""
    return json.dumps(
        {
            "header": {
                "name": name,
                "contract_type": contract_type,
                "description": description,
                "playbook_version": playbook_version,
            },
            "positions": positions,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def freeze_playbook_snapshot(playbook: _PlaybookLike) -> OrgPlaybookContent:
    """Freeze a live ``Playbook`` (+ its ordered positions) into immutable snapshot content.

    A deep, canonical copy — later edits to the live row do not retroactively change an
    already-frozen :class:`OrgPlaybookContent` (this is a snapshot, per D2 "approval pins bytes").
    """
    name = _s(playbook.name)
    contract_type = _s(playbook.contract_type)
    description = _s(playbook.description)
    playbook_version = _s(playbook.version)
    positions = canonicalize_positions(playbook.positions)
    payload = _canonical_payload(
        name=name,
        contract_type=contract_type,
        description=description,
        playbook_version=playbook_version,
        positions=positions,
    )
    encoded = payload.encode("utf-8")
    return OrgPlaybookContent(
        name=name,
        contract_type=contract_type,
        description=description,
        playbook_version=playbook_version,
        positions=positions,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        size_bytes=len(encoded),
        position_count=len(positions),
    )


def content_size_bytes(version: OrgPlaybookVersion) -> int:
    """Recompute the canonical-payload byte size from a stored version's immutable columns.

    Shared by the admin review read and the author's proposal read so "how big is this org
    playbook" has one definition. Content columns are immutable, so this is stable for a row."""
    payload = _canonical_payload(
        name=version.name,
        contract_type=version.contract_type,
        description=version.description or "",
        playbook_version=version.playbook_version,
        positions=list(version.positions or []),
    )
    return len(payload.encode("utf-8"))


def frozen_playbook_from_version(
    version: OrgPlaybookVersion, *, author_label: str, approver_label: str
) -> FrozenPlaybook:
    """Rehydrate an approved snapshot into the render object fed to ``render_practice_playbook``.

    Attaches the D3.5 provenance banner (author/approver/approval-date); reads ONLY the frozen
    ``positions`` JSONB, never the live ``playbooks`` row — the TOCTOU-closing guarantee.
    """
    approved_on = version.reviewed_at.date().isoformat() if version.reviewed_at else "unknown"
    banner = render_provenance_banner(author_label, approver_label, approved_on)
    positions = [
        FrozenPosition(
            issue=_s(p.get("issue", "")),
            description=_s(p.get("description", "")),
            standard_language=_s(p.get("standard_language", "")),
            fallback_tiers=list(p.get("fallback_tiers") or []),
            redline_strategy=_s(p.get("redline_strategy", "")),
            severity_if_missing=_s(p.get("severity_if_missing", "")),
        )
        for p in (version.positions or [])
        if isinstance(p, dict)
    ]
    return FrozenPlaybook(
        name=version.name,
        contract_type=version.contract_type,
        positions=positions,
        provenance_banner=banner,
    )


async def load_approved_org_playbook_versions(db: AsyncSession) -> dict[str, OrgPlaybookVersion]:
    """The org's currently-``approved`` org-playbook snapshots (ADR-F067 D2/D3, B-4), keyed by
    ``playbook_id`` as a string.

    The module's single DB touchpoint and the ONE place the ``state == 'approved'`` snapshot query
    lives, so "what counts as a live org playbook" cannot drift between the member Library read, the
    admin catalog/inventory, the runtime composition seam and the capability panel. Callers that
    only need the key set derive it from ``.keys()``."""
    rows = (
        (await db.execute(select(OrgPlaybookVersion).where(OrgPlaybookVersion.state == "approved")))
        .scalars()
        .all()
    )
    return {str(v.playbook_id): v for v in rows}


__all__ = [
    "ORG_PLAYBOOK_MAX_BYTES",
    "FrozenPlaybook",
    "FrozenPosition",
    "OrgPlaybookContent",
    "canonicalize_positions",
    "content_size_bytes",
    "freeze_playbook_snapshot",
    "frozen_playbook_from_version",
    "load_approved_org_playbook_versions",
    "render_provenance_banner",
]
