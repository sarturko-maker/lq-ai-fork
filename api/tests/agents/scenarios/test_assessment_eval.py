"""PRIV-A2 — pure unit tests for the assessment-build scorer (CI, no provider/DB).

The live scenario (`test_assessment_build_scenario.py`) is provider-gated and
self-skips in CI; these tests pin the PURE scoring + integrity logic it relies on,
so the harness's verdict is trustworthy and regressions are caught without a model
or a database. The snapshot read-back + cleanup (a select / delete by provenance)
are exercised end-to-end by the live test.
"""

from __future__ import annotations

from tests.agents.scenarios.assessment_eval import (
    AssessmentSnapshot,
    AssessmentView,
    RiskView,
    score_assessment,
)


def _risk(
    *,
    description: str = "A concrete harm to individuals.",
    likelihood: str = "medium",
    impact: str = "high",
    mitigation: str | None = "Tenant-scoped row-level security on the export query.",
    status: str = "mitigated",
) -> RiskView:
    return RiskView(
        description=description,
        likelihood=likelihood,
        impact=impact,
        mitigation=mitigation,
        status=status,
    )


def _assessment(
    *,
    type: str = "dpia",
    title: str = "AI profiling DPIA",
    status: str = "completed",
    risk_rating: str | None = "high",
    risks: list[RiskView] | None = None,
    linked_activities: list[str] | None = None,
) -> AssessmentView:
    return AssessmentView(
        type=type,
        title=title,
        status=status,
        risk_rating=risk_rating,
        summary_excerpt=None,
        conditions_excerpt=None,
        risks=risks if risks is not None else [_risk()],
        linked_activities=linked_activities
        if linked_activities is not None
        else ["Product analytics"],
    )


class TestRiskView:
    def test_documented_mitigation_requires_non_blank(self) -> None:
        assert _risk(mitigation="real safeguard").has_documented_mitigation is True
        assert _risk(mitigation=None).has_documented_mitigation is False
        assert _risk(mitigation="   ").has_documented_mitigation is False
        assert _risk(mitigation="").has_documented_mitigation is False


class TestAssessmentViewRules:
    def test_is_high_risk_for_dpia_or_high_rating(self) -> None:
        assert _assessment(type="dpia", risk_rating="low").is_high_risk is True
        assert _assessment(type="pia", risk_rating="high").is_high_risk is True
        assert _assessment(type="pia", risk_rating="medium").is_high_risk is False
        assert _assessment(type="lia", risk_rating=None).is_high_risk is False

    def test_completion_rule_only_bites_completed_high_risk(self) -> None:
        # A draft never violates the rule, even with no mitigation.
        assert (
            _assessment(status="draft", risks=[_risk(mitigation=None)]).completion_rule_satisfied
            is True
        )
        # A completed low-risk PIA with no mitigation is fine (rule doesn't bite).
        assert (
            _assessment(
                type="pia", risk_rating="low", risks=[_risk(mitigation=None)]
            ).completion_rule_satisfied
            is True
        )
        # A completed DPIA needs at least one documented mitigation.
        assert _assessment(risks=[_risk(mitigation=None)]).completion_rule_satisfied is False
        assert (
            _assessment(
                risks=[
                    _risk(mitigation=None),
                    _risk(mitigation="pseudonymise user_id at ingest"),
                ]
            ).completion_rule_satisfied
            is True
        )


class TestScoreAssessment:
    def test_empty_snapshot_scores_zero_and_integrity_holds(self) -> None:
        score = score_assessment(AssessmentSnapshot())
        assert score["counts"]["assessments"] == 0
        assert score["counts"]["total_risks"] == 0
        assert score["fractions"]["assessments_linked_to_activity"] == 0.0
        assert score["fractions"]["risks_with_documented_mitigation"] == 0.0
        # Vacuously true — no completed high-risk assessment violates the rule.
        assert score["completion_integrity_ok"] is True

    def test_counts_types_statuses_and_fractions(self) -> None:
        snap = AssessmentSnapshot(
            assessments=[
                _assessment(
                    type="dpia",
                    status="completed",
                    risk_rating="high",
                    risks=[_risk(mitigation="real"), _risk(mitigation=None)],
                    linked_activities=["Product analytics"],
                ),
                _assessment(
                    type="pia",
                    status="draft",
                    risk_rating=None,
                    risks=[_risk(mitigation=None)],
                    linked_activities=[],
                ),
            ]
        )
        score = score_assessment(snap)
        assert score["counts"]["assessments"] == 2
        assert score["counts"]["by_type"] == {"dpia": 1, "pia": 1}
        assert score["counts"]["by_status"] == {"completed": 1, "draft": 1}
        assert score["counts"]["completed"] == 1
        assert score["counts"]["total_risks"] == 3
        assert score["counts"]["risks_with_documented_mitigation"] == 1
        # 1 of 2 assessments is linked.
        assert score["fractions"]["assessments_linked_to_activity"] == 0.5
        # 1 of 3 risks carries a documented mitigation.
        assert score["fractions"]["risks_with_documented_mitigation"] == 0.33
        assert score["completion_integrity_ok"] is True

    def test_integrity_flags_a_completed_dpia_without_mitigation(self) -> None:
        # This record could not arise through the validated write path (the tool
        # refuses it) — but the scorer MUST catch it if it ever appears (a second
        # writer, a bad migration). Proves the regression guard has teeth.
        snap = AssessmentSnapshot(
            assessments=[
                _assessment(
                    status="completed",
                    risk_rating="high",
                    risks=[_risk(mitigation=None)],
                )
            ]
        )
        score = score_assessment(snap)
        assert score["completion_integrity_ok"] is False
        assert score["per_assessment"][0]["completion_rule_satisfied"] is False

    def test_per_assessment_shape(self) -> None:
        snap = AssessmentSnapshot(assessments=[_assessment()])
        row = score_assessment(snap)["per_assessment"][0]
        assert row["type"] == "dpia"
        assert row["status"] == "completed"
        assert row["risk_rating"] == "high"
        assert row["risk_count"] == 1
        assert row["risks_with_documented_mitigation"] == 1
        assert row["linked_activity_count"] == 1
        assert row["is_high_risk"] is True
        assert row["completion_rule_satisfied"] is True
