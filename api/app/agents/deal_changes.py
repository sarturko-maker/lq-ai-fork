"""Run-scoped deal-change ledger — C5b-3 (fork, ADR-F032/F024/F004).

The honest signal behind the cockpit's live *verdict chips*: when the Commercial
agent responds to a counterparty's marked-up contract (``respond_to_counterparty``),
the user should see each per-item verdict — accept / reject / counter / leave_open /
escalate / reply — flash inline in the conversation as the response lands ("watch
the negotiation round happen").

Companion to :mod:`app.agents.ropa_changes` (PRIV-9b): the SAME ledger seam
(:mod:`app.agents.live_changes`), a DIFFERENT transient frame. Privacy washes a
register row; Commercial has no deal-terms panel, so the chip lives in the
conversation (:meth:`app.agents.stream.RunStreamPublisher.deal_changed`). The
ledger is a B-class object (ADR-F004), injected at
:func:`app.agents.commercial_tools.build_commercial_tools`, never model-visible.

Render-determinism (ADR-F004): the chip is best-effort animation only. The saved
response ``.docx`` (the work product) and the run timeline remain the truth — a
dropped or spurious entry loses or mis-fires a chip, never the record. The frame
carries only ``ref`` (a synthetic decision reference) + ``verdict`` (a closed
taxonomy enum), both audit-safe (the contract allows counts/types/**IDs**/refs,
never raw clause text).

One ledger per run (created at the composition point), so no cross-run leakage;
appends (from the tool body) and drains (from the runner) all run on the one
event loop, so the plain list needs no lock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # publisher typed structurally; importing it at runtime would cycle
    from app.agents.stream import RunStreamPublisher

# The closed negotiation taxonomy (mirrors commercial_tools._RESPOND_VERDICTS):
# a change is accept|reject|counter|leave_open|escalate; a comment is
# reply|leave_open|escalate. The chip colours by verdict; the web validator
# rejects any value outside this set.
DealVerdict = str


@dataclass(frozen=True)
class DealChange:
    """One counterparty item the agent just decided: which ref, what verdict.

    ``ref`` is the synthetic decision reference the negotiation loop assigns —
    ``C1``, ``C2``, … for a tracked change, ``Com:N`` for a comment — a stable id
    decoupled from Adeu's internal numbering, NOT raw counterparty text. ``verdict``
    is the closed taxonomy. Both are audit-safe.
    """

    ref: str
    verdict: DealVerdict

    def publish(self, publisher: RunStreamPublisher) -> None:
        publisher.deal_changed(ref=self.ref, verdict=self.verdict)


@dataclass
class DealChangeLedger:
    """Append-only ledger of negotiation verdicts for one run, drained FIFO.

    :meth:`record` is called by ``respond_to_counterparty`` AFTER the response is
    verified-and-saved (reconciliation proved every decision landed) — only on a
    real, persisted round, never on a rejected proposal. :meth:`drain` returns
    everything appended since the last drain and advances the cursor, so every
    verdict is emitted exactly once regardless of which ``tool_result`` triggers
    the drain.
    """

    _changes: list[DealChange] = field(default_factory=list)
    _emitted: int = 0

    def record(self, ref: str, verdict: DealVerdict) -> None:
        self._changes.append(DealChange(ref=ref, verdict=verdict))

    def drain(self) -> list[DealChange]:
        """Changes appended since the last drain (advances the cursor)."""
        new = self._changes[self._emitted :]
        self._emitted = len(self._changes)
        return new
