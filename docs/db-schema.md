# LQ.AI — Canonical Database Schema

> **Purpose:** Single source of truth for the LQ.AI PostgreSQL schema. Every table, column, foreign key, and index lands here. When a feature requires a schema change, this document is updated in the same PR as the Alembic migration that implements it. Drift between this document and the migrations indicates a process failure.

The schema runs on PostgreSQL 16 with the `pgvector` extension for vector storage and `pg_trgm` for fuzzy text matching. The full-text search uses Postgres' built-in `tsvector` rather than an external service.

This document is structured by subsystem; tables that span subsystems (audit log, inference routing log) have their own section.

---

## Conventions

- **Primary keys:** all tables use UUID v7 (`uuid_generate_v7()`) as primary keys for time-ordered insertion. Where v7 is unavailable, v4 is acceptable.
- **Timestamps:** `TIMESTAMPTZ` (with timezone). `created_at` and `updated_at` are required on every entity table; `updated_at` is set by trigger on UPDATE.
- **Soft deletes:** entities that should retain history use `deleted_at TIMESTAMPTZ NULL`. Hard deletes are reserved for GDPR Article 17 requests after the grace period.
- **Foreign keys:** named explicitly (`fk_<source_table>_<column>`); ON DELETE behavior specified.
- **Indexes:** named explicitly (`idx_<table>_<columns>`); composite indexes ordered by selectivity.
- **JSONB vs. dedicated tables:** dedicated tables for any field queried by index; JSONB for opaque payloads (audit details, skill examples on disk).
- **Naming:** snake_case for all identifiers; pluralized table names; singular column names.

---

## Core entity tables

### `users`

```sql
CREATE TABLE users (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    email                 CITEXT NOT NULL UNIQUE,
    display_name          TEXT,
    hashed_password       TEXT NOT NULL,
    is_admin              BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_enabled           BOOLEAN NOT NULL DEFAULT FALSE,
    must_change_password  BOOLEAN NOT NULL DEFAULT FALSE,  -- B2: first-run admin + reset-admin
    totp_secret           TEXT,
    recovery_codes        TEXT[],  -- bcrypt-hashed
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at         TIMESTAMPTZ,
    deleted_at            TIMESTAMPTZ,
    deletion_scheduled_at TIMESTAMPTZ
);

CREATE INDEX idx_users_email_active ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_deletion_scheduled ON users(deletion_scheduled_at) WHERE deletion_scheduled_at IS NOT NULL;
```

`must_change_password` is set to TRUE for:
- the auto-created first-run admin (Task B2 / migration `0002`),
- any user touched by `python -m app.cli reset-admin-password`.

Authenticated endpoints (other than `GET /users/me`, `POST /auth/logout`, and `POST /auth/change-password`) return HTTP 403 with `error.code = "password_change_required"` while this flag is true. The flag is cleared by a successful `POST /auth/change-password`.

### `user_sessions`

Refresh tokens, hashed; access tokens are stateless JWTs.

```sql
CREATE TABLE user_sessions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash  TEXT NOT NULL,
    user_agent          TEXT,
    ip_address          INET,
    expires_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at          TIMESTAMPTZ
);

CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_token_hash ON user_sessions(refresh_token_hash) WHERE revoked_at IS NULL;
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);
```

---

## Projects (matter-scoped containers)

### `projects`

```sql
CREATE TABLE projects (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    name                     TEXT NOT NULL,
    description              TEXT,
    context                  TEXT,  -- free-form markdown
    owner_id                 UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    privileged               BOOLEAN NOT NULL DEFAULT FALSE,
    minimum_inference_tier   SMALLINT CHECK (minimum_inference_tier BETWEEN 1 AND 5),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at               TIMESTAMPTZ,
    CONSTRAINT chk_privileged_implies_tier CHECK (
        NOT privileged OR minimum_inference_tier IS NOT NULL
    )
);

CREATE INDEX idx_projects_owner_active ON projects(owner_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_projects_privileged ON projects(privileged) WHERE privileged = TRUE AND deleted_at IS NULL;
```

### `project_attached_skills` and `project_attached_files`

