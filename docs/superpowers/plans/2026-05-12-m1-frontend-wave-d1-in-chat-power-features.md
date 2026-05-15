# Wave D.1 — In-chat power features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the four in-chat power features from M1 spec §8.1 — Enhance Prompt expansion, KB attach modal, Tier-floor refusal block, Receipts drawer — plus the backend additions that support them (messages.kind discriminator, project↔KB junction + endpoints, tier-floor override endpoint, replay-at-read receipts endpoint, KB-retrieval audit logging).

**Architecture:** Frontend-first slice with three new backend endpoints + two Alembic migrations. Receipts uses replay-at-read (no materialized table) over `messages`, `inference_routing_log`, `audit_log` sources. Tier-floor override gates on admin role (per M1 RBAC). Refusal turns persist as `kind=refusal` messages so they show in Receipts and cross-link to audit. Visual composition validated during brainstorming: matter rail (left, unchanged) + ChatPanel with refusal-bubble variant + Receipts drawer (right, 240px, toggleable).

**Tech Stack:** SvelteKit (frontend), FastAPI + SQLAlchemy 2.0 async + Alembic (backend), Pydantic v2, Vitest (frontend unit), Cypress (E2E), pytest (backend integration).

**Decisions made before this plan (anchored in spec):**
1. `messages.kind` = dedicated NOT NULL column with CHECK + index (over JSONB metadata or hybrid).
2. Receipts = replay-at-read (over materialized table; M1 chats are small).
3. Receipts toggle UI = right-side drawer, 240px, persists per-chat in localStorage.
4. Tier-floor override = admin-role gated for M1 (per-user `override_tier_floor` permission deferred to v1.1+).
5. Skill Creator (§7.2) deferred to Wave D.2 — NOT in this plan.

**Out of scope (do not extend D.1 to cover):**
- Skill Creator wizard + try-it (`/lq-ai/skills/new`) → Wave D.2.
- `/lq-ai/knowledge` standalone browser surface → Wave F.
- `/lq-ai/saved-prompts` surface → Wave F.
- Outputs panel / Citation Engine UI → Wave F.
- Per-user `override_tier_floor` permission grant infrastructure → v1.1+.
- Materialized `chat_receipts` table → v1.1+ if replay-at-read latency degrades.

