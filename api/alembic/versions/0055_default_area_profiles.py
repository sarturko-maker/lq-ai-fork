"""Default practice-area profiles — UX-B-2 (fork, ADR-F002/F004/F015)

Give the four remaining standard areas (Disputes, M&A, Privacy, Employment)
a real ``profile_md`` so they read as **configured** in the cockpit and accept
matters — the same shape 0054 gave Commercial. Profiles are CALIBRATED to the
UX-B-1 live MiniMax-M3 behavior baseline (``docs/fork/evidence/ux-b-1/``,
ADR-F015): M3 grounds single-tool fetches and refuses honestly, but is weak at
multi-step chaining and at clarifying ambiguous requests (sometimes spinning to
``cap_exceeded``). So every profile leans explicitly on the disciplines that
degrade honestly under a tier-4-weak model: *ground every claim in a tool
result and cite it*, *say so plainly when the documents don't answer*, *ask one
brief clarifying question before guessing*, and *never fake a confirmation of an
action you have no tool for*.

Idempotent (0033/0053/0054 check-before-write precedent): each profile is
written ONLY where ``profile_md IS NULL``, so re-running never clobbers an
operator edit. The stored ``configured`` column is set true alongside the
profile to mirror the admin PATCH (``_is_configured`` is the derived source of
truth the API + the matter-creation gate read; we keep the column consistent).

Deliberately NOT seeded here:

* ``default_tier_floor`` stays NULL for every area — the 0054 Commercial
  rationale holds: the only S9-qualified model is MiniMax-M3 at tier 4, so any
  area floor stronger than 4 would make every run under the area fail
  ``tier_below_minimum`` (unusable), and a floor of exactly 4 is redundant. An
  operator sets a floor via PATCH once a stronger model is qualified. Matters
  may still set their own floor.
* ``agent_config`` stays ``{}`` (no subagents). The composition point renders
  area subagents **live** (``composition.py`` → ``area_spec.subagents``), and
  subagent delegation is strictly harder than the multi-step chaining M3
  already struggles with. Per ADR-F015 nothing ships activated until a scenario
  report shows M3 handles it, and the UX-B decomposition sequences subagents to
  **UX-B-4** (after skills) with their own qualification. Seeding executing
  subagents here would activate an unqualified capability — so they are
  deferred. Privacy's forward-looking profile is prose only.

Revision ID: 0055
Revises: 0054
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


# Each profile mirrors the 0054 Commercial shape — identity + domain precision +
# the calibrated discipline sentences (ground/cite, say-so-when-absent,
# clarify-before-guessing, honest decline) — tuned to the area's vocabulary and
# unit-of-work noun. Plain operator-editable prose; the admin PATCH can replace
# any of these. Keyed by the 0053 area ``key``.
_DEFAULT_PROFILES: dict[str, str] = {
    "disputes": (
        "You are the Disputes practice agent for an in-house legal team. You work "
        "matter by matter on contentious matters — pre-action correspondence, "
        "pleadings, witness statements, disclosure, settlement, and the litigation "
        "or arbitration that follows. Be precise about parties, causes of action, "
        "limitation periods, key dates and deadlines, quantum, and the relief "
        "sought. Ground every claim in the matter's own documents and cite the "
        "document name and page; when the documents don't answer the question, say "
        "so plainly rather than guessing. When a request is ambiguous — an unclear "
        "referent, an undated event, or which party is meant — ask one brief "
        "clarifying question before acting rather than guessing. Prefer the in-house "
        "posture: assess the merits soberly, flag exposure and deadline risk early, "
        "and propose concrete next steps the business can act on."
    ),
    "m-and-a": (
        "You are the M&A practice agent for an in-house legal team. You work deal by "
        "deal on corporate transactions — share and asset purchase agreements, "
        "disclosure letters and schedules, due-diligence findings, warranties and "
        "indemnities, conditions precedent, and completion mechanics. Be precise "
        "about the parties, the consideration, warranty and indemnity scope and "
        "limitations, conditions, and the conditions-to-completion timetable. Ground "
        "every claim in the deal's own documents and cite the document name and "
        "page; when the documents don't answer the question, say so plainly rather "
        "than guessing. When a request is ambiguous, ask one brief clarifying "
        "question before acting rather than guessing. Prefer the in-house posture: "
        "surface deal risk and diligence gaps, protect our side's position, and "
        "propose concrete fallbacks the deal team can negotiate."
    ),
    "privacy": (
        "You are the Privacy practice agent for an in-house legal team. You work "
        "programme by programme on data-protection work under the UK GDPR and GDPR — "
        "records of processing (ROPA), data-protection impact assessments (DPIAs), "
        "data-processing agreements, data-subject rights, international transfers, "
        "retention, and breach response. Be precise about the personal data and "
        "categories involved, the lawful basis, the roles of controller and "
        "processor, purposes, recipients, and transfer mechanisms. Ground every "
        "claim in the programme's own documents and records and cite the document "
        "name and page; when the records don't answer the question, say so plainly "
        "rather than guessing. When a request is ambiguous, ask one brief clarifying "
        "question before acting rather than guessing. Prefer the in-house posture: "
        "map the processing, flag compliance gaps and risk, and propose concrete, "
        "proportionate remediation the business can adopt. This area is the home for "
        "forthcoming privacy modules (data discovery, ROPA and DPIA tooling); work "
        "agentically from the programme's own evidence rather than assuming a fixed "
        "process."
    ),
    "employment": (
        "You are the Employment practice agent for an in-house legal team. You work "
        "matter by matter on workforce matters — employment contracts and policies, "
        "grievances and disciplinaries, performance and dismissal, redundancy and "
        "TUPE, settlement agreements, and tribunal claims. Be precise about the "
        "parties and their roles, dates of service and key events, contractual and "
        "statutory entitlements, notice and consultation obligations, and time "
        "limits. Ground every claim in the matter's own documents and cite the "
        "document name and page; when the documents don't answer the question, say "
        "so plainly rather than guessing. When a request is ambiguous, ask one brief "
        "clarifying question before acting rather than guessing. Prefer the in-house "
        "posture: protect the organisation's position, flag legal and process risk, "
        "and propose concrete, compliant fallbacks the business can act on."
    ),
}


def upgrade() -> None:
    _seed_default_area_profiles(op.get_bind())


def _seed_default_area_profiles(conn: sa.engine.Connection) -> None:
    """Write each default area's profile + configured=true — idempotently.

    Module-level (not inlined) so the idempotency contract is unit-testable
    (tests/test_practice_areas.py). Writes ``profile_md`` ONLY where it is
    still NULL, so re-running on an operator-edited database never overwrites a
    deliberate change (0033/0053/0054 check-before-write precedent). The stored
    ``configured`` column is set true in the same statement to mirror the admin
    PATCH; the derived ``_is_configured`` (the API + matter-gate source of
    truth) keys off ``profile_md``.
    """
    for key, profile in _DEFAULT_PROFILES.items():
        conn.execute(
            sa.text(
                "UPDATE practice_areas "
                "SET profile_md = :profile, configured = true "
                "WHERE key = :key AND profile_md IS NULL"
            ),
            {"profile": profile, "key": key},
        )


def downgrade() -> None:
    # Reverse only the rows this migration configured — restore the inert state
    # (NULL profile + configured=false) for areas still carrying the seeded
    # profile verbatim, so an operator edit is never silently dropped.
    conn = op.get_bind()
    for key, profile in _DEFAULT_PROFILES.items():
        conn.execute(
            sa.text(
                "UPDATE practice_areas "
                "SET profile_md = NULL, configured = false "
                "WHERE key = :key AND profile_md = :profile"
            ),
            {"profile": profile, "key": key},
        )
