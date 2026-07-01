"""Classification facts schema — the structural presence gate (AIC-2, ADR-F057).

Proves the invariant the whole module rests on: the model can supply FACTS and can
NEVER supply a verdict. A ``tier``/``risk_tier``/``route`` field is a hard rejection
(``extra="forbid"``), and the coherence validators reject incoherent fact combos
(reject, don't sanitize).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.classification import (
    AnnexIIIArea,
    Art6_3Condition,
    ClassificationFactsInput,
)


def test_empty_is_valid_all_defaults() -> None:
    facts = ClassificationFactsInput()
    assert facts.annex_iii_area is AnnexIIIArea.NONE
    assert facts.art6_3_derogation_condition is Art6_3Condition.NONE


@pytest.mark.parametrize("smuggled", ["tier", "risk_tier", "route", "verdict"])
def test_verdict_fields_are_rejected(smuggled: str) -> None:
    # The presence gate: there is no way to hand the engine a tier through the facts.
    with pytest.raises(ValidationError):
        ClassificationFactsInput(**{smuggled: "high"})  # type: ignore[arg-type]


def test_off_enum_annex_iii_area_rejected() -> None:
    with pytest.raises(ValidationError):
        ClassificationFactsInput(annex_iii_area="totally_made_up")  # type: ignore[arg-type]


def test_third_party_ca_without_annex_i_rejected() -> None:
    with pytest.raises(ValidationError):
        ClassificationFactsInput(requires_third_party_conformity_assessment=True)


def test_derogation_without_annex_iii_rejected() -> None:
    with pytest.raises(ValidationError):
        ClassificationFactsInput(art6_3_derogation_condition=Art6_3Condition.NARROW_PROCEDURAL_TASK)


def test_profiling_without_annex_iii_rejected() -> None:
    with pytest.raises(ValidationError):
        ClassificationFactsInput(profiling_of_natural_persons=True)


def test_derogation_with_annex_iii_ok() -> None:
    facts = ClassificationFactsInput(
        annex_iii_area=AnnexIIIArea.EMPLOYMENT,
        art6_3_derogation_condition=Art6_3Condition.NARROW_PROCEDURAL_TASK,
    )
    assert facts.art6_3_derogation_condition is Art6_3Condition.NARROW_PROCEDURAL_TASK
