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

## State — **COMMERCIAL milestone OPEN; plan authored + landed; building starts at C-R0.**

The pivot moved off Privacy to the **Commercial** practice area. The full COMM decomposition is written and
adversarially reviewed: **`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md` — read it first.**
**Privacy is PARKED, not abandoned** → its TODO is in **`docs/fork/plans/PRIV-BACKLOG.md`**.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL, STILL ACTIVE):** `smart`/`fast`/`budget` are repointed
`minimax/MiniMax-M3 → deepseek/deepseek-v4-flash` on the local gateway (MiniMax out of quota; survives restarts
via the `gateway-config` volume). DeepSeek is the qualified live-test target (maintainer decision F). Revert
when MiniMax quota returns.

## Done this session

- **PR #122 MERGED** (main `ac659fb`): Privacy A4 designed + **DEFERRED** (ADR-F020, no machine exposure) +
  the internal assessment write→complete→read loop **hardened + proven live** on DeepSeek. Privacy parked.
- **COMM plan authored** from a 14-agent research workflow (codebase + web: Adeu, doc-parsing landscape,
  lawyer-method, deep-agent orchestration) → synth → critic → refine, then **revised against maintainer
  feedback** and a **direct read of the `deepagents==0.6.8` source**.
- **Tools & skills architecture folded in**, adversarially reviewed (4 lenses). Key result: the contribution
  is a **decision rule** — *single-dispatch predicate → tool gate; sequence/completion predicate →
  deterministic flow; substantive legal correctness → human-owns*. Controlling-vs-advisory skill split;
  user/team skills are untrusted + advisory-only + not-yet-wired-to-the-agent. New ADRs **F038/F039/F040**.

## Maintainer decisions already locked (don't re-litigate)

- **Adeu** = sole redline path, **MIT**, confirmed working (no python-docx/lxml fallback — python-docx can't
  redline, models choke on OOXML; Adeu abstracts the tracked-changes XML).
- **DeepSeek** is the qualified provider/test target. **No copyleft in new deps** (hard rule).
- **The client = the operator's org profile** (`OrganizationProfile`, exists but NOT wired into the area agent
  → slice C-CLIENT wires it read-only).
- **Orchestration:** deepagents' model-driven `task`-tool subagents suffice for C0–C7; deterministic langgraph
  is only for *guarantees* (the deferred O-track; O0 spike validates feasibility).
- **Multi-turn redlining** is the maintainer's separate next project (held; C5 is its foundation).

## ▶ PICK UP EXACTLY HERE — slice **C-R0** (research spike, NO code, ~2d, gates C0 & C4)

Two committed research deliverables (docs only — this is the lowest-risk start):
1. **`docs/fork/research/commercial-lawyer-method.md`** — source-grounded lawyer-method doctrine (Alnajafi
   redlining etiquette / Sterling Miller playbook / Fisher & Ury BATNA-ZOPA), **reconciled with the four
   existing review skills** (`skills/{nda-review,msa-review-commercial-purchase,contract-qa,dpa-checklist-review}/SKILL.md`)
   so the C0 `profile_md` *derives from sources + extends shipped skills*, not unsourced assertion. Must also
   pin down a **concrete, code-checkable definition of "surgical"** (diff-ratio + token-span thresholds) for
   C4's gate.
