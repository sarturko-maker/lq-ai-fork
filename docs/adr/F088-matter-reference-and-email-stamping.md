# F088 — Matter reference `ORG-AREA-NNNN`, email stamping, and the inbound trust ladder

- Status: proposed
- Date: 2026-08-30
- Slice: INTAKE-4a (task #541). Parent plan: `docs/fork/plans/INTAKE-4-plan.md`.
  Related: ADR-F086 (+ Amendment A1) email intake; ADR-F048 Matter Roster; ADR-F087
  (HITL edit/respond + the approved send — INTAKE-4b, not decided here).
- Probe evidence: `docs/fork/evidence/intake-probe/findings.md`.

## Context

INTAKE-3 landed the intake run: an inbound email thread becomes a matter and an agent
run. Two gaps follow immediately.

**A matter has no name a human can say.** Lawyers quote a reference on the phone, in a
subject line, on an invoice. We have a uuid and a slug — neither is sayable, and the
slug is per-owner and mutable.

**A conversation only holds together while the provider's own threading holds.** A
counterparty who forwards our mail from a fresh compose, replies from a different
address, or answers a colleague's copy, arrives as a brand-new provider thread — and
INTAKE-3 opens a second matter for it. The lawyer then has one deal in two places.

The obvious fix — "read the reference out of the subject line and file it there" — is
exactly the move that must not be made naively. A subject line is text a stranger types.
A matter may hold privileged material. Filing a stranger's email into it on their say-so
is a disclosure, not a convenience.

Constraints the solution inherits: neutral naming (maintainer ruling 2026-08-30 — nothing
user-visible, in a header, a subject or a reference number carries our product name; the
codebase is Apache-2.0 and tenants make it their own); single-tenant deployments (no
`org_id` exists anywhere — CLAUDE.md blocker #5, SaaS posture is stack-per-tenant); email
content is untrusted model input; cross-user access is a 404, never a 403.

## Considered options

### The reference

1. **A per-area counter TABLE taken with `SELECT … FOR UPDATE`** — one row per area code,
   incremented inside the caller's transaction.
2. **A Postgres SEQUENCE per practice area.** Gap-free-ish and lock-free, but sequences
   are DDL: every new area needs a migration or runtime `CREATE SEQUENCE`, per-tenant
   stacks drift, and a sequence does not roll back with the matter — a failed creation
   burns a number, so the series a lawyer reads has holes it cannot explain.
3. **A uuid (or a short hash of it) as the reference.** No allocation problem at all, but
   it fails the actual requirement: a reference exists to be said out loud, typed into a
   subject line, and recognised. `NWT-COM-0042` is a filing system; `7f3a9c` is not.

**Chosen: option 1.** It participates in the caller's transaction (a matter that fails to
commit gives its number back — no holes), it needs no DDL per area so per-tenant stacks
stay migration-simple, and a dump/restore carries the counters as ordinary data.

### The inbound signal

1. **Trust the subject tag** — file anything carrying `[ORG-AREA-NNNN]` into that matter.
   Rejected: sender-controlled text becomes an access-control decision.
2. **Trust nothing but the provider's own thread id** (today's behaviour). Rejected: it is
   what produces the duplicate-matter problem; forwards and fresh composes are normal
   correspondence, not edge cases.
3. **A trust ladder in which weak signals never auto-merge** — chosen.

## Decision outcome

### The reference is `ORG-AREA-NNNN`

`NWT-COM-0042`: the tenant's own org code, the matter's HOME practice-area code, and a
per-area-code counter zero-padded to four digits which simply grows past four. Assigned to
EVERY matter at creation — cockpit-created and intake-born alike, through one allocator
(`app.matters.reference.allocate_reference`) called from every creation path — and
backfilled for existing matters in `created_at` order per area by migration 0100.

**It is immutable.** No create or update schema accepts it (`extra="forbid"` turns an
attempt into a 422), and nothing in the codebase writes `projects.reference` after
creation. A reference a counterparty has quoted back at us must not become a different
matter.

Details that are decisions, not accidents:

- **The counter is keyed by the area CODE, not the area id.** The code is what appears in
  the string, so keying on it is what actually makes the string unique: if a code were
  ever re-minted on a different area, an id-keyed counter would restart at 1 and collide
  with references already issued under that code.
- **Matters with no practice area allocate under the reserved code `GEN`.** No practice
  area row is created for it; it is a code, not an area. Manifests and the admin API may
  not claim it.
- **Sandboxes get no reference.** A sandbox is not a matter (`chk_projects_sandbox_no_area`);
  giving it one would put non-matters in the lawyer's filing series.
- **The org code has a neutral placeholder, not a derived guess.** This schema stores no
  company *name* to derive from (`organization_profile` is a single Markdown body, and the
  deployment's branding text is not the legal entity's name), so an unset code renders as
  `ORG` until an admin sets one on the House Brief page or in the setup wizard. Every
  reference minted meanwhile is still unique and still immutable.
- **No `org_id` column is introduced.** "Unique per org" is enforced as a plain global
  UNIQUE on `projects.reference`, because this deployment IS one org. Inventing a
  single-valued FK now would be dead weight that every later query has to carry.

### AREA is the HOME area only — keep-possible invariants

