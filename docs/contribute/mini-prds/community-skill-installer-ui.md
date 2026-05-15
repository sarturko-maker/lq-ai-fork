# Mini-PRD: Community Skill Installer (admin UI)

> **Status:** Open for contribution
> **Effort:** M (frontend + small backend)
> **Contributor profile:** Mid-level engineer (Svelte + FastAPI); legal-domain understanding helpful for the install-warning copy but not required
> **Mentor:** Maintainer (Kevin Keller, via PR review)

## What this is

An admin-only **"Browse community skills"** page in LQ.AI that surfaces skills from the [LegalQuants/lq-skills](https://github.com/LegalQuants/lq-skills) catalog (and, eventually, any operator-configured skill source) and lets an admin **install** a community skill directly into the operator's deployment. After install, the skill behaves like any other user-scope skill — readable, attachable, forkable.

This complements the existing M1 surface, which pulls community skills in at deploy time via the `skills/community/` git submodule (built-in path). The installer UI adds **runtime discoverability**: an admin browsing for, say, a German-data-residency skill doesn't need shell access to update the submodule and rebuild — they pick from a list and click Install.

## Why it matters

Three reasons:

1. **The git-submodule path makes community skills available at deploy time, not at runtime.** An operator who wants to add a new community skill after deployment has to update the submodule on the host, rebuild the api container, and restart. That's friction even for technical operators — and impossible for legal-team operators who don't manage their own deployment.

2. **The lq-skills catalog grows over time.** New skills land in lq-skills weekly. Without a runtime install path, operators are always behind whatever was current at the last submodule bump.

3. **It surfaces the contribution path back to the catalog.** An operator who installs `dpa-checklist-review-eu`, customizes it, and finds gaps in the upstream version has an obvious place to file a PR back to lq-skills. The installer becomes a discovery surface for the community's work product.

## What we'd ship

```
web/src/routes/lq-ai/admin/community-skills/
  +page.svelte                # Browse + install page (admin only)
web/src/lib/lq-ai/components/
  CommunitySkillCard.svelte   # Card with name, description, author, install button
  CommunitySkillInstallModal.svelte  # Confirm-install dialog with provenance + license
api/app/api/
  community_skills.py          # GET /admin/community-skills (list), POST /admin/community-skills/{slug}/install
api/app/skills/
  community_installer.py       # Fetches SKILL.md from lq-skills via GitHub raw content; writes to user_skills table
docs/
  community-skills-catalog.md  # How the installer chooses sources (config file path); how to point at a different catalog
```

The installer **does not run arbitrary code**. It reads the SKILL.md frontmatter + body from the upstream source, validates against the same Pydantic schema used for user-skill creation today (`api/app/api/user_skills.py`'s `UserSkillCreate`), and persists into the `user_skills` table with scope `user` (owner = the admin who installed it). After install, the skill is editable, forkable, and reviewable like any user skill.

Install attribution: the persisted skill carries `forked_from: "lq-skills:<slug>@<commit-sha>"` so the audit log + Versions tab show provenance.

## How we'd know it's done

- [ ] `GET /api/v1/admin/community-skills` returns a list with at least 30 entries (current lq-skills catalog size) when configured against the canonical source
- [ ] Each entry includes: slug, title, description, author, version, license, URL to upstream SKILL.md
- [ ] `POST /api/v1/admin/community-skills/{slug}/install` is admin-only (403 for member/viewer roles)
- [ ] Install creates a `user_skills` row with `forked_from = "lq-skills:<slug>@<commit-sha>"`
- [ ] Browse page renders cards with author + license + Install button; Install button opens a modal showing the full SKILL.md before confirming
- [ ] Cypress e2e: admin navigates to community-skills page, clicks Install on `adversarial-qc`, confirms, sees it appear in `/lq-ai/skills` skill list
- [ ] Unit tests: installer validates the upstream SKILL.md against the existing schema; install fails cleanly if the SKILL.md is malformed
- [ ] Audit log emits `community_skill.installed` action with the upstream slug + commit SHA
- [ ] Documentation: `docs/community-skills-catalog.md` explains how to point the installer at a different catalog (config-file or env var)

## Where to start

1. Read `api/app/skills/loader.py` and `api/app/skills/registry.py` (just landed in commit `800f9d6`) to understand how community skills are discovered via the submodule today
2. Read `api/app/api/user_skills.py` for the existing user-skill create/validate endpoint — the installer reuses the same Pydantic validators
3. Read `docs/skill-authoring-guide.md` for the canonical SKILL.md schema
4. Read `web/src/routes/lq-ai/admin/audit-log/+page.svelte` for the admin-page styling pattern + role-gate pattern
5. The lq-skills repo is at `https://github.com/LegalQuants/lq-skills`. The GitHub Contents API can list `skills/` and read individual `SKILL.md` files without authentication

## Scope cuts (what's out of scope for this PR)

- Multi-source catalogs (other repos beyond lq-skills). Ship with lq-skills as the only source; add a config knob for the URL but don't build a UI for multiple sources.
- Auto-update: when a community skill in lq-skills gets a new version, the installed copy doesn't auto-bump. Add an "Update" button in a v2.
- Curation / moderation flags: don't show "this skill has a known issue" warnings. Trust the upstream catalog's own quality signals.
- Per-team install scopes: install as user-scope (owner = installer). Team-scope installs can come later.

## How this strengthens the project

This is the substantive expression of LQ.AI's "skills as canonical artifact of value" framing (PRD §7.1). Today, an operator who wants a new skill either: (a) writes it themselves, (b) updates the submodule, or (c) waits for the maintainer team to port it. The installer makes the community catalog **operator-self-serve at runtime**. That's the difference between "skills are open source" and "skills are usable open source."

Procurement evaluators reading the README see a one-click install path for skills authored by lawyer-builders across 17+ jurisdictions. Closed-source competitors have no comparable surface — their prompt catalogs are vendor-curated, vendor-rate-limited, vendor-priced.

## References

- [PRD §3.2 Skill Library](../../PRD.md#32-skill-library) — the canonical skill format + scopes
- [PRD §7.1 Project Philosophy](../../PRD.md#71-project-philosophy) — "skills are work product"
- [HONEST-STATE.md §1](../../HONEST-STATE.md#1-conversational-and-workspace-surface) — what's shipped today on the skill surface
- [skills/CONTRIBUTING.md](../../../skills/CONTRIBUTING.md) — the skill contribution workflow (the installer's metadata mirrors this)
- [LegalQuants/lq-skills](https://github.com/LegalQuants/lq-skills) — the upstream catalog
- Related mini-PRD: [Acceptance tests for built-in skills](skill-acceptance-tests.md) — installed community skills should pass the same acceptance bar

## Definition of "merged"

The PR is merged when: (a) the acceptance criteria checklist is fully checked off, (b) Cypress e2e covers the install happy path, (c) the maintainer has reviewed the substance, (d) the security review for the new admin endpoint is in (per `.github/CODEOWNERS` if applicable — the install path persists external content, so it warrants the same review discipline as any new admin surface).
