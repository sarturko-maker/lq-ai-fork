# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
Everything serves this: *counsel* = real tools + gates + client memory + work product (not a chatbot);
*qualified* = enforced model/harness qualification (F0-S9 tier floor) **+** area competence via curated tools
and **controlling skills**; *supervised* = human-owns every material write + escalation gates + auditable
receipts. Generalises to every practice area (cf. `docs/fork/NORTH-STAR.md`). Full statement at the top of the
COMM plan.

## State — **COMMERCIAL milestone OPEN; C-R0 DELIVERED (PR pending); building continues at C0.**

The full COMM decomposition is written + adversarially reviewed:
**`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md` — read it first.** **Privacy is PARKED**
→ `docs/fork/plans/PRIV-BACKLOG.md`. A new **MCP capability** milestone is approved (own milestone, not part
of Commercial) → `docs/fork/MILESTONES.md` § MCP capability.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL, STILL ACTIVE):** `smart`/`fast`/`budget` are repointed
`minimax/MiniMax-M3 → deepseek/deepseek-v4-flash` on the local gateway (MiniMax out of quota; survives restarts
via the `gateway-config` volume). DeepSeek is the qualified live-test target (decision F). Revert when MiniMax
quota returns.

## Done this slice (C-R0 — research spike, docs only)