`AREA` is the area that owns the matter (`projects.practice_area_id`). When a future
milestone lets a second area help on a matter:

1. the matter keeps this ONE reference — a helper area never mints a second;
2. "which areas touch this matter" belongs in a future `matter_areas` relation, separate
   from the reference; `projects.practice_area_id` stays the home area;
3. no code in this slice may assume one-area-per-matter beyond that column.

### Outbound stamping: the subject tag, and nothing else

Every reply we send (INTAKE-4b) carries `Re: <original> [ORG-AREA-NNNN]`, appended exactly
once (`tag_subject` is idempotent, and budgets the ORIGINAL subject rather than the tag
when the RFC 5322 line limit bites — the tag is what routes the reply home).

We mint **no Message-IDs of our own.** The probe found the provider assigns its own
canonical `Message-ID` on send regardless of any caller-supplied header, so the
machine-readable stamp is that provider-assigned id, persisted on
`intake_messages.provider_message_id` and matched back out of an inbound `References`
header. A `make_message_id()` helper was drafted and deliberately dropped rather than
shipped unused.

### Inbound: the trust ladder

| # | Signal | May attach alone? | Behaviour |
|---|---|---|---|
| 1 | Same `(mailbox, provider_thread_id)` | yes | continue the thread (unchanged from INTAKE-1) |
| 2 | `References`/`In-Reply-To` names a message we hold **on this mailbox** | yes | NEW `intake_threads` row on the SAME matter, inheriting its `agent_thread_id` |
| 3 | `[ORG-AREA-NNNN]` subject tag **or** a plus-tagged recipient | only if the sender is on that matter's Roster | otherwise: new matter + a recorded `claimed_reference` |
| 4 | Agent suggestion | no | INTAKE-5 |
| 5 | Human "attach to Matter X" | authoritative | INTAKE-5 |

Layer 2 is strong because a message id we issued means the sender was genuinely in a
conversation with this inbox; it is scoped to the mailbox, which is the owner/area fence.
Layer 3 is weak because it is text a stranger types — including the plus-address, which
is a recipient a sender chooses (probed live 2026-08-30: plus-addressed mail reaches the
base inbox, lower-cased by the provider). Roster membership (ADR-F048) is the gate, matched
in Python over the JSONB aliases, case- and display-name-insensitively on both sides — never
as a SQL predicate built from untrusted text.

**Cross-owner is silence, not an error.** A reference naming a matter this queue does not
own behaves EXACTLY like a reference naming nothing: same 200, same new matter, same
recorded claim. Nothing in the response, the prompt, or the logs distinguishes the two, so
no one can probe for the existence of a matter — the 404-class posture of the rest of this
codebase, applied to references.

**An unhonoured claim becomes a note, not an action.** `intake_threads.claimed_reference`
holds the format-checked reference the sender asserted; `intake_prompt` renders it through
the existing `_single_line`/`_neutralise` sanitisers as a fork-authored note that says the
claim was NOT acted on and, deliberately, says nothing about whether the reference exists.
Code refuses to merge; the agent can raise it with the lawyer.

## Consequences

- Positive: every matter is sayable and quotable; a forwarded or re-composed reply lands on
  the right matter AND continues the same agent conversation; the strongest inbound signal
  is one we issued; the weak signal cannot disclose a matter to a stranger; the reference
  vocabulary is entirely the tenant's own words.
- Negative / accepted:
  - **The allocator serialises matter creation per area code** for the duration of the
    caller's transaction. At in-house volumes this is invisible; at bulk-import volumes it
    would need revisiting.
  - **Layer 3 is scoped to the mailbox owner's matters.** A tagged reply about a matter
    owned by a different lawyer opens a new matter instead of attaching. That is the safe
    default; the human "attach to Matter X" operation (INTAKE-5) is the intended answer.
  - **Attaching to an ARCHIVED matter parks the thread** rather than reopening it (the
    INTAKE-3 worker refuses to bind an archived matter). Correct for now; a "reply to a
    closed matter" affordance is INTAKE-5's.
  - **Layer 3 is NOT restricted to the mailbox's own practice area.** A Roster member of,
    say, a Privacy matter who writes to the Commercial front door with that matter's tag
    lands on their matter, and the run composes that matter's own area agent. That is the
    intended reading — the matter's area handles the matter's mail — but it means one
    mailbox can start runs on more than one area's agent. Layer 2 cannot: it is scoped to
    threads of this mailbox.
  - **The derivation logic is duplicated** between `app.matters.reference` and migration
    0100, because migrations in this repo import no app code. A parity test
    (`tests/matters/test_reference_migration_parity.py`) fails the build on drift.
  - An admin who changes an area's code changes only FUTURE matters; the series continues
    under the old code's counter, so nothing collides but the filing series has two
    prefixes. Documented in the admin UI's help text.

## Seams

One-line `# ADR-F088` comments mark: `app/matters/reference.py` and `app/matters/stamping.py`
(the module docstrings), `app/api/intake_emails.py` (the resolver block, the thread-creation
call and the eager matter creation), `app/api/projects.py` (the cockpit allocation),
`app/api/practice_areas.py` + `app/api/profiles.py` (area-code assignment), the new columns
in `app/models/{project,practice_area,organization_profile,intake}.py`, and migration 0100.
