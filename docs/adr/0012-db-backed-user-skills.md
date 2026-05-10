# ADR 0012 — DB-backed user skills (amends ADR 0004)

**Status:** Accepted (2026-05-10)
**Decision-makers:** Kevin Keller (initial maintainer)
**Affected components:** `api/` (new table, new endpoints, audit writes), `gateway/` (registry-merge during prompt assembly), `web/` (Skill Creator page in `/lq-ai`)
**Amends:** [ADR 0004 — Skill loader locus](0004-skill-loader-locus.md) (specifically §Neutral, §"Decision is local to C1+C2"). ADR 0004 explicitly anticipated this: *"The progression to a DB-backed skill table at user/team scope (deferred enhancement) lands in the backend, where the database lives. No locus change; just adding a backing store behind the same registry interface."*
**Related:** [PRD §3.10 Skill Creator](../PRD.md#310-skill-creator), [PRD §7.1 Skills as the canonical artifact of value](../PRD.md#71-skills-as-the-canonical-artifact-of-value), [PRD §1.3 Transparency as a founding principle](../PRD.md#13-transparency-as-a-founding-principle), [ADR 0007 Skill prompt assembly](0007-skill-prompt-assembly.md), [M1-IMPLEMENTATION-ORDER.md Task D8](../M1-IMPLEMENTATION-ORDER.md)

---

## Context

D7 landed Saved Prompts (per-user named prompt fragments — [migration 0011](../../api/alembic/versions/0011_create_saved_prompts.py), [`api/app/api/saved_prompts.py`](../../api/app/api/saved_prompts.py)) and a "Promote to Skill" affordance whose current implementation downloads a `SKILL.md` file for the user to drop into the filesystem out-of-band. That's a stand-in. The PRD §3.10 spec calls for the user to author and edit a skill *inside* LQ.AI without leaving the app — the filesystem download path is a placeholder until D8.

ADR 0004 already established that the **filesystem-canonical** built-ins (the 10 starter skills shipped in `skills/`) load through `api/app/skills/loader.py` into the backend's in-memory `SkillRegistry`. The gateway fetches resolved skill content from the backend over the existing `/internal/skills/{name}` HTTP boundary during C2 prompt assembly. The locus has been settled for nearly a year.

What hasn't been settled is **how user-authored skills coexist with the built-ins** at runtime. Specifically:

1. **Storage shape.** Where does the user's skill body live? A new table? A column on the user row? A file under a `skills-user/<user_id>/<slug>.md` directory?
2. **Resolution order.** When a chat is dispatched and the user's tier-floor-checked request references a skill that exists both as a built-in *and* as their own creation, which one shapes the prompt?
3. **Registry merge.** Does the in-memory `SkillRegistry` carry user skills (and rebuild on every CRUD)? Or does the registry stay built-in-only and the user-shadow layer joins at lookup time?
4. **Scope.** D8 was scoped to "user and team" in the original plan. Teams aren't a first-class concept in M1 — there's no `teams` table, no team-membership semantics, no team-scoped permissions checks anywhere in the codebase. Pulling teams in here is a meaningful surface expansion.
5. **Versioning.** Filesystem skills carry a free-form `version` string in their `lq_ai:` frontmatter. User skills get edited; how do we represent the version history (or do we)?

This ADR settles those five questions for D8. Team scope is explicitly deferred to **D8.1** (a separate, smaller task that lands the team table + scope routing once team-membership semantics exist elsewhere in M1 — likely not in M1 at all).

---

## Decision

### 1. Storage: new `user_skills` table

One table per migration 0013 (next free Alembic revision). Single row per `(scope, owner_user_id|owner_team_id, slug)` tuple — no version history at the row level (see §5).

```
user_skills
├─ id                 UUID PK (gen_random_uuid)
├─ scope              TEXT NOT NULL CHECK (scope IN ('user', 'team'))
├─ owner_user_id      UUID NULL  FK → users.id ON DELETE CASCADE
├─ owner_team_id      UUID NULL  FK → teams.id   ON DELETE CASCADE   -- table doesn't exist yet; FK added when teams ship in D8.1
├─ slug               TEXT NOT NULL              -- the stable identifier (matches filesystem skill folder-name conventions)
├─ display_name       TEXT NOT NULL              -- frontmatter.lq_ai.title equivalent
├─ description        TEXT NOT NULL              -- frontmatter.description
├─ version            TEXT NOT NULL DEFAULT '1.0.0'   -- user-set free-form semver; matches filesystem convention
├─ tags               TEXT[] NOT NULL DEFAULT '{}'
├─ frontmatter_extra  JSONB NOT NULL DEFAULT '{}'      -- everything else in lq_ai: (jurisdiction, output_format, min_inference_tier, …)
├─ body               TEXT NOT NULL                    -- the Markdown body
├─ archived_at        TIMESTAMPTZ NULL                 -- soft-delete; archived rows never resolve and never list
├─ created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
└─ updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()   -- set_updated_at() trigger per A2 convention

constraints:
  CHECK ((scope = 'user' AND owner_user_id IS NOT NULL AND owner_team_id IS NULL) OR
         (scope = 'team' AND owner_team_id IS NOT NULL AND owner_user_id IS NULL))
  UNIQUE (scope, owner_user_id, slug) WHERE scope = 'user' AND archived_at IS NULL
  UNIQUE (scope, owner_team_id, slug) WHERE scope = 'team' AND archived_at IS NULL

indexes:
  CREATE INDEX user_skills_owner_user_idx ON user_skills (owner_user_id) WHERE scope = 'user' AND archived_at IS NULL;
  CREATE INDEX user_skills_owner_team_idx ON user_skills (owner_team_id) WHERE scope = 'team' AND archived_at IS NULL;
```

The migration includes the `team` scope columns and CHECK clause from the start so D8.1's only job is to add the `teams` table + the FK constraint pointing at it, not to widen `user_skills`. The team-scoped UNIQUE index ships in migration 0013; it's unenforceable until D8.1's FK lands but it's cheap, and Postgres permits a partial UNIQUE on a NULLABLE column with no rows.

The migration is reversible — `downgrade()` drops the table.

### 2. Resolution order: user shadows built-in

When the gateway resolves a skill for a chat request, the order is:

1. **User-scope match** for the authenticated user, on the slug. If a non-archived row exists in `user_skills` with `scope='user'`, `owner_user_id=<the requesting user>`, and `slug=<the requested slug>` — that row wins.
2. **Filesystem built-in** with the same slug. The `SkillRegistry`'s existing path.
3. **404** if neither exists.

Team-scope insertion into the order is deferred to D8.1 (between steps 1 and 2). The empty middle slot is the slot D8.1 fills; D8 ships steps 1, 2, and 3 unchanged from the current world plus the user-shadowing layer.

The shadowing semantics are deliberate and grounded in [PRD §1.3 Transparency as a founding principle](../PRD.md#13-transparency-as-a-founding-principle): a user who finds a built-in skill almost-right should be able to copy it, tweak it, and have *their version* render in *their chats* without admin intervention. That's forking-by-shadowing, which is the open-source ergonomic the project's framing depends on. Refusing the collision (option B in the design space) or accepting the row but ignoring it (option C) both undermine the "skills are forkable" promise.

The user's shadow does NOT affect any other user's view. The filesystem built-in remains canonical for everyone else, including the original author of the built-in. If the operator later wants to upstream a popular user-skill, the path is a normal PR against `skills/` per [skills/CONTRIBUTING.md](../../skills/CONTRIBUTING.md) — not a DB-side promotion mechanism.

### 3. Registry merge: lookup-time join, not registry rebuild

The in-memory `SkillRegistry` stays exactly as it is today — a snapshot of filesystem-canonical built-ins, atomic-swapped on SIGHUP. User skills do not enter the registry. Instead, the internal-skills endpoint that the gateway calls (`GET /internal/skills/{slug}`) gains an optional `user_id` query parameter:

- Without `user_id`: returns the built-in (preserves existing behavior; safe for any caller that doesn't care about per-user shadowing — admin tooling, the public `GET /api/v1/skills` listing for an unauthenticated reader, etc.).
- With `user_id`: the handler queries `user_skills` first; if a non-archived row matches, the handler synthesizes a `Skill` payload from the row and returns it. Otherwise the handler falls through to the registry lookup.

The synthetic-`Skill` shape mirrors the filesystem case (same wire format the gateway already parses, per [`api/app/skills/schema.py`](../../api/app/skills/schema.py)). The `description`, `tags`, `version`, and any `lq_ai:` keys land in their canonical positions; the `body` becomes the assistant-system prompt's skill chunk per C2.

This design avoids two things that a registry-rebuild approach would force on the system:

- **Cache invalidation across edits.** Every PATCH /skills would have to either bust the registry (and pay the cost of reloading all filesystem skills) or maintain a parallel in-memory user-skills registry per user (memory pressure scales with user-count × skill-count). Lookup-time join is O(1) DB read per resolution, which the chat-message path already pays for.
- **Multi-process consistency.** When the api/ service runs more than one worker (M1: no; M2: probably), an in-memory user-skill registry needs cross-worker invalidation. A DB read on each resolution sidesteps that entirely.

### 4. API surface

The user-facing backend endpoints:

| Method | Path | Purpose | Audit action |
|---|---|---|---|
| `GET` | `/api/v1/skills` | List built-ins + the requesting user's user-scope skills, merged. Sort: user-scope rows first (so the user's tweaks float to the top), then built-ins by name. | none (read-only) |
| `GET` | `/api/v1/skills/{slug}` | Return the resolved skill for this user (user-shadow if any, else built-in, else 404). | none (read-only) |
| `POST` | `/api/v1/skills` | Create a user-scope skill. Body: `{slug, display_name, description, version, tags, frontmatter_extra, body}`. 409 on slug collision with the requesting user's existing user-scope skills (collision with a built-in is allowed — that's the shadow case). | `user_skill.created` (no privilege flag — skills are not privileged content surfaces) |
| `PATCH` | `/api/v1/skills/{id}` | Update fields on a user-scope skill the requesting user owns. 403 on attempts to modify someone else's skill or a built-in. | `user_skill.updated` |
| `DELETE` | `/api/v1/skills/{id}` | Soft-delete (set `archived_at = now()`). Subsequent resolutions stop returning it. 403 on someone else's row; 410 on already-archived. | `user_skill.deleted` |

`POST/PATCH/DELETE` accept the skill `id` (UUID), not the slug, because slug is mutable in principle (a user can rename their own skill) and audit rows need a stable target ID anyway. Audit `details` carry `{slug, version, scope}` for human-readable filtering in `/lq-ai/admin/audit-log`.

The gateway-internal endpoint:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/internal/skills/{slug}?user_id={uuid}` | Resolved-for-this-user skill content. Gateway calls this from the C2 prompt-assembly path, passing the authenticated user's UUID. Returns 404 if neither a user shadow nor a built-in matches. |

`X-LQ-AI-Gateway-Key` auth on this endpoint is unchanged from C2 (it's an internal-trust boundary).

### 5. Versioning: user-set string, single row, no history

`version` is a `TEXT` column the user types into the Skill Creator form. Convention: semver-ish (`"1.0.0"` initial; bump on edits). No enforcement — matches the filesystem skill convention where `lq_ai.version: "1.0.1"` is whatever the author wrote.

Edits replace the row in place. There is no `user_skill_versions` history table in D8. The audit log carries `user_skill.updated` rows with `details.version_before` and `details.version_after`, so the *fact* of an edit is forensically traceable; the *content* of the prior version isn't. This is a deliberate scope trim — a full edit-history surface is a candidate post-M1 enhancement (DE-XXX to file if a user asks).

`archived_at` is the soft-delete mechanism. Archived rows are excluded from all resolution paths and all list endpoints. Restoring an archived skill is a future enhancement; for D8 the path is "POST a new one with the same content."

---

## Consequences

### Positive

- **Skill Creator becomes real.** D7's "Promote to Skill → download SKILL.md" stand-in graduates to a real CRUD surface that lives entirely inside the app. PRD §3.10's primary capability spec is implemented end-to-end.
- **Forking by shadowing.** The transparency commitment (PRD §1.3) is honored at the level the user actually exercises it — copy, tweak, run.
- **No registry-rebuild churn.** The lookup-time join keeps the existing `SkillRegistry` invariant clean (built-ins only) and avoids a per-edit invalidation step.
- **Audit coverage is consistent.** The new endpoints follow the D3-coverage pattern landed in 2026-05-10c — every state-changing call writes an audit row, failure paths commit-before-raise to preserve forensic evidence (per the `feedback_audit_failure_rows.md` learning).
- **D8.1 is a small follow-on.** The migration ships team-scope columns from the start; D8.1 only adds the `teams` table + FK + the team-scope branch in resolution. No backfill, no schema rework.

### Negative

- **Two writes per skill view.** Listing user skills + listing built-ins is two paths joined in the handler. The `GET /api/v1/skills` listing now joins a DB query with a registry walk. The cost is negligible at any scale we project (registry walk is in-memory; DB query is indexed by `owner_user_id`); it's worth calling out as a deviation from the current single-path implementation.
- **Slug collisions with built-ins are silent.** A user who creates `nda-review` at user-scope won't get any warning that they're shadowing a built-in — the API accepts the create cleanly. The Skill Creator UI **must** surface this prominently ("This shadows the built-in `nda-review` skill for your chats; other users still see the built-in.") to keep the behavior comprehensible. Implementation responsibility lands in `web/src/routes/lq-ai/skills/new/+page.svelte`.
- **No edit history.** A user who wants to roll back a botched edit can't; their pre-edit body is gone. The audit log records that the edit happened but not what was there before. If real users complain about this in M1+, file as DE-XXX.

### Neutral

- **Filesystem built-ins remain the canonical artifact of value** per [PRD §7.1](../PRD.md#71-skills-as-the-canonical-artifact-of-value). User-scope rows are personal modifications; they don't enter the public skill corpus without a normal PR. The promotion path from "popular user skill" → "official built-in" is human review under [skills/CONTRIBUTING.md](../../skills/CONTRIBUTING.md), not a DB-side mechanism.
- **The `archived_at` soft-delete is a deliberate departure from D7's saved_prompts pattern**, which uses hard-delete. Skills are richer artifacts (frontmatter, body, versioning) and the "I deleted it by mistake" recovery story matters more; saved prompts are by design lightweight and disposable.

---

## Out of scope (filed as deferred or D8.1)

- **Team scope** — D8.1 lands the `teams` table, team-membership semantics, team-scope CRUD endpoints, and the resolution-order middle slot. The migration 0013 schema is ready for this; D8.1 is the path that turns the latent surface live.
- **Skill version history** — DE-XXX if a user asks. The audit-log records the fact of edits; recovering content from a past version isn't supported.
- **Reference files** — Filesystem skills can package additional `.md` reference files alongside `SKILL.md`. User skills are body-only in D8. Adding reference files is a meaningful UX expansion (file upload, storage in MinIO?, retrieval at prompt-assembly time) and a D9+ candidate.
- **Cross-user sharing** — "Share this skill with my colleague" isn't a path. Sharing happens via PR to `skills/` (the canonical-build-in path) or via team-scope when D8.1 lands.
- **Importing a SKILL.md file** — The Skill Creator form takes structured input. Drag-and-drop import of an `.md` file is a UX expansion; defer unless real users ask.

## References

- [ADR 0004 — Skill loader locus](0004-skill-loader-locus.md) (parent decision; this ADR extends §Neutral)
- [ADR 0007 — Skill prompt assembly](0007-skill-prompt-assembly.md) (the gateway's resolution path that consumes user shadows via `/internal/skills/{slug}?user_id=…`)
- [PRD §3.10 Skill Creator](../PRD.md#310-skill-creator)
- [PRD §7.1 Skills as the canonical artifact of value](../PRD.md#71-skills-as-the-canonical-artifact-of-value)
- [`api/app/api/internal.py`](../../api/app/api/internal.py) — `/internal/skills/{slug}` (extended in D8 to accept `user_id`)
- [`api/app/skills/schema.py`](../../api/app/skills/schema.py) — `Skill` / `SkillSummary` wire shapes the synthetic-Skill payload mirrors
- [`api/app/api/saved_prompts.py`](../../api/app/api/saved_prompts.py) — D7 pattern that D8 follows for ownership / CASCADE / audit-write
- [M1-IMPLEMENTATION-ORDER.md Task D8](../M1-IMPLEMENTATION-ORDER.md)
