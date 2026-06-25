"""The run-scoped deal-change ledger — C5b-3 (ADR-F032/F024), pure unit (no DB).

The ledger is the producer→consumer seam for the cockpit's live verdict chips:
``respond_to_counterparty`` appends one entry per decision, the runner drains them
onto the stream as transient ``data-deal-change`` frames. The load-bearing
property mirrors the ROPA ledger: **drain is FIFO + once-each** — a cursor
advances, so a verdict is emitted by exactly one drain regardless of how many
``tool_result`` steps trigger drains.
"""

from __future__ import annotations

from app.agents.deal_changes import DealChange, DealChangeLedger


def test_drain_returns_only_new_changes_and_advances_cursor() -> None:
    ledger = DealChangeLedger()
    assert ledger.drain() == []  # empty ledger → nothing

    ledger.record("C1", "accept")
    ledger.record("C2", "counter")
    first = ledger.drain()
    assert first == [
        DealChange(ref="C1", verdict="accept"),
        DealChange(ref="C2", verdict="counter"),
    ]

    # Nothing new since the last drain → empty, never a re-emit (once-each).
    assert ledger.drain() == []

    ledger.record("Com:1", "escalate")
    assert ledger.drain() == [DealChange(ref="Com:1", verdict="escalate")]
