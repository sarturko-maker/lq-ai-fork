"""link-table reverse FK index parity — PRIV-1 review fix (fork, ADR-F019)

The M:N link tables created in 0062 (taxonomy) and 0064 (assessments) omitted the
secondary index on the TRAILING composite-PK / FK column that the sibling link
tables 0059 (``ix_processing_activity_systems_system_id``) and 0060
(``ix_processing_activity_vendors_vendor_id``) deliberately add. A composite PK
indexes only its LEADING column, so a reverse lookup keyed on the trailing column
seq-scans the link table. Those reverse lookups are live read paths:

* ``selectinload(model.processing_activities)`` over ``DataSubjectCategory`` /
  ``DataCategory`` (``app.api.ropa._all_categories`` + ``app.agents.ropa_tools.
  _list_categories``) → ``WHERE data_*_category_id IN (...)``.
* the assessment register's activity-coverage reads (PRIV-A2/A3) and the
  ``ON DELETE CASCADE`` from a processing activity into
  ``assessment_processing_activities`` → keyed on ``processing_activity_id``.

This adds the three missing reverse indexes so all four privacy link tables carry
the same reverse-FK index. Migration-only by design: like 0059/0060, the link-table
reverse indexes live in the migrations, not the ORM ``Table()`` definitions (those
declare no reverse index for ANY link table — they stay mutually consistent).

The names use the same abbreviations as the FK constraints on these tables
(``fk_pa_dsc_*`` / ``fk_pa_dc_*`` / ``fk_apa_*``) because the full
``ix_<table>_<col>`` form exceeds PostgreSQL's 63-char identifier limit for the
long taxonomy/assessment link-table names.

Revision ID: 0065
Revises: 0064
Create Date: 2026-06-20
"""

from __future__ import annotations

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

# (table, column, index name) — the reverse-FK index each link table was missing.
_REVERSE_INDEXES = (
    (
        "processing_activity_data_subject_categories",
        "data_subject_category_id",
        "ix_pa_dsc_data_subject_category_id",
    ),
    (
        "processing_activity_data_categories",
        "data_category_id",
        "ix_pa_dc_data_category_id",
    ),
    (
        "assessment_processing_activities",
        "processing_activity_id",
        "ix_apa_processing_activity_id",
    ),
)


def upgrade() -> None:
    for table, column, name in _REVERSE_INDEXES:
        op.create_index(name, table, [column])


def downgrade() -> None:
    for table, _column, name in reversed(_REVERSE_INDEXES):
        op.drop_index(name, table_name=table)
