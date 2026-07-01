"""The deterministic EU AI Act verdict engine (AIC-2, ADR-F057) — the module's IP.

:func:`classify` is a **pure total function** of ``(facts, RULESET_VERSION)``: no LLM
call, no I/O, no key, no clock, no randomness. Given the same facts and rule set it
always returns the same sealed :class:`Verdict` (same ``verdict_hash``) — the property
that makes the legal determination reproducible and auditable *independent of model
quality*, and impossible to argue down in an intake conversation (ADR-F057).

The engine is an ordered waterfall; the FIRST rule that fires sets the tier and route,
and every step appends to ``predicate_trace`` so the reasoning is fully re-derivable:

1. Art 5 prohibited screen (incl. the Digital Omnibus NCII/CSAM branch) → prohibited.
2. Art 6(1) / Annex I — embedded safety component requiring third-party conformity
   assessment → high.
3. Art 6(2) / Annex III — standalone use-case area → high, UNLESS a valid Art 6(3)
   derogation applies (honoured conservatively: flagged ``draft_basis``, and NEVER
   when profiling of natural persons is present — Art 6(3) final subparagraph).
4. Art 50 transparency triggers → limited.
5. otherwise → minimal.

Role (provider/deployer) does NOT affect the tier — it changes *obligations* (AIC-3) —
so it is deliberately absent from the engine's inputs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.aiact import ruleset
from app.schemas.classification import (
    AnnexIIIArea,
    Art5Trigger,
    Art6_3Condition,
    ClassificationFactsInput,
    ClassificationRoute,
    RiskTier,
)


@dataclass(frozen=True)
class PredicateStep:
    """One evaluated rule in the waterfall — the audit trail of the verdict."""

    predicate: str
    value: str
    effect: str

    def as_dict(self) -> dict[str, str]:
        return {"predicate": self.predicate, "value": self.value, "effect": self.effect}


@dataclass(frozen=True)
class Verdict:
    """A sealed, re-derivable risk classification (ADR-F057).

    ``verdict_hash`` is an unsigned SHA-256 content digest over the normalised facts,
    the rule-set version, the tier, the route, and the sorted article refs — tamper
    evidence + idempotency (identical facts + rule set ⇒ identical hash). ``draft_basis``
    is set when the verdict leans on an unsettled predicate (an Art 6(3) derogation).
    """

    tier: RiskTier
    route: ClassificationRoute
    article_refs: tuple[str, ...]
    predicate_trace: tuple[PredicateStep, ...]
    ruleset_version: str
    verdict_hash: str
    draft_basis: bool

    def trace_as_dicts(self) -> list[dict[str, str]]:
        return [step.as_dict() for step in self.predicate_trace]


def _facts_canonical(facts: ClassificationFactsInput) -> str:
    """Deterministic JSON of the validated facts (enums → their string values)."""
    return json.dumps(facts.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def facts_hash(facts: ClassificationFactsInput) -> str:
    """SHA-256 of the normalised facts alone — detects a fact change vs a rule-set change."""
    return hashlib.sha256(_facts_canonical(facts).encode("utf-8")).hexdigest()


def _verdict_hash(
    facts: ClassificationFactsInput,
    tier: RiskTier,
    route: ClassificationRoute,
    article_refs: tuple[str, ...],
) -> str:
    payload = {
        "ruleset_version": ruleset.RULESET_VERSION,
        "facts": facts.model_dump(mode="json"),
        "tier": tier.value,
        "route": route.value,
        "article_refs": sorted(article_refs),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _art50_refs(facts: ClassificationFactsInput, *, is_gpai: bool) -> tuple[str, ...]:
    """Transparency citations for the triggers present (+ Art 50(4) for GPAI output)."""
    refs = [ruleset.ART50_REF]
    if is_gpai:
        refs.append(ruleset.ART50_GPAI_REF)
    return tuple(refs)


def _art50_triggered(facts: ClassificationFactsInput) -> bool:
    return (
        facts.interacts_with_natural_persons
        or facts.generates_synthetic_content
        or facts.emotion_recognition
        or facts.biometric_categorisation
    )


def _seal(
    facts: ClassificationFactsInput,
    tier: RiskTier,
    route: ClassificationRoute,
    article_refs: tuple[str, ...],
    trace: list[PredicateStep],
    *,
    draft_basis: bool,
) -> Verdict:
    return Verdict(
        tier=tier,
        route=route,
        article_refs=article_refs,
        predicate_trace=tuple(trace),
        ruleset_version=ruleset.RULESET_VERSION,
        verdict_hash=_verdict_hash(facts, tier, route, article_refs),
        draft_basis=draft_basis,
    )


def classify(facts: ClassificationFactsInput, *, is_gpai: bool = False) -> Verdict:
    """Compute the sealed risk verdict for a system from its structured facts.

    ``is_gpai`` (read from the register row, never a classification fact) only adds the
    Art 50(4) GPAI-output-marking citation to a limited-tier verdict; it does not move
    the tier (full Chapter V obligations are AIC-4b).
    """
    trace: list[PredicateStep] = []

    # 1 — Art 5 prohibited practices (incl. the Digital Omnibus NCII/CSAM branch).
    if facts.art5_trigger is not Art5Trigger.NONE:
        trace.append(
            PredicateStep("art5_prohibited_practice", facts.art5_trigger.value, "prohibited")
        )
        return _seal(
            facts,
            RiskTier.PROHIBITED,
            ClassificationRoute.ART5_PROHIBITED,
            ruleset.art5_refs(facts.art5_trigger),
            trace,
            draft_basis=False,
        )
    trace.append(PredicateStep("art5_prohibited_practice", "none", "not prohibited"))

    # 2 — Art 6(1) / Annex I embedded safety component with third-party conformity.
    if facts.annex_i_safety_component and facts.requires_third_party_conformity_assessment:
        trace.append(PredicateStep("annex_i_safety_component_third_party_ca", "true", "high-risk"))
        return _seal(
            facts,
            RiskTier.HIGH,
            ClassificationRoute.ANNEX_I_SAFETY_COMPONENT,
            (ruleset.ART6_1_REF, ruleset.ANNEX_I_REF),
            trace,
            draft_basis=False,
        )
    trace.append(
        PredicateStep("annex_i_safety_component_third_party_ca", "false", "not Annex I high-risk")
    )

    # 3 — Art 6(2) / Annex III standalone high-risk (with the Art 6(3) derogation).
    derogated = False
    # When a derogation applies, the residual (limited/minimal) verdict still cites WHY
    # the system was in Annex III scope (Annex III(n)) and the derogation basis (Art
    # 6(3)) — the citation trail is load-bearing for a compliance record of record
    # (ADR-F057). Empty until a derogation fires.
    derogation_refs: tuple[str, ...] = ()
    if facts.annex_iii_area is not AnnexIIIArea.NONE:
        annex_iii_refs = ruleset.annex_iii_refs(facts.annex_iii_area)
        if facts.profiling_of_natural_persons:
            # Art 6(3) final subparagraph: profiling of natural persons never derogates.
            trace.append(
                PredicateStep(
                    "annex_iii_profiling", "true", "high-risk (profiling never derogates)"
                )
            )
            return _seal(
                facts,
                RiskTier.HIGH,
                ClassificationRoute.ANNEX_III,
                (*annex_iii_refs, ruleset.ART6_3_PROFILING_REF),
                trace,
                draft_basis=False,
            )
        if facts.art6_3_derogation_condition is not Art6_3Condition.NONE:
            # Conservative posture (ADR-F057): honour the claimed ground, but mark the
            # verdict draft-basis and fall through for the residual (limited/minimal)
            # tier. The derogation shows in the trace + Art 6(3) ref, not as a route.
            trace.append(
                PredicateStep(
                    "art6_3_derogation",
                    facts.art6_3_derogation_condition.value,
                    "derogated from Annex III high-risk (draft basis)",
                )
            )
            derogated = True
            derogation_refs = (*annex_iii_refs, ruleset.ART6_3_REF)
        else:
            trace.append(PredicateStep("annex_iii_area", facts.annex_iii_area.value, "high-risk"))
            return _seal(
                facts,
                RiskTier.HIGH,
                ClassificationRoute.ANNEX_III,
                annex_iii_refs,
                trace,
                draft_basis=False,
            )
    else:
        trace.append(PredicateStep("annex_iii_area", "none", "not Annex III"))

    # 4 — Art 50 transparency triggers → limited.
    if _art50_triggered(facts):
        triggers = ",".join(
            name
            for name, present in (
                ("interacts_with_natural_persons", facts.interacts_with_natural_persons),
                ("generates_synthetic_content", facts.generates_synthetic_content),
                ("emotion_recognition", facts.emotion_recognition),
                ("biometric_categorisation", facts.biometric_categorisation),
            )
            if present
        )
        trace.append(PredicateStep("art50_transparency", triggers, "limited (transparency)"))
        return _seal(
            facts,
            RiskTier.LIMITED,
            ClassificationRoute.ART50_TRANSPARENCY,
            (*derogation_refs, *_art50_refs(facts, is_gpai=is_gpai)),
            trace,
            draft_basis=derogated,
        )
    trace.append(PredicateStep("art50_transparency", "none", "no transparency trigger"))

    # 5 — minimal risk (carrying the derogation citation trail when one applied).
    trace.append(PredicateStep("minimal", "true", "minimal"))
    return _seal(
        facts,
        RiskTier.MINIMAL,
        ClassificationRoute.MINIMAL,
        derogation_refs,
        trace,
        draft_basis=derogated,
    )