**Conventions (carry through every commit):**
- Conventional Commits: `feat(api|web)`, `fix(api|web)`, `test(api|web)`, `refactor(api|web)`, `docs(spec|plan)`.
- DCO sign-off mandatory: `git commit -s`.
- Co-author trailer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Atomic commits: one task = one commit (some tasks ship 2 commits when code + tests can't co-locate cleanly).
- Push every commit. Never `--no-verify`.
- Verify after each commit: `git log -1 --format=fuller` shows `Signed-off-by:` + `Co-Authored-By:`.

**Pre-flight (before first task):**
```bash
cd /Users/kevinkeller/Desktop/lq-ai
git status -sb                     # expect: clean on kk/main/Frontend_Design
git log -1 --oneline               # expect: d220fa5 docs(spec): Wave D.1 ...
docker compose ps                  # expect: 7 services healthy
cd web && npm run test:frontend -- --run 2>&1 | tail -3
                                   # expect: Tests 174 passed (174)
docker compose exec -w /app api pytest tests/ -m integration -q 2>&1 | tail -3
                                   # expect: 486 passed, 1 skipped, 0 failed
```

---

## File Structure

**New backend files:**

```
api/alembic/versions/0020_messages_kind_discriminator.py    (migration)
api/alembic/versions/0021_project_knowledge_bases_junction.py (migration)
api/app/models/project_knowledge_base.py                    (model)
api/app/api/inference_override.py                           (POST /override-tier-floor)
api/app/api/chat_receipts.py                                (GET receipts + export)
api/tests/api/test_messages_kind.py
api/tests/api/test_project_knowledge_bases.py
api/tests/api/test_inference_override.py
api/tests/api/test_chat_receipts.py
api/tests/api/test_kb_retrieval_audit.py
```

**New frontend files:**

```
web/src/lib/lq-ai/api/projectKnowledgeBases.ts
web/src/lib/lq-ai/api/inferenceOverride.ts
web/src/lib/lq-ai/api/receipts.ts
web/src/lib/lq-ai/components/AttachKBModal.svelte
web/src/lib/lq-ai/components/RefusalMessageBubble.svelte
web/src/lib/lq-ai/components/TierFloorOverrideModal.svelte
web/src/lib/lq-ai/components/ReceiptsDrawer.svelte
web/src/lib/lq-ai/components/ReceiptsList.svelte
web/src/lib/lq-ai/lib/receiptsExport.ts                     (JSONL serializer)
web/src/lib/lq-ai/__tests__/AttachKBModal.test.ts
web/src/lib/lq-ai/__tests__/RefusalMessageBubble.test.ts
web/src/lib/lq-ai/__tests__/TierFloorOverrideModal.test.ts
web/src/lib/lq-ai/__tests__/ReceiptsDrawer.test.ts
web/src/lib/lq-ai/__tests__/ReceiptsList.test.ts
web/src/lib/lq-ai/__tests__/receiptsExport.test.ts
web/src/lib/lq-ai/__tests__/project-knowledge-bases-api.test.ts
web/src/lib/lq-ai/__tests__/inference-override-api.test.ts
web/src/lib/lq-ai/__tests__/receipts-api.test.ts
web/cypress/e2e/wave-d1-power-features.cy.ts
```

**Modified backend files:**

```
api/app/models/chat.py                  (add kind column to Message)
api/app/api/projects.py                 (add POST/DELETE /knowledge-bases routes)
api/app/api/__init__.py                 (register inference_override + chat_receipts routers)
api/app/api/chats.py                    (write kind='ai' on assistant replies; write kind='refusal' on tier-mismatch refusal; existing flows pass kind='user')
api/app/knowledge/retrieval.py          (audit-row write per hybrid_search result for receipts)
```

**Modified frontend files:**

```
web/src/lib/lq-ai/components/MessageBubble.svelte    (dispatch to RefusalMessageBubble on kind='refusal')
web/src/lib/lq-ai/components/ChatPanel.svelte        (receipts drawer slot + 📜 toggle + 📎 button → AttachKBModal)
web/src/lib/lq-ai/components/Composer.svelte         (⌘E enhance hotkey + edge cases — only if T20 audit finds gaps)
web/src/lib/lq-ai/components/MatterRailKnowledge.svelte    (+ Attach KB → AttachKBModal)
web/src/lib/lq-ai/types/Message.ts                   (add kind field to Message type if not already there)
web/src/routes/lq-ai/settings/appearance/+page.svelte (auto-enhance toggle — only if T20 audit finds gap)
```

---

## Task ordering rationale

Schema-first → endpoints → API clients → components → integration → E2E. Tasks 1-7 are backend (most ship independently); 8-10 are frontend API clients (depend on 3, 4, 5); 11-12 are KB attach (depend on 3, 8); 13-15 are refusal block (depend on 1, 4, 9); 16-19 are receipts (depend on 5, 7, 10); 20 is Enhance Prompt audit-and-delta (independent); 21 is E2E (depends on everything).

Each backend task ships its own tests; each frontend task ships its own Vitest unit suite. Cypress E2E lands last and exercises end-to-end flows.

| # | Task | Depends on | Est. commits |
|---|---|---|---|
| 1 | Migration 0020: `messages.kind` discriminator + backfill | — | 1 |
| 2 | Migration 0021: `project_knowledge_bases` junction + model | — | 1 |
| 3 | Backend: `POST/DELETE /api/v1/projects/{id}/knowledge-bases` | 2 | 1 |
| 4 | Backend: `POST /api/v1/inference/override-tier-floor` | 1 | 1 |
| 5 | Backend: `GET /api/v1/chats/{id}/receipts` (replay-at-read) | 1 | 1 |
| 6 | Backend: `GET /api/v1/chats/{id}/receipts/export.jsonl` | 5 | 1 |
| 7 | Backend: KB retrieval audit-row write in `hybrid_search` call site | — | 1 |
| 8 | Frontend API client: `projectKnowledgeBases.ts` | 3 | 1 |
| 9 | Frontend API client: `inferenceOverride.ts` | 4 | 1 |
| 10 | Frontend API client: `receipts.ts` | 5 | 1 |
| 11 | Component: `AttachKBModal.svelte` | 8 | 1 |
| 12 | Wire `AttachKBModal` into Composer 📎 + MatterRailKnowledge | 11 | 1 |
| 13 | Component: `RefusalMessageBubble.svelte` | — | 1 |
| 14 | Component: `TierFloorOverrideModal.svelte` | 9 | 1 |
| 15 | `MessageBubble` dispatch on `kind='refusal'` + integration | 13, 14 | 1 |
| 16 | `receiptsExport.ts` JSONL serializer | — | 1 |
| 17 | Component: `ReceiptsList.svelte` | 10 | 1 |
| 18 | Component: `ReceiptsDrawer.svelte` | 17, 16 | 1 |
| 19 | Wire `ReceiptsDrawer` into ChatPanel + 📜 toggle | 18 | 1 |
| 20 | Enhance Prompt audit-and-delta | — | 1-3 |
| 21 | Cypress E2E: `wave-d1-power-features.cy.ts` | everything | 1 |

**Total estimated commits: 22-24.**

---

## Task 1: Migration 0020 — `messages.kind` discriminator

**Files:**
- Create: `api/alembic/versions/0020_messages_kind_discriminator.py`
- Modify: `api/app/models/chat.py` (add `kind` column to Message)
- Create: `api/tests/api/test_messages_kind.py`

**Background:**
Adds `messages.kind TEXT NOT NULL DEFAULT 'user'` with `CHECK (kind IN ('user','ai','refusal','system'))` + index. Backfills from existing `role` column. The `kind` column is the LQ.AI-specific message discriminator — distinct from `role` (which uses OpenAI conventions: user/assistant/system/tool). Refusal turns will set `kind='refusal'` with `role='assistant'` (since the assistant "spoke" the refusal).

**Mapping rule:** `assistant` → `ai`, `user` → `user`, `system` → `system`, `tool` → `system` (no `tool` kind in spec). All existing rows backfill via this rule.

- [ ] **Step 1: Write the migration**

Create `api/alembic/versions/0020_messages_kind_discriminator.py`:

```python
"""messages.kind discriminator column

Revision ID: 0020_messages_kind
Revises: 0019_user_preferences_extension
Create Date: 2026-05-12

Adds a LQ.AI-specific message classification column `messages.kind` with
CHECK constraint over {user, ai, refusal, system}. Distinct from the
OpenAI-style `messages.role` column. Backfill rule:
  role='assistant' -> kind='ai'
  role='user'      -> kind='user'
  role='system'    -> kind='system'
  role='tool'      -> kind='system'
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_messages_kind"
down_revision = "0019_user_preferences_extension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )
    op.create_check_constraint(
        "chk_messages_kind",
        "messages",
        "kind IN ('user', 'ai', 'refusal', 'system')",
    )
    op.execute(
        """
        UPDATE messages SET kind = CASE
            WHEN role = 'assistant' THEN 'ai'
            WHEN role = 'user'      THEN 'user'
            WHEN role = 'system'    THEN 'system'
            WHEN role = 'tool'      THEN 'system'
            ELSE 'user'
        END
        """
    )
    op.create_index("idx_messages_kind", "messages", ["kind"])


def downgrade() -> None:
    op.drop_index("idx_messages_kind", table_name="messages")
    op.drop_constraint("chk_messages_kind", "messages", type_="check")
    op.drop_column("messages", "kind")
```

- [ ] **Step 2: Update Message model**

Modify `api/app/models/chat.py`. In the `Message` class `__table_args__` add the new CHECK constraint and in the column section add `kind`:

```python
# In __table_args__ tuple, ADD this CheckConstraint:
CheckConstraint(
    "kind IN ('user', 'ai', 'refusal', 'system')",
    name="chk_messages_kind",
),

# In the columns section, ADD after the `role` column:
kind: Mapped[str] = mapped_column(
    Text,
    nullable=False,
    server_default=text("'user'"),
)
```

- [ ] **Step 3: Write the failing test**

Create `api/tests/api/test_messages_kind.py`:

```python
"""Migration 0020 — messages.kind discriminator."""

import pytest
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_kind_column_exists_with_check_constraint(db_session: AsyncSession):
    """Column exists and CHECK rejects bad values."""
    result = await db_session.execute(
        text("SELECT column_name, data_type, is_nullable "
             "FROM information_schema.columns "
             "WHERE table_name='messages' AND column_name='kind'")
    )
    row = result.first()
    assert row is not None, "messages.kind column should exist"
    assert row.data_type == "text"
    assert row.is_nullable == "NO"

    with pytest.raises(Exception):  # CheckConstraintViolation
        await db_session.execute(
            text("INSERT INTO messages (chat_id, role, kind, content) "
                 "VALUES (:cid, 'user', 'bogus', 'x')"),
            {"cid": str(uuid.uuid4())}
        )
        await db_session.commit()
    await db_session.rollback()


async def test_kind_index_exists(db_session: AsyncSession):
    result = await db_session.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname='idx_messages_kind'")
    )
    assert result.scalar() == 1


async def test_kind_backfill_rule(db_session: AsyncSession, sample_chat_id):
    """Existing messages backfilled: assistant->ai, tool->system."""
    # Insert via raw SQL bypassing the new model defaults
    await db_session.execute(
        text("INSERT INTO messages (id, chat_id, role, kind, content) "
             "VALUES (gen_random_uuid(), :cid, 'assistant', 'ai', 'hi')"),
        {"cid": str(sample_chat_id)}
    )
    await db_session.commit()
    result = await db_session.execute(
        text("SELECT kind FROM messages WHERE role='assistant' LIMIT 1")
    )
    assert result.scalar() == "ai"
```

- [ ] **Step 4: Apply migration + run tests**

```bash
cd /Users/kevinkeller/Desktop/lq-ai
docker compose exec -w /app api alembic upgrade head 2>&1 | tail -5
docker compose exec -w /app api pytest tests/api/test_messages_kind.py -v 2>&1 | tail -15
```

Expected: migration applies cleanly; all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/alembic/versions/0020_messages_kind_discriminator.py \
        api/app/models/chat.py \
        api/tests/api/test_messages_kind.py
git commit -s -m "$(cat <<'EOF'
feat(api): migration 0020 — messages.kind discriminator

Adds LQ.AI-specific message classification column over
{user, ai, refusal, system} with CHECK + idx. Backfills from
existing role column (assistant->ai, tool->system). Distinct from
OpenAI-style role; refusal turns will set kind='refusal' with
role='assistant'.

Required for: tier-floor refusal block (D.1 §3.4), receipts filtering
(D.1 §3.5).

Refs Wave D.1 plan T1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 2: Migration 0021 — `project_knowledge_bases` junction

**Files:**
- Create: `api/alembic/versions/0021_project_knowledge_bases_junction.py`
- Create: `api/app/models/project_knowledge_base.py`

**Background:**
The matter↔KB attach modal needs a junction table. No such table exists yet (verified). Composite PK on `(project_id, knowledge_base_id)`; both FKs CASCADE on delete; `attached_at` timestamp for ordering in receipts.

- [ ] **Step 1: Write the migration**

Create `api/alembic/versions/0021_project_knowledge_bases_junction.py`:

```python
"""project_knowledge_bases junction table

Revision ID: 0021_project_kb
Revises: 0020_messages_kind
Create Date: 2026-05-12

Junction for matter (project) <-> knowledge_base many-to-many.
Composite PK; FK CASCADE on either side; attached_at + attached_by
for audit ordering.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0021_project_kb"
down_revision = "0020_messages_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_knowledge_bases",
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("attached_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            ondelete="CASCADE",
            name="fk_pkb_project_id",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"],
            ondelete="CASCADE",
            name="fk_pkb_kb_id",
        ),
        sa.ForeignKeyConstraint(
            ["attached_by_user_id"], ["users.id"],
            ondelete="SET NULL",
            name="fk_pkb_attached_by",
        ),
        sa.PrimaryKeyConstraint("project_id", "knowledge_base_id"),
    )
    op.create_index(
        "idx_pkb_kb_id", "project_knowledge_bases", ["knowledge_base_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_pkb_kb_id", table_name="project_knowledge_bases")
    op.drop_table("project_knowledge_bases")
```

- [ ] **Step 2: Write the model**

Create `api/app/models/project_knowledge_base.py`:

```python
"""ProjectKnowledgeBase — matter <-> KB junction.

Composite PK on (project_id, knowledge_base_id). Both FKs CASCADE so
deleting a project or KB removes the attachment row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectKnowledgeBase(Base):
    __tablename__ = "project_knowledge_bases"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_pkb_project_id"),
        primary_key=True,
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE", name="fk_pkb_kb_id"),
        primary_key=True,
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    attached_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_pkb_attached_by"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectKnowledgeBase project_id={self.project_id} "
            f"kb_id={self.knowledge_base_id}>"
        )
```

- [ ] **Step 3: Apply migration**

```bash
docker compose exec -w /app api alembic upgrade head 2>&1 | tail -3
docker compose exec -w /app api python -c "from app.models.project_knowledge_base import ProjectKnowledgeBase; print('OK')" 2>&1
```

Expected: migration applies; import succeeds.

- [ ] **Step 4: Quick smoke test in shell**

```bash
docker compose exec -w /app api python -c "
from sqlalchemy import inspect
from app.db.session import sync_engine
ins = inspect(sync_engine)
assert 'project_knowledge_bases' in ins.get_table_names(), 'table missing'
print('OK: project_knowledge_bases exists')
"
```

Expected: `OK: project_knowledge_bases exists`.

- [ ] **Step 5: Commit**

```bash
git add api/alembic/versions/0021_project_knowledge_bases_junction.py \
        api/app/models/project_knowledge_base.py
git commit -s -m "$(cat <<'EOF'
feat(api): migration 0021 — project_knowledge_bases junction

Adds matter <-> KB many-to-many junction with composite PK,
CASCADE FKs, and attached_at + attached_by_user_id for audit
ordering. Required for KB attach modal (D.1 §3.3).

Refs Wave D.1 plan T2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 3: Backend — `POST/DELETE /api/v1/projects/{id}/knowledge-bases`

**Files:**
- Modify: `api/app/api/projects.py` (add 2 new routes near existing /skills routes)
- Create: `api/tests/api/test_project_knowledge_bases.py`

**Background:**
Mirrors the existing `POST/DELETE /api/v1/projects/{id}/files` and `/skills` pattern in `projects.py`. Audit actions `project.knowledge_base_attached` / `project.knowledge_base_detached`. Owner-only authorization via existing `require_project_access` pattern.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/api/test_project_knowledge_bases.py`:

```python
"""POST/DELETE /api/v1/projects/{id}/knowledge-bases."""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.project_knowledge_base import ProjectKnowledgeBase

pytestmark = pytest.mark.integration


async def test_attach_kb_to_project_creates_junction(
    client: AsyncClient, auth_headers, db_session, sample_project, sample_kb
):
    response = await client.post(
        f"/api/v1/projects/{sample_project.id}/knowledge-bases",
        json={"knowledge_base_id": str(sample_kb.id)},
        headers=auth_headers,
    )
    assert response.status_code == 200
    project = response.json()
    assert any(kb["id"] == str(sample_kb.id) for kb in project["knowledge_bases"])

    pkb = await db_session.execute(
        select(ProjectKnowledgeBase).where(
            ProjectKnowledgeBase.project_id == sample_project.id,
            ProjectKnowledgeBase.knowledge_base_id == sample_kb.id,
        )
    )
    assert pkb.scalar_one_or_none() is not None


async def test_attach_kb_writes_audit_row(
    client, auth_headers, db_session, sample_project, sample_kb, sample_user
):
    await client.post(
        f"/api/v1/projects/{sample_project.id}/knowledge-bases",
        json={"knowledge_base_id": str(sample_kb.id)},
        headers=auth_headers,
    )
    audit = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "project.knowledge_base_attached",
            AuditLog.user_id == sample_user.id,
        )
    )
    row = audit.scalar_one_or_none()
    assert row is not None
    assert row.resource_id == sample_project.id


async def test_detach_kb_removes_junction(
    client, auth_headers, db_session, sample_project, attached_kb
):
    response = await client.delete(
        f"/api/v1/projects/{sample_project.id}/knowledge-bases/{attached_kb.id}",
        headers=auth_headers,
    )
    assert response.status_code == 204
    result = await db_session.execute(
        select(ProjectKnowledgeBase).where(
            ProjectKnowledgeBase.project_id == sample_project.id,
            ProjectKnowledgeBase.knowledge_base_id == attached_kb.id,
        )
    )
    assert result.scalar_one_or_none() is None


async def test_attach_kb_nonexistent_kb_returns_404(
    client, auth_headers, sample_project
):
    fake_kb = uuid.uuid4()
    response = await client.post(
        f"/api/v1/projects/{sample_project.id}/knowledge-bases",
        json={"knowledge_base_id": str(fake_kb)},
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_attach_kb_non_owner_returns_403(
    client, other_user_auth_headers, sample_project, sample_kb
):
    response = await client.post(
        f"/api/v1/projects/{sample_project.id}/knowledge-bases",
        json={"knowledge_base_id": str(sample_kb.id)},
        headers=other_user_auth_headers,
    )
    assert response.status_code in (403, 404)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -w /app api pytest tests/api/test_project_knowledge_bases.py -v 2>&1 | tail -15
```

Expected: 5 failures with 404 or 405 (route doesn't exist yet).

- [ ] **Step 3: Implement the routes in `projects.py`**

Modify `api/app/api/projects.py` — add after the existing `/skills` DELETE route (around line 730):

```python
class ProjectKnowledgeBaseAttachBody(BaseModel):
    """``POST /api/v1/projects/{id}/knowledge-bases`` body."""

    knowledge_base_id: uuid.UUID


@router.post(
    "/{project_id}/knowledge-bases",
    response_model=ProjectResponse,
    summary="Attach a knowledge base to a matter",
    description=(
        "Attaches a KB to a matter via the project_knowledge_bases "
        "junction. Owner-only. Idempotent — re-attaching is a no-op "
        "with 200. Audit action: project.knowledge_base_attached."
    ),
)
async def attach_knowledge_base(
    project_id: uuid.UUID,
    payload: ProjectKnowledgeBaseAttachBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    project = await require_project_access(db, project_id, current_user)
    kb = await db.get(KnowledgeBase, payload.knowledge_base_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")

    existing = await db.execute(
        select(ProjectKnowledgeBase).where(
            ProjectKnowledgeBase.project_id == project_id,
            ProjectKnowledgeBase.knowledge_base_id == payload.knowledge_base_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(ProjectKnowledgeBase(
            project_id=project_id,
            knowledge_base_id=payload.knowledge_base_id,
            attached_by_user_id=current_user.id,
        ))
        await audit_action(
            db,
            request=request,
            user=current_user,
            action="project.knowledge_base_attached",
            resource_type="project",
            resource_id=project_id,
            project=project,
            details={"knowledge_base_id": str(payload.knowledge_base_id)},
        )
        await db.commit()
        await db.refresh(project)

    return await _build_project_response(db, project)


@router.delete(
    "/{project_id}/knowledge-bases/{kb_id}",
    status_code=204,
    summary="Detach a knowledge base from a matter",
    description=(
        "Detaches a KB from a matter. Owner-only. Idempotent — "
        "detaching a non-attached KB returns 204. "
        "Audit action: project.knowledge_base_detached."
    ),
)
async def detach_knowledge_base(
    project_id: uuid.UUID,
    kb_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await require_project_access(db, project_id, current_user)
    result = await db.execute(
        select(ProjectKnowledgeBase).where(
            ProjectKnowledgeBase.project_id == project_id,
            ProjectKnowledgeBase.knowledge_base_id == kb_id,
        )
    )
    pkb = result.scalar_one_or_none()
    if pkb is not None:
        await db.delete(pkb)
        await audit_action(
            db,
            request=request,
            user=current_user,
            action="project.knowledge_base_detached",
            resource_type="project",
            resource_id=project_id,
            project=project,
            details={"knowledge_base_id": str(kb_id)},
        )
        await db.commit()
```

Also: import `ProjectKnowledgeBase` and `KnowledgeBase` at the top of the file (and add `knowledge_bases: list[KnowledgeBaseSummary]` to `ProjectResponse` schema + `_build_project_response` if not already present).

- [ ] **Step 4: Re-run tests**

```bash
docker compose exec -w /app api pytest tests/api/test_project_knowledge_bases.py -v 2>&1 | tail -15
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/app/api/projects.py api/tests/api/test_project_knowledge_bases.py
git commit -s -m "$(cat <<'EOF'
feat(api): POST/DELETE /api/v1/projects/{id}/knowledge-bases

Adds matter <-> KB attach/detach endpoints mirroring the existing
/files and /skills attach pattern. Owner-only via require_project_
access. Idempotent. Audit actions project.knowledge_base_attached /
detached.

Refs Wave D.1 plan T3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 4: Backend — `POST /api/v1/inference/override-tier-floor`

**Files:**
- Create: `api/app/api/inference_override.py`
- Modify: `api/app/api/__init__.py` (register router)
- Create: `api/tests/api/test_inference_override.py`

**Background:**
Body: `{message_id: UUID, reason: str (10..500 chars)}`. Verifies caller has admin role (M1 simplification — fine-grained `override_tier_floor` permission deferred to v1.1+). Loads the refusal message, re-runs the original prompt with `tier_floor=None`, writes a new `kind='ai'` message + audit row.

**Implementation note:** for M1, the re-run logic delegates to the existing chat handler's gateway-call code path with an `override_tier_floor=True` flag. If that code path doesn't accept the flag yet, this task ALSO threads it through. Verify during implementation.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/api/test_inference_override.py`:

```python
"""POST /api/v1/inference/override-tier-floor — admin-gated re-run."""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.chat import Message

pytestmark = pytest.mark.integration


async def test_override_admin_succeeds_creates_ai_message(
    client: AsyncClient, admin_auth_headers, sample_refusal_message, db_session
):
    response = await client.post(
        "/api/v1/inference/override-tier-floor",
        json={
            "message_id": str(sample_refusal_message.id),
            "reason": "Urgent client request — risk-accepted by partner",
        },
        headers=admin_auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ai_message"]["kind"] == "ai"
    assert body["ai_message"]["chat_id"] == str(sample_refusal_message.chat_id)


async def test_override_member_returns_403(
    client, member_auth_headers, sample_refusal_message
):
    response = await client.post(
        "/api/v1/inference/override-tier-floor",
        json={
            "message_id": str(sample_refusal_message.id),
            "reason": "Trying to override",
        },
        headers=member_auth_headers,
    )
    assert response.status_code == 403


async def test_override_writes_audit_row_with_reason(
    client, admin_auth_headers, sample_refusal_message, db_session, admin_user
):
    reason = "Urgent client request — risk-accepted by partner"
    await client.post(
        "/api/v1/inference/override-tier-floor",
        json={"message_id": str(sample_refusal_message.id), "reason": reason},
        headers=admin_auth_headers,
    )
    audit = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "inference.tier_floor_overridden",
            AuditLog.user_id == admin_user.id,
        )
    )
    row = audit.scalar_one()
    assert row.details["reason"] == reason
    assert row.resource_id == sample_refusal_message.id


async def test_override_non_refusal_message_returns_404(
    client, admin_auth_headers, sample_ai_message
):
    """Override against a kind=ai message must fail."""
    response = await client.post(
        "/api/v1/inference/override-tier-floor",
        json={
            "message_id": str(sample_ai_message.id),
            "reason": "Test reason 10+ chars",
        },
        headers=admin_auth_headers,
    )
    assert response.status_code == 404


async def test_override_short_reason_returns_422(
    client, admin_auth_headers, sample_refusal_message
):
    """Reason must be 10..500 chars."""
    response = await client.post(
        "/api/v1/inference/override-tier-floor",
        json={"message_id": str(sample_refusal_message.id), "reason": "short"},
        headers=admin_auth_headers,
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -w /app api pytest tests/api/test_inference_override.py -v 2>&1 | tail -10
```

Expected: 5 failures (route doesn't exist).

- [ ] **Step 3: Implement the endpoint**

Create `api/app/api/inference_override.py`:

```python
"""POST /api/v1/inference/override-tier-floor.

Admin-only re-run of a refused inference with the tier-floor lifted
for this one turn. Logs the override + reason to audit_log.

Per Wave D.1 plan T4. M1 binds to admin role; per-user
override_tier_floor permission is a v1.1+ candidate.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.audit import audit_action
from app.models.chat import Chat, Message
from app.models.user import User
from app.schemas.message import MessageResponse

router = APIRouter(prefix="/inference", tags=["inference"])


class OverrideRequest(BaseModel):
    message_id: uuid.UUID
    reason: Annotated[str, Field(min_length=10, max_length=500)]


class OverrideResponse(BaseModel):
    ai_message: MessageResponse
    routing_log_id: uuid.UUID


@router.post(
    "/override-tier-floor",
    response_model=OverrideResponse,
    summary="Override a tier-floor refusal for one turn (admin only)",
)
async def override_tier_floor(
    payload: OverrideRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OverrideResponse:
    if current_user.role != "admin":
        raise HTTPException(
            403,
            "Tier-floor override requires admin role (M1)."
        )

    refusal = await db.get(Message, payload.message_id)
    if refusal is None or refusal.kind != "refusal":
        raise HTTPException(404, "Refusal message not found")

    chat = await db.get(Chat, refusal.chat_id)
    if chat is None:
        raise HTTPException(404, "Chat not found")

    # Re-run inference with tier_floor=None for this turn.
    # The original user prompt is the message immediately preceding
    # the refusal (kind='user'). Look it up by chat + ordering.
    user_msg_result = await db.execute(
        select(Message)
        .where(Message.chat_id == refusal.chat_id)
        .where(Message.kind == "user")
        .where(Message.created_at < refusal.created_at)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    user_msg = user_msg_result.scalar_one_or_none()
    if user_msg is None:
        raise HTTPException(409, "No preceding user message found")

    # Delegate to the existing inference re-run helper. This helper
    # lives in api/app/api/chats.py — verify name during implementation
    # and adjust import. The helper writes the new kind='ai' message
    # and the inference_routing_log row, and returns (message, log_id).
    from app.api.chats import run_inference_override  # noqa: PLC0415

    ai_message, routing_log_id = await run_inference_override(
        db=db,
        chat=chat,
        user_msg=user_msg,
        refusal_msg=refusal,
        override_reason=payload.reason,
    )

    await audit_action(
        db,
        request=request,
        user=current_user,
        action="inference.tier_floor_overridden",
        resource_type="message",
        resource_id=refusal.id,
        details={
            "reason": payload.reason,
            "chat_id": str(refusal.chat_id),
            "new_message_id": str(ai_message.id),
        },
    )
    await db.commit()
    await db.refresh(ai_message)
    return OverrideResponse(
        ai_message=MessageResponse.model_validate(ai_message),
        routing_log_id=routing_log_id,
    )
```

- [ ] **Step 4: Implement `run_inference_override` in `chats.py`**

Modify `api/app/api/chats.py`. Find the existing inference-call helper (around line 800 area where `applied_skills` is composed). Add a new module-level function `run_inference_override` that:
- Takes (db, chat, user_msg, refusal_msg, override_reason)
- Calls the gateway with `tier_floor=None` and `override_reason=...` in metadata
- Creates a new Message row with `kind='ai'`, `role='assistant'`
- Writes the inference_routing_log row with `refused=False`
- Returns (Message, log_id_uuid)

The exact implementation depends on the current chat-handler structure — read `chats.py` to find the closest existing pattern (likely the normal /chat POST handler's inference call) and extract a callable helper.

If extracting is non-trivial, alternative: have `override_tier_floor` POST handler import the chat handler's helper directly and call it. Either pattern is fine; pick the smaller diff.

- [ ] **Step 5: Register the router**

Modify `api/app/api/__init__.py`. Add the import and router registration alongside existing ones:

```python
from app.api import inference_override

# ... later, with other includes ...
api_router.include_router(inference_override.router, dependencies=_active)
```

- [ ] **Step 6: Re-run tests**

```bash
docker compose exec -w /app api pytest tests/api/test_inference_override.py -v 2>&1 | tail -10
```

Expected: all 5 pass.

- [ ] **Step 7: Commit**

```bash
git add api/app/api/inference_override.py \
        api/app/api/__init__.py \
        api/app/api/chats.py \
        api/tests/api/test_inference_override.py
git commit -s -m "$(cat <<'EOF'
feat(api): POST /api/v1/inference/override-tier-floor

Admin-only re-run of a refused inference with tier-floor lifted
for one turn. Validates reason (10..500), looks up the preceding
user message, delegates to run_inference_override helper in
chats.py, writes new kind='ai' Message + audit row with reason.

M1 binds to admin role per RBAC simplification; per-user
override_tier_floor permission deferred to v1.1+.

Refs Wave D.1 plan T4 (spec §7.4).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 5: Backend — `GET /api/v1/chats/{id}/receipts`

**Files:**
- Create: `api/app/api/chat_receipts.py`
- Modify: `api/app/api/__init__.py` (register router)
- Create: `api/tests/api/test_chat_receipts.py`

**Background:**
Replay-at-read over four sources: `messages`, `inference_routing_log`, `audit_log` (filtered to this chat), and `messages.applied_skills` (denormalized — produces skill-applied events). KB-retrieval events come from `audit_log` action `inference.kb_chunks_retrieved` (added in T7). Filter query param `event_kinds=...`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/api/test_chat_receipts.py`:

```python
"""GET /api/v1/chats/{id}/receipts — replay-at-read event log."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_receipts_merges_messages_inference_audit(
    client: AsyncClient, auth_headers, populated_chat
):
    """populated_chat has 1 user msg + 1 ai msg + 1 audit + 1 inference log."""
    response = await client.get(
        f"/api/v1/chats/{populated_chat.id}/receipts",
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = response.json()
    kinds = {e["kind"] for e in events}
    assert "message" in kinds
    assert "inference" in kinds
    assert "audit" in kinds


async def test_receipts_chronological_ascending(
    client, auth_headers, populated_chat
):
    response = await client.get(
        f"/api/v1/chats/{populated_chat.id}/receipts",
        headers=auth_headers,
    )
    events = response.json()
    timestamps = [e["ts"] for e in events]
    assert timestamps == sorted(timestamps), "events must be ascending by ts"


async def test_receipts_filters_by_event_kinds(
    client, auth_headers, populated_chat
):
    response = await client.get(
        f"/api/v1/chats/{populated_chat.id}/receipts?event_kinds=message,audit",
        headers=auth_headers,
    )
    events = response.json()
    kinds = {e["kind"] for e in events}
    assert kinds <= {"message", "audit"}


async def test_receipts_skill_event_from_applied_skills_array(
    client, auth_headers, chat_with_skill_applied
):
    response = await client.get(
        f"/api/v1/chats/{chat_with_skill_applied.id}/receipts",
        headers=auth_headers,
    )
    events = response.json()
    skill_events = [e for e in events if e["kind"] == "skill"]
    assert len(skill_events) >= 1
    assert "skill_name" in skill_events[0]["detail"]


async def test_receipts_non_owner_returns_403(
    client, other_user_auth_headers, populated_chat
):
    response = await client.get(
        f"/api/v1/chats/{populated_chat.id}/receipts",
        headers=other_user_auth_headers,
    )
    assert response.status_code in (403, 404)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -w /app api pytest tests/api/test_chat_receipts.py -v 2>&1 | tail -10
```

Expected: failures (route doesn't exist).

- [ ] **Step 3: Implement the endpoint**

Create `api/app/api/chat_receipts.py`:

```python
"""GET /api/v1/chats/{id}/receipts — replay-at-read event log.

Merges events from four sources into a single chronological stream:
  - messages          -> kind='message' event per row
  - inference_routing_log -> kind='inference' event per row
  - audit_log         -> kind='audit' event per row
                          (resource_type='chat' OR action ~ chat-related)
                          plus kind='retrieval' when action='inference.kb_chunks_retrieved'
  - messages.applied_skills text[] -> kind='skill' event per skill name
                                       (denormalized per ADR 0007)

Replay-at-read chosen over materialized table for M1 — chats are
bounded (<100 events typical). Path to materialization is v1.1+.

Per Wave D.1 plan T5 (spec §7.6).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.models.audit import AuditLog
from app.models.chat import Chat, Message
from app.models.inference import InferenceRoutingLog
from app.models.user import User

router = APIRouter(prefix="/chats", tags=["chats"])


EventKind = Literal["message", "inference", "audit", "skill", "retrieval", "error"]


class ReceiptEvent(BaseModel):
    ts: datetime
    kind: EventKind
    detail: dict[str, Any]


@router.get(
    "/{chat_id}/receipts",
    response_model=list[ReceiptEvent],
    summary="Chronological event log for a chat (replay-at-read)",
)
async def get_chat_receipts(
    chat_id: uuid.UUID,
    event_kinds: Annotated[str | None, Query(description="csv subset")] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReceiptEvent]:
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(404, "Chat not found")
    if chat.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(403, "Forbidden")

    requested = (
        set(event_kinds.split(","))
        if event_kinds
        else {"message", "inference", "audit", "skill", "retrieval", "error"}
    )

    events: list[ReceiptEvent] = []

    if "message" in requested or "skill" in requested:
        msgs = await db.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
        )
        for m in msgs.scalars():
            if "message" in requested:
                events.append(ReceiptEvent(
                    ts=m.created_at,
                    kind="message",
                    detail={
                        "message_id": str(m.id),
                        "message_kind": m.kind,
                        "role": m.role,
                        "prompt_tokens": m.prompt_tokens,
                        "completion_tokens": m.completion_tokens,
                    },
                ))
            if "skill" in requested and m.applied_skills:
                for skill_name in m.applied_skills:
                    events.append(ReceiptEvent(
                        ts=m.created_at,
                        kind="skill",
                        detail={
                            "skill_name": skill_name,
                            "message_id": str(m.id),
                        },
                    ))

    if "inference" in requested or "error" in requested:
        logs = await db.execute(
            select(InferenceRoutingLog)
            .where(InferenceRoutingLog.chat_id == chat_id)
            .order_by(InferenceRoutingLog.timestamp)
        )
        for log in logs.scalars():
            kind: EventKind = "error" if log.refused else "inference"
            if kind in requested:
                events.append(ReceiptEvent(
                    ts=log.timestamp,
                    kind=kind,
                    detail={
                        "provider": log.routed_provider,
                        "model": log.routed_model,
                        "tier": log.routed_inference_tier,
                        "tokens_in": log.tokens_in,
                        "tokens_out": log.tokens_out,
                        "latency_ms": log.latency_ms,
                        "refused": log.refused,
                        "refusal_reason": log.refusal_reason,
                    },
                ))

    if "audit" in requested or "retrieval" in requested:
        audits = await db.execute(
            select(AuditLog)
            .where(AuditLog.resource_type == "chat")
            .where(AuditLog.resource_id == chat_id)
            .order_by(AuditLog.timestamp)
        )
        for a in audits.scalars():
            kind = "retrieval" if a.action == "inference.kb_chunks_retrieved" else "audit"
            if kind in requested:
                events.append(ReceiptEvent(
                    ts=a.timestamp,
                    kind=kind,
                    detail={
                        "action": a.action,
                        "actor_user_id": str(a.user_id) if a.user_id else None,
                        "details": a.details,
                    },
                ))

    events.sort(key=lambda e: e.ts)
    return events
```

- [ ] **Step 4: Register router**

Modify `api/app/api/__init__.py`:

```python
from app.api import chat_receipts

# ... with includes:
api_router.include_router(chat_receipts.router, dependencies=_active)
```

- [ ] **Step 5: Re-run tests**

```bash
docker compose exec -w /app api pytest tests/api/test_chat_receipts.py -v 2>&1 | tail -10
```

Expected: 5 pass.

- [ ] **Step 6: Commit**

```bash
git add api/app/api/chat_receipts.py \
        api/app/api/__init__.py \
        api/tests/api/test_chat_receipts.py
git commit -s -m "$(cat <<'EOF'
feat(api): GET /api/v1/chats/{id}/receipts (replay-at-read)

Merges events from messages + inference_routing_log + audit_log +
messages.applied_skills into a single chronological stream. Filter
via ?event_kinds=message,inference,audit,skill,retrieval,error.
Owner + admin scoped.

KB retrieval events surface from audit rows with action=
inference.kb_chunks_retrieved (written by hybrid_search call site
in T7). Refusal-bearing inference rows surface as kind='error'.

Refs Wave D.1 plan T5 (spec §7.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 6: Backend — `GET /api/v1/chats/{id}/receipts/export.jsonl`

**Files:**
- Modify: `api/app/api/chat_receipts.py` (add export route)
- Modify: `api/tests/api/test_chat_receipts.py` (add export tests)

**Background:**
Same payload as T5 but serialized one event per line. `Content-Type: application/jsonl`. `Content-Disposition: attachment; filename="chat-{id}-receipts.jsonl"`.

- [ ] **Step 1: Write the failing test**

Append to `api/tests/api/test_chat_receipts.py`:

```python
async def test_receipts_export_jsonl(
    client: AsyncClient, auth_headers, populated_chat
):
    response = await client.get(
        f"/api/v1/chats/{populated_chat.id}/receipts/export.jsonl",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/jsonl")
    assert "attachment" in response.headers["content-disposition"]
    assert f"chat-{populated_chat.id}-receipts.jsonl" in response.headers["content-disposition"]

    import json
    lines = [l for l in response.text.splitlines() if l.strip()]
    assert len(lines) > 0
    for line in lines:
        parsed = json.loads(line)
        assert "ts" in parsed
        assert "kind" in parsed
        assert "detail" in parsed
```

- [ ] **Step 2: Run test to verify failure**

```bash
docker compose exec -w /app api pytest tests/api/test_chat_receipts.py::test_receipts_export_jsonl -v 2>&1 | tail -5
```

Expected: 404.

- [ ] **Step 3: Implement the export route**

Append to `api/app/api/chat_receipts.py`:

```python
from fastapi.responses import Response
import json as _json


@router.get(
    "/{chat_id}/receipts/export.jsonl",
    summary="Export receipts as JSONL",
    response_class=Response,
)
async def export_chat_receipts(
    chat_id: uuid.UUID,
    event_kinds: Annotated[str | None, Query()] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    events = await get_chat_receipts(
        chat_id=chat_id,
        event_kinds=event_kinds,
        db=db,
        current_user=current_user,
    )
    body = "\n".join(_json.dumps(e.model_dump(mode="json")) for e in events)
    return Response(
        content=body,
        media_type="application/jsonl",
        headers={
            "Content-Disposition": (
                f'attachment; filename="chat-{chat_id}-receipts.jsonl"'
            ),
        },
    )
```

- [ ] **Step 4: Re-run test**

```bash
docker compose exec -w /app api pytest tests/api/test_chat_receipts.py::test_receipts_export_jsonl -v 2>&1 | tail -5
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add api/app/api/chat_receipts.py api/tests/api/test_chat_receipts.py
git commit -s -m "$(cat <<'EOF'
feat(api): GET /api/v1/chats/{id}/receipts/export.jsonl

JSONL export of the chronological event stream with proper
Content-Type and attachment Content-Disposition. Same filter
query param as the JSON endpoint. Owner + admin scoped.

Refs Wave D.1 plan T6 (spec §7.6 "Export receipts as JSONL").

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 7: Backend — KB retrieval audit-row write at `hybrid_search` call site

**Files:**
- Modify: `api/app/knowledge/retrieval.py` OR `api/app/api/chats.py` (wherever hybrid_search is called from the chat path)
- Create: `api/tests/api/test_kb_retrieval_audit.py`

**Background:**
Currently `hybrid_search` returns retrieved chunks but no audit event is written. Receipts can't show "📎 KB retrieval" events without this. Add an `audit_action(action='inference.kb_chunks_retrieved')` call at the site where chat-initiated retrievals happen. Audit `details` payload: `{kb_id, chunk_count, chunk_ids[], total_tokens, score_threshold}`.

**Investigation:** during implementation, grep for `hybrid_search(` in `api/app/` to find call sites. Likely 1-2 sites. Add audit write at each chat-initiated site.

- [ ] **Step 1: Write the failing test**

Create `api/tests/api/test_kb_retrieval_audit.py`:

```python
"""Audit row written when KB retrieval fires from a chat."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

pytestmark = pytest.mark.integration


async def test_chat_with_kb_attached_writes_retrieval_audit_row(
    client, auth_headers, chat_with_kb_attached, db_session: AsyncSession
):
    """Sending a chat message in a chat with an attached KB writes a
    retrieval audit row alongside the inference."""
    response = await client.post(
        f"/api/v1/chats/{chat_with_kb_attached.id}/messages",
        json={"content": "What does the NDA say about non-compete?"},
        headers=auth_headers,
    )
    assert response.status_code in (200, 201)

    audits = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "inference.kb_chunks_retrieved",
            AuditLog.resource_id == chat_with_kb_attached.id,
        )
    )
    rows = audits.scalars().all()
    assert len(rows) >= 1
    detail = rows[0].details
    assert "kb_id" in detail
    assert "chunk_count" in detail
    assert detail["chunk_count"] > 0


async def test_chat_without_kb_writes_no_retrieval_audit(
    client, auth_headers, chat_without_kb, db_session: AsyncSession
):
    await client.post(
        f"/api/v1/chats/{chat_without_kb.id}/messages",
        json={"content": "hi"},
        headers=auth_headers,
    )
    audits = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "inference.kb_chunks_retrieved",
            AuditLog.resource_id == chat_without_kb.id,
        )
    )
    assert audits.scalar_one_or_none() is None
```

- [ ] **Step 2: Locate the hybrid_search call site**

Run:
```bash
grep -rn "hybrid_search(" api/app/ | grep -v test | grep -v __pycache__
```

Expected: 1-3 call sites. Note the line numbers.

- [ ] **Step 3: Add audit write at the call site**

At each chat-initiated `hybrid_search(...)` call site, immediately after the call wrap the result:

```python
# After: chunks = await hybrid_search(db=..., kb_ids=[kb.id], query=...)
if chunks:
    await audit_action(
        db,
        request=request,  # may need to thread through if not already in scope
        user=current_user,
        action="inference.kb_chunks_retrieved",
        resource_type="chat",
        resource_id=chat.id,
        details={
            "kb_ids": [str(kb.id) for kb in attached_kbs],
            "chunk_count": len(chunks),
            "chunk_ids": [str(c.chunk_id) for c in chunks],
            "query_token_estimate": len(query.split()),
        },
    )
```

If `request` isn't in scope at the call site, pass `None` — the helper accepts it.

- [ ] **Step 4: Run tests**

```bash
docker compose exec -w /app api pytest tests/api/test_kb_retrieval_audit.py -v 2>&1 | tail -10
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add api/app/knowledge/retrieval.py api/app/api/chats.py \
        api/tests/api/test_kb_retrieval_audit.py
git commit -s -m "$(cat <<'EOF'
feat(api): write audit row on KB chunk retrieval

Adds an audit_log row with action='inference.kb_chunks_retrieved'
every time the chat path's hybrid_search returns results. Details
carry kb_ids, chunk_count, chunk_ids[], query_token_estimate.

Required so Receipts can show '📎 KB retrieval' events without
a dedicated kb_retrieval_log table (M1 simplification).

Refs Wave D.1 plan T7 (spec §7.6 retrieval-event row).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 8: Frontend API client — `projectKnowledgeBases.ts`

**Files:**
- Create: `web/src/lib/lq-ai/api/projectKnowledgeBases.ts`
- Create: `web/src/lib/lq-ai/__tests__/project-knowledge-bases-api.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/lq-ai/__tests__/project-knowledge-bases-api.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { attachKnowledgeBase, detachKnowledgeBase } from '../api/projectKnowledgeBases';

describe('projectKnowledgeBases api', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    global.fetch = vi.fn();
  });

  it('attachKnowledgeBase POSTs to /api/v1/projects/{id}/knowledge-bases', async () => {
    const fakeProject = { id: 'p1', knowledge_bases: [{ id: 'kb1' }] };
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => fakeProject,
    });

    const result = await attachKnowledgeBase('p1', 'kb1', { fetch: global.fetch as any });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/projects/p1/knowledge-bases'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ knowledge_base_id: 'kb1' }),
      })
    );
    expect(result).toEqual(fakeProject);
  });

  it('detachKnowledgeBase DELETEs to /.../knowledge-bases/{kbId}', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 204,
    });
    await detachKnowledgeBase('p1', 'kb1', { fetch: global.fetch as any });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/projects/p1/knowledge-bases/kb1'),
      expect.objectContaining({ method: 'DELETE' })
    );
  });

  it('attachKnowledgeBase throws on 404', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: false, status: 404, json: async () => ({ detail: 'Knowledge base not found' }),
    });
    await expect(attachKnowledgeBase('p1', 'kb1', { fetch: global.fetch as any }))
      .rejects.toThrow(/not found/i);
  });

  it('detachKnowledgeBase throws on 403', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: false, status: 403, json: async () => ({ detail: 'Forbidden' }),
    });
    await expect(detachKnowledgeBase('p1', 'kb1', { fetch: global.fetch as any }))
      .rejects.toThrow();
  });
});
```

- [ ] **Step 2: Implement the API client**

Create `web/src/lib/lq-ai/api/projectKnowledgeBases.ts`:

```ts
import { apiBaseUrl, withAuthHeaders } from './_shared';
import type { Project } from '../types/Project';

