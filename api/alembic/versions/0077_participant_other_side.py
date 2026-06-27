"""matter_participants — add the 'other' (third-party) side (ADR-F048 Slice 2)

A negotiation often involves a KNOWN third party who is neither our side nor the
direct counterparty — an escrow agent, a lender's counsel, a regulator. Slice 1
shipped the roster with ``side`` ∈ {ours, counterparty, unknown}; Slice 2 adds
``'other'`` so such a participant has a home and the agent treats their edits
distinctly (weigh, never silently adopt) rather than mis-bucketing them as the
counterparty or as "unknown".

CHECK-only change, mirroring the ``0070`` ``fact_type`` extension precedent
(drop + recreate the CHECK). Additive: no column/table/backfill. The literal must
stay in sync with ``app.models.project._MATTER_PARTICIPANT_SIDES`` and
``app.schemas.matter_memory.MatterParticipantSide``.

Revision ID: 0077
Revises: 0076
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend the side domain to admit the third-party side.
    op.drop_constraint("chk_matter_participants_side", "matter_participants", type_="check")
    op.create_check_constraint(
        "chk_matter_participants_side",
        "matter_participants",
        "side IN ('ours', 'counterparty', 'other', 'unknown')",
    )


def downgrade() -> None:
    # Third-party rows cannot survive the reverted (stricter) side CHECK.
    op.execute("DELETE FROM matter_participants WHERE side = 'other'")
    op.drop_constraint("chk_matter_participants_side", "matter_participants", type_="check")
    op.create_check_constraint(
        "chk_matter_participants_side",
        "matter_participants",
        "side IN ('ours', 'counterparty', 'unknown')",
    )
