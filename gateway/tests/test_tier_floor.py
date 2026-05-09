"""Unit tests for tier-floor resolution (D1 helper module).

These tests exercise :func:`app.tier_floor.resolve_tier_floor` and
:func:`app.tier_floor.is_refused` in isolation — no FastAPI, no DB.
The integration of the helper into the chat-completions handler is
covered in ``test_inference_tier_floor.py``.

Coverage maps to PRD §4.4 / D1 verification cases (a)-(d):

* (a) request override only → request is the binding source.
* (b) skill floor only → ``skill:<name>`` is the binding source.
* (c) project floor only → ``project`` is the binding source.
* All three present → max wins; ties broken request > project > skill.
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


# --- Resolution: max-wins across sources ------------------------------------


def test_max_wins_request_beats_project() -> None:
    """Most-restrictive (highest value) wins when sources differ."""

    floor = resolve_tier_floor(
        request=_request(minimum=4, project_minimum=2),
        skills=[],
    )
    assert floor == TierFloor(value=4, source="request")


def test_max_wins_skill_beats_request() -> None:
    """Skill floor at 5 trumps a request floor at 2."""

    floor = resolve_tier_floor(
        request=_request(minimum=2),
        skills=[_skill("paranoid", minimum=5)],
    )
    assert floor == TierFloor(value=5, source="skill:paranoid")


def test_multiple_skills_take_max() -> None:
    """Multiple attached skills → ``max(floors)`` across them."""

    floor = resolve_tier_floor(
        request=_request(),
        skills=[
            _skill("loose", minimum=2),
            _skill("strict", minimum=4),
            _skill("medium", minimum=3),
        ],
    )
    assert floor == TierFloor(value=4, source="skill:strict")


# --- Tie-breaking on equal values -------------------------------------------


def test_tie_request_wins_over_project() -> None:
    """When request and project both declare the same floor, request wins."""

    floor = resolve_tier_floor(
        request=_request(minimum=3, project_minimum=3),
        skills=[],
    )
    assert floor == TierFloor(value=3, source="request")


def test_tie_project_wins_over_skill() -> None:
    """Project beats a skill at the same floor."""

    floor = resolve_tier_floor(
        request=_request(project_minimum=3),
        skills=[_skill("skill-a", minimum=3)],
    )
    assert floor == TierFloor(value=3, source="project")


def test_tie_first_skill_wins_among_skills() -> None:
    """Among skills tied at max, attachment order picks the first."""

    floor = resolve_tier_floor(
        request=_request(),
        skills=[
            _skill("first", minimum=3),
            _skill("second", minimum=3),
        ],
    )
    assert floor == TierFloor(value=3, source="skill:first")


# --- is_refused predicate ----------------------------------------------------


def test_is_refused_none_floor_never_refuses() -> None:
    assert is_refused(resolved_tier=1, floor=None) is False
    assert is_refused(resolved_tier=5, floor=None) is False


def test_is_refused_below_floor_refuses() -> None:
    floor = TierFloor(value=3, source="request")
    assert is_refused(resolved_tier=1, floor=floor) is True
    assert is_refused(resolved_tier=2, floor=floor) is True


def test_is_refused_at_floor_passes() -> None:
    """A resolved tier equal to the floor is allowed (minimum, not exclusive)."""

    floor = TierFloor(value=3, source="request")
    assert is_refused(resolved_tier=3, floor=floor) is False


def test_is_refused_above_floor_passes() -> None:
    floor = TierFloor(value=3, source="request")
    assert is_refused(resolved_tier=4, floor=floor) is False
    assert is_refused(resolved_tier=5, floor=floor) is False


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