export interface FetchOptions {
  fetch?: typeof fetch;
}

export async function attachKnowledgeBase(
  projectId: string,
  knowledgeBaseId: string,
  opts: FetchOptions = {},
): Promise<Project> {
  const f = opts.fetch ?? fetch;
  const res = await f(
    `${apiBaseUrl()}/api/v1/projects/${projectId}/knowledge-bases`,
    {
      method: 'POST',
      headers: withAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ knowledge_base_id: knowledgeBaseId }),
    }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `attachKnowledgeBase failed (${res.status})`);
  }
  return await res.json();
}

export async function detachKnowledgeBase(
  projectId: string,
  knowledgeBaseId: string,
  opts: FetchOptions = {},
): Promise<void> {
  const f = opts.fetch ?? fetch;
  const res = await f(
    `${apiBaseUrl()}/api/v1/projects/${projectId}/knowledge-bases/${knowledgeBaseId}`,
    {
      method: 'DELETE',
      headers: withAuthHeaders(),
    }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `detachKnowledgeBase failed (${res.status})`);
  }
}
```

If `_shared.ts` doesn't expose `apiBaseUrl` or `withAuthHeaders`, match the convention used by `web/src/lib/lq-ai/api/projects.ts` (read it first; mirror the pattern exactly).

- [ ] **Step 3: Run tests**

```bash
cd web && npm run test:frontend -- --run project-knowledge-bases-api 2>&1 | tail -10
```

Expected: 4 pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/api/projectKnowledgeBases.ts \
        web/src/lib/lq-ai/__tests__/project-knowledge-bases-api.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): projectKnowledgeBases API client (attach/detach)

Mirrors the existing projects.ts attach pattern. attachKnowledgeBase
returns the updated Project; detachKnowledgeBase returns void on 204.
Surfaces backend error detail on failure.

Refs Wave D.1 plan T8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 9: Frontend API client — `inferenceOverride.ts`

**Files:**
- Create: `web/src/lib/lq-ai/api/inferenceOverride.ts`
- Create: `web/src/lib/lq-ai/__tests__/inference-override-api.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/lq-ai/__tests__/inference-override-api.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { overrideTierFloor } from '../api/inferenceOverride';

