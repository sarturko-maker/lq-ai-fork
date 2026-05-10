"""add requested_model to messages — ADR 0011 follow-on

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-10

ADR 0011 makes alias resolution visible: every alias publishes its
resolved primary target inline, and ``Message.routed_provider`` /
``routed_model`` capture *what actually ran*. The piece that's been
missing is *what the user asked for*. If a user picks ``smart`` and the
gateway routes to ``anthropic-prod/claude-opus-4-7``, today only the
resolved pair lands on the row; the alias label is lost. The
TierDetailsPanel can describe the destination but not the journey
("Requested: smart → routed to anthropic-prod/claude-opus-4-7").

This migration adds ``requested_model`` — the value the client sent in
``ChatCompletionRequest.model``. Nullable for backwards compatibility
with rows written before this column existed. Plain TEXT (no length
cap) because aliases and direct ``provider/model`` strings vary in
length and are operator-defined.

No index — query patterns hit messages by ``chat_id`` (already indexed)
and ``id`` (PK). Filtering by ``requested_model`` directly is not a
known access pattern; we can add an index when one materializes.

Reversible: ``downgrade()`` drops the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("requested_model", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "requested_model")
