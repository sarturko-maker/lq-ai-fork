"""Unit tests for tier-floor resolution (D1 helper module).

These tests exercise :func:`app.tier_floor.resolve_tier_floor` and
:func:`app.tier_floor.is_refused` in isolation — no FastAPI, no DB.
The integration of the helper into the chat-completions handler is
covered in ``test_inference_tier_floor.py``.

Coverage maps to PRD §4.4 / D1 verification cases (a)-(d):

* (a) request override only → request is the binding source.
* (b) skill floor only → ``skill:<name>`` is the binding source.
* (c) project floor only → ``project`` is the binding source.
* All three present → min wins (lowest number = strongest security per
  PRD §1.5.2); ties broken request > project > skill.
"""

from __future__ import annotations

import pytest

from app.clients.backend import Skill
from app.providers import ChatCompletionMessage, ChatCompletionRequest
from app.tier_floor import TierFloor, is_refused, resolve_tier_floor


def _request(
    *,
    minimum: int | None = None,
    project_minimum: int | None = None,
) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="smart",
        messages=[ChatCompletionMessage(role="user", content="hi")],
        minimum_inference_tier=minimum,
        lq_ai_project_minimum_inference_tier=project_minimum,
    )


def _skill(name: str, *, minimum: int | None) -> Skill:
    return Skill(name=name, minimum_inference_tier=minimum)


# --- Resolution: zero / single source ----------------------------------------


def test_no_sources_returns_none() -> None:
    """No floor anywhere → no refusal axis."""

    floor = resolve_tier_floor(request=_request(), skills=[])
    assert floor is None


def test_request_floor_only() -> None:
    """Case (a) — only the request override declares a floor."""

    floor = resolve_tier_floor(request=_request(minimum=2), skills=[])
    assert floor == TierFloor(value=2, source="request")


def test_project_floor_only() -> None:
    """Case (c) — only the project declares a floor."""

    floor = resolve_tier_floor(request=_request(project_minimum=3), skills=[])
    assert floor == TierFloor(value=3, source="project")


def test_skill_floor_only() -> None:
    """Case (b) — only the skill declares a floor."""

    floor = resolve_tier_floor(
        request=_request(),
        skills=[_skill("nda-review", minimum=2)],
    )
    assert floor == TierFloor(value=2, source="skill:nda-review")


def test_skill_with_no_floor_is_ignored() -> None:
    """Skills without a declared floor don't contribute."""

    floor = resolve_tier_floor(
        request=_request(),
        skills=[_skill("plain", minimum=None)],
    )
    assert floor is None


# --- Resolution: min-wins across sources (PRD §1.5.2: lower = stricter) -----


def test_min_wins_request_beats_project() -> None:
    """Most-restrictive (lowest value under PRD §1.5.2) wins when sources differ.

    Request declares floor=2 (requires Tier 2 or stronger);
    project declares floor=4 (requires Tier 4 or stronger).
    min(2, 4)=2 — the request's stricter floor wins.
    """

    floor = resolve_tier_floor(
        request=_request(minimum=2, project_minimum=4),
        skills=[],
    )
    assert floor == TierFloor(value=2, source="request")


def test_min_wins_skill_beats_request() -> None:
    """Skill floor at 1 (strictest) trumps a request floor at 4.

    Under PRD §1.5.2, Tier 1 is the most secure (local/air-gapped).
    min(4, 1)=1 — the skill's stricter floor wins.
    """

    floor = resolve_tier_floor(
        request=_request(minimum=4),
        skills=[_skill("air-gap-only", minimum=1)],
    )
    assert floor == TierFloor(value=1, source="skill:air-gap-only")


def test_multiple_skills_take_min() -> None:
    """Multiple attached skills → ``min(floors)`` across them (strictest wins)."""

    floor = resolve_tier_floor(
        request=_request(),
        skills=[
            _skill("loose", minimum=4),
            _skill("strict", minimum=2),
            _skill("medium", minimum=3),
        ],
    )
    assert floor == TierFloor(value=2, source="skill:strict")


# --- Tie-breaking on equal values -------------------------------------------


def test_tie_request_wins_over_project() -> None:
    """When request and project both declare the same floor, request wins."""

    floor = resolve_tier_floor(
        request=_request(minimum=2, project_minimum=2),
        skills=[],
    )
    assert floor == TierFloor(value=2, source="request")


def test_tie_project_wins_over_skill() -> None:
    """Project beats a skill at the same floor."""

    floor = resolve_tier_floor(
        request=_request(project_minimum=2),
        skills=[_skill("skill-a", minimum=2)],
    )
    assert floor == TierFloor(value=2, source="project")


def test_tie_first_skill_wins_among_skills() -> None:
    """Among skills tied at min, attachment order picks the first."""

    floor = resolve_tier_floor(
        request=_request(),
        skills=[
            _skill("first", minimum=2),
            _skill("second", minimum=2),
        ],
    )
    assert floor == TierFloor(value=2, source="skill:first")


# --- is_refused predicate ----------------------------------------------------
# Under PRD §1.5.2: lower tier number = stronger security.
# floor=2 means "require Tier 2 or stronger (lower-numbered)".
# Refused when resolved_tier > floor.value (weaker than the floor).


def test_is_refused_none_floor_never_refuses() -> None:
    assert is_refused(resolved_tier=1, floor=None) is False
    assert is_refused(resolved_tier=5, floor=None) is False


def test_is_refused_weaker_than_floor_refuses() -> None:
    """Tiers weaker (higher-numbered) than the floor are refused.

    floor=2 (requires Tier 2 or stronger).
    Tier 3, 4, 5 are all weaker — refused.
    """
    floor = TierFloor(value=2, source="request")
    assert is_refused(resolved_tier=3, floor=floor) is True
    assert is_refused(resolved_tier=4, floor=floor) is True
    assert is_refused(resolved_tier=5, floor=floor) is True


def test_is_refused_at_floor_passes() -> None:
    """A resolved tier equal to the floor is allowed (floor is the weakest acceptable)."""

    floor = TierFloor(value=2, source="request")
    assert is_refused(resolved_tier=2, floor=floor) is False


def test_is_refused_stronger_than_floor_passes() -> None:
    """Tiers stronger (lower-numbered) than the floor are allowed.

    floor=2 (requires Tier 2 or stronger).
    Tier 1 is stronger — allowed.
    """
    floor = TierFloor(value=2, source="request")
    assert is_refused(resolved_tier=1, floor=floor) is False


# --- Edge cases --------------------------------------------------------------


def test_floor_value_clamped_by_pydantic() -> None:
    """Pydantic enforces 1-5 on the request fields; out-of-range rejected."""

    with pytest.raises(ValueError):
        ChatCompletionRequest(
            model="smart",
            messages=[ChatCompletionMessage(role="user", content="hi")],
            minimum_inference_tier=6,  # above the 1-5 range
        )

    with pytest.raises(ValueError):
        ChatCompletionRequest(
            model="smart",
            messages=[ChatCompletionMessage(role="user", content="hi")],
            minimum_inference_tier=0,
        )
