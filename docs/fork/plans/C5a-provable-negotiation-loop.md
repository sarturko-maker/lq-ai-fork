# Plan — COMM **C5a: Provable negotiation loop** (counterparty extraction + the no-silent-action gate) (ADR-F032)

## Context

The commercial agent can read/review/redline/remember a deal and the lawyer can download the redline
(C1/C2/C4/C8/C7a). The missing capability is the **second round**: the counterparty returns a *marked-up*
`.docx` (their tracked changes + Word comments), and the agent must respond to **every** change and **every**
comment — **provably, with nothing silent**. The maintainer's hard requirement: *"how do we know the agent
never silently accepts or rejects, and that everything it does is either a tracked change, or a comment in the
right place, or a reply to a comment in the right place."*

Two investigations reshaped the design:
- **Adeu 1.12.1 does the OOXML read/write natively** (verified live on the pinned stack). Read:
  `extract_text_from_stream(clean_view=False)` → CriticMarkup with stable `Chg:N` ids + authors;
  `CommentsManager.extract_comments_data()` → `Com:N` with author/text/date/`resolved`/`parent_id`. Write:
  `apply_review_actions([AcceptChange/RejectChange/ReplyComment])` + `ModifyText(target,new,comment=)` for a
  counter. So we **do not** rebuild OOXML walkers / comment writers / anchoring — that's all SDK now.
- **The maintainer's prior project `Claude-Plugin-MCP`** (MIT) decomposes this exact problem and its *concepts*
  are reusable — but its Adeu calls are obsolete (old Adeu) and, critically, **it does NOT solve the
  no-silent-action guarantee**: it leaves "address every change" to the prompt + a human eyeball (no coverage
  pass; its `no_action` is a literal silent drop; its output validator only checks the file opens in Word). **So
  the code-enforced completeness/reconciliation gate is the net-new, load-bearing piece C5a owns.**

**Scope (locked, AskUserQuestion):** SPLIT — **C5a is the provable core (backend)**. Deferred to **C5b**: the
`negotiation-review` skill calibration, the inline live verdict chips (the `data-deal-change` seam), and a
multi-round eval. C5a proves the gate by unit tests + one live round-2 scenario; because the guarantee is in
*code*, it holds regardless of prompt quality (the live run leans on tool docstrings + existing review skills).

**Dependency-forced call (not a choice):** C6 (controlling playbooks) + ADR-F036 aren't built, so C5a uses the
**prose** house positions the bound review skills already carry — never the `PlaybookPosition` mechanism.

## Decisions (locked)

1. **Two guarded agent tools, model-judges / code-disposes** (ADR-F018):
   - `extract_counterparty_position` — **deterministic READ** (no model call, ADR-F010): Adeu read → a
     `StateOfPlay` (flat, document-order, every `Chg:N` + `Com:N` with type/author/date/context/text/stable-id/
     replies), tagged `provenance=counterparty` (untrusted). **This enumerates the coverage checklist.**
   - `respond_to_counterparty` — **guarded WRITE**: takes the model's per-id decisions, enforces the gate,
     applies via Adeu, **reconciles**, persists the output `.docx`.
2. **Closed action taxonomy** (lifted from the prior art): `accept · counter · comment · reply · resolve ·
   leave_open · escalate`. **Layer-don't-reject** invariant — a "reject" is never a silent delete; it is a
   client-attributed tracked change (`RejectChange` leaves a tracked change) and/or a `counter` `ModifyText`
   over their markup. **Every decision yields a visible artifact** (tracked change / anchored comment / threaded
   reply); `leave_open`/`escalate` are *recorded + visibly noted*, never silent omissions.
