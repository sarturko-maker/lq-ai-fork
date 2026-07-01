"""Seed the AI Compliance practice area — AIC-0 (fork, ADR-F057)

Adds a sixth, **configured** standard area — **AI Compliance** — the home of the
EU AI Act (Regulation (EU) 2024/1689) governance module (ADR-F057). The area does
not exist in the 0053 ``_STANDARD_AREAS`` list, so this migration INTRODUCES the
row (identity + unit noun + profile) in one idempotent INSERT — the 0053-seed +
0055-profile shape collapsed into a single statement because there is no pre-seeded
inert row to promote.

Idempotent (0033/0053/0055 check-before-write precedent): inserts only when the key
is absent; never overwrites an operator edit. ``configured = true`` alongside a
non-empty ``profile_md`` makes the area render a composer and accept matters
(``_is_configured`` — the API + matter-gate source of truth — keys off
``profile_md``). Deliberately NOT seeded, mirroring the 0055 rationale:
``default_tier_floor`` stays NULL (the only qualified model is tier 4, so any
stronger area floor would fail every run ``tier_below_minimum``; a floor of exactly
4 is redundant), and ``agent_config`` stays ``{}`` (no subagents — the helper roster
ships only once a scenario report qualifies it; skills bind in AIC-7).

Scope note (AIC-0 = the configured-area + doctrine shell): the domain tools — the
AI-system register, and the deterministic classification engine that OWNS the risk
verdict (ADR-F057) — are NOT wired here. Every matter filed under this area already
gets the read-only memory tiers + document retrieval for free (area-agnostic
grants), so the agent answers with the AI-Act persona over the matter's own
evidence. The AI-system register lands in AIC-1; the verdict engine in AIC-2.

Revision ID: 0084
Revises: 0083
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


_AREA_KEY = "ai-compliance"
_AREA_NAME = "AI Compliance"
_AREA_UNIT_LABEL = "Programme"
_AREA_POSITION = 6

# The agent's job description for the area — folded into the system prompt as the
# controlling doctrine (LAST, so it governs). Same calibrated shape as the 0055
# profiles (identity + domain precision + ground/cite + say-so-when-absent +
# clarify-before-guessing + honest decline), tuned to the EU AI Act and carrying
# the module's defining discipline: a risk classification is a LEGAL DETERMINATION
# owned by deterministic code (ADR-F057), never asserted by the model — so even
# before the classification tool exists (AIC-2) the agent gathers facts and abstains
# from minting a tier rather than guessing one. Plain operator-editable prose.
_AREA_PROFILE = (
    "You are the AI Compliance practice agent for an in-house legal team. You work "
    "programme by programme on EU AI Act (Regulation (EU) 2024/1689) governance — "
    "maintaining a register of the organisation's AI systems, establishing each "
    "system's role (provider, deployer, importer, distributor) and its risk tier "
    "(prohibited, high-risk, limited/transparency, or minimal), mapping the "
    "obligations that follow from role and tier, and tracking conformity, incidents "
    "and deadlines. Be precise about each system's intended purpose (it drives the "
    "Annex III use-case match), who plays which role, the data and any "
    "general-purpose model involved, and the evidence behind every obligation. A "
    "risk classification is a LEGAL DETERMINATION owned by the deterministic "
    "classification engine, not something you assert: you gather and record the "
    "facts; the engine decides the tier and the applicable articles. Ground every "
    "statement in the system's own documentation and the register and cite it; when "
    "the evidence does not answer the question, say so plainly rather than guessing, "
    "and leave a field blank rather than inventing it. When a request is ambiguous, "
    "ask one brief clarifying question before acting rather than guessing. Prefer "
    "the in-house posture: surface the highest-risk systems and the nearest "
    "deadlines first, flag compliance gaps honestly, and propose concrete, "
    "proportionate steps the business can act on. The Act applies in phases and the "
    "law is still moving — treat dates and thresholds as data to verify against "
    "current primary sources, not as fixed knowledge."
)


def upgrade() -> None:
    _seed_ai_compliance_area(op.get_bind())


def _seed_ai_compliance_area(conn: sa.engine.Connection) -> None:
    """Insert the AI Compliance area configured — idempotently.

    Module-level (not inlined) so the idempotency contract is unit-testable
    (tests/test_practice_areas.py). Inserts ONLY when the key is absent, so
    re-running on a seeded / operator-edited database never duplicates the row and
    never clobbers an edit (0033/0053/0055 check-before-write precedent).
    """
    exists = conn.execute(
        sa.text("SELECT 1 FROM practice_areas WHERE key = :key"),
        {"key": _AREA_KEY},
    ).first()
    if exists:
        return
    conn.execute(
        sa.text(
            "INSERT INTO practice_areas "
            "(key, name, unit_label, configured, position, profile_md) "
            "VALUES (:key, :name, :unit_label, true, :position, :profile)"
        ),
        {
            "key": _AREA_KEY,
            "name": _AREA_NAME,
            "unit_label": _AREA_UNIT_LABEL,
            "position": _AREA_POSITION,
            "profile": _AREA_PROFILE,
        },
    )


def downgrade() -> None:
    # Remove only the row this migration seeded, and only while it still carries the
    # seeded profile verbatim — so an operator edit is never silently dropped. (A
    # FK from an existing matter would block the delete; you do not downgrade past a
    # used area.)
    op.get_bind().execute(
        sa.text("DELETE FROM practice_areas WHERE key = :key AND profile_md = :profile"),
        {"key": _AREA_KEY, "profile": _AREA_PROFILE},
    )
