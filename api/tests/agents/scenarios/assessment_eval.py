"""PRIV-A2/A3 — read-back + scoring for live assessment-build scenario runs.

The assessment-track sibling of :mod:`tests.agents.scenarios.ropa_eval`. A
scenario :class:`~tests.agents.scenarios.harness.Receipt` records only a run's
*shape* (tool names, step count, the final answer). For an assessment-*build*
test the honest measure is the assessment the agent actually wrote — so this
module reads the deployment-global assessment register back (filtered by
``source_project_id``, ADR-F019 provenance), scores it (counts, risk/mitigation
quality, and the ADR-F027 completion integrity), and cleans the rows up so a
live run never pollutes the dev register.

Everything here is pure or read-only except :func:`cleanup_assessment`, which
deletes ONLY the assessments a run stamped with its own ``source_project_id``
(risks + the M:N link rows cascade from the DB FKs). The skill-binding helpers
live in :mod:`ropa_eval` and are reused as-is (they are area-generic).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models.assessment import Assessment

# Bound the agent-written free-text we echo into the committed report. The values
# are the AGENT's own structured output (never a third-party source verbatim), but
# the report is an evidence artifact, not a copy — keep excerpts short.
_TEXT_EXCERPT = 240


# --- assessment register read-back -------------------------------------------


@dataclass
class RiskView:
    """One risk finding within an assessment — observations only."""

    description: str
    likelihood: str
    impact: str
    mitigation: str | None
    status: str

    @property
    def has_documented_mitigation(self) -> bool:
        """The ADR-F027 notion of a non-blank mitigation (not None / whitespace)."""
        return bool(self.mitigation and self.mitigation.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": _excerpt(self.description, _TEXT_EXCERPT),
            "likelihood": self.likelihood,
            "impact": self.impact,
            "mitigation": _excerpt(self.mitigation, _TEXT_EXCERPT) if self.mitigation else None,
            "status": self.status,
            "has_documented_mitigation": self.has_documented_mitigation,
        }


@dataclass
class AssessmentView:
    """One assessment plus its risks and linked activities — observations only."""

    type: str
    title: str
    status: str
    risk_rating: str | None
    summary_excerpt: str | None
    conditions_excerpt: str | None
    risks: list[RiskView]
    linked_activities: list[str]

    @property
    def is_high_risk(self) -> bool:
        """High-risk for the completion rule: a DPIA, or any ``high`` rating (ADR-F027)."""
        return self.type == "dpia" or self.risk_rating == "high"

    @property
    def completion_rule_satisfied(self) -> bool:
        """A completed high-risk assessment must carry >=1 documented mitigation.

        The headline ADR-F027 invariant, read back off the persisted record. For a
        non-completed or non-high-risk assessment the rule does not bite → True.
        """
        if self.status != "completed" or not self.is_high_risk:
            return True
        return any(r.has_documented_mitigation for r in self.risks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "risk_rating": self.risk_rating,
            "summary_excerpt": self.summary_excerpt,
            "conditions_excerpt": self.conditions_excerpt,
            "risks": [r.to_dict() for r in self.risks],
            "linked_activities": self.linked_activities,
            "is_high_risk": self.is_high_risk,
            "completion_rule_satisfied": self.completion_rule_satisfied,
        }


@dataclass
class AssessmentSnapshot:
    """The assessments a run produced, scoped to its ``source_project_id``."""

    assessments: list[AssessmentView] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"assessments": [a.to_dict() for a in self.assessments]}


async def snapshot_assessment(
    factory: async_sessionmaker[AsyncSession], source_project_id: Any
) -> AssessmentSnapshot:
    """Read back every assessment a run stamped with ``source_project_id`` (ADR-F019).

    Risks and linked processing activities are eager-loaded. The read is RAW
    (no API-layer projection); linked-activity names are taken straight off the
    M:N relationship so a test can see exactly what the agent linked.
    """
    async with factory() as db:
        rows = (
            (
                await db.execute(
                    select(Assessment)
                    .where(Assessment.source_project_id == source_project_id)
                    .options(
                        selectinload(Assessment.risks),
                        selectinload(Assessment.processing_activities),
                    )
                    .order_by(Assessment.created_at, Assessment.title)
                )
            )
            .scalars()
            .all()
        )

    snapshot = AssessmentSnapshot()
    for a in rows:
        snapshot.assessments.append(
            AssessmentView(
                type=a.type,
                title=a.title,
                status=a.status,
                risk_rating=a.risk_rating,
                summary_excerpt=_excerpt(a.summary, _TEXT_EXCERPT) if a.summary else None,
                conditions_excerpt=(
                    _excerpt(a.conditions, _TEXT_EXCERPT) if a.conditions else None
                ),
                risks=[
                    RiskView(
                        description=r.description,
                        likelihood=r.likelihood,
                        impact=r.impact,
                        mitigation=r.mitigation,
                        status=r.status,
                    )
                    for r in a.risks
                ],
                linked_activities=[p.name for p in a.processing_activities],
            )
        )
    return snapshot


def _excerpt(value: str, limit: int) -> str:
    return value[:limit] + ("…" if len(value) > limit else "")


# --- scoring (pure) ----------------------------------------------------------


def score_assessment(snapshot: AssessmentSnapshot) -> dict[str, Any]:
    """Score an assessment snapshot for completeness + risk quality (pure).

    The required fields (type/title/status) are present by construction — the
    write path rejects a row that lacks them — so the interesting signal is what
    the agent built: how many assessments, of which types/statuses, with how many
    risks, how many of those risks carry a *documented* (non-blank, ADR-F027)
    mitigation, and whether each assessment is linked to a processing activity.

    The load-bearing regression check is ``completion_integrity_ok``: EVERY
    completed high-risk assessment carries at least one documented mitigation.
    That is the headline ADR-F027 invariant — it must hold on any record the
    single, code-validated write path produced; a False here is a real defect
    (or a non-write-path mutation), not a model-quality observation.
    """
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    total_risks = 0
    risks_with_mitigation = 0

    per_assessment: list[dict[str, Any]] = []
    for a in snapshot.assessments:
        by_type[a.type] = by_type.get(a.type, 0) + 1
        by_status[a.status] = by_status.get(a.status, 0) + 1
        documented = sum(1 for r in a.risks if r.has_documented_mitigation)
        total_risks += len(a.risks)
        risks_with_mitigation += documented
        per_assessment.append(
            {
                "title": a.title,
                "type": a.type,
                "status": a.status,
                "risk_rating": a.risk_rating,
                "risk_count": len(a.risks),
                "risks_with_documented_mitigation": documented,
                "linked_activity_count": len(a.linked_activities),
                "is_high_risk": a.is_high_risk,
                "completion_rule_satisfied": a.completion_rule_satisfied,
            }
        )

    completed = [a for a in snapshot.assessments if a.status == "completed"]
    linked = sum(1 for a in snapshot.assessments if a.linked_activities)
    n = len(snapshot.assessments)

    return {
        "counts": {
            "assessments": n,
            "by_type": dict(sorted(by_type.items())),
            "by_status": dict(sorted(by_status.items())),
            "completed": len(completed),
            "total_risks": total_risks,
            "risks_with_documented_mitigation": risks_with_mitigation,
        },
        "fractions": {
            "assessments_linked_to_activity": round(linked / n, 2) if n else 0.0,
            "risks_with_documented_mitigation": (
                round(risks_with_mitigation / total_risks, 2) if total_risks else 0.0
            ),
        },
        "per_assessment": per_assessment,
        # The ADR-F027 headline invariant, read back off the persisted record.
        "completion_integrity_ok": all(a.completion_rule_satisfied for a in snapshot.assessments),
    }


# --- dev-DB hygiene ----------------------------------------------------------


async def cleanup_assessment(
    factory: async_sessionmaker[AsyncSession], source_project_id: Any
) -> None:
    """Delete ONLY the assessments a run stamped with ``source_project_id``.

    The register is deployment-global with ``source_project_id`` ON DELETE SET
    NULL (provenance, not ownership), so the harness's project teardown would
    orphan these rows. Deleting an assessment cascades its risks (FK CASCADE) and
    its M:N link rows (link-table FKs CASCADE both ends); the linked processing
    activities themselves survive (a different provenance — cleaned by
    :func:`~tests.agents.scenarios.ropa_eval.cleanup_register`). Call before the
    matter teardown nulls the provenance.
    """
    async with factory() as db:
        await db.execute(
            delete(Assessment).where(Assessment.source_project_id == source_project_id)
        )
        await db.commit()
