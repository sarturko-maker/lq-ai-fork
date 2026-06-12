"""Pure unit tests for the L0/L1 scorers (no stack, no tokens).

Run with the harness (`pytest evals/test_scoring_unit.py`) — kept out
of api/tests/ because `evals` is not an installed package in CI (only
`app` is); the containerized gate runs this file explicitly.
"""

from __future__ import annotations

import pytest

from evals.scoring import score_all, score_metric

_STEPS = [
    {
        "seq": 1,
        "kind": "model_turn",
        "name": None,
        "summary": "thinking [requested tools: search_documents]",
    },
    {
        "seq": 2,
        "kind": "tool_call",
        "name": "search_documents",
        "summary": '{"query": "liability cap"}',
    },
    {"seq": 3, "kind": "tool_result", "name": "search_documents", "summary": "Top 3 passages..."},
    {
        "seq": 4,
        "kind": "tool_call",
        "name": "read_document",
        "summary": '{"name": "msa-vendor-services.txt"}',
    },
    {
        "seq": 5,
        "kind": "tool_result",
        "name": "read_document",
        "summary": "[msa-vendor-services.txt — full text]...",
    },
    {"seq": 6, "kind": "model_turn", "name": None, "summary": "final"},
]

_ANSWER = (
    "The cap equals fees paid in the twelve (12) months before the event; "
    "gross negligence is excluded."
)


def test_tool_fired_and_not_fired() -> None:
    assert score_metric({"kind": "tool_fired", "tool": "search_documents"}, _STEPS, "") is True
    assert score_metric({"kind": "tool_fired", "tool": "task"}, _STEPS, "") is False
    assert score_metric({"kind": "tool_not_fired", "tool": "task"}, _STEPS, "") is True
    assert score_metric({"kind": "tool_not_fired", "tool": "read_document"}, _STEPS, "") is False


def test_tool_fired_any_counts_across_tools() -> None:
    spec = {
        "kind": "tool_fired_any",
        "tools": ["search_documents", "read_document"],
        "min_count": 2,
    }
    assert score_metric(spec, _STEPS, "") is True


def test_tool_arg_contains_and_only_if_fired() -> None:
    spec = {"kind": "tool_arg_contains", "tool": "read_document", "fragment": "msa-vendor-services"}
    assert score_metric(spec, _STEPS, "") is True
    na = {"kind": "tool_arg_contains", "tool": "task", "fragment": "x", "only_if_fired": True}
    assert score_metric(na, _STEPS, "") is None


def test_answer_checks_casefold() -> None:
    assert (
        score_metric(
            {"kind": "answer_contains_any", "fragments": ["TWELVE (12) MONTHS"]}, [], _ANSWER
        )
        is True
    )
    assert (
        score_metric(
            {
                "kind": "answer_contains_all_groups",
                "groups": [["twelve (12) months"], ["gross negligence"]],
            },
            [],
            _ANSWER,
        )
        is True
    )
    assert (
        score_metric(
            {"kind": "answer_not_contains_any", "fragments": ["four-year vesting"]}, [], _ANSWER
        )
        is True
    )
    assert (
        score_metric({"kind": "answer_contains_all_groups", "groups": [["england"]]}, [], _ANSWER)
        is False
    )


@pytest.mark.parametrize(
    ("n_tasks", "named_items", "expected"),
    [
        (4, 4, "one_per_item"),
        (4, 3, "partition"),  # enough calls but an item never named
        (2, 2, "partition"),
        (1, 1, "none"),
        (0, 0, "none"),
    ],
)
def test_task_strategy_enum(n_tasks: int, named_items: int, expected: str) -> None:
    items = ["nda-alpha", "nda-beta", "nda-gamma", "nda-delta"]
    steps = [
        {
            "seq": i,
            "kind": "tool_call",
            "name": "task",
            "summary": f'{{"description": "extract from {items[i % named_items]}"}}'
            if named_items
            else '{"description": "extract"}',
        }
        for i in range(n_tasks)
    ]
    spec = {"kind": "task_strategy", "item_fragments": items}
    assert score_metric(spec, steps, "") == expected


def test_score_all_shapes() -> None:
    out = score_all(
        {
            "a": {"kind": "tool_fired", "tool": "search_documents"},
            "b": {"kind": "answer_contains_any", "fragments": ["twelve"]},
        },
        _STEPS,
        _ANSWER,
    )
    assert out == {"a": True, "b": True}


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown metric kind"):
        score_metric({"kind": "nope"}, [], "")
