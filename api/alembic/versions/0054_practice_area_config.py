"""practice_area config vocabulary + projects/audit FK — F1-S3 (fork, ADR-F002/F004/F010)

ADDITIVE extension of 0053 (never recreates the table):

* ``practice_areas`` gains config columns:
  - ``profile_md``        — area profile markdown, folded into the agent system prompt.
  - ``default_tier_floor``— area's default minimum inference tier (1..5), combined
                            with the matter floor via ``min()`` API-side.
  - ``agent_config``      — declarative shape data consumed by ONE renderer (ADR-F004):
                            ``subagents`` (declarative SubAgent specs — NO model key,
                            ADR-F010), and by-reference ``playbooks``/``mcp_servers``
                            (ids/names only, NO credentials — NORTH-STAR inv 3; recorded
                            for forward config, not consumed by the renderer yet).
* ``projects.practice_area_id`` — nullable FK (legacy/unfiled matters keep NULL; no
  backfill, the 0052 posture). CHECK: sandbox rows (``is_sandbox=true``) are not matters
  and must not file under an area.
* ``audit_log.practice_area_id`` — nullable FK, first-class for per-area slicing (F002).
* ``practice_area_skills`` — m2m join (practice_area_id, skill_name TEXT); skills stay
  filesystem-canonical (ADR-0004), mirrors ``project_skills``.

All FKs ``ON DELETE SET NULL`` (deleting a configured-then-removed area must not delete
matters or audit history). Commercial gets a real profile + tier floor via an idempotent
``_seed_commercial_config`` (0033/0053 precedent: write only when the column is still
NULL — never overwrite an operator edit).

Revision ID: 0054
Revises: 0053
Create Date: 2026-06-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


# Commercial's seed profile — the area identity the per-area agent renders from.
# Plain operator-editable prose (the admin PATCH can replace it); the seed writes
# it only when profile_md is still NULL so re-running never clobbers an edit.
_COMMERCIAL_PROFILE_MD = (
    "You are the Commercial practice agent for an in-house legal team. You work "
    "matter by matter on commercial agreements — NDAs, MSAs, SOWs, DPAs, and their "
    "renewals and amendments. Be precise about parties, defined terms, liability "
    "caps, indemnities, termination, and governing law. Ground every claim in the "
    "matter's own documents and cite the document name and page; when the documents "
    "don't answer the question, say so plainly rather than guessing. Prefer the "
    "in-house posture: protect our position, flag risk, and propose concrete "
    "fallbacks the business can act on."
)
# Commercial seeds NO area tier floor. The area-floor MECHANISM ships and is
# enforced (the gateway combines it via min() and rejects too-weak models —
# proven live), but the only S9-qualified model today is MiniMax-M3 at tier 4
# (weaker). An area floor stronger than 4 would make EVERY run under the area
# fail tier_below_minimum until a stronger model is qualified — i.e. it would
# make Commercial unusable, defeating F1's "one configurable area usable for a
# real task". An operator sets a floor via PATCH once a qualifying model lands
# (model-compatibility.md, S9). Matters may still set their own floor.
_COMMERCIAL_TIER_FLOOR: int | None = None


def upgrade() -> None:
    op.add_column("practice_areas", sa.Column("profile_md", sa.Text(), nullable=True))
    op.add_column(
        "practice_areas",
        sa.Column("default_tier_floor", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        "chk_practice_areas_tier_range",
        "practice_areas",
        "default_tier_floor IS NULL OR (default_tier_floor BETWEEN 1 AND 5)",
    )
    op.add_column(
        "practice_areas",
        sa.Column(
            "agent_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.add_column(
        "projects",
        sa.Column("practice_area_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_practice_area_id",
        "projects",
        "practice_areas",
        ["practice_area_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "chk_projects_sandbox_no_area",
        "projects",
        "NOT (is_sandbox AND practice_area_id IS NOT NULL)",
    )
    op.create_index(
        "idx_projects_practice_area_id",
        "projects",
        ["practice_area_id"],
        postgresql_where=sa.text("practice_area_id IS NOT NULL AND archived_at IS NULL"),
    )

    op.add_column(
        "audit_log",
        sa.Column("practice_area_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_log_practice_area_id",
        "audit_log",
        "practice_areas",
        ["practice_area_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "practice_area_skills",
        sa.Column("practice_area_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_name", sa.String(), nullable=False),
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["practice_area_id"],
            ["practice_areas.id"],
            name="fk_practice_area_skills_area_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("practice_area_id", "skill_name", name="pk_practice_area_skills"),
        sa.CheckConstraint(
            "char_length(skill_name) > 0 AND char_length(skill_name) <= 200",
            name="chk_practice_area_skills_name_len",
        ),
    )

    _seed_commercial_config(op.get_bind())


def _seed_commercial_config(conn: sa.engine.Connection) -> None:
    """Give Commercial a real profile + tier floor — idempotently.

    Module-level (not inlined) so the idempotency contract is unit-testable
    (tests/test_practice_areas.py). Writes profile_md / default_tier_floor ONLY
    when they are still NULL, so re-running on an operator-edited database never
    overwrites a deliberate change (0033/0053 check-before-write precedent).
    """
    conn.execute(
        sa.text(
            "UPDATE practice_areas SET profile_md = :profile "
            "WHERE key = 'commercial' AND profile_md IS NULL"
        ),
        {"profile": _COMMERCIAL_PROFILE_MD},
    )
    if _COMMERCIAL_TIER_FLOOR is not None:
        conn.execute(
            sa.text(
                "UPDATE practice_areas SET default_tier_floor = :tier "
                "WHERE key = 'commercial' AND default_tier_floor IS NULL"
            ),
            {"tier": _COMMERCIAL_TIER_FLOOR},
        )


def downgrade() -> None:
    op.drop_table("practice_area_skills")
    op.drop_constraint("fk_audit_log_practice_area_id", "audit_log", type_="foreignkey")
    op.drop_column("audit_log", "practice_area_id")
    op.drop_index("idx_projects_practice_area_id", table_name="projects")
    op.drop_constraint("chk_projects_sandbox_no_area", "projects", type_="check")
    op.drop_constraint("fk_projects_practice_area_id", "projects", type_="foreignkey")
    op.drop_column("projects", "practice_area_id")
    op.drop_column("practice_areas", "agent_config")
    op.drop_constraint("chk_practice_areas_tier_range", "practice_areas", type_="check")
    op.drop_column("practice_areas", "default_tier_floor")
    op.drop_column("practice_areas", "profile_md")
