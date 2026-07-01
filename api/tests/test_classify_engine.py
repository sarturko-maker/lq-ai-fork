"""Golden fact→verdict table for the deterministic engine (AIC-2, ADR-F057).

The real legal-logic gate: pure, $0, no model, no DB. Every waterfall branch is
pinned to an expected (tier, route) with the key article refs asserted, so a rule
regression is caught deterministically. Also proves the two ADR-F057 invariants the
whole module rests on: the verdict is REPRODUCIBLE (identical facts ⇒ identical hash)
and the ordering is correct (a higher tier always wins).
"""

from __future__ import annotations

from app.aiact.classify import classify
from app.schemas.classification import (
    AnnexIIIArea,
    Art5Trigger,
    Art6_3Condition,
    ClassificationFactsInput,
    ClassificationRoute,
    RiskTier,
)


def _facts(**kw: object) -> ClassificationFactsInput:
    return ClassificationFactsInput(**kw)  # type: ignore[arg-type]


# --- terminal tiers, one per branch ---------------------------------------------


def test_empty_facts_are_minimal() -> None:
    v = classify(_facts())
    assert v.tier is RiskTier.MINIMAL
    assert v.route is ClassificationRoute.MINIMAL
    assert v.article_refs == ()
    assert v.draft_basis is False
    assert v.ruleset_version.startswith("2024-1689+omnibus-2026-06-30")


def test_art5_trigger_is_prohibited() -> None:
    v = classify(_facts(art5_trigger=Art5Trigger.SOCIAL_SCORING))
    assert v.tier is RiskTier.PROHIBITED
    assert v.route is ClassificationRoute.ART5_PROHIBITED
    assert "Art 5" in v.article_refs
    assert "Art 5(1)(c)" in v.article_refs


def test_new_omnibus_ncii_csam_is_prohibited() -> None:
    # The Digital Omnibus (2026-06-30) addition must classify as prohibited.
    v = classify(_facts(art5_trigger=Art5Trigger.NCII_CSAM_GENERATION))
    assert v.tier is RiskTier.PROHIBITED
    assert any("NCII/CSAM" in r for r in v.article_refs)


def test_annex_i_safety_component_with_third_party_ca_is_high() -> None:
    v = classify(
        _facts(
            annex_i_safety_component=True,
            requires_third_party_conformity_assessment=True,
        )
    )
    assert v.tier is RiskTier.HIGH
    assert v.route is ClassificationRoute.ANNEX_I_SAFETY_COMPONENT
    assert "Art 6(1)" in v.article_refs
    assert "Annex I" in v.article_refs


def test_annex_i_safety_component_without_third_party_ca_is_minimal() -> None:
    # Annex I embedding without a third-party conformity assessment is not Art 6(1) high-risk.
    v = classify(_facts(annex_i_safety_component=True))
    assert v.tier is RiskTier.MINIMAL


def test_annex_iii_area_is_high() -> None:
    v = classify(_facts(annex_iii_area=AnnexIIIArea.EMPLOYMENT))
    assert v.tier is RiskTier.HIGH
    assert v.route is ClassificationRoute.ANNEX_III
    assert "Art 6(2)" in v.article_refs
    assert "Annex III(4)" in v.article_refs


def test_annex_iii_credit_scoring_is_high() -> None:
    v = classify(_facts(annex_iii_area=AnnexIIIArea.ESSENTIAL_SERVICES_CREDIT_INSURANCE))
    assert v.tier is RiskTier.HIGH
    assert "Annex III(5)" in v.article_refs


def test_art50_chatbot_is_limited() -> None:
    v = classify(_facts(interacts_with_natural_persons=True))
    assert v.tier is RiskTier.LIMITED
    assert v.route is ClassificationRoute.ART50_TRANSPARENCY
    assert "Art 50" in v.article_refs


