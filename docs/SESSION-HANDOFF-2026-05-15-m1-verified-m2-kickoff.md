# Session Handoff — 2026-05-15 — M1 verified, M2 kickoff

> **Purpose:** Context transfer for the next session. v0.1.0 is end-to-end-verified on a fresh wipe + clone; only the tag itself remains. Then M2 starts on a new branch.

---

## 1. State at handoff

- **Repo HEAD:** `main` at `23511bc` ("docs: fresh-install polish — labeled secret-gen, port-collision troubleshooting, bootstrap-pw note, DE-273").
- **Mirrors:** `origin` → https://github.com/LegalQuants/lq-ai · `tucuxi` → https://github.com/Tucuxi-Inc/lq-ai (internal). Both at `23511bc`.
- **M2 branch:** `m2-development` (created + pushed to both remotes this session; tracks `main` at branch-creation point).
- **Services on dev machine:** 7 healthy.
- **CI:** green on `23511bc` (all 3 jobs: web, API, gateway).

---

## 2. What landed this session (10 commits since `7a12a13`)

The first six closed the v0.1.0 critical path the previous handoff identified. The next two added the InfoTip UX pass + the AliasForm color fix. The final two resolved the external-CC fresh-install evaluation.

| # | Commit | Summary |
|---|---|---|
| 1 | `0388af7` | fix(gateway): rebalance tier-floor fixture for corrected comparator semantics |
| 2 | `50c631f` | fix(ci): pgvector-enabled Postgres image + order-independent caplog in skill loader tests (first caplog attempt) |
| 3 | `5d0629a` | docs(prd): 3 new Appx E entries — UPL, EU AI Act, attorney exposure |
| 4 | `0db4bf8` | docs(ecosystem): surface lq-skills auto-pull + DE-264 PrivacyQuant integration path |
| 5 | `2a99512` | docs(roadmap): adversarial-review additions — 6 new DEs (265–268, 270, 271) + DE-244 sharpening + coverage-matrix gap |
| 6 | `6b7555c` | fix(api): bypass caplog for skill_loader order-dependent tests (monkeypatch v3 — root-cause fix) |
| 7 | `3b4c5d5` | feat(web): InfoTip primitive + 7-surface hover/info pass for non-technical users |
| 8 | `cd38bde` | fix(web): AliasForm renders in light mode to match the surrounding admin chrome (DE-272 sub-task B closed pre-tag) |
| 9 | `2c845a2` | fix(api): fresh-install blockers — auto-run migrations + admin role sync + fork-body validation |
| 10 | `23511bc` | docs: fresh-install polish — labeled secret-gen, port-collision troubleshooting, bootstrap-pw note, DE-273 |

### 2.1 Fresh-install fix detail (the critical work)

An external CC's first-time-user evaluation against `0ab2fab` surfaced 9 issues. Validated locally by full `docker compose down -v --rmi local` + fresh `git clone` into `/tmp/lq-ai-fresh-validate` + walking the README Quick Start verbatim. Final state of each:

| # | Severity | Issue | Fix landed | Where |
|---|---|---|---|---|
| 3 | BLOCKER (critical) | Migrations never run on fresh install | Yes | `api/entrypoint.sh` + `api/Dockerfile` ENTRYPOINT (commit `2c845a2`) |
| 2 | BLOCKER | Host port :5432 collision (Homebrew Postgres on macOS) | Doc-only (per Kevin's call) | README Troubleshooting block with full `*_HOST_PORT` env-var catalog |
| 4 | MAJOR | Bootstrap admin gets `role='member'` despite `is_admin=true` | Yes | `admin_bootstrap.py` insert now sets `role="admin"` alongside `is_admin=True` |
| 1 | MINOR | Secret-gen snippet labels are `secret_0..3` | Yes | README Step 1 snippet now prints `VARNAME=value` lines |
| 5 | MINOR | `reset-admin-password` CLI doesn't sync role | Yes | Defensive self-healing branch in `cli.py` |
| 6 | MINOR | Bootstrap auto-password printed to logs as WARNING | Doc-only | README callout between Step 2 and Step 3 |
| 7 | MINOR | `/skills/{slug}/fork` silently drops typoed body fields | Yes | `SkillForkBody` Pydantic model with `extra="forbid"` in `api/app/api/skills.py` |
| 8 | MINOR | Audit log returns bare `user_id` UUID without enrichment | Filed | DE-273 in PRD §9 (server-side join — bigger work, post-tag) |
| 9 | MINOR | Compose project name shared across same-named clone dirs | Doc-only | README Troubleshooting block on `COMPOSE_PROJECT_NAME` |

### 2.2 End-to-end validation result

Fresh clone of `main` (`23511bc`) into `/tmp/lq-ai-fresh-validate`, README Quick Start walked verbatim:

- Step 1 secret-gen snippet outputs labeled lines, pasteable into `.env` ✓
- Step 2 `docker compose up -d` hit the `:5432` collision (host Homebrew Postgres) — applied new README-documented workaround (`POSTGRES_HOST_PORT=15432`) → all 7 services healthy ✓
- api startup logs show migrations running automatically: `LQ.AI api: running alembic upgrade head…` → 0001 → 0023 → `migrations complete` → uvicorn ✓
- Step 3 `reset-admin-password` succeeded first try ✓
- `SELECT email, is_admin, role FROM users;` → `admin@lq.ai | t | admin` ✓
- POST `/api/v1/auth/login` → 200 with valid JWT ✓
- POST `/skills/nda-review/fork {"name":"x"}` → 422 with `extra_forbidden` ✓
- POST `/skills/nda-review/fork {"new_name":"x"}` → 201 ✓

---

## 3. Remaining for v0.1.0 tag

1. **Fresh-pull verification on Kevin's second machine** (his role).
2. **Final walkthrough together** if Kevin wants — he confirmed the earlier walkthrough on the rebuilt web image looked fine.
3. **Tag and push:**
   ```bash
   git tag -s v0.1.0 -m "v0.1.0 — M1 Foundation release"
   git push origin v0.1.0
   git push tucuxi v0.1.0
   ```

Optional pre-tag housekeeping that won't block:
- Triage the ~19 Dependabot PRs on the public remote (none are v0.1.0 blockers).
- Apply GitHub Rulesets on `main` per the walkthrough provided in the session (Settings → Rules → Rulesets → "main protection" with Block force pushes, Require linear history, Require PR before merging at 0 approvals, Require status checks for the 3 CI jobs).

---

## 4. M2 kickoff — what the next session does

### 4.1 The plan

`docs/M2-IMPLEMENTATION-PLAN.md` is the authoritative implementation contract for M2. 18 tasks across 6 phases (A–F), ~150 hours total, ~6 weeks for one focused contributor.

**Three deliverables ship together:**

1. **Citation Engine verification** (PRD §3.3) — 4-stage verification pipeline (exact-match → tolerant-match → LLM paraphrase judge → ensemble for high-stakes ops). Failed citations render as "unverified."
2. **Anonymization Layer** (PRD §4.7) — gateway pre/post middleware (Presidio + spaCy + custom legal recognizers). Pseudonymizes chat/skill content; sourced documents stay un-pseudonymized per Decision M2-1.
3. **Azure OpenAI adapter** (DE-267) — small but strategically important; unblocks Microsoft-shop enterprise deployments.

**Two architectural decisions locked at kickoff (not up for renegotiation mid-task):**

- **M2-1:** Anonymization preserves source-document retrieval. (Alternative is DE-269 for future consideration.)
- **M2-2:** Ensemble verification ships in M2 baseline, not as a follow-on. "Verified by multiple models in parallel for high-stakes operations" is part of the v0.2.0 procurement story.

### 4.2 First task

**M2-A1 — add `normalized_content` + `was_ocrd` columns to documents** (4–6 hours; per `docs/M2-IMPLEMENTATION-PLAN.md` Phase A).

- Alembic migration `0024_normalized_content.py` adds two columns.
- `api/app/pipeline/ingest.py` populates both during processing.
- One-time backfill script `scripts/backfill_normalized_content.py` reconstructs `normalized_content` for existing documents from their chunks.
- `docs/db-schema.md` updated for both columns.

Verification per the plan: psql query against dev DB shows both columns populated on a sample document; re-extraction from `normalized_content` at chunk offsets reproduces the chunk byte-for-byte; backfill script is idempotent.

After M2-A1: M2-A2 (Citation Engine Stage 1 exact-match verification) and M2-A3 (Anonymization scaffold) can run in parallel.

### 4.3 Recommended workflow (from the plan)

1. Hand Claude Code: the M2 plan + `docs/PRD.md` + `docs/db-schema.md` + the two OpenAPI sketches + `gateway.yaml.example` + `CLAUDE.md`.
2. Pick the next task by ID: "Implement Task M2-A1 — Add normalized content + OCR flag to documents."
3. Let Claude Code execute the full task in one session.
4. Verify against the documented verification step before moving on.
5. **Don't let Claude Code make architectural decisions mid-task.** Decisions M2-1 and M2-2 are locked at kickoff; if a task surfaces a question they don't anticipate, stop, decide with Kevin, document the decision before resuming.
6. Surface ideas out of M2 scope as new DE-XXX entries in PRD §9; don't expand the task.

### 4.4 Branch strategy

`m2-development` is the long-lived integration branch for the full M2 milestone. Per-task feature branches branch off `m2-development` and merge back into it. When M2 lands, `m2-development` merges to `main` (probably as a squashed merge to keep `main`'s log readable).

---

## 5. Lessons / process notes worth carrying

- **Fresh-install validation is a different class of verification than "tests pass on the live stack."** The pre-tag stack had been running for hours with migrated schema + seeded admin. Every check looked clean. The external CC's wipe-and-clone caught the #3 critical blocker that had been hiding behind the live stack's prior state. Each milestone tag should do a full wipe + clone + README walk before shipping. (Captured in `feedback_dry_run_value.md`.)
- **`git add -A` is still the trap.** No new occurrences this session; the lesson holds.
- **Two-remote push is explicit** (`git push origin main && git push tucuxi main`). No push-fanout group; Kevin prefers the explicit form so neither remote silently rejects without surfacing.
- **The pgvector image change** in `.github/workflows/ci.yml` (postgres:16-alpine → pgvector/pgvector:pg16) was load-bearing for the API CI job. The 860+ pytest collection only runs because pgvector is available; previously the migration `CREATE EXTENSION IF NOT EXISTS vector` failed and produced ~570 fixture errors.
- **caplog v3** (`monkeypatch log.warning` directly) is the working pattern for the skill_loader tests; if any other test surfaces order-dependent caplog flakiness in the same suite, apply the same monkeypatch pattern rather than continuing to debug pytest-asyncio + FastAPI lifespan + basicConfig interactions. (Three attempts before landing the working fix — see commits 50c631f, 8d1fff5, 6b7555c.)

---

## 6. Launch announcements (gitignored, local only)

- `ANNOUNCEMENT.md` (~1500 words) — long-form blog/post version with full "Where to start" contribution section, 5 categories of pickup items.
- `LAUNCH-POST.md` (~850 words) — WhatsApp/community-channel variant with tight 4-category contribution bullets and the "30 minutes with the tools any reviewer has free access to here" slop-rebuttal bridge that Kevin specifically liked.

Both ignored via `.gitignore` lines 240–241 (committed in `0ab2fab`). Update either freely; nothing flows to the repo.

---

## 7. How to resume next session

**Pre-flight:**
```bash
git status -sb
git log --oneline -5
docker compose ps
gh run list --branch main --workflow CI --limit 1 --json conclusion,status,headSha
```

**Sequence:**
1. Confirm CI still green on `main` HEAD.
2. (If Kevin has done the fresh-pull on his second machine + walkthrough is done): tag v0.1.0 + push to both remotes.
3. `git checkout m2-development` and start Task M2-A1 per `docs/M2-IMPLEMENTATION-PLAN.md` Phase A.
4. Per-task feature branch off `m2-development`: e.g., `git checkout -b m2/a1-normalized-content`.

---

*Handoff written end-of-session 2026-05-15. Next session: tag v0.1.0 (if not done) + start M2-A1 on `m2-development`.*
