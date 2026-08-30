"""INTAKE-3 — thread outcome, inbound message content, and the intake-triage skill (ADR-F086)

Three additive schema items plus one skill binding, all in ONE migration (the
INTAKE-3 slice's only DDL):

* ``intake_threads.outcome`` — nullable TEXT, CHECK IN ('dealt_with',
  'needs_human'). The STRUCTURAL conclusion of the thread's agent run, written
  only by the ``record_intake_outcome`` tool (ADR-F086: "the run concludes via a
  tool call with a closed outcome field — never free prose"). NULL = no run has
  concluded on this thread yet.

  TWO outcomes, not three (ADR-F086 Amendment A1, maintainer ruling 2026-08-29):
  every intake thread IS a matter from message one, so there is no promotion step
  and no "candidate" outcome. ``dealt_with`` closes the matter (``archived_at``);
  ``needs_human`` leaves it open for the lawyer. ``projects.intake_state`` is
  PROVENANCE ("born from email") and the intake-tool grant gate — the agent path
  never writes it, and this migration deliberately leaves the INTAKE-1 column and
  its enum alone (retiring the unused values is a later slice).

* ``intake_messages`` content columns — ``from_addr``, ``to_addrs`` (JSONB
  array), ``subject``, ``body_text``, ``attachment_filenames`` (JSONB array),
  ``provider_timestamp``. **Why these are needed (design gap closed here):**
  the arq job payload is deliberately ONLY the thread id (``queue.py``:
  "the job must re-derive everything else from the DB at execution time...
  keeps email content out of the arq/Redis payload"), but INTAKE-1 persisted
  no message content at all — sender, recipients, body and attachment names
  were dropped on the floor after ingest, so no worker could render the email
  for the agent. These columns are the DB home for the fenced prompt block
  (``app.agents.intake_prompt``). They are ALSO the storage for a
  ``direction='out'`` draft written by ``draft_email_reply`` (a not-yet-sent
  reply); delivery lands in INTAKE-4.

  Bounds mirror the boundary caps in ``app.schemas.intake`` (320 chars per
  address, 998 for a subject, 512k for the body) as CHECKs — defense in depth
  behind the Pydantic boundary, never a substitute for it.

* the ``skills/intake-triage`` doctrine skill is bound to Commercial and
  adopted into the Org Library exactly like ``0097_bind_adversarial_review_skill``
  (idempotent NOT-EXISTS inserts; users-gated adoption so an EXISTING
  deployment does not get a bound-but-unadopted — i.e. silently inert — skill
  on upgrade day, while a fresh org adopts it through the Commercial profile
  apply, B-7a).

Downgrade is symmetric and drops only what this migration added — the two columns sets
and their CHECKs, the Commercial binding, AND the ``org_library_entries`` adoption row
(the 0097 precedent: a downgrade that left the adoption behind would leave the Library
advertising a skill nothing is bound to).

Revision ID: 0099
Revises: 0098
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

# CHECK value set — mirrors app.models.intake._THREAD_OUTCOMES. Keep in sync.
_THREAD_OUTCOMES = ("dealt_with", "needs_human")

_AREA_KEY = "commercial"
_SKILL_NAME = "intake-triage"


def upgrade() -> None:
    quoted = ", ".join(f"'{v}'" for v in _THREAD_OUTCOMES)
    op.add_column("intake_threads", sa.Column("outcome", sa.Text(), nullable=True))
    op.create_check_constraint(
        "chk_intake_threads_outcome",
        "intake_threads",
        f"outcome IS NULL OR outcome IN ({quoted})",
    )

    op.add_column("intake_messages", sa.Column("from_addr", sa.Text(), nullable=True))
    op.add_column(
        "intake_messages",
        sa.Column("to_addrs", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("intake_messages", sa.Column("subject", sa.Text(), nullable=True))
    op.add_column("intake_messages", sa.Column("body_text", sa.Text(), nullable=True))
    op.add_column(
        "intake_messages",
        sa.Column(
            "attachment_filenames",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "intake_messages",
        sa.Column("provider_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "chk_intake_messages_from_addr_len",
        "intake_messages",
        "from_addr IS NULL OR char_length(from_addr) BETWEEN 1 AND 320",
    )
    op.create_check_constraint(
        "chk_intake_messages_subject_len",
        "intake_messages",
        "subject IS NULL OR char_length(subject) <= 998",
    )
    op.create_check_constraint(
        "chk_intake_messages_body_text_len",
        "intake_messages",
        "body_text IS NULL OR char_length(body_text) <= 512000",
    )

    conn = op.get_bind()
    # Bind the doctrine skill to Commercial (only where the seeded area exists;
    # CAST — the 0056 asyncpg one-placeholder-two-types trap).
    conn.execute(
        sa.text(
            "INSERT INTO practice_area_skills (practice_area_id, skill_name) "
            "SELECT pa.id, CAST(:skill AS VARCHAR) FROM practice_areas pa "
            "WHERE pa.key = :key AND NOT EXISTS ("
            "  SELECT 1 FROM practice_area_skills s "
            "  WHERE s.practice_area_id = pa.id AND s.skill_name = CAST(:skill AS VARCHAR)"
            ")"
        ),
        {"skill": _SKILL_NAME, "key": _AREA_KEY},
    )
    # Users-empty gate (0088/0097 posture): an existing deployment adopts the shipped
    # skill so the new binding resolves on upgrade day; a fresh org's Library stays
    # empty (the Commercial profile apply adopts it there).
    has_users = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM users)")).scalar()
    if has_users:
        conn.execute(
            sa.text(
                "INSERT INTO org_library_entries (capability_kind, capability_key) "
                "SELECT 'skill', CAST(:skill AS TEXT) "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM org_library_entries e "
                "  WHERE e.capability_kind = 'skill' "
                "    AND e.capability_key = CAST(:skill AS TEXT)"
                ")"
            ),
            {"skill": _SKILL_NAME},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM org_library_entries "
            "WHERE capability_kind = 'skill' AND capability_key = :skill"
        ),
        {"skill": _SKILL_NAME},
    )
    conn.execute(
        sa.text(
            "DELETE FROM practice_area_skills "
            "WHERE skill_name = :skill AND practice_area_id = ("
            "  SELECT id FROM practice_areas WHERE key = :key"
            ")"
        ),
        {"skill": _SKILL_NAME, "key": _AREA_KEY},
    )

    op.drop_constraint("chk_intake_messages_body_text_len", "intake_messages", type_="check")
    op.drop_constraint("chk_intake_messages_subject_len", "intake_messages", type_="check")
    op.drop_constraint("chk_intake_messages_from_addr_len", "intake_messages", type_="check")
    op.drop_column("intake_messages", "provider_timestamp")
    op.drop_column("intake_messages", "attachment_filenames")
    op.drop_column("intake_messages", "body_text")
    op.drop_column("intake_messages", "subject")
    op.drop_column("intake_messages", "to_addrs")
    op.drop_column("intake_messages", "from_addr")

    op.drop_constraint("chk_intake_threads_outcome", "intake_threads", type_="check")
    op.drop_column("intake_threads", "outcome")
