"""Wave D.2 / Task 2.5 — unit tests for ``_rank_autocomplete_match``.

The autocomplete endpoint ranks merged-skill rows by three signals (in
descending priority):

* prefix on ``slash_alias`` (after stripping the leading slash from the
  user-typed query) — score 3
* prefix on ``slug`` — score 2
* substring match in ``title`` — score 1

These are the only signals; they compose by ``max()`` (a row that
matches more than one signal takes the highest). Rows are returned in
descending-score order; ties keep the input order (Python's ``sorted``
is stable).

This file exercises the pure scoring helper without spinning up
FastAPI, Postgres, or the registry. The endpoint-level filtering +
clamping are covered in
``api/tests/integration/test_skills_autocomplete_endpoint.py``.
"""

from __future__ import annotations

import pytest

from app.api.skills import _rank_autocomplete_match


def _row(
    *,
    slug: str,
    title: str,
    slash_alias: str | None = None,
    description: str = "",
    scope: str = "builtin",
) -> dict[str, object]:
    return {
        "slug": slug,
        "slash_alias": slash_alias,
        "title": title,
        "description": description,
        "scope": scope,
    }


# ---------------------------------------------------------------------------
# Prefix on slash_alias outranks contains-in-title
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_prefix_on_slash_alias_outranks_contains_in_title() -> None:
    rows = [
        # Contains-in-title only — score 1.
        _row(slug="some-other-skill", title="Reviews an NDA matter"),
        # Prefix-on-slash-alias — score 3.
        _row(slug="my-skill", slash_alias="/nda", title="My NDA helper"),
    ]
    ranked = _rank_autocomplete_match("nda", rows)
    assert ranked[0]["slug"] == "my-skill"
    assert ranked[1]["slug"] == "some-other-skill"


# ---------------------------------------------------------------------------
# Prefix on slug outranks contains-in-title
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_prefix_on_slug_outranks_contains_in_title() -> None:
    rows = [
        # Contains-in-title — score 1.
        _row(slug="z-skill", title="Catch-all NDA review pass"),
        # Prefix-on-slug — score 2.
        _row(slug="nda-personal", title="Personal NDA"),
    ]
    ranked = _rank_autocomplete_match("nda", rows)
    assert ranked[0]["slug"] == "nda-personal"
    assert ranked[1]["slug"] == "z-skill"


# ---------------------------------------------------------------------------
# Prefix on slash_alias outranks prefix-on-slug
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_prefix_on_slash_alias_outranks_prefix_on_slug() -> None:
    rows = [
        # Prefix-on-slug — score 2.
        _row(slug="nda-personal", title="Personal NDA"),
        # Prefix-on-slash-alias — score 3.
        _row(slug="my-skill", slash_alias="/nda", title="My NDA"),
    ]
    ranked = _rank_autocomplete_match("nda", rows)
    assert ranked[0]["slug"] == "my-skill"
    assert ranked[1]["slug"] == "nda-personal"


# ---------------------------------------------------------------------------
# Case-insensitive matching
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ranking_is_case_insensitive() -> None:
    rows = [
        _row(slug="NDA-Review", title="NDA Review Skill"),
    ]
    ranked = _rank_autocomplete_match("NDA", rows)
    # Upper-case query still matches the lower-cased slug-prefix path.
    assert ranked[0]["slug"] == "NDA-Review"


# ---------------------------------------------------------------------------
# Non-matching rows keep their relative input order at the tail
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_non_matching_rows_preserve_input_order() -> None:
    rows = [
        _row(slug="alpha", title="Alpha skill"),
        _row(slug="beta", title="Beta skill"),
        _row(slug="nda-personal", title="Personal NDA"),
    ]
    ranked = _rank_autocomplete_match("nda", rows)
    # nda-personal wins on slug-prefix; alpha and beta tie at 0 and keep
    # their input order (stable sort).
    assert ranked[0]["slug"] == "nda-personal"
    assert [r["slug"] for r in ranked[1:]] == ["alpha", "beta"]
