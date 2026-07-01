"""Run-scoped AI-systems register change ledger — AIC-1 (fork, ADR-F057/F024).

The AI Compliance twin of :mod:`app.agents.ropa_changes` (PRIV-9b): when the AI
Compliance agent mutates the deployment-global ``ai_systems`` register, the cockpit
highlights exactly which row changed, live, as it commits ("watch it happen").

Same design as the ROPA ledger: a B-class object (ADR-F004), injected at
:func:`app.agents.compliance_tools.build_compliance_tools`, never model-visible.
Each mutating tool records its ``(kind, id, verb)`` after a successful flush; the
runner drains it and emits a transient ``data-compliance-change`` frame
(:meth:`app.agents.stream.RunStreamPublisher.ai_system_changed`). It structurally
satisfies the area-agnostic :class:`~app.agents.live_changes.LiveChange` /
:class:`~app.agents.live_changes.ChangeLedger` Protocols, so the runner drain needs
no AI-Compliance-specific code.

Render-determinism (ADR-F004): the ledger drives a best-effort highlight only. The
register's poll/reconcile is the source of truth — a dropped or spurious entry
loses or mis-fires a flash, it can never corrupt the register. Ids are audit-safe
(counts/types/**IDs**, never raw values).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # publisher typed structurally; importing it at runtime would cycle
    from app.agents.stream import RunStreamPublisher

# AIC-1 renders one top-level register entity. Future AI Compliance entities
# (providers, classifications) add kinds here.
AiSystemChangeKind = str  # 'ai_system'
AiSystemChangeVerb = str  # 'create' | 'retire'


@dataclass(frozen=True)
class AiSystemChange:
    """One register mutation worth highlighting: which row, and how it changed.

    ``id`` is the stringified row UUID — the entity id the read DTO keys on, so the
    client matches it directly against its ``{#each}`` rows.
    """

    kind: AiSystemChangeKind
    id: str
    verb: AiSystemChangeVerb

    def publish(self, publisher: RunStreamPublisher) -> None:
        """Announce this change as its transient ``data-compliance-change`` frame.

        The :class:`~app.agents.live_changes.LiveChange` contract — lets the runner
        drain any area's ledger uniformly.
        """
        publisher.ai_system_changed(kind=self.kind, entity_id=self.id, verb=self.verb)


@dataclass
class AiSystemChangeLedger:
    """Append-only ledger of register mutations for one run, drained FIFO.

    :meth:`record` is called by the tool bodies after a successful flush (only on a
    REAL change — never a rejection or an idempotent no-op). :meth:`drain` returns
    everything appended since the last drain and advances the cursor, so every
    change is emitted exactly once.
    """

    _changes: list[AiSystemChange] = field(default_factory=list)
    _emitted: int = 0

    def record(
        self, kind: AiSystemChangeKind, entity_id: str | uuid.UUID, verb: AiSystemChangeVerb
    ) -> None:
        self._changes.append(AiSystemChange(kind=kind, id=str(entity_id), verb=verb))

    def drain(self) -> list[AiSystemChange]:
        """Changes appended since the last drain (advances the cursor)."""
        new = self._changes[self._emitted :]
        self._emitted = len(self._changes)
        return new
