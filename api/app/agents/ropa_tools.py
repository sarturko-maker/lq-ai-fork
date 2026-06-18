"""ROPA agent tools — PRIV-2/PRIV-3 (fork, ADR-F018/F019): the validated write path.

The Privacy practice-area Deep Agent maintains the company's **deployment-global**
ROPA inventory (ADR-F019 — LQ.AI is single-tenant; the in-house team's one client
is its own organization, so the register is the company's standing record, not a
per-matter artifact). Five guarded tools over the two-tier graph
(:class:`~app.models.ropa.ProcessingActivity` ↔ :class:`~app.models.ropa.System`):

* :func:`propose_processing_activity` — the **code-validated write** of an Article
  30 record. The model PROPOSES; the tool validates against
  :class:`app.schemas.ropa.ProcessingActivityInput` (PRIV-1) BEFORE commit; a pass
  is written, a failure is **rejected back to the model with the reason**. Agent
  proposes → code disposes → commit OR reject-and-retry; never a silent write/fix.
* :func:`propose_system` — same loop for an IT system/asset
  (:class:`app.schemas.ropa.SystemInput`).
* :func:`propose_vendor` — same loop for a vendor/recipient
  (:class:`app.schemas.ropa.VendorInput`) — the Article 30(1)(e) categories of
  recipients (PRIV-5a).
* :func:`link_processing_activity_to_system` / :func:`link_vendor_to_activity` —
  record that an activity uses a system / discloses to a vendor (the M:N links),
  by the IDs the list tools surface.
* :func:`list_processing_activities` / :func:`list_systems` / :func:`list_vendors`
  — the current register (with IDs), so the agent can see what exists and link
  records.

**Scope / authz (ADR-F019).** The register is company-wide, NOT matter- or
user-scoped — so the tools do not filter by ``project_id``. The matter still
governs *whether* these tools exist (the composition point grants them only to a
matter filed under the Privacy area) and the ``guarded_dispatch`` chokepoint
governs *whether this run may write* (R6 grant set, R5 live re-check, one audit
row per dispatch — counts/types/IDs, never the proposal's values). The run's
matter is stamped onto new rows as ``source_project_id`` (provenance only — a
``rejection`` carries no row). A rejection is returned as ordinary tool-result
text (not raised): the dispatch succeeded, the *write* was refused.
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
from app.models.ropa import (
    ProcessingActivity,
    System,
    Vendor,
    processing_activity_systems,
    processing_activity_vendors,
)
from app.schemas.ropa import ProcessingActivityInput, SystemInput, VendorInput

# The stable key of the Privacy practice area (migration 0053). The composition
# point grants the ROPA tools only to a matter filed under this area.
PRIVACY_AREA_KEY = "privacy"

ROPA_TOOL_NAMES = frozenset(
    {
        "propose_processing_activity",
        "propose_system",
        "propose_vendor",
        "link_processing_activity_to_system",
        "link_vendor_to_activity",
        "list_processing_activities",
        "list_systems",
        "list_vendors",
    }
)

# Cap the register dump so a large register's tool result stays inside the model's
# working context; the read UI (PRIV-3) is the place to browse a long register.
_LIST_LIMIT = 100


def build_ropa_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the Privacy matter's guarded ROPA tools for one run.

    The guard context grants exactly the ROPA tool names (R6's grant set). The
    run's matter (``binding.project_id``) is closure-injected as row provenance
    (``source_project_id``), never as a scoping filter (ADR-F019).
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
            lambda db: _propose_activity(
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

    async def propose_system(
        name: str,
        system_type: str,
        description: str | None = None,
        owner: str | None = None,
        hosting_location: str | None = None,
        retention: str | None = None,
        security_measures: str | None = None,
        ai_usage: bool = False,
    ) -> str:
        """Propose one IT system/asset where personal data lives.

        Only ``name`` and ``system_type`` are required; fill the rest as you learn
        it. The proposal is validated before recording; a failure comes back with
        the reasons to fix and re-propose.

        - ``system_type``: one of database, analytics, crm, support,
          email_marketing, logs, backup, third_party_processor, other.
        - ``hosting_location``: country/region where the system hosts data.
        - ``security_measures``: technical/organisational measures (TOMs).
        - ``ai_usage``: true if the system applies AI/automated decision-making.
        """
        return await guarded_dispatch(
            "propose_system",
            lambda db: _propose_system(
                db,
                binding,
                name=name,
                system_type=system_type,
                description=description,
                owner=owner,
                hosting_location=hosting_location,
                retention=retention,
                security_measures=security_measures,
                ai_usage=ai_usage,
            ),
            ctx,
        )

    async def propose_vendor(
        name: str,
        vendor_role: str,
        dpa_status: str,
        description: str | None = None,
        country: str | None = None,
    ) -> str:
        """Propose one vendor / third party (recipient) the company discloses data to.

        Only ``name``, ``vendor_role`` and ``dpa_status`` are required; fill the
        rest as you learn it. The proposal is validated before recording; a
        failure comes back with the reasons to fix and re-propose.

        - ``vendor_role``: one of processor, sub_processor, joint_controller,
          separate_controller, recipient (the GDPR recipient/relationship
          category).
        - ``dpa_status``: status of the Article 28 data-processing agreement —
          one of in_place, pending, not_required, none.
        - ``country``: where the vendor is established (informs transfers).
        """
        return await guarded_dispatch(
            "propose_vendor",
            lambda db: _propose_vendor(
                db,
                binding,
                name=name,
                vendor_role=vendor_role,
                dpa_status=dpa_status,
                description=description,
                country=country,
            ),
            ctx,
        )

    async def link_processing_activity_to_system(
        processing_activity_id: str,
        system_id: str,
    ) -> str:
        """Record that a processing activity uses a system (the data-flow link).

        Pass the IDs shown by list_processing_activities and list_systems. If
        either ID is unknown the link is refused with the reason. Linking an
        already-linked pair is a no-op.
        """
        return await guarded_dispatch(
            "link_processing_activity_to_system",
            lambda db: _link(
                db,
                processing_activity_id=processing_activity_id,
                system_id=system_id,
            ),
            ctx,
        )

    async def link_vendor_to_activity(
        processing_activity_id: str,
        vendor_id: str,
    ) -> str:
        """Record that a processing activity discloses data to a vendor (recipient link).

        Pass the IDs shown by list_processing_activities and list_vendors. If
        either ID is unknown the link is refused with the reason. Linking an
        already-linked pair is a no-op.
        """
        return await guarded_dispatch(
            "link_vendor_to_activity",
            lambda db: _link_vendor(
                db,
                processing_activity_id=processing_activity_id,
                vendor_id=vendor_id,
            ),
            ctx,
        )

    async def list_processing_activities() -> str:
        """List the processing activities in the company ROPA register (with IDs)."""
        return await guarded_dispatch(
            "list_processing_activities", lambda db: _list_activities(db), ctx
        )

    async def list_systems() -> str:
        """List the systems in the company inventory (with IDs)."""
        return await guarded_dispatch("list_systems", lambda db: _list_systems(db), ctx)

    async def list_vendors() -> str:
        """List the vendors/recipients in the company register (with IDs)."""
        return await guarded_dispatch("list_vendors", lambda db: _list_vendors(db), ctx)

    return [
        propose_processing_activity,
        propose_system,
        propose_vendor,
        link_processing_activity_to_system,
        link_vendor_to_activity,
        list_processing_activities,
        list_systems,
        list_vendors,
    ]


async def _propose_activity(
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
        return _rejection_text(exc, "propose_processing_activity")

    db.add(
        ProcessingActivity(
            source_project_id=binding.project_id,
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
        f'Recorded processing activity "{proposal.name}" in the company ROPA '
        f"(lawful basis: {proposal.lawful_basis.value}; role: "
        f"{proposal.controller_role.value}; retention: {proposal.retention})."
    )


async def _propose_system(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    name: str,
    system_type: str,
    description: str | None,
    owner: str | None,
    hosting_location: str | None,
    retention: str | None,
    security_measures: str | None,
    ai_usage: bool,
) -> str:
    """Validate the system proposal, then write it (or return the rejection)."""
    try:
        proposal = SystemInput(
            name=name,
            system_type=system_type,  # type: ignore[arg-type]  # str → enum coercion
            description=description,
            owner=owner,
            hosting_location=hosting_location,
            retention=retention,
            security_measures=security_measures,
            ai_usage=ai_usage,
        )
    except ValidationError as exc:
        return _rejection_text(exc, "propose_system")

    db.add(
        System(
            source_project_id=binding.project_id,
            name=proposal.name,
            system_type=proposal.system_type.value,
            description=proposal.description,
            owner=proposal.owner,
            hosting_location=proposal.hosting_location,
            retention=proposal.retention,
            security_measures=proposal.security_measures,
            ai_usage=proposal.ai_usage,
        )
    )
    await db.flush()
    return f'Recorded system "{proposal.name}" ({proposal.system_type.value}) in the company inventory.'


async def _propose_vendor(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    name: str,
    vendor_role: str,
    dpa_status: str,
    description: str | None,
    country: str | None,
) -> str:
    """Validate the vendor proposal, then write it (or return the rejection)."""
    try:
        proposal = VendorInput(
            name=name,
            vendor_role=vendor_role,  # type: ignore[arg-type]  # str → enum coercion
            dpa_status=dpa_status,  # type: ignore[arg-type]
            description=description,
            country=country,
        )
    except ValidationError as exc:
        return _rejection_text(exc, "propose_vendor")

    db.add(
        Vendor(
            source_project_id=binding.project_id,
            name=proposal.name,
            vendor_role=proposal.vendor_role.value,
            dpa_status=proposal.dpa_status.value,
            description=proposal.description,
            country=proposal.country,
        )
    )
    await db.flush()
    return (
        f'Recorded vendor "{proposal.name}" ({proposal.vendor_role.value}; '
        f"DPA: {proposal.dpa_status.value}) in the company register."
    )


async def _link(
    db: AsyncSession,
    *,
    processing_activity_id: str,
    system_id: str,
) -> str:
    """Link an activity to a system after checking both exist (else reject)."""
    try:
        pa_uuid = uuid.UUID(processing_activity_id)
        sys_uuid = uuid.UUID(system_id)
    except ValueError:
        return (
            "Link refused — processing_activity_id and system_id must be the IDs "
            "shown by list_processing_activities / list_systems. Nothing was linked."
        )

    activity = await db.get(ProcessingActivity, pa_uuid)
    system = await db.get(System, sys_uuid)
    missing = []
    if activity is None:
        missing.append(f"no processing activity with id {processing_activity_id}")
    if system is None:
        missing.append(f"no system with id {system_id}")
    if missing:
        return "Link refused — " + "; ".join(missing) + ". Nothing was linked."
    assert activity is not None and system is not None  # narrowed by the checks above

    existing = (
        await db.execute(
            select(processing_activity_systems).where(
                processing_activity_systems.c.processing_activity_id == pa_uuid,
                processing_activity_systems.c.system_id == sys_uuid,
            )
        )
    ).first()
    if existing is not None:
        return f'"{activity.name}" is already linked to system "{system.name}".'

    await db.execute(
        processing_activity_systems.insert().values(
            processing_activity_id=pa_uuid, system_id=sys_uuid
        )
    )
    await db.flush()
    return f'Linked processing activity "{activity.name}" to system "{system.name}".'


async def _link_vendor(
    db: AsyncSession,
    *,
    processing_activity_id: str,
    vendor_id: str,
) -> str:
    """Link an activity to a vendor/recipient after checking both exist (else reject)."""
    try:
        pa_uuid = uuid.UUID(processing_activity_id)
        vendor_uuid = uuid.UUID(vendor_id)
    except ValueError:
        return (
            "Link refused — processing_activity_id and vendor_id must be the IDs "
            "shown by list_processing_activities / list_vendors. Nothing was linked."
        )

    activity = await db.get(ProcessingActivity, pa_uuid)
    vendor = await db.get(Vendor, vendor_uuid)
    missing = []
    if activity is None:
        missing.append(f"no processing activity with id {processing_activity_id}")
    if vendor is None:
        missing.append(f"no vendor with id {vendor_id}")
    if missing:
        return "Link refused — " + "; ".join(missing) + ". Nothing was linked."
    assert activity is not None and vendor is not None  # narrowed by the checks above

    existing = (
        await db.execute(
            select(processing_activity_vendors).where(
                processing_activity_vendors.c.processing_activity_id == pa_uuid,
                processing_activity_vendors.c.vendor_id == vendor_uuid,
            )
        )
    ).first()
    if existing is not None:
        return f'"{activity.name}" already discloses to vendor "{vendor.name}".'

    await db.execute(
        processing_activity_vendors.insert().values(
            processing_activity_id=pa_uuid, vendor_id=vendor_uuid
        )
    )
    await db.flush()
    return f'Linked processing activity "{activity.name}" to vendor "{vendor.name}".'


async def _list_activities(db: AsyncSession) -> str:
    """Format the company ROPA register (oldest first), with IDs for linking."""
    rows = (
        (
            await db.execute(
                select(ProcessingActivity)
                .order_by(ProcessingActivity.created_at.asc(), ProcessingActivity.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "The company ROPA has no processing activities yet."

    blocks: list[str] = []
    for row in rows:
        sc = (
            f"special-category (Article 9: {row.art9_condition})"
            if row.special_category
            else "not special-category"
        )
        blocks.append(
            f"- [{row.id}] {row.name}\n"
            f"  purpose: {row.purpose}\n"
            f"  lawful basis: {row.lawful_basis}; role: {row.controller_role}; "
            f"retention: {row.retention}; {sc}"
        )
    noun = "activity" if len(rows) == 1 else "activities"
    return f"Company ROPA — {len(rows)} processing {noun}:\n\n" + "\n".join(blocks)


async def _list_systems(db: AsyncSession) -> str:
    """Format the company system inventory (oldest first), with IDs for linking."""
    rows = (
        (
            await db.execute(
                select(System)
                .order_by(System.created_at.asc(), System.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "The company system inventory has no systems yet."

    blocks: list[str] = []
    for row in rows:
        extras = []
        if row.hosting_location:
            extras.append(f"hosted: {row.hosting_location}")
        if row.ai_usage:
            extras.append("uses AI")
        tail = f" ({'; '.join(extras)})" if extras else ""
        blocks.append(f"- [{row.id}] {row.name} — {row.system_type}{tail}")
    noun = "system" if len(rows) == 1 else "systems"
    return f"Company inventory — {len(rows)} {noun}:\n\n" + "\n".join(blocks)


async def _list_vendors(db: AsyncSession) -> str:
    """Format the company vendor/recipient register (oldest first), with IDs for linking."""
    rows = (
        (
            await db.execute(
                select(Vendor)
                .order_by(Vendor.created_at.asc(), Vendor.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "The company register has no vendors/recipients yet."

    blocks: list[str] = []
    for row in rows:
        tail = f"; based in {row.country}" if row.country else ""
        blocks.append(f"- [{row.id}] {row.name} — {row.vendor_role} (DPA: {row.dpa_status}{tail})")
    noun = "vendor" if len(rows) == 1 else "vendors"
    return f"Company register — {len(rows)} {noun}:\n\n" + "\n".join(blocks)


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