describe('inferenceOverride api', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    global.fetch = vi.fn();
  });

  it('POSTs to /api/v1/inference/override-tier-floor with message_id + reason', async () => {
    const fakeReply = {
      ai_message: { id: 'm2', kind: 'ai', chat_id: 'c1', content: 'overridden response' },
      routing_log_id: 'log1',
    };
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => fakeReply,
    });

    const result = await overrideTierFloor('m1', 'Urgent client request — partner risk-accepted', { fetch: global.fetch as any });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/inference/override-tier-floor'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          message_id: 'm1',
          reason: 'Urgent client request — partner risk-accepted',
        }),
      })
    );
    expect(result.ai_message.kind).toBe('ai');
  });

  it('throws on 403 with descriptive message', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: false, status: 403,
      json: async () => ({ detail: 'Tier-floor override requires admin role (M1).' }),
    });
    await expect(overrideTierFloor('m1', '10+ char reason here', { fetch: global.fetch as any }))
      .rejects.toThrow(/admin role/);
  });

  it('throws on 422 with validation message', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: false, status: 422,
      json: async () => ({ detail: 'reason too short' }),
    });
    await expect(overrideTierFloor('m1', 'short', { fetch: global.fetch as any }))
      .rejects.toThrow(/too short/);
  });
});
```

- [ ] **Step 2: Implement the client**

Create `web/src/lib/lq-ai/api/inferenceOverride.ts`:

```ts
import { apiBaseUrl, withAuthHeaders } from './_shared';
import type { Message } from '../types/Message';

export interface OverrideResponse {
  ai_message: Message;
  routing_log_id: string;
}

export interface FetchOptions {
  fetch?: typeof fetch;
}

export async function overrideTierFloor(
  messageId: string,
  reason: string,
  opts: FetchOptions = {},
): Promise<OverrideResponse> {
  const f = opts.fetch ?? fetch;
  const res = await f(
    `${apiBaseUrl()}/api/v1/inference/override-tier-floor`,
    {
      method: 'POST',
      headers: withAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ message_id: messageId, reason }),
    }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `overrideTierFloor failed (${res.status})`);
  }
  return await res.json();
}
```

- [ ] **Step 3: Run tests**

```bash
cd web && npm run test:frontend -- --run inference-override-api 2>&1 | tail -8
```

Expected: 3 pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/api/inferenceOverride.ts \
        web/src/lib/lq-ai/__tests__/inference-override-api.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): inferenceOverride API client

Wraps POST /api/v1/inference/override-tier-floor. Surfaces admin-
gating + reason-validation errors as descriptive Error throws.

Refs Wave D.1 plan T9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 10: Frontend API client — `receipts.ts`

**Files:**
- Create: `web/src/lib/lq-ai/api/receipts.ts`
- Create: `web/src/lib/lq-ai/__tests__/receipts-api.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/lq-ai/__tests__/receipts-api.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { listChatReceipts, exportChatReceiptsJsonl } from '../api/receipts';

