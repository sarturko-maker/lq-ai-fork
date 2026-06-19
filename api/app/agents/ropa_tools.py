"""ROPA agent tools — PRIV-2/PRIV-3/PRIV-5 (fork, ADR-F018/F019): the validated write path.

The Privacy practice-area Deep Agent maintains the company's **deployment-global**
ROPA inventory (ADR-F019 — LQ.AI is single-tenant; the in-house team's one client
is its own organization, so the register is the company's standing record, not a
per-matter artifact). Guarded, code-validated tools over the inventory graph
(:class:`~app.models.ropa.ProcessingActivity` ↔ :class:`~app.models.ropa.System` /
:class:`~app.models.ropa.Vendor`, with :class:`~app.models.ropa.Transfer` hung off
each activity):

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
* :func:`propose_transfer` — same loop for a third-country transfer
  (:class:`app.schemas.ropa.TransferInput`) — the Article 30(1)(e) transfers +
  safeguards (PRIV-5b); a child of a processing activity, with the headline
  restricted⇔mechanism invariant validated before commit.
* :func:`link_processing_activity_to_system` / :func:`link_vendor_to_activity` —
  record that an activity uses a system / discloses to a vendor (the M:N links),
  by the IDs the list tools surface.
* :func:`add_data_subject_categories` / :func:`add_data_categories` — tag an
  activity with the Article 30(1)(c) categories of data subjects / personal data
  (PRIV-6a). List-valued + find-or-create against the controlled vocabulary: each
  name is validated, then found-or-created by name and linked (idempotent), so a
  vocabulary term is reused, never duplicated.
* :func:`list_processing_activities` / :func:`list_systems` / :func:`list_vendors`
  / :func:`list_transfers` / :func:`list_data_subject_categories` /
  :func:`list_data_categories` — the current register (with IDs), so the agent can
  see what exists and link records.

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
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import CursorResult, Table, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import MatterBinding
from app.models.ropa import (
    DataCategory,
    DataSubjectCategory,
    ProcessingActivity,
    System,
    Transfer,
    Vendor,
    processing_activity_data_categories,
    processing_activity_data_subject_categories,
    processing_activity_systems,
    processing_activity_vendors,
)
from app.schemas.ropa import (
    DataCategoryInput,
    DataSubjectCategoryInput,
    ProcessingActivityInput,
    SystemInput,
    TransferInput,
    VendorInput,
)

# The stable key of the Privacy practice area (migration 0053). The composition
# point grants the ROPA tools only to a matter filed under this area.
PRIVACY_AREA_KEY = "privacy"

ROPA_TOOL_NAMES = frozenset(
    {
        "propose_processing_activity",
        "propose_system",
        "propose_vendor",
        "propose_transfer",
        "link_processing_activity_to_system",
        "link_vendor_to_activity",
        "add_data_subject_categories",
        "add_data_categories",
        # PRIV-8a (ADR-F023): the change verbs — soft-retire + unlink. The agent
        # can now *change* the register (replace a vendor/system, drop a link), not
        # only append. Retire never destroys a row (it stays for audit); unlink
        # removes one M:N link.
        "retire_processing_activity",
        "retire_system",
        "retire_vendor",
        "retire_transfer",
        "unlink_system_from_activity",
        "unlink_vendor_from_activity",
        "list_processing_activities",
        "list_systems",
        "list_vendors",
        "list_transfers",
        "list_data_subject_categories",
        "list_data_categories",
    }
)

# Cap the register dump so a large register's tool result stays inside the model's
# working context; the read UI (PRIV-3) is the place to browse a long register.
_LIST_LIMIT = 100

# Max length of a soft-retire reason note (PRIV-8a, ADR-F023) — mirrors the
# ``retirement_reason`` CHECK in app.models.ropa (defense-in-depth; reject, don't
# truncate). One source for the bound so the tool and the DB agree.
_MAX_RETIREMENT_REASON = 1000

# The two Article 30(1)(c) controlled-vocabulary entities share an identical
# shape, so the tag/list helpers below are generic over them (PEP 695 constrained
# type parameter — ``[CatT: (DataSubjectCategory, DataCategory)]``).


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

    async def propose_transfer(
        processing_activity_id: str,
        destination: str,
        restricted: bool = False,
        mechanism: str | None = None,
        vendor_id: str | None = None,
        details: str | None = None,
    ) -> str:
        """Propose one third-country transfer of a processing activity's data.

        A transfer belongs to a processing activity (pass the id shown by
        list_processing_activities) and optionally names a recipient vendor (an
        id from list_vendors). The proposal is validated before recording; a
        failure comes back with the reasons to fix and re-propose.

        - ``destination``: the third country / international organisation the data
          goes to (e.g. "United States", "India").
        - ``restricted``: true if this is a restricted transfer — the recipient is
          OUTSIDE the UK/EEA. When true, ``mechanism`` is REQUIRED; when false,
          ``mechanism`` must be left unset.
        - ``mechanism``: the Chapter V safeguard — one of adequacy_regulations,
          standard_contractual_clauses, uk_idta, binding_corporate_rules,
          derogation (Article 49).
        - ``vendor_id``: the recipient vendor, if it is a known vendor.
        - ``details``: free-text safeguard detail (e.g. "EU SCCs module 2 + UK
          Addendum; transfer risk assessment dated 2026-03").
        """
        return await guarded_dispatch(
            "propose_transfer",
            lambda db: _propose_transfer(
                db,
                binding,
                processing_activity_id=processing_activity_id,
                destination=destination,
                restricted=restricted,
                mechanism=mechanism,
                vendor_id=vendor_id,
                details=details,
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

    async def add_data_subject_categories(
        processing_activity_id: str,
        names: list[str],
    ) -> str:
        """Tag a processing activity with the categories of data subjects it processes.

        Pass the activity id (from list_processing_activities) and one or more
        category names (the classes of individuals whose data is processed — e.g.
        "Employees", "Customers", "Job applicants"). Each name is validated, then
        found-or-created in the company's controlled vocabulary and linked to the
        activity (a name already in the vocabulary is reused, not duplicated;
        re-tagging an already-tagged category is a no-op). If a name is invalid or
        the activity id is unknown the call is refused with the reason and nothing
        is recorded. Use Title Case for consistent vocabulary terms.
        """
        return await guarded_dispatch(
            "add_data_subject_categories",
            lambda db: _add_categories(
                db,
                binding,
                model=DataSubjectCategory,
                input_cls=DataSubjectCategoryInput,
                link_table=processing_activity_data_subject_categories,
                link_col="data_subject_category_id",
                kind="data subject categories",
                processing_activity_id=processing_activity_id,
                names=names,
            ),
            ctx,
        )

    async def add_data_categories(
        processing_activity_id: str,
        names: list[str],
    ) -> str:
        """Tag a processing activity with the categories of personal data it processes.

        Pass the activity id (from list_processing_activities) and one or more
        category names (the classes of personal data processed — e.g. "Contact
        details", "Financial data", "Health data", "Location data"). Same
        find-or-create + idempotent-link behaviour as add_data_subject_categories;
        an invalid name or unknown activity id is refused with the reason and
        nothing is recorded. Use Title Case for consistent vocabulary terms.
        """
        return await guarded_dispatch(
            "add_data_categories",
            lambda db: _add_categories(
                db,
                binding,
                model=DataCategory,
                input_cls=DataCategoryInput,
                link_table=processing_activity_data_categories,
                link_col="data_category_id",
                kind="data categories",
                processing_activity_id=processing_activity_id,
                names=names,
            ),
            ctx,
        )

    async def retire_processing_activity(
        processing_activity_id: str, reason: str | None = None
    ) -> str:
        """Retire a processing activity — the company no longer carries out this processing.

        Soft, auditable: the record is removed from the LIVE register (and from the
        export, summary and data-flow) but is never destroyed — it stays on record
        so the change can be audited. Pass the id from list_processing_activities and
        optionally a short ``reason`` (e.g. "process discontinued 2026-06"). Use this
        only when the whole activity has ended — to stop using ONE system/vendor for an
        activity that continues, use unlink_* instead. Retiring an already-retired
        record is a no-op.
        """
        return await guarded_dispatch(
            "retire_processing_activity",
            lambda db: _retire(
                db,
                model=ProcessingActivity,
                entity_id=processing_activity_id,
                noun="processing activity",
                list_hint="list_processing_activities",
                reason=reason,
            ),
            ctx,
        )

    async def retire_system(system_id: str, reason: str | None = None) -> str:
        """Retire a system/asset — the company no longer uses this system at all.

        Soft, auditable (see retire_processing_activity): the system leaves the live
        register but stays on record. This is company-wide — it drops the system from
        EVERY activity that used it. To stop using it for just one activity that keeps
        running, use unlink_system_from_activity instead. Pass the id from list_systems
        and an optional ``reason`` (e.g. "decommissioned; replaced by X"). Retiring an
        already-retired system is a no-op.
        """
        return await guarded_dispatch(
            "retire_system",
            lambda db: _retire(
                db,
                model=System,
                entity_id=system_id,
                noun="system",
                list_hint="list_systems",
                reason=reason,
            ),
            ctx,
        )

    async def retire_vendor(vendor_id: str, reason: str | None = None) -> str:
        """Retire a vendor/recipient — the company no longer discloses data to it.

        Soft, auditable (see retire_processing_activity): the vendor leaves the live
        register but stays on record. This is company-wide — it drops the vendor as a
        recipient of EVERY activity. To stop disclosing to it for just one activity,
        use unlink_vendor_from_activity instead. Typical use: replacing a vendor — add
        the new one (propose_vendor + link_vendor_to_activity), then retire the old one
        here. Pass the id from list_vendors and an optional ``reason`` (e.g. "moved off
        Mixpanel; replaced by Hotjar"). Retiring an already-retired vendor is a no-op.
        """
        return await guarded_dispatch(
            "retire_vendor",
            lambda db: _retire(
                db,
                model=Vendor,
                entity_id=vendor_id,
                noun="vendor",
                list_hint="list_vendors",
                reason=reason,
            ),
            ctx,
        )

    async def retire_transfer(transfer_id: str, reason: str | None = None) -> str:
        """Retire a third-country transfer — this transfer no longer happens.

        Soft, auditable (see retire_processing_activity): the transfer leaves the live
        register but stays on record. Pass the id from list_transfers and an optional
        ``reason``. Retiring an already-retired transfer is a no-op.
        """
        return await guarded_dispatch(
            "retire_transfer",
            lambda db: _retire(
                db,
                model=Transfer,
                entity_id=transfer_id,
                noun="transfer",
                list_hint="list_transfers",
                reason=reason,
            ),
            ctx,
        )

    async def unlink_system_from_activity(processing_activity_id: str, system_id: str) -> str:
        """Remove the link between a processing activity and a system.

        The activity no longer uses this system, but BOTH records stay live (the
        system may still serve other activities). Pass the IDs from
        list_processing_activities / list_systems. If they were not linked it is a
        no-op. To remove the system from the register entirely, use retire_system.
        """
        return await guarded_dispatch(
            "unlink_system_from_activity",
            lambda db: _unlink(
                db,
                link_table=processing_activity_systems,
                other_col="system_id",
                other_model=System,
                other_noun="system",
                list_hint="list_systems",
                processing_activity_id=processing_activity_id,
                other_id=system_id,
            ),
            ctx,
        )

    async def unlink_vendor_from_activity(processing_activity_id: str, vendor_id: str) -> str:
        """Remove the link between a processing activity and a vendor/recipient.

        The activity no longer discloses to this vendor, but BOTH records stay live
        (the vendor may still receive data for other activities). Pass the IDs from
        list_processing_activities / list_vendors. If they were not linked it is a
        no-op. To remove the vendor from the register entirely, use retire_vendor.
        """
        return await guarded_dispatch(
            "unlink_vendor_from_activity",
            lambda db: _unlink(
                db,
                link_table=processing_activity_vendors,
                other_col="vendor_id",
                other_model=Vendor,
                other_noun="vendor",
                list_hint="list_vendors",
                processing_activity_id=processing_activity_id,
                other_id=vendor_id,
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

    async def list_transfers() -> str:
        """List the third-country transfers in the company ROPA (with IDs)."""
        return await guarded_dispatch("list_transfers", lambda db: _list_transfers(db), ctx)

    async def list_data_subject_categories() -> str:
        """List the categories of data subjects in the company ROPA vocabulary (with IDs)."""
        return await guarded_dispatch(
            "list_data_subject_categories",
            lambda db: _list_categories(
                db,
                model=DataSubjectCategory,
                empty="The company ROPA has no categories of data subjects yet.",
                heading="categories of data subjects",
            ),
            ctx,
        )

    async def list_data_categories() -> str:
        """List the categories of personal data in the company ROPA vocabulary (with IDs)."""
        return await guarded_dispatch(
            "list_data_categories",
            lambda db: _list_categories(
                db,
                model=DataCategory,
                empty="The company ROPA has no categories of personal data yet.",
                heading="categories of personal data",
            ),
            ctx,
        )

    return [
        propose_processing_activity,
        propose_system,
        propose_vendor,
        propose_transfer,
        link_processing_activity_to_system,
        link_vendor_to_activity,
        add_data_subject_categories,
        add_data_categories,
        retire_processing_activity,
        retire_system,
        retire_vendor,
        retire_transfer,
        unlink_system_from_activity,
        unlink_vendor_from_activity,
        list_processing_activities,
        list_systems,
        list_vendors,
        list_transfers,
        list_data_subject_categories,
        list_data_categories,
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


async def _propose_transfer(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    processing_activity_id: str,
    destination: str,
    restricted: bool,
    mechanism: str | None,
    vendor_id: str | None,
    details: str | None,
) -> str:
    """Validate the transfer proposal + resolve its FKs, then write it (or reject).

    Content (incl. the restricted⇔mechanism invariant) is validated against
    ``TransferInput`` first; then the parent activity (required) and the optional
    recipient vendor are resolved against the register — both refusals come back
    to the model so it can fix and re-propose (never a silent write/fix).
    """
    try:
        proposal = TransferInput(
            destination=destination,
            restricted=restricted,
            mechanism=mechanism,  # type: ignore[arg-type]  # str → enum coercion
            details=details,
        )
    except ValidationError as exc:
        return _rejection_text(exc, "propose_transfer")

    try:
        pa_uuid = uuid.UUID(processing_activity_id)
        vendor_uuid = uuid.UUID(vendor_id) if vendor_id is not None else None
    except ValueError:
        return (
            "Transfer refused — processing_activity_id (and vendor_id, if given) must "
            "be the IDs shown by list_processing_activities / list_vendors. Nothing was recorded."
        )

    activity = await db.get(ProcessingActivity, pa_uuid)
    vendor = await db.get(Vendor, vendor_uuid) if vendor_uuid is not None else None
    missing = []
    if activity is None:
        missing.append(f"no processing activity with id {processing_activity_id}")
    if vendor_uuid is not None and vendor is None:
        missing.append(f"no vendor with id {vendor_id}")
    if missing:
        return "Transfer refused — " + "; ".join(missing) + ". Nothing was recorded."
    assert activity is not None  # narrowed by the check above

    blocked = _retired_target_block((activity, "processing activity"), (vendor, "vendor"))
    if blocked is not None:
        return blocked

    db.add(
        Transfer(
            source_project_id=binding.project_id,
            processing_activity_id=pa_uuid,
            vendor_id=vendor_uuid,
            destination=proposal.destination,
            restricted=proposal.restricted,
            mechanism=(proposal.mechanism.value if proposal.mechanism else None),
            details=proposal.details,
        )
    )
    # Flush so the DB CHECK mirror (the restricted⇔mechanism invariant) surfaces
    # inside the guard's try, audited and rolled back together with the audit row.
    await db.flush()
    safeguard = (
        f"; mechanism: {proposal.mechanism.value}" if proposal.mechanism else "; not restricted"
    )
    return f'Recorded transfer of "{activity.name}" to {proposal.destination}{safeguard}.'


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

    blocked = _retired_target_block((activity, "processing activity"), (system, "system"))
    if blocked is not None:
        return blocked

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

    blocked = _retired_target_block((activity, "processing activity"), (vendor, "vendor"))
    if blocked is not None:
        return blocked

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


# ---------------------------------------------------------------------------
# Change verbs (PRIV-8a, ADR-F023): soft-retire + unlink
# ---------------------------------------------------------------------------


def _retire_label(row: ProcessingActivity | System | Vendor | Transfer) -> str:
    """A human label for a register row — the name for the named entities, the
    destination for a transfer (which carries no name)."""
    if isinstance(row, Transfer):
        return row.destination
    return row.name


def _retired_target_block(
    *candidates: tuple[ProcessingActivity | System | Vendor | None, str],
) -> str | None:
    """Refuse a link/tag/transfer that targets a RETIRED record (ADR-F023).

    The live register must never grow a link to a retired row: the reads hide it,
    so the join would be latent, invisible state that resurfaces incoherently on a
    future un-retire. Returns the refusal text for the first retired target, or
    ``None`` if every target is live. ``None`` candidates (e.g. an absent optional
    vendor) are skipped.
    """
    for row, noun in candidates:
        if row is not None and row.retired_at is not None:
            return (
                f'Refused — {noun} "{row.name}" is retired; link/tag a live record instead. '
                "Nothing was changed."
            )
    return None


async def _retire[R: (ProcessingActivity, System, Vendor, Transfer)](
    db: AsyncSession,
    *,
    model: type[R],
    entity_id: str,
    noun: str,
    list_hint: str,
    reason: str | None,
) -> str:
    """Soft-retire one register row (set ``retired_at``); never delete it.

    Idempotent (an already-retired row is a friendly no-op); an unknown id is
    refused with the reason (never a silent change). The row stays on record for
    audit; the reads exclude it from the live register. ``reason`` is an optional
    note — rejected (not silently truncated) if it exceeds the stored length, per
    ADR-F018 (reject, don't sanitize).
    """
    try:
        eid = uuid.UUID(entity_id)
    except ValueError:
        return f"Retire refused — the id must be one shown by {list_hint}. Nothing was changed."
    if reason is not None and len(reason.strip()) > _MAX_RETIREMENT_REASON:
        return (
            f"Retire refused — reason is too long (max {_MAX_RETIREMENT_REASON} characters). "
            "Shorten it and call again. Nothing was changed."
        )
    row: R | None = await db.get(model, eid)
    if row is None:
        return f"Retire refused — no {noun} with id {entity_id}. Nothing was changed."
    label = _retire_label(row)
    if row.retired_at is not None:
        return f'The {noun} "{label}" is already retired — nothing to do.'
    row.retired_at = datetime.now(UTC)
    if reason is not None and reason.strip():
        row.retirement_reason = reason.strip()
    await db.flush()
    return (
        f'Retired the {noun} "{label}" from the live register — it is hidden from the '
        "register but kept on record for audit."
    )


async def _unlink[O: (System, Vendor)](
    db: AsyncSession,
    *,
    link_table: Table,
    other_col: str,
    other_model: type[O],
    other_noun: str,
    list_hint: str,
    processing_activity_id: str,
    other_id: str,
) -> str:
    """Delete one M:N link row after checking both ends exist (else reject).

    The mirror of ``_link`` / ``_link_vendor``: removes the single
    (activity, system|vendor) pair. Idempotent — if the pair was not linked it is a
    no-op. The entities themselves are untouched (use the retire verbs to remove a
    record from the register entirely).
    """
    try:
        pa_uuid = uuid.UUID(processing_activity_id)
        other_uuid = uuid.UUID(other_id)
    except ValueError:
        return (
            f"Unlink refused — processing_activity_id and the {other_noun} id must be the IDs "
            f"shown by list_processing_activities / {list_hint}. Nothing was unlinked."
        )

    activity = await db.get(ProcessingActivity, pa_uuid)
    other = await db.get(other_model, other_uuid)
    missing = []
    if activity is None:
        missing.append(f"no processing activity with id {processing_activity_id}")
    if other is None:
        missing.append(f"no {other_noun} with id {other_id}")
    if missing:
        return "Unlink refused — " + "; ".join(missing) + ". Nothing was unlinked."
    assert activity is not None and other is not None  # narrowed by the checks above

    # One DELETE; rowcount tells us whether the pair was actually linked (idempotent
    # no-op message when it wasn't) — no separate existence SELECT needed.
    result: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
        delete(link_table).where(
            link_table.c.processing_activity_id == pa_uuid,
            link_table.c[other_col] == other_uuid,
        )
    )
    await db.flush()
    if result.rowcount == 0:
        return (
            f'"{activity.name}" was not linked to {other_noun} "{other.name}" — nothing to unlink.'
        )
    return f'Unlinked {other_noun} "{other.name}" from processing activity "{activity.name}".'


async def _retired_count[R: (ProcessingActivity, System, Vendor, Transfer)](
    db: AsyncSession, model: type[R]
) -> int:
    """How many rows of ``model`` are retired (for the list tools' hidden-count footer)."""
    count = (
        await db.execute(
            select(func.count()).select_from(model).where(model.retired_at.is_not(None))
        )
    ).scalar_one()
    return int(count)


def _hidden_footer(retired: int) -> str:
    """A one-line note appended to a live list when retired rows exist (PRIV-8a).

    So the agent knows a name it can't see is retired (won't recreate it) without
    a tool to list retired rows — they are audit-only this slice.
    """
    if retired <= 0:
        return ""
    noun = "record" if retired == 1 else "records"
    return f"\n\n({retired} retired {noun} hidden — retired entries stay on record for audit.)"


async def _list_activities(db: AsyncSession) -> str:
    """Format the company ROPA register (oldest first), with IDs for linking."""
    rows = (
        (
            await db.execute(
                select(ProcessingActivity)
                .where(ProcessingActivity.retired_at.is_(None))
                .order_by(ProcessingActivity.created_at.asc(), ProcessingActivity.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    retired = await _retired_count(db, ProcessingActivity)
    if not rows:
        return "The company ROPA has no processing activities yet." + _hidden_footer(retired)

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
    return (
        f"Company ROPA — {len(rows)} processing {noun}:\n\n"
        + "\n".join(blocks)
        + _hidden_footer(retired)
    )


async def _list_systems(db: AsyncSession) -> str:
    """Format the company system inventory (oldest first), with IDs for linking."""
    rows = (
        (
            await db.execute(
                select(System)
                .where(System.retired_at.is_(None))
                .order_by(System.created_at.asc(), System.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    retired = await _retired_count(db, System)
    if not rows:
        return "The company system inventory has no systems yet." + _hidden_footer(retired)

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
    return (
        f"Company inventory — {len(rows)} {noun}:\n\n" + "\n".join(blocks) + _hidden_footer(retired)
    )


async def _list_vendors(db: AsyncSession) -> str:
    """Format the company vendor/recipient register (oldest first), with IDs for linking."""
    rows = (
        (
            await db.execute(
                select(Vendor)
                .where(Vendor.retired_at.is_(None))
                .order_by(Vendor.created_at.asc(), Vendor.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    retired = await _retired_count(db, Vendor)
    if not rows:
        return "The company register has no vendors/recipients yet." + _hidden_footer(retired)

    blocks: list[str] = []
    for row in rows:
        tail = f"; based in {row.country}" if row.country else ""
        blocks.append(f"- [{row.id}] {row.name} — {row.vendor_role} (DPA: {row.dpa_status}{tail})")
    noun = "vendor" if len(rows) == 1 else "vendors"
    return (
        f"Company register — {len(rows)} {noun}:\n\n" + "\n".join(blocks) + _hidden_footer(retired)
    )


async def _list_transfers(db: AsyncSession) -> str:
    """Format the company's third-country transfers (oldest first), with IDs."""
    rows = (
        (
            await db.execute(
                select(Transfer)
                # Hide a transfer that is itself retired OR whose parent activity is
                # retired (the activity has vanished from the register, so its
                # transfer must too — matches the API _load_register; ADR-F023).
                .where(
                    Transfer.retired_at.is_(None),
                    Transfer.processing_activity.has(ProcessingActivity.retired_at.is_(None)),
                )
                .options(
                    selectinload(Transfer.processing_activity),
                    selectinload(Transfer.vendor),
                    # A retired recipient vendor renders as no recipient (not its name).
                    with_loader_criteria(Vendor, Vendor.retired_at.is_(None)),
                )
                .order_by(Transfer.created_at.asc(), Transfer.destination.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    retired = await _retired_count(db, Transfer)
    if not rows:
        return "The company ROPA has no third-country transfers yet." + _hidden_footer(retired)

    blocks: list[str] = []
    for row in rows:
        safeguard = (
            f"restricted (mechanism: {row.mechanism})" if row.restricted else "not restricted"
        )
        recipient = f"; recipient: {row.vendor.name}" if row.vendor is not None else ""
        blocks.append(
            f"- [{row.id}] {row.processing_activity.name} → {row.destination} "
            f"({safeguard}){recipient}"
        )
    noun = "transfer" if len(rows) == 1 else "transfers"
    return (
        f"Company ROPA — {len(rows)} third-country {noun}:\n\n"
        + "\n".join(blocks)
        + _hidden_footer(retired)
    )


async def _add_categories[CatT: (DataSubjectCategory, DataCategory)](
    db: AsyncSession,
    binding: MatterBinding,
    *,
    model: type[CatT],
    input_cls: type[DataSubjectCategoryInput] | type[DataCategoryInput],
    link_table: Table,
    link_col: str,
    kind: str,
    processing_activity_id: str,
    names: list[str],
) -> str:
    """Validate each category name, then find-or-create + idempotently link it.

    Article 30(1)(c) tagging (PRIV-6a): a name already in the controlled
    vocabulary is reused (matched **case-insensitively** on ``lower(name)``, so
    "Health data"/"Health Data" are one term, not two); a new one is created. The
    whole call is refused (nothing written) if the activity id is unknown or any
    name fails validation — never a silent fix.

    Create is race-safe: the lookup→insert window over the deployment-global
    register (ADR-F019; concurrent runs / subagent fan-out) is closed by a
    SAVEPOINT — a lost race raises ``IntegrityError`` against the
    ``lower(name)`` unique index, which we absorb and re-select the winning row
    (so the dispatch returns a normal result, never a raised DB error that would
    leak SQL/params into the run error and discard sibling links).
    """
    if not names:
        return f"No {kind} given — pass one or more category names. Nothing was recorded."

    # Validate every name first; reject the whole call on any failure.
    validated: list[str] = []
    problems: list[str] = []
    for raw in names:
        try:
            validated.append(input_cls(name=raw).name)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"]) or "(name)"
                problems.append(f"- {raw!r} ({loc}): {err['msg']}")
    if problems:
        return (
            f"Tagging refused — one or more {kind} are invalid. Nothing was recorded. "
            "Fix and call again:\n" + "\n".join(problems)
        )

    try:
        pa_uuid = uuid.UUID(processing_activity_id)
    except ValueError:
        return (
            "Tagging refused — processing_activity_id must be an id shown by "
            "list_processing_activities. Nothing was recorded."
        )
    activity = await db.get(ProcessingActivity, pa_uuid)
    if activity is None:
        return (
            f"Tagging refused — no processing activity with id {processing_activity_id}. "
            "Nothing was recorded."
        )
    if activity.retired_at is not None:
        return (
            f'Tagging refused — processing activity "{activity.name}" is retired; '
            "tag a live activity instead. Nothing was recorded."
        )

    added: list[str] = []
    already: list[str] = []
    created: list[str] = []
    seen: set[str] = set()
    for name in validated:
        key = name.casefold()
        if key in seen:  # de-dupe (case-insensitively) within this one call
            continue
        seen.add(key)
        category = await _find_or_create_category(db, model, binding, name, created)
        existing_link = (
            await db.execute(
                select(link_table).where(
                    link_table.c.processing_activity_id == pa_uuid,
                    link_table.c[link_col] == category.id,
                )
            )
        ).first()
        if existing_link is None:
            await db.execute(
                link_table.insert().values(
                    processing_activity_id=pa_uuid, **{link_col: category.id}
                )
            )
            added.append(category.name)
        else:
            already.append(category.name)
    await db.flush()

    parts = [f'Tagged "{activity.name}" with {kind}.']
    if added:
        parts.append("Added: " + ", ".join(added) + ".")
    if already:
        parts.append("Already tagged: " + ", ".join(already) + ".")
    if created:
        parts.append("New to the vocabulary: " + ", ".join(created) + ".")
    return " ".join(parts)


async def _find_or_create_category[CatT: (DataSubjectCategory, DataCategory)](
    db: AsyncSession,
    model: type[CatT],
    binding: MatterBinding,
    name: str,
    created: list[str],
) -> CatT:
    """Find a vocabulary term case-insensitively, or create it race-safely.

    The find + the unique backstop both key on ``lower(name)`` (PRIV-6a). The
    create runs in a SAVEPOINT so a concurrent insert of the same term (its
    ``IntegrityError`` against the ``lower(name)`` unique index) is absorbed and
    the winning row re-selected — the dispatch never raises a DB error.
    """
    lowered = func.lower(model.name)
    key = name.casefold()
    found = (await db.execute(select(model).where(lowered == key))).scalar_one_or_none()
    if found is not None:
        return found
    try:
        async with db.begin_nested():  # SAVEPOINT — isolate a possible unique violation
            category = model(source_project_id=binding.project_id, name=name)
            db.add(category)
            await db.flush()
        created.append(name)
        return category
    except IntegrityError:
        # Lost the race (or a case-variant exists): reuse the committed winner.
        return (await db.execute(select(model).where(lowered == key))).scalar_one()


async def _list_categories[CatT: (DataSubjectCategory, DataCategory)](
    db: AsyncSession,
    *,
    model: type[CatT],
    empty: str,
    heading: str,
) -> str:
    """Format a category vocabulary (oldest first), with IDs and per-term usage counts."""
    rows = (
        (
            await db.execute(
                select(model)
                .options(
                    selectinload(model.processing_activities),
                    # The per-term usage count must reflect LIVE activities only —
                    # a retired activity no longer "uses" the term (matches the API
                    # _all_categories; ADR-F023). Without this, an orphaned term reads
                    # as still in use.
                    with_loader_criteria(
                        ProcessingActivity, ProcessingActivity.retired_at.is_(None)
                    ),
                )
                .order_by(model.created_at.asc(), model.name.asc())
                .limit(_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return empty

    blocks: list[str] = []
    for row in rows:
        n = len(row.processing_activities)
        noun = "activity" if n == 1 else "activities"
        blocks.append(f"- [{row.id}] {row.name} ({n} {noun})")
    return f"Company ROPA — {len(rows)} {heading}:\n\n" + "\n".join(blocks)


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
