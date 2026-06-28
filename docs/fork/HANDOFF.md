# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

> ▶▶ **PICKUP (2026-06-28): RETRIEVAL & MEMORY E1 — the Track-A agentic baseline (masked-judge scenarios)
> SHIPPED + MERGED (PR #161, `main` `a2eabaab`). Phase-E exit REACHED. NEXT SLICE = N0 (wire the native
> `AsyncPostgresStore` + `CompositeBackend` into `compose_and_execute_run`, accepts ADR-F049).** E1 is the
> subjective/agentic half of the eval-first instrument (E0 = the objective Track-B retrieval floor).
> *(Follow-up shipping separately: a fan-out "when to delegate for document knowledge work" research note
> → `docs/fork/research/` — input for the Phase-3 strategy/R4 slice, NOT a blocker for N0.)*
> - **What shipped (all `tests/agents/scenarios/`):** `track_a_lib.py` — `build_judging_packet` (the
>   **masked judging packet**: projects steps to the 5 audited `fetch_steps` fields + strips `<think>`;
>   carries ONLY timeline + visible answer + rubric/expectations — never docs / agent prompt / `run_id`),
>   `JudgeRubric`/`JudgeVerdict`, `parse_verdict` (evidence-quote-must-be-in-answer), and `masked_judge`
>   (the gateway fallback judge, generalises `craft_judge`). `track_a_fixtures.py` — A1/A5/A7/A8
>   `TrackAScenario`s. `test_track_a_unit.py` — **free CI net** (masking-leak assertion, verdict parsing,
>   fake-gateway wiring, L1 via `score_all`). `test_track_a_eval.py` — provider-marked live matrix.
>   `harness.Receipt` gained `run_id` (additive). **L1 reuses `evals.scoring.score_all`; masking reuses
>   `evals.runner.fetch_steps` + `evals.scoring.visible_answer` — no new scorer/dependency.**
> - **THE JUDGE (maintainer call):** the **orchestrator (Claude) is the primary judge** over the frozen
>   masked packets (a fan-out Workflow, one independent judge per packet — "Claude-judged DeepSeek", $0 on
>   the gateway); the gateway `deepseek-pro` `masked_judge` is the automated fallback. Masking is what makes
>   Claude-as-judge fair (it never sees the docs/prompt, only what the agent surfaced).
> - **FROZEN BASELINE (N=10, DeepSeek agent, Claude-judged; `docs/fork/evidence/retrieval-eval/track-a/`):**
>   **A1** multi-doc grounding **8/10** (grounded 9/10, no cross-doc bleed 10/10; the 2 fails are
>   cap-exceeded **empty answers** — grounded in the timeline, never delivered); **A5** cross-thread recall
>   **0/10 (RED — turns green with N2/N3)** but **honest-abstention 10/10**; **A7** strategy: **no *autonomous*
>   fan-out 0/10** — DeepSeek synthesises inline on a bounded 4-doc task (judge-appropriate 8/10).
>   INVESTIGATED (not a bug): the `task` tool + the mig-0073 subagents WERE wired/available, and DeepSeek
>   delegates 3× when *coached* (C7b `test_commercial_fan_out_scenario.py`) — uncoached strategy-selection on
>   a small matter, NOT a capability limit; the Phase-3 strategy/R4 question is *at what corpus scale*
>   autonomous fan-out is needed; **A8** negative control honest-absence **10/10**, fabrication 0/10.
> - **Maintainer calls settled (plan §Open calls):** #3 rubric strictness = **record rates, bars unset**
>   (set later vs this baseline); #5 spend = **N=1 smoke / N≥10 freeze**, Claude-judging free; #6 = **single
>   DeepSeek family** now (2nd family = later one-env-var expansion).
> - **PICK UP EXACTLY HERE → START N0:** instantiate `AsyncPostgresStore` in the lifespan (mirror the
>   checkpointer DI seam), pass `store=` + a `CompositeBackend` with
>   `/memories/{company,practice,user,matter}/` + `/conversation_history/` routes to `create_deep_agent`;
>   read-only wrapper for company/practice; namespace-distinctness assertion; key via `rt.context`. **No
>   semantic index yet** (filter-only). **Gate: A5 must light up** (cross-thread recall 0/10 → rises) with
>   nothing else regressing — re-run the Track-A matrix and compare. ADR-F049 is *accepted* with N0.
> - **Gotchas (carry forward):** the **agent's retrieved CHUNK set is still not observable** from steps
>   (only doc filenames in `tool_result` summaries, bounded ~2000 chars) — chunk-level retrieval attribution
>   (a `retrieved_chunks` column) is deferred to N0+ if doc-level proves too coarse; **A5 fixtures must use a
>   NON-matter aside** (the agent auto-writes matter facts via `record_matter_fact` → cross-thread recall of
>   *matter* facts already works via memory; the fixture asserts thread-1 fired no matter-memory write tool);
>   the **`args` Workflow param arrives as a STRING** (`JSON.parse` it in the script); the dev container
>   writes evidence as **root** → chown back; R4 cost cap still a **no-op**; deepagents minors break →
>   re-verify Store/CompositeBackend signatures at the N0 boundary; run pytest/ruff in the dev image with the
>   repo ROOT + `./skills` mounted.
> - **Decision context still live:** ADR-F049 (native Store + CompositeBackend substrate, eval-gated, accepts
>   at N0) + the eval-first plan `plans/RETRIEVAL-MEMORY-eval-first.md` (Phase-E exit reached); PageIndex =
>   eval candidate (Slice P), not a skip; reuse `retrieval_metrics.py`/`cuad_eval.fts_retrieve` (Track B) +
>   `track_a_lib`/`evals.scoring.score_all` (Track A) for any new gate.
>
> ▶ **PREVIOUS (2026-06-28): RETRIEVAL & MEMORY E0 — the CUAD Track-B retrieval-eval instrument + the
> FTS-only baseline SHIPPED + MERGED (PR #160, `main` `d0b117c8`).** Frozen floor
> (`docs/fork/evidence/retrieval-eval/`): within-doc hit@8 **0.39** / MAP 0.30; **cross-doc (150 docs) hit@8
> 0.04 / MAP 0.02 — lexical FTS collapses at scale**, 0.00 for semantically-named clauses — the headroom
> embeddings/rerank/PageIndex must earn. Reuse `retrieval_metrics.py` + `cuad_eval.fts_retrieve`; the matter
> `_FTS_SQL` projects no offsets (the eval mirrors it, drift-guarded); seed `normalized_content` verbatim;
> CUAD CC-BY-4.0/gitignored. (E1 above builds on this harness.)
>
> ▶ **PREVIOUS (2026-06-26): AUTHORSHIP Slice 2 — roster-aware negotiation + richer authorship signals —
> SHIPPED + MERGED (PR #156, main `c661c70`) (ADR-F048 addendum; migration `0077`; NO new HTTP
> route / no new dependency).**
>
> ✅ **MERGED (2026-06-27): PR [#156](https://github.com/sarturko-maker/lq-ai-fork/pull/156) squash-merged under
> the full ADR-F005 gate (all 3 CI jobs SUCCESS on `e07d48c`).** `main` is now at `c661c70`; branch
> `fork/authorship-roster-slice2` deleted. The dev stack already runs the Slice-2 code (api+arq+web at mig `0077`,
> healthy) — no rebuild needed. **NEXT = the maintainer's-call line above** (don't start a new slice without
> confirmation).
>
> Delivers the four Slice-1 deferrals. Maintainer rulings: distinct THIRD-PARTY bucket for `'other'`; lazy
> operator auto-seed; `get_document_metadata` exposes email + docx author.
> - **`'other'` third-party side** (mig `0077` = drop+recreate the `side` CHECK, precedent `0070`; literals
>   in sync across `app.models.project._MATTER_PARTICIPANT_SIDES` / `schemas.matter_memory.MatterParticipantSide`
>   / frontend `PARTICIPANT_SIDES`+`sideLabel`('Third party')+`sideToneClass`(violet)). A known third party
>   (escrow agent, lender's counsel) renders in its OWN bucket — "weigh, don't silently adopt" — in both the
>   editor hand-back and the negotiation render.
> - **`get_document_metadata` tool** (`tools.py`, in `MATTER_TOOL_NAMES`, granted every matter-bound run):
>   email → stored `Document.structured_content` headers (From/To/Cc/Date/Subject, no re-parse); docx →
>   `core_properties` author/last-modified via the shared `load_matter_docx_bytes`. Matter-scoped, 404-conflated,
>   counts-only guard audit. **No new HTTP route → no `test_endpoints`/`test_openapi` change.** UNTRUSTED/forgeable
>   — informs candidacy, never authenticates.
> - **Roster-aware C5a render** (`commercial_tools._render_state_of_play` + `_negotiation_side` + `_group_by_side`):
>   groups marked-up changes/comments by side (OUR SIDE / THIRD PARTY / COUNTERPARTY). **KEY:** an unplaced author
>   defaults to COUNTERPARTY here (the agent opened the counterparty's doc → preserves the C5a respond-to-every-ref
>   loop) — UNLIKE the editor hand-back which ASKs on unknown. Classification is ADDITIVE LABELLING ONLY — every ref
>   still requires one decision; `evaluate_coverage`/`evaluate_anchoring` + the no-silent-action guarantee UNCHANGED.
> - **Lazy operator auto-seed** (`matter_roster_tools.ensure_operator_participant`, called in `composition.py` at
>   run start when a matter is bound): seeds the run owner (the authenticated session user, NEVER model input) as
>   `side='ours'`/`trust='confirmed'` (email as alias), so the agent needn't ask who its own side is. Committed in
>   its OWN session so it's visible to the same run's roster block + tool-time `classify_author`. Idempotent over
>   **active OR retired** rows — a lawyer-retired operator is NOT resurrected (ADR-F042 B2).
> - **DURABLE TRAP — coverage parity.** The negotiation render must keep EVERY change/open-comment ref in the
>   "decide one verdict per ref" list after grouping (the gate keys on refs, not authors). The editor and
>   negotiation renders deliberately do NOT share a bucketer (different unknown-default + the editor drops the
>   agent's own/resolved); they share only the public `classify_author`.
> - **DURABLE TRAP — operator seed must COMMIT in its own session** (the long compose read-session doesn't commit);
>   and probe idempotency over active+retired, else a human removal is undone.
> - **Verify:** mig `0077` round-trip; full api suite **2818 passed / 35 skipped / 0 failed**; mypy + ruff clean.
>   Web svelte-check 0, vitest **987**, prettier clean. Live: Cypress `authorship-roster.cy.ts` **3/3** (Third-party
>   badge, light/dark) + DeepSeek scenario (operator seeded + third party 'other' recorded). Adversarial review
>   (4-dim × verify, 14 agents): **0 blockers / 1 should-fix (fixed: retired-operator re-seed) / nits folded**.
>   Evidence `docs/fork/evidence/authorship-slice2/`.
>
> ▶ **PREVIOUS (2026-06-26): AUTHORSHIP Slice 1 — matter who-is-who roster + hand-back author
> resolution — SHIPPED on branch `fork/authorship-roster-slice1` (ADR-F048; migration `0076`; no new
> dependency).**
> A negotiation has many people redlining; the agent now knows who is who. Replaces the editor Slice-5
> naive author filter (over-trust: every non-agent author treated as the lawyer).
> - **Data** (`matter_participants`, mig `0076`): identity (display name + `aliases` JSONB match-set) →
>   `side` ∈ {ours, counterparty, unknown} + `role_label`, `trust` ∈ {inferred, confirmed}. Matter-scoped
>   (CASCADE); soft-retire via `superseded_at`; CHECK literals mirror `app.models.project` (keep in sync).
> - **Agent** (`app/agents/matter_roster_tools.py`, ZERO model calls): `record_matter_participant`
>   (auto-write `inferred`; **human-confirmed never overridden** — at most aliases widen) +
>   `list_matter_roster` + the pure `classify_author(author, roster) → agent|ours|counterparty|unknown`
>   (Python alias-match, normalised lower/trim — never SQL from the untrusted author string). Granted to
>   EVERY matter-bound run (all areas), grant set disjoint. Roster injected read-only (`format_roster_block`
>   → `MATTER_ROSTER_PROMPT`) + `MATTER_ROSTER_DOCTRINE` (record from emails/statements; on a re-read
>   incorporate ours, treat counterparty as a position, **ASK** on unknown then record the answer).
> - **The over-trust fix** (`review_edited_document_tools.py`): `_classify_edits` buckets each
>   change/comment via the roster (agent's own `DEFAULT_AUTHOR` dropped); `_render_supervised_edits` renders
>   OUR SIDE (incorporate) / COUNTERPARTY (negotiating position) / UNIDENTIFIED (ASK the user) distinctly.
> - **Check-in needs NO new machinery** — there is no langgraph interrupt and no `ask_user` tool; the agent
>   asks in its answer, the run ends, the user replies → existing thread-resume (ADR-F008). Doctrine, not a gate.
> - **Email signal is already agent-visible** (`read_document()` returns the `From:` line) — no ingestion
>   change for Slice 1; a structured `get_document_metadata` tool is deferred to Slice 2.
> - **Human surface** (`app/api/matter_roster.py`): `POST /matters/{id}/roster` (create, `trust='confirmed'`,
>   `user_id` from session), `PATCH /…/roster/{entry_id}` (partial edit, re-confirms), `POST /…/roster/{entry_id}/retire`
>   (soft). Owner-scoped 404; counts/IDs+side-only audit (`matter_roster.*`, no name/role text). The active
>   roster folds into the composite `GET /matters/{id}/memory` (`roster` field). Cockpit **Participants**
>   section in `MemoryPanel.svelte` (add/edit/remove; side badge; confirmed marker).
> - **DURABLE TRAP — author strings are untrusted/forgeable** (ADR-F048 §Consequences): a counterparty could
>   set their docx author to our lawyer's name → classified `ours`. The roster *reduces* over-trust (unknown
>   → ask) but is NOT cryptographic identity. Trusted authorship (WOPI-stamped) is future work.
> - **DURABLE TRAP — meta-test path count.** New roster routes → `test_endpoints.IMPLEMENTED_ROUTES` (PATCH
>   counts) + `test_openapi.EXPECTED_PATHS` + the `len(actual)` assertion (151 → 154; 3 path STRINGS:
>   `/roster`, `/roster/{entry_id}`, `/roster/{entry_id}/retire`).
> - **Verify:** migration `0076` upgrade→downgrade→upgrade round-trip on a throwaway pgvector container;
>   new `test_matter_roster` (20) + `test_matter_roster_api` + rewritten `test_review_edited_document` +
>   composition roster grant/inject tests; **full api suite 2800 passed / 34 skipped / 0 failed**, mypy +
>   ruff clean. Web: svelte-check 0, vitest **987**, prettier clean. Live Cypress `authorship-roster.cy.ts`
>   (add/edit/remove + light/dark) — run after rebuilding the `web` container.
> - **Deferred → authorship Slice 2 (on record):** C5a negotiation-path classification
>   (`extract_counterparty_position`/`respond_to_counterparty`); structured `get_document_metadata`; an
>   `'other'` side for third parties; auto-seed the operator/WOPI user as `ours`.
>
> ▶ **PREVIOUS (2026-06-26): editor Slice 5 "Done — hand back to agent" — SHIPPED on branch
> `fork/libreoffice-editor-slice5` (ADR-F047 Slice-5 addendum; NO migration / no new HTTP route / no new
> dependency). ✅ THE IN-APP WORD-EDITOR MILESTONE IS COMPLETE.**
> The lawyer clicks **Done — hand back** in the editor → the doc is saved → the editor closes and the
> conversation composer is **primed + focused** with an editable instruction naming the doc; the lawyer sends
> it (the existing `createRun({prompt, thread_id})` path) and the agent re-reads their edits.
> - **Resume was already real** — the agent-run subsystem continues a thread via the langgraph checkpointer
>   (`create_agent_run(thread_id=…)`); the CLAUDE.md "single-turn" blocker is the LEGACY CHAT endpoint, NOT
>   agent runs. The frontend resume is the existing `ConversationPanel.submit()` path — no new run code.
> - **"Zero new agent code" was wrong** (maintainer: *trusted supervisor*): C5a `extract_counterparty_position`
>   frames markup as the UNTRUSTED other side — wrong for a trusted lawyer. New **generic, area-agnostic** tool
>   `review_edited_document` (`app/agents/review_edited_document_tools.py`), granted to EVERY matter-bound run
>   beside the matter-memory tools: reuses `read_state_of_play` in a TRUSTED frame + **filters out the agent's
>   own pending redline** (author == `DEFAULT_AUTHOR`). Doctrine `MATTER_REVIEW_DOCTRINE` in the prompt (no
>   migration). Matter-docx loaders factored `commercial_tools` → generic `tools.py` (DRY).
> - **DURABLE TRAP — track-changes recording.** An Adeu redline has tracked CONTENT but NOT the
>   `<w:trackChanges/>` recording flag → the editor opens with Record Changes OFF → the lawyer's edits are
>   UNTRACKED (invisible to the re-read). Fixed in the BYTES: `redline_service.ensure_track_changes_recording`
>   (lxml) injects the flag into the redline output's `settings.xml`, **schema-ordered** (CT_Settings is an
>   ordered sequence) and handling an explicit `w:val="false"` (Word's "tracking off" → flip ON). Do NOT use a
>   client `.uno:TrackChanges` postMessage — it's a TOGGLE (turns recording OFF if already on) + races the load.
> - **DURABLE TRAP — hand-back button enablement.** Gate it on `phase==='ready'`, NOT on `saveState` leaving
>   `'loading'` (Collabora's `Document_Loaded` postMessage is ~50/50 under automation → a saveState gate traps
>   the user with a dead button + breaks Cypress). The CLICK guarantees the save (dirty → save-then-handback;
>   pure `saveTickOutcome` decides saved/failed/pending). Live Cypress: inject the `Document_Loaded` postMessage
>   to drive saveState deterministically.
> - **Authorship is naive for now** (one agent author == "ours"; ANY other author → "the lawyer", incl. a
>   counterparty's markup if present — bounded by the R6 grant + a per-author "flag it" cue, not eliminated); a
>   proper "who's on our team" identity model is a flagged Backlog slice (maintainer).
> - **Verify:** API suite **2775 / 0 failed** (+ Slice-5 tests), mypy + ruff clean; web svelte-check 0, Vitest
>   **976**, prettier clean; live headed-Cypress hand-back (editor → close → primed composer), evidence
>   `docs/fork/evidence/libreoffice-slice5/`. Adversarial review (4-dim × verify, 18 agents): **0 blockers**;
>   4 should-fixes + cheap nits folded (recording val=false + schema order, trusted-frame author cue, clean_view
>   label, EditorPhase reuse, `saveTickOutcome` test, this HANDOFF); deferred-on-record nits: lawyer-reply
>   `parent_id` handling, `_render_redline` inline dup (divergent), `_render_supervised_edits` over-passing.
>
> ▶ **PREVIOUS (2026-06-26): editor POLISH slice (4b) — SHIPPED on branch `fork/libreoffice-editor-slice4b`
> (ADR-F047 Slice-4b addendum; frontend + compose only — NO backend/migration/dependency).**
> Fixed the 4 maintainer-reported Slice-4 UX defects, live-verified at 1920/1440/1024 (light+dark):
> 1. *Editor too narrow* → `ConversationHost` editor card `flex-[2_1_0%]` vs conversation `flex-1` (2/3 : 1/3)
>    **+ the load-bearing companion: `DocumentEditorPanel` `<section>` needs `w-full`** or it shrinks to ~iframe
>    intrinsic width and leaves the blank gap (the "white space reserved for a panel" — was complaint #4).
> 2. *"What's New"/feedback/update popups* → compose `extra_params`: `--o:home_mode.enable=${COLLABORA_HOME_MODE:-true}`
>    (**the ONLY lever that sticks on prebuilt `collabora/code`**; **TRADE-OFF: caps 20 conn / 10 docs**, env-override)
>    + `--o:allow_update_popup=false`. `COLLABORA_HOME_MODE` + `COLLABORA_SSL_TERMINATION` now in `.env.example`.
> 3+4. *Doc tiny at 30% / whitespace-right* → **client-side iterative fit-to-width** off the **same-origin** internal
>    map (`iframe.contentWindow.app.map.setZoom` — there is **NO zoom postMessage**), fully `try/catch`-guarded.
>    THREE hard-won facts (all probe-verified, probes since deleted): **(a)** drive it from a **poll + ResizeObserver**,
>    NOT the one-shot `Document_Loaded` postMessage (unreliable + docPx lags it); the observer re-fits on every width
>    change (slide-in / rail-collapse / window-resize). **(b)** `getScaleZoom` is **base-2 but Collabora's real pixel
>    scaling is ~1.2×/level**, so a single computed jump lands ~0.68 short → **iterate ONE level/tick off the MEASURED
>    docPx** (pure unit-tested `nextFitAction`: grow to a 92–99% band, back off 1 level on overflow). **(c)** gate
>    convergence on **`getSize()` being STABLE across ticks** (it lags the iframe resize → a shrink vs a stale large
>    width leaves the doc overflowing the new pane) + separate the long cold-boot wait from the short fit budget.
>    A `fitted` spinner overlay masks the cold-zoom→fit jump.
>
> **DURABLE TRAPS (4b):** the internal-map reach (`app.map`/`_docLayer._docPixelSize`/`getSize`/`setZoom`) is
> version-fragile — keep it isolated behind `getCoolMap()`+`nextFitAction`, fully guarded (no-op → Collabora's default
> zoom, never a crash). `getScaleZoom` ≠ Collabora's pixel scaling (don't trust it; iterate off measured docPx).
> `getSize()` lags element resize (gate on stability). The `<section>` filling its flex slot needs **`w-full`** not
> just `h-full`. **Verify:** svelte-check 0; Vitest **969** (+6 `nextFitAction`); headed Cypress asserts doc fills pane
> (ratio∈[0.8,1.0]) at 3 widths; evidence `docs/fork/evidence/libreoffice-slice4b/`. Adversarial review (4-dim×verify,
> 20 agents): **0 blockers / 0 should-fixes**; all confirmed nice-to-haves folded (resize-refit, fit overlay,
> `nextFitAction` unit tests, `.env.example` vars, symmetric `load()` teardown).
>
> **NEXT = Slice 5 = "Hand back to agent"** (editor milestone's last slice): "Done — hand back" action beside Close →
> save → resume the run on the same `thread_id`; the agent re-reads the lawyer's tracked changes + comments via the
> existing **C5a** `extract_counterparty_position` path — **zero new agent code**.
>
> ▶ **PICKUP (2026-06-25): in-app Word editor — Slice 4 (cockpit Editor panel + reskin) SHIPPED**
> (branch `fork/libreoffice-editor-slice4`; **ADR-F047 Slice-4 addendum**; NO backend/gateway change, NO
> migration, NO new dependency). Slices 1–3 MERGED (S3 = PR #151, `8710af4`). **NEXT (after 4b) = Slice 5 = "Hand back to
> agent"** (the editor milestone's last slice): save → resume the run on the same `thread_id`; the agent re-reads
> the lawyer's tracked changes + comments via the existing **C5a** `extract_counterparty_position` path — **zero
> new agent code**. Put the hand-back affordance in the editor chrome (a "Done — hand back" action beside Close).
>
> **What Slice 4 shipped.** The lawyer opens an agent-redlined `.docx` IN the cockpit: it renders in a reskinned
> Collabora iframe + edits save back through the S3 WOPI PutFile.
> - **Asset-URL blocker solved (the S1 open question):** `cool.html` uses **absolute root asset paths**
>   (`/browser/<hash>/…`) + a `/cool/<wopisrc>/ws` socket (`data-service-root=""`), so the S1 `/collabora/`
>   sub-path could never serve the iframe. Fix = host Collabora at its **native root paths** in `web/nginx.conf`
>   (`/browser/`, `/cool/` WS-upgrade, `/hosting/`, **no strip**); the admin-deny stays a **regex** location so
>   nginx matches it BEFORE the plain-prefix proxies (admin paths still 404). `docker-compose`:
>   `COLLABORA_SSL_TERMINATION` defaults **false** for HTTP dev (→ `ws://`); **prod MUST set `true`**. Frontend
>   re-homes the discovery `urlsrc` PATHNAME onto `window.location.origin`.
> - **UX (maintainer-specified):** agent redlines (or lawyer clicks *Edit* in Documents) → editor **slides in
>   from the right**, conversation stays **left**, the practice-area **rail gracefully collapses** (shared
>   `cockpit.editorOpen` signal; `+layout.svelte` restores it only if it collapsed it). Conversation **never
>   remounts** (live-SSE): always the first flex child; editor flies in as a sibling (hidden+mounted on a
>   narrow/stacked host so the editor gets the whole pane). Auto-open fires only for a **freshly** produced
>   redline — baseline of existing redline ids snapshotted EAGERLY when the matter is known (NOT on the first
>   completed-run refresh — a review-caught bug where the headline "fresh conversation, first ask is a redline"
>   silently never opened); won't yank a doc the lawyer is editing.
> - **Launch = WOPI form-POST:** `POST /files/{id}/editor-session` (exists) → `GET /hosting/discovery` urlsrc →
>   iframe carries only `WOPISrc`; a hidden `<form method=POST>` POSTs the `access_token` (never in a URL).
>   **Reskin** = WOPI `ui_defaults` (classic toolbar, no sidebar/ruler — RELIABLE) + best-effort
>   `Hide_Menubar`/save-pill via same-origin (origin-checked) postMessage (one-shot `App_LoadingStatus` races the
>   `Host_PostmessageReady` handshake → reliable on a real cold open, ~50/50 under rapid automation; degrades
>   gracefully). **Deferred (incremental):** charcoal toolbar theming (`css_variables`) + reliable menubar-hide.
> - **Verify:** svelte-check 0 errors; **Vitest 963**; prettier/eslint clean (lone eslint = pre-existing
>   `catch (e)` in untouched code). **Live (headed Cypress, real Collabora):** agent redline renders with tracked
>   changes + comments (light/dark × wide/narrow); **edit→save round-trips through PutFile** (DB: `(agent draft)`
>   snapshot + live row flipped human-authored + `editor.file_saved` audit); **auto-open regression test passes**.
>   Evidence `docs/fork/evidence/libreoffice-slice4/`. Adversarial review (4-dim × verify, 13 agents): **5
>   confirmed / 4 refuted**, all 5 folded (auto-open seed + yank-guard + stacked-full-width + `isRedlineOutput`
>   dedup + failed-save `success` flag).
>
> **Slice 3 verified (MERGED):** ruff + mypy clean; migration **0075**
> round-trip on a throwaway DB; targeted `test_wopi`+storage+meta **68 passed**; **live smoke 20/20** on the
> rebuilt api (real MinIO+DB) incl. snapshot-then-mutate at the storage level
> (`docs/fork/evidence/libreoffice-slice3/`); adversarial review (4-dim × verify, 11 agents) **5 confirmed / 2
> refuted**, all folded. **The live dev stack is at mig 0075 with api+arq rebuilt on the merged code.**
>
> **Slice 3 what shipped (the WOPI write half; api only — no web/nginx change).** `POST /wopi/files/{id}/contents`
> (`X-WOPI-Override: PUT`); session now **editable** (`UserCanWrite=true`/`SupportsUpdate=true`/`ReadOnly=false`).
> **Version model = snapshot-then-mutate (maintainer's call), as TWO durable commits:** on the FIRST human save of
> an agent redline (`created_by_run_id` set) the agent's bytes are `copy_object`'d to a NEW immutable `File` row
> (`(agent draft)`, provenance kept → C7a Documents tab, key==id per ADR-0005) and the live row is flipped to
> `created_by_run_id=NULL` — **committed BEFORE** the live object is overwritten — so a PutFile retry after a later
> commit failure never re-snapshots the edited bytes. Then the live row is overwritten in place (`hash`/`size`/
> `updated_at`). Later saves mutate only; identical-hash = no-op. Untrusted body gated: size cap → 413,
> `guard_ooxml` (REUSED, in `pipeline/readers/_base.py`) + `ooxml_subtype=='docx'` → 400; lock via pure
> `decide_putfile_lock` (409 + `X-WOPI-Lock`); `X-COOL-WOPI-Timestamp` save-race → `409 {"COOLStatusCode":1010}`.
> **GetFile streams CHUNKED (no pinned Content-Length)** so it's correct across any DB/storage divergence window.
> **`files.updated_at`** (mig **0075**, nullable) makes `LastModifiedTime = updated_at or created_at` honest.
> Counts-only audit `editor.file_saved`; no model calls / no gateway reach / no new dependency. Decisions =
> **ADR-F047 Slice-3 addendum**. Research `docs/fork/research/libreoffice-editor.md`; Slice 1 = isolated
> `collabora` service + `/collabora/` proxy; Slice 2 = the WOPI read host (Slice-2 addendum).
>
> **Slice-4 durable traps (carry into S5 / any UI work):** Collabora's lifecycle postMessages only flow after
> the host pings `Host_PostmessageReady`, and `App_LoadingStatus` is ONE-SHOT — so the save-pill/menubar-hide are
> best-effort (retry the ping; degrade gracefully; don't gate a test on the pill). The redline-render canvas
> tiles paint several seconds AFTER the `<canvas>` element exists — settle generously before a screenshot.
> Cypress `trashAssetsBeforeRuns` (default true) WIPES `cypress/screenshots/` before EACH spec run — copy
> evidence out to `docs/` immediately, and run capture specs LAST. A real edit→save round-trip is drivable via
> Collabora postMessage `Action_Paste` + `Action_Save` (then verify the DB), but it MUTATES the file one-shot
> (agent→human-authored + a snapshot). The committed `libreoffice-editor.cy.ts` is live (needs the stack +
> Collabora + a redline in the Atlas matter) — not a CI gate.
>
> **Build/licence posture (resolved, unchanged):** **Collabora is MPL-2.0, NOT AGPL** (lighter than the
> grandfathered PyMuPDF AGPL). Dev + every integration slice run the **prebuilt `collabora/code`** pinned by
> digest (`sha256:75859dc9…` = 26.04.1.4). Clean unbranded/supported **production** posture (self-build OR
> subscription) is a deferred productionisation decision (MILESTONES Backlog). PyMuPDF-AGPL-cleanup is a separate
> backlog slice.
>
> **Carry into Slice 5 (durable traps):** run api ruff/pytest in the **dev image** (`lq-ai-api-dev`) with
> **`./api` mounted at `/app` AND `./skills` at `/skills:ro`** on `--network lq-ai_default` with `DATABASE_URL` →
> postgres; ruff uses the **repo-root** `ruff.toml` (mount repo root). Web: `cd web && npm run check && npm run
> test:frontend`; **rebuild the prebuilt `web` container before any UI/Cypress check** (it serves a built bundle).
> Cockpit Cypress nav: narrow needs `lq-cockpit-new-conversation` first; tabs use `class:hidden` (no-remount
> invariant); `{@html}` only via `renderModelMarkdown`. When a migration lands, rebuild api (+arq-worker) — api
> auto-migrates on boot; NEVER host-side `alembic upgrade` on the live DB; `docker image prune -f` (dangling) after
> a build. New api routes → BOTH `test_endpoints.IMPLEMENTED_ROUTES` AND `test_openapi.EXPECTED_PATHS` (a GET+POST
> on the same path string is ONE OpenAPI path). `gh pr create` → **`--repo sarturko-maker/lq-ai-fork`**. The
> `collabora/code` image ships **only bash**; the sandbox runs on **MKNOD alone**.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
*counsel* = real tools + gates + client memory + work product; *qualified* = enforced model/harness
qualification (F0-S9 tier floor) + area competence via curated tools and **controlling skills**; *supervised* =
human-owns every material write + escalation gates + auditable receipts. Full statement at the top of the COMM
plan (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`).

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ C4 ✓ C8 ✓ C9 ✓ + cockpit chat-UX ✓. C3 REFRAMED → matter-memory track (C3a/b/c); ADR-F042 ACCEPTED. C3a ✓ · C3b-1 ✓ · C3b-2 ✓ (ADR-F043) · C3c-1 ✓ (READ backend, ADR-F044) · C3c-2 ✓ (cockpit Memory panel) · C3-UM ✓ (the human "update memory" UX — pin composer + inline correct-a-fact + retire). The ENTIRE matter-memory track (read + write + human-correct) is SHIPPED. **C8/C9 redline-eval RE-RUN ✓** (2026-06-24): re-ran both
craft evals with the `surgical-redline` skill LOADED — confound removed, finding CONFIRMED. **REDLINE WORD-DIFF ✓**
(2026-06-24, branch `fork/redline-worddiff-adeu`, **ADR-F045**): the redline tool now renders surgically via Adeu's
NATIVE `adeu.diff.generate_edits_from_text` (applied via `engine.apply_edits` to bypass `validate_edits`) instead of
the wholesale prefix/suffix-trim path that SWALLOWED interiors; skill simplified to "quote the clause, change only the
necessary words — the tool diffs it." **Live-judged (Claude Opus 4.8): C9 surgical-pass 3/7 → 6/7, the Aegis NDA
pervasive-mutualisation case now STRONG·surgical (survived the refuter), seam defects eliminated.** **C7 SPLIT →
C7a redline-download SHIPPED** (2026-06-24, branch `fork/c7a-redline-download`, **ADR-F046**, migration `0071`): a
cockpit **Documents tab** + an **inline run-timeline download** surface the agent's redlined `.docx` over a new
`GET /matters/{id}/files` + a `File.created_by_run_id` provenance column, reusing the existing
`GET /files/{id}/content` (no new bytes path / SSE change). Live-proven on Atlas: a real DeepSeek redline →
output carries `created_by_run_id` → appears in the tab + inline. **C5 SPLIT → C5a PROVABLE NEGOTIATION LOOP
SHIPPED** (2026-06-24, branch `fork/c5a-negotiation-core`, **ADR-F032**, NO migration/endpoint/dep): the agent
reads the counterparty's marked-up `.docx` (Adeu-native tracked changes + comments) via
`extract_counterparty_position` → a `StateOfPlay` checklist, and responds to **every** change/comment via
`respond_to_counterparty` (closed taxonomy accept/reject/counter/leave_open/escalate + reply) under a
**code-enforced no-silent-action gate** (upfront coverage: exactly one decision per ref; post-write
reconciliation: every decision proved to land). Live-proven on DeepSeek: round-2 NDA → extract→respond,
accepted benign edits, rejected the one-directional swap (reverted to mutual), **escalated the below-floor
perpetuity demand (left visible, not conceded)**, replied to the comment; full coverage in one pass
(`docs/fork/evidence/c5a/`). **C5 SPLIT further → C5b-1 COMMENT-WIPE FIX SHIPPED** (2026-06-24, branch
`fork/c5b1-comment-wipe-fix`, ADR-F032 addendum, NO migration/endpoint/dep): the C5a guarantee was lossy at the
*document* level — a comment `reply` was silently deleted when the agent accept/reject-ed the change it was
anchored to (Adeu reports it `applied`; only raw-OOXML inspection caught it). Fixed with three code layers —
anchor-map capture (`StateOfPlay.comment_anchors`), an upfront `evaluate_anchoring` gate (reject `reply` on an
accept/reject-ed anchored change), and document-level reply-survival reconciliation. Live-re-verified at the
OOXML level (`docs/fork/evidence/c5b1/`): the counterparty comment now SURVIVES the round (it was deleted
before). **C5b-2 NEGOTIATION-REVIEW SKILL SHIPPED** (2026-06-25, branch `fork/c5b2-negotiation-review-skill`,
ADR-F032 addendum + ADR-F041, migration `0072`): the **craft layer** — a curated `negotiation-review` skill
(round-2 companion to `surgical-redline`) bound to Commercial + the stale 0066 negotiation doctrine refreshed +
a provider-marked DeepSeek/Claude-judged craft eval. Live (DeepSeek, `docs/fork/evidence/c5b2/`): **3/3
substantive craft pass** (one-sided strip reverted to mutual, below-floor perpetuity held, full coverage,
nothing conceded); **counter-with-reply 0/3** — an honest recorded tuning finding (the model reverts §3 rather
than counter-with-reply, so the comment is preserved-but-orphaned; the guarantee holds, no silent loss).
**C5b-3 NEGOTIATION LIVE VERDICT CHIPS SHIPPED** (2026-06-25, branch `fork/c5b3-deal-change-chips`, ADR-F032 +
ADR-F024 addenda, NO migration/endpoint/dep): the **live signal** on the round-2 loop — as the agent responds to
the counterparty, the cockpit flashes a transient **verdict chip per item** inline in the conversation ("C1 ·
accepted", "C3 · countered", "Com:1 · escalated"). Clones the `data-ropa-change` ledger→drain→transient-frame
seam (PRIV-9b), generalised to a `LiveChange`/`ChangeLedger` Protocol (area-agnostic runner drain; `RopaChange` +
new `DealChange` each `publish` themselves). `respond_to_counterparty` records `(ref, verdict)` per decision ONLY
on a verified+saved round; `data-deal-change` frame is `{ref, verdict}` (audit-safe, no clause text). Chip lives
in `ConversationPanel` (Commercial has no register), persists across stream re-opens, decays. Live-proven
end-to-end on DeepSeek (5 frames) + deterministic Cypress light/dark (`docs/fork/evidence/c5b3/`).
**NEXT = maintainer's call: C7b (drafter/reviewer fan-out roster) / C6 (controlling playbook skills — needs ADRs
F036/F038 first). Backlog: counter-with-reply skill tuning + a Claude-judged eval re-run when the gateway has an
Anthropic key (deepseek-pro stood in as judge — Claude not reachable locally).**

C4 was built **ahead of C3** (maintainer reprioritised 2026-06-22: C4 retires the milestone's central risk +
produces the work product). The full decomposition: `docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`.
**Privacy PARKED** (`docs/fork/plans/PRIV-BACKLOG.md`). **MCP capability** is its own approved milestone.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL):** `smart`/`fast`/`budget` repointed
minimax/MiniMax-M3 → deepseek on the local gateway (MiniMax out of quota). **`deepseek` alias has quota** and is
the qualified live-test target. Revert when MiniMax quota returns. C9 fact: `deepseek` → `deepseek-v4-flash`;
**`deepseek-pro` → `deepseek-v4-pro`** (both wired in `gateway.yaml`, same DeepSeek account/quota) — the
stronger tier for the "is it the model?" control.

## Done this session (C7b — DRAFTER/REVIEWER FAN-OUT ROSTER + POST-FAN-OUT RECONCILIATION — branch `fork/c7b-fan-out-roster`; ADR-F034; migration `0073`; NO endpoint/dep)

**What:** the complex-deal **roster** + the **reconciliation pass**. The lead fans out `clause-drafter` (one per
material head) + consults `clause-reviewer`, then reconciles the drafts into ONE position per head before emitting
one work product. Completes C7 (C7a download + C5b-3 live signal already shipped).
- **Fan-out is deepagents-native + model-driven — C7b added NO orchestration** (see the pickup note above). The
  roster is two declarative subagent dicts; the reconciliation is a single-dispatch tool gate, NOT a guaranteed
  flow (the flow guarantee is the deferred O-series — ADR-F034 names this boundary honestly).
- **Migration `0073`** (`down_revision 0072`): `_extend_commercial_roster` — a **reconciling** never-clobber JSONB
  swap of the verbatim 0057 single-researcher config → `[document-researcher, clause-drafter, clause-reviewer]`
  (0057's `= '{}'` guard is dead now; mirror 0066/0072's `WHERE col = :old` instead) + `_bind_deal_review_skill`
  (NOT EXISTS). Both module-level for the idempotency test. New subagents: model-free (ADR-F010), no `tools`
  (inherit guarded matter tools), `skills` ⊆ area (ADR-F017).
- **`skills/deal-review/SKILL.md`** (ADR-F041 craft layer, bound in 0073): triage → fan out per head → review
  (over-reach/under-protection/inconsistency/gaps) → `reconcile_positions` → emit one work product.
- **`reconcile_positions` tool** (in `COMMERCIAL_TOOL_NAMES`) + pure `evaluate_position_consistency`
  (`schemas/commercial.py`, mirrors `evaluate_coverage`): a head where drafts diverge needs an explicit
  `resolutions[head]` or the batch is **rejected** (no-silent-divergence). On success records a SAVEPOINT-isolated
  **counts+head-names-only** matter receipt (`_record_reconciliation_receipt`) + audits **counts only**. Records
  only on success.
- **Verify:** full api suite **2708 passed / 32 skipped / 0 failed**; ruff + mypy clean; migration round-trip
  (upgrade→downgrade→upgrade) on a throwaway pgvector DB. **Live (DeepSeek, `docs/fork/evidence/c7b/`):** the real
  agent fanned out **3 `task` delegations / 43 nested steps** and called **`reconcile_positions` (2 calls → 1
  receipt)** end-to-end — fan-out + reconcile + receipt all proven live (run ends `cap_exceeded` only because
  deepseek-flash keeps exploring AFTER reconciling — an honest ADR-F015 over-exploration finding, not a mechanism
  defect; mechanics are deterministically pinned). Adversarial review: **0 blockers / 0 should-fixes / 1 nit
  folded** (a docstring overstated resolution precedence — code is correct), 4 refuted; security clean
  (audit counts-only + receipt head-labels-only verified, matter-scoped, no leaks).

## Done earlier this session (C5b-3 — NEGOTIATION LIVE VERDICT CHIPS — branch `fork/c5b3-deal-change-chips`; ADR-F032 + ADR-F024 addenda; NO migration/endpoint/dep)

**What:** the **live signal** on the round-2 loop — the C5 analogue of PRIV-9b's changed-row highlight. As the
agent responds to the counterparty, the cockpit flashes a transient **verdict chip per item** inline in the
conversation. Clones the `data-ropa-change` ledger→drain→transient-frame seam.
- **Seam generalised (the one structural call):** new `app/agents/live_changes.py` = a `LiveChange`
  (`publish(publisher)`) + `ChangeLedger` (`drain()`) **Protocol**. The runner drain is now area-agnostic
  (`for change in change_ledger.drain(): change.publish(publisher)`). `RopaChange` gained a 2-line `publish`
  (byte-identical Privacy behaviour); the new `app/agents/deal_changes.py` `DealChange`/`DealChangeLedger` is
  the 2nd implementer (composition root already anticipated a 3rd — assessments). ADR-F024 addendum.
- **Backend:** `RunStreamPublisher.deal_changed(ref, verdict)` → transient `data-deal-change` `{ref, verdict}`
  (audit-safe; no clause text). `composition.py` creates a `DealChangeLedger()` in the COMMERCIAL branch +
  passes it to `build_commercial_tools`. `respond_to_counterparty` records one `(ref, verdict)` per decision
  ONLY after `recon.ok` + persist (record-only-on-a-real-change; nothing on a rejected round).
- **Web:** `run-stream.ts` `parseDealChangePayload` (both `ref`+`verdict` load-bearing; unknown verdict → null)
  + pure `dealVerdictLabel`/`dealVerdictTone` presenters. `ConversationPanel.svelte` `case 'data-deal-change'`
  → `pushDealChip` (dedupe by ref, 6s decay, reset on run change via `dealChipRunId`); chips render inline in
  the running turn, coloured per verdict tone via `--color-status-*` tokens. **Key fix:** chips are NOT cleared
  in `clearStreamState` (the poll re-opens the stream + re-delivers the transient frames every 2s, keeping them
  lit) — reset on run change / thread switch (`startPolling`) / decay / `onDestroy`.
- **Verify:** backend `tests/agents` 489 passed/1 skipped + 8 new tests green; full api suite green (see below);
  ruff + mypy clean. Web `npm run check` 0 err, vitest **942** (+ deal-change parser/presenter tests),
  prettier clean (lone eslint error = pre-existing `catch (e)` in untouched code). **Live (DeepSeek):** the
  provider-marked `test_commercial_deal_change_frames_live` captured **5 real `data-deal-change` frames**
  end-to-end (C1 accept / C2 reject / C3 accept / C4 escalate / Com:1 leave_open). **Cypress 2/2** light+dark,
  screenshots verified (`docs/fork/evidence/c5b3/`). NO migration/endpoint/dep; NO gate/guarantee change.

## Done earlier this session (C5b-2 — NEGOTIATION-REVIEW SKILL + BINDING + CRAFT EVAL — branch `fork/c5b2-negotiation-review-skill`; ADR-F041/F032 addendum; migration `0072`; NO endpoint/dep)

**What:** the **craft layer** on the round-2 negotiation loop — *prompt quality tuned by eval, not a runtime
gate* (ADR-F041), so it adds no gate and changes no guarantee. The negotiation companion to `surgical-redline`.
- **`skills/negotiation-review/SKILL.md` (NEW curated skill):** decide-every-item + the closed taxonomy +
  materiality + counter **surgically** (term-swap, cross-refs `surgical-redline`) + **counter-with-reply over
  reject-then-orphan** (the C5b-1 nuance) + escalate-don't-concede + untrusted-input framing (ADR-F028). Bound to
  Commercial. It *teaches*; the code (`evaluate_coverage`/`evaluate_anchoring`/`evaluate_gate` + reconciliation)
  *enforces*.
- **Migration `0072` (NEW, mirrors 0067):** `_bind_negotiation_review_skill` (idempotent `NOT EXISTS`) +
  `_refresh_negotiation_doctrine` (never-clobber `REPLACE` of the stale 0066 "accept, reject, or counter"
  paragraph — it predated the C5a tools — pointing at `extract_counterparty_position`/`respond_to_counterparty` +
  the skill + the full taxonomy). down_revision `0071`. No schema/route/openapi change.
- **`api/tests/agents/scenarios/test_commercial_negotiation_eval.py` (NEW, provider-marked):** fuses the C5a
  scenario with the C9 judge pattern — a plain task drives the **bound** skill; judge grades the response `.docx`
  for mutuality-restored / floor-held / comment-engaged. RIG assertions only (ADR-F015). Agent vs judge aliases
  decoupled (`LQ_AI_SCENARIO_MODEL` / `LQ_AI_JUDGE_MODEL`).
- **Tests + simplification:** two mirrored tests in `test_practice_areas.py` (binding+doctrine API assertion +
  migration idempotency/never-clobber); factored a generic `capture_output_file` into `commercial_redline_lib.py`
  (single-sources the storage fetch; `capture_redline` delegates; C5a scenario test refactored to use it).
- **Verify:** **full api suite 2684 passed / 31 skipped / 0 failed** (dev-image, throwaway test DBs); ruff
  (CI-exact, root config) + mypy clean. **Live (DeepSeek agent, deepseek-pro judge, 3 reps,
  `docs/fork/evidence/c5b2/`):** 3/3 substantive craft pass (§3 reverted to mutual surgically, §4 below-floor
  perpetuity held, §2 benign accepted, full coverage, `respond_calls` 7/7/4 = the gate adapting). **Honest
  finding: counter-with-reply 0/3** — the model reverts §3 (orphaning Com:1) rather than counter+reply; the
  guarantee holds (comment preserved, reply never silently lost), the *ideal* isn't yet driven on deepseek-flash
  → backlog tuning item (the skill carries the coaching; the model under-follows it). Claude (Opus 4.8) read the
  artifacts directly and **concurs** with the deepseek-pro verdicts (Claude not reachable on the local gateway —
  `ANTHROPIC_API_KEY` unset / no `claude` alias). Adversarial review: **SHIP**, 0 blockers/should-fixes/nits.

## Done earlier this session (C5b-1 — COMMENT-WIPE FIX — branch `fork/c5b1-comment-wipe-fix`; ADR-F032 addendum; NO migration/endpoint/dep)

**What:** make C5a's no-silent-action guarantee hold at the **document** level for comments. Raw-OOXML
inspection of the C5a live output found a real gap: when the agent `reply`-ed to a counterparty comment **and**
accepted/rejected the change it was anchored to, Adeu deletes the whole thread — silently wiping the reply while
reporting it `applied` (count-based reconciliation missed it). Three code layers (model judges, code disposes):
- **`negotiation_service.py` (A + C):** `read_state_of_play` now captures `StateOfPlay.comment_anchors`
  (`Com:N → Cn`, from a `[Com:N]` token sharing a change's `{>>…<<}` meta block); `apply_decisions` re-reads the
  output and **proves every reply survived** (raw `parent_id` match) — a wiped reply → `Reconciliation.ok=False`
  → persist nothing. Replaces the old corruption-only re-read that deliberately didn't count threads.
- **`schemas/commercial.py` (B):** model-free `evaluate_anchoring(comment_anchors, decisions)` + `AnchorReport`
  — rejects a `reply` on a comment anchored to an `accept`/`reject`-ed change (counter/leave_open are safe),
  collect-all-errors, refs-only message telling the model to counter or leave_open instead.
- **`commercial_tools.py` (E):** gate wired as step 3.5 in `_respond_to_counterparty` (after coverage, before
  the counter gate); `_render_state_of_play` annotates anchored comments + a coupling RULE so the model
  self-corrects up front.
- **Probed on the pin (Step 0, like F045):** `[Com:N]` co-occurs with `[Chg:N]` in the meta block (the anchor
  signal); `extract_comments_data` keys by RAW unprefixed ids (`"1"`); `add_comment(author,text,parent_id)` has
  **no text-range anchor** → no pure margin comment → the gate is the guarantee (not a re-homing trick); reject
  of an anchored change with a reply wipes the whole thread (applied=3/skipped=0 yet reply gone).
- **Verify:** 48 negotiation tests + `tests/agents` 502 green; **full api suite 2680 passed / 1 failed (the
  documented `test_ready` env-flake) / 2 skipped**; ruff + mypy clean. **Live (DeepSeek, `docs/fork/evidence/c5b1/`):**
  re-ran the round-2 NDA → the counterparty comment now **survives** the round (was deleted in C5a); the agent
  adapted across **4 `respond_to_counterparty` calls** when the gate refused reply+reject; swap reverted to
  mutual, perpetuity escalated (visible). Adversarial review: SHIP, 0 blockers, NITs folded.

## Done earlier this session (C5a — PROVABLE NEGOTIATION LOOP — branch `fork/c5a-negotiation-core`; ADR-F032; NO migration/endpoint/dep)

**What:** the commercial agent's **second round**. The counterparty returns a marked-up `.docx`; the agent
reads their tracked changes + comments and responds to **every** item, with a **code-enforced guarantee it
never silently accepts/rejects** (the maintainer's hard requirement). C5 was SPLIT: **C5a = the provable
backend core**; deferred → **C5b** (skill calibration + inline live chips + multi-round eval). Plan
`docs/fork/plans/C5a-provable-negotiation-loop.md`; ADR-F032.

- **Adeu 1.12.1 reads/writes the markup natively** (no OOXML code of ours; verified live then built on):
  `extract_text_from_stream(clean_view=False/True)` (CriticMarkup + `Chg:N` ids / accept-all) +
  `engine.comments_manager.extract_comments_data()` (`Com:N`); `engine.apply_review_actions([AcceptChange|
  RejectChange|ReplyComment])` + `apply_edits([ModifyText(comment=)])` for a counter. The maintainer's prior
  art `Claude-Plugin-MCP` (MIT) gave the *concepts* (closed taxonomy, layer-don't-reject, per-id state) but
  left completeness to the prompt — the **gate is the net-new piece**.
- **`api/app/agents/negotiation_service.py` (NEW)** — `read_state_of_play(docx)→StateOfPlay` (parses the
  CriticMarkup regions into synthetic refs `C1..Cn` in doc order + comments from `extract_comments_data`) and
  `apply_decisions(docx, state, decisions)→(bytes, Reconciliation)` (replies→rejects→accepts then counters;
  re-reads to prove each landed). SDK-only.
- **`api/app/schemas/commercial.py`** — `CounterpartyDecision` (closed taxonomy), `RespondToCounterpartyInput`,
  `evaluate_coverage` + `CoverageReport` (the **upfront coverage gate**: exactly one decision per ref).
- **`api/app/agents/commercial_tools.py`** — `extract_counterparty_position` + `respond_to_counterparty`
  closures (guarded, matter-scoped via `_matter_files_query`, 404-conflated); `respond` re-extracts ground
  truth → coverage gate → counter gate (D1–D6) → `apply_decisions` → reconcile → persist a `(response).docx`
  File (`created_by_run_id`) + a matter-memory `open_point` receipt fact; audit counts/IDs only. Both names in
  `COMMERCIAL_TOOL_NAMES` (auto-granted via the existing `build_commercial_tools`).
- **`api/app/agents/redline_service.py`** — extracted `word_diff_edits` to a module function (single-sourced
  for the counter path; the instance method delegates). Redline path unchanged (10/10 regression green).
- **Verify:** unit/integration (negotiation service + tools) green; ruff + mypy clean; redline regression
  10/10. **Live (DeepSeek, `docs/fork/evidence/c5a/`):** round-2 NDA, `status=completed`, both tools called,
  full coverage in one pass, **escalated** the below-floor perpetuity demand (left as a visible tracked
  change, not conceded). No new HTTP route (no `test_endpoints`/`test_openapi` change).

## Done earlier this session (C7a — REDLINE-DOWNLOAD surface — branch `fork/c7a-redline-download`; ADR-F046; migration `0071`)

**What:** the lawyer can now **download the redlined `.docx`** the commercial agent produces — both from a cockpit
**Documents tab** (every matter, all areas) and **inline** under the completed run that made it. Closes the stranded
work-product gap (the redline was persisted + audited but never surfaced). C7 was SPLIT (3 features > one-PR
discipline): **C7a = download only**; deferred = **C7b** drafter/reviewer fan-out roster, and the accept/reject/counter
**classification + deal-context live signal → C5**. Plan `docs/fork/plans/C7a-redline-download-surface.md`; ADR-F046.

- **Reused, not rebuilt:** `GET /api/v1/files/{file_id}/content` already streams bytes (owner-scoped 404). The
  download path is unchanged; C7a only adds a way to *find* the file + the UI. **No SSE/step protocol change** —
  `AgentRunStep` has only a text summary (no structured-artifact channel), so one matter-files endpoint feeds BOTH
  surfaces instead of threading a new frame (settled-rows-decide intact).
- **`File.created_by_run_id`** (mig `0071`, nullable FK → `agent_runs.id`, `ON DELETE SET NULL`, additive/no-backfill);
  `_apply_redline` stamps it (`run_id` already in scope at `build_commercial_tools`). Honest run→file provenance → the
  inline button filters to `created_by_run_id === run.id` (precise, not a filename heuristic).
- **`GET /matters/{project_id}/files`** — new `api/app/api/matter_files.py` on the `/matters` router, owner-scoped via
  `_load_visible_project` (404 cross-user/archived). Metadata only, newest-first, membership-union scope (mirrors
  `tools._matter_files_query`). Registered in `api/__init__.py`; meta-tests updated (`test_endpoints` IMPLEMENTED_ROUTES
  + `test_openapi` EXPECTED_PATHS, count 147→148).
- **Web:** `files.ts` `downloadFile` + pure `pickDownloadFilename`; `matterFiles.ts` `listMatterFiles`; `types.ts`
  `MatterFile`. `DocumentsPanel.svelte` (new, Svelte-5 runes; load/poll/reconcile mirror MemoryPanel; pure helpers in
  `<script module>`). `ConversationHost` — `'documents'` tab whenever a matter is set; conversation region stays MOUNTED
  behind `class:hidden` via `matterPanelOpen` (no-remount invariant); reset-on-leave. `ConversationPanel` (Svelte-4) —
  inline Download under each completed run, refetched when the completed-run set changes.
- **Verify:** migration upgrade+**downgrade** round-trip on a throwaway DB (live DB untouched); full api suite **2639
  passed / 2 skipped** (lone failure = the documented env-flake `test_ready`); targeted endpoint/commercial-tools/meta
  tests green; ruff + mypy clean. Web: `npm run check` 0 errors, vitest **938 passed** (+12), prettier/eslint clean on
  touched files. **Headed Cypress 2/2** (`c7a-documents.cy.ts`) + screenshot matrix → `docs/fork/evidence/c7a/`.
  **Live (Atlas, DeepSeek):** real redline run `b588d8f8…` completed → output `…(redlined).docx` carries
  `created_by_run_id` == the run id; uploads carry `null`; nonexistent matter → 404. Full chain proven through the
  rebuilt arq-worker.

## Previous slice (REDLINE WORD-DIFF — branch `fork/redline-worddiff-adeu`; ADR-F045; NO migration / deps)

**What:** the redline TOOL now produces surgical tracked changes itself, so the model only has to preserve unchanged
wording. Root cause of the C8/C9 swallow (read from Adeu's engine source): our adapter sent ONE wholesale
`ModifyText` per edit → Adeu's `_pre_resolve_heuristic_edit` trims only common prefix/suffix → **swallows unchanged
interiors**. Plan `docs/fork/plans/redline-worddiff-via-adeu.md`; ADR-F045; headline `docs/fork/evidence/c9/SUMMARY.md`.

- **`api/app/agents/redline_service.py` (the fix):** new `_word_diff_edits(engine, edits)` — for each
  `(target,new)`, diff `full` vs `full.replace(target,new)` via `adeu.diff.generate_edits_from_text` (sub-edits carry
  full-document `_match_start_index`), rationale on the first sub-edit; `dry_run`/`apply` now call
  **`engine.apply_edits(...)` directly, NOT `process_batch`** (the canonical `adeu.sanitize.core` pattern — bypasses
  `validate_edits`' per-sub-edit uniqueness check, which would reject a short region like "the Customer"; `apply_edits`
  trusts the positional index). **Wholesale fallback** when `full.count(target)!=1` (rare whitespace mismatch; D4
  already guarantees uniqueness in the doc text) — logged counts-only. Removed dead `_counts`.
- **`skills/surgical-redline/SKILL.md` → v2.0.0:** dropped the anchor-mechanics / decompose / "split the block" /
  "fold into the boundary" coaching; teaches "quote the clause, change only the necessary words, keep the rest
  verbatim — the tool diffs it." Skill-loader guard re-run green (no `": "` silent-drop).
- **`api/app/agents/commercial_tools.py`:** tool docstrings + preview self-review text realigned to the new approach.
- **`api/app/schemas/commercial.py`:** removed dead `changed_regions()`. **Gate D1–D5 UNCHANGED** — it keys on the
  minimal token diff (renderer-agnostic) and still guards genuine over-rewording; no threshold change (unverifiable
  at n=1, ADR-F045).
- **Empirically proven before coding** (read Adeu's `engine.py`/`diff.py`/`sanitize/core.py`; scratchpad
  `worddiff_design_probe2.py`): indemnity → 3 regions verb-phrase bare, multi-edit batches don't cross-contaminate,
  genuine rewrite still ONE block (renderer doesn't fake surgery), hyphen/underscore no corruption.
- **Verify:** `test_redline_service.py` 10/10 (5 new word-diff cases) · gate/loader/tools 52 · broad non-provider
  regression **513 passed** · ruff check+format clean · mypy clean on changed files. **Live (DeepSeek flash, C9
  harness, all 7 instruments + Claude-judge via `scratchpad/c9-judge.js`): surgical-pass 3/7 → 6/7, STRONG 6/7,
  redlined 7/7, boilerplate-bare 6/7 → 7/7; Aegis NDA mutualisation STRONG·surgical (refuter held); seam-defect
  duplication eliminated (deterministic scan).** The lone ADEQUATE (Meridian) is the model *choosing* to
  wholesale-rewrite a warranty disclaimer — a genuine rewrite the renderer correctly preserves, NOT a swallow.
  Evidence: `c9/flash`, `c9/verdicts/*.md`, `c9/SUMMARY.md` (v3) + `c9/v2-wholesale-render/` (archived v2).

### Earlier (C3c-2 — cockpit matter-memory panel SHIPPED; PR #137, branch `fork/c3c2-cockpit-memory-panel`)

**What:** the **frontend half** of the matter-memory tier (ADR-F042 §C3c) — a new **"Memory" tab** in the
cockpit's matter view rendering the C3c-1 composite + a human-authenticated wiki revert. **Pure frontend over
existing endpoints: no backend change, NO migration** (head stays `0070`), **zero new deps**. **Maintainer
chose** (AskUserQuestion): **Memory tab on ALL matters, any area** + **revert behind a confirm dialog**
(disabled while a run is active). No new ADR — F044 stays the governing decision (noted in the PR).

- **`web/src/lib/lq-ai/components/matter/MemoryPanel.svelte` (NEW)** — one scrollable view, four sections
  (Working summary / Facts / Pinned corrections / Activity log). `<script module>` exports the pure helpers
  (`logKindLabel`/`isRevertable`/`shortRunId`/`logTailNote`/`canRevert`) — the codebase has **no
  @testing-library/svelte**, so logic is tested at the helper layer (pattern: `MatterCard`/`AttachKBModal`).
  Mirrors `RopaRegister` for the `loadGeneration` out-of-order guard + the `runActive` `schedulePoll`/`stopPoll`
  poll + the `reloadKey` settle-reconcile. Revert = a `wiki_snapshot` log row → confirm `Dialog` → POST →
  refetch; **disabled while `runActive`** (don't race the agent). **Every** model-authored body
  (`content_md`/`body_md`/`body_preview`) renders through `renderModelMarkdown` (DOMPurify, media-forbid) —
  the only `{@html}`, never raw.
- **`web/src/lib/lq-ai/api/matterMemory.ts` (NEW)** — `readMatterMemory(id)` (GET) + `revertWiki(id, snap)`
  (POST `{snapshot_id}`) over `apiRequest` (base already `/api/v1`); barrel-exported as `matterMemoryApi`.
- **`web/src/lib/lq-ai/types.ts`** — hand-written interfaces mirroring the C3c-1 Pydantic models exactly
  (datetimes = ISO strings); **no frontend OpenAPI contract test exists** (verified) so nothing else to update.
- **`web/src/lib/lq-ai/cockpit/ConversationHost.svelte`** — widened `matterTab` to add `'memory'`; derived
  `matterTabs` (conversation always; `register` only narrow-Privacy; `memory` whenever a matter is set; **none
  for the unfiled bucket**). The conversation/register region stays **MOUNTED** under `class:hidden` so the
  live SSE stream + `runActive` never drop on a tab switch; `MemoryPanel` is a sibling `{#if}`. **No-remount
  invariant preserved** (verified by the reviewer).
- **Adversarial review (fresh-context, 8 lenses → per-finding refutation): SHIP — 0 blockers, 0 should-fixes,
  2 NITs, both folded:** (1) reset `matterTab`→`conversation` when the active tab leaves the strip (Privacy
  widen retires the register tab → nothing highlighted); (2) clear the revert dialog's target/error on close.
- **Verify:** `npm run check` 0 errors (5 pre-existing warnings); vitest **915 passed** (+11 new); eslint +
  prettier clean on all touched files. **Real-stack smoke** (rebuilt `api`): `GET /matters/{id}/memory` → 200
  with the exact composite shape. **Headed Cypress** (`c3c2-matter-memory.cy.ts`, rebuilt `web`): **2/2** —
  render-the-four-sections + revert round-trip (confirm dialog → POST `{snapshot_id}` → refetch) + the
  screenshot matrix → `docs/fork/evidence/c3c2/` (light/dark × wide/narrow, all visually verified clean; the
  Privacy capture shows Memory **beside** the ROPA register, proving the all-areas placement).

### Previous slice (C3c-1 — matter-memory READ backend; merged #136, ADR-F044, branch `fork/c3c1-matter-read-revert`)

The read/manage **backend** (this slice's dependency): two guarded agent read tools — `search_matter_memory`
(Python keyword match over the **LIVE** corpus, no SQL from the model, superseded facts never resurface) +
`matter_facts_as_of` (bi-temporal as-of; the date is reject-not-crash hardened via a `mode='before'`
`_require_iso_date_string` + `_utc_aware`) — granted to every matter-bound run, all areas, disjoint grant. A
composite `GET /matters/{id}/memory` (wiki + live facts + live corrections via the new uncapped
`live_corrections` + capped/counted log) and a human-authenticated `POST .../memory/wiki/revert {snapshot_id}`
(restore a chosen `wiki_snapshot`, snapshot-current-first → reversible, append-only; triple-scoped lookup →
404; **no agent revert tool**). **No migration; no model calls.** Full detail: memory `c3c1-matter-read-revert-shipped`.

### Previous slice (C3b-2 — gateway-routed consolidation/Lint SHIPPED; merged #135; branch `fork/c3b2-gateway-consolidation`)

(C3a — PR #133; C3b-1 — PR #134 [[matter-facts-c3b1-shipped]]: the typed bi-temporal fact ledger, ZERO model
calls. C3b-2 builds the automated hygiene on top.)

**What:** the matter agent can now **consolidate its own memory** in one tool call — the **first matter-memory
code that calls a model**, so the **ADR-F010 egress obligation lands here**. `consolidate_matter_memory` loads
the matter's live fact set whole + the wiki + the pinned corrections, routes **ONE** gateway chat completion
(mem0 extract→judge + Lint) under a new `lq_ai_purpose`, then applies the proposal **supersede-only** (retire /
replace — never delete, never edit a body in place) and **rewrites the wiki**. **Maintainer chose** (AskUserQuestion):
**facts + wiki**, **supersede-only**, **match the R4-no-op cost posture + gateway audit**. **No migration** (reuses
`0070` + `context_md`); **zero new deps**. Plan `docs/fork/plans/C3b-2-gateway-consolidation.md`; **ADR-F043** (proposed).

- **`app/agents/matter_consolidation.py` (NEW)** — `MATTER_CONSOLIDATION_TOOL_NAMES` (disjoint),
  `build_matter_consolidation_tools(session_factory, *, run_id, binding, gateway_factory=get_gateway_client)`
  (the **gateway DI seam** tests override), the zero-arg guarded `consolidate_matter_memory()`, and
  `_consolidate_matter_memory` = load → ONE `gateway.chat_completion` (`max_tokens` cap, `anonymize=False`,
  `lq_ai_purpose="consolidate_matter_memory"`) → lenient JSON parse → **pure validation pass** (every op id a
  LIVE `kind='fact'` row of THIS matter; no double-ref; temporal coherence for retire AND replace) → **all-or-nothing
  supersede-only apply** + `snapshot_and_rewrite_wiki`. A gateway error / truncation / malformed output / bad id
  → **reject-and-retry string, never a crash, zero writes**.
- **`schemas/matter_memory.py`** — `RetireConsolidationOp`/`ReplaceConsolidationOp` (discriminated on `op`) +
  `ConsolidationResult` (`extra='forbid'`, `new_wiki` ≤ wiki budget); extracted shared `_utc_aware` /
  `_absent_if_blank` helpers (C3b-1's `RecordMatterFactInput` now reuses them — single-sources the tz fix).
- **`app/agents/matter_memory_tools.py`** — extracted `snapshot_and_rewrite_wiki(...)` from `_update_matter_memory`
  (single-sources the snapshot+overwrite for C3a + C3b-2).
- **`app/agents/composition.py`** — grants `build_matter_consolidation_tools(...)` to **every** matter-bound run
  (all areas), beside the memory + fact grants; disjoint.
- **Gateway** — `consolidate_matter_memory` added to `_KNOWN_PURPOSES` (`gateway/app/api/inference.py`) +
  documented (`openai_schema.py`) + the propagation test (`test_inference_b4.py`). **⚠ frozenset at module load
  → the gateway must be RESTARTED to recognise the purpose** (unknown purposes fall back to `chat`, so the call
  still succeeds — only the routing-log tag differs until restart).
- **B2 carries over (structural):** corrections are read-only prompt input; the apply only touches live
  `kind='fact'` rows (a correction/cross-matter/superseded/invented id is unreachable) — no-fabrication +
  no-overwrite hold without prose. The tool's only model access is the injected `GatewayClient` (asserted by a
  unit test + an AST-parse egress guard — no provider SDK).
- **Adversarial review (workflow, 5 lenses → per-finding refutation): 0 blockers, 1 should-fix + 6 nits; 2 refuted.**
  Folded: **should-fix** = a `retire` of a *future-dated* fact set `invalid_at=now < valid_at` → DB CHECK crash
  (now rejected in validation, + regression test); nits = bound the echoed parse-error text, detect
  `finish_reason='length'` truncation → diagnosable reject, single-source the resolved `valid_at`
  (validation→apply), drop the dead `model_alias` builder kwarg, distinct `MAX_SUPERSEDES` constant. **Deferred**
  (documented): the DB connection held across the gateway await (consistent with every guarded tool; no lock).
- **Verify:** ruff (CI-exact 0.15.18) + format + mypy `app` clean; gateway mypy `--strict` + ruff clean;
  gateway suite **595 passed** (purpose test 3/3; lone `test_model_discovery` failure is pre-existing env-sensitive,
  reproduces in isolation, CI-green on main); **full api suite 2585 passed / 2 skipped** (lone failure = the
  documented env-sensitive `test_ready`).
- **Live (DeepSeek, `docs/fork/evidence/c3b2/live-matter-consolidation.json`):** seeded a duplicate party fact +
  a stale draft cap; the agent called `consolidate_matter_memory` → **`deepseek-pro` retired the duplicate**
  (`superseded_count=1`, `live_fact_count` 3→2, `total_fact_rows` stays 3 — **supersede-only, history preserved**)
  + rewrote the wiki; `status=completed`, no crash. **Craft finding (ADR-F015):** flash returned an all-NOOP (didn't
  dedupe); pro's first attempt set a `valid_from` ≤ the prior's `valid_at` → the temporal check **correctly
  rejected it** (no crash, agent surfaced "consolidation failed") — proving the validation works; a **prompt fix**
  (dedupe = RETIRE the redundant copy; `valid_from` only for a genuine LATER value change) then made pro
  consolidate cleanly. The supersede/wiki mechanics are deterministically covered by 19 unit tests.

### Previous slice (cockpit chat-UX render polish — merged #132, on main): dark-mode markdown parity
(`dark:prose-invert` on the agent-surface prose containers — the GFM-parser theory was a red herring) +
quieter tool calls. `vitest` 904/904. Redline download deferred to C7.

## Previous slice (C9 — Claude-judged manual redline tests; merged #131; no migration; no new ADR)

**What:** upgraded C8's craft signal from DeepSeek-judging-itself to **Claude (Opus 4.8) judging DeepSeek**
over a corpus spanning contract types **and** complexity, with the produced `.docx` surfaced for the
maintainer. Reuses C4/C8 (`apply_redline`/`preview_redline`, `seed_doc_matter`/`capture_redline`,
reconstruction). Plan `docs/fork/plans/C9-claude-judged-redline-tests.md`.

- **7 corpus instruments** (single-source `.docx`==normalized text): *moderate* — `securescan_msa`,
  `databridge_license`, NEW `aegis_mutual_nda`, `northwind_dpa`, `meridian_services_sow`; *complex*
  (dense multi-limb, added mid-slice on the maintainer's "the real test is long clauses where most language
  must be LEFT ALONE") — NEW `helios_master_agreement`, `orion_dev_licence`.
- **`tests/agents/scenarios/test_commercial_redline_manual.py`** (NEW, provider-marked) — purposive
  per-instrument prompts (names the one-sided heads, leaves surgical technique to the bound skill); runs the
  chosen model with the skill registry active; writes `c9/<id>/` (`original-*.docx`, `* (redlined).docx`,
  `reconstruction.txt`, `accepted-clean.txt`) + a merge-safe `manifest.json`; `LQ_AI_C9_ONLY` runs a subset;
  `LQ_AI_SCENARIO_MODEL` selects `deepseek` (flash) vs `deepseek-pro`. `complexity` field added to
  `RedlineScenarioDoc`.
- **Substrate bugfix `api/app/agents/skill_backend.py`** — `RegistrySkillBackend.grep`/`glob` now return a
  graceful unsupported `GrepResult`/`GlobResult` instead of inheriting the protocol's `raise
  NotImplementedError`. deepagents' `agrep`/`aglob` do NOT catch that, so **any run where the model called the
  builtin grep/glob hard-failed** (observed live: the NDA crashed mid-redline). Fixes every area agent
  (Privacy too). Test in `tests/agents/test_skill_backend.py`.
- **Judge deliverables (Claude):** `docs/fork/evidence/c9/SUMMARY.md` + `verdicts/<id>.md` + `flash/` & `pro/`
  `.docx`. **Finding:** flash surgical-craft **5/7** by the strong judge (vs C8's self-judged 2/6); the
  **complex** docs scored *among the best on both models* — complexity is NOT the craft predictor. The one
  consistent weakness is **pervasive mutualisation** (one-directional-throughout clauses → whole-clause
  rewrite). Pro re-run of the flash failures: fixed the SOW *robustness* (flash produced no redline) but did
  **worse** on the NDA (looped to `cap_exceeded`) — so the stronger tier does NOT reliably fix craft; the
  lever is **method** (a mutualisation worked-example in `surgical-redline` + a redline step-budget tier).
- **Live cockpit UAT (maintainer, end of C9):** drove the agent in the real UI on a "Project Atlas" deal
  suite (`/home/sarturko/atlas-deal-suite/`: an `.eml` with a **nested** term-sheet PDF, the Cirrus MSA
  `.docx`, a processor DPA PDF; org profile seeded as Northwind). The agent read all four (incl. the nested
  attachment), used **company memory**, produced a correct gap analysis + a successful tracked-changes
  redline. **Real fix committed:** the **arq-worker had no S3/MinIO env** (api/ingest did) → storage-backed
  agent tools failed in the worker; added the S3 block to `docker-compose.yml`. Dev-only/local (NOT
  committed): `LQ_AI_DOCLING_ENABLED=false` (Docling hung PDFs to its 300s timeout) and the seeded org
  profile. Full findings: memory `commercial-agent-live-uat-findings`.

## ▶ PICK UP — REDLINE WORD-DIFF SHIPPED (ADR-F045); next = maintainer's call (C7 / C5 / C6)

**C3-UM (the human "update memory" UX) is DONE** on branch `fork/c3-update-memory-ux` (squash-merged; the whole
matter-memory track is now complete). What shipped — three human gestures on `MemoryPanel.svelte`, all
overlay/append-only per ADR-F042, disabled while a run is active:
1. **Pin a correction** — `+ Pin a correction` composer (textarea + char cap) → `POST .../memory/corrections`
   (the existing C3a human-authenticated pin, `trust='human-pinned'`). Pin VISUAL = F013 brand-left-accent.
2. **Correct a fact** — a quiet `Correct` on each Fact row pre-fills the composer with a `Re: "…" →` stub
   (free-text, **no DB link** — maintainer chose free-text over an anchor column → NO migration). Still a
   plain correction (B2 no-overwrite).
3. **Retire** — quiet `Retire` on a correction (soft `superseded_at`) AND on a fact (close `invalid_at`),
   shared confirm dialog. **Maintainer chose corrections + facts.** NO free-edit of the working summary (it's
   agent-regenerated; levers stay pin + revert).

**Backend (NO migration, head stays `0070`):** two new endpoints in `api/app/api/matter_memory.py` —
`POST .../memory/corrections/{entry_id}/retire` (idempotent soft-retire) + `POST .../memory/facts/{entry_id}/retire`
(close window; **future-dated fact `valid_at >= now` → 409 Conflict**, never the `invalid_at > valid_at` CHECK 500;
the C3b-2 trap). Both owner-scoped 404 + kind-scoped, audit IDs-only, tz-aware `datetime.now(UTC)`. Frontend:
`api/matterMemory.ts` (`pinCorrection`/`retireCorrection`/`retireFact`) + `types.ts` + the `MemoryPanel.svelte`
gestures (`canWrite` aliases `canRevert`; one shared retire dialog). **Traps hit:** new endpoints must be
registered in BOTH `tests/test_endpoints.py` `IMPLEMENTED_ROUTES` AND `tests/test_openapi.py` `EXPECTED_PATHS`
(+ bump the hardcoded `len(actual) == N` path count) or the meta-tests fail; new path params need a value in
`test_endpoints.py` `_PARAM_VALUES` (`entry_id`).
**Verify:** api 2627 passed (lone failure = the documented env-flake `test_ready` — expects 503 but the dev-image
runs on the live network so deps are reachable → 200; CI-green in a clean env). web 926 vitest + `npm run check`
0 err + Cypress 2/2 + live Atlas smoke (pin→retire-correction→retire-fact, idempotent, cross-kind 404). Evidence
`docs/fork/evidence/c3-um/`. No new ADR (F042/F044 govern).

**Disk-cleanup folded into the same PR** (Crostini hit 100% full, 2026-06-24): root cause = btrfs storage-driver
subvolume leak (690+ orphaned layers from frequent ~6 GB rebuilds). Reclaimed ~100 GB (3.9 GB → 82 GB free; rebuild
brought it to ~74 GB). Prevention = CLAUDE.md rebuild-time rule (`docker image prune -f` after every build,
dangling-only) + `scripts/docker-prune.sh` (dangling + stopped containers + leftover `lq_ai_test_*`), no cron.
**Recovery playbook if it recurs:** `docker system prune -af` (keeps running-stack images + volumes); if orphaned
btrfs subvolumes persist, `apt-get install btrfs-progs`, stop docker, delete `/var/lib/docker/btrfs/subvolumes/*`
(safe when `docker images` is empty), then `rm -rf /var/lib/docker/{image,buildkit,btrfs,containers}` (KEEP
`volumes`+`network`), restart docker, `compose up -d --build`. The btrfs cleaner reclaims on the first commit
(starting docker triggers it). See [[redline-viewing-direction]] memory for the new redline-viewer roadmap input.

**Test vehicle on the dev stack:** the **Atlas** Commercial matter (`905720d1-5d17-43cd-a8f0-3a76d095de34`, owner
admin) seeded with a wiki + 2 wiki snapshots + 5 live facts + 1 superseded fact + 1 human-pinned correction.
Deep-link `/lq-ai?area=commercial&matter=905720d1-5d17-43cd-a8f0-3a76d095de34` → **Memory** tab.

**▶▶ PICK UP HERE — C5b-1 COMMENT-WIPE FIX SHIPPED; next slice = maintainer's call.** C5a's negotiation loop is
now document-level-honest for comments (a reply can no longer be silently wiped — anchor map + `evaluate_anchoring`
gate + reply-survival reconciliation, ADR-F032 addendum; live-re-verified at the OOXML level). C5 split into
C5a (core) + C5b-1 (this fix) + C5b-2/C5b-3 (below). **Remaining open commercial slices (maintainer picks):**
- **C5b-2** — the negotiation craft layer: a `negotiation-review` SKILL.md (materiality / authority zones /
  worked examples — incl. *prefer counter-with-reply over reject-then-leave-open when there's a comment to
  engage*, so the comment stays anchored + visibly answered; this is the C5b-1 craft follow-up) + skill-binding
  migration `0072` (mirror `0067`, down_revision `0071`); a multi-round Claude-judged eval (like C9).
- **C5b-3** — the **inline live verdict chips**: clone the `data-ropa-change` ledger→drain→transient-frame seam
  to a `data-deal-change` frame rendered as a transient chip **in the conversation** (NOT a register-row wash —
  there is no deal-terms panel; chip keyed by ref/verdict). Full clone recipe mapped (ropa_changes.py →
  deal_changes.py, composition COMMERCIAL_AREA_KEY branch, runner drain on tool_result, stream.deal_changed,
  run-stream.ts parseDealChangePayload, ConversationPanel dispatch).
- **C7b** — drafter/reviewer **fan-out roster** + post-fan-out reconciliation. The fan-out *infrastructure*
  already works (subagent steps nest via `parent_step_id`, mirrored to SSE + parsed by the web, tested in
  `test_agent_composition.py`); **blocker #6 (`work_product_attributions`) is a legacy-chat concern, NOT on the
  agent path** — so C7b is "define drafter/reviewer subagents (mig reconciling `0057`) + a reconciliation pass."
- **C6** — controlling playbook skills (blocked by ADRs **F036 + F038** — canonical severity scale + the
  controlling-skill plane — which must be decided first). C5a deliberately uses **prose** house positions, not
  the `PlaybookPosition` mechanism, to stay unblocked.
**C5a backlog (Adeu gaps, recorded):** no public pure-margin-comment (comment with no edit) — C5a anchors a
comment to a change/counter, and accept/reject carry their reason in the receipt not a Word comment;
per-revision dates not surfaced. **Carried cross-cutting:** in-app redline *viewer/accept*
([[redline-viewing-direction]], MCP-gated / AGPL caveat); marker-fence hardening (C3a nit); embedding/FTS
search UI (gateway `/v1/embeddings` 501 until B6); log pagination.

## Gotchas / durable traps (C8 + C4 + carried)

- **C5a — Adeu `Chg:N`/`Com:N` ids are internal and RENUMBER after accept/reject; a *modify* is a del+ins
  PAIR.** So (1) the model must reference the ids from the **extract** step (C5a hands it synthetic `C1..Cn`
  refs that decouple it from Adeu's numbering — `negotiation_service` re-derives the map on respond from the
  same unchanged doc); (2) accept/reject of one logical change acts on **both** Adeu ids; (3) reconciliation
  must NOT re-diff ids across the apply — trust Adeu's `(applied, skipped)` + `skipped_details`. **Accepting a
  change deletes the comment thread anchored to it** (correct — the acceptance resolves their comment), so
  apply **replies before accepts** and do NOT post-count threads (it false-fails). `apply_review_actions`
  takes ONLY `AcceptChange`/`RejectChange`/`ReplyComment` — no public resolve / no pure-margin comment.
- **C5a — the coverage gate must re-extract the StateOfPlay as GROUND TRUTH, not trust the model's view.**
  `respond_to_counterparty` re-reads the doc and runs `evaluate_coverage(state.change_refs,
  state.open_comment_refs, decisions)` — exactly one decision per ref. A silent omission → reject; the
  reconciliation then proves each decision landed (skipped/under-applied counter → reject, persist nothing).
  This is the no-silent-action guarantee; keep it prompt-independent.
- **C5b-1 — accepting OR rejecting a change DELETES the comment thread anchored to it (incl. a reply we made),
  and Adeu reports it `applied` — so a reply could silently vanish.** Three things close it and must stay
  together: (1) `read_state_of_play` builds `StateOfPlay.comment_anchors` (`Com:N → Cn`) from a `[Com:N]` token
  sharing a change's `{>>…<<}` meta block; (2) `schemas.commercial.evaluate_anchoring` rejects a `reply` on an
  `accept`/`reject`-ed anchored change BEFORE any write (counter/leave_open are safe — a counter layers a new
  edit and keeps the original change + thread); (3) `apply_decisions` re-reads the output and proves each reply
  survived. **`extract_comments_data` keys comments by RAW unprefixed ids** (`"1"`, not `"Com:1"`) for both the
  id and `parent_id` — the survival match normalizes `Com:N → N` (`split(":")[-1]`). **There is NO public
  margin-comment API** (`add_comment` has no text-range anchor), so the gate is the guarantee, not a re-homing
  trick. Rejecting a commented change *orphans* the counterparty comment (text preserved, anchor gone — may not
  render in Word) — not a silent loss, but the *ideal* is to **counter** (keeps it anchored) + reply; that
  coaching is C5b-2. **Always re-verify redline/comment output at the OOXML level (`word/comments*.xml`), not the
  reconstruction text — the reconstruction masked this bug.**
- **C7a — `api`, `arq-worker`, `ingest-worker` are SEPARATE per-service images** (`lq-ai-api` /
  `lq-ai-arq-worker` / `lq-ai-ingest-worker`), all built from `./api`. `docker compose build api` rebuilds ONLY
  `lq-ai-api` — the workers keep their old image. After a code/migration change you must
  `docker compose build api arq-worker ingest-worker` (then `up -d --force-recreate` them) or the **agent loop
  runs stale worker code** (the agent run executes in arq-worker — confirmed by the C9 UAT S3-env finding). Verify
  with `docker inspect --format '{{.Image}}' lq-ai-<svc>-1` after a rebuild. The CLAUDE.md "rebuild all three
  together" rule means three SEPARATE builds, not one.
- **C7a — Postgres `now()` is CONSTANT within a transaction.** Two rows inserted in the same test transaction
  share `created_at`, so a "newest-first" ordering assertion falls back to the id tiebreaker and flaps. Set an
  explicit `created_at` per row in ordering tests (in production each file is its own transaction, so it's fine).
- **C7a — a new FK column means a unit test that INSERTS the row must satisfy it.** `_apply_redline`'s
  `created_by_run_id` FK → `agent_runs.id` forced the happy-path test to seed a real thread+run; the
  reject/scope tests never persist a File so a bare `uuid` passes. And **Svelte merges `<script module>` +
  `<script>` into one module** — importing a type in both blocks is a "Duplicate identifier" (import once).
- **C3c-2 — the `web` container serves a PRE-BUILT bundle; rebuild it before any UI/Cypress verification**
  (`docker compose up -d --build web`) or you test stale code (a CLAUDE.md hard rule — bit the cockpit
  screenshot workflow). Headed Cypress needs `DISPLAY=:0` (`X0`/`X1` sockets present on this box).
- **C3c-2 — no `@testing-library/svelte` in `web/`.** Test Svelte component LOGIC by exporting pure functions
  from `<script module>` and unit-testing those (pattern: `MatterCard`/`AttachKBModal`); cover DOM + interaction
  via Cypress. Don't add the library (CLAUDE.md: justify every dep).
- **C3c-2 — cockpit Cypress nav:** deep-link `/lq-ai?area=<key>&matter=<id>` and wait for
  `[data-testid="lq-cockpit-conversation"]`. At narrow/stacked width a fresh deep-link (no `&thread=`) shows the
  thread LIST, not the panel where the matter tab strip lives — click `lq-cockpit-new-conversation` to enter the
  panel first, THEN the `lq-cockpit-matter-tab-{id}` tabs (incl. `…-memory`) are reachable.
- **C3c-2 — adding a cockpit tab must NOT remount the conversation pane.** Keep the conversation/register region
  MOUNTED behind `class:hidden={matterTab === '…'}` and render the new view as a SIBLING `{#if}`; moving
  `{@render conversationPane()}` to a new DOM position remounts `ConversationPanel` → drops the live SSE stream
  and resets the bound `runActive`. Also reset `matterTab` to a tab that's always present when the active tab can
  leave the derived strip (e.g. a Privacy matter widening past the split budget retires the `register` tab).
- **C3c-2 — any `{@html}` of model output needs `renderModelMarkdown` + an `eslint-disable-next-line
  svelte/no-at-html-tags` comment** (the shared sanitizer is DOMPurify media-forbid; raw `{@html}` fails lint
  and is an XSS sink). Every matter-memory body (`content_md`/`body_md`/`body_preview`) is untrusted model text.

- **F045 — the redline renderer uses Adeu's NATIVE word-diff applied via `engine.apply_edits`, NOT
  `process_batch`.** `redline_service._word_diff_edits` diffs `full` vs `full.replace(target,new)` with
  `adeu.diff.generate_edits_from_text` (sub-edits carry full-document `_match_start_index`), then
  `engine.apply_edits(subs)` applies them positionally. **Do NOT switch back to `process_batch`** — it runs
  `validate_edits`, which re-checks each sub-edit's `target_text` for uniqueness and REJECTS a short region
  ("the Customer" recurs) with `BatchValidationError: Ambiguous match`. `apply_edits` trusts the index and
  skips that check (the canonical `adeu.sanitize.core` pattern). The fragment-relative trap: diff the FULL doc
  text, never the bare clause, or `_match_start_index` is relative to the fragment and misplaces. Fallback to a
  wholesale `ModifyText` only when `full.count(target)!=1`. Proof scripts: `scratchpad/worddiff_design_probe2.py`.
- **F045 — a genuine rewrite (every word changed) correctly renders as ONE block; the renderer does not fake
  surgery.** So the surgical signal still depends on the model preserving unchanged wording (the skill teaches
  it) and the gate (D1–D5, minimal-diff) still guards genuine over-rewording. A carve-out APPEND now renders as
  a clean insertion via the word-diff (no more zero-width-insertion crash to dodge) — the skill no longer needs
  the "fold into the boundary" mechanic, though `_EDITOR_ERROR_MSG` remains as a defensive catch.
- **C8 — the surgical-craft eval is provider-marked** (`test_commercial_redline_eval.py`): run live with
  `LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_REDLINE_EVAL_REPS=N UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c8`.
  It regenerates ALL eval files in one run — if a (doc,rep) yields no redline, no per-rep file is written, so
  reconcile the dir against `eval-report.json` before committing (delete stale files from a prior run).
- **C9 — builtin `grep`/`glob` crash a run if the backend doesn't implement them.** deepagents exposes
  `grep`/`glob` filesystem tools; `BackendProtocol`'s default `grep`/`glob` `raise NotImplementedError`, and
  the async wrappers (`agrep`/`aglob`) do NOT catch it → the exception leaves the tools node and fails the
  whole run. Any custom backend MUST override `grep`/`glob` to return a `GrepResult`/`GlobResult` (even just
  an `error=`), never inherit the raise. Fixed for `RegistrySkillBackend` (C9); watch for it in any future
  backend. **C9 manual harness** (`test_commercial_redline_manual.py`, provider-marked) writes per-MODEL dirs
  (`c9/flash`, `c9/pro`) with a merge-safe `manifest.json`; `LQ_AI_C9_ONLY` runs a subset. The one open craft
  weakness it found is **pervasive mutualisation** (see pickup) — flash rip-and-replaces, pro can `cap_exceeded`.

- **C8/C9 re-run — a bound skill's BODY reaches the model ONLY on-demand (ADR-F016 progressive disclosure).**
  deepagents' SkillsMiddleware auto-injects only the skill **index** (name + `description:`) into the system
  prompt; the full SKILL.md body is fetched by the model calling the builtin **`read_file`** on
  `/skills/<name>/SKILL.md`. So "skill loaded + bound" (the premise gate) ≠ "the worked examples are in context"
  — the model must choose to read them. So (1) make the `description:` itself carry the core directive (always
  present); (2) to confirm the body was consulted, look for `read_file` in the manifest `tools_called` (distinct
  from `read_document`, the matter-doc reader) and/or the redline reproducing the skill's worked examples.
- **C8/C9 re-run — redline craft at n=1 is NOISE; the `surgical` boolean is judge-borderline.** C9 is one run per
  (instrument, model); the surgical-pass *count* swings on borderline "is a bare-grant-clause wholesale rewrite
  surgical?" calls — even the *same* Claude panel split on it across two runs. Read deterministic signals
  (manifest `redlined`/`boilerplate_bare`) + direct text inspection as primary; treat verdict counts as
  qualitative. A real craft-rate change needs **multi-rep × strong-judge** → **don't ship a craft tweak you can't
  measure**. To compare two runs fairly, re-judge BOTH with the *identical* panel (removes judge drift).
- **C8/C9 re-run — a judge agent given a path to a MISSING `reconstruction.txt` (a no-redline run) will hunt and
  read a DIFFERENT run's file → a verdict for the wrong artifact.** Bit the v1 Meridian + pro DataBridge/Northwind
  cells. **Gate trust on file-existence**: a verdict is valid only if its `reconstruction.txt` exists on disk;
  otherwise use the manifest ground-truth (no-redline).

- **Adeu is installed `--no-deps`** (4 places: api/Dockerfile, api/Dockerfile.dev, ci.yml, + any dev-image test
  command). Its `fastmcp[apps]` dep bumps starlette 0.48/pydantic 2.13/mcp → breaks `APIRouter`. The SDK
  (`RedlineEngine`/`ModifyText`/`process_batch`) needs only `diff-match-patch` + `structlog` (+ lxml/python-docx
  /rapidfuzz/pydantic already in-tree). **Dev-image test commands MUST `pip install diff-match-patch structlog`
  + `pip install --no-deps adeu==1.12.1`** or `from adeu import …` fails `ModuleNotFoundError: structlog`.
- **`apply_redline` redlines the named doc FRESH each call (no stacking)** — the agent must pass ALL edits in
  ONE batched call (the tool docstring says so). Multiple calls each re-redline the ORIGINAL → only the last
  call's edits survive in its output File. For long docs needing >50 edits/call → chain on the prior output or
  fan out (C7). A redline run is step-intensive; ADR-F026 budget is 100 steps/900s (fine for one batched
  single-doc redline; **50-page docs need C7 fan-out + a redline budget tier** — recorded as a finding).
- **`max_steps` is API-capped at `le=100`** (`schemas/agent_runs.py`); the harness sets it directly on the
  AgentRun row (bypasses the schema), so live scenarios can exceed 100 if needed — but production is 100.
- **Killed-container test-DB contamination:** killing a `docker compose run` suite container mid-run leaves the
  reused test DB dirty (leftover admin/session rows) → spurious CLI/audit/last-admin failures on the next run.
  Re-run the suspect files in a FRESH container to confirm. The `test_ready_reports_per_dependency_status`
  health test is separately env-sensitive (passes isolated; "fails" on the live network).
- **Provider tests need the gateway key UNSET to skip:** `docker compose run api` inherits `LQ_AI_GATEWAY_KEY`
  from the api service env, so the full suite would RUN the provider tests (slow/hangs on real gateway calls).
  Run the regression suite with `-e LQ_AI_GATEWAY_KEY= -m 'not provider and not e2e'`.
- **Live redline scenario:** `tests/agents/scenarios/test_commercial_redline_scenario.py` (provider-marked) seeds
  the real `securescan_msa.build_msa_docx()` into MinIO + runs DeepSeek + writes `.docx`/reconstruction/
  accept-clean/judge to `UX_B1_EVIDENCE_DIR`. The judge's input was truncated at first (false WEAK); caps are
  now generous (must fit the full redline). Run via the dev image on `lq-ai_default` with the api gateway env +
  `UX_B1_EVIDENCE_DIR` mounted; `chown` the root-owned evidence before `git add`.
- **Migration head is `0070`** (`0070_matter_memory_typed_facts.py`, C3b-1 — additive-nullable typed-fact
  columns on `matter_memory_entries`; `0068` is the store, `0069` the skill binding; **C3b-2 added NO
  migration** — it reuses `0070` + `context_md`). Re-check the head before writing in case anything lands first. Fresh-head check before any migration; rebuild api+arq-worker+
  ingest-worker after one; never host-side `alembic upgrade` on the dev DB; never `compose down -v`.
  (**C3c-1 added NO migration** — pure read + revert over existing rows/columns; head stays `0070`.)
- **C3b-1 — a Pydantic `datetime` field accepts a tz-NAIVE value from a bare ISO date** ("2026-01-01" parses
  with `tzinfo=None`). Comparing it against a tz-aware `DateTime(timezone=True)` column raises `TypeError`,
  which escapes a guarded tool as a CRASH (audited error + re-raised), not a reject-and-retry. Any datetime the
  model supplies must be normalised to UTC-aware at the schema boundary (now the shared `_utc_aware` helper in
  `schemas/matter_memory.py`, used by `RecordMatterFactInput` + the C3b-2 `ReplaceConsolidationOp`). Tests using
  only `+00:00` offsets mask it — add a bare-date case.
- **C3c-1 — a Pydantic `datetime` field reads a BARE NUMERIC string as a Unix timestamp, not a year.** `"2026"`
  becomes `1970-01-01`, `"1700000000"` becomes 2023 — silently, no reject. On a load-bearing arg (the
  `matter_facts_as_of` date) that is a confidently-wrong recall, not a crash, so `_utc_aware` (a `mode='after'`
  validator) can't catch it. Reject an all-digit string at the boundary with a `mode='before'` validator (the
  shared `_require_iso_date_string` in `schemas/matter_memory.py`, on `as_of` + both `valid_from`s). A `"2026-05"`/
  `"last Tuesday"` is already rejected by Pydantic; only the all-numeric case slips through. Add a `"2026"` test.
- **C3c-1 — `load_pinned_corrections` is the per-run prompt-INJECT slice (newest 30, capped), NOT the search/read
  corpus.** It exists to bound prompt size; reusing it for a read surface silently hides older live corrections.
  The read surface (search + the GET) uses the UNCAPPED `live_corrections(db, project_id)` (oldest-first rows) in
  `matter_fact_tools.py`. Keep the two distinct: capped-bodies-newest-first for injection, uncapped-rows-oldest
  for read.
- **C3b-2 — closing a bi-temporal window must respect the `invalid_at > valid_at` CHECK or the flush CRASHES.**
  Setting `invalid_at` to a time **at or before** a fact's `valid_at` (e.g. retiring a *future-dated* fact at
  `now`) violates `chk_matter_memory_entries_valid_window` → `IntegrityError` on flush → escapes the guarded
  tool as a crash, not a reject. The consolidation validation pass guards BOTH op kinds (`retire`: `now > valid_at`;
  `replace`: `new_valid_at > prior.valid_at`) BEFORE any write. Any future window-closing code must do the same
  pre-flush check. `record_matter_fact`'s supersede already enforces this for its one path; a *retire* (no
  replacement) was the new gap.
- **C3b-2 — a new `lq_ai_purpose` only takes effect after a GATEWAY RESTART** (`_KNOWN_PURPOSES` is a
  module-load frozenset in `gateway/app/api/inference.py`). An unknown purpose falls back to `chat` (the call
  still succeeds), so a live agent run works against an un-rebuilt gateway — only the routing-log tag is wrong
  until the gateway is rebuilt. Rebuild `gateway` when adding a purpose. **Egress-guard test pattern:** assert a
  module's only model access is the injected `GatewayClient` by AST-parsing its imports (forbid
  openai/anthropic/httpx/requests roots) — grepping the source text is fooled by a docstring that *names*
  `api.openai.com` (`test_module_has_no_direct_provider_egress`).
- **🔴 SKILL.md frontmatter must not contain an unquoted `": "` (colon-space) in any value (`description:` is
  the usual culprit).** The loader does `yaml.safe_load`; an unquoted plain scalar with `": "` parses as a
  mapping → `frontmatter YAML is invalid: mapping values are not allowed here` → the loader logs a WARNING and
  **silently skips the skill** (it vanishes from the registry; bound skills are filtered to known names, so the
  binding is silently dropped). This bit C8's `surgical-redline` (never loaded until C3a fixed it) and C3a's
  `matter-memory`. Use " — " / "," / "(…)", or quote the value. Guarded now by
  `test_every_real_skill_loads_no_silent_drops` (`tests/test_skill_loader.py`) — run it after adding/editing any SKILL.md.
- **The per-area grant seam** is `composition.py` (`area_key == PRIVACY_AREA_KEY` / now `== COMMERCIAL_AREA_KEY`).
  `COMMERCIAL_AREA_KEY = "commercial"` lives in `commercial_tools.py` (mirrors `PRIVACY_AREA_KEY` in ropa_tools).
- **Dev-image suite/lint recipe:** `docker compose run --rm --no-deps --entrypoint bash -v "$PWD/api:/app"
  -v "$PWD/skills:/skills" -v "$PWD/ruff.toml:/ruff.toml" -e LQ_AI_SKILLS_DIR=/skills api -c "pip install -q
  pytest pytest-asyncio respx mypy types-PyYAML 'ruff>=0.6' diff-match-patch structlog && pip install --no-deps
  adeu==1.12.1 && <cmds>"`; `chown -R $(id -u):$(id -g) app tests` after. CI ruff = `ruff>=0.6`; format with it
  before pushing (version drift). `mypy app` via unpinned mypy false-flags `ropa_export.py`/`tabular.py` — ignore.
- Dev login `admin@lq.ai` (password in local `.env`, not committed); api :8000, web :3000, gateway :8001.
  Privacy area id `71bb11f9-e5e6-403d-ae91-e4401a644927`. Adeu SDK-only — never `adeu.server`/`adeu.mcp_components`.

## Merge policy (ADR-F005, agent-merged)

Squash-merge when the FULL gate passes: CI green + containerized suites (counts quoted) + fresh-context
adversarial+security+simplification review + live verification (DeepSeek) when behaviour changes + HANDOFF
updated. `gh` always `--repo sarturko-maker/lq-ai-fork --head <branch>`. Branch off `main` first.
