"""Assessment agent tools — PRIV-A2 (fork, ADR-F018/F019/F027): the validated write path.

The assessment-track sibling of :mod:`app.agents.ropa_tools`. The Privacy
practice-area Deep Agent maintains the company's **deployment-global** assessment
record (ADR-F019 — LQ.AI is single-tenant; the register is the company's standing
accountability record, not a per-matter artifact): PIA / DPIA / LIA / TIA records
(:class:`~app.models.assessment.Assessment`) and the risk findings within them
(:class:`~app.models.assessment.Risk`), linked to the ROPA processing activities
they cover.

Guarded, code-validated tools (agent proposes → code disposes → commit OR
reject-and-retry; never a silent write/fix — ADR-F018):

* :func:`propose_assessment` — the code-validated write of a PIA/DPIA/LIA/TIA. The
  model PROPOSES; the tool validates against
  :class:`app.schemas.assessment.AssessmentInput` (PRIV-A1) BEFORE commit; a pass
  is written, a failure is rejected back to the model with the reasons.
* :func:`add_risk` — same loop for a risk finding within an assessment
  (:class:`app.schemas.assessment.RiskInput`), the CASCADE child of its parent.
* :func:`complete_assessment` — the transition to ``completed``, gated by the
  headline cross-row invariant (ADR-F027): a DPIA — or any ``high``-rated
  assessment — cannot be completed unless ≥1 of its risks carries a non-blank
  mitigation. This is the only write path (besides a create-completed) that can
  reach ``completed``, so it is where :func:`validate_assessment_completable`
  lives on the live path.
* :func:`link_assessment_to_activity` — record that an assessment covers a ROPA
  processing activity (the M:N link), by the IDs the list tools surface.
* :func:`list_assessments` — the current assessment register (with IDs), so the
  agent can see what exists and link/complete records.

**Scope / authz (ADR-F019).** The register is company-wide, NOT matter- or
user-scoped — so the tools do not filter by ``project_id``. The matter still
governs *whether* these tools exist (the composition point grants them only to a
matter filed under the Privacy area) and the ``guarded_dispatch`` chokepoint
governs *whether this run may write* (R6 grant set, R5 live re-check, one audit
row per dispatch — counts/types/IDs, never the proposal's values). The run's
matter is stamped onto new rows as ``source_project_id`` (provenance only).

The agent reaches ROPA activity IDs through the ROPA tools' ``list_processing_activities``
(a Privacy matter is granted both tool sets at the composition point), so this
module does not re-export an activity list. A run-scoped change ledger (the ROPA
live changed-row highlight, PRIV-9b) has no consumer until the assessment read UI
lands (PRIV-A3), so it is deliberately not wired here.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import MatterBinding
from app.models.assessment import Assessment, Risk, assessment_processing_activities
from app.models.ropa import ProcessingActivity
from app.schemas.assessment import (
    AssessmentInput,
    AssessmentStatus,
    AssessmentType,
    RiskInput,
    RiskLevel,
    validate_assessment_completable,
)

ASSESSMENT_TOOL_NAMES = frozenset(
    {
        "propose_assessment",
        "add_risk",
        "complete_assessment",
        "link_assessment_to_activity",
        "list_assessments",
    }
)

# Cap the register dump so a large register's tool result stays inside the model's
# working context; the read UI (PRIV-A3) is the place to browse a long register.
_LIST_LIMIT = 100


def build_assessment_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the Privacy matter's guarded assessment tools for one run.

    The guard context grants exactly the assessment tool names (R6's grant set).
    The run's matter (``binding.project_id``) is closure-injected as row provenance
    (``source_project_id``), never as a scoping filter (ADR-F019).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=ASSESSMENT_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def propose_assessment(
        type: str,
        title: str,
        summary: str | None = None,
        status: str = "draft",
        risk_rating: str | None = None,
        conditions: str | None = None,
    ) -> str:
        """Propose one privacy assessment (PIA / DPIA / LIA / TIA).

        The proposal is validated before it is recorded; if it fails you get the
        reasons back and should fix them and call this tool again. Create the
        assessment as a ``draft`` first, add its risks (add_risk), then move it to
        ``completed`` (complete_assessment) — a high-risk assessment cannot be
        created already-completed because it has no documented risk yet.

        - ``type``: one of pia (privacy impact assessment), dpia (Article 35
          data-protection impact assessment), lia (legitimate-interests
          assessment), tia (transfer impact assessment).
        - ``title``: a short name for the assessment (required).
        - ``summary``: what the assessment covers (optional).
        - ``status``: one of draft, in_progress, completed (defaults to draft). A
          ``completed`` assessment MUST carry a risk_rating.
        - ``risk_rating``: the overall residual rating — one of low, medium, high.
          Leave unset until you have assessed; required to complete.
        - ``conditions``: required mitigations/conditions before the processing may
          proceed (free text; optional).
        """
        return await guarded_dispatch(
            "propose_assessment",
            lambda db: _propose_assessment(
                db,
                binding,
                type=type,
                title=title,
                summary=summary,
                status=status,
                risk_rating=risk_rating,
                conditions=conditions,
            ),
            ctx,
        )

    async def add_risk(
        assessment_id: str,
        description: str,
        likelihood: str,
        impact: str,
        mitigation: str | None = None,
        owner: str | None = None,
        status: str = "open",
    ) -> str:
        """Add one risk finding to an assessment.

        Pass the assessment id (from list_assessments). The finding is validated
        before recording; a failure comes back with the reasons to fix and re-add.

        - ``description``: what the risk is (required).
        - ``likelihood`` / ``impact``: each one of low, medium, high.
        - ``mitigation``: the safeguard that reduces the risk (free text; document
          a specific, design-tied mitigation — it is what lets a high-risk
          assessment be completed).
        - ``owner``: who owns the mitigation (optional).
        - ``status``: one of open, mitigated, accepted (defaults to open).
        """
        return await guarded_dispatch(
            "add_risk",
            lambda db: _add_risk(
                db,
                assessment_id=assessment_id,
                description=description,
                likelihood=likelihood,
                impact=impact,
                mitigation=mitigation,
                owner=owner,
                status=status,
            ),
            ctx,
        )

    async def complete_assessment(assessment_id: str, risk_rating: str | None = None) -> str:
        """Mark an assessment completed — gated by the high-risk mitigation rule.

        Pass the assessment id (from list_assessments). A completed assessment
        must carry a risk_rating; pass ``risk_rating`` here if it is not already
        set (one of low, medium, high). A DPIA — or any assessment rated ``high``
        — cannot be completed unless at least one of its risks has a documented
        (non-blank) mitigation: if it does not, this is refused with the reason,
        and you should add a mitigated risk (add_risk) and call this again.
        Re-completing an already-completed assessment with no new ``risk_rating``
        is a no-op; passing a ``risk_rating`` re-rates it (still subject to the
        same high-risk mitigation rule).
        """
        return await guarded_dispatch(
            "complete_assessment",
            lambda db: _complete_assessment(
                db, assessment_id=assessment_id, risk_rating=risk_rating
            ),
            ctx,
        )

    async def link_assessment_to_activity(assessment_id: str, processing_activity_id: str) -> str:
        """Record that an assessment covers a ROPA processing activity (the link).

        Pass the IDs shown by list_assessments and list_processing_activities. If
        either ID is unknown — or the activity is retired — the link is refused
        with the reason. Linking an already-linked pair is a no-op.
        """
        return await guarded_dispatch(
            "link_assessment_to_activity",
            lambda db: _link_assessment_to_activity(
                db,
                assessment_id=assessment_id,
                processing_activity_id=processing_activity_id,
            ),
            ctx,
        )

    async def list_assessments() -> str:
        """List the privacy assessments in the company register (with IDs)."""
        return await guarded_dispatch("list_assessments", lambda db: _list_assessments(db), ctx)

    return [
        propose_assessment,
        add_risk,
        complete_assessment,
        link_assessment_to_activity,
        list_assessments,
    ]


async def _propose_assessment(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    type: str,
    title: str,
    summary: str | None,
    status: str,
    risk_rating: str | None,
    conditions: str | None,
) -> str:
    """Validate the proposal, then write it (or return the rejection)."""
    try:
        proposal = AssessmentInput(
            type=type,  # type: ignore[arg-type]  # str → enum coercion
            title=title,
            summary=summary,
            status=status,  # type: ignore[arg-type]
            risk_rating=risk_rating,  # type: ignore[arg-type]
            conditions=conditions,
        )
    except ValidationError as exc:
        return _rejection_text(exc, "propose_assessment")

    # A brand-new assessment created already-completed has no risks yet, so the
    # cross-row headline invariant (ADR-F027) is checked against the empty set —
    # a completed DPIA/high-risk is refused here (it must be built draft-first).
    if proposal.status is AssessmentStatus.COMPLETED:
        try:
            validate_assessment_completable(
                assessment_type=proposal.type,
                risk_rating=proposal.risk_rating,
                status=proposal.status,
                risk_mitigations=[],
            )
        except ValueError as exc:
            return (
                f"Assessment cannot be created already-completed — {exc}. Create it as a "
                "draft, add a risk with a documented mitigation (add_risk), then complete it "
                "(complete_assessment). Nothing was recorded."
            )

    row = Assessment(
        source_project_id=binding.project_id,
        type=proposal.type.value,
        title=proposal.title,
        summary=proposal.summary,
        status=proposal.status.value,
        risk_rating=(proposal.risk_rating.value if proposal.risk_rating else None),
        conditions=proposal.conditions,
    )
    db.add(row)
    # Flush (not commit) so a DB CHECK violation — the defense-in-depth mirror of
    # the within-row invariants — surfaces INSIDE the guard's try (audited as an
    # error, rolled back). The guard commits the row together with its audit row.
    await db.flush()
    rating = f"; risk rating: {proposal.risk_rating.value}" if proposal.risk_rating else ""
    return (
        f'Recorded {proposal.type.value.upper()} assessment "{proposal.title}" in the '
        f"company register (status: {proposal.status.value}{rating})."
    )


async def _add_risk(
    db: AsyncSession,
    *,
    assessment_id: str,
    description: str,
    likelihood: str,
    impact: str,
    mitigation: str | None,
    owner: str | None,
    status: str,
) -> str:
    """Validate the risk proposal + resolve its parent, then write it (or reject)."""
    try:
        proposal = RiskInput(
            description=description,
            likelihood=likelihood,  # type: ignore[arg-type]  # str → enum coercion
            impact=impact,  # type: ignore[arg-type]
            mitigation=mitigation,
            owner=owner,
            status=status,  # type: ignore[arg-type]
        )
    except ValidationError as exc:
        return _rejection_text(exc, "add_risk")

    try:
        aid = uuid.UUID(assessment_id)
    except ValueError:
        return (
            "Risk refused — assessment_id must be an id shown by list_assessments. "
            "Nothing was recorded."
        )
    assessment = await db.get(Assessment, aid)
    if assessment is None:
        return f"Risk refused — no assessment with id {assessment_id}. Nothing was recorded."

    db.add(
        Risk(
            assessment_id=aid,
            description=proposal.description,
            likelihood=proposal.likelihood.value,
            impact=proposal.impact.value,
            mitigation=proposal.mitigation,
            owner=proposal.owner,
            status=proposal.status.value,
        )
    )
    await db.flush()
    return (
        f"Added a {proposal.likelihood.value}/{proposal.impact.value} "
        f'(likelihood/impact) risk to assessment "{assessment.title}".'
    )


async def _complete_assessment(
    db: AsyncSession,
    *,
    assessment_id: str,
    risk_rating: str | None,
) -> str:
    """Move an assessment to ``completed``, enforcing the headline invariant.

    The within-row half (completed ⇒ risk_rating present) and the cross-row half
    (completed DPIA/high-risk ⇒ ≥1 risk with a non-blank mitigation, ADR-F027) are
    both checked here against the persisted risks; a violation is rejected back to
    the model verbatim (never a silent write/fix). The DB CHECK is the within-row
    backstop.
    """
    try:
        aid = uuid.UUID(assessment_id)
    except ValueError:
        return (
            "Completion refused — assessment_id must be an id shown by list_assessments. "
            "Nothing was changed."
        )

    rating: RiskLevel | None = None
    if risk_rating is not None:
        try:
            rating = RiskLevel(risk_rating)
        except ValueError:
            allowed = ", ".join(r.value for r in RiskLevel)
            return (
                f"Completion refused — risk_rating must be one of {allowed}. Nothing was changed."
            )

    assessment = (
        await db.execute(
            select(Assessment).options(selectinload(Assessment.risks)).where(Assessment.id == aid)
        )
    ).scalar_one_or_none()
    if assessment is None:
        return f"Completion refused — no assessment with id {assessment_id}. Nothing was changed."

    if assessment.status == AssessmentStatus.COMPLETED.value and rating is None:
        return f'Assessment "{assessment.title}" is already completed — nothing to do.'

    effective_rating = rating or (
        RiskLevel(assessment.risk_rating) if assessment.risk_rating else None
    )
    if effective_rating is None:
        return (
            "Completion refused — a completed assessment must carry a risk_rating; pass "
            "risk_rating (low, medium or high). Nothing was changed."
        )

    try:
        validate_assessment_completable(
            assessment_type=AssessmentType(assessment.type),
            risk_rating=effective_rating,
            status=AssessmentStatus.COMPLETED,
            risk_mitigations=[r.mitigation for r in assessment.risks],
        )
    except ValueError as exc:
        return (
            f"Completion refused — {exc}. Add a risk with a documented mitigation (add_risk), "
            "then call complete_assessment again. Nothing was changed."
        )

    assessment.status = AssessmentStatus.COMPLETED.value
    assessment.risk_rating = effective_rating.value
    await db.flush()
    return (
        f'Completed {assessment.type.upper()} assessment "{assessment.title}" '
        f"(risk rating: {effective_rating.value})."
    )


async def _link_assessment_to_activity(
    db: AsyncSession,
    *,
    assessment_id: str,
    processing_activity_id: str,
) -> str:
    """Link an assessment to a processing activity after checking both exist (else reject)."""
    try:
        aid = uuid.UUID(assessment_id)
        pa_uuid = uuid.UUID(processing_activity_id)
    except ValueError:
        return (
            "Link refused — assessment_id and processing_activity_id must be the IDs shown by "
            "list_assessments / list_processing_activities. Nothing was linked."
        )

    assessment = await db.get(Assessment, aid)
    activity = await db.get(ProcessingActivity, pa_uuid)
    missing = []
    if assessment is None:
        missing.append(f"no assessment with id {assessment_id}")
    if activity is None:
        missing.append(f"no processing activity with id {processing_activity_id}")
    if missing:
        return "Link refused — " + "; ".join(missing) + ". Nothing was linked."
    assert assessment is not None and activity is not None  # narrowed by the checks above

    # A retired activity has left the live register; never grow a hidden link to
    # it (mirrors the ROPA write path's retired-target guard, ADR-F023).
    if activity.retired_at is not None:
        return (
            f'Link refused — processing activity "{activity.name}" is retired; link a live '
            "activity instead. Nothing was linked."
        )

    existing = (
        await db.execute(
            select(assessment_processing_activities).where(
                assessment_processing_activities.c.assessment_id == aid,
                assessment_processing_activities.c.processing_activity_id == pa_uuid,
            )
        )
    ).first()
    if existing is not None:
        return (
            f'Assessment "{assessment.title}" is already linked to processing activity '
            f'"{activity.name}".'
        )

    await db.execute(
        assessment_processing_activities.insert().values(
            assessment_id=aid, processing_activity_id=pa_uuid
        )
    )
    await db.flush()
    return (
        f'Linked {assessment.type.upper()} assessment "{assessment.title}" to processing '
        f'activity "{activity.name}".'
    )


async def _list_assessments(db: AsyncSession) -> str:
    """Format the company assessment register (oldest first), with IDs for linking."""
    rows = (
        (
            await db.execute(
                select(Assessment)
                .options(
                    selectinload(Assessment.risks),
                    selectinload(Assessment.processing_activities),
                    # "Covers N activities" must reflect LIVE activities only — a
                    # retired activity has left the register (parity with the ROPA
                    # reads; ADR-F023). Without this an orphaned link reads as cover.
                    with_loader_criteria(
                        ProcessingActivity, ProcessingActivity.retired_at.is_(None)
                    ),
                )
                .order_by(Assessment.created_at.asc(), Assessment.title.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "The company has no privacy assessments yet."

    blocks: list[str] = []
    for row in rows:
        rating = row.risk_rating or "unrated"
        n_risks = len(row.risks)
        risk_noun = "risk" if n_risks == 1 else "risks"
        n_act = len(row.processing_activities)
        act_noun = "activity" if n_act == 1 else "activities"
        blocks.append(
            f"- [{row.id}] {row.type.upper()}: {row.title}\n"
            f"  status: {row.status}; risk rating: {rating}; "
            f"{n_risks} {risk_noun}; covers {n_act} {act_noun}"
        )
    noun = "assessment" if len(rows) == 1 else "assessments"
    return f"Company privacy register — {len(rows)} {noun}:\n\n" + "\n".join(blocks)


def _rejection_text(exc: ValidationError, tool_name: str) -> str:
    """Turn a Pydantic validation failure into a fix-and-retry message.

    Reports the offending field(s) and the rule each broke (the message carries
    the allowed set for an off-enum value) so the model can correct and
    re-propose — never a silent fix (ADR-F018).
    """
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(record)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        "Proposal rejected — it does not satisfy the validation rules. "
        f"Nothing was recorded. Fix the following and call {tool_name} again:\n"
        + "\n".join(problems)
    )