3. **★ The completeness guarantee is code-enforced, in two phases** (the slice's reason to exist):
   - **Upfront coverage gate** — re-extract the StateOfPlay (ground truth, not the model's view); require
     **exactly one decision per extracted `Chg:N`/`Com:N`**: a missing id (silent accept) → REJECT; unknown id,
     duplicate, or accept+counter conflict → REJECT; counter must pass the D1–D5 surgical gate; reasons required
     for `leave_open`/`escalate`. All-or-nothing, collect-all-errors, before any mutation.
   - **Post-write reconciliation** — re-read the OUTPUT `.docx` via Adeu and prove each decision landed at the
     right anchor (`applied` not `skipped`; the `Chg` resolved / the counter's ins+del present / the
     comment/reply exists in the thread / `resolved` flag set). Any discrepancy → REJECT, persist nothing,
     report the unaccounted ids. **Silent-accept fails upfront; silent-reject is impossible.**
4. **Counterparty markup is untrusted model input** (prompt injection). The extract tool frames it as the
   counterparty's *text* (data, not instructions). The skill (C5b) reinforces it; C5a's gate is prompt-agnostic.
5. **Reuse, don't rebuild:** Adeu for read/write; the existing **D1–D5 redline gate** (`schemas/commercial.py`)
   + word-diff (`redline_service.py`, ADR-F045) for counter edits; `_matter_files_query` for scoping;
   `created_by_run_id` (mig 0071) for output provenance → downloadable via C7a. **No migration; no new HTTP
   endpoint; no new dep** (Adeu already pinned).

## Design — the loop & the gate

```
counterparty .docx (matter-scoped)
 └─ extract_counterparty_position(document_name)            [deterministic guarded READ, ADR-F010]
      _fetch_matter_docx (user_id+project_id+deleted_at → 404)
      Adeu: extract_text_from_stream(clean_view=False) + CommentsManager.extract_comments_data()
      → StateOfPlay{changes:[Chg:N…], comments:[Com:N…]}  (provenance=counterparty, bounded)
 └─ model decides one verdict per id  (taxonomy: accept/counter/comment/reply/resolve/leave_open/escalate)
 └─ respond_to_counterparty(document_name, decisions)       [guarded WRITE]
      ① UPFRONT GATE  re-extract StateOfPlay → exactly-one-decision-per-id (miss/dup/conflict → REJECT)
                      counter edits → D1–D5 surgical gate; reasons for leave_open/escalate
      ② APPLY (Adeu, one in-memory doc, fixed order — reply/comment BEFORE accept, then counter, then resolve)
                      accept→AcceptChange(+brief confirming comment)  counter→ModifyText(comment=rationale)
                      reply→ReplyComment(Com:N)  comment→anchored  resolve→done
      ③ RECONCILE  re-read output → every decision landed (applied≠skipped, artifact at anchor) else REJECT
      ④ PERSIST  output .docx as File(created_by_run_id=run_id) [C7a-downloadable] + matter-memory receipt fact
      audit counts/types/IDs only (never clause text)
```

## Files

### Backend — Adeu adapter (read + respond)
- **`api/app/agents/negotiation_service.py`** (NEW, sibling of `redline_service.py`, SDK-only) —
  `read_state_of_play(docx_bytes) -> StateOfPlay` (Adeu `extract_text_from_stream` + `CommentsManager`); and
  `apply_decisions(docx_bytes, decisions) -> (output_bytes, Reconciliation)` — applies review-actions + counter
  `ModifyText` edits on one engine in the verified order, then re-reads to build the reconciliation. Reuses
  `redline_service`'s word-diff for counters. Respects the **reply-before-accept** ordering gotcha (else a
  reply on an accepted run loses its anchor). Counts-only logging.
- **`api/app/schemas/commercial.py`** — ADD `CounterpartyChange`, `StateOfPlay`, `CounterpartyDecision`
  (`verdict: Literal["accept","counter","comment","reply","resolve","leave_open","escalate"]` + conditional
  required fields; `extra='forbid'`, bounded lengths), `RespondToCounterpartyInput`. Reuse the existing
  `evaluate_gate` / `RedlineEditInput` for counter replacements.

### Backend — tools + grant
- **`api/app/agents/commercial_tools.py`** — ADD `extract_counterparty_position` + `respond_to_counterparty`
  closures inside `build_commercial_tools()` (`:78`); extend `COMMERCIAL_TOOL_NAMES` (`:56`); route through
  `guarded_dispatch` (R6/R5). Read via `_fetch_matter_docx`/`_matter_files_query` (re-asserts user_id AND
  project_id AND deleted_at → 404). The completeness gate lives in the `respond_to_counterparty` body (calls
  `negotiation_service` + `evaluate_gate`). Persist output as a File (mirror `_apply_redline`,
  `created_by_run_id=run_id`); record a matter-memory receipt fact (reuse C3b-1 `record_matter_fact`,
  `provenance=counterparty`). Audit counts/IDs only.
- **`api/app/agents/composition.py`** — both names auto-granted in the `COMMERCIAL_AREA_KEY` branch (`:404`)
  (they ride the existing `build_commercial_tools` grant; confirm `granted` set includes them).

### Docs / ADR
- **`docs/adr/F032-negotiation-rounds-counterparty-extraction.md`** (NEW, proposed) — records: the closed
  taxonomy + layer-don't-reject; the **code-enforced completeness/reconciliation gate** as the fork's
  distinctive safety property (contrast: the prior art left it to the prompt); Adeu-native read/respond reuse;
  escalation = a verdict + visible note (no new gate mechanism); counterparty markup untrusted; classification
  vs **prose** positions (explicit non-dependency on C6/F036). Notes the C5a/C5b split + the pure-margin-comment
  + per-revision-date Adeu gaps as backlog.
- **`docs/fork/plans/C5a-provable-negotiation-loop.md`** (committed copy of this plan); **HANDOFF.md**,
  **MILESTONES.md**, memory (+ a new memory on the Adeu read/respond capability + the completeness-gate pattern,
  linking the prior-art repo).

## Verification (4-discipline DoD, ADR-F005 gate)

- **Fixture:** a small deterministic `.docx` with known counterparty tracked changes **and** comments, built
  via Adeu in a fixture helper (mirror `commercial_redline_lib.py` builders; concept from the prior art's
  multi-author round fixtures). 
- **Containerized, counts quoted:**
  - `read_state_of_play` over the fixture → exact `StateOfPlay` (every `Chg:N`/`Com:N`, authors, threads).
  - **Coverage gate:** omit one id → REJECT naming the unaddressed id; duplicate decision → REJECT;
    accept+counter conflict → REJECT; unknown id → REJECT; counter failing D1–D5 → REJECT.
  - **Reconciliation:** a decision engineered to not land (`skipped`) → REJECT, **no File persisted**.
  - **Happy path:** full coverage → output `.docx` persisted with the expected tracked changes + comments +
    threaded replies; `created_by_run_id` stamped; matter-memory receipt fact written `provenance=counterparty`.
  - **Scope:** extract/respond re-assert user_id + project_id (404 cross-user **and** cross-matter, no leak).
  - **Audit:** rows carry counts/types/IDs only — assert no clause text. **No** `test_endpoints`/`test_openapi`
    change (no new route — confirm path count unchanged). ruff + mypy clean.
- **Live (DeepSeek) round-2 scenario IS a deliverable:** counterparty pushback on a redlined NDA — seed a
  counterparty-marked-up `.docx`; drive the agent → `extract_counterparty_position` → per-id decisions →
  `respond_to_counterparty`; it covers every change/comment, counters with surgical drafted language,
  **escalates a below-floor demand** (visible note, not a concession), and the **gate proves full coverage**.
  Evidence → `docs/fork/evidence/c5a/` (StateOfPlay + decisions + output reconstruction + reconciliation
  result). Rebuild `api`+`arq-worker`+`ingest-worker` together (agent loop runs in arq-worker); dev image test
  cmd installs `diff-match-patch structlog` + `--no-deps adeu==1.12.1`; `docker image prune -f` after.
- **Fresh-context adversarial + security + simplification review:** the **prompt-injection** surface
  (counterparty markup framed as data, never executed); the gate can't be bypassed (re-extract is ground truth,
  not the model's StateOfPlay); cross-user/matter scoping; audit IDs-only; no secrets; SDK boundary respected
  (no `adeu.server`/`adeu.mcp_components`); simplification (Adeu replaces would-be OOXML code; no dead paths).
- **HANDOFF + memory updated; merge per ADR-F005** — branch `fork/c5a-negotiation-core` off `main`
  (`352a775`), squash when green; `gh --repo sarturko-maker/lq-ai-fork --head <branch>`.

## Non-goals (→ C5b / backlog)

- **C5b (next slice):** the `negotiation-review` SKILL.md calibration (materiality / authority zones / worked
  examples) + skill-binding migration; the **inline live verdict chips** (`DealChangeLedger` → `data-deal-change`
  transient frame, clone of `data-ropa-change`); a **multi-round eval** (Claude-judged, like C9).
- **No structured-playbook classification** (`PlaybookPosition`/F036) — that's C6. C5a uses prose positions.
- **No new escalation gate mechanism / approval queue** — `escalate` is a recorded, visibly-noted verdict.
- **No pure margin comments (no-edit)** and **no per-revision dates** in the projection — small Adeu/python-docx
  gaps recorded for backlog; C5a anchors comments to a change/counter.
- **No auto-acceptance of concessions** (human owns them); **no fan-out** (C7b).
