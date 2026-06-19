"""The run-scoped ROPA change ledger — PRIV-9b (ADR-F024), pure unit (no DB).

The ledger is the producer→consumer seam for the cockpit's live changed-row
highlight: the ROPA tools append, the runner drains onto the stream. The two
load-bearing properties:

* **drain is FIFO + once-each** — a cursor advances, so a change is emitted by
  exactly one drain regardless of how many ``tool_result`` steps trigger drains
  (the concurrency-safety the runner relies on);
* **ids are stringified** — the wire/DTO key the client matches on is a string,
  whether the tool recorded a ``uuid.UUID`` or an already-stringified id.
"""

from __future__ import annotations

import uuid

from app.agents.ropa_changes import RopaChange, RopaChangeLedger


def test_drain_returns_only_new_changes_and_advances_cursor() -> None:
    ledger = RopaChangeLedger()
    assert ledger.drain() == []  # empty ledger → nothing

    ledger.record("system", "id-1", "create")
    ledger.record("processing_activity", "id-2", "link")
    first = ledger.drain()
    assert first == [
        RopaChange(kind="system", id="id-1", verb="create"),
        RopaChange(kind="processing_activity", id="id-2", verb="link"),
    ]

    # Nothing new since the last drain → empty, never a re-emit (once-each).
    assert ledger.drain() == []

    ledger.record("vendor", "id-3", "retire")
    assert ledger.drain() == [RopaChange(kind="vendor", id="id-3", verb="retire")]


def test_record_stringifies_uuid_ids() -> None:
    ledger = RopaChangeLedger()
    eid = uuid.uuid4()
    ledger.record("system", eid, "create")
    (change,) = ledger.drain()
    assert change.id == str(eid)
    assert isinstance(change.id, str)
