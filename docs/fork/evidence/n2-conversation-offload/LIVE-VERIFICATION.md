# N2 live verification (ADR-F049) — conversation-history offload + within-chat recall (A6)

Dev stack, 2026-06-29. The conversation-history offload that N2 was meant to *build* was found to be
**already wired by N0**: deepagents' always-on default `SummarizationMiddleware` (which `create_deep_agent`
installs unconditionally) runs over our N0 `CompositeBackend`, so evicted history offloads to
`/conversation_history/{thread_id}.md` → the Store namespace `("conversation", thread_id)`. N2 therefore
shipped as **verify + test + eval** — no production code. IDs/counts only; no clause text, no secrets.

## 1. Deterministic gate (dev image, no Postgres / no live model)

`tests/agents/test_summarization_offload.py` — **5 passed**. Drives the **real** deepagents
`SummarizationMiddleware` (built exactly as `create_deep_agent` does, `create_summarization_middleware(model,
backend)`) over our `build_memory_backend` composite + an `InMemoryStore`, through a langgraph runtime:

- **Routing drift-guard:** `artifacts_root == "/"` → `_history_path_prefix == "/conversation_history"` →
  the offload path `/conversation_history/{thread}.md` resolves to `CONVERSATION_ROUTE` (a *writable*
  `StoreBackend`, not the read-only company/practice wrapper). Fails loudly if deepagents changes
  `artifacts_root` handling or the offload path (the orphaned-transcript regression).
- **Offload lands in the Store:** `_aoffload_to_backend(...)` → ns `("conversation", thread_id)`, key
  `/{thread_id}.md`; file name == namespace key (both `str(thread_id)`).
- **Append on 2nd offload** (single key, two `## Summarized` sections, all turns present).
- **Thread isolation** (a 2nd thread → disjoint namespace; cross-read → not-found).
- **Read-back** through the composite (the builtin-`read_file` recall routing) returns the content.

Full api suite (touched-service gate): **2864 passed / 38 skipped / 0 failed**. `ruff` (root) + `mypy app`
(205 files): clean.

## 2. Live A6 — within-chat recall post-compaction (the N2 gate; finding per ADR-F015)

Provider-marked Track-A matrix, N=1, agent `deepseek`, judge `deepseek-pro`, the N2 code mounted, an
`InMemoryStore` injected so the `/conversation_history/` route is live and a `compaction_max_input_tokens`
override (7000) so the always-on summariser's 0.85x trigger fires in a bounded run (production sends 200k).
`test_track_a_eval.py` **1 passed** (rig assertions: every run terminal + every masked packet emitted).

**A6 result — `a6_within_chat_recall_post_compaction`:**
- **`conversation_offloaded = True` (378 B)** — compaction **actually fired**; the opening, code-bearing
  turn was evicted to the Store under `("conversation", thread_id)`. (Observed post-run by searching the
  injected Store — turns "likely compacted" into measured.)
- **`status = completed`** (14 steps: `search_documents` + 4× `read_document`; no cap).
- **L1 `recalled_code = True`** — the post-compaction answer states the exact aside `ORION-7741`;
  `did_the_work = True` (both vendors summarised).
- **L2 verdict PASS** (`recalled_correctly=true`, `fabricated_code=false`). The masked judge was given the
  ground-truth code in `expectations` as an answer key — necessary because `ORION-7741` is a *self-stated*
  fact in the user prompt, which masking strips (unlike A1/A8, whose ground truth is in the timeline).
- **`read_file` was NOT called** — recall flowed through the **LLM-generated summary**, which preserved the
  code. So native compaction's summary sufficed here; the explicit offload-file read (and N3's
  `search_matter_conversations`) is the backstop for details a summary drops or for cross-thread recall.

**Finding:** within-chat recall *after a real compaction* worked for this case (carried by the summary).
The deterministic test guarantees the durable transcript is always in the Store regardless; N3 adds the
explicit retrieval tool. Tuning note: at the small fixture-document scale the conversation sits near the
trigger — windows of 12000/9000 completed but did **not** compact (in-context recall only); 7000 was the
point where compaction fired while the light per-doc task still finished. The trigger is model-/content-
dependent (ADR-F015), which is itself a reason the robust path is N3's explicit search, not trigger-tuning.

## 3. No-regression smoke (the other four scenarios, same N=1 snapshot)

Same matrix, scenarios unchanged by N2 (none use the new knobs; their compose path is byte-identical):
- **A5** cross-thread recall — honest abstention, `recalled_detail=False`, verdict PASS (expected-fail) ✓
- **A7** strategy — inline synthesis (`delegated=False`), `compared_both=True`, verdict PASS ✓
- **A8** negative control — verdict PASS (honest absence; the L1 `acknowledges_absence` fragment list
  missed the wording this sample, the judge confirmed honest absence) ✓
- **A1** multi-doc grounding — this N=1 sample **failed** with an empty answer mid-tool-loop (2 model
  turns) — a transient DeepSeek/gateway run failure on an **unchanged** scenario path (E1 baseline is 8/10
  over N=10; the 2 known fails there are also empty/capped answers). Noise, not an N2 regression; recorded
  honestly rather than re-rolled. The rig assertion (`status` terminal + packet emitted) held — the
  provider test passed.

Evidence: `track-a-report.json` + `packets/*.json` in this directory (masked packets — timeline + visible
answer + rubric only; no docs, no agent prompt, no run id).

## Gate status

- Offload mechanism (routing + Store landing + append + isolation + read-back): ✅ deterministic
  (`test_summarization_offload.py`) + ✅ live (A6 `conversation_offloaded=True`).
- Within-chat recall post-compaction: ✅ observed live (A6 recalled `ORION-7741` after a real compaction);
  a finding (ADR-F015), not a frozen baseline.
- Nothing regresses: ✅ full api suite 2864/38/0; the live matrix passed (A1's transient failure is
  unchanged-path noise, documented).
- **No production code, no migration, no new dependency, no gateway change** (maintainer ruling: the
  offload was already wired by N0; the degraded-key edge is accepted + documented — ADR-F049 N2 addendum).