Many-to-many join tables. A project can have multiple skills attached and multiple files attached.

```sql
CREATE TABLE project_attached_skills (
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    skill_name   TEXT NOT NULL,
    skill_version TEXT,  -- NULL means latest
    attached_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, skill_name)
);

CREATE TABLE project_attached_files (
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_id      UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    attached_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, file_id)
);

CREATE INDEX idx_project_attached_files_file ON project_attached_files(file_id);
```

---

## Chats and messages

### `chats`

```sql
CREATE TABLE chats (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    title       TEXT,
    owner_id    UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    project_id  UUID REFERENCES projects(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);

CREATE INDEX idx_chats_owner_active ON chats(owner_id, updated_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_chats_project ON chats(project_id) WHERE project_id IS NOT NULL AND deleted_at IS NULL;
```

### `chat_attached_skills` and `chat_attached_files`

```sql
CREATE TABLE chat_attached_skills (
    chat_id      UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    skill_name   TEXT NOT NULL,
    skill_version TEXT,
    skill_inputs JSONB,  -- per-skill input values
    attached_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, skill_name)
);

CREATE TABLE chat_attached_files (
    chat_id      UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    file_id      UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    attached_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, file_id)
);
```

### `messages`

```sql
CREATE TABLE messages (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    chat_id                  UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role                     TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content                  TEXT NOT NULL,
    model                    TEXT,
    provider                 TEXT,
    routed_inference_tier    SMALLINT CHECK (routed_inference_tier BETWEEN 1 AND 5),
    tokens_in                INTEGER,
    tokens_out               INTEGER,
    cost_estimate            NUMERIC(10,4),
    latency_ms               INTEGER,
    error                    TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_chat ON messages(chat_id, created_at);
CREATE INDEX idx_messages_routed_tier ON messages(routed_inference_tier, created_at);
```

### `message_citations`

```sql
CREATE TABLE message_citations (
    id                        UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    message_id                UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    source_file_id            UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    source_offset_start       INTEGER NOT NULL,
    source_offset_end         INTEGER NOT NULL,
    source_page               INTEGER,
    source_text               TEXT NOT NULL,
    verified                  BOOLEAN NOT NULL DEFAULT FALSE,
    verification_method       TEXT,  -- 'exact-match', 'llm-judge', 'failed'
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_offsets CHECK (source_offset_end > source_offset_start)
);

CREATE INDEX idx_message_citations_message ON message_citations(message_id);
CREATE INDEX idx_message_citations_file ON message_citations(source_file_id);
```

---

## Skills

Skills are stored both on disk (the canonical source for built-in skills loaded at startup) and in the database (for user-scoped and team-scoped skills, plus any forks of built-ins).

### `skills`

```sql
CREATE TABLE skills (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    name                     TEXT NOT NULL,
    version                  TEXT NOT NULL,
    scope                    TEXT NOT NULL CHECK (scope IN ('builtin','user','team')),
    owner_id                 UUID REFERENCES users(id) ON DELETE CASCADE,
    is_organization_profile  BOOLEAN NOT NULL DEFAULT FALSE,
    title                    TEXT NOT NULL,
    description              TEXT NOT NULL,
    tags                     TEXT[],
    jurisdiction             TEXT,
    output_format            TEXT NOT NULL CHECK (output_format IN ('report','issues_list','table','redline')),
    minimum_inference_tier   SMALLINT CHECK (minimum_inference_tier BETWEEN 1 AND 5),
    use_organization_profile BOOLEAN NOT NULL DEFAULT TRUE,
    self_improvement         BOOLEAN NOT NULL DEFAULT FALSE,
    content_yaml             TEXT NOT NULL,  -- frontmatter
    content_md               TEXT NOT NULL,  -- body
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at               TIMESTAMPTZ,
    UNIQUE (name, version, scope, owner_id),
    CONSTRAINT chk_org_profile_singleton CHECK (
        NOT is_organization_profile OR (scope = 'team' AND owner_id IS NULL)
    )
);

CREATE UNIQUE INDEX idx_skills_org_profile_singleton 
    ON skills(is_organization_profile) 
    WHERE is_organization_profile = TRUE AND deleted_at IS NULL;
CREATE INDEX idx_skills_name_active ON skills(name) WHERE deleted_at IS NULL;
CREATE INDEX idx_skills_owner_active ON skills(owner_id, scope) WHERE deleted_at IS NULL;
```

