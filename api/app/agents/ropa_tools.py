"""ROPA agent tools — PRIV-2 (fork, ADR-F018): the validated write path.

The Privacy practice-area Deep Agent gets two guarded ROPA tools over the
matter's :class:`app.models.ropa.ProcessingActivity` register:

* :func:`propose_processing_activity` — the **code-validated write**. The model
  PROPOSES a Records-of-Processing-Activities entry; the tool validates the
  proposal against :class:`app.schemas.ropa.ProcessingActivityInput` (the single
  validation contract — PRIV-1) BEFORE any commit. A proposal that passes is
  written; one that fails is **rejected back to the model with the reason**, so
  the model can fix and re-propose. Agent proposes → code disposes → commit OR
  reject-and-retry; never a silent write, never a silent fix (ADR-F018). A
  rejection is returned as ordinary tool-result text (not raised): the dispatch
  succeeded, the *write* was refused — the model reads the reason and retries.
* :func:`list_processing_activities` — the matter's current register, so the
  agent can see what it has already recorded (and a future read UI is PRIV-3).

**Scoping / authz.** Like the matter document tools, the matter + owner are
B-class parameters (ADR-F004): closure-injected at :func:`build_ropa_tools`,
never model-visible. Every row is scoped to ``binding.project_id`` — which the
composition point already resolved from the run's project AFTER asserting
``Project.owner_id == run.user_id`` (``compose_and_execute_run``). The model
cannot name another project, so there is no cross-matter / cross-user vector at
the tool layer to leak; the project-ownership 404 posture belongs to the PRIV-3
read API, where a project id IS user-supplied. The ``processing_activities``
foreign key (ON DELETE CASCADE) keeps every row anchored to its matter.

Every dispatch passes the :mod:`app.agents.guard` chokepoint FIRST (ADR-F002):
R6 grants exactly these two tool names, R5 re-checks the run is live, one audit
row records the outcome (counts/types/IDs — never the proposal's values).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import MatterBinding
from app.models.ropa import ProcessingActivity
from app.schemas.ropa import ProcessingActivityInput

# The stable key of the Privacy practice area (migration 0053). The composition
# point grants the ROPA tools only to a matter filed under this area.
PRIVACY_AREA_KEY = "privacy"

ROPA_TOOL_NAMES = frozenset({"propose_processing_activity", "list_processing_activities"})

# Cap the register dump so a large matter's tool result stays inside the model's
# working context; the read UI (PRIV-3) is the place to browse a long register.
_LIST_LIMIT = 100


def build_ropa_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the Privacy matter's guarded ROPA tools for one run.

    The closures carry the B-class scope (matter + owner); the guard context
    grants exactly these two tools (R6's grant set).
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=ROPA_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def propose_processing_activity(
        name: str,
        purpose: str,
        lawful_basis: str,
        controller_role: str,
        retention: str,
        special_category: bool = False,
        art9_condition: str | None = None,
    ) -> str:
        """Propose one Records-of-Processing-Activities (Article 30) entry.

        The proposal is validated before it is recorded; if it fails you get the
        reasons back and should fix them and call this tool again.

        - ``lawful_basis``: one of consent, contract, legal_obligation,
          vital_interests, public_task, legitimate_interests (Article 6(1)).
        - ``controller_role``: controller, joint_controller, or processor.
        - ``retention``: required — how long the data is kept (e.g. "7 years
          after contract end").
        - ``special_category``: true if the activity processes special-category
          data (Article 9); then ``art9_condition`` is REQUIRED and must be one
          of explicit_consent, employment_social_security, vital_interests,
          not_for_profit_body, made_public_by_data_subject, legal_claims,
          substantial_public_interest, health_or_social_care, public_health,
          archiving_research_statistics. Leave ``art9_condition`` unset when the
          activity is not special-category.
        """
        return await guarded_dispatch(
            "propose_processing_activity",
            lambda db: _propose(
                db,
                binding,
                name=name,
                purpose=purpose,
                lawful_basis=lawful_basis,
                controller_role=controller_role,
                retention=retention,
                special_category=special_category,
                art9_condition=art9_condition,
            ),
            ctx,
        )

    async def list_processing_activities() -> str:
        """List the processing activities already recorded for this matter.

        Returns the matter's ROPA register — each entry's name, purpose, lawful
        basis, role, retention, and special-category condition — so you can see
        what is already recorded before proposing more.
        """
        return await guarded_dispatch(
            "list_processing_activities", lambda db: _list(db, binding), ctx
        )

    return [propose_processing_activity, list_processing_activities]


async def _propose(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    name: str,
    purpose: str,
    lawful_basis: str,
    controller_role: str,
    retention: str,
    special_category: bool,
    art9_condition: str | None,
) -> str:
    """Validate the proposal, then write it (or return the rejection)."""
    try:
        proposal = ProcessingActivityInput(
            name=name,
            purpose=purpose,
            lawful_basis=lawful_basis,  # type: ignore[arg-type]  # str → enum coercion
            controller_role=controller_role,  # type: ignore[arg-type]
            retention=retention,
            special_category=special_category,
            art9_condition=art9_condition,  # type: ignore[arg-type]
        )
    except ValidationError as exc:
        return _rejection_text(exc)

    db.add(
        ProcessingActivity(
            project_id=binding.project_id,
            name=proposal.name,
            purpose=proposal.purpose,
            lawful_basis=proposal.lawful_basis.value,
            controller_role=proposal.controller_role.value,
            retention=proposal.retention,
            special_category=proposal.special_category,
            art9_condition=(proposal.art9_condition.value if proposal.art9_condition else None),
        )
    )
    # Flush (not commit) so a DB CHECK violation — the defense-in-depth mirror of
    # the same invariants — surfaces INSIDE the guard's try (audited as an error,
    # rolled back). The guard commits the row together with its audit row.
    await db.flush()
    return (
        f'Recorded processing activity "{proposal.name}" in this matter\'s ROPA '
        f"(lawful basis: {proposal.lawful_basis.value}; role: "
        f"{proposal.controller_role.value}; retention: {proposal.retention})."
    )


async def _list(db: AsyncSession, binding: MatterBinding) -> str:
    """Format the matter's ROPA register (oldest first)."""
    rows = (
        (
            await db.execute(
                select(ProcessingActivity)
                .where(ProcessingActivity.project_id == binding.project_id)
                .order_by(ProcessingActivity.created_at.asc(), ProcessingActivity.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "This matter's ROPA has no processing activities yet."

    blocks: list[str] = []
    for row in rows:
        sc = (
            f"special-category (Article 9: {row.art9_condition})"
            if row.special_category
            else "not special-category"
        )
        blocks.append(
            f"- {row.name}\n"
            f"  purpose: {row.purpose}\n"
            f"  lawful basis: {row.lawful_basis}; role: {row.controller_role}; "
            f"retention: {row.retention}; {sc}"
        )
    noun = "activity" if len(rows) == 1 else "activities"
    return f"This matter's ROPA — {len(rows)} processing {noun}:\n\n" + "\n".join(blocks)


def _rejection_text(exc: ValidationError) -> str:
    """Turn a Pydantic validation failure into a fix-and-retry message.

    Reports the offending field(s) and the rule each broke (the message carries
    the allowed set for an off-enum value) so the model can correct and
    re-propose — never a silent fix (ADR-F018).
    """
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(activity)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        "Proposal rejected — it does not satisfy the ROPA validation rules. "
        "Nothing was recorded. Fix the following and call "
        "propose_processing_activity again:\n" + "\n".join(problems)
    )
