"""EU AI Act rule set — versioned legal DATA for the verdict engine (AIC-2, ADR-F057).

The article references, prohibited-practice map, and Annex III area map the
deterministic engine cites — kept HERE, out of :mod:`app.aiact.classify`, so a legal
update is a data + version bump, not an engine rewrite (ADR-F057: "law content is
versioned data, not code").

**Grounding (web-researched 2026-07-01).** Regulation (EU) 2024/1689 as amended by
the **Digital Omnibus** (Council final green light 29 June 2026; EP endorsement 16
June 2026; publication imminent). The Omnibus did **not** change the classification
TEST (Art 5 / Art 6 / Annex III / Art 6(3) / Art 50 remain the baseline text); it
deferred application DATES (those live in AIC-6's regulatory calendar, not this
engine) and added ONE prohibited practice — non-consensual intimate imagery / CSAM
generators (Art 5). This engine therefore encodes the settled classification test
plus that one Art 5 branch; the phased dates are out of scope here (AIC-2 cites
articles, not deadlines).

**Not legal advice.** These predicates are a good-faith encoding of primary sources,
NOT a substitute for counsel. Every verdict carries this ``RULESET_VERSION`` and, on
any predicate that leans on unsettled guidance (Art 6(3) derogations), a
``draft_basis`` flag. A verdict is authoritative only after counsel validates the
rule set (ADR-F057 open item #8).
"""

from __future__ import annotations

from app.schemas.classification import AnnexIIIArea, Art5Trigger

# Bump on any change to the encoded rules or article refs. Format:
# "<regulation>+<amendment>-<amendment-date>.v<n>". The verdict_hash folds this in,
# so a rule-set change visibly invalidates every prior verdict.
RULESET_VERSION = "2024-1689+omnibus-2026-06-30.v1"

# Surfaced with every verdict (API/UI) — the module is a decision-support record, not
# legal advice, until the rule set is counsel-reviewed (ADR-F057).
DISCLAIMER = (
    "Deterministic EU AI Act classification (Regulation (EU) 2024/1689 as amended by "
    "the Digital Omnibus, 2026-06-30). Decision-support only, pending counsel review — "
    "not legal advice."
)

# Article 5 — one citation per prohibited practice. The Digital Omnibus added the
# NCII/CSAM branch (Art 5(1) new point).
_ART5_REFS: dict[Art5Trigger, tuple[str, ...]] = {
    Art5Trigger.SUBLIMINAL_MANIPULATION: ("Art 5(1)(a)",),
    Art5Trigger.EXPLOITS_VULNERABILITIES: ("Art 5(1)(b)",),
    Art5Trigger.SOCIAL_SCORING: ("Art 5(1)(c)",),
    Art5Trigger.PREDICTIVE_POLICING_PROFILING: ("Art 5(1)(d)",),
    Art5Trigger.UNTARGETED_FACIAL_SCRAPING: ("Art 5(1)(e)",),
    Art5Trigger.EMOTION_RECOGNITION_WORKPLACE_EDUCATION: ("Art 5(1)(f)",),
    Art5Trigger.BIOMETRIC_CATEGORISATION_SENSITIVE: ("Art 5(1)(g)",),
    Art5Trigger.REALTIME_RBI_PUBLIC_LE: ("Art 5(1)(h)",),
    # Digital Omnibus (2026-06-30) addition — NCII / CSAM generators ("nudifiers").
    Art5Trigger.NCII_CSAM_GENERATION: ("Art 5 (Digital Omnibus — NCII/CSAM)",),
}

# Annex III — one citation per high-risk use-case area (Annex III points 1-8).
_ANNEX_III_REFS: dict[AnnexIIIArea, tuple[str, ...]] = {
    AnnexIIIArea.BIOMETRICS: ("Annex III(1)",),
    AnnexIIIArea.CRITICAL_INFRASTRUCTURE: ("Annex III(2)",),
    AnnexIIIArea.EDUCATION: ("Annex III(3)",),
    AnnexIIIArea.EMPLOYMENT: ("Annex III(4)",),
    AnnexIIIArea.ESSENTIAL_SERVICES_CREDIT_INSURANCE: ("Annex III(5)",),
    AnnexIIIArea.LAW_ENFORCEMENT: ("Annex III(6)",),
    AnnexIIIArea.MIGRATION_BORDER: ("Annex III(7)",),
    AnnexIIIArea.JUSTICE_DEMOCRACY: ("Annex III(8)",),
}

# Stable one-off citations used by the engine.
ART5_PROHIBITED_REF = "Art 5"
ART6_1_REF = "Art 6(1)"
ANNEX_I_REF = "Annex I"
ART6_2_REF = "Art 6(2)"
ART6_3_REF = "Art 6(3)"
ART6_3_PROFILING_REF = "Art 6(3) final subparagraph (profiling)"
ART50_REF = "Art 50"
ART50_GPAI_REF = "Art 50(4)"


def art5_refs(trigger: Art5Trigger) -> tuple[str, ...]:
    """Article citations for a prohibited-practice trigger (specific point + Art 5)."""
    specific = _ART5_REFS.get(trigger, ())
    return (ART5_PROHIBITED_REF, *specific)


def annex_iii_refs(area: AnnexIIIArea) -> tuple[str, ...]:
    """Article citations for an Annex III area (Art 6(2) + the specific Annex III point)."""
    specific = _ANNEX_III_REFS.get(area, ())
    return (ART6_2_REF, *specific)