The `idx_skills_org_profile_singleton` partial unique index enforces that there is at most one Organization Profile in the deployment.

### `skill_reference_files` and `skill_example_files`

Reference and example files associated with a skill. For built-in skills these are loaded from disk at startup; user/team skills store them here.

```sql
CREATE TABLE skill_reference_files (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    skill_id     UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    path         TEXT NOT NULL,  -- e.g. 'reference/severity_rubric.md'
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (skill_id, path)
);

CREATE TABLE skill_example_files (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    skill_id     UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    path         TEXT NOT NULL,  -- e.g. 'examples/example_recipient.md'
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (skill_id, path)
);
```

---

## Files and document pipeline

### `files`

Original uploaded files; the bytes themselves live in object storage (MinIO/S3).

```sql
CREATE TABLE files (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
    filename        TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    hash_sha256     TEXT NOT NULL,
    storage_path    TEXT NOT NULL,  -- object-storage key
    ingestion_status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (ingestion_status IN ('pending','processing','ready','failed')),
    ingestion_error TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_files_owner_active ON files(owner_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_files_project ON files(project_id) WHERE project_id IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX idx_files_status ON files(ingestion_status) WHERE ingestion_status IN ('pending','processing');
CREATE INDEX idx_files_hash ON files(hash_sha256);  -- dedup detection
```

### `documents`

Parsed-document metadata after the document pipeline runs.