2. **`docs/fork/research/adeu-pinning.md`** — Adeu is confirmed (no go/no-go): pin the exact version; verify
   the `RedlineEngine`/`ModifyText`/`process_batch` SDK signatures **on the pinned version** (docs stale at
   v1.6.0; PyPI ~1.12.x); confirm **zero network/provider calls**; confirm the **transitive tree is all
   permissive — no copyleft** (`fastmcp`/lxml/rapidfuzz etc.). Throwaway-venv `pip install adeu==<pin>` import
   smoke. Do NOT add Adeu to `pyproject` yet (that's C4).

**Verification for C-R0:** docs reviewed — every method claim cites a source; the surgical definition is
numeric thresholds C4 can test; Adeu pinning records the exact pin + verified permissive license chain + the
import smoke. ADR **F028** drafted here (accepted with C0). Then HANDOFF → point at **C0**.

**Ladder:** C-R0 → C0 → C-CLIENT → C1 → C2 → C3 → C4 → C5 → C6 → C7 (+ O0 spike). Two ADRs gate dependents:
**F030 before C3**, **F036 + F038 before C6**.

## Open decisions still pending the maintainer (in the COMM plan § Open questions)

1. **PyMuPDF/copyleft** — current PDF parser is **AGPL**; rule B forbids copyleft. Grandfather under the
   server-side boundary, or replace with pypdfium2/pypdf? 2. Counterparty-entity timing (client is resolved).
   3. Typed deal-context schema vs free-form. 4. Playbook ownership model (company-global vs per-matter).
   5. Orchestration greenlight (fund O1/O2/O3?). 6. Confirm multi-turn handoff. 7. **F039 — do user/team
   skills ever reach the live agent** (advisory-only gated build) or stay curated-only? This decides if F039
   exists.

## Gotchas / durable traps

- **Migration head is `0065`** — fresh-head check before any migration (`ls api/alembic/versions | sort | tail`);
  never reuse a number (`0041/0054/0056/0057` taken). C1/C2 likely need no migration; C3/C6/C7 do.
- **Ruff version drift:** the dev image's ruff is OLDER than CI's (`ruff>=0.6` ≈ 0.15.18). Format with the CI
  ruff version + run CI's exact commands before pushing or eat a wasted CI round-trip. (See the memory.)
- **Migrations:** never host-side `alembic upgrade` on the live dev DB; verify on a throwaway pgvector
  container; rebuild api+arq-worker+ingest-worker together; **never `docker compose down -v`**; rebuild `web`
  for UI changes.
- **The one per-area code seam** is the area-keyed grant branch in `composition.py:224`
  (`area_key == PRIVACY_AREA_KEY`) — mirror it for `COMMERCIAL_AREA_KEY`. Everything else is declarative config
  (seeded subagents/skills/profile). Build ON the `0057` `document-researcher` + the four review skills.
- **`allowed_tools` in SKILL.md is decorative** (`extra="allow"` drops it) — NOT a security boundary; the only
  tool boundary is the per-run area-keyed granted frozenset.
- **Controlling company skills must be deterministically bound** (instrument classifier → inject body), NOT
  relevance-surfaced — a relevance miss on the controlling playbook is malpractice-grade. User/team skills are
  advisory-only, never controlling; the controlling namespace must be non-shadowable.
- **Org profile is NOT wired into `api/app/agents/`** today (only the legacy skill-assembly path); C-CLIENT
  wires it read-only.
- **deepagents source** (for the orchestration/skills design) was extracted to `/tmp/da/*` — **ephemeral**;
  re-extract from the `lq-ai-api-dev:latest` image if needed
  (`docker run --rm lq-ai-api-dev:latest cat /usr/local/lib/python3.12/site-packages/deepagents/<path>`).
- **Severity-scale conflict (F036):** playbook DB CHECK `critical/high/medium/low` (`0031:139`) vs review
  skills' `critical/material/minor` — incompatible at the data layer; resolve before C6.
- **Security every slice:** treat retrieved docs / email HTML / Office XML / counterparty markup / stored
  playbook text / user skills as **untrusted**; audit carries counts/types/IDs only; cross-user → 404 (NOT the
  matter-scoped Commercial records, which filter by `binding.project_id`, ADR-F035).
- Dev login `admin@lq.ai` (password in your local `.env`, not committed); api :8000, web :3000, gateway
  internal :8001 (admin header `X-LQ-AI-Gateway-Key`). Privacy area id `71bb11f9-e5e6-403d-ae91-e4401a644927`.

## Merge policy (ADR-F005, agent-merged)

Squash-merge when the FULL gate passes: CI green + containerized suites (counts quoted) + fresh-context
adversarial+security+simplification review + live verification (DeepSeek) + HANDOFF updated. `gh` always with
`--repo sarturko-maker/lq-ai-fork --head <branch>`. Branch off `main` first.
