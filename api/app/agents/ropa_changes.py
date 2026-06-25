"""Run-scoped ROPA change ledger — PRIV-9b (fork, ADR-F024).

The honest signal behind the cockpit's *changed-row highlight*: when the Privacy
agent mutates the deployment-global ROPA register, the user should see exactly
which row changed, live, as it commits (PRIV-9 "watch it happen").

Why a ledger and not the tool return. Every guarded ROPA tool returns a plain
prose string (``guarded_dispatch`` is typed ``-> str``); the runner's
``on_tool_end`` sees only that string. Threading a structured ``(kind, id,
verb)`` onto the tool output would mean polluting the model-visible prose
(fragile to parse, truncation-prone) or relying on langchain
``content_and_artifact`` (version-coupled). Instead each tool body records its
change into THIS ledger — a B-class object (ADR-F004), injected at
:func:`app.agents.ropa_tools.build_ropa_tools`, never model-visible. The runner
drains it and emits a dedicated transient ``data-ropa-change`` stream frame
(:meth:`app.agents.stream.RunStreamPublisher.ropa_changed`).

Render-determinism (ADR-F004) governs the contract: the ledger drives a
best-effort *highlight* only. The settled re-read (the register's poll/reconcile)
remains the source of truth — a dropped or even a spurious entry loses or
mis-fires a flash, it can never corrupt the register. Ids are explicitly allowed
by the audit contract (counts/types/**IDs**, never raw values), so emitting them
is audit-safe.

One ledger per run (created at the composition point), so there is no cross-run
leakage; appends (from tool bodies) and drains (from the runner) all run on the
one event loop, so the plain list needs no lock.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # publisher typed structurally; importing it at runtime would cycle
    from app.agents.stream import RunStreamPublisher

# The register's three top-level rows (the tables the UI renders + highlights).
# Links/tags/transfers map to the affected *activity* (and a link also records
# the system/vendor it touched), so the visible top-level row is what washes.
RopaChangeKind = str  # 'processing_activity' | 'system' | 'vendor'
RopaChangeVerb = str  # 'create' | 'retire' | 'link' | 'unlink' | 'tag'


@dataclass(frozen=True)
class RopaChange:
    """One register mutation worth highlighting: which row, and how it changed.

    ``id`` is the stringified row UUID — the entity id the read DTOs key on, so
    the client matches it directly against its ``{#each}`` rows. ``verb`` is
    carried for honesty/auditing and future per-verb treatment; the v1 highlight
    is verb-agnostic (any change washes the row).
    """

    kind: RopaChangeKind
    id: str
    verb: RopaChangeVerb

    def publish(self, publisher: RunStreamPublisher) -> None:
        """Announce this register change as its transient ``data-ropa-change`` frame.

        The :class:`~app.agents.live_changes.LiveChange` contract — lets the runner
        drain any area's ledger uniformly (PRIV-9b's wash, C5b-3's verdict chips, …).
        """
        publisher.ropa_changed(kind=self.kind, entity_id=self.id, verb=self.verb)


@dataclass
class RopaChangeLedger:
    """Append-only ledger of register mutations for one run, drained FIFO.

    :meth:`record` is called by the tool bodies after a successful flush (only on
    a REAL change — never an idempotent no-op or a rejection). :meth:`drain`
    returns everything appended since the last drain and advances the cursor, so
    every change is emitted exactly once regardless of which ``tool_result`` step
    triggers the drain (robust to concurrent tool calls).
    """

    _changes: list[RopaChange] = field(default_factory=list)
    _emitted: int = 0

    def record(
        self, kind: RopaChangeKind, entity_id: str | uuid.UUID, verb: RopaChangeVerb
    ) -> None:
        self._changes.append(RopaChange(kind=kind, id=str(entity_id), verb=verb))

    def drain(self) -> list[RopaChange]:
        """Changes appended since the last drain (advances the cursor)."""
        new = self._changes[self._emitted :]
        self._emitted = len(self._changes)
        return new