```sql
CREATE TABLE documents (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    file_id             UUID NOT NULL UNIQUE REFERENCES files(id) ON DELETE CASCADE,
    parser              TEXT NOT NULL,  -- 'docling', 'pymupdf', 'docling+ocr'
    page_count          INTEGER,
    character_count     INTEGER,
    structured_content  JSONB,  -- Docling's structured representation
    processed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `document_chunks`

Chunked content with embeddings and full-text indexing.

```sql
CREATE TABLE document_chunks (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    document_id          UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index          INTEGER NOT NULL,
    content              TEXT NOT NULL,
    page_start           INTEGER,
    page_end             INTEGER,
    char_offset_start    INTEGER NOT NULL,
    char_offset_end      INTEGER NOT NULL,
    embedding            VECTOR(1536),  -- adjust dim per embedding model
    content_tsv          TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    metadata             JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_chunks_tsv ON document_chunks USING gin (content_tsv);
CREATE INDEX idx_chunks_document ON document_chunks(document_id, chunk_index);
```

The `ivfflat` index is appropriate for moderate scale; transition to `hnsw` (Postgres 16+) for larger deployments.

---

## Knowledge bases

### `knowledge_bases`

```sql
CREATE TABLE knowledge_bases (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    name         TEXT NOT NULL,
    description  TEXT,
    owner_id     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    project_id   UUID REFERENCES projects(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX idx_kbs_owner_active ON knowledge_bases(owner_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_kbs_project ON knowledge_bases(project_id) WHERE project_id IS NOT NULL;
```

### `knowledge_base_files`

```sql
CREATE TABLE knowledge_base_files (
    kb_id        UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    file_id      UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    added_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kb_id, file_id)
);
```

---

## Saved prompts (per [DE-013](docs/PRD.md#de-013--saved-prompts-library) / Issue 04)

```sql
CREATE TABLE saved_prompts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    tags        TEXT[],
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_saved_prompts_user ON saved_prompts(user_id, updated_at DESC);
CREATE INDEX idx_saved_prompts_tags ON saved_prompts USING gin (tags);
```

---

## Audit log (cross-cutting)

The most consequential table in the schema. Every privilege-affecting action lands here. Privileged-marked entries and routed-inference-tier values are first-class fields, not buried in JSONB.

### `audit_log`

```sql
CREATE TABLE audit_log (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    timestamp             TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id               UUID REFERENCES users(id) ON DELETE SET NULL,
    action                TEXT NOT NULL,           -- e.g. 'chat.create', 'message.send', 'skill.fork'
    resource_type         TEXT NOT NULL,           -- e.g. 'chat', 'project', 'skill'
    resource_id           TEXT,                    -- typically a UUID stringified
    privilege_marked      BOOLEAN NOT NULL DEFAULT FALSE,
    privilege_basis       TEXT,                    -- 'project_privileged_flag', 'matter_attorney_directive', etc.
    routed_inference_tier SMALLINT CHECK (routed_inference_tier BETWEEN 1 AND 5),
    routed_provider       TEXT,
    ip_address            INET,
    user_agent            TEXT,
    request_id            TEXT,                    -- correlation across services
    details               JSONB,                   -- opaque payload, queryable but not indexed by default
    CONSTRAINT chk_privileged_with_basis CHECK (
        NOT privilege_marked OR privilege_basis IS NOT NULL
    )
);

CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_log_user_timestamp ON audit_log(user_id, timestamp DESC);
CREATE INDEX idx_audit_log_resource ON audit_log(resource_type, resource_id);
CREATE INDEX idx_audit_log_privileged ON audit_log(privilege_marked, timestamp DESC) WHERE privilege_marked = TRUE;
CREATE INDEX idx_audit_log_tier ON audit_log(routed_inference_tier, timestamp DESC) WHERE routed_inference_tier IS NOT NULL;
```

The audit log is **append-only** at the application layer; the database does not enforce this directly (the maintainer-team can add a trigger if desired).

### `inference_routing_log`

Distinct from the general audit log because it has a different access pattern (every inference request, hot path) and different retention policy (operator-configurable, often shorter than audit log). Not a simple subset of audit_log.

```sql
CREATE TABLE inference_routing_log (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    timestamp                TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id                  UUID REFERENCES users(id) ON DELETE SET NULL,
    chat_id                  UUID REFERENCES chats(id) ON DELETE SET NULL,
    message_id               UUID REFERENCES messages(id) ON DELETE SET NULL,
    requested_model          TEXT,
    routed_provider          TEXT NOT NULL,
    routed_model             TEXT NOT NULL,
    routed_inference_tier    SMALLINT NOT NULL CHECK (routed_inference_tier BETWEEN 1 AND 5),
    tokens_in                INTEGER,
    tokens_out               INTEGER,
    cost_estimate            NUMERIC(10,4),
    latency_ms               INTEGER,
    anonymization_applied    BOOLEAN NOT NULL DEFAULT FALSE,
    refused                  BOOLEAN NOT NULL DEFAULT FALSE,
    refusal_reason           TEXT,                    -- 'tier_below_minimum', 'provider_unavailable', etc.
    request_id               TEXT
);

CREATE INDEX idx_inference_log_timestamp ON inference_routing_log(timestamp DESC);
CREATE INDEX idx_inference_log_user ON inference_routing_log(user_id, timestamp DESC) WHERE user_id IS NOT NULL;
CREATE INDEX idx_inference_log_tier_time ON inference_routing_log(routed_inference_tier, timestamp DESC);
CREATE INDEX idx_inference_log_provider_time ON inference_routing_log(routed_provider, timestamp DESC);
CREATE INDEX idx_inference_log_refused ON inference_routing_log(timestamp DESC) WHERE refused = TRUE;
```

---

## M3+ tables (sketched, land at the indicated milestone)

### `playbooks` (M3)

```sql
CREATE TABLE playbooks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    name            TEXT NOT NULL,
    version         TEXT NOT NULL,
    scope           TEXT NOT NULL CHECK (scope IN ('builtin','user','team')),
    owner_id        UUID REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT,
    content_yaml    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE (name, version, scope, owner_id)
);
```

### `playbook_runs` (M3)

```sql
CREATE TABLE playbook_runs (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    playbook_id       UUID NOT NULL REFERENCES playbooks(id) ON DELETE RESTRICT,
    chat_id           UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ,
    status            TEXT NOT NULL CHECK (status IN ('running','completed','failed','cancelled')),
    output_summary    TEXT,
    findings_count    INTEGER,
    error             TEXT
);
```

### `autonomous_tasks` (M4)

```sql
CREATE TABLE autonomous_tasks (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    schedule          TEXT,                    -- cron expression
    trigger_type      TEXT NOT NULL CHECK (trigger_type IN ('cron','watch_kb','watch_email','watch_calendar')),
    trigger_config    JSONB NOT NULL,
    skill_chain       TEXT[] NOT NULL,         -- ordered list of skills
    enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at       TIMESTAMPTZ,
    next_run_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_autonomous_tasks_next_run ON autonomous_tasks(next_run_at) WHERE enabled = TRUE AND next_run_at IS NOT NULL;
```

### `contract_relationships` (M4 — Contract Repository auto-relationship detection)

```sql
CREATE TABLE contract_relationships (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    kb_id           UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    source_file_id  UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    target_file_id  UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    relationship    TEXT NOT NULL CHECK (relationship IN ('amends','restates','references','master_of','sub_of')),
    confidence      NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (kb_id, source_file_id, target_file_id, relationship)
);

CREATE INDEX idx_relationships_source ON contract_relationships(source_file_id);
CREATE INDEX idx_relationships_target ON contract_relationships(target_file_id);
```

---

## Schema diagram (logical)

```
                        ┌──────────────┐
                        │    users     │◄────────────────────────┐
                        └──────┬───────┘                         │
                               │                                  │
                ┌──────────────┼──────────────┐                  │
                ▼              ▼              ▼                  │
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
        │   projects   │ │    chats     │ │    files     │      │
        └──────┬───────┘ └──────┬───────┘ └──────┬───────┘      │
               │                │                 │              │
        ┌──────┴──────┐  ┌──────┴──────┐         ▼              │
        ▼             ▼  ▼             ▼  ┌──────────────┐      │
  attached_skills  files  attached_skills  │   documents  │      │
  attached_files  messages attached_files  └──────┬───────┘      │
                     │                            ▼              │
                     ▼                    ┌──────────────┐      │
              message_citations            │document_chunks│     │
                                           └──────────────┘      │
                                                                  │
    ┌──────────────┐    ┌──────────────┐                         │
    │    skills    │    │  knowledge_  │                         │
    │              │    │    bases     │                         │
    └──────┬───────┘    └──────┬───────┘                         │
           │                    │                                 │
           ▼                    ▼                                 │
  reference_files       knowledge_base_files                     │
  example_files                                                   │
                                                                  │
    ┌──────────────────────────────────┐                         │
    │         audit_log                │─────────────────────────┘
    │  (privilege_marked, tier, etc.)  │
    └──────────────────────────────────┘
    ┌──────────────────────────────────┐
    │     inference_routing_log        │
    └──────────────────────────────────┘
```

---

## Migration approach

- **Alembic** for schema migrations.
- Initial migration `0001_initial.py` creates all M1 tables.
- `0002_skills.py` creates skills + reference + example tables.
- `0003_audit_log.py` creates audit_log + inference_routing_log.
- M2 migrations add citation-engine fields.
- M3 migrations add playbooks, playbook_runs.
- M4 migrations add autonomous_tasks, contract_relationships.

Migration conventions:
- Every migration is reversible (`downgrade()` always implemented).
- Every migration runs in a transaction.
- Backfill scripts for data-shape changes are in `scripts/backfill/`.
- Migration testing: spin up clean Postgres, run all migrations, run all-down + all-up cycle, verify schema is identical.

---

## Performance baseline expectations

- **Hot path:** `messages` and `inference_routing_log` see write-heavy traffic. Indexes minimized on these tables to reduce write amplification.
- **Audit log:** writes are queued and batched (every ~100ms or 100 entries) to reduce contention. Async-safe append.
- **Vector search:** ivfflat with `lists = 100` is appropriate for KBs up to ~1M chunks. Beyond that, transition to hnsw (Postgres 16+ supports it natively in pgvector 0.5+).
- **Full-text:** `tsvector` with GIN index handles document-corpus FTS well; for very large corpora (10M+ chunks), consider partitioning by knowledge_base_id.

---

*Schema maintained alongside the PRD. Substantive changes are documented in PRD §9 deferred-enhancements (if forward-looking) or in the changelog of the migration that lands them.*
