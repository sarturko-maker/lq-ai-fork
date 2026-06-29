# N3 live verification (ADR-F049) — cross-thread conversation recall (A5)

Dev stack, 2026-06-29. N3 adds the agent's **reader** over the conversation transcripts that N2 made
persist to the langgraph Store: a thin, matter-scoped `search_matter_conversations(query, thread_id=None)`.
The single new behaviour — an agent in thread 2 recalls what was said in thread 1 of the *same matter*
(CLAUDE.md blocker #3). **No migration, no new dependency, no gateway change.** IDs/counts only in audit;
no clause text, no secrets (evidence packets verified clean of gateway key / DB URL).

## 1. Deterministic gate (dev image, real test DB + an InMemoryStore — no live model)

`tests/agents/test_matter_conversation_tools.py` — **13 passed**. Drives the tool against the real test DB +
an `InMemoryStore` seeded exactly where the N2 offload writes (`("conversation", str(thread_id))`):

- **Cross-thread recall:** a detail in an EARLIER thread is found from a different (current) thread; the
  earlier thread is identified by title; the result is wrapped in the untrusted-data label.
- **Current-thread excluded** from the whole-matter sweep (already in the agent's context).
- **`thread_id` filter** narrows to one thread; a **foreign thread_id** (another matter/owner) silently
  matches nothing — no cross-read, no existence leak.
- **Cross-matter isolation:** matter A's search never returns matter B's transcript though both share one
  Store (the SQL `WHERE user_id AND project_id` thread enumeration is the boundary).
- **404-conflation:** a vanished / cross-owner matter → "no longer available".
- **Untrusted text:** an embedded "ignore previous instructions" comes back INSIDE the labelled data block;
  the tool acts on nothing.
- **Reject-not-crash:** a blank query / malformed thread_id is rejected back to the model.
- **Audit body-free:** a seeded marker reaches the model's result but never the audit row (counts/IDs +
  `result_chars` only).

Grant confinement: `MATTER_CONVERSATION_TOOL_NAMES` is disjoint from every other matter/domain grant
(asserted here + in `test_matter_consolidation.py`). Full api suite (touched-service gate): **2877 passed /
1 failed / 37 skipped**, where the single failure was the prompt-assembly oracle
(`test_agent_composition.py::test_system_prompt_assembly`) reacting to the new `MATTER_CONVERSATION_DOCTRINE`
— updated to assert the new doctrine order + that `search_matter_conversations` is named, then **re-verified
green (3 passed)**. So the suite is green with that one test-only correction; CI re-runs the full suite on
the PR as the authoritative gate. `ruff` (root) + `mypy app` (206 files): clean.

## 2. Live A5 — cross-thread recall via the tool (the N3 gate; finding per ADR-F015)

Provider-marked Track-A matrix, N=1, agent `deepseek`, judge `deepseek-pro`, the N3 code mounted, a shared
`InMemoryStore` injected across both threads of the same matter. `test_track_a_eval.py` **1 passed** (rig
assertions: every run terminal + every masked packet emitted; 1m55s).

**A5 result — `a5_cross_thread_recall` (expected `pass`):**
- **L1 `recalled_detail = True`** — thread 2's answer states the planted aside: *"You said you're working
  from our **Manchester office** today."*
- **The recall is GROUNDED, not a guess** — thread 2's timeline shows a `search_matter_conversations`
  tool call (the ONLY tool it called), which retrieved thread 1's transcript before answering.
- **L2 verdict PASS** (`recalled_correctly=true`, `hallucinated_detail=false`); judge evidence-quote:
  *"You said you're working from our Manchester office today."*
- **`fixture_valid = True`** — thread 1 fired NO matter-memory write tool (`t1_memory_writes=[]`), so the
  recall is genuinely cross-thread *conversation* memory, not the matter-fact tier.
- **`conversation_offloaded_t1 = False` → `conversation_seeded_t1 = True`** — thread 1's one-line ack did
  not cross the compaction trigger (content-dependent at fixture scale, the N2 finding), so the gate seeded
  thread 1's `("conversation", …)` namespace deterministically — exactly the "seed + best-effort live"
  design (maintainer ruling). The seed path is what made the gate repeatable; the deterministic unit test
  also seeds, so N3's *reader* (its actual deliverable) is proven independently of N2's compaction trigger.

**Finding:** cross-thread conversation recall works — the agent reaches for `search_matter_conversations`,
retrieves the prior thread, and grounds its answer. A5 was RED (0/10) through E1; N3 turns it green.

## 3. No-regression (the other four scenarios, same N=1 snapshot)

| scenario | expected | verdict | note |
|---|---|---|---|
| **A1** multi-doc grounding | pass | **PASS** | unchanged path |
| **A5** cross-thread recall | pass | **PASS** | the N3 gate (above) |
| **A6** within-chat recall post-compaction | expected-fail | **PASS** | N2 finding, holds |
| **A7** strategy choice | pass | **FAIL** | `cap_exceeded` — see below |
| **A8** negative control | pass | **PASS** | honest absence holds |

**A7 FAIL is unchanged-path DeepSeek variance, not an N3 regression — and this is provable.** A7 does not
inject a Store, so its conversation tool is never built; its 28-step timeline contains only pre-existing
tools (`read_document` ×4, `get_document_metadata` ×4, `record_matter_participant` ×3, `search_documents`,
`write_todos`) and **zero `search_matter_conversations` attempts** — the N3 tool and doctrine provably
played no part. The run wandered into metadata/roster work and exhausted its step budget → empty final
answer → judge FAIL. This is the same `cap_exceeded` failure mode the E1 baseline documents for A7
(autonomous fan-out 0/10; judge-appropriate ~8/10) and that N2's evidence saw transiently on A1. N2's
single A7 run happened to pass; N3's single A7 run happened to cap — N=1 variance on an unchanged path.
Recorded honestly rather than re-rolled. (The only N3 delta to A7's prompt is 4 lines of conversation
doctrine for a tool the harness does not build — a harness-only asymmetry; in production every matter-bound
run has a live Store, so the tool is always present and the doctrine always matches.)

Evidence: `track-a-report.json` + `packets/*.json` in this directory (masked packets — timeline + visible
answer + rubric only; no source docs, no agent prompt, no run id; verified free of gateway key / DB URL).

## Gate status

- The reader (cross-thread find + cross-matter/owner + foreign-thread_id isolation + current-thread
  exclusion + reject-not-crash + injection-as-data + audit-body-free): ✅ deterministic
  (`test_matter_conversation_tools.py` 13/13).
- Cross-thread recall via the tool: ✅ observed live (A5 grounded PASS, `recalled_detail=True`).
- Cross-matter / cross-owner 404 + isolation security check: ✅ deterministic + clean review.
- Nothing N3-attributable regresses: ✅ full api suite green (one test-only oracle update); A1/A6/A8 pass;
  A7's `cap_exceeded` is proven unchanged-path variance (no conversation-tool involvement).
- **No production change beyond the tool + its wiring; no migration, no new dependency, no gateway change.**
- Adversarial review (4-dim × adversarial verify): **SHIP, 0 blockers**; 1 should-fix folded (the
  `thread_id` param documented in the tool docstring).
