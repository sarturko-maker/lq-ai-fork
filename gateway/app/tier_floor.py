"""Tier-floor resolution + refusal helpers (D1).

Per PRD §4.4, every chat-completion request can declare a *minimum
inference tier* — a floor below which the gateway must refuse to route.
Three independent declarations contribute:

1. **Request override** — ``ChatCompletionRequest.minimum_inference_tier``.
   Per-call clamping. Highest specificity (one request).
2. **Project** — forwarded by the backend on
   ``ChatCompletionRequest.lq_ai_project_minimum_inference_tier`` when the
   chat lives in a project. The backend is authoritative on chat ↔
   project; the gateway only sees the value forwarded on the request.
3. **Skill** — ``Skill.minimum_inference_tier`` (frontmatter field per
   the skill-authoring guide). Each attached skill contributes its own
   floor; multiple attached skills mean ``max(floors)``.

The **effective floor** is ``max(any of the three)`` — the most
restrictive declaration wins. ``None`` from any source means "no
opinion"; we ignore it. If every source is ``None``, no floor applies
and the request is never refused on this axis.

When the resolved routed tier falls below the effective floor, the
gateway responds **HTTP 403** with the structured ``tier_below_minimum``
error envelope and writes a routing-log row carrying ``refused=True``
and ``refusal_reason='tier_below_minimum'``. Per PRD §4.4 / D1
verification cases (a)-(d).

This module is pure logic — no FastAPI / no DB / no Pydantic. The route
handler in :mod:`app.api.inference` calls :func:`resolve_tier_floor`
after skill-prompt assembly (so skill floors are visible) and before
dispatch (so refusal happens before any upstream call).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.clients.backend import Skill
from app.providers import ChatCompletionRequest


@dataclass(frozen=True)
class TierFloor:
    """Resolved tier floor with provenance.

    The provenance string is wired into the 403 response's
    ``details.source`` field so a caller looking at a refused request
    sees which declaration was binding (skill name / "project" /
    "request"). Operators reading audit logs see the same string in the
    ``refusal_reason`` row.
    """

    value: int
    """The effective floor; the most restrictive of all sources."""

    source: str
    """Human-readable origin: ``"request"``, ``"project"``, or
    ``"skill:<name>"``. When several sources tie at the same value, the
    request override wins, then project, then skill (in attachment
    order). Tie-breaking is purely diagnostic — the *value* is the same
    either way; we just want the surface to be deterministic so tests
    aren't flaky."""


def resolve_tier_floor(
    *,
    request: ChatCompletionRequest,
    skills: list[Skill] | None = None,
) -> TierFloor | None:
    """Compute the effective tier floor for a chat-completion request.

    Returns ``None`` when no source declared a floor — the request is
    not subject to D1 refusal on this axis.

    Tie-breaking is deterministic per :class:`TierFloor.source`'s
    docstring: request > project > skill (attachment order). The
    *value* is identical across ties; we pick a stable source string so
    tests can pin a deterministic ``details.source``.
    """

    # Collect (value, priority, label) entries; priority is the
    # tie-break order (smaller wins on ties). The actual floor is
    # ``max(value)``; the chosen entry is the highest-priority one
    # among those that share that max value.
    entries: list[tuple[int, int, str]] = []

    if request.minimum_inference_tier is not None:
        entries.append((int(request.minimum_inference_tier), 0, "request"))

    if request.lq_ai_project_minimum_inference_tier is not None:
        entries.append((int(request.lq_ai_project_minimum_inference_tier), 1, "project"))

    for index, skill in enumerate(skills or []):
        if skill.minimum_inference_tier is not None:
            entries.append((int(skill.minimum_inference_tier), 2 + index, f"skill:{skill.name}"))

    if not entries:
        return None

    max_value = max(e[0] for e in entries)
    # Among entries tied at the max, pick the one with the lowest
    # priority number. Stable sort means equal-priority entries stay in
    # insertion order — only relevant for skills (which already have
    # distinct priorities encoded by attachment index).
    candidates = [e for e in entries if e[0] == max_value]
    candidates.sort(key=lambda e: e[1])
    chosen = candidates[0]
    return TierFloor(value=chosen[0], source=chosen[2])


def is_refused(*, resolved_tier: int, floor: TierFloor | None) -> bool:
    """Return True iff the resolved tier is strictly below the floor.

    A floor of ``None`` (no declaration) never refuses. A resolved tier
    equal to the floor passes — the floor is a *minimum*, not an
    exclusive bound.
    """

    if floor is None:
        return False
    return int(resolved_tier) < int(floor.value)


__all__ = ["TierFloor", "is_refused", "resolve_tier_floor"]
