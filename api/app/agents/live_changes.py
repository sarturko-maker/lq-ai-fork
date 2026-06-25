"""The live change-ledger seam — the producer→consumer contract for transient
"watch it happen" cockpit signals (fork; ADR-F024 generalised, ADR-F004).

A *run-scoped* ledger records best-effort UI signals (which row/clause changed,
how) that the runner drains at each ``tool_result`` and the publisher announces
as a transient ``data-*`` SSE frame. Each concrete change knows how to publish
itself (:meth:`LiveChange.publish`), so the runner's drain loop is **area
agnostic**: Privacy records :class:`~app.agents.ropa_changes.RopaChange`
(PRIV-9b, the register-row wash), the Commercial negotiation loop records
:class:`~app.agents.deal_changes.DealChange` (C5b-3, the inline verdict chips),
and a future register (the assessment track) is a third implementer with no
runner change.

Render-determinism (ADR-F004) governs the contract: the ledger drives a
best-effort *animation* only. The settled re-read (the register poll, the saved
work product, the run timeline) remains the source of truth — a dropped or even
a spurious entry loses or mis-fires a flash, it can never corrupt the record.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # publisher typed structurally; importing it at runtime would cycle
    from app.agents.stream import RunStreamPublisher


class LiveChange(Protocol):
    """One change worth a transient cockpit flash, that knows how to announce itself."""

    def publish(self, publisher: RunStreamPublisher) -> None:
        """Emit this change as its dedicated transient stream frame."""
        ...


class ChangeLedger(Protocol):
    """A run-scoped, FIFO-drained ledger of :class:`LiveChange` items.

    The runner holds one per run (created at the composition point for the areas
    that produce signals; ``None`` otherwise — no drain). Concrete ledgers
    (``RopaChangeLedger``, ``DealChangeLedger``) satisfy this structurally.
    """

    def drain(self) -> Sequence[LiveChange]:
        """Changes appended since the last drain (advances the cursor)."""
        ...
