# NOTICES — Upstream Skill Provenance

> **Purpose:** Track the upstream provenance of every skill ported into
> this repository from an external source. Skills authored originally by
> LQ.AI contributors do not appear here. Skills ported from third-party
> corpora (law firm knowledge bases, open-source legal-AI repositories,
> academic datasets, etc.) must have a row in this table.
>
> **Governed by:** [CONTRIBUTING.md — Porting skills from external sources](CONTRIBUTING.md#porting-skills-from-external-sources)
> and [skills/CONTRIBUTING.md](skills/CONTRIBUTING.md).
>
> **How to add a row:** When porting a skill, add a row here in the same
> PR that adds the skill. All five columns are required. "None" is a valid
> value for Attribution requirement when the licence does not impose one
> (e.g., Apache-2.0, MIT). Leave Notes blank when there is nothing material
> to record.

---

## Ported Skills

| Skill scope | Upstream source | License | Attribution requirement | Notes |
|---|---|---|---|---|
| `skills/community/**` | https://github.com/LegalQuants/lq-skills | Per-skill LICENSE in each skill folder | Authors named in SKILL.md frontmatter `author` field | Git submodule pinned to a specific commit; bump via `git submodule update --remote skills/community` |

---

## Format reference

| Column | What to put here |
|---|---|
| **Skill slug** | The slug as it appears in `skills/<slug>/` and the `slug:` frontmatter field. |
| **Upstream source** | Full URI of the upstream repository, document, or dataset. If the source has no stable URI, use a human-readable description (e.g., "Smith & Jones LLP internal knowledge base, licensed for open-source use 2026-04-01"). |
| **License** | [SPDX identifier](https://spdx.org/licenses/) (e.g., `Apache-2.0`, `CC-BY-4.0`). If the licence is not SPDX-enumerated, describe it briefly (e.g., "Custom permissive; see upstream README"). |
| **Attribution requirement** | The exact attribution text required by the licence, or "None". For CC licences, copy the required credit line here. |
| **Notes** | Any material caveats: jurisdiction limitations not captured in frontmatter, version-specific notes, contact for licence questions, etc. |

---

## Amendment procedure

To update a row (e.g., if a upstream source moves or a licence changes):
1. Open a PR with the updated NOTICES.md row.
2. Include the reason for the change in the PR description.
3. If the licence change is restrictive (e.g., the upstream relicensed from permissive to copyleft), flag the maintainer team for review before merging.
