"""AI Compliance agent tools — AIC-1 (fork, ADR-F057/F018/F019): the validated write path.

The AI Compliance practice-area Deep Agent maintains the company's **deployment-global**
register of AI systems under the EU AI Act (Regulation (EU) 2024/1689). The AI-native
twin of :mod:`app.agents.ropa_tools`: guarded, code-validated tools over one entity —
:class:`~app.models.compliance.AiSystem`.

* :func:`propose_ai_system` — the **code-validated write** of one AI-systems register
  entry. The model PROPOSES facts; the tool validates against
  :class:`app.schemas.compliance.AiSystemInput` BEFORE commit; a pass is written, a
  failure is **rejected back to the model with the reason** (agent proposes → code
  disposes → commit OR reject-and-retry; never a silent write/fix — ADR-F018).
* :func:`retire_ai_system` — soft-retire one entry (never destroyed; kept for audit).
* :func:`list_ai_systems` — the current register (with IDs), so the agent sees what
  exists.

**The presence gate (ADR-F057).** These tools record FACTS. There is no tool that
writes a risk tier or a legal role — under the EU AI Act a risk classification is a
*legal determination* owned by the deterministic engine (AIC-2), and the model can
neither mint nor assert it. ``development_origin`` is captured as the raw fact that
*informs* the provider/deployer role; the engine derives the authoritative role.

**Scope / authz (ADR-F019).** The register is company-wide, NOT matter- or
user-scoped — so the tools do not filter reads by ``project_id``. The matter still
governs *whether* these tools exist (the composition point grants them only to a
matter filed under the AI Compliance area) and the ``guarded_dispatch`` chokepoint
governs *whether this run may write* (R6 grant set, R5 live re-check, one audit row
per dispatch — counts/types/IDs, never the proposal's values). The run's matter is
stamped onto new rows as ``source_project_id`` (provenance only) and the area as the
NON-NULL ``practice_area_id`` (ADR-F057/F021 — born flip-ready); both come from the
binding, never from a model argument. A rejection is returned as ordinary
tool-result text (not raised): the dispatch succeeded, the *write* was refused.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.ai_system_changes import AiSystemChangeLedger
from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import MatterBinding
from app.models.compliance import AiSystem
from app.schemas.compliance import AiSystemInput

# The stable key of the AI Compliance practice area (migration 0084). The composition
# point grants these tools only to a matter filed under this area — the string MUST
# equal the seeded ``practice_areas.key`` or the branch never fires.
COMPLIANCE_AREA_KEY = "ai-compliance"

COMPLIANCE_TOOL_NAMES = frozenset(
    {
        "propose_ai_system",
        "list_ai_systems",
        "retire_ai_system",
    }
)

# The register's one top-level entity kind (AIC-1) — the row the UI highlights.
_KIND_AI_SYSTEM = "ai_system"

# Cap the register dump so a large register's tool result stays inside the model's
# working context; the read UI (AIC-1) is the place to browse a long register.
_LIST_LIMIT = 100

# Max length of a soft-retire reason note — mirrors the ``retirement_reason`` CHECK
# in app.models.compliance (defense-in-depth; reject, don't truncate).
_MAX_RETIREMENT_REASON = 1000


def build_compliance_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
    change_ledger: AiSystemChangeLedger | None = None,
) -> list[Callable[..., Any]]:
    """Build the AI Compliance matter's guarded ai_systems register tools for one run.

    The guard context grants exactly the compliance tool names (R6's grant set). The
    run's matter (``binding.project_id``) is closure-injected as row provenance
    (``source_project_id``) and the run's area (``binding.practice_area_id``) as the
    NON-NULL scoping key — never as model arguments, never as scoping filters
    (ADR-F019).

    ``change_ledger`` (ADR-F024) is the run-scoped, B-class (never model-visible)
    sink each mutating tool records its ``(kind, id, verb)`` into after a successful
    flush — drives the cockpit's live changed-row highlight. ``None`` ⇒ no recording.
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=COMPLIANCE_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def propose_ai_system(
        name: str,
        intended_purpose: str,
        lifecycle_status: str,
        development_origin: str,
        is_gpai: bool = False,
        gpai_systemic: bool = False,
        notes: str | None = None,
    ) -> str:
        """Record one AI system in the company's EU AI Act register.

        You record the FACTS about the system; you do NOT decide its risk tier or
        legal role. Those are a legal determination made by the classification
        engine over these facts — they are not yours to assert. The proposal is
        validated before it is recorded; if it fails you get the reasons back and
        should fix them and call this tool again.

        - ``intended_purpose``: what the system is intended to do (required) — the
          single most important fact for classification (it drives the Annex III
          high-risk use-case match and the Article 5 prohibited-practice screen).
        - ``lifecycle_status``: one of in_development, in_service, decommissioned.
        - ``development_origin``: one of in_house (the organisation built it),
          third_party (procured / used as supplied), or hybrid (procured then
          substantially modified in-house). This is the raw fact that informs
          whether the organisation is a provider or a deployer — record the origin;
          the engine decides the role.
        - ``is_gpai``: true if the system embeds or is a general-purpose AI model.
        - ``gpai_systemic``: true if that general-purpose model presents systemic
          risk; only valid when ``is_gpai`` is true.
        - ``notes``: optional free-text (e.g. where the model card / vendor
          conformity documentation lives).
        """
        return await guarded_dispatch(
            "propose_ai_system",
            lambda db: _propose_ai_system(
                db,
                binding,
                name=name,
                intended_purpose=intended_purpose,
                lifecycle_status=lifecycle_status,
                development_origin=development_origin,
                is_gpai=is_gpai,
                gpai_systemic=gpai_systemic,
                notes=notes,
                ledger=change_ledger,
            ),
            ctx,
        )

    async def retire_ai_system(ai_system_id: str, reason: str | None = None) -> str:
        """Retire one AI system from the live register (kept on record for audit).

        Pass the id shown by list_ai_systems. Retiring never destroys the row — it
        leaves the live register but stays on record. ``reason`` is an optional short
        note. If the id is already retired it is a no-op.
        """
        return await guarded_dispatch(
            "retire_ai_system",
            lambda db: _retire_ai_system(db, ai_system_id, reason, ledger=change_ledger),
            ctx,
        )

    async def list_ai_systems() -> str:
        """List the AI systems in the company register (with IDs)."""
        return await guarded_dispatch("list_ai_systems", lambda db: _list_ai_systems(db), ctx)

    return [propose_ai_system, list_ai_systems, retire_ai_system]


async def _propose_ai_system(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    name: str,
    intended_purpose: str,
    lifecycle_status: str,
    development_origin: str,
    is_gpai: bool,
    gpai_systemic: bool,
    notes: str | None,
    ledger: AiSystemChangeLedger | None = None,
) -> str:
    """Validate the proposal, then write it (or return the rejection)."""
    try:
        proposal = AiSystemInput(
            name=name,
            intended_purpose=intended_purpose,
            lifecycle_status=lifecycle_status,  # type: ignore[arg-type]  # str → enum coercion
            development_origin=development_origin,  # type: ignore[arg-type]
            is_gpai=is_gpai,
            gpai_systemic=gpai_systemic,
            notes=notes,
        )
    except ValidationError as exc:
        return _rejection_text(exc, "propose_ai_system")

    if binding.practice_area_id is None:
        # Can't happen: build_compliance_tools is only wired for a matter filed under
        # the AI Compliance area (composition gate), so the binding always carries
        # that area id. Guard explicitly for the NON-NULL practice_area_id scoping key
        # (ADR-F057/F021) — and to narrow the type for the write below.
        return (
            "Recording refused — this matter is not bound to a practice area. Nothing was recorded."
        )

    row = AiSystem(
        practice_area_id=binding.practice_area_id,
        source_project_id=binding.project_id,
        name=proposal.name,
        intended_purpose=proposal.intended_purpose,
        lifecycle_status=proposal.lifecycle_status.value,
        development_origin=proposal.development_origin.value,
        is_gpai=proposal.is_gpai,
        gpai_systemic=proposal.gpai_systemic,
        notes=proposal.notes,
    )
    db.add(row)
    # Flush (not commit) so a DB CHECK violation — the defense-in-depth mirror of the
    # same invariants — surfaces INSIDE the guard's try (audited as an error, rolled
    # back). The guard commits the row together with its audit row.
    await db.flush()
    # ADR-F024: the flushed id is now known — record the live change.
    if ledger is not None:
        ledger.record(_KIND_AI_SYSTEM, row.id, "create")
    return (
        f'Recorded AI system "{proposal.name}" in the company register (lifecycle: '
        f"{proposal.lifecycle_status.value}; origin: {proposal.development_origin.value}"
        f"{_gpai_phrase(proposal.is_gpai, proposal.gpai_systemic)}). Its risk tier and "
        "role are a legal determination for the classification engine over these "
        "facts, not asserted here."
    )


async def _retire_ai_system(
    db: AsyncSession,
    entity_id: str,
    reason: str | None,
    *,
    ledger: AiSystemChangeLedger | None = None,
) -> str:
    """Soft-retire one AI system row (set ``retired_at``); never delete it.

    Idempotent (an already-retired row is a friendly no-op); an unknown id is refused
    with the reason (never a silent change). ``reason`` is rejected — not silently
    truncated — if it exceeds the stored length (ADR-F018: reject, don't sanitize).
    """
    try:
        eid = uuid.UUID(entity_id)
    except ValueError:
        return "Retire refused — the id must be one shown by list_ai_systems. Nothing was changed."
    if reason is not None and len(reason.strip()) > _MAX_RETIREMENT_REASON:
        return (
            f"Retire refused — reason is too long (max {_MAX_RETIREMENT_REASON} characters). "
            "Shorten it and call again. Nothing was changed."
        )
    row = await db.get(AiSystem, eid)
    if row is None:
        return f"Retire refused — no AI system with id {entity_id}. Nothing was changed."
    if row.retired_at is not None:
        return f'The AI system "{row.name}" is already retired — nothing to do.'
    row.retired_at = datetime.now(UTC)
    if reason is not None and reason.strip():
        row.retirement_reason = reason.strip()
    await db.flush()
    # ADR-F024: a real retirement (this row was live until now).
    if ledger is not None:
        ledger.record(_KIND_AI_SYSTEM, eid, "retire")
    return (
        f'Retired the AI system "{row.name}" from the live register — it is hidden '
        "from the register but kept on record for audit."
    )


async def _list_ai_systems(db: AsyncSession) -> str:
    """Format the company AI-systems register (oldest first), with IDs."""
    rows = (
        (
            await db.execute(
                select(AiSystem)
                .where(AiSystem.retired_at.is_(None))
                .order_by(AiSystem.created_at.asc(), AiSystem.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    retired = int(
        (
            await db.execute(
                select(func.count()).select_from(AiSystem).where(AiSystem.retired_at.is_not(None))
            )
        ).scalar_one()
    )
    if not rows:
        return "The company AI-systems register is empty." + _hidden_footer(retired)

    blocks: list[str] = []
    for row in rows:
        gpai = _gpai_label(row.is_gpai, row.gpai_systemic)
        blocks.append(
            f"- [{row.id}] {row.name}\n"
            f"  intended purpose: {row.intended_purpose}\n"
            f"  lifecycle: {row.lifecycle_status}; origin: {row.development_origin}; {gpai}"
        )
    noun = "system" if len(rows) == 1 else "systems"
    return (
        f"Company AI-systems register — {len(rows)} {noun}:\n\n"
        + "\n".join(blocks)
        + _hidden_footer(retired)
    )


def _gpai_phrase(is_gpai: bool, gpai_systemic: bool) -> str:
    """A trailing clause for the create confirmation (empty when not GPAI)."""
    if gpai_systemic:
        return "; systemic-risk GPAI"
    if is_gpai:
        return "; GPAI"
    return ""


def _gpai_label(is_gpai: bool, gpai_systemic: bool) -> str:
    """The GPAI descriptor shown in the list dump."""
    if gpai_systemic:
        return "systemic-risk GPAI"
    if is_gpai:
        return "GPAI"
    return "not GPAI"


def _hidden_footer(retired: int) -> str:
    """A one-line note appended to a live list when retired rows exist.

    So the agent knows a name it can't see is retired (won't recreate it) without a
    tool to list retired rows — they are audit-only this slice.
    """
    if retired <= 0:
        return ""
    noun = "system" if retired == 1 else "systems"
    return f"\n\n({retired} retired {noun} hidden — retired entries stay on record for audit.)"


def _rejection_text(exc: ValidationError, tool_name: str) -> str:
    """Turn a Pydantic validation failure into a fix-and-retry message (ADR-F018).

    Mirrors ``app.agents.ropa_tools._rejection_text`` (each domain-tool module keeps
    its own copy so it stays self-contained). Reports the offending field(s) and the
    rule each broke so the model can correct and re-propose — never a silent fix.
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
