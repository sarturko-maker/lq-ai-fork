# M1 Frontend — Wave D.2 (Skill Creator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three skill-creation modes (capture-from-chat · from-scratch wizard · fork), the four-tab skill detail page (Use / Source / Try-it / Versions), the per-user try-it sandbox matter scope, and the composer slash-invocation surface — landing the last M1 frontend item before v0.1.0 tag.

**Architecture:** Three creation modes converge on one storage (`user_skills` per ADR 0012) and one wizard component (`/lq-ai/skills/new`) with different entry-state. The try-it sandbox is a first-class matter (`projects.is_sandbox=true`, lazy-created per-user) so Wave E onboarding reuses the same column. Slash invocation is the third way to attach context to a chat alongside `📎 KB attach` and the existing skill picker — surfaced as a removable pill in the existing attached-context row, fed by a new `GET /skills/autocomplete` endpoint resolver-aware over user > team > built-in.

**Tech Stack:** FastAPI (api/) · Alembic (Postgres) · SvelteKit + TypeScript (web/) · Pydantic v2 · Vitest · pytest · Cypress.

**Scope contract:** Wave D.2 does NOT implement: full `/slug arg=value` slash grammar, snapshot diffs in Versions tab, conversational capture via the existing `skill-creator` SKILL, cross-device draft sync, Wave E onboarding UX (Acme NDA pre-load + guided walkthrough), or the ADR 0007 amendment. These are DE-222..226 deferrals filed during brainstorming.