def test_gpai_output_adds_art50_4_ref() -> None:
    v = classify(_facts(generates_synthetic_content=True), is_gpai=True)
    assert v.tier is RiskTier.LIMITED
    assert "Art 50(4)" in v.article_refs


# --- Art 6(3) derogation (conservative posture, ADR-F057) -----------------------


def test_annex_iii_derogation_drops_to_minimal_but_flags_draft_basis() -> None:
    v = classify(
        _facts(
            annex_iii_area=AnnexIIIArea.EMPLOYMENT,
            art6_3_derogation_condition=Art6_3Condition.NARROW_PROCEDURAL_TASK,
        )
    )
    assert v.tier is RiskTier.MINIMAL
    assert v.draft_basis is True
    assert any(s.predicate == "art6_3_derogation" for s in v.predicate_trace)
    # A derogated verdict of record still cites the Annex III scope + the Art 6(3) basis.
    assert "Art 6(3)" in v.article_refs
    assert any("Annex III" in r for r in v.article_refs)


def test_annex_iii_derogation_with_art50_trigger_is_limited_draft_basis() -> None:
    v = classify(
        _facts(
            annex_iii_area=AnnexIIIArea.EDUCATION,
            art6_3_derogation_condition=Art6_3Condition.PREPARATORY_TASK,
            interacts_with_natural_persons=True,
        )
    )
    assert v.tier is RiskTier.LIMITED
    assert v.draft_basis is True
    # Both the derogation trail and the Art 50 basis are cited.
    assert "Art 6(3)" in v.article_refs
    assert "Art 50" in v.article_refs


def test_profiling_never_derogates() -> None:
    # Even with a derogation ground claimed, profiling of natural persons stays high-risk.
    v = classify(
        _facts(
            annex_iii_area=AnnexIIIArea.EMPLOYMENT,
            profiling_of_natural_persons=True,
            art6_3_derogation_condition=Art6_3Condition.NARROW_PROCEDURAL_TASK,
        )
    )
    assert v.tier is RiskTier.HIGH
    assert v.draft_basis is False
    assert any("Art 6(3)" in r for r in v.article_refs)


# --- ordering + sealing ---------------------------------------------------------


def test_art5_beats_annex_iii() -> None:
    v = classify(
        _facts(
            art5_trigger=Art5Trigger.SOCIAL_SCORING,
            annex_iii_area=AnnexIIIArea.LAW_ENFORCEMENT,
        )
    )
    assert v.tier is RiskTier.PROHIBITED


def test_annex_i_beats_annex_iii() -> None:
    v = classify(
        _facts(
            annex_i_safety_component=True,
            requires_third_party_conformity_assessment=True,
            annex_iii_area=AnnexIIIArea.BIOMETRICS,
        )
    )
    assert v.route is ClassificationRoute.ANNEX_I_SAFETY_COMPONENT


def test_verdict_hash_is_reproducible() -> None:
    facts = _facts(annex_iii_area=AnnexIIIArea.EMPLOYMENT)
    assert classify(facts).verdict_hash == classify(facts).verdict_hash


def test_different_facts_change_the_hash() -> None:
    a = classify(_facts(annex_iii_area=AnnexIIIArea.EMPLOYMENT))
    b = classify(_facts(annex_iii_area=AnnexIIIArea.EDUCATION))
    assert a.verdict_hash != b.verdict_hash


def test_gpai_flag_changes_the_hash_for_same_facts() -> None:
    facts = _facts(generates_synthetic_content=True)
    # is_gpai adds the Art 50(4) ref → the sealed article_refs differ → hash differs.
    assert classify(facts, is_gpai=False).verdict_hash != classify(facts, is_gpai=True).verdict_hash


def test_trace_is_serialisable_dicts() -> None:
    v = classify(_facts(annex_iii_area=AnnexIIIArea.EMPLOYMENT))
    dicts = v.trace_as_dicts()
    assert all(set(d) == {"predicate", "value", "effect"} for d in dicts)