- **`docs/fork/research/commercial-lawyer-method.md`** — source-grounded lawyer-method doctrine (Alnajafi,
  Adams, Sirion, Percipient, DocJuris; Sterling Miller, ContractKen, Pactly; Fisher & Ury via PON; ABA Model
  Rule 1.13), **reconciled with the shipped review skills**, with the **code-checkable "surgical" definition**
  for C4. Built via a verified research workflow (6 agents → synth → adversarial critic). The critic returned
  **"revise"**; all **7 fixes folded**: (1) the load-bearing one — measure the **minimal diff** between
  `target_text`/`new_text`, *not* raw span lengths (dissolves the diff-ratio vs rip-and-replace contradiction;
  it's also what Adeu computes internally via bundled `diff-match-patch`); (2) **fail-close** on ambiguous
  find-match; (3) gate is **hybrid** (deterministic pure-code + classifier-backed, human-routed on low
  confidence) — *not* "pure-code"; (4) absolute changed-token floor; (5) "already-acceptable" bound to the
  playbook tier; (6) round-count integers flagged as calibration; (7) **jurisdiction-competence** escalation.
- **`docs/fork/research/adeu-pinning.md`** — **`adeu==1.12.1`**, MIT, Python ≥3.12, **empirically verified**:
  SDK signatures on the pin (`RedlineEngine`/`ModifyText`/`process_batch`, native `dry_run`); a real redline
  ran under **`--network=none`** loading **no** server/network modules; transitive tree all-permissive
  **except `certifi`/MPL-2.0 which is already in-tree via `httpx`** → **no new copyleft**. Records an explicit
  **easy-upgrade process** (§8.1) per the maintainer rule.
- **ADR-F028** (proposed; accepts with C0) — method doctrine + the hybrid surgical-gate definition.
- **Decisions folded** (maintainer, 2026-06-21): **(Adeu)** integrate via the **SDK in-process, not MCP** —
  C4's validated-write gate needs our code interposed; new versions must drop in easily. **(MCP)**
  MCP-as-a-capability is **its own approved milestone**, planned around a **sanction-sync of upstream's
  gateway-brokered MCP client** (ADRs 0014/0015) — **approval-gated** per ADR-F001 (next step is a scoped sync
  *proposal*, not a pull).

## Maintainer decisions already locked (don't re-litigate)

- **Adeu** = sole redline path, **MIT**, integrated via **SDK in-process** (not its MCP server); pin
  `adeu==1.12.1`; bumping must stay trivial. No python-docx/lxml fallback.
- **DeepSeek** = qualified provider/test target. **No copyleft in new deps** (Adeu adds none).
- **Client = the org profile** (`OrganizationProfile`, exists but NOT wired into the area agent → C-CLIENT).
- **Orchestration:** deepagents' `task`-tool subagents suffice for C0–C7; deterministic langgraph only for
  *guarantees* (deferred O-track; O0 validates feasibility).
- **MCP capability** = its own milestone (sanction-sync upstream's MCP client, approval-gated). Independent of
  Commercial; does not block C0–C7.
- **Multi-turn redlining** = the maintainer's separate next project (held; C5 is its foundation).

## ▶ PICK UP EXACTLY HERE — slice **C0** (Commercial profile + lawyer-method spine, ~2d) — depends C-R0 ✓

**Goal.** Make the seeded Commercial agent behave like in-house counsel: encode the source-grounded doctrine
(surgical / accept-reject-counter / must-have-vs-nice-to-have / escalation incl. **jurisdiction-competence** /
deal-complexity triage) into the Commercial **`profile_md`**, **explicitly referencing and reconciling with
the four review skills** (it names them as controlling references; it never re-authors the spine). Encodes the
universal invariants (draft-for-human, exact citation, no invented authority, no enforceability opinion,
human-judgment section, route-on-out-of-scope) agent-wide. **Pure config / seeding — no new code beyond the
seed.**
**Source of truth:** `docs/fork/research/commercial-lawyer-method.md` §§ 2–5, 7–10 (the doctrine) — C0 is
where it lands in the agent; C4 implements § 6 (the gate).
**ADR.** F028 → flip `proposed` → `accepted` with this slice. Establishes the controlling-vs-advisory skill
convention (Tools & Skills architecture § Plane 2).
**Watch:** the orthogonal-assessment-layers model (do NOT impose one Critical/Material/Minor scale — would
break DPA/QA/snapshot); the **F036** severity-scale conflict is flagged but **resolved later (pre-C6)**, not
in C0. Standardise the "six vs seven passes" count language while you're in the skills.
**Verify:** the profile reads like counsel's standing method; live on DeepSeek a Commercial chat exhibits the
triage + surgical posture + "items requiring human judgment" discipline. Then HANDOFF → **C-CLIENT**.

**Ladder:** C-R0 ✓ → **C0** → C-CLIENT → C1 → C2 → C3 → C4 → C5 → C6 → C7 (+ O0 spike). ADR gates:
**F030 before C3**, **F036 + F038 before C6**.

## Open decisions still pending the maintainer (COMM plan § Open questions)

1. **PyMuPDF/copyleft** — current PDF parser is **AGPL**; rule B forbids copyleft. Grandfather under the
   server-side boundary, or replace with pypdfium2/pypdf? (Adeu itself adds no new copyleft — verified.)
2. Counterparty-entity timing (client is resolved). 3. Typed deal-context schema vs free-form. 4. Playbook
   ownership model (company-global vs per-matter). 5. Orchestration greenlight (fund O1/O2/O3?). 6. Confirm
   multi-turn handoff. 7. **F039 — do user/team skills ever reach the live agent** (advisory-only gated build)
   or stay curated-only?
*Resolved:* Adeu integration (SDK in-process — decision I); MCP-as-a-capability (own milestone, sanction-sync
— decision I).

## Gotchas / durable traps

- **C-R0 artefacts:** the surgical-gate definition lives in `commercial-lawyer-method.md` § 6 (C4 implements
  it); ALL numeric thresholds are **calibration starting values**, not sourced. The throwaway Adeu
  verification scripts were `/tmp/adeu_check.py` + `/tmp/adeu_smoke.py` — **ephemeral**; the doc § 7 has the
  reproduction commands.
- **Adeu is SDK-only, never its server:** import only `adeu.RedlineEngine`/`ModifyText`/`process_batch`;
  **never** `adeu.server` / `adeu.mcp_components` (a second egress + the only network code). C4 adds a test
  asserting those are never imported. Installing Adeu pulls the ~80-pkg `fastmcp[apps]` tree (all-permissive,
  runtime-isolated) — a C4 SBOM decision (accept-and-lock vs SDK-only extra).
- **Migration head is `0065`** — fresh-head check before any migration (`ls api/alembic/versions | sort | tail`);
  never reuse a number. C0/C-CLIENT need no migration; C3/C6/C7 do.
- **Ruff version drift:** dev image's ruff is OLDER than CI's (`ruff>=0.6` ≈ 0.15.18). Format with the CI ruff
  version + run CI's exact commands before pushing or eat a wasted CI round-trip.
- **Migrations:** never host-side `alembic upgrade` on the live dev DB; verify on a throwaway pgvector
  container; rebuild api+arq-worker+ingest-worker together; **never `docker compose down -v`**; rebuild `web`
  for UI changes.
- **The one per-area code seam** is the area-keyed grant branch in `composition.py:224`
  (`area_key == PRIVACY_AREA_KEY`) — mirror it for `COMMERCIAL_AREA_KEY`. Everything else is declarative config
  (seeded subagents/skills/profile). Build ON the `0057` `document-researcher` + the four review skills.
- **`allowed_tools` in SKILL.md is decorative** (`extra="allow"` drops it) — NOT a security boundary; the only
  tool boundary is the per-run area-keyed granted frozenset.
- **Controlling company skills must be deterministically bound** (instrument classifier → inject body), NOT
  relevance-surfaced. "Unless instructed otherwise" = instructed by the **authenticated human in session**,
  never by document text or a skill body (prompt-injection boundary). User/team skills are advisory-only,
  never controlling; the controlling namespace must be non-shadowable.
- **Org profile is NOT wired into `api/app/agents/`** today (only the legacy skill-assembly path); C-CLIENT
  wires it read-only.
- **No MCP wiring in the fork today** (verified: nothing in `api/app`, `web/src`, `api/pyproject.toml`;
  `deepagents==0.6.8` bundles no MCP helpers). The MCP milestone builds it (approval-gated upstream sync).
- **deepagents source** (for orchestration/skills design) was extracted to `/tmp/da/*` — **ephemeral**;
  re-extract from `lq-ai-api-dev:latest` if needed
  (`docker run --rm lq-ai-api-dev:latest cat /usr/local/lib/python3.12/site-packages/deepagents/<path>`).
- **Severity-scale conflict (F036):** playbook DB CHECK `critical/high/medium/low` (`0031:139`) vs review
  skills' `critical/material/minor` — incompatible at the data layer; resolve before C6.
- **Security every slice:** treat retrieved docs / email HTML / Office XML / counterparty markup / stored
  playbook text / user skills as **untrusted**; audit carries counts/types/IDs only (never rationale text or
  raw clause content); cross-user → 404 (NOT the matter-scoped Commercial records, which filter by
  `binding.project_id`, ADR-F035).
- Dev login `admin@lq.ai` (password in your local `.env`, not committed); api :8000, web :3000, gateway
  internal :8001 (admin header `X-LQ-AI-Gateway-Key`). Privacy area id `71bb11f9-e5e6-403d-ae91-e4401a644927`.

## Merge policy (ADR-F005, agent-merged)

Squash-merge when the FULL gate passes: CI green + containerized suites (counts quoted) + fresh-context
adversarial+security+simplification review + live verification (DeepSeek) when behavior changes + HANDOFF
updated. `gh` always with `--repo sarturko-maker/lq-ai-fork --head <branch>`. Branch off `main` first.