**Anchors:** [Design spec 2026-05-13](../specs/2026-05-13-wave-d2-skill-creator-design.md) · [M1 Frontend Design §7.2](../specs/2026-05-10-m1-frontend-design.md#72-skill-creator-three-modes) · [ADR 0012 DB-backed user skills](../../adr/0012-db-backed-user-skills.md) · [Session handoff 2026-05-12](../../SESSION-HANDOFF-2026-05-12-pre-d2.md).

---

## Spec refinements (plan-time corrections)

Two corrections to the spec discovered during reconnaissance. These ARE the contract — the spec's wording will be amended in Wave 9 docs work.

1. **Audit-log column names.** Spec §3 + §6 referenced `target_type` / `target_id`. The actual `audit_log` table (per `api/app/models/audit.py:52-53`) uses **`resource_type`** + **`resource_id`**. The plan uses the actual column names; doc updates land in Task 9.2.

2. **Versions tab endpoint.** Spec §3 implied extending `GET /api/v1/admin/audit-log` with new filters. That endpoint is admin-only (`AdminUser` dependency at `api/app/api/admin.py:96`) — it can't serve a per-skill Versions tab that any owner/team-member must see. The plan introduces a new user-scoped endpoint **`GET /api/v1/user-skills/{id}/versions`** that internally queries `audit_log` after authorizing the caller against skill ownership/membership. The admin endpoint is untouched.

---

## File structure

**Net-new backend files:**

| File | Responsibility |
|---|---|
| `api/alembic/versions/0022_add_projects_is_sandbox.py` | Adds `projects.is_sandbox` column + partial index |
| `api/alembic/versions/0023_add_user_skills_slash_alias_and_forked_from.py` | Adds `slash_alias` + `forked_from` columns + unique-per-owner-active partial index on `slash_alias` |
| `api/tests/test_user_skills_slash_alias.py` | Unit: regex validation, length bounds |
| `api/tests/test_skills_autocomplete_ranking.py` | Unit: prefix vs contains ranking, resolver shadowing |
| `api/tests/test_projects_sandbox_slug_reserved.py` | Unit: POST /projects rejects reserved slug pattern |
| `api/tests/test_skills_capture_payload.py` | Unit: `source_message_id` accepted; `forked_from` write-once |
| `api/tests/integration/test_user_skills_create_with_slash_alias.py` | Integration: collision returns 422; archive frees alias |
| `api/tests/integration/test_skills_autocomplete_endpoint.py` | Integration: ordering + resolution + recent-fallback |
| `api/tests/integration/test_projects_sandbox_ensure.py` | Integration: idempotency, re-create on archive |
| `api/tests/integration/test_projects_sandbox_concurrency.py` | Integration: two concurrent ensures return same row |
| `api/tests/integration/test_user_skills_versions_endpoint.py` | Integration: scoped audit-log view, authz |
| `api/tests/integration/test_skills_send_with_slash_unresolved.py` | Integration: leading `/unknown` falls through |
| `api/tests/test_openapi_wave_d2.py` | Schema-conformance for new + modified endpoints |

**Backend files modified:**

| File | Change |
|---|---|
| `api/app/models/project.py` | Add `is_sandbox: Mapped[bool]` |
| `api/app/models/user_skill.py` | Add `slash_alias: Mapped[str \| None]`, `forked_from: Mapped[str \| None]` |
| `api/app/api/projects.py` | Slug-reservation check; `POST /projects/sandbox/ensure`; `?include_sandbox` / `?only_sandbox` query params |
| `api/app/api/skills.py` | `GET /skills/autocomplete?q=&limit=`; expose `slash_alias` + `forked_from` in skill detail response |
| `api/app/api/user_skills.py` | Accept `slash_alias` / `forked_from` / `source_message_id` on POST + PATCH; `GET /user-skills/{id}/versions` |
| `api/app/schemas/projects.py` | Extend `ProjectCreateRequest` (defensive — `is_sandbox` not user-settable here); extend `ProjectResponse` |
| `api/app/services/audit.py` (or wherever audit-write helpers live) | Write `audit_log` rows on user_skill create/update/archive with rich `details` JSON |

**Net-new frontend files:**

| File | Responsibility |
|---|---|
| `web/src/lib/lq-ai/components/SkillWizard.svelte` | Single-page-sections wizard layout, save/discard/draft footer |
| `web/src/lib/lq-ai/components/SkillWizardSection.svelte` | Section block (title + helper text + slot) |
| `web/src/lib/lq-ai/components/SkillTryItPane.svelte` | Embedded sandbox chat (wizard section 4 AND detail-page tab) |
| `web/src/lib/lq-ai/components/CaptureSkillModal.svelte` | Thin 4-field capture modal |
| `web/src/lib/lq-ai/components/MessageOverflowMenu.svelte` | `⋯` menu on AI messages |
| `web/src/lib/lq-ai/components/SkillTryItTab.svelte` | Detail-page Try-it tab wrapper |
| `web/src/lib/lq-ai/components/SkillVersionsTab.svelte` | Detail-page Versions tab (audit-log view) |
| `web/src/lib/lq-ai/components/SlashPopover.svelte` | Composer slash autocomplete popover |
| `web/src/lib/lq-ai/components/AttachedSkillPill.svelte` | Skill pill in attached-context row |
| `web/src/lib/lq-ai/preferences/capture-affordance.ts` | Toggle store: inline capture button on/off |
| `web/src/lib/lq-ai/__tests__/SkillWizard.test.ts` | Wizard section visibility, slug auto-derivation, draft autosave |
| `web/src/lib/lq-ai/__tests__/CaptureSkillModal.test.ts` | Pre-population from AI message, save call shape |
| `web/src/lib/lq-ai/__tests__/SlashPopover.test.ts` | Bare-`/` trigger, keyboard nav, dismissal |
| `web/src/lib/lq-ai/__tests__/SkillVersionsTab.test.ts` | Built-in empty state, table render |
| `web/src/lib/lq-ai/__tests__/AttachedSkillPill.test.ts` | Render + dismiss + a11y |
| `web/cypress/e2e/wave-d2-skill-creator.cy.ts` | 6 E2E scenarios |

**Frontend files modified:**

| File | Change |
|---|---|
| `web/src/routes/lq-ai/skills/new/+page.svelte` | Shrinks to a wrapper around `SkillWizard`; reads `?fork=` / `?capture=` / `?draft=` |
| `web/src/routes/lq-ai/skills/[id]/+page.svelte` | Adds `🔱 Fork` action + 4-tab layout via `SkillDetailTabs` |
| `web/src/lib/lq-ai/components/SkillDetailTabs.svelte` | Extends from 2 tabs to 4 (use / source / try / versions) |
| `web/src/lib/lq-ai/components/ChatPanel.svelte` | Composer: bare-`/` detector → `SlashPopover`; attached-context row hosts `AttachedSkillPill` |
| `web/src/lib/lq-ai/components/MessageBubble.svelte` | Adds inline `📝 Capture as skill` button + overflow menu trigger |
| `web/src/lib/lq-ai/api/skills.ts` | Adds `autocomplete(q)` method |
| `web/src/lib/lq-ai/api/projects.ts` | Adds `ensureSandbox()` + `listSandbox()` methods |
| `web/src/lib/lq-ai/api/userSkills.ts` | Adds `listVersions(id)` method |

**Docs files modified:**

| File | Change |
|---|---|
| `docs/api/backend-openapi.yaml` | Add `/skills/autocomplete`, `/projects/sandbox/ensure`, `/user-skills/{id}/versions`; extend `/user-skills` body + `/projects` query params |
| `docs/db-schema.md` | Document `projects.is_sandbox`, `user_skills.slash_alias`, `user_skills.forked_from` |
| `docs/skill-authoring-guide.md` | Document `slash_alias` frontmatter field |

---

## Wave layout

Nine waves. Waves 1+2 are backend-only and unblock everything else. Waves 3-7 are frontend (with internal dependencies described below). Wave 8 is the live-run integration pass; Wave 9 is docs.

Indicative ordering (PLAN execution may parallelize within a wave):

| Wave | Title | Tasks | Depends on |
|---|---|---|---|
| 1 | Schema foundation | 1.1, 1.2 | — |
| 2 | Backend endpoints + tests | 2.1 – 2.7 | Wave 1 |
| 3 | Frontend foundation (shared components + API client) | 3.1 – 3.4 | Wave 2 (for API client shapes) |
| 4 | Wizard (Modes B + C) | 4.1 – 4.5 | Wave 3 |
| 5 | Capture from chat (Mode A) | 5.1 – 5.5 | Wave 3 |
| 6 | Detail tabs | 6.1 – 6.4 | Wave 3 |
| 7 | Slash invocation in composer | 7.1 – 7.3 | Wave 3 |
| 8 | Cypress E2E + live-run | 8.1 – 8.8 | Waves 4–7 |
| 9 | Documentation | 9.1 – 9.3 | All preceding |

Each task is self-contained: write failing test → run → implement → run → commit.

---

## Wave 1 — Schema foundation

### Task 1.1: Migration 0022 — `projects.is_sandbox`

**Files:**
- Create: `api/alembic/versions/0022_add_projects_is_sandbox.py`
- Modify: `api/app/models/project.py`
- Test: `api/tests/test_models_project_is_sandbox.py` (new)

- [ ] **Step 1: Write the failing model test**

```python
# api/tests/test_models_project_is_sandbox.py
from app.models.project import Project


def test_project_has_is_sandbox_default_false():
    p = Project(owner_id="00000000-0000-0000-0000-000000000000", name="x", slug="x")
    assert p.is_sandbox is False  # SQLAlchemy default
```

- [ ] **Step 2: Run test, expect FAIL**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_models_project_is_sandbox.py -v
```
Expected: `AttributeError: 'Project' object has no attribute 'is_sandbox'`.

- [ ] **Step 3: Add column to model**

In `api/app/models/project.py`, inside `class Project(Base):` near the other Mapped declarations:

```python
is_sandbox: Mapped[bool] = mapped_column(
    Boolean,
    nullable=False,
    server_default=text("false"),
    default=False,
)
```

(Add `Boolean` to the SQLAlchemy imports if not present.)

- [ ] **Step 4: Author the migration**

```python
# api/alembic/versions/0022_add_projects_is_sandbox.py
"""add projects.is_sandbox

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "is_sandbox",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Partial index keeps the default matters-list query fast.
    op.create_index(
        "idx_projects_not_sandbox",
        "projects",
        ["owner_id", "created_at"],
        postgresql_where=sa.text("is_sandbox = false AND archived_at IS NULL"),
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_projects_not_sandbox", table_name="projects")
    op.drop_column("projects", "is_sandbox")
```

- [ ] **Step 5: Apply the migration in the test DB and run the test**

```bash
docker cp api/alembic/versions/0022_add_projects_is_sandbox.py lq-ai-api-1:/app/alembic/versions/
docker exec -w /app lq-ai-api-1 alembic upgrade head
docker exec -w /app lq-ai-api-1 pytest tests/test_models_project_is_sandbox.py -v
```
Expected: 1 passed.

- [ ] **Step 6: Verify the index exists**

```bash
docker exec lq-ai-postgres-1 psql -U postgres -d lq_ai -c "\d projects" | grep -E 'is_sandbox|idx_projects_not_sandbox'
```
Expected: two lines — the column + the partial index.

- [ ] **Step 7: Commit**

```bash
git add api/alembic/versions/0022_add_projects_is_sandbox.py \
        api/app/models/project.py \
        api/tests/test_models_project_is_sandbox.py
git commit -s -m "feat(api): add projects.is_sandbox column (Wave D.2 / migration 0022)"
```

---

### Task 1.2: Migration 0023 — `user_skills.slash_alias` + `forked_from`

**Files:**
- Create: `api/alembic/versions/0023_add_user_skills_slash_alias_and_forked_from.py`
- Modify: `api/app/models/user_skill.py`
- Test: `api/tests/test_models_user_skill_new_columns.py` (new)

- [ ] **Step 1: Write the failing model test**

```python
# api/tests/test_models_user_skill_new_columns.py
from app.models.user_skill import UserSkill


def test_user_skill_has_slash_alias_and_forked_from_columns():
    us = UserSkill(scope="user", slug="x", body_md="x", title="x", description="x")
    assert hasattr(us, "slash_alias")
    assert hasattr(us, "forked_from")
    assert us.slash_alias is None
    assert us.forked_from is None
```

- [ ] **Step 2: Run test, expect FAIL**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_models_user_skill_new_columns.py -v
```
Expected: AttributeError on `slash_alias`.

- [ ] **Step 3: Add columns to model**

In `api/app/models/user_skill.py`, inside `class UserSkill(Base):`:

```python
slash_alias: Mapped[str | None] = mapped_column(Text, nullable=True)
"""Optional /slash invocation alias. Format `^/[a-z0-9-]{1,32}$`."""

forked_from: Mapped[str | None] = mapped_column(Text, nullable=True)
"""Documentary: slug of source skill if this skill was forked. No FK
since skills are filesystem-canonical for built-ins."""
```

- [ ] **Step 4: Author the migration**

```python
# api/alembic/versions/0023_add_user_skills_slash_alias_and_forked_from.py
"""add user_skills.slash_alias and user_skills.forked_from

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_skills", sa.Column("slash_alias", sa.Text(), nullable=True))
    op.add_column("user_skills", sa.Column("forked_from", sa.Text(), nullable=True))

    op.create_check_constraint(
        "chk_user_skills_slash_alias_format",
        "user_skills",
        "slash_alias IS NULL OR slash_alias ~ '^/[a-z0-9-]{1,32}$'",
    )

    # Unique per (owner_user_id, slash_alias) for active rows only.
    # Mirrors the existing slug-uniqueness partial-index pattern.
    op.create_index(
        "idx_user_skills_slash_alias_owner_active",
        "user_skills",
        ["owner_user_id", "slash_alias"],
        unique=True,
        postgresql_where=sa.text(
            "slash_alias IS NOT NULL AND archived_at IS NULL AND scope = 'user'"
        ),
    )

    # Team-scope analogue (one alias per team).
    op.create_index(
        "idx_user_skills_slash_alias_team_active",
        "user_skills",
        ["owner_team_id", "slash_alias"],
        unique=True,
        postgresql_where=sa.text(
            "slash_alias IS NOT NULL AND archived_at IS NULL AND scope = 'team'"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_user_skills_slash_alias_team_active", table_name="user_skills")
    op.drop_index("idx_user_skills_slash_alias_owner_active", table_name="user_skills")
    op.drop_constraint("chk_user_skills_slash_alias_format", "user_skills", type_="check")
    op.drop_column("user_skills", "forked_from")
    op.drop_column("user_skills", "slash_alias")
```

- [ ] **Step 5: Apply migration + run the test**

```bash
docker cp api/alembic/versions/0023_add_user_skills_slash_alias_and_forked_from.py lq-ai-api-1:/app/alembic/versions/
docker exec -w /app lq-ai-api-1 alembic upgrade head
docker exec -w /app lq-ai-api-1 pytest tests/test_models_user_skill_new_columns.py -v
```
Expected: 1 passed.

- [ ] **Step 6: Verify constraint + indexes**

```bash
docker exec lq-ai-postgres-1 psql -U postgres -d lq_ai -c "\d user_skills" \
  | grep -E 'slash_alias|forked_from|chk_user_skills_slash_alias_format'
```
Expected: 3 columns + 1 check + 2 partial unique indexes visible.

- [ ] **Step 7: Commit**

```bash
git add api/alembic/versions/0023_add_user_skills_slash_alias_and_forked_from.py \
        api/app/models/user_skill.py \
        api/tests/test_models_user_skill_new_columns.py
git commit -s -m "feat(api): add user_skills.slash_alias + forked_from (Wave D.2 / migration 0023)"
```

---

## Wave 2 — Backend endpoints + tests

### Task 2.1: Reserve `__*__` slug pattern on `POST /projects`

**Files:**
- Modify: `api/app/api/projects.py`
- Test: `api/tests/test_projects_sandbox_slug_reserved.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_projects_sandbox_slug_reserved.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_projects_rejects_double_underscore_slug(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/projects", json={
        "name": "Test", "slug": "__sandbox__", "description": "x",
    })
    assert r.status_code == 422
    assert "reserved" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_projects_rejects_any_double_underscore_pattern(authed_client: AsyncClient):
    for slug in ("__system__", "__internal__", "__foo__"):
        r = await authed_client.post("/api/v1/projects", json={
            "name": "Test", "slug": slug, "description": "x",
        })
        assert r.status_code == 422, f"slug {slug} should be reserved"
```

- [ ] **Step 2: Run test, expect FAIL (probably 201 created)**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_projects_sandbox_slug_reserved.py -v
```

- [ ] **Step 3: Implement reservation in the create handler**

In `api/app/api/projects.py`, in the `POST /projects` handler (find by `@router.post("")` or similar), after the existing slug-validity check:

```python
import re

_RESERVED_SLUG_RE = re.compile(r"^__[a-z0-9-]+__$")


def _check_slug_not_reserved(slug: str) -> None:
    if _RESERVED_SLUG_RE.match(slug):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Slug pattern '__*__' is reserved for system-managed matters; '{slug}' rejected.",
        )
```

Call `_check_slug_not_reserved(payload.slug)` at the top of the create handler. The same check is bypassed by the sandbox-ensure endpoint (Task 2.2) which constructs the slug internally.

- [ ] **Step 4: Run test, expect PASS**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_projects_sandbox_slug_reserved.py -v
```

- [ ] **Step 5: Commit**

```bash
git add api/app/api/projects.py api/tests/test_projects_sandbox_slug_reserved.py
git commit -s -m "feat(api): reserve __*__ slug pattern for system matters (Wave D.2)"
```

---

### Task 2.2: `POST /api/v1/projects/sandbox/ensure`

**Files:**
- Modify: `api/app/api/projects.py`
- Test: `api/tests/integration/test_projects_sandbox_ensure.py` (new)
- Test: `api/tests/integration/test_projects_sandbox_concurrency.py` (new)

- [ ] **Step 1: Write the idempotency integration test**

```python
# api/tests/integration/test_projects_sandbox_ensure.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sandbox_ensure_creates_then_idempotent(authed_client: AsyncClient):
    r1 = await authed_client.post("/api/v1/projects/sandbox/ensure")
    assert r1.status_code == 201
    p1 = r1.json()
    assert p1["is_sandbox"] is True
    assert p1["slug"] == "__sandbox__"
    assert p1["privileged"] is False
    assert p1["minimum_inference_tier"] is None

    r2 = await authed_client.post("/api/v1/projects/sandbox/ensure")
    assert r2.status_code == 200
    p2 = r2.json()
    assert p2["id"] == p1["id"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sandbox_ensure_recreates_after_archive(authed_client: AsyncClient):
    r1 = await authed_client.post("/api/v1/projects/sandbox/ensure")
    pid1 = r1.json()["id"]

    # archive via the standard delete endpoint
    await authed_client.delete(f"/api/v1/projects/{pid1}")

    r2 = await authed_client.post("/api/v1/projects/sandbox/ensure")
    assert r2.status_code == 201
    assert r2.json()["id"] != pid1
```

- [ ] **Step 2: Write the concurrency integration test**

```python
# api/tests/integration/test_projects_sandbox_concurrency.py
import asyncio
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sandbox_ensure_concurrent_returns_same_row(authed_client: AsyncClient):
    results = await asyncio.gather(
        authed_client.post("/api/v1/projects/sandbox/ensure"),
        authed_client.post("/api/v1/projects/sandbox/ensure"),
        authed_client.post("/api/v1/projects/sandbox/ensure"),
    )
    ids = {r.json()["id"] for r in results}
    assert len(ids) == 1, f"expected one sandbox row, got {ids}"
```

- [ ] **Step 3: Run tests, expect FAIL (404 on the route)**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/integration/test_projects_sandbox_ensure.py \
                                              tests/integration/test_projects_sandbox_concurrency.py -v -m integration
```

- [ ] **Step 4: Implement the endpoint**

Add to `api/app/api/projects.py`:

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert


@router.post(
    "/sandbox/ensure",
    response_model=ProjectResponse,
    summary="Find or create the caller's try-it sandbox matter (Wave D.2)",
)
async def ensure_sandbox(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> ProjectResponse:
    """Idempotent find-or-create of the per-user sandbox project."""
    # Look up an existing non-archived sandbox first (fast path).
    existing = await db.scalar(
        select(Project).where(
            Project.owner_id == user.id,
            Project.is_sandbox.is_(True),
            Project.archived_at.is_(None),
        )
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _project_to_response(existing, attached_skill_names=[])

    # Insert with ON CONFLICT DO NOTHING in case of concurrent ensures.
    # The unique-per-owner-active partial index on slug guarantees one
    # active sandbox per user.
    stmt = (
        pg_insert(Project)
        .values(
            owner_id=user.id,
            name="Try-it sandbox",
            slug="__sandbox__",
            description="Auto-created sandbox for skill try-it. Conversations here are non-billable.",
            privileged=False,
            minimum_inference_tier=None,
            is_sandbox=True,
        )
        .on_conflict_do_nothing(
            index_elements=["owner_id", "slug"],
            index_where=sa.text("archived_at IS NULL"),
        )
        .returning(Project)
    )
    row = await db.scalar(stmt)

    if row is None:
        # Another concurrent caller won the race; re-read.
        row = await db.scalar(
            select(Project).where(
                Project.owner_id == user.id,
                Project.is_sandbox.is_(True),
                Project.archived_at.is_(None),
            )
        )
        await db.commit()
        response.status_code = status.HTTP_200_OK
    else:
        await db.commit()
        response.status_code = status.HTTP_201_CREATED

    assert row is not None  # invariant: post-insert there's always a row
    return _project_to_response(row, attached_skill_names=[])
```

`ActiveUser` and `_project_to_response` should already exist in the module; if `_project_to_response` is not a current helper, factor the existing response-construction out into one. `import sqlalchemy as sa` if not already in scope.

- [ ] **Step 5: Run tests, expect PASS**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/integration/test_projects_sandbox_ensure.py \
                                              tests/integration/test_projects_sandbox_concurrency.py -v -m integration
```

- [ ] **Step 6: Commit**

```bash
git add api/app/api/projects.py \
        api/tests/integration/test_projects_sandbox_ensure.py \
        api/tests/integration/test_projects_sandbox_concurrency.py
git commit -s -m "feat(api): POST /projects/sandbox/ensure — idempotent sandbox matter (Wave D.2)"
```

---

### Task 2.3: `is_sandbox` query filters on `GET /projects`

**Files:**
- Modify: `api/app/api/projects.py`
- Test: extend `api/tests/integration/test_projects_sandbox_ensure.py`

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/integration/test_projects_sandbox_ensure.py`:

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_projects_excludes_sandbox_by_default(authed_client: AsyncClient):
    await authed_client.post("/api/v1/projects/sandbox/ensure")
    # create a regular project too
    await authed_client.post("/api/v1/projects", json={
        "name": "Acme NDA", "slug": "acme-nda", "description": ""
    })
    r = await authed_client.get("/api/v1/projects")
    assert r.status_code == 200
    slugs = {p["slug"] for p in r.json()["items"]}
    assert "acme-nda" in slugs
    assert "__sandbox__" not in slugs


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_projects_include_sandbox(authed_client: AsyncClient):
    await authed_client.post("/api/v1/projects/sandbox/ensure")
    r = await authed_client.get("/api/v1/projects?include_sandbox=true")
    assert r.status_code == 200
    slugs = {p["slug"] for p in r.json()["items"]}
    assert "__sandbox__" in slugs


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_projects_only_sandbox(authed_client: AsyncClient):
    await authed_client.post("/api/v1/projects/sandbox/ensure")
    r = await authed_client.get("/api/v1/projects?only_sandbox=true")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(p["is_sandbox"] for p in items)
```

- [ ] **Step 2: Run, expect FAIL**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/integration/test_projects_sandbox_ensure.py -v -m integration -k "list_projects"
```

- [ ] **Step 3: Implement the filters**

In `api/app/api/projects.py`, in the `GET /projects` handler signature, add:

```python
include_sandbox: Annotated[bool, Query(description="Include sandbox matters in results.")] = False,
only_sandbox: Annotated[bool, Query(description="Return only sandbox matters.")] = False,
```

In the query construction, replace the existing where-clause snippet on `Project.archived_at.is_(None)` with composed conditions:

```python
conditions: list[ColumnElement[bool]] = [
    Project.owner_id == user.id,
    Project.archived_at.is_(None),
]
if only_sandbox:
    conditions.append(Project.is_sandbox.is_(True))
elif not include_sandbox:
    conditions.append(Project.is_sandbox.is_(False))
# else: include both
stmt = select(Project).where(*conditions).order_by(Project.created_at.desc())
```

Also extend the project response shape to include `is_sandbox` (add `is_sandbox: bool` to `ProjectResponse` in `api/app/schemas/projects.py`).

- [ ] **Step 4: Run, expect PASS**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/integration/test_projects_sandbox_ensure.py -v -m integration
```

- [ ] **Step 5: Commit**

```bash
git add api/app/api/projects.py api/app/schemas/projects.py \
        api/tests/integration/test_projects_sandbox_ensure.py
git commit -s -m "feat(api): is_sandbox query filters on GET /projects (Wave D.2)"
```

---

### Task 2.4: `slash_alias` + `forked_from` + `source_message_id` on user-skills

**Files:**
- Modify: `api/app/api/user_skills.py`
- Test: `api/tests/test_user_skills_slash_alias.py` (new)
- Test: `api/tests/integration/test_user_skills_create_with_slash_alias.py` (new)
- Test: `api/tests/test_skills_capture_payload.py` (new)

- [ ] **Step 1: Write unit tests for regex**

```python
# api/tests/test_user_skills_slash_alias.py
import pytest
from pydantic import ValidationError

from app.api.user_skills import UserSkillCreate


def _base_payload(**overrides):
    payload = {
        "scope": "user", "slug": "x", "title": "X", "description": "x",
        "body_md": "x", "version": "1.0.0",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("alias", ["/foo", "/foo-bar", "/a", "/a1b-2c", "/" + "z" * 32])
def test_slash_alias_valid(alias):
    UserSkillCreate(**_base_payload(slash_alias=alias))


@pytest.mark.parametrize(
    "alias",
    ["foo", "/FOO", "/foo_bar", "/foo bar", "//foo", "/", "/" + "z" * 33, "/foo!"],
)
def test_slash_alias_invalid(alias):
    with pytest.raises(ValidationError):
        UserSkillCreate(**_base_payload(slash_alias=alias))


def test_slash_alias_none_accepted():
    m = UserSkillCreate(**_base_payload(slash_alias=None))
    assert m.slash_alias is None
```

- [ ] **Step 2: Write capture-payload unit tests**

```python
# api/tests/test_skills_capture_payload.py
from app.api.user_skills import UserSkillCreate, UserSkillUpdate


def test_source_message_id_optional():
    m = UserSkillCreate(
        scope="user", slug="x", title="X", description="x", body_md="x",
        version="1.0.0", source_message_id="msg_abc123",
    )
    assert m.source_message_id == "msg_abc123"


def test_forked_from_write_once_not_on_update():
    # PATCH model must not accept forked_from or source_message_id
    u = UserSkillUpdate.model_validate({"description": "new"})
    assert not hasattr(u, "forked_from") or u.forked_from is None
    # Confirm the field is excluded from the update schema
    assert "forked_from" not in UserSkillUpdate.model_fields
    assert "source_message_id" not in UserSkillUpdate.model_fields
```

- [ ] **Step 3: Write the collision integration test**

```python
# api/tests/integration/test_user_skills_create_with_slash_alias.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_with_slash_alias_roundtrip(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "test-skill", "title": "Test", "description": "x",
        "body_md": "x", "version": "1.0.0", "slash_alias": "/test",
    })
    assert r.status_code == 201
    pk = r.json()["id"]
    r2 = await authed_client.get(f"/api/v1/user-skills/{pk}")
    assert r2.json()["slash_alias"] == "/test"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_with_colliding_slash_alias_rejected(authed_client: AsyncClient):
    await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "a", "title": "A", "description": "x",
        "body_md": "x", "version": "1.0.0", "slash_alias": "/foo",
    })
    r = await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "b", "title": "B", "description": "x",
        "body_md": "x", "version": "1.0.0", "slash_alias": "/foo",
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "foo" in str(detail).lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_archive_frees_slash_alias(authed_client: AsyncClient):
    r1 = await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "a", "title": "A", "description": "x",
        "body_md": "x", "version": "1.0.0", "slash_alias": "/foo",
    })
    pk = r1.json()["id"]
    await authed_client.delete(f"/api/v1/user-skills/{pk}")  # archives
    r2 = await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "b", "title": "B", "description": "x",
        "body_md": "x", "version": "1.0.0", "slash_alias": "/foo",
    })
    assert r2.status_code == 201
```

- [ ] **Step 4: Run, expect FAIL**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_user_skills_slash_alias.py \
                                              tests/test_skills_capture_payload.py \
                                              tests/integration/test_user_skills_create_with_slash_alias.py -v
```

- [ ] **Step 5: Extend the Pydantic schemas**

In `api/app/api/user_skills.py`:

```python
from pydantic import Field, field_validator
import re

_SLASH_ALIAS_RE = re.compile(r"^/[a-z0-9-]{1,32}$")


class UserSkillCreate(BaseModel):
    # ... existing fields ...
    slash_alias: str | None = Field(default=None, description="Optional /slug invocation alias.")
    forked_from: str | None = Field(default=None, description="Source slug if forked.")
    source_message_id: str | None = Field(default=None, description="Capture: source AI message UUID.")

    @field_validator("slash_alias")
    @classmethod
    def _validate_slash_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _SLASH_ALIAS_RE.match(v):
            raise ValueError(
                "slash_alias must match ^/[a-z0-9-]{1,32}$ (lowercase, dash-separated, max 32 chars)"
            )
        return v


class UserSkillUpdate(BaseModel):
    # ... existing fields ...
    slash_alias: str | None = Field(default=None)
    # NOTE: forked_from and source_message_id are write-once on create.

    @field_validator("slash_alias")
    @classmethod
    def _validate_slash_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _SLASH_ALIAS_RE.match(v):
            raise ValueError(
                "slash_alias must match ^/[a-z0-9-]{1,32}$ (lowercase, dash-separated, max 32 chars)"
            )
        return v
```

In the create + patch handlers, persist `slash_alias`/`forked_from`/`source_message_id` to the `UserSkill` row. Wrap the create-INSERT in `try/except IntegrityError`: on unique-constraint failure for `slash_alias`, raise `HTTPException(422, detail=f"slash_alias '{slash_alias}' is already used by another of your skills.")`.

In `UserSkillResponse`, expose `slash_alias` and `forked_from` (not `source_message_id` — documentary only).

- [ ] **Step 6: Run, expect PASS**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_user_skills_slash_alias.py \
                                              tests/test_skills_capture_payload.py \
                                              tests/integration/test_user_skills_create_with_slash_alias.py -v
```

- [ ] **Step 7: Commit**

```bash
git add api/app/api/user_skills.py \
        api/tests/test_user_skills_slash_alias.py \
        api/tests/test_skills_capture_payload.py \
        api/tests/integration/test_user_skills_create_with_slash_alias.py
git commit -s -m "feat(api): slash_alias + forked_from + source_message_id on user-skills (Wave D.2)"
```

---

### Task 2.5: `GET /api/v1/skills/autocomplete`

**Files:**
- Modify: `api/app/api/skills.py`
- Test: `api/tests/test_skills_autocomplete_ranking.py` (new)
- Test: `api/tests/integration/test_skills_autocomplete_endpoint.py` (new)

- [ ] **Step 1: Write the ranking unit test**

```python
# api/tests/test_skills_autocomplete_ranking.py
from app.api.skills import _rank_autocomplete_match


def test_prefix_on_slash_alias_outranks_contains_on_title():
    rows = [
        {"slug": "x", "slash_alias": "/foo", "title": "Other"},
        {"slug": "y", "slash_alias": None,   "title": "About foo"},
    ]
    ranked = _rank_autocomplete_match("foo", rows)
    assert ranked[0]["slug"] == "x"


def test_prefix_on_slug_outranks_contains():
    rows = [
        {"slug": "nda-review", "slash_alias": None, "title": "NDA Review"},
        {"slug": "other",      "slash_alias": None, "title": "About nda matters"},
    ]
    ranked = _rank_autocomplete_match("nda", rows)
    assert ranked[0]["slug"] == "nda-review"
```

- [ ] **Step 2: Write the endpoint integration test**

```python
# api/tests/integration/test_skills_autocomplete_endpoint.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_autocomplete_empty_q_returns_recents(authed_client: AsyncClient):
    r = await authed_client.get("/api/v1/skills/autocomplete?q=")
    assert r.status_code == 200
    assert isinstance(r.json()["results"], list)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_autocomplete_filters_by_query(authed_client: AsyncClient):
    await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "nda-personal", "title": "NDA Personal",
        "description": "x", "body_md": "x", "version": "1.0.0",
        "slash_alias": "/nda-p",
    })
    r = await authed_client.get("/api/v1/skills/autocomplete?q=nda")
    slugs = [item["slug"] for item in r.json()["results"]]
    assert "nda-personal" in slugs


@pytest.mark.asyncio
@pytest.mark.integration
async def test_autocomplete_resolver_excludes_shadowed_builtin(authed_client: AsyncClient):
    # Create a user-skill with the same slug as a built-in (e.g., 'nda-review')
    await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "nda-review", "title": "My NDA",
        "description": "x", "body_md": "x", "version": "1.0.0",
    })
    r = await authed_client.get("/api/v1/skills/autocomplete?q=nda-review")
    matches = [it for it in r.json()["results"] if it["slug"] == "nda-review"]
    assert len(matches) == 1
    assert matches[0]["scope"] == "user"  # the user-scope row wins


@pytest.mark.asyncio
@pytest.mark.integration
async def test_autocomplete_limit_clamped(authed_client: AsyncClient):
    r = await authed_client.get("/api/v1/skills/autocomplete?limit=50")
    # Default max is 25
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 25
```

- [ ] **Step 3: Run, expect FAIL (404 on route)**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_skills_autocomplete_ranking.py \
                                              tests/integration/test_skills_autocomplete_endpoint.py -v
```

- [ ] **Step 4: Implement the endpoint**

In `api/app/api/skills.py`:

```python
class SkillAutocompleteItem(BaseModel):
    slug: str
    slash_alias: str | None
    title: str
    description: str
    scope: str  # 'user' | 'team' | 'builtin'
    icon: str | None = None


class SkillAutocompleteResponse(BaseModel):
    results: list[SkillAutocompleteItem]


def _rank_autocomplete_match(
    q: str, rows: list[dict]
) -> list[dict]:
    """Score: prefix on slash_alias = 3; prefix on slug = 2; contains in title = 1."""
    q_lower = q.lower()

    def score(r: dict) -> int:
        s = 0
        if r.get("slash_alias") and r["slash_alias"].lower().startswith("/" + q_lower):
            s = max(s, 3)
        if r["slug"].lower().startswith(q_lower):
            s = max(s, 2)
        if q_lower and q_lower in r["title"].lower():
            s = max(s, 1)
        return s

    return sorted(rows, key=score, reverse=True)


@router.get(
    "/autocomplete",
    response_model=SkillAutocompleteResponse,
    summary="Autocomplete skills by /alias / slug / title (Wave D.2)",
)
async def autocomplete_skills(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str, Query(description="Substring to match.")] = "",
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> SkillAutocompleteResponse:
    # Reuse the existing resolver merge — see _list_skills_merged or equivalent.
    # The resolver returns user-scope first, then team, then built-in,
    # with user/team shadowing built-in by slug.
    merged = await _list_merged_skills_for_user(db, user)

    if not q:
        # Empty q: top-N recent by user's chat attachments.
        recent_slugs = await _recent_attached_skill_slugs(db, user, limit=limit)
        recent_set = set(recent_slugs)
        ordered = [s for s in merged if s["slug"] in recent_set]
        if len(ordered) < limit:
            # Pad with alphabetical
            remaining = [s for s in merged if s["slug"] not in recent_set]
            ordered = ordered + sorted(remaining, key=lambda s: s["title"])
        return SkillAutocompleteResponse(
            results=[SkillAutocompleteItem(**s) for s in ordered[:limit]]
        )

    ranked = _rank_autocomplete_match(q, merged)
    # Drop zero-scored entries
    q_lower = q.lower()
    filtered = [
        s for s in ranked
        if (s.get("slash_alias") and s["slash_alias"].lower().startswith("/" + q_lower))
        or s["slug"].lower().startswith(q_lower)
        or q_lower in s["title"].lower()
    ]
    return SkillAutocompleteResponse(
        results=[SkillAutocompleteItem(**s) for s in filtered[:limit]]
    )
```

Stubs to wire:
- `_list_merged_skills_for_user(db, user)` — reuse existing merge logic from the `GET /skills` listing handler; refactor into a private helper if not already.
- `_recent_attached_skill_slugs(db, user, limit)` — query the recent messages/chats of `user` for their `attached_skill_names`, return distinct slugs ordered by most-recent first.

- [ ] **Step 5: Run, expect PASS**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_skills_autocomplete_ranking.py \
                                              tests/integration/test_skills_autocomplete_endpoint.py -v
```

- [ ] **Step 6: Commit**

```bash
git add api/app/api/skills.py \
        api/tests/test_skills_autocomplete_ranking.py \
        api/tests/integration/test_skills_autocomplete_endpoint.py
git commit -s -m "feat(api): GET /skills/autocomplete (Wave D.2 slash invocation)"
```

---

### Task 2.6: `GET /api/v1/user-skills/{id}/versions`

**Files:**
- Modify: `api/app/api/user_skills.py`
- Modify: `api/app/services/audit.py` (or wherever audit-write helpers live)
- Test: `api/tests/integration/test_user_skills_versions_endpoint.py` (new)

- [ ] **Step 1: Write the integration test**

```python
# api/tests/integration/test_user_skills_versions_endpoint.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_versions_lists_create_and_updates(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "t", "title": "T", "description": "d",
        "body_md": "b", "version": "1.0.0",
    })
    pk = r.json()["id"]
    await authed_client.patch(f"/api/v1/user-skills/{pk}", json={"description": "d2"})
    await authed_client.patch(f"/api/v1/user-skills/{pk}", json={"body_md": "b2"})

    v = await authed_client.get(f"/api/v1/user-skills/{pk}/versions")
    assert v.status_code == 200
    items = v.json()["items"]
    assert len(items) == 3
    actions = [i["action"] for i in items]
    assert actions[-1] == "user_skill.created"  # ordering: most recent first
    # i.e. items[0] is the most recent update.


@pytest.mark.asyncio
@pytest.mark.integration
async def test_versions_forbidden_for_non_owner(
    authed_client: AsyncClient, other_authed_client: AsyncClient
):
    r = await authed_client.post("/api/v1/user-skills", json={
        "scope": "user", "slug": "t", "title": "T", "description": "d",
        "body_md": "b", "version": "1.0.0",
    })
    pk = r.json()["id"]
    v = await other_authed_client.get(f"/api/v1/user-skills/{pk}/versions")
    assert v.status_code in (403, 404)
```

(`other_authed_client` may need to be added to `conftest.py` — a second authenticated test client. If the existing fixtures don't support that, mirror however `authed_client` is built and parameterize the user.)

- [ ] **Step 2: Run, expect FAIL**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/integration/test_user_skills_versions_endpoint.py -v
```

- [ ] **Step 3: Ensure audit writes exist for user-skill changes**

In the user-skills create/update/archive handlers (or in a shared audit helper they call), add audit-log writes:

```python
async def _write_user_skill_audit(
    db: AsyncSession, *, action: str, user_id: uuid.UUID,
    skill_id: uuid.UUID, details: dict[str, Any],
) -> None:
    db.add(AuditLog(
        user_id=user_id,
        action=action,            # 'user_skill.created' | 'user_skill.updated' | 'user_skill.archived'
        resource_type="user_skill",
        resource_id=str(skill_id),
        privilege_marked=False,
        details=details,
    ))
```

Call sites:
- Create: `_write_user_skill_audit(db, action="user_skill.created", user_id=user.id, skill_id=row.id, details={"version": row.version, "forked_from": row.forked_from})`
- Update: include `changed_fields: list[str]` in `details`.
- Archive: `action="user_skill.archived"`.

- [ ] **Step 4: Implement the endpoint**

```python
class UserSkillVersionItem(BaseModel):
    timestamp: datetime
    actor_user_id: str | None
    actor_email: str | None
    action: str
    version: str | None
    details: dict[str, Any] | None


class UserSkillVersionsResponse(BaseModel):
    items: list[UserSkillVersionItem]


@router.get(
    "/{skill_id}/versions",
    response_model=UserSkillVersionsResponse,
    summary="Audit-log view of edits for this user-skill (Wave D.2)",
)
async def list_user_skill_versions(
    skill_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> UserSkillVersionsResponse:
    # AuthZ: caller must own (user-scope) or be a member of the team (team-scope).
    skill = await db.scalar(select(UserSkill).where(UserSkill.id == skill_id))
    if skill is None:
        raise HTTPException(404, "Skill not found")
    await _check_skill_read_access(db, skill, user)  # raises 403 if not allowed

    rows = (await db.scalars(
        select(AuditLog, User.email)
        .outerjoin(User, AuditLog.user_id == User.id)
        .where(
            AuditLog.resource_type == "user_skill",
            AuditLog.resource_id == str(skill_id),
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )).all()

    items = [
        UserSkillVersionItem(
            timestamp=r.AuditLog.timestamp,
            actor_user_id=str(r.AuditLog.user_id) if r.AuditLog.user_id else None,
            actor_email=r.email,
            action=r.AuditLog.action,
            version=(r.AuditLog.details or {}).get("version"),
            details=r.AuditLog.details,
        )
        for r in rows
    ]
    return UserSkillVersionsResponse(items=items)
```

`_check_skill_read_access` should encapsulate the user-scope owner check + team-scope membership check that the existing skill-read endpoint already does.

- [ ] **Step 5: Run, expect PASS**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/integration/test_user_skills_versions_endpoint.py -v
```

- [ ] **Step 6: Commit**

```bash
git add api/app/api/user_skills.py \
        api/app/services/audit.py \
        api/tests/integration/test_user_skills_versions_endpoint.py
git commit -s -m "feat(api): GET /user-skills/{id}/versions — audit-log view (Wave D.2)"
```

---

### Task 2.7: OpenAPI schema-conformance test + send-time slash-fallback

**Files:**
- Modify: `api/app/api/messages.py` or `api/app/api/chats.py` (wherever send-message lives)
- Test: `api/tests/integration/test_skills_send_with_slash_unresolved.py` (new)
- Test: `api/tests/test_openapi_wave_d2.py` (new)

- [ ] **Step 1: Write the slash-fallback integration test**

```python
# api/tests/integration/test_skills_send_with_slash_unresolved.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_send_with_leading_unresolved_slash_sends_as_plain_text(
    authed_client: AsyncClient,
):
    chat_id = (await authed_client.post("/api/v1/chats", json={"title": "x"})).json()["id"]
    r = await authed_client.post(f"/api/v1/chats/{chat_id}/messages", json={
        "content": "/nonexistent-skill review this",
    })
    assert r.status_code == 200
    body = r.json()
    # Backend records slash_unresolved=true on the message provenance
    assert body.get("slash_unresolved") is True
    # The skill is NOT attached
    assert body.get("attached_skill_names", []) == []
```

- [ ] **Step 2: Write the OpenAPI conformance test**

```python
# api/tests/test_openapi_wave_d2.py
from app.main import app


def test_openapi_includes_new_endpoints():
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/skills/autocomplete" in paths
    assert "/api/v1/projects/sandbox/ensure" in paths
    assert "/api/v1/user-skills/{skill_id}/versions" in paths


def test_user_skills_create_accepts_slash_alias():
    schema = app.openapi()
    body = schema["paths"]["/api/v1/user-skills"]["post"]["requestBody"]
    ref = body["content"]["application/json"]["schema"]["$ref"]
    cls = ref.rsplit("/", 1)[-1]
    props = schema["components"]["schemas"][cls]["properties"]
    assert "slash_alias" in props
    assert "forked_from" in props
    assert "source_message_id" in props


def test_projects_list_accepts_sandbox_filters():
    schema = app.openapi()
    params = schema["paths"]["/api/v1/projects"]["get"]["parameters"]
    names = {p["name"] for p in params}
    assert "include_sandbox" in names
    assert "only_sandbox" in names
```

- [ ] **Step 3: Run both, expect FAIL**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/integration/test_skills_send_with_slash_unresolved.py \
                                              tests/test_openapi_wave_d2.py -v
```

- [ ] **Step 4: Implement send-time slash fallback**

In the send-message handler, before constructing the LLM call:

```python
import re

_LEADING_SLASH_RE = re.compile(r"^/([a-z0-9-]{1,64})\s")


async def _maybe_resolve_leading_slash(
    db: AsyncSession, user: User, content: str
) -> tuple[str | None, str]:
    """If content starts with '/slug ', try to resolve to a skill.

    Returns (resolved_slug_or_None, content_with_slash_stripped_if_resolved).
    On no match: returns (None, original_content).
    """
    m = _LEADING_SLASH_RE.match(content)
    if not m:
        return None, content
    slug_or_alias = m.group(1)
    # Try slug first, then slash_alias.
    skill = await _resolve_skill_for_user(db, user, slug=slug_or_alias)
    if skill is None:
        skill = await _resolve_skill_for_user(db, user, slash_alias="/" + slug_or_alias)
    if skill is None:
        return None, content
    return skill["slug"], content[m.end():]
```

In the send handler, if no `attached_skill_names` were supplied by the frontend AND the body starts with a slash, attempt resolution. Set `slash_unresolved=True` on the response if a slash was detected but didn't resolve.

- [ ] **Step 5: Run, expect PASS**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/integration/test_skills_send_with_slash_unresolved.py \
                                              tests/test_openapi_wave_d2.py -v
```

- [ ] **Step 6: Full backend test run**

```bash
docker exec -w /app lq-ai-api-1 pytest -v --tb=short
```
Expected: all tests pass; integration tests gated behind `-m integration` if not on by default.

- [ ] **Step 7: Commit**

```bash
git add api/app/api/messages.py \
        api/tests/integration/test_skills_send_with_slash_unresolved.py \
        api/tests/test_openapi_wave_d2.py
git commit -s -m "feat(api): send-time slash fallback + OpenAPI conformance (Wave D.2)"
```


---

## Wave 3 — Frontend foundation (shared components + API clients)

### Task 3.1: Extend API clients

**Files:**
- Modify: `web/src/lib/lq-ai/api/skills.ts`
- Modify: `web/src/lib/lq-ai/api/projects.ts`
- Modify: `web/src/lib/lq-ai/api/userSkills.ts`
- Modify: `web/src/lib/lq-ai/types.ts` (add types)
- Test: `web/src/lib/lq-ai/__tests__/skills-autocomplete-api.test.ts` (new)
- Test: `web/src/lib/lq-ai/__tests__/projects-sandbox-api.test.ts` (new)

- [ ] **Step 1: Add response types**

Append to `web/src/lib/lq-ai/types.ts`:

```ts
export interface SkillAutocompleteItem {
  slug: string;
  slash_alias: string | null;
  title: string;
  description: string;
  scope: 'user' | 'team' | 'builtin';
  icon: string | null;
}

export interface SkillAutocompleteResponse {
  results: SkillAutocompleteItem[];
}

export interface UserSkillVersion {
  timestamp: string;
  actor_user_id: string | null;
  actor_email: string | null;
  action: string;
  version: string | null;
  details: Record<string, unknown> | null;
}

export interface UserSkillVersionsResponse {
  items: UserSkillVersion[];
}
```

Also extend `Project` type to include `is_sandbox: boolean`, and `UserSkill` / `Skill` types to include `slash_alias: string | null` and `forked_from: string | null`.

- [ ] **Step 2: Write the API client tests**

```ts
// web/src/lib/lq-ai/__tests__/skills-autocomplete-api.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { skillsApi } from '../api/skills';

describe('skillsApi.autocomplete', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('calls GET /skills/autocomplete with q + limit', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ results: [] }), { status: 200 })
    );
    await skillsApi.autocomplete('nda', 5);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/skills/autocomplete?q=nda&limit=5'),
      expect.any(Object),
    );
  });
});
```

```ts
// web/src/lib/lq-ai/__tests__/projects-sandbox-api.test.ts
import { describe, it, expect, vi } from 'vitest';
import { projectsApi } from '../api/projects';

describe('projectsApi.ensureSandbox', () => {
  it('POSTs to /projects/sandbox/ensure with no body', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 'x', is_sandbox: true }), { status: 200 })
    );
    await projectsApi.ensureSandbox();
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/projects/sandbox/ensure'),
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
```

- [ ] **Step 3: Run tests, expect FAIL**

```bash
cd web && npm run test:frontend -- --run __tests__/skills-autocomplete-api __tests__/projects-sandbox-api
```

- [ ] **Step 4: Implement client methods**

In `web/src/lib/lq-ai/api/skills.ts`, add to the `skillsApi` object:

```ts
async autocomplete(q: string, limit: number = 10): Promise<SkillAutocompleteResponse> {
  const url = `${API_BASE}/skills/autocomplete?q=${encodeURIComponent(q)}&limit=${limit}`;
  return apiClient.get<SkillAutocompleteResponse>(url);
},
```

In `web/src/lib/lq-ai/api/projects.ts`:

```ts
async ensureSandbox(): Promise<Project> {
  return apiClient.post<Project>(`${API_BASE}/projects/sandbox/ensure`, {});
},

async listProjects(opts: { includeSandbox?: boolean; onlySandbox?: boolean } = {}): Promise<{ items: Project[] }> {
  const params = new URLSearchParams();
  if (opts.includeSandbox) params.set('include_sandbox', 'true');
  if (opts.onlySandbox) params.set('only_sandbox', 'true');
  const qs = params.toString();
  return apiClient.get(`${API_BASE}/projects${qs ? '?' + qs : ''}`);
},
```

In `web/src/lib/lq-ai/api/userSkills.ts`:

```ts
async listVersions(skillId: string, limit: number = 50): Promise<UserSkillVersionsResponse> {
  return apiClient.get<UserSkillVersionsResponse>(
    `${API_BASE}/user-skills/${skillId}/versions?limit=${limit}`,
  );
},
```

(Use whatever `apiClient` / `API_BASE` conventions the existing methods in those files already use — match them exactly.)

- [ ] **Step 5: Run tests, expect PASS**

```bash
cd web && npm run test:frontend -- --run __tests__/skills-autocomplete-api __tests__/projects-sandbox-api
```

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/lq-ai/api/skills.ts \
        web/src/lib/lq-ai/api/projects.ts \
        web/src/lib/lq-ai/api/userSkills.ts \
        web/src/lib/lq-ai/types.ts \
        web/src/lib/lq-ai/__tests__/skills-autocomplete-api.test.ts \
        web/src/lib/lq-ai/__tests__/projects-sandbox-api.test.ts
git commit -s -m "feat(web): extend API clients for autocomplete + sandbox + versions (Wave D.2)"
```

---

### Task 3.2: `AttachedSkillPill` component

**Files:**
- Create: `web/src/lib/lq-ai/components/AttachedSkillPill.svelte`
- Create: `web/src/lib/lq-ai/__tests__/AttachedSkillPill.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/lq-ai/__tests__/AttachedSkillPill.test.ts
import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import AttachedSkillPill from '../components/AttachedSkillPill.svelte';

describe('AttachedSkillPill', () => {
  it('renders skill title + remove button', () => {
    render(AttachedSkillPill, {
      props: { skill: { slug: 'nda-review', title: 'NDA Review' }, onRemove: () => {} },
    });
    expect(screen.getByText('NDA Review')).toBeTruthy();
    expect(screen.getByLabelText(/remove nda review/i)).toBeTruthy();
  });

  it('calls onRemove when × clicked', async () => {
    const onRemove = vi.fn();
    render(AttachedSkillPill, {
      props: { skill: { slug: 'nda-review', title: 'NDA Review' }, onRemove },
    });
    await fireEvent.click(screen.getByLabelText(/remove nda review/i));
    expect(onRemove).toHaveBeenCalledWith('nda-review');
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd web && npm run test:frontend -- --run AttachedSkillPill
```

- [ ] **Step 3: Implement the component**

```svelte
<!-- web/src/lib/lq-ai/components/AttachedSkillPill.svelte -->
<script lang="ts">
  interface Skill { slug: string; title: string; icon?: string | null; }
  export let skill: Skill;
  export let onRemove: (slug: string) => void;
</script>

<span class="lq-skill-pill" role="status">
  <span class="icon">{skill.icon ?? '📜'}</span>
  <span class="title">{skill.title}</span>
  <button
    type="button"
    class="remove"
    aria-label={`Remove ${skill.title}`}
    on:click={() => onRemove(skill.slug)}
  >×</button>
</span>

<style>
  .lq-skill-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--lq-secure-tint, #ecfdf5);
    color: var(--lq-secure-deep, #065f46);
    border: 1px solid var(--lq-secure, #6ee7b7);
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 500;
    font-family: var(--lq-font-sans);
  }
  .remove { background: none; border: 0; cursor: pointer; opacity: 0.6; }
  .remove:hover { opacity: 1; }
</style>
```

- [ ] **Step 4: Run, expect PASS**

```bash
cd web && npm run test:frontend -- --run AttachedSkillPill
```

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/AttachedSkillPill.svelte \
        web/src/lib/lq-ai/__tests__/AttachedSkillPill.test.ts
git commit -s -m "feat(web): AttachedSkillPill component (Wave D.2)"
```

---

### Task 3.3: `SlashPopover` component

**Files:**
- Create: `web/src/lib/lq-ai/components/SlashPopover.svelte`
- Create: `web/src/lib/lq-ai/__tests__/SlashPopover.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/lib/lq-ai/__tests__/SlashPopover.test.ts
import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SlashPopover from '../components/SlashPopover.svelte';
import { skillsApi } from '../api/skills';

beforeEach(() => {
  vi.spyOn(skillsApi, 'autocomplete').mockResolvedValue({
    results: [
      { slug: 'nda-review', slash_alias: '/nda', title: 'NDA Review',
        description: 'd', scope: 'builtin', icon: null },
      { slug: 'nda-drafting', slash_alias: null, title: 'NDA Drafting',
        description: 'd', scope: 'user', icon: null },
    ],
  });
});

describe('SlashPopover', () => {
  it('fetches results on mount with empty q', async () => {
    render(SlashPopover, { props: { query: '', onSelect: () => {}, onDismiss: () => {} } });
    expect(skillsApi.autocomplete).toHaveBeenCalledWith('', 10);
  });

  it('renders results from autocomplete', async () => {
    render(SlashPopover, { props: { query: 'nda', onSelect: () => {}, onDismiss: () => {} } });
    await new Promise((r) => setTimeout(r, 10));
    expect(screen.getByText('NDA Review')).toBeTruthy();
  });

  it('Enter on focused row calls onSelect', async () => {
    const onSelect = vi.fn();
    const { container } = render(SlashPopover, {
      props: { query: 'nda', onSelect, onDismiss: () => {} },
    });
    await new Promise((r) => setTimeout(r, 10));
    await fireEvent.keyDown(container, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ slug: 'nda-review' })
    );
  });

  it('Esc calls onDismiss', async () => {
    const onDismiss = vi.fn();
    const { container } = render(SlashPopover, {
      props: { query: '', onSelect: () => {}, onDismiss },
    });
    await fireEvent.keyDown(container, { key: 'Escape' });
    expect(onDismiss).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd web && npm run test:frontend -- --run SlashPopover
```

- [ ] **Step 3: Implement the component**

```svelte
<!-- web/src/lib/lq-ai/components/SlashPopover.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { skillsApi } from '$lib/lq-ai/api/skills';
  import type { SkillAutocompleteItem } from '$lib/lq-ai/types';

  export let query: string;
  export let onSelect: (skill: SkillAutocompleteItem) => void;
  export let onDismiss: () => void;

  let results: SkillAutocompleteItem[] = [];
  let activeIndex = 0;
  let loading = false;
  let error: string | null = null;

  async function fetchResults(q: string) {
    loading = true;
    error = null;
    try {
      const r = await skillsApi.autocomplete(q, 10);
      results = r.results;
      activeIndex = 0;
    } catch (e) {
      error = "Couldn't load suggestions";
      results = [];
    } finally {
      loading = false;
    }
  }

  onMount(() => fetchResults(query));

  $: if (query !== undefined) fetchResults(query);

  function handleKey(e: KeyboardEvent) {
    if (results.length === 0) {
      if (e.key === 'Escape') onDismiss();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % results.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + results.length) % results.length;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      onSelect(results[activeIndex]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onDismiss();
    }
  }
</script>

<svelte:window on:keydown={handleKey} />

<div class="lq-slash-popover" role="listbox">
  {#if loading}
    <div class="empty">Loading…</div>
  {:else if error}
    <div class="empty">{error} · <button on:click={() => fetchResults(query)}>retry</button></div>
  {:else if results.length === 0}
    <div class="empty">
      {query
        ? `No matching skills · Esc to dismiss`
        : `You don't have any skills yet — `}
      {#if !query}
        <a href="/lq-ai/skills">Browse</a> · <a href="/lq-ai/skills/new">Create</a>
      {/if}
    </div>
  {:else}
    {#each results as r, i (r.slug)}
      <button
        type="button"
        class="row"
        class:active={i === activeIndex}
        on:mousedown|preventDefault={() => onSelect(r)}
        on:mouseenter={() => (activeIndex = i)}
        role="option"
        aria-selected={i === activeIndex}
      >
        <span class="icon">{r.icon ?? '📜'}</span>
        <span class="body">
          <span class="title">{r.title}</span>
          <span class="desc">{r.description}</span>
        </span>
      </button>
    {/each}
  {/if}
</div>

<style>
  .lq-slash-popover {
    background: var(--lq-surface);
    border: 1px solid var(--lq-border);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    padding: 4px;
    min-width: 280px;
    max-height: 280px;
    overflow-y: auto;
  }
  .row {
    display: flex; align-items: center; gap: 8px;
    width: 100%; padding: 6px 8px;
    background: transparent; border: 0; cursor: pointer; text-align: left;
    border-radius: 4px;
  }
  .row.active { background: var(--lq-secure-tint, #ecfdf5); }
  .title { font-weight: 600; display: block; }
  .desc { color: var(--lq-text-tertiary); font-size: 11px; display: block; }
  .empty { padding: 12px; color: var(--lq-text-tertiary); font-size: 13px; }
</style>
```

- [ ] **Step 4: Run, expect PASS**

```bash
cd web && npm run test:frontend -- --run SlashPopover
```

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/SlashPopover.svelte \
        web/src/lib/lq-ai/__tests__/SlashPopover.test.ts
git commit -s -m "feat(web): SlashPopover component (Wave D.2)"
```

---

### Task 3.4: `SkillTryItPane` component (shared sandbox embed)

**Files:**
- Create: `web/src/lib/lq-ai/components/SkillTryItPane.svelte`

- [ ] **Step 1: Implement the component**

This is a wrapper around a minimal chat view configured against the user's sandbox matter. It accepts either a saved-skill slug OR a draft body (for wizard try-it). It calls `ensureSandbox()` on mount, creates a chat in that sandbox project, and renders the existing message list + a small composer.

```svelte
<!-- web/src/lib/lq-ai/components/SkillTryItPane.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { projectsApi } from '$lib/lq-ai/api/projects';
  import { chatsApi } from '$lib/lq-ai/api/chats';
  import { messagesApi } from '$lib/lq-ai/api/messages';
  import type { Project, ChatMessage } from '$lib/lq-ai/types';

  /** EITHER skillSlug (saved skill) OR draftBody+draftSlug (wizard draft). */
  export let skillSlug: string | null = null;
  export let draftBody: string | null = null;
  export let draftSlug: string | null = null;
  export let source: 'tryit-tab' | 'wizard-tryout';

  let sandbox: Project | null = null;
  let chatId: string | null = null;
  let messages: ChatMessage[] = [];
  let composerText = '';
  let sending = false;
  let error: string | null = null;

  onMount(async () => {
    try {
      sandbox = await projectsApi.ensureSandbox();
      const chat = await chatsApi.createChat({
        title: `Try-it · ${skillSlug ?? draftSlug ?? 'draft'}`,
        project_id: sandbox.id,
      });
      chatId = chat.id;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to set up sandbox';
    }
  });

  async function send() {
    if (!chatId || !composerText.trim() || sending) return;
    sending = true;
    try {
      const body = {
        content: composerText,
        attached_skills: skillSlug
          ? [{ slug: skillSlug, source }]
          : [{ inline_body: draftBody!, slug: draftSlug ?? 'draft', source }],
      };
      const reply = await messagesApi.send(chatId, body);
      // optimistic insert + reply append
      messages = [...messages, reply.user_message, reply.assistant_message];
      composerText = '';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Send failed';
    } finally {
      sending = false;
    }
  }

  function reset() {
    if (!chatId) return;
    messages = [];
    // Note: server-side chat reset is out of scope at M1; we just clear the
    // local view. Subsequent send creates messages in the same chat.
  }
</script>

<div class="lq-tryit-pane">
  {#if error}
    <div class="error">{error}</div>
  {:else if !sandbox || !chatId}
    <div class="loading">Setting up sandbox…</div>
  {:else}
    <div class="header">
      <span class="badge">non-billable</span>
      <span class="badge">sandbox</span>
      <button class="reset" on:click={reset}>Reset</button>
    </div>
    <div class="messages">
      {#each messages as m (m.id)}
        <div class="msg msg-{m.role}">
          <strong>{m.role === 'user' ? 'You' : 'AI'}:</strong>
          <span style="white-space: pre-wrap;">{m.content}</span>
        </div>
      {/each}
    </div>
    <div class="composer">
      <textarea
        bind:value={composerText}
        placeholder="Try a prompt that would use this skill…"
        rows="3"
        disabled={sending}
      />
      <button class="send" on:click={send} disabled={!composerText.trim() || sending}>
        {sending ? 'Sending…' : 'Send'}
      </button>
    </div>
  {/if}
</div>

<style>
  .lq-tryit-pane { display: flex; flex-direction: column; min-height: 400px; gap: 12px; }
  .header { display: flex; gap: 8px; align-items: center; }
  .badge {
    background: var(--lq-surface-tinted); border: 1px solid var(--lq-border);
    padding: 2px 8px; border-radius: 999px; font-size: 11px;
    color: var(--lq-text-secondary);
  }
  .reset { margin-left: auto; }
  .messages { flex: 1; overflow-y: auto; padding: 8px; border: 1px solid var(--lq-border); border-radius: 6px; }
  .msg { margin-bottom: 8px; }
  .composer { display: flex; gap: 8px; }
  textarea { flex: 1; padding: 8px; border: 1px solid var(--lq-border); border-radius: 6px; }
  .send { padding: 0 16px; background: var(--lq-accent); color: white; border-radius: 6px; border: 0; }
</style>
```

- [ ] **Step 2: Verify build**

```bash
cd web && npm run check
```
Expected: no new type errors in this component (svelte-check baseline has ~9.3k pre-existing legacy errors per CLAUDE.md — measure only delta).

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/lq-ai/components/SkillTryItPane.svelte
git commit -s -m "feat(web): SkillTryItPane shared component (Wave D.2)"
```


---

## Wave 4 — Wizard (Modes B + C)

### Task 4.1: `SkillWizardSection` slot wrapper

**Files:**
- Create: `web/src/lib/lq-ai/components/SkillWizardSection.svelte`

- [ ] **Step 1: Implement**

```svelte
<!-- web/src/lib/lq-ai/components/SkillWizardSection.svelte -->
<script lang="ts">
  export let index: number;
  export let title: string;
  export let hint: string = '';
</script>

<section class="lq-wiz-section">
  <header>
    <span class="num">{index}</span>
    <h3>{title}</h3>
  </header>
  {#if hint}
    <p class="hint">{hint}</p>
  {/if}
  <div class="body">
    <slot />
  </div>
</section>

<style>
  .lq-wiz-section {
    border-bottom: 1px solid var(--lq-border);
    padding: 24px 0;
  }
  header { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
  .num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 50%;
    background: var(--lq-accent-tint, #ecfdf5); color: var(--lq-accent);
    font-weight: 600; font-size: 13px;
  }
  h3 { margin: 0; font-size: 18px; font-weight: 600; }
  .hint { color: var(--lq-text-tertiary); font-size: 13px; margin: 0 0 12px 0; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/lq-ai/components/SkillWizardSection.svelte
git commit -s -m "feat(web): SkillWizardSection slot wrapper (Wave D.2)"
```

---

### Task 4.2: `SkillWizard` component

**Files:**
- Create: `web/src/lib/lq-ai/components/SkillWizard.svelte`
- Create: `web/src/lib/lq-ai/__tests__/SkillWizard.test.ts`

- [ ] **Step 1: Write the unit tests**

```ts
// web/src/lib/lq-ai/__tests__/SkillWizard.test.ts
import { render, fireEvent, screen } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SkillWizard from '../components/SkillWizard.svelte';

beforeEach(() => {
  localStorage.clear();
});

describe('SkillWizard', () => {
  it('auto-derives slug from display_name', async () => {
    render(SkillWizard, { props: { initial: {}, onSave: () => Promise.resolve('id-1') } });
    const nameInput = screen.getByLabelText(/display name/i) as HTMLInputElement;
    await fireEvent.input(nameInput, { target: { value: 'NDA Review' } });
    const slugInput = screen.getByLabelText(/slug/i) as HTMLInputElement;
    expect(slugInput.value).toBe('nda-review');
  });

  it('rejects invalid slash_alias on blur', async () => {
    render(SkillWizard, { props: { initial: {}, onSave: () => Promise.resolve('id-1') } });
    const aliasInput = screen.getByLabelText(/slash alias/i) as HTMLInputElement;
    await fireEvent.input(aliasInput, { target: { value: 'foo bar' } });
    await fireEvent.blur(aliasInput);
    expect(screen.queryByText(/must start with/i)).toBeTruthy();
  });

  it('Save button is disabled until required fields filled', async () => {
    render(SkillWizard, { props: { initial: {}, onSave: () => Promise.resolve('id-1') } });
    const save = screen.getByRole('button', { name: /^save$/i });
    expect((save as HTMLButtonElement).disabled).toBe(true);
  });

  it('autosaves draft to localStorage on field change', async () => {
    render(SkillWizard, {
      props: { initial: {}, draftKey: 'k1', onSave: () => Promise.resolve('id-1') },
    });
    const nameInput = screen.getByLabelText(/display name/i) as HTMLInputElement;
    await fireEvent.input(nameInput, { target: { value: 'My Skill' } });
    await new Promise((r) => setTimeout(r, 350)); // debounce
    const stored = JSON.parse(localStorage.getItem('lq-ai:wizard-draft:k1') ?? '{}');
    expect(stored.displayName).toBe('My Skill');
  });

  it('restores draft from localStorage on mount', async () => {
    localStorage.setItem('lq-ai:wizard-draft:k1', JSON.stringify({
      displayName: 'Restored', slug: 'restored', description: 'd', body: 'b',
    }));
    render(SkillWizard, { props: { initial: {}, draftKey: 'k1', onSave: () => Promise.resolve('id-1') } });
    const nameInput = screen.getByLabelText(/display name/i) as HTMLInputElement;
    expect(nameInput.value).toBe('Restored');
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd web && npm run test:frontend -- --run SkillWizard
```

- [ ] **Step 3: Implement `SkillWizard`**

```svelte
<!-- web/src/lib/lq-ai/components/SkillWizard.svelte -->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import SkillWizardSection from './SkillWizardSection.svelte';
  import SkillTryItPane from './SkillTryItPane.svelte';

  export let initial: {
    slug?: string; displayName?: string; description?: string; body?: string;
    tags?: string[]; slashAlias?: string | null; jurisdiction?: string;
    version?: string; scope?: 'user' | 'team'; ownerTeamId?: string;
    forkedFrom?: string | null;
  } = {};
  export let draftKey: string | null = null;     // when set: enable localStorage autosave
  export let onSave: (payload: any) => Promise<string>;  // returns new skill id (slug)
  export let onDiscard: () => void = () => {};

  // Form state
  let slug = initial.slug ?? '';
  let displayName = initial.displayName ?? '';
  let description = initial.description ?? '';
  let body = initial.body ?? '';
  let tagsInput = (initial.tags ?? []).join(', ');
  let slashAlias = initial.slashAlias ?? '';
  let jurisdiction = initial.jurisdiction ?? '';
  let version = initial.version ?? '1.0.0';
  let scope: 'user' | 'team' = initial.scope ?? 'user';
  let ownerTeamId = initial.ownerTeamId ?? '';
  const forkedFrom = initial.forkedFrom ?? null;

  let slugTouched = false;
  let slashAliasError: string | null = null;
  let advancedOpen = false;
  let saving = false;
  let saveError: string | null = null;

  const SLUG_RE = /^[a-z0-9]([a-z0-9-]{0,78}[a-z0-9])?$/;
  const SLASH_RE = /^\/[a-z0-9-]{1,32}$/;

  function kebab(s: string): string {
    return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);
  }

  $: if (!slugTouched && displayName) slug = kebab(displayName);
  $: slugValid = SLUG_RE.test(slug);
  $: slashAliasValid = !slashAlias || SLASH_RE.test(slashAlias);
  $: canSave =
    !saving && slug && slugValid && displayName.trim() && description.trim() &&
    body.trim() && slashAliasValid && (scope !== 'team' || ownerTeamId);

  function validateSlashAlias() {
    slashAliasError = slashAlias && !SLASH_RE.test(slashAlias)
      ? 'Slash alias must start with / and use lowercase letters, digits, and dashes (max 32 chars).'
      : null;
  }

  // localStorage autosave
  let saveTimer: number | null = null;
  function scheduleAutosave() {
    if (!draftKey) return;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => {
      localStorage.setItem(`lq-ai:wizard-draft:${draftKey}`, JSON.stringify({
        slug, displayName, description, body, tagsInput, slashAlias,
        jurisdiction, version, scope, ownerTeamId,
      }));
    }, 300);
  }
  $: { slug; displayName; description; body; tagsInput; slashAlias;
       jurisdiction; version; scope; ownerTeamId; scheduleAutosave(); }

  onMount(() => {
    if (!draftKey) return;
    const raw = localStorage.getItem(`lq-ai:wizard-draft:${draftKey}`);
    if (!raw) return;
    try {
      const d = JSON.parse(raw);
      slug = d.slug ?? slug;
      displayName = d.displayName ?? displayName;
      description = d.description ?? description;
      body = d.body ?? body;
      tagsInput = d.tagsInput ?? tagsInput;
      slashAlias = d.slashAlias ?? slashAlias;
      jurisdiction = d.jurisdiction ?? jurisdiction;
      version = d.version ?? version;
      scope = d.scope ?? scope;
      ownerTeamId = d.ownerTeamId ?? ownerTeamId;
    } catch { /* ignore */ }
  });

  async function save() {
    saving = true;
    saveError = null;
    try {
      const payload = {
        scope,
        slug,
        title: displayName.trim(),
        description: description.trim(),
        body_md: body,
        version,
        tags: tagsInput.split(',').map((t) => t.trim()).filter(Boolean),
        slash_alias: slashAlias || null,
        jurisdiction: jurisdiction || null,
        owner_team_id: scope === 'team' ? ownerTeamId : null,
        forked_from: forkedFrom,
      };
      const newId = await onSave(payload);
      if (draftKey) localStorage.removeItem(`lq-ai:wizard-draft:${draftKey}`);
      return newId;
    } catch (e: any) {
      saveError = e?.message ?? 'Save failed';
      // Surface server-side 422 on slash_alias collision specifically
      if (typeof e?.message === 'string' && e.message.toLowerCase().includes('slash_alias')) {
        slashAliasError = e.message;
      }
      return null;
    } finally {
      saving = false;
    }
  }

  function saveDraft() {
    scheduleAutosave();
    setTimeout(() => alert('Draft saved locally — resume from /lq-ai/skills'), 350);
  }

  function discard() {
    if (!confirm('Discard this draft?')) return;
    if (draftKey) localStorage.removeItem(`lq-ai:wizard-draft:${draftKey}`);
    onDiscard();
  }

  onDestroy(() => { if (saveTimer) clearTimeout(saveTimer); });
</script>

<form on:submit|preventDefault={save} class="lq-skill-wizard">
  <SkillWizardSection index={1} title="What does this skill do?"
    hint="A name + one-line description; what triggers the skill is in section 2.">
    <label>
      <span>Display name *</span>
      <input bind:value={displayName} aria-label="display name" />
    </label>
    <label>
      <span>Slug *</span>
      <input
        bind:value={slug}
        on:input={() => (slugTouched = true)}
        aria-label="slug"
        pattern="^[a-z0-9]([a-z0-9-]{'{0,78}'}[a-z0-9])?$"
      />
      {#if slug && !slugValid}
        <span class="error">Lowercase letters, digits, and dashes; 1–80 chars.</span>
      {/if}
    </label>
    <label>
      <span>Description *</span>
      <textarea bind:value={description} aria-label="description" rows="2" />
    </label>
  </SkillWizardSection>

  <SkillWizardSection index={2} title="When should it run?"
    hint="What user phrasings or contexts indicate this skill applies?">
    <label>
      <span>Slash alias (optional)</span>
      <input
        bind:value={slashAlias}
        on:blur={validateSlashAlias}
        placeholder="/nda-review"
        aria-label="slash alias"
      />
      {#if slashAliasError}<span class="error">{slashAliasError}</span>{/if}
    </label>
    <label>
      <span>Tags (comma-separated)</span>
      <input bind:value={tagsInput} aria-label="tags" placeholder="contracts, nda" />
    </label>
  </SkillWizardSection>

  <SkillWizardSection index={3} title="What does it produce?"
    hint="The actual skill body — instructions the model follows.">
    <textarea bind:value={body} aria-label="body" rows="14"
              placeholder="# NDA Review&#10;Apply this skill when the user shares an NDA…" />
  </SkillWizardSection>

  <SkillWizardSection index={4} title="Try it out"
    hint="Test against a sandbox matter. This conversation is non-billable.">
    {#if body.trim()}
      <SkillTryItPane draftBody={body} draftSlug={slug || 'draft'} source="wizard-tryout" />
    {:else}
      <p class="hint">Add a body in section 3 to enable the sandbox.</p>
    {/if}
  </SkillWizardSection>

  <details class="advanced" bind:open={advancedOpen}>
    <summary>Advanced</summary>
    <label><span>Version</span><input bind:value={version} /></label>
    <label><span>Jurisdiction</span><input bind:value={jurisdiction} placeholder="us | eu | global | regime-aware" /></label>
    <!-- Scope/team picker reuses the existing patterns from /skills/new — wire in via parent if needed. -->
  </details>

  {#if saveError}
    <div class="error banner">{saveError}</div>
  {/if}

  <footer class="actions">
    <button type="button" class="ghost" on:click={discard}>Discard</button>
    <button type="button" class="ghost" on:click={saveDraft}>Save draft</button>
    <button type="submit" class="primary" disabled={!canSave}>{saving ? 'Saving…' : 'Save'}</button>
  </footer>
</form>

<style>
  .lq-skill-wizard { max-width: 760px; margin: 0 auto; padding: 24px; }
  label { display: block; margin-bottom: 12px; }
  label > span { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
  input, textarea {
    width: 100%; padding: 8px; border: 1px solid var(--lq-border);
    border-radius: 6px; font-size: 14px; font-family: inherit;
  }
  textarea { font-family: ui-monospace, monospace; }
  .error { color: var(--lq-error, #b91c1c); font-size: 12px; }
  .banner { margin: 16px 0; padding: 8px 12px; border-radius: 6px;
            background: rgba(185, 28, 28, 0.08); }
  .advanced { margin: 16px 0; }
  .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 24px;
             padding-top: 16px; border-top: 1px solid var(--lq-border); }
  .ghost { background: transparent; border: 1px solid var(--lq-border);
           padding: 8px 16px; border-radius: 6px; cursor: pointer; }
  .primary { background: var(--lq-accent); color: white; border: 0;
             padding: 8px 16px; border-radius: 6px; cursor: pointer; }
  .primary:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
```

- [ ] **Step 4: Run, expect PASS**

```bash
cd web && npm run test:frontend -- --run SkillWizard
```

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/SkillWizard.svelte \
        web/src/lib/lq-ai/__tests__/SkillWizard.test.ts
git commit -s -m "feat(web): SkillWizard component with localStorage drafts (Wave D.2)"
```

---

### Task 4.3: Refactor `/lq-ai/skills/new/+page.svelte` to wrap `SkillWizard`

**Files:**
- Modify: `web/src/routes/lq-ai/skills/new/+page.svelte`

- [ ] **Step 1: Rewrite the page**

Replace the contents of `web/src/routes/lq-ai/skills/new/+page.svelte` with:

```svelte
<script lang="ts">
  /**
   * /lq-ai/skills/new — Wave D.2 wizard entry point.
   * Supports three entry modes via query params:
   *   blank      (no params)
   *   ?fork=<slug>      pre-populate from source skill via GET /skills/{slug}
   *   ?capture=<key>    pre-populate from localStorage stash by key
   *   ?draft=<key>      resume in-progress wizard draft by key
   */
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { skillsApi, userSkillsApi } from '$lib/lq-ai/api';
  import SkillWizard from '$lib/lq-ai/components/SkillWizard.svelte';

  let initial: any = {};
  let draftKey: string | null = null;
  let loadError: string | null = null;
  let loading = true;

  $: forkSlug = $page.url.searchParams.get('fork');
  $: captureKey = $page.url.searchParams.get('capture');
  $: explicitDraftKey = $page.url.searchParams.get('draft');

  onMount(async () => {
    try {
      if (forkSlug) {
        const source = await skillsApi.getSkill(forkSlug);
        initial = {
          slug: await uniqueSlug(`${source.name}-fork`),
          displayName: `${source.title ?? source.name} (fork)`,
          description: source.description ?? '',
          body: source.content_md ?? '',
          tags: source.tags ?? [],
          slashAlias: null,
          jurisdiction: source.jurisdiction ?? '',
          version: '1.0.0',
          scope: 'user',
          forkedFrom: source.name,
        };
        draftKey = `fork-${forkSlug}-${crypto.randomUUID()}`;
      } else if (captureKey) {
        const stash = localStorage.getItem(`lq-ai:capture-stash:${captureKey}`);
        if (stash) {
          initial = JSON.parse(stash);
          localStorage.removeItem(`lq-ai:capture-stash:${captureKey}`);
        }
        draftKey = captureKey;
      } else if (explicitDraftKey) {
        draftKey = explicitDraftKey;
      } else {
        draftKey = crypto.randomUUID();
      }
    } catch (e: any) {
      loadError = e?.message ?? 'Failed to load source';
    } finally {
      loading = false;
    }
  });

  async function uniqueSlug(base: string): Promise<string> {
    // Cheap dedup: append -2, -3, etc. if collision-check against user's skills.
    // Server returns 409 on collision at save-time; this is a UX nicety only.
    const mine = await userSkillsApi.listUserSkills('all');
    const taken = new Set(mine.map((s) => s.slug));
    if (!taken.has(base)) return base;
    for (let i = 2; i < 100; i++) {
      const candidate = `${base}-${i}`;
      if (!taken.has(candidate)) return candidate;
    }
    return `${base}-${crypto.randomUUID().slice(0, 6)}`;
  }

  async function onSave(payload: any): Promise<string> {
    const r = await userSkillsApi.createUserSkill(payload);
    goto(`/lq-ai/skills/${encodeURIComponent(r.slug)}?just_saved=1`);
    return r.id;
  }

  function onDiscard() {
    goto('/lq-ai/skills');
  }
</script>

<main class="lq-skills-new">
  {#if loading}
    <p class="lq-text-body">Loading…</p>
  {:else if loadError}
    <div class="banner">
      Couldn't load source skill ({loadError}). Starting blank.
      <a href="/lq-ai/skills">Pick a different source</a>
    </div>
    <SkillWizard {initial} {draftKey} {onSave} {onDiscard} />
  {:else}
    <SkillWizard {initial} {draftKey} {onSave} {onDiscard} />
  {/if}
</main>

<style>
  .lq-skills-new { padding: 32px 24px; }
  .banner {
    background: rgba(234, 179, 8, 0.1); padding: 12px 16px;
    border-radius: 6px; margin-bottom: 16px;
  }
</style>
```

- [ ] **Step 2: Verify build + existing tests**

```bash
cd web && npm run test:frontend -- --run
```
Expected: all 228+ Vitest tests pass; no test regression.

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/lq-ai/skills/new/+page.svelte
git commit -s -m "refactor(web): /skills/new wraps SkillWizard with fork/capture/draft entry modes (Wave D.2)"
```

---

### Task 4.4: `🔱 Fork as my own` button on skill detail page

**Files:**
- Modify: `web/src/routes/lq-ai/skills/[id]/+page.svelte`

- [ ] **Step 1: Edit the detail page**

Update the header actions to add a Fork button alongside Edit. In the existing `<header>` block:

```svelte
<header style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--lq-space-4);">
  <div>
    <h1 class="lq-text-page-h">{skill.title ?? skill.name}</h1>
    <p class="lq-text-caption" style="color: var(--lq-text-tertiary); margin-top: var(--lq-space-1);">
      {skill.name}{skill.version ? ` · v${skill.version}` : ''}
    </p>
  </div>
  <div style="display: flex; gap: 8px;">
    <a
      href={`/lq-ai/skills/new?fork=${encodeURIComponent(skill.name)}`}
      class="lq-btn-ghost"
      aria-label={`Fork ${skill.title ?? skill.name} as my own`}
    >🔱 Fork as my own</a>
    {#if skill.owned_by_me}
      <a href={`/lq-ai/skills/${encodeURIComponent(skill.name)}/edit`} class="lq-btn-primary">Edit</a>
    {/if}
  </div>
</header>
```

Add `.lq-btn-ghost` style (or reuse an existing ghost-button class) at the bottom:

```css
.lq-btn-ghost {
  background: transparent;
  color: var(--lq-text-primary);
  border: 1px solid var(--lq-border);
  border-radius: var(--lq-radius);
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}
.lq-btn-ghost:hover { background: var(--lq-surface-tinted); }
```

The `skill.owned_by_me` field must come back from `GET /skills/{slug}` — if it's not already returned, add it in the response shape: true when the caller's id matches `owner_user_id` (or team membership for team-scope). Backend change is small; piggyback on Task 2.4's user_skills response work if not already done.

- [ ] **Step 2: Manual verification**

Start the stack, log in, navigate to a built-in skill, see the Fork button. Click → land on `/skills/new?fork=<slug>` with the wizard pre-populated.

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/lq-ai/skills/[id]/+page.svelte
git commit -s -m "feat(web): 🔱 Fork as my own button on skill detail (Wave D.2)"
```


---

## Wave 5 — Capture from chat (Mode A)

### Task 5.1: `capture-affordance` preference store

**Files:**
- Create: `web/src/lib/lq-ai/preferences/capture-affordance.ts`
- Modify: `web/src/lib/lq-ai/preferences/index.ts` (export the new store)

- [ ] **Step 1: Implement the store**

```ts
// web/src/lib/lq-ai/preferences/capture-affordance.ts
/**
 * Whether the inline "📝 Capture as skill" button shows next to thumbs
 * on every AI message. When false, the button is demoted to the message's
 * overflow (⋯) menu.
 *
 * Persisted via the existing user-preferences API.
 */
import { writable } from 'svelte/store';
import { preferencesApi } from '$lib/lq-ai/api/preferences';

const PREF_KEY = 'capture_affordance_inline';
const DEFAULT_VALUE = true;

function createStore() {
  const { subscribe, set } = writable<boolean>(DEFAULT_VALUE);

  return {
    subscribe,
    async load(): Promise<void> {
      try {
        const prefs = await preferencesApi.getMyPreferences();
        const stored = (prefs as any)[PREF_KEY];
        set(typeof stored === 'boolean' ? stored : DEFAULT_VALUE);
      } catch { /* keep default */ }
    },
    async setValue(v: boolean): Promise<void> {
      set(v);
      try {
        await preferencesApi.patchMyPreferences({ [PREF_KEY]: v });
      } catch { /* swallow; user can retry by toggling again */ }
    },
  };
}

export const captureAffordanceInline = createStore();
```

If the user-preferences API doesn't support arbitrary keys, store this preference as a column-style preference. Pattern-match what the existing `web/src/lib/lq-ai/preferences/` files do (e.g., look at how an existing toggle like `auto_enhance` is wired).

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/lq-ai/preferences/capture-affordance.ts \
        web/src/lib/lq-ai/preferences/index.ts
git commit -s -m "feat(web): capture-affordance preference store (Wave D.2)"
```

---

### Task 5.2: `CaptureSkillModal` component

**Files:**
- Create: `web/src/lib/lq-ai/components/CaptureSkillModal.svelte`
- Create: `web/src/lib/lq-ai/__tests__/CaptureSkillModal.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/lq-ai/__tests__/CaptureSkillModal.test.ts
import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import CaptureSkillModal from '../components/CaptureSkillModal.svelte';
import { userSkillsApi } from '../api/userSkills';

describe('CaptureSkillModal', () => {
  const message = {
    id: 'msg-1',
    role: 'assistant' as const,
    content: '# NDA Review Outcome\n\nThe NDA you shared has two unusual provisions…',
  };

  it('pre-populates from an AI message', () => {
    render(CaptureSkillModal, {
      props: { sourceMessage: message, onClose: () => {} },
    });
    const name = screen.getByLabelText(/name/i) as HTMLInputElement;
    expect(name.value.toLowerCase()).toContain('nda');

    const body = screen.getByLabelText(/body/i) as HTMLTextAreaElement;
    expect(body.value).toContain('NDA you shared');
  });

  it('Save calls POST /user-skills with source_message_id', async () => {
    const spy = vi.spyOn(userSkillsApi, 'createUserSkill').mockResolvedValue({
      id: 'new-id', slug: 'nda-review-outcome', title: 'NDA Review Outcome',
    } as any);
    render(CaptureSkillModal, {
      props: { sourceMessage: message, onClose: () => {} },
    });
    const description = screen.getByLabelText(/description/i) as HTMLTextAreaElement;
    await fireEvent.input(description, { target: { value: 'Captures NDA outcomes' } });
    await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({
      source_message_id: 'msg-1',
      title: expect.any(String),
      body_md: expect.stringContaining('NDA'),
    }));
  });

  it('Save button disabled when body or name is empty', async () => {
    render(CaptureSkillModal, {
      props: { sourceMessage: { ...message, content: '' }, onClose: () => {} },
    });
    const save = screen.getByRole('button', { name: /^save$/i }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd web && npm run test:frontend -- --run CaptureSkillModal
```

- [ ] **Step 3: Implement the modal**

```svelte
<!-- web/src/lib/lq-ai/components/CaptureSkillModal.svelte -->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { userSkillsApi } from '$lib/lq-ai/api';
  import type { ChatMessage } from '$lib/lq-ai/types';

  export let sourceMessage: ChatMessage;
  export let onClose: () => void;

  function derive() {
    const lines = sourceMessage.content.split('\n').map((l) => l.trim()).filter(Boolean);
    const heading = lines.find((l) => l.startsWith('#'))?.replace(/^#+\s*/, '') ?? '';
    const firstSentence = lines.find((l) => !l.startsWith('#') && !l.startsWith('-'))?.split(/(?<=[.!?])\s/)[0] ?? '';
    const derivedName = heading || firstSentence.slice(0, 60) || 'Captured skill';
    const derivedSlug = derivedName.toLowerCase()
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) ||
      `captured-skill-${sourceMessage.id.slice(0, 6)}`;
    const derivedDescription = firstSentence;
    return { name: derivedName, slug: derivedSlug, description: derivedDescription };
  }
  const derived = derive();

  let name = derived.name;
  let slug = derived.slug;
  let description = derived.description;
  let body = sourceMessage.content;
  let saving = false;
  let error: string | null = null;

  $: canSave = !saving && name.trim() && slug.trim() && body.trim();

  async function save() {
    saving = true;
    error = null;
    try {
      await userSkillsApi.createUserSkill({
        scope: 'user',
        slug,
        title: name.trim(),
        description: description.trim() || name.trim(),
        body_md: body,
        version: '1.0.0',
        source_message_id: sourceMessage.id,
      } as any);
      onClose();
      // toast handled by parent (which subscribes to 'skill-captured' event or
      // listens to a store); for now goto the new skill
      goto(`/lq-ai/skills/${encodeURIComponent(slug)}?just_saved=1`);
    } catch (e: any) {
      error = e?.message ?? 'Save failed';
    } finally {
      saving = false;
    }
  }

  function editInWizard() {
    const key = crypto.randomUUID();
    localStorage.setItem(`lq-ai:capture-stash:${key}`, JSON.stringify({
      slug, displayName: name, description, body,
      forkedFrom: null, scope: 'user', version: '1.0.0',
    }));
    onClose();
    goto(`/lq-ai/skills/new?capture=${key}`);
  }
</script>

<div class="modal-scrim" on:click={onClose}>
  <div class="modal" on:click|stopPropagation role="dialog" aria-label="Capture as skill">
    <h2>Capture as a skill</h2>
    <p class="hint">Save this exchange as a personal skill. You can refine triggers later in the editor.</p>

    <label>
      <span>Name *</span>
      <input bind:value={name} aria-label="name" />
    </label>
    <label>
      <span>Slug *</span>
      <input bind:value={slug} aria-label="slug" />
    </label>
    <label>
      <span>Description</span>
      <textarea bind:value={description} aria-label="description" rows="2" />
    </label>
    <label>
      <span>Body *</span>
      <textarea bind:value={body} aria-label="body" rows="10" />
    </label>

    {#if error}<div class="error">{error}</div>{/if}

    <footer>
      <button type="button" class="ghost" on:click={onClose}>Cancel</button>
      <button type="button" class="ghost" on:click={editInWizard}>Edit in wizard</button>
      <button type="button" class="primary" on:click={save} disabled={!canSave}>
        {saving ? 'Saving…' : 'Save'}
      </button>
    </footer>
  </div>
</div>

<style>
  .modal-scrim {
    position: fixed; inset: 0; background: rgba(0,0,0,0.4);
    display: flex; align-items: center; justify-content: center; z-index: 1000;
  }
  .modal {
    background: var(--lq-surface); border-radius: 8px; padding: 24px;
    width: 560px; max-width: 90vw; max-height: 90vh; overflow-y: auto;
  }
  label { display: block; margin-bottom: 12px; }
  label > span { font-size: 13px; font-weight: 600; display: block; margin-bottom: 4px; }
  input, textarea {
    width: 100%; padding: 8px; border: 1px solid var(--lq-border);
    border-radius: 6px; font-family: inherit; font-size: 14px;
  }
  textarea { font-family: ui-monospace, monospace; }
  footer { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
  .ghost { background: transparent; border: 1px solid var(--lq-border);
           padding: 8px 16px; border-radius: 6px; cursor: pointer; }
  .primary { background: var(--lq-accent); color: white; border: 0;
             padding: 8px 16px; border-radius: 6px; cursor: pointer; }
  .primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .error { color: var(--lq-error); margin-top: 8px; }
  .hint { color: var(--lq-text-tertiary); font-size: 13px; }
</style>
```

- [ ] **Step 4: Run, expect PASS**

```bash
cd web && npm run test:frontend -- --run CaptureSkillModal
```

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/CaptureSkillModal.svelte \
        web/src/lib/lq-ai/__tests__/CaptureSkillModal.test.ts
git commit -s -m "feat(web): CaptureSkillModal — thin Mode-A capture flow (Wave D.2)"
```

---

### Task 5.3: `MessageOverflowMenu` + integrate into `MessageBubble`

**Files:**
- Create: `web/src/lib/lq-ai/components/MessageOverflowMenu.svelte`
- Modify: `web/src/lib/lq-ai/components/MessageBubble.svelte`

- [ ] **Step 1: Implement `MessageOverflowMenu`**

```svelte
<!-- web/src/lib/lq-ai/components/MessageOverflowMenu.svelte -->
<script lang="ts">
  export let onCapture: () => void;
  export let captureInOverflow: boolean = false;
  let open = false;
</script>

<div class="overflow" on:focusout={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) open = false; }}>
  <button class="trigger" aria-label="more actions" on:click={() => (open = !open)}>⋯</button>
  {#if open}
    <ul class="menu" role="menu">
      {#if captureInOverflow}
        <li><button role="menuitem" on:click={() => { open = false; onCapture(); }}>
          📝 Capture as skill
        </button></li>
      {/if}
      <li><button role="menuitem" disabled>Copy markdown</button></li>
      <li><button role="menuitem" disabled>Retry</button></li>
    </ul>
  {/if}
</div>

<style>
  .overflow { position: relative; display: inline-block; }
  .trigger { background: transparent; border: 0; padding: 4px 8px; cursor: pointer;
             color: var(--lq-text-tertiary); }
  .menu { list-style: none; padding: 4px 0; margin: 0;
          position: absolute; right: 0; top: 100%;
          background: var(--lq-surface); border: 1px solid var(--lq-border);
          border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);
          min-width: 180px; z-index: 10; }
  .menu button { width: 100%; text-align: left; padding: 6px 12px;
                 background: transparent; border: 0; font-size: 14px; cursor: pointer; }
  .menu button:hover:not(:disabled) { background: var(--lq-surface-tinted); }
  .menu button:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
```

- [ ] **Step 2: Integrate into `MessageBubble`**

In `web/src/lib/lq-ai/components/MessageBubble.svelte`, in the AI-message branch:

```svelte
<script lang="ts">
  // existing imports + props...
  import { captureAffordanceInline } from '$lib/lq-ai/preferences/capture-affordance';
  import CaptureSkillModal from './CaptureSkillModal.svelte';
  import MessageOverflowMenu from './MessageOverflowMenu.svelte';

  let captureOpen = false;
  // Subscribe to preference store
  let captureInline = true;
  $: captureAffordanceInline.subscribe((v) => (captureInline = v));
</script>

<!-- inside the AI message's action row -->
<div class="msg-actions">
  <button aria-label="thumbs up">👍</button>
  <button aria-label="thumbs down">👎</button>
  {#if message.role === 'assistant' && captureInline}
    <button
      aria-label="capture as skill"
      title="Capture as skill"
      on:click={() => (captureOpen = true)}
    >📝</button>
  {/if}
  {#if message.role === 'assistant'}
    <MessageOverflowMenu
      captureInOverflow={!captureInline}
      onCapture={() => (captureOpen = true)}
    />
  {/if}
</div>

{#if captureOpen}
  <CaptureSkillModal
    sourceMessage={message}
    onClose={() => (captureOpen = false)}
  />
{/if}
```

(Adjust paths/syntax to match the actual `MessageBubble.svelte` layout — wrap the existing action row rather than replacing it wholesale. Don't touch the user-message branch.)

- [ ] **Step 3: Manual verification**

```bash
docker compose up -d
```
Log in at `http://localhost:3000/lq-ai/login` (creds in `reference_lq_ai_dev_quirks` memory: `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!`). Open a chat, send a prompt, see the `📝` icon on the AI reply. Click it → modal opens pre-populated. Save → land on the new skill's detail page.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/components/MessageOverflowMenu.svelte \
        web/src/lib/lq-ai/components/MessageBubble.svelte
git commit -s -m "feat(web): Capture button + overflow menu on AI messages (Wave D.2)"
```

---

### Task 5.4: Settings entry for capture-affordance toggle

**Files:**
- Modify: `web/src/routes/lq-ai/settings/appearance/+page.svelte`

- [ ] **Step 1: Add the toggle row**

Append a toggle to the appearance settings page (or a more apt settings sub-page if the codebase already has a "chat" settings section):

```svelte
<script lang="ts">
  // existing imports
  import { captureAffordanceInline } from '$lib/lq-ai/preferences/capture-affordance';
  import { onMount } from 'svelte';

  let inline = true;
  onMount(() => captureAffordanceInline.load());
  $: captureAffordanceInline.subscribe((v) => (inline = v));
</script>

<!-- existing markup, then: -->
<section class="pref-row">
  <h3>Skill capture button</h3>
  <p class="hint">Show <code>📝 Capture as skill</code> inline on every AI message. When off, the action stays available in the message's overflow menu.</p>
  <label>
    <input
      type="checkbox"
      bind:checked={inline}
      on:change={() => captureAffordanceInline.setValue(inline)}
    />
    Show inline on AI messages
  </label>
</section>
```

- [ ] **Step 2: Manual verification**

Toggle off in settings → return to chat → see capture button moved into `⋯` menu. Toggle on → returns to inline.

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/lq-ai/settings/appearance/+page.svelte
git commit -s -m "feat(web): toggle for inline capture-as-skill affordance (Wave D.2)"
```


---

## Wave 6 — Detail tabs (Try-it + Versions)

### Task 6.1: `SkillTryItTab` wrapper

**Files:**
- Create: `web/src/lib/lq-ai/components/SkillTryItTab.svelte`

- [ ] **Step 1: Implement**

```svelte
<!-- web/src/lib/lq-ai/components/SkillTryItTab.svelte -->
<script lang="ts">
  import SkillTryItPane from './SkillTryItPane.svelte';
  export let skillSlug: string;
</script>

<SkillTryItPane {skillSlug} source="tryit-tab" />
```

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/lq-ai/components/SkillTryItTab.svelte
git commit -s -m "feat(web): SkillTryItTab wrapper (Wave D.2)"
```

---

### Task 6.2: `SkillVersionsTab`

**Files:**
- Create: `web/src/lib/lq-ai/components/SkillVersionsTab.svelte`
- Create: `web/src/lib/lq-ai/__tests__/SkillVersionsTab.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/lq-ai/__tests__/SkillVersionsTab.test.ts
import { render, screen, waitFor } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import SkillVersionsTab from '../components/SkillVersionsTab.svelte';
import { userSkillsApi } from '../api/userSkills';

describe('SkillVersionsTab', () => {
  it('renders empty state for built-in skill (skillId null)', () => {
    render(SkillVersionsTab, { props: { skill: { name: 'nda-review', scope: 'builtin' } } });
    expect(screen.getByText(/no edit history/i)).toBeTruthy();
  });

  it('renders a row per audit entry', async () => {
    vi.spyOn(userSkillsApi, 'listVersions').mockResolvedValue({
      items: [
        { timestamp: '2026-05-13T14:00:00Z', actor_email: 'a@b.com', action: 'user_skill.updated',
          version: '1.0.1', actor_user_id: null, details: null },
        { timestamp: '2026-05-13T12:00:00Z', actor_email: 'a@b.com', action: 'user_skill.created',
          version: '1.0.0', actor_user_id: null, details: null },
      ],
    });
    render(SkillVersionsTab, { props: { skill: { id: 'sk-1', name: 'x', scope: 'user' } } });
    await waitFor(() => expect(screen.getByText('user_skill.created')).toBeTruthy());
    expect(screen.getByText('user_skill.updated')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

```bash
cd web && npm run test:frontend -- --run SkillVersionsTab
```

- [ ] **Step 3: Implement**

```svelte
<!-- web/src/lib/lq-ai/components/SkillVersionsTab.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { userSkillsApi } from '$lib/lq-ai/api';
  import type { UserSkillVersion } from '$lib/lq-ai/types';

  /** Pass the full skill object (built-in or user-skill). */
  export let skill: { id?: string; name: string; scope: 'user' | 'team' | 'builtin' };

  let versions: UserSkillVersion[] = [];
  let loading = false;
  let error: string | null = null;

  onMount(async () => {
    if (skill.scope === 'builtin' || !skill.id) return;
    loading = true;
    try {
      const r = await userSkillsApi.listVersions(skill.id);
      versions = r.items;
    } catch (e: any) {
      error = e?.message ?? 'Failed to load versions';
    } finally {
      loading = false;
    }
  });
</script>

{#if skill.scope === 'builtin'}
  <div class="empty">
    <p><strong>Built-in skill · no edit history.</strong></p>
    <p>Fork it to create your own version with tracked changes.</p>
  </div>
{:else if loading}
  <p>Loading versions…</p>
{:else if error}
  <p class="error">{error}</p>
{:else if versions.length === 0}
  <p class="empty">No edit history yet.</p>
{:else}
  <table class="versions">
    <thead>
      <tr><th>When</th><th>Who</th><th>Action</th><th>Version</th></tr>
    </thead>
    <tbody>
      {#each versions as v}
        <tr>
          <td>{new Date(v.timestamp).toLocaleString()}</td>
          <td>{v.actor_email ?? '—'}</td>
          <td>{v.action}</td>
          <td>{v.version ?? '—'}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  .empty { padding: 24px; text-align: center; color: var(--lq-text-tertiary); }
  .versions { width: 100%; border-collapse: collapse; }
  .versions th, .versions td {
    padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--lq-border);
    font-size: 13px;
  }
  .versions th { font-weight: 600; color: var(--lq-text-secondary); }
  .error { color: var(--lq-error); }
</style>
```

- [ ] **Step 4: Run, expect PASS**

```bash
cd web && npm run test:frontend -- --run SkillVersionsTab
```

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/SkillVersionsTab.svelte \
        web/src/lib/lq-ai/__tests__/SkillVersionsTab.test.ts
git commit -s -m "feat(web): SkillVersionsTab audit-log view (Wave D.2)"
```

---

### Task 6.3: Extend `SkillDetailTabs` to 4 tabs

**Files:**
- Modify: `web/src/lib/lq-ai/components/SkillDetailTabs.svelte`

- [ ] **Step 1: Replace the tab definitions**

The current component has 2 tabs (use, source). Extend the `activeTab` union and add the two new tab buttons:

```svelte
<script lang="ts">
  export let activeTab: 'use' | 'source' | 'try' | 'versions' = 'use';
  export let onTabChange: (t: 'use' | 'source' | 'try' | 'versions') => void;

  const tabs: { id: 'use' | 'source' | 'try' | 'versions'; label: string }[] = [
    { id: 'use',      label: 'Use it' },
    { id: 'source',   label: 'View source' },
    { id: 'try',      label: 'Try it' },
    { id: 'versions', label: 'Versions' },
  ];
</script>

<nav class="lq-skill-tabs" role="tablist">
  {#each tabs as t}
    <button
      role="tab"
      aria-selected={activeTab === t.id}
      class:active={activeTab === t.id}
      on:click={() => onTabChange(t.id)}
    >{t.label}</button>
  {/each}
</nav>

<style>
  .lq-skill-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--lq-border); }
  .lq-skill-tabs button {
    padding: 8px 16px; background: transparent; border: 0; cursor: pointer;
    border-bottom: 2px solid transparent; font-size: 14px; font-weight: 500;
    color: var(--lq-text-secondary);
  }
  .lq-skill-tabs button.active {
    color: var(--lq-accent); border-bottom-color: var(--lq-accent);
  }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/lq-ai/components/SkillDetailTabs.svelte
git commit -s -m "feat(web): SkillDetailTabs adds Try it + Versions tabs (Wave D.2)"
```

---

### Task 6.4: Wire skill detail page with 4 tabs + `?tab=` deep link

**Files:**
- Modify: `web/src/routes/lq-ai/skills/[id]/+page.svelte`

- [ ] **Step 1: Update the page**

Replace the tab body and add `?tab=` handling:

```svelte
<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { skillsApi } from '$lib/lq-ai/api';
  import type { Skill } from '$lib/lq-ai/types';
  import SkillDetailTabs from '$lib/lq-ai/components/SkillDetailTabs.svelte';
  import SkillSourceView from '$lib/lq-ai/components/SkillSourceView.svelte';
  import SkillTryItTab from '$lib/lq-ai/components/SkillTryItTab.svelte';
  import SkillVersionsTab from '$lib/lq-ai/components/SkillVersionsTab.svelte';

  type Tab = 'use' | 'source' | 'try' | 'versions';
  const VALID: Tab[] = ['use', 'source', 'try', 'versions'];

  let skill: Skill | null = null;
  let error: string | null = null;

  $: skillName = $page.params.id;
  $: activeTab = (VALID.includes($page.url.searchParams.get('tab') as Tab)
    ? ($page.url.searchParams.get('tab') as Tab)
    : 'use');

  onMount(async () => {
    try {
      skill = await skillsApi.getSkill(skillName);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load skill';
    }
  });

  function setTab(t: Tab) {
    const url = new URL($page.url);
    url.searchParams.set('tab', t);
    goto(url.pathname + url.search, { keepFocus: true, replaceState: false });
  }
</script>

<main style="padding: var(--lq-space-6); max-width: 1100px; margin: 0 auto;">
  {#if error}
    <p style="color: var(--lq-error);">Couldn't load skill: {error}</p>
  {:else if skill}
    <!-- existing header with title + Fork + Edit (from Task 4.4) -->

    <SkillDetailTabs {activeTab} onTabChange={setTab} />

    <div style="margin-top: var(--lq-space-4);">
      {#if activeTab === 'use'}
        <article style="white-space: pre-wrap;">
          {skill.description ?? '(no description)'}
        </article>
      {:else if activeTab === 'source'}
        <SkillSourceView
          slug={skill.name}
          contentMd={skill.content_md}
          contentYaml={skill.content_yaml}
        />
      {:else if activeTab === 'try'}
        <SkillTryItTab skillSlug={skill.name} />
      {:else if activeTab === 'versions'}
        <SkillVersionsTab {skill} />
      {/if}
    </div>
  {:else}
    <p>Loading skill…</p>
  {/if}
</main>
```

Note: `skill.id` is needed by `SkillVersionsTab` when scope is `user` or `team`. If the existing `getSkill` response doesn't include `id` for user/team skills, extend the response in `api/app/api/skills.py` to include it.

- [ ] **Step 2: Verify**

```bash
cd web && npm run test:frontend -- --run
```
Expected: all tests pass; no regressions.

Manual: navigate to `/lq-ai/skills/nda-review` → see 4 tabs → click each → URL reflects `?tab=`.

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/lq-ai/skills/[id]/+page.svelte
git commit -s -m "feat(web): skill detail page renders 4 tabs with deep-link via ?tab= (Wave D.2)"
```


---

## Wave 7 — Slash invocation in composer

### Task 7.1: Wire `SlashPopover` into `ChatPanel`

**Files:**
- Modify: `web/src/lib/lq-ai/components/ChatPanel.svelte`

The existing `ChatPanel.svelte` is ~953 LOC and already hosts the composer + `SkillPicker`. Add bare-`/` detection at line-start, surface the popover, and on selection attach the skill via the same mechanism the picker already uses.

- [ ] **Step 1: Add slash detection state to the script block**

Near the top of the `<script lang="ts">` block in `ChatPanel.svelte`:

```ts
import SlashPopover from '$lib/lq-ai/components/SlashPopover.svelte';
import AttachedSkillPill from '$lib/lq-ai/components/AttachedSkillPill.svelte';

let slashOpen = false;
let slashQuery = '';        // characters typed after the leading slash
let slashStartIndex = -1;   // position in composerText where '/' was typed

function isAtLineStart(text: string, pos: number): boolean {
  if (pos === 0) return true;
  const prev = text[pos - 1];
  return prev === '\n';
}

function detectSlash(text: string, caret: number) {
  // Look backward from caret for a '/' at line-start with only [a-z0-9-] after it.
  if (caret === 0) { slashOpen = false; return; }
  // Find the last '/' before caret
  let scan = caret;
  while (scan > 0 && /[a-z0-9-]/.test(text[scan - 1])) scan--;
  if (scan === 0 || text[scan - 1] !== '/') { slashOpen = false; return; }
  const slashPos = scan - 1;
  if (!isAtLineStart(text, slashPos)) { slashOpen = false; return; }
  slashOpen = true;
  slashStartIndex = slashPos;
  slashQuery = text.slice(slashPos + 1, caret);
}

function onComposerInput(e: Event) {
  const ta = e.target as HTMLTextAreaElement;
  composerText = ta.value;
  detectSlash(composerText, ta.selectionStart);
}

function onSlashSelect(item: any) {
  // item is SkillAutocompleteItem
  // 1. Strip "/<query>" from composer text
  const before = composerText.slice(0, slashStartIndex);
  const after = composerText.slice(slashStartIndex + 1 + slashQuery.length);
  composerText = (before + after).replace(/^\s*/, ''); // trim leading whitespace from the now-floated suffix

  // 2. Attach skill via the same store/state that SkillPicker uses
  attachedSkills = [
    ...attachedSkills.filter((s) => s.slug !== item.slug),
    { slug: item.slug, title: item.title, icon: item.icon ?? null, source: 'slash' },
  ];

  slashOpen = false;
}

function onSlashDismiss() {
  slashOpen = false;
}

function removeAttachedSkill(slug: string) {
  attachedSkills = attachedSkills.filter((s) => s.slug !== slug);
}
```

(`composerText`, `attachedSkills` should already exist in the file — refactor names to match. `attachedSkills` may already be tracked under a different name like `selectedSkills` from `SkillPicker` integration. Use the existing name.)

- [ ] **Step 2: Update composer textarea + add popover render**

In the template, wherever the `<textarea>` for the composer lives:

```svelte
<div class="composer-attached-row">
  {#each attachedSkills as s (s.slug)}
    <AttachedSkillPill skill={s} onRemove={removeAttachedSkill} />
  {/each}
  <!-- existing KB pills, if any, render alongside -->
</div>

<textarea
  bind:value={composerText}
  on:input={onComposerInput}
  on:keydown={onComposerKeydown}
  placeholder="Ask anything…"
  rows="3"
></textarea>

{#if slashOpen}
  <div class="composer-popover-anchor">
    <SlashPopover
      query={slashQuery}
      onSelect={onSlashSelect}
      onDismiss={onSlashDismiss}
    />
  </div>
{/if}
```

CSS for `.composer-attached-row` (chip row above composer):

```css
.composer-attached-row {
  display: flex; gap: 6px; flex-wrap: wrap;
  margin-bottom: 6px; min-height: 0;
}
.composer-attached-row:empty { display: none; }
.composer-popover-anchor {
  position: absolute; bottom: 100%; left: 0; right: 0;
  margin-bottom: 6px; z-index: 20;
}
```

The composer textarea container needs `position: relative` for the anchor to attach correctly. If the existing container doesn't have it, add it.

- [ ] **Step 3: Manual verification**

```bash
docker compose up -d
```
- Log in, open a chat.
- Type `/` at the start of the composer → popover should appear with autocomplete results.
- Type `/nda` → results filter; arrow keys navigate; Enter picks.
- See pill appear in the attached-context row; composer text cleared of `/nda`.
- Click the `×` on the pill → pill removed.
- Type `/foo` mid-message (e.g., after a space) → popover does NOT open.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/components/ChatPanel.svelte
git commit -s -m "feat(web): slash-invocation popover wired into ChatPanel composer (Wave D.2)"
```

---

### Task 7.2: Send-time attaches `source: "slash"` provenance

**Files:**
- Modify: `web/src/lib/lq-ai/components/ChatPanel.svelte`

Slash-picked skills must reach the send-message payload with `source: "slash"` so receipts + audit can distinguish slash vs picker vs default attachments.

- [ ] **Step 1: Update the send handler**

Find the existing send handler in `ChatPanel.svelte` (search for `messagesApi.send` or `POST /messages`). Update payload construction to pass per-skill source if present:

```ts
async function sendMessage() {
  // ... existing logic ...
  const payload = {
    content: composerText,
    attached_skills: attachedSkills.map((s) => ({
      slug: s.slug,
      source: s.source ?? 'picker',  // 'slash' | 'picker' | 'default'
    })),
    attached_kbs: /* existing */,
  };
  await messagesApi.send(chatId, payload);
  // ...
}
```

The backend `attached_skills` field already exists; the `source` sub-field may be new. If the backend expects only `list[str]` of slugs, extend the API in api/app/api/messages.py to accept the richer shape and store `source` on the chat message provenance metadata.

- [ ] **Step 2: Manual verification**

After sending a slash-picked message, check the Receipts view (`💬 Chat ⇄ 📜 Receipts` toggle) → confirm the skill-attached event shows source = "slash".

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/lq-ai/components/ChatPanel.svelte api/app/api/messages.py
git commit -s -m "feat(web+api): slash-picked skills carry source=slash provenance (Wave D.2)"
```


---

## Wave 8 — Cypress E2E + live-run

**Discipline:** Per `feedback_dry_run_value` (memory) and the wave-D.1 lesson, every Cypress spec must be live-executed before Wave D.2 closes. The live-run is its own task (8.5) and produces real fixes, not just an assertion of green.

**Pre-flight per `reference_lq_ai_dev_quirks` (memory):**
- web binds `127.0.0.1:3000 -> 8080/tcp` (host port 3000)
- viewport must be `1440x900` (existing `cypress.config.ts`)
- the OpenWebUI bootstrap-admin hook is spec-name-gated; wave-prefixed specs (`wave-*`) skip it
- admin user `admin@lq.ai` password `LQ-AI-smoke-test-Pw1!` is reset via the CLI before runs

### Task 8.1: Spec scaffold + fixtures + custom commands

**Files:**
- Create: `web/cypress/e2e/wave-d2-skill-creator.cy.ts`
- Modify: `web/cypress/support/commands.ts` (or wherever shared commands live)

- [ ] **Step 1: Add shared commands**

In `web/cypress/support/commands.ts`, ensure (or add) these commands used by D.2 tests:

```ts
declare global {
  namespace Cypress {
    interface Chainable {
      loginAsLqAdmin(): Chainable<void>;
      createSampleMatter(name: string): Chainable<string>; // returns matter slug
      sendChatPrompt(text: string): Chainable<void>;
    }
  }
}

Cypress.Commands.add('loginAsLqAdmin', () => {
  const email = 'admin@lq.ai';
  const password = Cypress.env('LQAI_ADMIN_PASSWORD') ?? 'LQ-AI-smoke-test-Pw1!';
  cy.visit('/lq-ai/login');
  cy.findByLabelText(/email/i).type(email);
  cy.findByLabelText(/password/i).type(password);
  cy.findByRole('button', { name: /sign in/i }).click();
  cy.url({ timeout: 15000 }).should('include', '/lq-ai');
});

Cypress.Commands.add('createSampleMatter', (name: string) => {
  cy.visit('/lq-ai/matters');
  cy.findByRole('button', { name: /new matter/i }).click();
  cy.findByLabelText(/name/i).type(name);
  cy.intercept('POST', '/api/v1/projects').as('createProject');
  cy.findByRole('button', { name: /^create$/i }).click();
  cy.wait('@createProject').its('response.statusCode').should('eq', 201);
  return cy.url().then((url) => {
    const slug = url.split('/').pop()!;
    return cy.wrap(slug);
  });
});

Cypress.Commands.add('sendChatPrompt', (text: string) => {
  cy.findByRole('button', { name: /new chat/i }).click();
  cy.findByRole('textbox').type(text);
  cy.findByRole('button', { name: /send/i }).click();
});

export {};
```

(Reuse existing commands if they're already named differently — match the wave-d1 spec's conventions.)

- [ ] **Step 2: Author the spec file with placeholder describe blocks**

```ts
// web/cypress/e2e/wave-d2-skill-creator.cy.ts
/// <reference types="cypress" />

describe('Wave D.2 — Skill Creator', () => {
  beforeEach(() => {
    cy.loginAsLqAdmin();
  });

  it('1. Capture happy path: AI reply → modal → save → skill in list', () => {
    // populated in Task 8.2
  });

  it('2. Wizard from scratch: blank → fill 3 sections → set slash_alias → save', () => {
    // populated in Task 8.2
  });

  it('3. Fork flow: detail page → fork → wizard pre-populated → save', () => {
    // populated in Task 8.3
  });

  it('4. Slash invocation: type "/" in composer → popover → pick → pill → send', () => {
    // populated in Task 8.4
  });

  it('5. Try-it sandbox: detail Try-it tab → ensure sandbox → send → conversation persists', () => {
    // populated in Task 8.4
  });

  it('6. Versions tab + slash_alias collision: edit twice → tab shows 3 rows; collision → inline error', () => {
    // populated in Task 8.3
  });
});
```

- [ ] **Step 3: Reset admin password before commit**

```bash
docker exec -w /app lq-ai-api-1 python -m app.cli reset-admin-password \
  --email admin@lq.ai --password 'LQ-AI-smoke-test-Pw1!' --no-force-change
```

- [ ] **Step 4: Commit the scaffold**

```bash
git add web/cypress/e2e/wave-d2-skill-creator.cy.ts \
        web/cypress/support/commands.ts
git commit -s -m "test(web): wave-d2 Cypress spec scaffold + shared commands (Wave D.2)"
```

---

### Task 8.2: Tests 1 + 2 — Capture + From-scratch wizard

- [ ] **Step 1: Populate Test 1 (capture happy path)**

```ts
it('1. Capture happy path: AI reply → modal → save → skill in list', () => {
  cy.createSampleMatter('Capture Test Matter');
  cy.sendChatPrompt('Summarize the typical structure of a one-page sales contract.');

  // wait for AI reply
  cy.findAllByText(/contract/i, { timeout: 60000 }).should('exist');

  // click capture
  cy.findByLabelText(/capture as skill/i).click();
  cy.findByRole('dialog', { name: /capture as skill/i }).should('exist');

  // modify name
  cy.findByLabelText(/^name/i).clear().type('Sales Contract Structure');
  cy.findByLabelText(/^slug/i).clear().type('sales-contract-structure');

  cy.intercept('POST', '/api/v1/user-skills').as('createSkill');
  cy.findByRole('button', { name: /^save$/i }).click();
  cy.wait('@createSkill').its('response.statusCode').should('eq', 201);

  // verify in /skills list
  cy.visit('/lq-ai/skills');
  cy.findByText('Sales Contract Structure').should('exist');
});
```

- [ ] **Step 2: Populate Test 2 (wizard from scratch)**

```ts
it('2. Wizard from scratch: blank → fill 3 sections → set slash_alias → save', () => {
  cy.visit('/lq-ai/skills');
  cy.findByRole('link', { name: /new skill/i }).click();
  cy.url().should('include', '/lq-ai/skills/new');

  cy.findByLabelText(/display name/i).type('D.2 Test Skill');
  cy.findByLabelText(/^slug/i).should('have.value', 'd-2-test-skill');
  cy.findByLabelText(/^description/i).type('Test skill for Wave D.2 Cypress spec.');
  cy.findByLabelText(/slash alias/i).type('/d2-test');
  cy.findByLabelText(/^body/i).type('# D.2 test\nThis skill is a Cypress fixture.');

  cy.intercept('POST', '/api/v1/user-skills').as('createSkill');
  cy.findByRole('button', { name: /^save$/i }).click();
  cy.wait('@createSkill').its('response.statusCode').should('eq', 201);

  cy.url({ timeout: 5000 }).should('match', /\/lq-ai\/skills\/d-2-test-skill/);
  cy.findByText(/use it/i).should('exist');
});
```

- [ ] **Step 3: Run these two tests**

```bash
docker exec lq-ai-web-1 npx cypress run --spec cypress/e2e/wave-d2-skill-creator.cy.ts \
  --env grep="Test 1|Test 2"
```

(If `--env grep` isn't configured, run the whole spec and observe.)

- [ ] **Step 4: Commit**

```bash
git add web/cypress/e2e/wave-d2-skill-creator.cy.ts
git commit -s -m "test(web): wave-d2 Tests 1+2 — capture + wizard (Wave D.2)"
```

---

### Task 8.3: Tests 3 + 6 — Fork flow + Versions/Collision

- [ ] **Step 1: Populate Test 3 (fork flow)**

```ts
it('3. Fork flow: detail page → fork → wizard pre-populated → save', () => {
  cy.visit('/lq-ai/skills/nda-review');
  cy.findByRole('link', { name: /fork as my own/i }).click();
  cy.url().should('include', 'fork=nda-review');

  // wizard should be pre-populated
  cy.findByLabelText(/display name/i).should('have.value').and('match', /\(fork\)$/);
  cy.findByLabelText(/^slug/i).clear().type('nda-review-cypress-fork');
  cy.findByLabelText(/^description/i).should('not.have.value', '');

  cy.intercept('POST', '/api/v1/user-skills').as('saveFork');
  cy.findByRole('button', { name: /^save$/i }).click();
  cy.wait('@saveFork').its('request.body.forked_from').should('eq', 'nda-review');
});
```

- [ ] **Step 2: Populate Test 6 (Versions tab + collision)**

```ts
it('6. Versions tab + slash_alias collision: edit twice → 3 rows; collision → inline error', () => {
  // Pre-create a skill with a /foo alias
  cy.request('POST', '/api/v1/user-skills', {
    scope: 'user', slug: 'd2-versions-target', title: 'D2 Versions Target',
    description: 'd', body_md: 'b', version: '1.0.0', slash_alias: '/d2-target',
  }).its('body.id').as('skillId');

  cy.get('@skillId').then((id) => {
    // Edit description
    cy.request('PATCH', `/api/v1/user-skills/${id}`, { description: 'd2' });
    cy.request('PATCH', `/api/v1/user-skills/${id}`, { body_md: 'b2' });

    cy.visit('/lq-ai/skills/d2-versions-target?tab=versions');
    cy.findByText(/user_skill\.created/i).should('exist');
    cy.findAllByText(/user_skill\.updated/i).should('have.length', 2);
  });

  // Collision: try to create another skill with the same /d2-target alias
  cy.visit('/lq-ai/skills/new');
  cy.findByLabelText(/display name/i).type('Collision Test');
  cy.findByLabelText(/^description/i).type('x');
  cy.findByLabelText(/^body/i).type('x');
  cy.findByLabelText(/slash alias/i).type('/d2-target');
  cy.intercept('POST', '/api/v1/user-skills').as('collide');
  cy.findByRole('button', { name: /^save$/i }).click();
  cy.wait('@collide').its('response.statusCode').should('eq', 422);
  cy.findByText(/already used/i).should('exist');
});
```

- [ ] **Step 3: Run + commit**

```bash
docker exec lq-ai-web-1 npx cypress run --spec cypress/e2e/wave-d2-skill-creator.cy.ts
git add web/cypress/e2e/wave-d2-skill-creator.cy.ts
git commit -s -m "test(web): wave-d2 Tests 3+6 — fork + versions/collision (Wave D.2)"
```

---

### Task 8.4: Tests 4 + 5 — Slash invocation + Try-it sandbox (LLM-touching)

These two tests depend on a real LLM round-trip and are the most flake-prone. Set generous timeouts.

- [ ] **Step 1: Populate Test 4 (slash invocation)**

```ts
it('4. Slash invocation: type "/" in composer → popover → pick → pill → send', () => {
  // Pre-create the skill the popover will match
  cy.request('POST', '/api/v1/user-skills', {
    scope: 'user', slug: 'd2-slash-skill', title: 'D2 Slash Skill',
    description: 'd', body_md: 'echo: respond with "skill applied"',
    version: '1.0.0', slash_alias: '/d2-slash',
  });

  cy.createSampleMatter('Slash Test Matter');
  cy.findByRole('button', { name: /new chat/i }).click();

  // Type slash query
  cy.findByRole('textbox').type('/d2');

  // Popover should appear
  cy.findByRole('listbox').should('exist');
  cy.findByText('D2 Slash Skill').should('exist');

  // Pick via Enter
  cy.findByRole('textbox').type('{enter}');

  // Pill should appear in attached-context row
  cy.findByText('D2 Slash Skill').should('exist');
  cy.findByLabelText(/remove d2 slash skill/i).should('exist');

  // Composer text should no longer contain /d2
  cy.findByRole('textbox').should('have.value', '');

  // Type a prompt and send
  cy.intercept('POST', '/api/v1/chats/*/messages').as('sendMessage');
  cy.findByRole('textbox').type('test prompt');
  cy.findByRole('button', { name: /send/i }).click();

  cy.wait('@sendMessage', { timeout: 60000 })
    .its('request.body.attached_skills')
    .should('deep.include', { slug: 'd2-slash-skill', source: 'slash' });
});
```

- [ ] **Step 2: Populate Test 5 (try-it sandbox)**

```ts
it('5. Try-it sandbox: detail Try-it tab → ensure sandbox → send → conversation persists', () => {
  // ensure the skill exists
  cy.request('POST', '/api/v1/user-skills', {
    scope: 'user', slug: 'd2-tryit-skill', title: 'D2 Try-it Skill',
    description: 'd', body_md: 'respond briefly with "sandbox ok"',
    version: '1.0.0',
  });

  cy.intercept('POST', '/api/v1/projects/sandbox/ensure').as('sandboxEnsure');

  cy.visit('/lq-ai/skills/d2-tryit-skill?tab=try');
  cy.wait('@sandboxEnsure').its('response.statusCode').should('be.oneOf', [200, 201]);

  // Send a sandbox prompt
  cy.findByPlaceholderText(/try a prompt/i).type('hello sandbox');
  cy.findByRole('button', { name: /send/i }).click();

  // Wait for AI response
  cy.findByText(/sandbox ok|sandbox|hello/i, { timeout: 60000 }).should('exist');

  // Navigate away then back — conversation should persist
  cy.visit('/lq-ai/skills/d2-tryit-skill?tab=use');
  cy.visit('/lq-ai/skills/d2-tryit-skill?tab=try');
  cy.findByText('hello sandbox').should('exist');
});
```

- [ ] **Step 3: Run + commit**

```bash
docker exec lq-ai-web-1 npx cypress run --spec cypress/e2e/wave-d2-skill-creator.cy.ts
git add web/cypress/e2e/wave-d2-skill-creator.cy.ts
git commit -s -m "test(web): wave-d2 Tests 4+5 — slash + try-it sandbox (Wave D.2)"
```

---

### Task 8.5: Live-run integration pass (the wave-D.1 lesson)

The previous session learned the hard way that "lint-clean" Cypress specs hide integration bugs. This task is explicit time-budget for running the full spec end-to-end on the live stack and fixing surfaced bugs.

- [ ] **Step 1: Full stack up + admin password reset**

```bash
docker compose up -d
docker compose ps   # confirm 7 services healthy
docker exec -w /app lq-ai-api-1 python -m app.cli reset-admin-password \
  --email admin@lq.ai --password 'LQ-AI-smoke-test-Pw1!' --no-force-change
```

- [ ] **Step 2: Apply migrations 0022 + 0023 in the live container**

```bash
docker cp api/alembic/versions/0022_add_projects_is_sandbox.py lq-ai-api-1:/app/alembic/versions/
docker cp api/alembic/versions/0023_add_user_skills_slash_alias_and_forked_from.py lq-ai-api-1:/app/alembic/versions/
docker exec -w /app lq-ai-api-1 alembic upgrade head
```

- [ ] **Step 3: Run the full wave-d2 spec**

```bash
docker exec lq-ai-web-1 npx cypress run --spec cypress/e2e/wave-d2-skill-creator.cy.ts \
  --config video=false 2>&1 | tee /tmp/wave-d2-cypress-run-1.log
```

Expected: 6 tests run; baseline target ≥ 5/6 passing on the first integration run. Tests 4 + 5 (LLM-touching) are the most likely flake sources — they require ~30–60s wall time per LLM round-trip.

- [ ] **Step 4: Fix integration bugs surfaced**

Whatever the run discovers — wrong selectors, races, missing intercepts, viewport clipping, OpenWebUI auth pollution — fix at the source. Commit each fix atomically:

```bash
git commit -s -m "fix(web): <specific integration bug surfaced by wave-d2 live-run>"
```

- [ ] **Step 5: Re-run until baseline reached**

Re-run after each fix. Stop when 5/6 stable (or 6/6 best). Document any remaining flakes as DE-227+ in the wrap-up.

```bash
docker exec lq-ai-web-1 npx cypress run --spec cypress/e2e/wave-d2-skill-creator.cy.ts 2>&1 | tee /tmp/wave-d2-cypress-run-N.log
```

- [ ] **Step 6: Final commit summarizing the baseline**

```bash
git commit -s --allow-empty -m "test(web): wave-d2 live-run baseline reached — N/6 stable (Wave D.2)"
```


---

## Wave 9 — Documentation

### Task 9.1: Update `docs/api/backend-openapi.yaml`

**Files:**
- Modify: `docs/api/backend-openapi.yaml`

- [ ] **Step 1: Add new path entries**

Add to the `paths:` section:

```yaml
/skills/autocomplete:
  get:
    summary: Autocomplete skills for slash invocation
    parameters:
      - in: query
        name: q
        schema: { type: string }
        required: false
        description: Substring to match against slash_alias / slug / title.
      - in: query
        name: limit
        schema: { type: integer, minimum: 1, maximum: 25, default: 10 }
        required: false
    responses:
      '200':
        description: Ordered, resolver-aware matches.
        content:
          application/json:
            schema:
              type: object
              properties:
                results:
                  type: array
                  items:
                    $ref: '#/components/schemas/SkillAutocompleteItem'

/projects/sandbox/ensure:
  post:
    summary: Find-or-create the caller's try-it sandbox matter
    responses:
      '200':
        description: Sandbox matter already exists; idempotent return.
        content:
          application/json:
            schema: { $ref: '#/components/schemas/ProjectResponse' }
      '201':
        description: Newly created sandbox matter.
        content:
          application/json:
            schema: { $ref: '#/components/schemas/ProjectResponse' }

/user-skills/{skill_id}/versions:
  get:
    summary: Audit-log view of edits for a user-skill
    parameters:
      - in: path
        name: skill_id
        required: true
        schema: { type: string, format: uuid }
      - in: query
        name: limit
        schema: { type: integer, minimum: 1, maximum: 200, default: 50 }
    responses:
      '200':
        description: Versions (newest first).
        content:
          application/json:
            schema:
              type: object
              properties:
                items:
                  type: array
                  items: { $ref: '#/components/schemas/UserSkillVersionItem' }
      '403':
        description: Caller cannot access this skill.
      '404':
        description: Skill not found.
```

Extend the existing `/projects` GET path with `include_sandbox` and `only_sandbox` query params.

Extend `UserSkillCreate` request schema to include `slash_alias`, `forked_from`, `source_message_id` (nullable strings).

Extend `UserSkill` / `Skill` response schemas to include `slash_alias`, `forked_from` (nullable strings).

Add component schemas:

```yaml
SkillAutocompleteItem:
  type: object
  required: [slug, slash_alias, title, description, scope]
  properties:
    slug: { type: string }
    slash_alias: { type: string, nullable: true }
    title: { type: string }
    description: { type: string }
    scope: { type: string, enum: [user, team, builtin] }
    icon: { type: string, nullable: true }

UserSkillVersionItem:
  type: object
  properties:
    timestamp: { type: string, format: date-time }
    actor_user_id: { type: string, nullable: true }
    actor_email: { type: string, nullable: true }
    action: { type: string }
    version: { type: string, nullable: true }
    details: { type: object, nullable: true }
```

Add `is_sandbox: { type: boolean }` to the `ProjectResponse` schema (required, default false).

- [ ] **Step 2: Verify the schema-conformance test still passes**

```bash
docker exec -w /app lq-ai-api-1 pytest tests/test_openapi_wave_d2.py -v
```

- [ ] **Step 3: Commit**

```bash
git add docs/api/backend-openapi.yaml
git commit -s -m "docs(api): document Wave D.2 endpoints + extended schemas"
```

---

### Task 9.2: Update `docs/db-schema.md`

**Files:**
- Modify: `docs/db-schema.md`

- [ ] **Step 1: Add column documentation**

In the `projects` section, after the existing column list:

```markdown
### `projects.is_sandbox` (added in migration 0022)

Boolean. Default `FALSE`. When `TRUE`, the project is a per-user try-it sandbox
auto-created by `POST /api/v1/projects/sandbox/ensure`. Sandbox matters:

- Are excluded from the default `GET /projects` list (`?include_sandbox=true` to include)
- Are marked `non-billable` in cost aggregation
- Use `privileged=false` and no `minimum_inference_tier` enforcement
- Hold the reserved slug `__sandbox__` per user-active (uniqueness via existing partial index)

Wave E onboarding reuses this column.

### Index: `idx_projects_not_sandbox`

Partial index on `(owner_id, created_at)` where `is_sandbox = false AND archived_at IS NULL`.
Keeps the default matters-list query fast.
```

In the `user_skills` section:

```markdown
### `user_skills.slash_alias` (added in migration 0023)

Optional text. Format `^/[a-z0-9-]{1,32}$` (enforced via CHECK constraint).
When set, the skill can be invoked by typing the alias at the start of the
composer (Wave D.2 slash-invocation surface).

Uniqueness: per (`owner_user_id`, `slash_alias`) for active rows where
`scope = 'user'`; per (`owner_team_id`, `slash_alias`) for active rows where
`scope = 'team'`. Two partial unique indexes enforce this.

Users CAN intentionally shadow a built-in slash alias by setting the same
value (the resolver picks user > team > built-in).

### `user_skills.forked_from` (added in migration 0023)

Optional text. Documentary: the slug of the source skill if this skill was
forked. Not a foreign key (built-in skills are filesystem-canonical per
ADR 0004). Surfaced in the Versions tab's audit `details`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/db-schema.md
git commit -s -m "docs(db): document is_sandbox + slash_alias + forked_from columns (Wave D.2)"
```

---

### Task 9.3: Update `docs/skill-authoring-guide.md`

**Files:**
- Modify: `docs/skill-authoring-guide.md`

- [ ] **Step 1: Document the `slash_alias` frontmatter field**

In the "SKILL.md frontmatter" section, after `trigger_examples:`:

```markdown
- **`lq_ai.slash_alias`** (optional) — a `/slash` invocation alias for the
  composer slash-invocation surface (Wave D.2). Format: `^/[a-z0-9-]{1,32}$`.
  Used in addition to `trigger_examples` — the slash alias is the *explicit*
  invocation, while `trigger_examples` drive the *implicit* attach-on-chat
  matcher.

  Uniqueness: per-scope (one alias per user-skill in a user's collection;
  one per team-skill in a team's collection). User-scope aliases shadow
  team and built-in aliases per the user > team > built-in resolver.

  Best practice: pick a short, memorable token. `/nda` is better than
  `/nda-review`. Do not duplicate the slug if a shorter alias is available
  — the slug is automatic; the alias is for fluency.
```

- [ ] **Step 2: Commit**

```bash
git add docs/skill-authoring-guide.md
git commit -s -m "docs(skills): document slash_alias frontmatter field (Wave D.2)"
```


---

## Dependency graph + parallelization notes

If executed sequentially by a single developer, the wave order above is the natural path. If subagent-driven (multiple workers), useful parallel splits:

- **Within Wave 2** — Tasks 2.1, 2.2/2.3 (sandbox suite), 2.4 (user-skills), 2.5 (autocomplete), 2.6 (versions endpoint), 2.7 (slash fallback + OpenAPI) can all run in parallel after Wave 1 completes. They touch different endpoint groups.
- **Waves 4, 5, 6, 7** — All depend on Wave 3 (shared components) and Wave 2 (backend contracts). After Wave 3 closes, Waves 4–7 can run in parallel. They touch different routes/components with minimal overlap. The one shared file is `ChatPanel.svelte` (Wave 7 only).
- **Wave 8 (Cypress)** — Tasks 8.1–8.4 author the spec; Task 8.5 is the live-run. 8.1–8.4 can interleave with the implementation waves, but 8.5 must come last (it requires the full system stable).

A reasonable parallel batching:

```
Wave 1 (schema) — sequential, fast.
↓
Wave 2 (six parallel tasks on backend endpoints).
↓
Wave 3 (four parallel tasks on shared frontend components).
↓
Waves 4 + 5 + 6 + 7 — parallel; coordinate only at ChatPanel touchpoints.
↓
Wave 8 (Cypress spec author tasks 8.1–8.4 in parallel, then 8.5 live-run).
↓
Wave 9 (docs — three parallel tasks).
```

---

## Goal-backward verification

Per the wave-D.1 cycle's `gsd-plan-checker` convention: verify the plan delivers the goal by walking backward from each design decision.

| Design decision (from spec §3) | Plan delivers via | Verification check |
|---|---|---|
| D1 — One wave, atomic | Single PLAN.md; no D.2.1/D.2.2 split | Plan has one set of waves; no split markers |
| D2 — Composer popover slash | Task 3.3 (SlashPopover) + Task 7.1 (ChatPanel wiring) + Task 2.5 (autocomplete endpoint) | Tests in Task 3.3 + 7.1 cover the popover behavior; Cypress Test 4 covers end-to-end |
| D3 — Capture inline + toggleable | Tasks 5.1 (preference), 5.3 (overflow menu + inline), 5.4 (settings entry) | Cypress Test 1 covers inline; manual verification in 5.3 covers overflow |
| D4 — projects.is_sandbox column | Task 1.1 (migration) + Task 2.2 (sandbox/ensure) + Task 2.3 (filters) | Integration tests in 2.2 + 2.3; Cypress Test 5 covers sandbox round-trip |
| D5 — Thin capture modal | Task 5.2 (CaptureSkillModal) | Vitest in 5.2; Cypress Test 1 covers end-to-end |
| D6 — Single-page wizard sections | Tasks 4.1 (SkillWizardSection) + 4.2 (SkillWizard) | Vitest in 4.2; Cypress Test 2 covers end-to-end |
| D7 — Versions = audit-log view | Task 2.6 (endpoint) + Task 6.2 (SkillVersionsTab) | Integration tests in 2.6; Cypress Test 6 covers detail-page render |
| D8 — Fork via frontend pre-populate | Task 4.3 (`?fork=` handling) + Task 4.4 (fork button) | Cypress Test 3 covers end-to-end forking with `forked_from` set |
| D9 — Slash composer separate-row pill | Task 3.2 (AttachedSkillPill) + Task 7.1 (composer integration) | Cypress Test 4 asserts pill renders + composer text cleared |

**Spec sections coverage check:**

- **§4 Architecture** — Tasks 1.1, 1.2 land the schema beats; Wave 2 lands the API beats; Waves 4–7 land the frontend beats.
- **§5 Components** — Every ★ net-new file in §5 has a corresponding task; every ⟳ modified file has a corresponding task.
- **§6 Data flows** — Mode A → Wave 5 + Cypress Test 1; Mode B → Wave 4 + Test 2; Mode C → Wave 4 + Test 3; slash → Wave 7 + Test 4; try-it → Wave 6 + Test 5; Versions → Wave 6 + Test 6.
- **§7 Error handling** — Slash collisions handled in Task 2.4 (server) + Task 4.2 (form); sandbox concurrency in Task 2.2; capture session-expiry in Task 5.2; fork 404 in Task 4.3.
- **§8 Testing** — Wave 8 lists exactly the 6 Cypress scenarios from §8. Vitest specs match the §8 list (SkillWizard, CaptureSkillModal, SlashPopover, SkillVersionsTab, AttachedSkillPill).
- **§9 DE-XXX** — All five DE candidates from spec §9 are explicitly out-of-scope; no plan task implements them.
- **§10 Risks** — Slash popover positioning + sandbox migration + ADR 0007 slip + Cypress flake all have mitigations in this plan: manual verification step at end of 7.1; migration 0022 is backfill-safe (default false); ADR 0007 amendment is out-of-scope; 8.5 lives-runs the flake-prone tests.

---

## Self-review checklist (writing-plans skill protocol)

Run after the plan is written; fix anything that fails.

1. **Spec coverage** — Every numbered decision (D1–D9) and every spec section maps to a task. ✅ (see Goal-backward table above)
2. **Placeholder scan** — Search for `TBD`, `TODO`, `XXX`, `???`, "implement later", "add appropriate error handling", "similar to Task N". Fix inline.
3. **Type/method consistency** — `SkillAutocompleteItem`, `UserSkillVersion`, `AttachedSkillPill` props, `onSelect` / `onDismiss` callbacks, `slash_alias` field name — all used consistently across tasks.
4. **File paths** — Every reference to a backend or frontend file path matches the codebase. Reconnaissance confirmed paths exist (or are net-new with the right parent directory).

---

## Out-of-band tasks (queued for separate planning, not in this wave)

These are referenced by the spec but explicitly NOT in this plan:

- ADR 0007 amendment for the Q1 dual-invocation model — separate planning task per session handoff.
- `CONTRIBUTING.md` ported-skill attestation paragraph template — gates on Wave G.
- `NOTICES.md` authoring — gates on Wave G first port.
- DE-222..226 deferrals — to be added to PRD §9 by a separate small docs task after Wave D.2 closes.

---

*End of plan. Next step is execution: pick subagent-driven-development (recommended) or executing-plans.*