describe('receipts api', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    global.fetch = vi.fn();
  });

  it('listChatReceipts GETs /api/v1/chats/{id}/receipts', async () => {
    const fakeEvents = [
      { ts: '2026-05-12T10:14:00Z', kind: 'message', detail: { message_id: 'm1' } },
      { ts: '2026-05-12T10:14:01Z', kind: 'inference', detail: { provider: 'anthropic' } },
    ];
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => fakeEvents,
    });

    const events = await listChatReceipts('c1', undefined, { fetch: global.fetch as any });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/chats/c1/receipts'),
      expect.any(Object)
    );
    expect(events).toHaveLength(2);
    expect(events[0].kind).toBe('message');
  });

  it('listChatReceipts passes event_kinds as comma-separated csv', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => [],
    });
    await listChatReceipts('c1', ['message', 'audit'], { fetch: global.fetch as any });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('event_kinds=message%2Caudit'),
      expect.any(Object)
    );
  });

  it('exportChatReceiptsJsonl returns the JSONL text and the suggested filename', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200,
      headers: new Map([
        ['content-type', 'application/jsonl'],
        ['content-disposition', 'attachment; filename="chat-c1-receipts.jsonl"'],
      ]),
      text: async () => '{"ts":"2026-05-12T10:14:00Z","kind":"message","detail":{}}',
    });
    const { jsonl, filename } = await exportChatReceiptsJsonl('c1', { fetch: global.fetch as any });
    expect(jsonl).toContain('"kind":"message"');
    expect(filename).toBe('chat-c1-receipts.jsonl');
  });
});
```

- [ ] **Step 2: Implement the client**

Create `web/src/lib/lq-ai/api/receipts.ts`:

```ts
import { apiBaseUrl, withAuthHeaders } from './_shared';

export type ReceiptEventKind =
  | 'message' | 'inference' | 'audit' | 'skill' | 'retrieval' | 'error';

export interface ReceiptEvent {
  ts: string;
  kind: ReceiptEventKind;
  detail: Record<string, unknown>;
}

export interface FetchOptions {
  fetch?: typeof fetch;
}

export async function listChatReceipts(
  chatId: string,
  eventKinds?: ReceiptEventKind[],
  opts: FetchOptions = {},
): Promise<ReceiptEvent[]> {
  const f = opts.fetch ?? fetch;
  const url = new URL(`${apiBaseUrl()}/api/v1/chats/${chatId}/receipts`);
  if (eventKinds && eventKinds.length > 0) {
    url.searchParams.set('event_kinds', eventKinds.join(','));
  }
  const res = await f(url.toString(), { headers: withAuthHeaders() });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `listChatReceipts failed (${res.status})`);
  }
  return await res.json();
}

export async function exportChatReceiptsJsonl(
  chatId: string,
  opts: FetchOptions = {},
): Promise<{ jsonl: string; filename: string }> {
  const f = opts.fetch ?? fetch;
  const res = await f(
    `${apiBaseUrl()}/api/v1/chats/${chatId}/receipts/export.jsonl`,
    { headers: withAuthHeaders() }
  );
  if (!res.ok) {
    throw new Error(`exportChatReceiptsJsonl failed (${res.status})`);
  }
  const jsonl = await res.text();
  const disposition =
    (res.headers as any).get?.('content-disposition') ??
    (res.headers as any).get('content-disposition');
  const match = /filename="([^"]+)"/.exec(disposition ?? '');
  const filename = match?.[1] ?? `chat-${chatId}-receipts.jsonl`;
  return { jsonl, filename };
}
```

- [ ] **Step 3: Run tests**

```bash
cd web && npm run test:frontend -- --run receipts-api 2>&1 | tail -8
```

Expected: 3 pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/api/receipts.ts \
        web/src/lib/lq-ai/__tests__/receipts-api.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): receipts API client (list + JSONL export)

Wraps GET /api/v1/chats/{id}/receipts with optional event_kinds
filter, and GET .../receipts/export.jsonl which returns both the
JSONL text and the filename from Content-Disposition for direct
download trigger.

Refs Wave D.1 plan T10.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 11: Component — `AttachKBModal.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/AttachKBModal.svelte`
- Create: `web/src/lib/lq-ai/__tests__/AttachKBModal.test.ts`

**Background:**
Searchable card grid (auto-fill min 200px), multi-select with live counter, sort menu (Recently used / Alphabetical / Most attached / Indexing status), inline upload section, "currently attached" badge for KBs already on this matter, first-time JIT pre-action banner.

**Props:**
- `open: boolean`
- `projectId: string`
- `attachedKbIds: string[]` — already-attached for this matter
- `onClose: () => void`
- `onAttach: (newlyAttachedKbIds: string[]) => void` — called after successful attach
- `onDetach: (kbId: string) => void` — for currently-attached cards' Detach link

**Test cases (write first per TDD):**

```ts
// web/src/lib/lq-ai/__tests__/AttachKBModal.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import AttachKBModal from '../components/AttachKBModal.svelte';
import * as kbApi from '../api/knowledgeBases';
import * as pkbApi from '../api/projectKnowledgeBases';

describe('AttachKBModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(kbApi, 'listKnowledgeBases').mockResolvedValue([
      { id: 'kb1', name: 'NDA-Playbook', doc_count: 47, ingestion_status: 'ready', attached_count: 3, updated_at: '2026-05-01T00:00:00Z' },
      { id: 'kb2', name: 'M&A Templates', doc_count: 23, ingestion_status: 'indexing', attached_count: 1, updated_at: '2026-05-10T00:00:00Z' },
      { id: 'kb3', name: 'Lease KB',     doc_count: 12, ingestion_status: 'ready', attached_count: 5, updated_at: '2026-04-20T00:00:00Z' },
    ]);
  });

  it('renders nothing when open=false', () => {
    const { queryByText } = render(AttachKBModal, {
      open: false, projectId: 'p1', attachedKbIds: [],
      onClose: () => {}, onAttach: () => {}, onDetach: () => {},
    });
    expect(queryByText(/attach knowledge bases/i)).toBeNull();
  });

  it('renders title + grid + uploader when open', async () => {
    const { getByText, findByText } = render(AttachKBModal, {
      open: true, projectId: 'p1', attachedKbIds: [],
      onClose: () => {}, onAttach: () => {}, onDetach: () => {},
    });
    expect(getByText(/attach knowledge bases/i)).toBeTruthy();
    await findByText('NDA-Playbook');
    expect(getByText(/upload a new kb/i)).toBeTruthy();
  });

  it('filters by search input', async () => {
    const { getByPlaceholderText, findByText, queryByText } = render(AttachKBModal, {
      open: true, projectId: 'p1', attachedKbIds: [],
      onClose: () => {}, onAttach: () => {}, onDetach: () => {},
    });
    await findByText('NDA-Playbook');
    const search = getByPlaceholderText(/search by name/i);
    await fireEvent.input(search, { target: { value: 'M&A' } });
    expect(queryByText('NDA-Playbook')).toBeNull();
    expect(queryByText('M&A Templates')).toBeTruthy();
  });

  it('CTA counter updates with multi-select', async () => {
    const { findByText, getByText, container } = render(AttachKBModal, {
      open: true, projectId: 'p1', attachedKbIds: [],
      onClose: () => {}, onAttach: () => {}, onDetach: () => {},
    });
    await findByText('NDA-Playbook');
    const checkboxes = container.querySelectorAll('input[type=checkbox]');
    await fireEvent.click(checkboxes[0]);
    await fireEvent.click(checkboxes[1]);
    expect(getByText(/attach 2 selected/i)).toBeTruthy();
  });

  it('renders "currently attached" badge for attached KBs', async () => {
    const { findByText } = render(AttachKBModal, {
      open: true, projectId: 'p1', attachedKbIds: ['kb3'],
      onClose: () => {}, onAttach: () => {}, onDetach: () => {},
    });
    await findByText('Lease KB');
    expect((await findByText(/currently attached/i))).toBeTruthy();
  });

  it('clicking Attach calls attachKnowledgeBase for each selected then onAttach', async () => {
    const attachSpy = vi.spyOn(pkbApi, 'attachKnowledgeBase').mockResolvedValue({} as any);
    const onAttach = vi.fn();
    const { findByText, getByText, container } = render(AttachKBModal, {
      open: true, projectId: 'p1', attachedKbIds: [],
      onClose: () => {}, onAttach, onDetach: () => {},
    });
    await findByText('NDA-Playbook');
    const checkboxes = container.querySelectorAll('input[type=checkbox]');
    await fireEvent.click(checkboxes[0]);
    await fireEvent.click(getByText(/attach 1 selected/i));
    await waitFor(() => expect(attachSpy).toHaveBeenCalledWith('p1', 'kb1', expect.anything()));
    expect(onAttach).toHaveBeenCalledWith(['kb1']);
  });

  it('sort menu reorders cards', async () => {
    const { findByText, getByLabelText, container } = render(AttachKBModal, {
      open: true, projectId: 'p1', attachedKbIds: [],
      onClose: () => {}, onAttach: () => {}, onDetach: () => {},
    });
    await findByText('NDA-Playbook');
    const sort = getByLabelText(/sort/i);
    await fireEvent.change(sort, { target: { value: 'alphabetical' } });
    const headings = Array.from(container.querySelectorAll('.kb-card h3')).map(n => n.textContent);
    expect(headings).toEqual(['Lease KB', 'M&A Templates', 'NDA-Playbook']);
  });
});
```

- [ ] **Step 1: Run tests to verify they fail**

```bash
cd web && npm run test:frontend -- --run AttachKBModal 2>&1 | tail -10
```

Expected: failures — component doesn't exist.

- [ ] **Step 2: Implement `AttachKBModal.svelte`**

Create `web/src/lib/lq-ai/components/AttachKBModal.svelte`. Use the design from spec §3.3 and the test cases as the contract. Required behaviors:
- Modal frame (use the existing modal pattern from Wave C's NewMatterModal — read it for shape).
- Top: search input + sort dropdown.
- Body: card grid (auto-fill min 200px).
- Each card: name · doc count · ingestion status badge (`✓ indexed` / `⏳ {N}%` / `⚠ failed`) · attached-count badge · checkbox (or "currently attached" + Detach link if already attached).
- Below grid: divider + inline upload section using `<input type="file">` that creates a new KB via `kbApi.createKnowledgeBase` then refreshes.
- Footer: Cancel + "Attach N selected" primary CTA, disabled if N === 0.
- First-time JIT banner: small dismissible amber strip at top on first open (use localStorage key `lq_ai_jit_kb_attach_seen`).

Test cases drive implementation — write code until all 7 pass.

- [ ] **Step 3: Re-run tests until green**

```bash
cd web && npm run test:frontend -- --run AttachKBModal 2>&1 | tail -10
```

Expected: 7 pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/components/AttachKBModal.svelte \
        web/src/lib/lq-ai/__tests__/AttachKBModal.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): AttachKBModal — searchable card grid with multi-select

Shared modal for the three KB-attach entry points (composer 📎,
matter rail '+ Attach KB', and Wave F's /lq-ai/knowledge surface).
Card grid with search, sort (recent / alphabetical / most-attached
/ indexing-status), multi-select with live CTA counter, inline
uploader, and a 'currently attached' state for KBs already on the
matter.

7 unit tests cover render, filter, multi-select, attached-state,
attach flow, sort.

Refs Wave D.1 plan T11 (spec §7.3).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 12: Wire `AttachKBModal` into Composer 📎 + MatterRailKnowledge

**Files:**
- Modify: `web/src/lib/lq-ai/components/ChatPanel.svelte` (or `Composer.svelte` — wherever the toolbar lives)
- Modify: `web/src/lib/lq-ai/components/MatterRailKnowledge.svelte` (or the rail component that lists KBs)

**Background:**
Two entry points → same modal. Both wire `open` state, pass `attachedKbIds` from the current matter, refresh the matter rail's KB list on success.

- [ ] **Step 1: Locate the existing matter rail KB section**

```bash
cd /Users/kevinkeller/Desktop/lq-ai
grep -rn "Attach KB\|attach.*kb\|knowledge.*section\|MatterRailKnowledge" web/src/lib/lq-ai/ web/src/routes/lq-ai/ | head -10
```

Note the file + line range. If `MatterRailKnowledge.svelte` doesn't exist as a separate component, the KB section is inlined in `MatterRail.svelte` — modify there.

- [ ] **Step 2: Wire from matter rail**

In the matter rail file (likely `web/src/lib/lq-ai/components/MatterRail.svelte` or similar), find the "Knowledge" section and the "+ Attach KB" link. Add modal state:

```svelte
<script lang="ts">
  // ... existing imports
  import AttachKBModal from './AttachKBModal.svelte';
  // ...
  let attachKbModalOpen = false;

  function handleAttachSuccess(newKbIds: string[]) {
    // refresh the matter's KB list — call the parent's refresh hook
    onMatterChanged?.();
  }
</script>

<!-- ... existing Knowledge section ... -->
<a on:click={() => (attachKbModalOpen = true)}>+ Attach KB</a>

<AttachKBModal
  bind:open={attachKbModalOpen}
  projectId={matter.id}
  attachedKbIds={matter.knowledge_bases?.map((kb) => kb.id) ?? []}
  onClose={() => (attachKbModalOpen = false)}
  onAttach={handleAttachSuccess}
  onDetach={async (kbId) => {
    await detachKnowledgeBase(matter.id, kbId);
    onMatterChanged?.();
  }}
/>
```

- [ ] **Step 3: Wire from composer toolbar**

In `ChatPanel.svelte` (or wherever the composer toolbar lives — check Wave C's structure), find the existing toolbar with `📎` button. Wire it to open the same modal:

```svelte
<script lang="ts">
  // ... existing imports
  import AttachKBModal from './AttachKBModal.svelte';
  export let projectId: string | null = null;
  export let attachedKbIds: string[] = [];
  let attachKbModalOpen = false;
</script>

