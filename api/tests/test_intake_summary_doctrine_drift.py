"""Drift guard: the thread-summary bounds, the tool, and the doctrine that teaches it.

INTAKE-5a (ADR-F086 ruling 7) spreads ONE fact — "conclude with at most five short
titled bullets, ≤40 and ≤300 characters" — across four files that cannot import each
other's intent:

* ``app.schemas.intake`` enforces it (the only place that rejects);
* ``app.agents.intake_tools.record_intake_outcome``'s signature and docstring are what
  the MODEL sees when it decides what to send;
* ``app.agents.composition.INTAKE_DOCTRINE`` + ``app.agents.intake_prompt`` tell every
  intake run the obligation exists at all;
* ``skills/intake-triage/SKILL.md`` teaches the shape.

Loosen the schema and forget the skill and the model keeps writing 40-character titles
it no longer has to; tighten the schema and forget the skill and every run starts its
life with a rejection it was coached into. Neither shows up in a test of any single
file, so this one reads all four.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.composition import INTAKE_DOCTRINE
from app.agents.intake_prompt import IntakeEmailView, build_intake_prompt
from app.agents.intake_tools import build_intake_tools
from app.agents.tools import MatterBinding
from app.schemas.intake import (
    INTAKE_SUMMARY_MAX_ITEMS,
    INTAKE_SUMMARY_TEXT_MAX_CHARS,
    INTAKE_SUMMARY_TITLE_MAX_CHARS,
    RecordIntakeOutcomeInput,
)

pytestmark = pytest.mark.unit

_SKILL = Path(__file__).resolve().parents[2] / "skills" / "intake-triage" / "SKILL.md"

# The doctrine spells the item cap out in words, as prose should; the schema counts.
# Keeping the two tied together is the whole point of this file.
_SPELLED = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def _outcome_tool() -> Callable[..., Any]:
    """The real ``record_intake_outcome`` closure — no DB is touched by building it."""
    tools = build_intake_tools(
        async_sessionmaker(),
        run_id=uuid.uuid4(),
        binding=MatterBinding(
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="m",
            privileged=False,
            minimum_inference_tier=None,
            practice_area_id=None,
        ),
        intake_thread_id=uuid.uuid4(),
    )
    return next(t for t in tools if t.__name__ == "record_intake_outcome")


def test_summary_is_a_required_tool_argument() -> None:
    """The model cannot conclude a thread without an account of it.

    Required, not optional-with-a-default: an optional summary is one the model skips
    on exactly the runs that need it most (the long, messy threads), and the Inbox
    then shows a row that says nothing.
    """
    assert RecordIntakeOutcomeInput.model_fields["summary"].is_required()
    param = inspect.signature(_outcome_tool()).parameters["summary"]
    assert param.default is inspect.Parameter.empty


def test_tool_docstring_states_the_shape_the_schema_enforces() -> None:
    """What the model reads and what the boundary rejects must be the same numbers."""
    doc = " ".join((inspect.getdoc(_outcome_tool()) or "").split())
    assert '"title"' in doc and '"text"' in doc
    assert f"{INTAKE_SUMMARY_TITLE_MAX_CHARS} characters" in doc
    assert f"{INTAKE_SUMMARY_TEXT_MAX_CHARS} characters" in doc
    assert f"to {_SPELLED[INTAKE_SUMMARY_MAX_ITEMS]} bullets" in doc


def test_every_intake_run_is_told_the_summary_is_part_of_concluding() -> None:
    """Both fork-authored instruction surfaces name it — the static area doctrine and
    the per-thread prompt. A model that never hears about the argument meets it only
    as a rejection."""
    assert "summary of the thread so far" in INTAKE_DOCTRINE
    prompt = build_intake_prompt(
        IntakeEmailView(
            thread_ref=str(uuid.uuid4()),
            from_addr="counterparty@example.net",
            to_addrs=["legal-intake@example.com"],
            subject="Please review the attached NDA",
            body_text="Hi, please review the attached mutual NDA.",
        )
    )
    assert "summary of the thread so far" in prompt


def test_skill_doctrine_teaches_the_same_bounds() -> None:
    """The skill is the only place the bullet SHAPE is taught; its numbers are the
    schema's."""
    text = " ".join(_SKILL.read_text(encoding="utf-8").split())
    assert f"at most {INTAKE_SUMMARY_TITLE_MAX_CHARS} characters" in text
    assert f"at most {INTAKE_SUMMARY_TEXT_MAX_CHARS} characters" in text
    assert f"at most {_SPELLED[INTAKE_SUMMARY_MAX_ITEMS]} bullets" in text
    # The rewrite rule is the one thing a reader can get wrong in a way the schema
    # cannot catch: an append validates and is still wrong.
    assert "Rewrite the whole summary every time" in text
    # And the confidentiality carve-out has to reach the summary, or the one place a
    # misdirected/privileged message gets retold is the Inbox row.
    assert "Do not summarise its contents" in text


def test_skill_frontmatter_has_no_unquoted_colon_space() -> None:
    """The loader's known silent-drop trap: a bare ``": "`` inside a frontmatter VALUE
    makes PyYAML read the line as a mapping and the whole skill vanishes from the
    registry with only a warning. ``test_skill_loader`` catches it corpus-wide; this
    keeps the failure local to the file this slice edits (the body, which may contain
    JSON examples, is not YAML and is deliberately not checked)."""
    _, frontmatter, _ = _SKILL.read_text(encoding="utf-8").split("---", 2)
    for line in frontmatter.strip().splitlines():
        key, _, value = line.partition(": ")
        assert ": " not in value, f"unquoted ': ' in frontmatter key {key!r}"
