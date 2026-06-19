"""Privacy programme summary — PRIV-6b (fork, ADR-F018/F019).

Pure aggregation over the deployment-global ROPA register: turns the loaded
``*Read`` DTOs (exactly what the Article 30 export assembles) into a
:class:`~app.schemas.ropa.ProgrammeSummary` — headline totals, categorical
breakdowns in canonical enum order, and honest "needs attention" gaps. No I/O:
the read handler loads the rows and hands them here, mirroring
``app.ropa_export.build_export`` — so the aggregation is unit-tested in isolation
and there is one load path (``app.api.ropa._load_register``) for both the export
and the dashboard.

Counts only (no free-text): the summary payload carries even less than the
register read endpoints, so neither the shared-read posture (ADR-F019) nor the
private→shared confused-deputy concern (Backlog / ADR-F021) is heightened here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from enum import StrEnum

from app.schemas.ropa import (
    ControllerRole,
    CountByValue,
    DpaStatus,
    LawfulBasis,
    ProcessingActivityRead,
    ProgrammeGaps,
    ProgrammeSummary,
    SystemRead,
    VendorRead,
)

# DPA states that count as "needs attention" — an Article 28 agreement still
# owed. ``in_place`` and ``not_required`` are settled; ``pending`` and ``none``
# are outstanding.
_DPA_OUTSTANDING = frozenset({DpaStatus.PENDING.value, DpaStatus.NONE.value})


def _breakdown(values: Iterable[str], members: Sequence[StrEnum]) -> list[CountByValue]:
    """Count ``values`` into one bucket per enum member, in canonical enum order.

    Zero buckets are kept so the breakdown renders deterministically; an off-enum
    value (impossible past the DB CHECK, but be defensive) is simply not counted.
    """
    counts = Counter(values)
    return [CountByValue(value=m.value, count=counts.get(m.value, 0)) for m in members]


def build_summary(
    activities: list[ProcessingActivityRead],
    systems: list[SystemRead],
    vendors: list[VendorRead],
) -> ProgrammeSummary:
    """Aggregate the loaded register into the programme overview (PRIV-6b)."""
    return ProgrammeSummary(
        activities_total=len(activities),
        systems_total=len(systems),
        vendors_total=len(vendors),
        transfers_total=sum(len(a.transfers) for a in activities),
        transfers_restricted=sum(1 for a in activities for t in a.transfers if t.restricted),
        special_category_activities=sum(1 for a in activities if a.special_category),
        systems_using_ai=sum(1 for s in systems if s.ai_usage),
        lawful_basis=_breakdown((a.lawful_basis for a in activities), list(LawfulBasis)),
        controller_role=_breakdown((a.controller_role for a in activities), list(ControllerRole)),
        dpa_status=_breakdown((v.dpa_status for v in vendors), list(DpaStatus)),
        gaps=ProgrammeGaps(
            activities_without_systems=sum(1 for a in activities if not a.systems),
            activities_without_recipients=sum(1 for a in activities if not a.vendors),
            activities_without_data_categories=sum(1 for a in activities if not a.data_categories),
            activities_without_data_subjects=sum(
                1 for a in activities if not a.data_subject_categories
            ),
            vendors_without_dpa=sum(1 for v in vendors if v.dpa_status in _DPA_OUTSTANDING),
        ),
    )