<!-- toolbar -->
<button title="Attach knowledge base" on:click={() => (attachKbModalOpen = true)}>📎</button>

{#if projectId}
  <AttachKBModal
    bind:open={attachKbModalOpen}
    {projectId}
    {attachedKbIds}
    onClose={() => (attachKbModalOpen = false)}
    onAttach={() => {
      attachKbModalOpen = false;
      dispatch('kbsAttached');
    }}
    onDetach={() => {}}
  />
{/if}
```

The `dispatch('kbsAttached')` event bubbles up to the matter workspace page which can refresh the matter object.

- [ ] **Step 4: Smoke test in browser**

```bash
docker compose up -d --no-deps --build web 2>&1 | tail -5
# wait ~30s for build
```

Open `http://localhost:3000/lq-ai/matters/<some-matter-id>`. Click `+ Attach KB` from rail → modal opens. Click composer 📎 → modal opens. Multi-select → Attach → modal closes → rail shows the new KBs.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/MatterRail.svelte \
        web/src/lib/lq-ai/components/ChatPanel.svelte
git commit -s -m "$(cat <<'EOF'
feat(web): wire AttachKBModal into composer 📎 + matter rail

Two entry points share the same modal: composer toolbar 📎 button
and the matter rail's '+ Attach KB' link. Both pass the current
matter's attachedKbIds so already-attached KBs render with the
'currently attached' badge. On successful attach, parent refreshes
the matter object (which re-renders the rail KB list).

Refs Wave D.1 plan T12 (spec §7.3 entry points 1+2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 13: Component — `RefusalMessageBubble.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/RefusalMessageBubble.svelte`
- Create: `web/src/lib/lq-ai/__tests__/RefusalMessageBubble.test.ts`

**Background:**
Amber-tinted variant of MessageBubble for `kind='refusal'`. Three buttons: Re-run / Override / Why. Override hidden when user is not admin. Provenance pills `🔒 tier mismatch` + `📜 audited`.

**Props:**
- `message: Message` — must have `kind='refusal'` and details (refusal_reason, requested_tier, enforced_tier — pulled from `inference_routing_log` joined or from message metadata; the chat handler should populate these)
- `currentUserRole: 'admin' | 'member' | 'viewer'`
- `onRerun: () => void`
- `onOverrideRequested: () => void` — opens TierFloorOverrideModal
- `onExplainerRequested: () => void` — opens "Why am I seeing this?" JIT

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/lq-ai/__tests__/RefusalMessageBubble.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import RefusalMessageBubble from '../components/RefusalMessageBubble.svelte';

const refusalMsg = {
  id: 'm1', chat_id: 'c1', kind: 'refusal', role: 'assistant', content: '',
  refusal_reason: 'tier_mismatch',
  requested_tier: 'standard', enforced_tier: 'privileged',
  created_at: '2026-05-12T10:14:01Z',
};

describe('RefusalMessageBubble', () => {
  it('renders shield heading with enforced tier', () => {
    const { getByText } = render(RefusalMessageBubble, {
      message: refusalMsg, currentUserRole: 'admin',
      onRerun: () => {}, onOverrideRequested: () => {}, onExplainerRequested: () => {},
    });
    expect(getByText(/refused at privileged-floor/i)).toBeTruthy();
  });

  it('renders body paragraph with tier substitutions', () => {
    const { getByText } = render(RefusalMessageBubble, {
      message: refusalMsg, currentUserRole: 'admin',
      onRerun: () => {}, onOverrideRequested: () => {}, onExplainerRequested: () => {},
    });
    expect(getByText(/standard.*tier provider/i)).toBeTruthy();
    expect(getByText(/privileged-floor/i)).toBeTruthy();
  });

  it('renders all 3 buttons for admin', () => {
    const { getByText } = render(RefusalMessageBubble, {
      message: refusalMsg, currentUserRole: 'admin',
      onRerun: () => {}, onOverrideRequested: () => {}, onExplainerRequested: () => {},
    });
    expect(getByText(/re-run/i)).toBeTruthy();
    expect(getByText(/override/i)).toBeTruthy();
    expect(getByText(/why am i seeing this/i)).toBeTruthy();
  });

  it('hides Override button for non-admin', () => {
    const { queryByText, getByText } = render(RefusalMessageBubble, {
      message: refusalMsg, currentUserRole: 'member',
      onRerun: () => {}, onOverrideRequested: () => {}, onExplainerRequested: () => {},
    });
    expect(queryByText(/override/i)).toBeNull();
    expect(getByText(/re-run/i)).toBeTruthy();
    expect(getByText(/why am i seeing this/i)).toBeTruthy();
  });

  it('Re-run button fires onRerun', async () => {
    const onRerun = vi.fn();
    const { getByText } = render(RefusalMessageBubble, {
      message: refusalMsg, currentUserRole: 'admin',
      onRerun, onOverrideRequested: () => {}, onExplainerRequested: () => {},
    });
    await fireEvent.click(getByText(/re-run/i));
    expect(onRerun).toHaveBeenCalled();
  });

  it('Override button fires onOverrideRequested', async () => {
    const onOverrideRequested = vi.fn();
    const { getByText } = render(RefusalMessageBubble, {
      message: refusalMsg, currentUserRole: 'admin',
      onRerun: () => {}, onOverrideRequested, onExplainerRequested: () => {},
    });
    await fireEvent.click(getByText(/override/i));
    expect(onOverrideRequested).toHaveBeenCalled();
  });

  it('renders both provenance pills', () => {
    const { getByText } = render(RefusalMessageBubble, {
      message: refusalMsg, currentUserRole: 'admin',
      onRerun: () => {}, onOverrideRequested: () => {}, onExplainerRequested: () => {},
    });
    expect(getByText(/tier mismatch/i)).toBeTruthy();
    expect(getByText(/audited/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests (fail)**

```bash
cd web && npm run test:frontend -- --run RefusalMessageBubble 2>&1 | tail -8
```

- [ ] **Step 3: Implement the component**

Create `web/src/lib/lq-ai/components/RefusalMessageBubble.svelte`. Visual treatment per spec §7.4 (amber `#fffbeb` / `#f59e0b` border / `#92400e` heading). Use the same provenance-pill component from Wave A if it exists.

- [ ] **Step 4: Re-run tests**

```bash
cd web && npm run test:frontend -- --run RefusalMessageBubble 2>&1 | tail -8
```

Expected: 7 pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/RefusalMessageBubble.svelte \
        web/src/lib/lq-ai/__tests__/RefusalMessageBubble.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): RefusalMessageBubble — kind=refusal inline message

Amber-tinted message bubble for tier-floor refusals. Three actions:
Re-run at enforced floor · Override for this turn (admin-only) ·
Why am I seeing this. Renders body with tier-string substitutions.
Provenance pills: 🔒 tier mismatch · 📜 audited (no provider pill —
no call was made).

7 unit tests cover render, tier substitution, role-based Override
visibility, button-event wiring, provenance pills.

Refs Wave D.1 plan T13 (spec §7.4).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 14: Component — `TierFloorOverrideModal.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/TierFloorOverrideModal.svelte`
- Create: `web/src/lib/lq-ai/__tests__/TierFloorOverrideModal.test.ts`

**Background:**
Confirmation modal opened by RefusalMessageBubble. Required textarea (10..500 chars). On confirm → calls `overrideTierFloor(messageId, reason)`. On 200 → fires `onSuccess(newAiMessage)`. On error → inline error banner.

**Props:**
- `open: boolean`
- `messageId: string`
- `originalTier: string` — e.g. "standard" — for display copy
- `enforcedTier: string` — e.g. "privileged"
- `onClose: () => void`
- `onSuccess: (newMessage: Message) => void`

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/lq-ai/__tests__/TierFloorOverrideModal.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import TierFloorOverrideModal from '../components/TierFloorOverrideModal.svelte';
import * as overrideApi from '../api/inferenceOverride';

describe('TierFloorOverrideModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when closed', () => {
    const { queryByText } = render(TierFloorOverrideModal, {
      open: false, messageId: 'm1', originalTier: 'standard', enforcedTier: 'privileged',
      onClose: () => {}, onSuccess: () => {},
    });
    expect(queryByText(/override tier floor/i)).toBeNull();
  });

  it('renders title + reason field + buttons when open', () => {
    const { getByText, getByLabelText } = render(TierFloorOverrideModal, {
      open: true, messageId: 'm1', originalTier: 'standard', enforcedTier: 'privileged',
      onClose: () => {}, onSuccess: () => {},
    });
    expect(getByText(/override tier floor/i)).toBeTruthy();
    expect(getByLabelText(/reason/i)).toBeTruthy();
    expect(getByText(/cancel/i)).toBeTruthy();
    expect(getByText(/confirm/i)).toBeTruthy();
  });

  it('disables Confirm when reason < 10 chars', async () => {
    const { getByLabelText, getByText } = render(TierFloorOverrideModal, {
      open: true, messageId: 'm1', originalTier: 'standard', enforcedTier: 'privileged',
      onClose: () => {}, onSuccess: () => {},
    });
    const reasonField = getByLabelText(/reason/i);
    await fireEvent.input(reasonField, { target: { value: 'short' } });
    expect((getByText(/confirm/i).closest('button') as HTMLButtonElement).disabled).toBe(true);
  });

  it('Confirm calls overrideTierFloor and onSuccess', async () => {
    const fakeAi = { id: 'm2', kind: 'ai', content: 'overridden' };
    const overrideSpy = vi.spyOn(overrideApi, 'overrideTierFloor').mockResolvedValue({
      ai_message: fakeAi as any, routing_log_id: 'log1',
    });
    const onSuccess = vi.fn();
    const { getByLabelText, getByText } = render(TierFloorOverrideModal, {
      open: true, messageId: 'm1', originalTier: 'standard', enforcedTier: 'privileged',
      onClose: () => {}, onSuccess,
    });
    await fireEvent.input(getByLabelText(/reason/i), {
      target: { value: 'Urgent client request — partner risk-accepted' }
    });
    await fireEvent.click(getByText(/confirm/i));
    await waitFor(() => expect(overrideSpy).toHaveBeenCalledWith(
      'm1', 'Urgent client request — partner risk-accepted', expect.anything()
    ));
    expect(onSuccess).toHaveBeenCalledWith(fakeAi);
  });

  it('shows error banner on API failure', async () => {
    vi.spyOn(overrideApi, 'overrideTierFloor').mockRejectedValue(new Error('Backend exploded'));
    const { getByLabelText, getByText, findByText } = render(TierFloorOverrideModal, {
      open: true, messageId: 'm1', originalTier: 'standard', enforcedTier: 'privileged',
      onClose: () => {}, onSuccess: () => {},
    });
    await fireEvent.input(getByLabelText(/reason/i), {
      target: { value: 'Long enough reason here.' }
    });
    await fireEvent.click(getByText(/confirm/i));
    expect(await findByText(/backend exploded/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests (fail)**

```bash
cd web && npm run test:frontend -- --run TierFloorOverrideModal 2>&1 | tail -8
```

- [ ] **Step 3: Implement**

Create the component. Per spec §3.4: title, body paragraph with `{original_tier}` and `{enforced_tier}` substitutions, required textarea (visible counter "X/500"), Cancel + Confirm, inline error banner on API failure.

- [ ] **Step 4: Re-run tests**

Expected: 5 pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/components/TierFloorOverrideModal.svelte \
        web/src/lib/lq-ai/__tests__/TierFloorOverrideModal.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): TierFloorOverrideModal — admin reason confirmation

Required textarea (10..500 chars) with live counter. On confirm
calls inferenceOverride.ts which POSTs to /api/v1/inference/
override-tier-floor. On 200 fires onSuccess(newAiMessage); on
error shows inline banner.

5 unit tests cover render, reason validation, success flow, error
banner.

Refs Wave D.1 plan T14 (spec §7.4 override confirmation).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 15: MessageBubble dispatch + integration

**Files:**
- Modify: `web/src/lib/lq-ai/components/MessageBubble.svelte`
- Modify: `web/src/lib/lq-ai/types/Message.ts` (add `kind` field if missing)
- Modify: `web/src/lib/lq-ai/components/ChatPanel.svelte` (handle override-success → replace refusal with new AI in message list)

**Background:**
When `message.kind === 'refusal'`, render `RefusalMessageBubble` instead of the default bubble. ChatPanel owns the `TierFloorOverrideModal` state and handles the override-success → in-place replacement of the refusal in the rendered message list.

- [ ] **Step 1: Update Message type**

Modify `web/src/lib/lq-ai/types/Message.ts` (verify location with `find web/src/lib/lq-ai/types -name "Message*"`). Add:

```ts
export type MessageKind = 'user' | 'ai' | 'refusal' | 'system';

export interface Message {
  // existing fields...
  kind: MessageKind;
  // for refusal messages:
  refusal_reason?: string;
  requested_tier?: string;
  enforced_tier?: string;
}
```

- [ ] **Step 2: Update MessageBubble dispatch**

Modify `web/src/lib/lq-ai/components/MessageBubble.svelte`. At the top of the template, dispatch to RefusalMessageBubble when kind matches:

```svelte
<script lang="ts">
  import RefusalMessageBubble from './RefusalMessageBubble.svelte';
  // ... existing imports
  export let message: Message;
  export let currentUserRole: 'admin' | 'member' | 'viewer' = 'member';
  // event-bubbling props for refusal actions:
  export let onRefusalRerun: (msg: Message) => void = () => {};
  export let onRefusalOverrideRequested: (msg: Message) => void = () => {};
  export let onRefusalExplainerRequested: (msg: Message) => void = () => {};
</script>

{#if message.kind === 'refusal'}
  <RefusalMessageBubble
    {message}
    {currentUserRole}
    onRerun={() => onRefusalRerun(message)}
    onOverrideRequested={() => onRefusalOverrideRequested(message)}
    onExplainerRequested={() => onRefusalExplainerRequested(message)}
  />
{:else}
  <!-- existing default bubble rendering -->
{/if}
```

- [ ] **Step 3: Wire override flow in ChatPanel**

Modify `web/src/lib/lq-ai/components/ChatPanel.svelte` to own the override modal state + handle success:

```svelte
<script lang="ts">
  import TierFloorOverrideModal from './TierFloorOverrideModal.svelte';
  // ...
  let overrideModalOpen = false;
  let overrideMessage: Message | null = null;

  function handleRefusalOverrideRequested(msg: Message) {
    overrideMessage = msg;
    overrideModalOpen = true;
  }

  function handleRefusalRerun(msg: Message) {
    // Re-send the original user prompt; backend uses same /chat path
    // with tier_floor enforced. Need to find the preceding user msg.
    const userMsg = messages.find(m => m.created_at < msg.created_at && m.kind === 'user');
    if (userMsg) submitMessage(userMsg.content);
  }

  function handleOverrideSuccess(newAi: Message) {
    // Replace the refusal in-place with the new ai message
    if (overrideMessage) {
      const idx = messages.findIndex(m => m.id === overrideMessage!.id);
      if (idx >= 0) {
        messages[idx] = newAi;
        messages = [...messages];  // trigger reactivity
      }
    }
    overrideModalOpen = false;
    overrideMessage = null;
  }
</script>

<!-- in the message list rendering: -->
{#each messages as msg (msg.id)}
  <MessageBubble
    message={msg}
    {currentUserRole}
    onRefusalRerun={handleRefusalRerun}
    onRefusalOverrideRequested={handleRefusalOverrideRequested}
    onRefusalExplainerRequested={() => { /* open JIT or link */ }}
  />
{/each}

{#if overrideMessage}
  <TierFloorOverrideModal
    bind:open={overrideModalOpen}
    messageId={overrideMessage.id}
    originalTier={overrideMessage.requested_tier ?? 'unknown'}
    enforcedTier={overrideMessage.enforced_tier ?? 'unknown'}
    onClose={() => (overrideModalOpen = false)}
    onSuccess={handleOverrideSuccess}
  />
{/if}
```

- [ ] **Step 4: Smoke test in browser**

```bash
docker compose up -d --no-deps --build web 2>&1 | tail -3
```

Force a refusal by sending a chat in a privileged matter that asks for a standard model. Confirm the amber block renders. As admin: click Override → modal → reason → confirm → block replaces with AI response. As member: confirm Override button is hidden.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/lq-ai/types/Message.ts \
        web/src/lib/lq-ai/components/MessageBubble.svelte \
        web/src/lib/lq-ai/components/ChatPanel.svelte
git commit -s -m "$(cat <<'EOF'
feat(web): wire refusal dispatch + override flow in ChatPanel

MessageBubble dispatches to RefusalMessageBubble when
kind='refusal'. ChatPanel owns the TierFloorOverrideModal state,
the re-run handler, and the override-success in-place replacement
of the refusal message in the rendered list.

Adds kind + refusal_reason + requested_tier + enforced_tier to the
Message TS type.

Refs Wave D.1 plan T15 (spec §7.4 integration).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 16: `receiptsExport.ts` JSONL serializer

**Files:**
- Create: `web/src/lib/lq-ai/lib/receiptsExport.ts`
- Create: `web/src/lib/lq-ai/__tests__/receiptsExport.test.ts`

**Background:**
Browser-side download trigger: takes JSONL text + filename and triggers a `<a download>` blob download. Used by the Receipts drawer's export button.

- [ ] **Step 1: Write failing tests**

Create `web/src/lib/lq-ai/__tests__/receiptsExport.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { triggerJsonlDownload } from '../lib/receiptsExport';

describe('receiptsExport', () => {
  it('creates a blob and triggers an anchor click', () => {
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL')
      .mockImplementation(() => 'blob:fake');
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL')
      .mockImplementation(() => {});
    const anchorClickSpy = vi.fn();
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      if (tag === 'a') {
        return {
          set href(v: string) { (this as any)._href = v; },
          set download(v: string) { (this as any)._download = v; },
          click: anchorClickSpy,
          style: { display: '' },
        } as any;
      }
      return document.createElement(tag);
    }) as any);

    triggerJsonlDownload('{"a":1}\n{"b":2}', 'chat-c1-receipts.jsonl');

    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(anchorClickSpy).toHaveBeenCalled();
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:fake');
  });
});
```

- [ ] **Step 2: Implement**

Create `web/src/lib/lq-ai/lib/receiptsExport.ts`:

```ts
/**
 * Triggers a browser download of JSONL text under the given filename.
 * Wraps the URL.createObjectURL + anchor-click + revoke pattern.
 */
export function triggerJsonlDownload(jsonl: string, filename: string): void {
  const blob = new Blob([jsonl], { type: 'application/jsonl' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 3: Run tests**

```bash
cd web && npm run test:frontend -- --run receiptsExport 2>&1 | tail -5
```

Expected: 1 pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/lib/receiptsExport.ts \
        web/src/lib/lq-ai/__tests__/receiptsExport.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): receiptsExport — JSONL browser download helper

Wraps URL.createObjectURL + anchor-click + revoke for triggering
JSONL downloads from receipts. Used by ReceiptsDrawer's export
button.

Refs Wave D.1 plan T16 (spec §7.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 17: Component — `ReceiptsList.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/ReceiptsList.svelte`
- Create: `web/src/lib/lq-ai/__tests__/ReceiptsList.test.ts`

**Background:**
Pure render component fed by an array of `ReceiptEvent`. Shows: timestamp (HH:MM:SS) · kind icon · short description · expandable detail on click. Filter chips at the top.

**Props:**
- `events: ReceiptEvent[]`
- `selectedKinds: ReceiptEventKind[]` (default: all 6)
- `onFilterChange: (kinds: ReceiptEventKind[]) => void`

**Test cases:**

```ts
// web/src/lib/lq-ai/__tests__/ReceiptsList.test.ts
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import ReceiptsList from '../components/ReceiptsList.svelte';
import type { ReceiptEvent } from '../api/receipts';

const events: ReceiptEvent[] = [
  { ts: '2026-05-12T10:14:00Z', kind: 'message', detail: { message_kind: 'user', role: 'user' } },
  { ts: '2026-05-12T10:14:01Z', kind: 'inference', detail: { provider: 'anthropic', model: 'claude-opus-4-7' } },
  { ts: '2026-05-12T10:14:02Z', kind: 'audit', detail: { action: 'message.created' } },
  { ts: '2026-05-12T10:14:03Z', kind: 'skill', detail: { skill_name: 'nda-review' } },
  { ts: '2026-05-12T10:14:04Z', kind: 'retrieval', detail: { kb_id: 'kb1', chunk_count: 3 } },
  { ts: '2026-05-12T10:14:05Z', kind: 'error', detail: { refused: true, refusal_reason: 'tier_mismatch' } },
];

describe('ReceiptsList', () => {
  it('renders all 6 kinds when no filter', () => {
    const { container } = render(ReceiptsList, {
      events, selectedKinds: ['message','inference','audit','skill','retrieval','error'], onFilterChange: () => {},
    });
    expect(container.querySelectorAll('.receipt-row')).toHaveLength(6);
  });

  it('filters by selectedKinds', () => {
    const { container } = render(ReceiptsList, {
      events, selectedKinds: ['message', 'audit'], onFilterChange: () => {},
    });
    expect(container.querySelectorAll('.receipt-row')).toHaveLength(2);
  });

  it('shows formatted timestamp (HH:MM:SS)', () => {
    const { container } = render(ReceiptsList, {
      events, selectedKinds: ['message'], onFilterChange: () => {},
    });
    expect(container.textContent).toMatch(/10:14:00/);
  });

  it('renders kind icon for each event', () => {
    const { container } = render(ReceiptsList, {
      events, selectedKinds: ['message','inference','audit','skill','retrieval','error'], onFilterChange: () => {},
    });
    const text = container.textContent ?? '';
    expect(text).toContain('👤');  // user message
    expect(text).toContain('🧠');  // inference
    expect(text).toContain('📜');  // audit
    expect(text).toContain('🛠');  // skill
    expect(text).toContain('📎');  // retrieval
    expect(text).toContain('🛡');  // error/refusal
  });

  it('clicking row toggles expanded detail', async () => {
    const { container, getAllByRole } = render(ReceiptsList, {
      events: [events[1]], selectedKinds: ['inference'], onFilterChange: () => {},
    });
    const row = getAllByRole('button')[0];
    await fireEvent.click(row);
    expect(container.textContent).toContain('claude-opus-4-7');
  });

  it('filter chip click fires onFilterChange', async () => {
    const onFilterChange = vi.fn();
    const { getByText } = render(ReceiptsList, {
      events, selectedKinds: ['message','inference','audit','skill','retrieval','error'], onFilterChange,
    });
    await fireEvent.click(getByText(/events/i));
    expect(onFilterChange).toHaveBeenCalled();
  });

  it('renders empty-state when events is empty', () => {
    const { getByText } = render(ReceiptsList, {
      events: [], selectedKinds: ['message'], onFilterChange: () => {},
    });
    expect(getByText(/no receipts yet/i)).toBeTruthy();
  });
});
```

- [ ] **Step 1: Run tests (fail)**

```bash
cd web && npm run test:frontend -- --run ReceiptsList 2>&1 | tail -8
```

- [ ] **Step 2: Implement**

Create `web/src/lib/lq-ai/components/ReceiptsList.svelte`. Layout per spec §3.5 + the design mockup from brainstorming.

- [ ] **Step 3: Run tests until green**

Expected: 7 pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/components/ReceiptsList.svelte \
        web/src/lib/lq-ai/__tests__/ReceiptsList.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): ReceiptsList — chronological events with filter chips

Pure-render component for the chronological event list inside the
Receipts drawer. Six kind chips (all / events / retrievals /
providers / audit / errors). HH:MM:SS timestamp + kind icon + short
description + expand-on-click for full detail. Empty-state copy.

7 unit tests cover render, filtering, timestamp formatting, icon
dispatch, expand, chip click, empty-state.

Refs Wave D.1 plan T17 (spec §7.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 18: Component — `ReceiptsDrawer.svelte`

**Files:**
- Create: `web/src/lib/lq-ai/components/ReceiptsDrawer.svelte`
- Create: `web/src/lib/lq-ai/__tests__/ReceiptsDrawer.test.ts`

**Background:**
Right-side toggleable drawer (240px width). Owns the data-fetching for receipts (calls `listChatReceipts` on open + polls every 5s while open). Hosts `ReceiptsList`. Hosts the export-JSONL button which calls `exportChatReceiptsJsonl` + `triggerJsonlDownload`. localStorage persistence of open/closed state per chat.

**Props:**
- `open: boolean` (two-way bind)
- `chatId: string`
- `onClose: () => void`

**Test cases:**

```ts
// web/src/lib/lq-ai/__tests__/ReceiptsDrawer.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import ReceiptsDrawer from '../components/ReceiptsDrawer.svelte';
import * as receiptsApi from '../api/receipts';
import * as exportLib from '../lib/receiptsExport';

const sampleEvents = [
  { ts: '2026-05-12T10:14:00Z', kind: 'message' as const, detail: { message_kind: 'user' } },
];

describe('ReceiptsDrawer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(receiptsApi, 'listChatReceipts').mockResolvedValue(sampleEvents);
  });
  afterEach(() => { vi.useRealTimers(); });

  it('renders nothing when open=false', () => {
    const { queryByText } = render(ReceiptsDrawer, {
      open: false, chatId: 'c1', onClose: () => {},
    });
    expect(queryByText(/receipts/i)).toBeNull();
  });

  it('fetches receipts on mount when open=true', async () => {
    const spy = vi.spyOn(receiptsApi, 'listChatReceipts').mockResolvedValue(sampleEvents);
    render(ReceiptsDrawer, { open: true, chatId: 'c1', onClose: () => {} });
    await waitFor(() => expect(spy).toHaveBeenCalledWith('c1', undefined, expect.anything()));
  });

  it('persists open-state to localStorage keyed by chat', async () => {
    render(ReceiptsDrawer, { open: true, chatId: 'c1', onClose: () => {} });
    await waitFor(() => {
      expect(localStorage.getItem('lq_ai_receipts_drawer_open_c1')).toBe('true');
    });
  });

  it('Close button fires onClose', async () => {
    const onClose = vi.fn();
    const { getByLabelText } = render(ReceiptsDrawer, { open: true, chatId: 'c1', onClose });
    await fireEvent.click(getByLabelText(/close/i));
    expect(onClose).toHaveBeenCalled();
  });

  it('polls every 5s while open', async () => {
    const spy = vi.spyOn(receiptsApi, 'listChatReceipts').mockResolvedValue(sampleEvents);
    render(ReceiptsDrawer, { open: true, chatId: 'c1', onClose: () => {} });
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    vi.advanceTimersByTime(5100);
    await waitFor(() => expect(spy.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('Export button calls exportChatReceiptsJsonl + triggerJsonlDownload', async () => {
    vi.spyOn(receiptsApi, 'exportChatReceiptsJsonl').mockResolvedValue({
      jsonl: '{"a":1}', filename: 'chat-c1-receipts.jsonl',
    });
    const triggerSpy = vi.spyOn(exportLib, 'triggerJsonlDownload').mockImplementation(() => {});
    const { findByText } = render(ReceiptsDrawer, { open: true, chatId: 'c1', onClose: () => {} });
    const btn = await findByText(/export/i);
    await fireEvent.click(btn);
    await waitFor(() => expect(triggerSpy).toHaveBeenCalledWith('{"a":1}', 'chat-c1-receipts.jsonl'));
  });
});
```

- [ ] **Step 1: Run tests (fail)**

```bash
cd web && npm run test:frontend -- --run ReceiptsDrawer 2>&1 | tail -8
```

- [ ] **Step 2: Implement**

Create `web/src/lib/lq-ai/components/ReceiptsDrawer.svelte`. Drawer chrome per spec §3.5 / brainstorm mock: 240px wide, header with `📜 Receipts` + close button, ReceiptsList in the body, export button in sticky footer. Set up `setInterval(5000)` poll while open; clear on close/unmount. Persist open state to `localStorage[lq_ai_receipts_drawer_open_{chatId}]` on every state change.

- [ ] **Step 3: Run tests until green**

Expected: 6 pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/lq-ai/components/ReceiptsDrawer.svelte \
        web/src/lib/lq-ai/__tests__/ReceiptsDrawer.test.ts
git commit -s -m "$(cat <<'EOF'
feat(web): ReceiptsDrawer — toggleable right-side receipts drawer

240px drawer with header (📜 Receipts + close), ReceiptsList body,
export-JSONL footer. Fetches receipts on open; polls every 5s while
open; clears on close. Open-state persists per-chat in localStorage.
Export button serializes via api/receipts.exportChatReceiptsJsonl
then triggers browser download via lib/receiptsExport.

6 unit tests cover render gating, on-mount fetch, localStorage
persistence, close-button, polling, export-button.

Refs Wave D.1 plan T18 (spec §7.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 19: Wire `ReceiptsDrawer` into ChatPanel + 📜 toggle

**Files:**
- Modify: `web/src/lib/lq-ai/components/ChatPanel.svelte`

**Background:**
Composer toolbar already has a 📜 button (added in mock — verify or add). Clicking it toggles `receiptsDrawerOpen`. Drawer renders adjacent to the chat body, right side.

- [ ] **Step 1: Wire**

Modify `web/src/lib/lq-ai/components/ChatPanel.svelte`:

```svelte
<script lang="ts">
  // existing imports...
  import ReceiptsDrawer from './ReceiptsDrawer.svelte';
  // existing props...
  export let chatId: string | null = null;

  let receiptsDrawerOpen = false;

  // Restore open state from localStorage at mount
  $: if (chatId && typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(`lq_ai_receipts_drawer_open_${chatId}`);
    if (stored === 'true') receiptsDrawerOpen = true;
  }
</script>

<div class="chat-shell" style="display:flex">
  <div class="chat-body" style="flex:1;display:flex;flex-direction:column">
    <!-- existing message list -->
    <!-- composer toolbar: -->
    <div class="composer-toolbar">
      <button title="Attach KB" on:click={() => (attachKbModalOpen = true)}>📎</button>
      <button title="Enhance prompt" on:click={handleEnhance}>✨</button>
      <button title="Receipts" on:click={() => (receiptsDrawerOpen = !receiptsDrawerOpen)}>📜</button>
      <!-- existing send / etc -->
    </div>
    <!-- existing composer textarea -->
  </div>

  {#if chatId && receiptsDrawerOpen}
    <ReceiptsDrawer
      bind:open={receiptsDrawerOpen}
      {chatId}
      onClose={() => (receiptsDrawerOpen = false)}
    />
  {/if}
</div>
```

- [ ] **Step 2: Smoke test in browser**

```bash
docker compose up -d --no-deps --build web 2>&1 | tail -3
```

Open `http://localhost:3000/lq-ai/matters/<id>`. Send a message. Click 📜 → drawer opens with events. Filter chip → list updates. Export → file downloads. Reload page → drawer state persists.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/lq-ai/components/ChatPanel.svelte
git commit -s -m "$(cat <<'EOF'
feat(web): wire ReceiptsDrawer + 📜 toggle into ChatPanel

Composer toolbar 📜 button toggles receiptsDrawerOpen. Drawer
mounts to the right of the chat body when open. Open state
restored from localStorage on chat change so it survives reloads.

Refs Wave D.1 plan T19 (spec §3.5 composition).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 20: Enhance Prompt audit-and-delta

**Files:**
- Modify (as needed): `web/src/lib/lq-ai/components/EnhancePromptExpansion.svelte`, `Composer.svelte`, `MessageBubble.svelte`, `/lq-ai/settings/appearance/+page.svelte`

**Background:**
EnhancePromptExpansion already exists (429 lines). Grade against spec §7.1 and ship the deltas. Likely 1-3 commits.

- [ ] **Step 1: Audit current state against §7.1**

Read each existing file and grade:

```bash
cd /Users/kevinkeller/Desktop/lq-ai
sed -n '1,30p' web/src/lib/lq-ai/components/EnhancePromptExpansion.svelte
grep -nE "Use enhanced|Edit enhanced|Keep original|onUseEnhanced|onEditEnhanced|onKeepOriginal" web/src/lib/lq-ai/components/EnhancePromptExpansion.svelte
grep -rnE "auto.enhance|⌘E|cmd.*e\b" web/src/ | head -5
grep -rnE "enhanced.*pill|✨.*pill|ProvenancePill.*enhance" web/src/lib/lq-ai/components/MessageBubble.svelte 2>&1
```

Score against this checklist:

| §7.1 requirement | Verify |
|---|---|
| ✨ button in composer toolbar | already present |
| `⌘E` keyboard shortcut | grep should find it |
| Inline expansion below composer | already present |
| Three actions: Use / Edit / Keep | already present (handlers exist) |
| First-time JIT post-action toast | verify ProvenancePill or JIT manager |
| `✨ enhanced` provenance pill on sent | verify MessageBubble dispatch |
| Tap pill → diff view | verify |
| Settings: auto-enhance on send | search `/lq-ai/settings/appearance` |
| Empty composer disables button | verify |
| >500-token prompt → "Refine" framing | verify |
| Error → inline retry | verify |

For each row in the checklist that's MISSING, add it. For each PRESENT, no work. The audit produces a delta list which becomes the implementation TODO for this task.

- [ ] **Step 2: Ship the deltas**

For each missing item, write the code + unit test (if it's a component behavior). Commit each delta as its own atomic commit with message `fix(web): enhance prompt — add <feature> per spec §7.1`. Typical deltas:
- Adding `⌘E` keyboard handler to Composer
- Adding "Refine" label switch when input token count > 500 (estimate as char count / 4)
- Adding auto-enhance toggle to settings (look at Wave A's user-preference helpers)
- Wiring the `✨ enhanced` provenance pill into MessageBubble if missing

If the audit shows NO gaps (current implementation matches spec exactly), commit a single no-op verification:

```bash
git commit -s --allow-empty -m "$(cat <<'EOF'
chore(web): Enhance Prompt — audit complete, spec §7.1 already met

Audited EnhancePromptExpansion.svelte + Composer.svelte +
MessageBubble.svelte against spec §7.1. All 11 requirements
already implemented from prior waves. No code changes needed.

Refs Wave D.1 plan T20.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 3: Run all Vitest tests to verify no regressions**

```bash
cd web && npm run test:frontend -- --run 2>&1 | tail -5
```

Expected: all tests pass, count = previous + new tests added by T8-T19.

---

## Task 21: Cypress E2E

**Files:**
- Create: `web/cypress/e2e/wave-d1-power-features.cy.ts`

**Background:**
Five scenarios per spec §5 testing strategy: enhance prompt cycle, KB attach modal, tier-floor refusal + override, receipts drawer, refusal without override permission.

- [ ] **Step 1: Write the Cypress spec**

Create `web/cypress/e2e/wave-d1-power-features.cy.ts`:

```ts
describe('Wave D.1 — in-chat power features', () => {
  beforeEach(() => {
    cy.lqAiLogin('admin@lq.ai', Cypress.env('LQ_AI_ADMIN_PASSWORD'));
  });

  it('enhance prompt: ⌘E expands, Use sends with provenance pill', () => {
    cy.visit('/lq-ai/chats');
    cy.get('[data-testid="composer-input"]').type('draft an NDA');
    cy.get('body').type('{cmd}e');
    cy.contains(/enhanced/i).should('be.visible');
    cy.contains(/use enhanced/i).click();
    cy.contains(/✨/).should('be.visible');  // provenance pill on sent message
  });

  it('KB attach modal: composer 📎 → multi-select → attach → rail updates', () => {
    cy.lqAiOpenSampleMatter();
    cy.get('[data-testid="composer-attach-kb"]').click();
    cy.contains(/attach knowledge bases/i).should('be.visible');
    cy.get('input[type=checkbox]').first().check();
    cy.contains(/attach 1 selected/i).click();
    cy.contains(/attach knowledge bases/i).should('not.exist');
    // matter rail KB section should now show the attached KB
    cy.get('[data-testid="matter-rail-knowledge"]').should('contain', /NDA-Playbook|sample/i);
  });

  it('tier-floor refusal: amber block renders, override succeeds (admin)', () => {
    cy.lqAiOpenPrivilegedMatter();
    cy.get('[data-testid="composer-input"]').type(
      'Quick rough draft — standard model is fine'
    );
    cy.get('[data-testid="composer-send"]').click();
    cy.contains(/refused at privileged-floor/i, { timeout: 30000 }).should('be.visible');
    cy.contains(/override for this turn/i).click();
    cy.get('textarea[name=reason]').type(
      'Urgent — partner risk-accepted (Cypress E2E test reason)'
    );
    cy.contains(/^confirm$/i).click();
    cy.contains(/refused at privileged-floor/i, { timeout: 30000 }).should('not.exist');
    // expect a kind=ai message in its place
  });

  it('receipts drawer: 📜 toggles, filter + export work', () => {
    cy.lqAiOpenSampleMatter();
    cy.get('[data-testid="composer-input"]').type('hello');
    cy.get('[data-testid="composer-send"]').click();
    cy.get('[data-testid="composer-receipts-toggle"]').click();
    cy.contains(/📜 Receipts/i).should('be.visible');
    // filter chips
    cy.contains(/events/i).click();
    cy.contains(/audit/i).should('be.visible');
    // export
    cy.contains(/export jsonl/i).click();
    cy.readFile(`cypress/downloads/chat-${'??'}-receipts.jsonl`, { timeout: 5000 })
      .should((content: string) => {
        expect(content).to.contain('"kind":"message"');
      });
  });

  it('refusal without override: member sees Re-run only', () => {
    cy.lqAiLogin('member@lq.ai', Cypress.env('LQ_AI_MEMBER_PASSWORD'));
    cy.lqAiOpenPrivilegedMatter();
    cy.get('[data-testid="composer-input"]').type('rough draft please');
    cy.get('[data-testid="composer-send"]').click();
    cy.contains(/refused at privileged-floor/i, { timeout: 30000 }).should('be.visible');
    cy.contains(/re-run at privileged-floor/i).should('be.visible');
    cy.contains(/override for this turn/i).should('not.exist');
  });
});
```

Add `lqAiLogin`, `lqAiOpenSampleMatter`, `lqAiOpenPrivilegedMatter` to `web/cypress/support/commands.ts` if not already present (mirror Wave C's Cypress helpers).

- [ ] **Step 2: Run Cypress**

```bash
cd web && npx cypress run --spec cypress/e2e/wave-d1-power-features.cy.ts 2>&1 | tail -30
```

Expected: 5 specs pass. If any spec depends on a member-user fixture and one doesn't exist, create it in the `beforeEach` or in a seed script.

- [ ] **Step 3: Commit**

```bash
git add web/cypress/e2e/wave-d1-power-features.cy.ts \
        web/cypress/support/commands.ts
git commit -s -m "$(cat <<'EOF'
test(web): Cypress E2E for Wave D.1 power features

Five scenarios covering: enhance prompt expand + use + pill ·
KB attach modal multi-select → rail update · tier-floor refusal +
admin override · receipts drawer toggle + filter + export ·
refusal without override permission shows Re-run only.

Refs Wave D.1 plan T21 (spec §5).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Definition of done

Wave D.1 ships when all of:

1. Migrations 0020 + 0021 applied; backfill verified.
2. Backend endpoints implemented: project-KB attach/detach, inference/override-tier-floor (admin-gated), chats/{id}/receipts (JSON + export.jsonl), KB retrieval audit-row write at hybrid_search call site.
3. Frontend API clients: projectKnowledgeBases, inferenceOverride, receipts.
4. Frontend components: AttachKBModal, RefusalMessageBubble, TierFloorOverrideModal, ReceiptsExport (lib), ReceiptsList, ReceiptsDrawer.
5. Composer toolbar carries 📎 (KB attach) · ✨ (enhance) · 📜 (receipts) buttons; MessageBubble dispatches to RefusalMessageBubble on kind='refusal'; ChatPanel owns override-modal + receipts-drawer state.
6. Enhance Prompt audited against spec §7.1; gaps shipped.
7. Cypress E2E suite (5 scenarios) passes.
8. Vitest baseline grows by ~35-45 tests (covered tasks 8-19); zero regressions.
9. Pytest integration baseline grows by ~25 tests (covered tasks 1-7); zero regressions.
10. Zero V2-FALLBACKs introduced (Wave C precedent).
11. Every commit DCO-signed + Co-Author trailer + Conventional Commit prefix + pushed.
12. Smoke-tested in real browser: log in as admin → open matter → exercise each of 4 features → verify receipts drawer + refusal flow + KB attach modal + enhance prompt all behave per spec.

---

## Out-of-scope items routed forward

- **Skill Creator wizard + try-it (§7.2)** → Wave D.2 (separate brainstorm + spec + plan cycle).
- **`/lq-ai/knowledge` standalone browser surface + entry-point 3 to AttachKBModal** → Wave F.
- **`/lq-ai/saved-prompts` surface** → Wave F.
- **Outputs panel · Citation Engine UI** → Wave F.
- **Per-user `override_tier_floor` permission grant** → v1.1+ if operator demand surfaces.
- **Materialized `chat_receipts` table** → v1.1+ if replay-at-read latency degrades.
- **Audit log (§7.5) extensions: cross-links + saved filters + advanced export** → Wave F.
