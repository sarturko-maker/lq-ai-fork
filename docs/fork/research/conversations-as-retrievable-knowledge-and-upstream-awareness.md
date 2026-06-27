# Research — Conversations as a first-class retrievable source (and an upstream-awareness review)

**For:** the maintainer's new point on top of the two prior retrieval docs
(`document-discovery-and-map.md`, `document-retrieval-at-scale-and-cost.md`). Those established a
documents **MAP** (L1 routing) + a local-embedding **hybrid retriever** (L2: pgvector + FTS + rerank,
*already shipped for KnowledgeBases, not wired to matters*) + within-doc navigation (L3); PageIndex =
niche/later; local embeddings = the cost play. **THE NEW REQUIREMENT:** retrieval must NOT be
documents-only. A matter's knowledge also lives in **CONVERSATION** history. We must support *"search
CONVERSATIONS within a matter"* (across past threads) and recall *"within a chat"* (one thread), and
the embedding/index strategy must span **documents + conversations + distilled memory**. This doc also
records an **upstream-awareness** review (LegalQuants/lq-ai), since upstream has moved since our
baseline.

**Method:** codebase discovery on the chat/conversation substrate + matter-conversation links (LQ.AI
fork, `main`, head `3ed7596`; code claims re-read at the cited `file:line`) + a code-grounded
upstream-awareness diff (`upstream/main` `4de10ec`, **76 commits** since our baseline `f91149a`) + web
research on conversation-retrieval patterns + the two prior docs' verified verdicts carried forward.
**Date:** 2026-06-27.

**Posture reminders baked into every recommendation:** all **external-provider** LLM calls route
through the in-house gateway (sole key-holder + only egress, ADR-F010); **local in-process model
compute is permitted** (torch already in-image); a per-action cost cap / halt / grant brake on every
agent tool call (R4/R5/R6, ADR-F002); unit-of-work memory is **auto-write-then-correct** (ADR-F042);
Apache-2.0 posture; new dependencies are SBOM/supply-chain surface. **GOVERNANCE:** upstream is
**FROZEN** (ADR-F001) — §6 is *awareness only*; any sync needs the maintainer's explicit **per-case**
approval; nothing here recommends merging or cherry-picking.

**What carries forward from the prior two docs (intact):** the four-layer stack — **L1 documents MAP**
(router) → **L2 within-corpus hybrid retrieval** (local dense + FTS + local rerank, reusing
`api/app/knowledge/retrieval.py`) → **L3 within-doc navigation** → selection/stickiness glue; the map
lives in the typed fact ledger (ADR-F042/F043/F044); local embeddings are the cost play (torch
in-image; gateway has local-provider doors); PageIndex is niche/later. **What this doc adds:**
conversations become a **first-class source inside the SAME L2 stack** (source-typed, matter-scoped,
recency-weighted), plus the raw-vs-distilled split and within-a-chat context management.

---

## 1. Executive summary

- **Unified-corpus verdict: one retriever, three source types.** A matter's knowledge is
  **documents + conversations + distilled memory**. The right design is **not** three separate search
  engines but **one local hybrid retriever (L2)** over a **source-typed, matter-scoped** index where a
  conversation turn is just another chunk (`source_type='conversation'`) alongside document chunks
  (`source_type='document'`) and — optionally — distilled-memory entries (`source_type='memory'`). The
  documents MAP (L1) generalises to a **matter index** that routes across all three. This is additive to
  the prior plan, not a new architecture.

- **What already exists in the fork (queryable today).** The **legacy chat path** already has
  **FTS over message content** — `messages.content_tsv` (a `GENERATED ALWAYS` tsvector, migration
  `0016_chat_search_fts.py:48-53`) exposed via `GET /api/v1/chats/search`, which FTS-ranks **chats +
  messages** owner-scoped (`api/app/api/chats.py:475-570`). So "search my past chats" *lexically*
  already ships — but it is **owner-scoped, not matter-scoped**, **FTS-only** (no dense recall), and on
  the **legacy** substrate, not the agent path the matter agent runs on.

- **What exists but is NOT searchable.** The **agent path** (where matters actually run) persists
  conversation in two places, **neither indexed for retrieval**: (1) `AgentRunStep` rows — the settled
  step log (model turns / tool calls / results), bounded ~2000-char summaries
  (`api/app/models/agent_run.py:183-238`); (2) the **langgraph checkpointer** — the full message
  lineage per thread, in **library-owned, alembic-opaque** tables keyed by `thread_id`
  (`api/app/agents/checkpointer.py:1-25,57-104`). There is **no FTS, no embedding, and no
  cross-thread search** over agent conversation anywhere.

- **What is absent.** A **matter-scoped conversation search** ("across this deal's past threads, where
  did we discuss the audit-rights notice period?"); a **conversation→chunk→embed** path; any
  **dense/semantic** recall over conversation; and any tool that lets the agent search prior
  conversations the way it searches documents (`search_documents`). The agent's only cross-thread recall
  today is the **distilled** matter wiki + fact ledger (injected read-only) — never the raw transcript.

- **Multi-turn within a chat: works on the agent path, missing on the legacy path.** The agent path is
  genuinely multi-turn — the langgraph checkpointer replays the full thread lineage and deepagents
  compacts at ~0.85× (the §1 blocker #3 is a **legacy-chat** problem, not an agent-path one). The
  **legacy chat path is still single-turn** (`api/app/api/chats.py:1370-1374`: *"C3 still sends a
  single-turn request … a future task may widen this to include prior history"*) — and **upstream has
  since fixed exactly this on their fork** (§6), which is the headline awareness item.

- **Upstream-awareness headline (FROZEN — awareness only).** Upstream's 76 post-baseline commits are a
  **legal-research (CourtListener) + MCP + chat-tool-loop** milestone (ADRs 0014/0015; migrations
  0048-0057) — plus **#151 "Replay prior chat turns to the model (multi-turn memory)"**, a simple
  **window-replay** of prior turns (token-budget + message-count cap;
  `_load_history_messages`/`_select_history_within_budget`). Upstream has **NOT** pivoted to deepagents
  (still `langgraph>=0.2.76,<0.3`) and has **NO conversation embeddings / vector-over-chat /
  cross-thread conversation retrieval** — so on *this* doc's core need (conversations as a retrievable
  corpus) **upstream solved nothing we're about to build**. Their multi-turn fix targets the *legacy*
  chat path we are migrating away from. **No sync recommended; one item (§8) is a candidate for a
  per-case request if the maintainer wants the legacy path patched in the interim.**

- **Raw transcript vs distilled memory — keep BOTH, with a clear split.** Distilled memory (wiki +
  fact ledger) is the **answer to "what is true now"** — consolidated, deduped, human-correctable,
  cheap to inject. The raw transcript is the **answer to "what was actually said / why / by whom /
  when"** — the audit trail, the superseded reasoning, the exact wording. Web consensus is firm:
  **summary-only memory is lossy and hallucination-prone**; the production pattern (MemGPT and
  successors) is **window + running summary + a conversation-search tool over persisted recall**. So:
  distill for injection, **retrieve raw on demand**; never delete the transcript; let the distilled tier
  win on "current truth" and the raw tier answer "what was said."

- **Recommended approach + decomposition.** Make conversations a source type in the existing local
  hybrid stack — **reusing** the shipped retriever, the embed worker, the local-embedding plan (prior
  Slice C), and the auto-write-then-correct distillation — and add **net-new** only: a
  conversation→chunk→embed path, a source-typed matter-scoped index, a `search_matter_conversations`
  agent tool, and **recency weighting**. Within a chat, keep deepagents' native window+compaction and
  add **retrieval over the thread's older turns** when a chat runs long. **Cheap win first:** a
  matter-scoped, FTS-first `search_matter_conversations` tool over indexed turns (degrades to FTS
  exactly like the documents wiring). **Then:** fold conversation embeddings into the same local
  backfill as documents. **ADR-F049** (next number) covers conversations-as-a-retrievable-source as a
  sibling decision to the documents/local-embedding ADR.

---

## 2. What exists in our fork today (conversation/chat substrate)

There are **two distinct conversation substrates**, and they must not be conflated — the legacy chat
path and the agent path. The matter Deep Agent runs on the **agent path**.

### 2a. EXISTS and is QUERYABLE — legacy chat FTS (owner-scoped, not matter-scoped)

- **Storage.** `Chat` (owner-scoped conversation, optional `project_id`, soft-delete via `archived_at`)
  + `Message` (per-turn rows; `role ∈ {user,assistant,system,tool}`, `content`, routing metadata, cost,
  citations) — `api/app/models/chat.py:54-213`. A `POST /chats/{id}/messages` writes a `user` row and
  one `assistant` row (`chat.py:3-6`).
- **Queryable.** `messages.content_tsv` is a **`GENERATED ALWAYS AS (to_tsvector('english',
  coalesce(content,''))) STORED`** tsvector with a GIN index (migration
  `0016_chat_search_fts.py:48-54`), mirrored by `chats.title_tsv` (`:42-46`). `GET /api/v1/chats/search`
  runs `websearch_to_tsquery` over both, `ts_rank_cd`-ranks, returns `ts_headline` snippets, **owner-
  scoped**, archived excluded (`api/app/api/chats.py:475-570`). So **lexical search over past chat
  message content already ships** — the substrate the maintainer is asking about *partially exists*.
- **The catch.** It is **(a) owner-scoped, not matter-scoped** (no `project_id` filter in the search —
  it spans all the user's chats); **(b) FTS-only** (no dense/semantic recall — the exact recall gap the
  scale doc proved for documents applies identically to conversation paraphrase); **(c) on the legacy
  chat substrate**, which is **single-turn** (§2c) and **not** where matter Deep Agents run; **(d) not
  agent-callable** — it's a REST endpoint for the human UI, not a tool the agent can invoke mid-run.

### 2b. EXISTS but NOT searchable — the agent path (where matters run)

The matter Deep Agent persists conversation in two places, **neither indexed**:

- **`AgentThread` / `AgentRun` / `AgentRunStep`** (`api/app/models/agent_run.py`). `AgentThread` =
  one conversation (`title`, `project_id` = the Matter binding, `last_run_at`); its `id` doubles as the
  checkpointer `thread_id` (`:55-97`). `AgentRunStep` = one settled loop step (`kind ∈
  {model_turn,tool_call,tool_result}`, a **bounded ~2000-char `summary`** with secrets stripped) keyed
  `(run_id, seq)` (`:183-238`). These are the **glass-cockpit** activity records the UI polls
  (ADR-F002/F004) — **there is no tsvector, no embedding, and no search endpoint/tool over them.** The
  `summary` is a digest, not the verbatim turn, and is explicitly audit-shaped (counts/types/IDs).
- **The langgraph checkpointer** (`api/app/agents/checkpointer.py`). One process-global
  `AsyncPostgresSaver` holds the **full message lineage** (messages, todos, workspace files) per
  thread, in tables **owned by the library's `setup()`, deliberately NOT alembic-managed**
  (`:1-25,57-104`). This is the verbatim conversation — but it is **opaque application state addressed
  only by `thread_id`** (`thread_config`, `:121-123`); it is **not queryable by content**, not
  cross-thread searchable, and not a corpus we control the schema of. Reading another thread's
  checkpoint to search it is neither supported nor advisable (it's the agent's private working state).

**Net:** the place matters actually converse (the agent path) has **zero** content-search over
conversation — lexical or semantic, within-thread or cross-thread.

### 2c. Multi-turn behaviour within a chat — the single-turn blocker, status

- **Agent path: multi-turn WORKS.** A follow-up run on a thread is detected by querying prior
  `AgentRun` rows (`composition.py:327-333`); the run executes against the thread's checkpoint
  (`composition.py:422-423,585-586`), so the model sees the full prior lineage; a follow-up with **no**
  checkpoint is **honestly refused** rather than silently answering blind (`checkpointer.py:126-137`;
  `composition.py:423-433`). deepagents compacts the working window at ~0.85× of the
  `DEFAULT_MAX_INPUT_TOKENS = 200_000` budget. **So CLAUDE.md blocker #3 ("chat sends single-turn …
  the model never sees prior turns") is a *legacy-chat-path* statement and does NOT describe the agent
  path.**
- **Legacy chat path: STILL single-turn.** `api/app/api/chats.py:1370-1374` is explicit: *"C3 still
  sends a single-turn request (the user's content as one user message); a future task may widen this to
  include prior history."* The gateway request is built from the **current turn only** (`:1368`,
  `:1381-1395`). The blocker is **open on the legacy path** — and upstream has since closed it on their
  fork (§6).

### 2d. How matter memory already distills conversation (the distilled tier)

The agent path already turns conversation into durable matter knowledge — **auto-write-then-correct**,
the distilled tier of the unified corpus:

- **The matter wiki** — the agent's `update_matter_memory(content_md)` tool rewrites
  `projects.context_md` in place (snapshot-then-overwrite; reject-not-truncate; guarded R4/R5/R6),
  recording *"what you LEARN about the matter, each fact with its source … not your working notes or
  this turn's chat"* (`api/app/agents/matter_memory_tools.py:79-108,157-192`). It is **injected
  read-only into every future run** (`composition.py:358`).
- **The typed bi-temporal fact ledger** — `record_matter_fact` / supersede over `MatterMemoryEntry`
  (`fact_type ∈ {party,term,date,decision,open_point,fact}`, `valid_at`/`invalid_at`/`superseded_by` —
  never delete) (`api/app/models/project.py:246-368`), with an in-run gateway-routed consolidation pass
  (ADR-F043) and read tools (`search_matter_memory`, `matter_facts_as_of`, ADR-F044).
- **Human-pinned corrections** — authenticated, un-overwritable by the agent (B2), injected read-only
  (`load_pinned_corrections` / `format_corrections_block`, `matter_memory_tools.py:195-242`;
  `composition.py:359-361`).
- **The authorship roster** — who-is-who → side (ADR-F048), also distilled-from-conversation/documents
  and injected (`composition.py:380-384`).

**This is the key architectural fact for §4:** the fork **already** distills conversation into a
consolidated, human-correctable, injected tier. What it does **not** do is keep the **raw** conversation
retrievable — so when the distilled summary is too lossy (the exact wording, the superseded reasoning,
who said what when), there is no fallback. That gap is the new requirement.

---

## 3. The two new needs, defined

Both are **conversation** retrieval; they differ in **scope** and therefore in mechanism.

### 3a. "Search CONVERSATIONS within a matter" (across past threads)

*The need:* a matter is a long-running deal with **many threads** over weeks. The lawyer (or the agent)
asks *"across this deal's conversations, where did we agree the audit-rights notice would be 30 days?"*
or *"did we ever discuss the source-code escrow with opposing counsel?"* — and the answer lives in a
**prior thread**, not the current one, and not (or not faithfully) in the distilled wiki.

*Failure mode today:* **total.** The agent has no tool to search prior threads; its only cross-thread
recall is the distilled wiki/ledger, which is a **consolidated one-pager**, not the transcript — if the
detail was dropped during consolidation, or the lawyer wants the *exact wording* or *which thread*, it
is unrecoverable through the agent. The human can fall back to legacy `GET /chats/search` (§2a) **only**
if the conversation happened on the *legacy* chat path **and** they manually filter their own chats —
it is not matter-scoped and not on the agent substrate.

*How it differs from document retrieval:* conversations are **dialogic** (turns by different speakers,
including the agent itself), **temporally ordered and decay-prone** (a decision in turn 3 may be
reversed in turn 30 — recency matters far more than for a static contract), **self-referential** (the
agent's own answers are in the corpus — risk of the agent "remembering" its own past speculation as
fact), and **untrusted-mixed** (a turn may quote an injected document). Document chunks are static,
authored once, citation-anchored. **Same retriever, different weighting + provenance + trust handling.**

### 3b. Recall "within a chat" (one thread)

*The need:* a single thread runs long (a multi-hour negotiation session, dozens of turns). The lawyer
asks *"what did you say earlier about the indemnity carve-out?"* — referring to **turn 6 of the current
thread**, now outside the working window.

*Failure mode today:* **partial / latent.** On the agent path the checkpointer holds the full lineage,
but deepagents **compacts** at ~0.85× budget — so a *very* long thread's early turns get summarised away
and the verbatim early turn is no longer in context. There is no within-thread **retrieval** to pull a
specific earlier turn back; the agent relies on whatever the compaction summary kept. On the **legacy**
path it is worse — single-turn means *nothing* prior is seen at all (§2c).

*How it differs from 3a:* scope is **one thread**, the bar is **lower** (the data is already in the
checkpoint, just possibly compacted), and the right primitive is usually **better context management**
(window + running summary + targeted retrieval of older turns) rather than a full cross-corpus index.
3a needs an **index**; 3b needs **context engineering** plus optional within-thread retrieval.

---

## 4. Raw transcript vs distilled memory — the central design tension

We **already** auto-write distilled matter memory (wiki + fact ledger, §2d). The new requirement adds
the **raw transcript**. The design question: **when do we search raw vs distilled, and how do we avoid
duplication, staleness, and cross-matter leakage?**

### 4a. The web consensus (verified)

Multiple 2025-2026 sources converge: **summary-only memory is lossy** — *"inherently lossy … eventually
leads to large holes … sub-optimal performance due to information loss"* and *"long-context LLMs are
prone to … hallucinations"*
([On Memory Construction and Retrieval, arXiv 2502.05589](https://arxiv.org/pdf/2502.05589);
[Awesome-Memory-for-Agents](https://github.com/TsinghuaC3I/Awesome-Memory-for-Agents)). The production
answer is **hybrid**: MemGPT keeps the full conversation in **recall memory** and exposes a
**conversation-search tool** *"similar to how you might search your chat history in WhatsApp"*, replacing
evicted turns with a recursive summary rather than discarding them
([MemGPT, arXiv](https://readwise-assets.s3.amazonaws.com/media/wisereads/articles/memgpt-towards-llms-as-operati/MEMGPT.pdf);
[Mem0, arXiv 2504.19413](https://arxiv.org/pdf/2504.19413)). I.e. **distill for the hot path, keep raw
for retrieval, never delete.** This is precisely the split below.

### 4b. The split (recommended)

| | **Distilled memory** (wiki + fact ledger — exists) | **Raw transcript** (new, retrievable) |
|---|---|---|
| **Answers** | "What is **true now** about this matter?" | "What was **actually said** / why / by whom / when?" |
| **Form** | Consolidated one-pager + typed dated facts | Verbatim turns, indexed as chunks |
| **Access** | **Injected read-only** every run (hot, cheap) | **Retrieved on demand** via a search tool (cold) |
| **Authority** | **Wins on "current truth"** (human-correctable, bi-temporal supersede) | Wins on "what was said" (audit/forensic; never authoritative on current truth) |
| **Lifecycle** | Rewritten/superseded; consolidation prunes | **Append-only, never deleted** (audit trail) |
| **Trust** | Curated; pins immutable to agent (B2) | **Untrusted model input** (a turn may quote an injected doc) |

**Rule of thumb for the agent (prompt/skill):** *consult distilled memory first (it's already in
context); reach for raw conversation search only when you need the exact wording, the reasoning behind a
decision, who said something, or a detail the wiki doesn't carry — and treat retrieved turns as "what
was said," not as current truth (the wiki/corrections win on that).*

### 4c. Avoiding the three hazards

- **Duplication.** The distilled tier is **derived from** the raw tier — that's not duplication, it's a
  hot cache over a cold log (the MemGPT pattern). Guard against *double-counting* at retrieval: when a
  query is answered, **prefer the distilled fact** for "current truth" and cite the raw turn only as
  provenance ("agreed on 2026-05-02, thread #4"). Do **not** inject both the wiki *and* a pile of raw
  turns by default — raw is on-demand only, so the hot path stays the small distilled tier.
- **Staleness (a superseded decision).** This is the sharpest risk: raw turn 3 says *"liability cap =
  12 months"*; turn 30 supersedes it to *"24 months."* A naive transcript search returns turn 3 and the
  agent "remembers" the stale figure. **Two guards:** (1) **recency weighting** in the conversation
  retriever (newer turns rank higher — §5d), so the superseding turn surfaces; (2) the **distilled
  ledger is bi-temporal** — `matter_facts_as_of` already answers "what did we believe when," and the
  *current* value is the live fact, so the agent's authoritative answer comes from the ledger, with raw
  turns as colour. The transcript is **forensic**, not the source of current truth — that division is
  what makes staleness safe.
- **Cross-matter leakage.** Conversation chunks **must** be matter-scoped exactly as document chunks are
  — every retrieval re-asserts `(owner_id, project_id)` and 404-conflates cross-user access (the
  `_matter_files_query` / ADR-F035 posture, mirrored). A thread's `project_id` binding
  (`AgentThread.project_id`) is the scope key. **Never** build a cross-matter conversation index; the
  blast radius of an injected/poisoned turn stays inside its matter (the ADR-F042 confinement
  principle). This is also why the legacy **owner-scoped** `GET /chats/search` is the *wrong* primitive
  to hand the agent — it crosses matters.

### 4d. What this means concretely

Keep distillation exactly as shipped (it's the right hot path). Add the raw transcript as a
**separately-scoped, recency-weighted, on-demand retrieval source** that is **never authoritative on
current truth** and **never injected by default**. The distilled tier and the raw tier are
complementary layers of one memory system, not competitors.

---

## 5. Unified retrieval design — conversations as a first-class source

The thesis: **do not build a second search engine for conversations.** Make a conversation turn a
**chunk** in the **same local pgvector hybrid stack** the scale doc specified for documents —
**source-typed**, **matter-scoped**, **recency-weighted** — and let L1 routing and the agent's
select-then-read loop compose over all three source types.

### 5a. The message/turn → chunk → embed path (net-new, but small)

- **Source rows.** A conversation "turn" worth indexing is a **user turn** and the **agent's final
  answer** per run — the durable, meaningful content. The natural source is the **agent path**:
  `AgentRun.prompt` (the user turn) + `AgentRun.final_answer` (the agent's answer), both already
  persisted on `agent_runs` (`api/app/models/agent_run.py:151-152`), scoped to a matter via
  `AgentRun.project_id` / the thread. (Indexing intermediate `AgentRunStep` summaries is *optional* and
  lower-value — they're digests, not verbatim, and noisier; start with run prompt + final answer.)
- **Chunking.** Reuse the existing character-precise chunker (`chunker.py`) for long turns; most turns
  are short enough to be one chunk. Keep it model-free (no LLM chunking — same discipline as documents).
- **Embedding.** Reuse the **same local embedder + worker path** the document plan adds (prior Slice C):
  the embed worker that fires on ingest (`document_pipeline.py`) gets a sibling that fires when a run
  **completes** (`final_answer` settles), embedding the turn(s) with the **same local model, same
  dimension, $0** (no per-token cost, in-process compute — the gateway rule's Door A, ADR-F010
  governs *external-provider* calls, not a local model file).
- **Index.** A **source-typed** chunk store. Two shapes (decision in §7):
  - **(i) Reuse `document_chunks`** with a nullable `source_type` discriminator + a nullable
    `agent_run_id` FK — conversation turns become chunks with `source_type='conversation'`, `document_id`
    NULL, `agent_run_id` set. **Smallest schema delta; one retriever, one index, automatic fusion.**
  - **(ii) A dedicated `conversation_chunks` table** mirroring `document_chunks` (content, tsvector,
    `vector(N)`, matter scope, `agent_run_id`). Cleaner separation; the retriever `UNION`s the two.
  Either way the **citation invariant is relaxed for conversation** (a turn has no
  `normalized_content` byte-offset contract like a document — its "source" is the run/thread, not a
  page), so conversation chunks are **provenance-cited** ("thread #4, your answer on 2026-05-02"), not
  offset-verified by the Citation Engine.

### 5b. Composition with L1 (documents MAP → matter index) and L2 (hybrid retriever)

- **L1 generalises from "documents MAP" to "matter index."** The prior docs' MAP routes *which
  documents* are relevant; extended, the same router answers *which **sources*** (documents,
  conversations, memory) and *which threads* hold the answer. The map's one-line descriptions already
  double as a cheap dense router (scale doc §7a); conversation threads get the same treatment (a
  per-thread one-line "what this thread was about" — cheaply the `AgentThread.title` to start, a
  distilled summary later).
- **L2 is the shipped hybrid retriever, made matter-scoped and source-typed.** `hybrid_search`
  (`api/app/knowledge/retrieval.py:71-180`) already does pgvector cosine + FTS + min-max fusion + 4×
  overshoot. The scale doc's Slice A points the matter tools at a **matter-scoped** variant; this doc
  adds a **`source_types` filter** (documents-only / conversations-only / both) and a
  **recency-weighting** term for conversation candidates (§5d). The local cross-encoder rerank (prior
  Slice D) reranks the fused set regardless of source type. **One retriever, two source types, one
  rerank.**
- **The agent's loop is unchanged in shape.** Today: `search_documents` (FTS) + `read_document`. Add
  **`search_matter_conversations(query)`** → matter-scoped hybrid over `source_type='conversation'`,
  returning ranked turns with thread/run provenance — the conversational sibling of `search_documents`.
  The model picks the tool by intent ("where is the escrow clause" → documents; "what did we agree about
  escrow" → conversations; "tell me about this deal" → both / the map). This matches the agentic-search
  pattern the fork is already built on (and the [agentic-retrieval](https://ragflow.io/blog/rag-review-2025-from-rag-to-context)
  consensus).

### 5c. Within-a-chat context management (need 3b) — window vs running summary vs retrieval

Web consensus is explicit and maps onto what we already have
([CallSphere](https://callsphere.ai/blog/context-window-management-ai-agents-summarization-pruning-sliding-2026);
[AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/11/agent-context-engineering-sliding-windows-memory-2026)):
**sliding window** is trivial but loses long-term context; **running summary** retains high-level context
but risks "abstraction hazard"; **retrieval** fetches specific older facts but is weaker for dense
reasoning — so the **practical pattern is all three**: system prompt + immediately-relevant retrieved
context + the last few turns, with **30-50% headroom** for tool outputs.

- **We already have window + running summary for free:** deepagents' native compaction at ~0.85× **is**
  the window-plus-running-summary mechanism (it summarises evicted turns and keeps recent ones). **No
  build needed** for the common case.
- **The net-new for 3b is the retrieval leg, used sparingly:** when a thread grows long enough that
  compaction has evicted early turns, let the agent pull a *specific* earlier turn back via
  within-thread retrieval. **Reuse `search_matter_conversations` scoped to the current thread**
  (`thread_id` filter) — same tool, narrower scope. This is the cheapest possible win because it's the
  cross-thread tool with one extra predicate.
- **Recommendation:** rely on deepagents compaction for 3b first (it already works); add within-thread
  retrieval **only if** long-session recall failures are observed — don't pre-build a within-chat
  summariser (deepagents owns that), and don't pre-build within-thread retrieval before measuring need.

### 5d. Recency weighting (the conversation-specific term)

Documents are static; conversations decay. Temporal-aware retrieval is a recognised axis
([Chronos, arXiv 2603.16862](https://arxiv.org/pdf/2603.16862)). For conversation candidates, blend a
**recency score** into the fused score: `final = (1-β)·hybrid + β·recency`, where `recency` is a decay
(e.g. exponential by run `started_at` / `last_run_at`) so a superseding turn 30 outranks a superseded
turn 3 (the §4c staleness guard). Keep β a **tunable, conservative** weight (and **document-source
candidates get β=0** — no recency decay on static contracts). This is a few lines in the fusion step,
not a new subsystem.

### 5e. Cost and posture (local, near-zero, gateway-honest)

- **One-time:** embedding conversation turns is the **same $0 local compute** as document chunks (prior
  Slice C). A matter's conversation is far smaller than its document corpus (turns are short; a deal
  with 1000 docs might have a few hundred turns), so the marginal index cost is **negligible**.
- **Per-query:** local hybrid + rerank = **~$0, tens of ms** (scale doc §4c). Recency weighting is
  arithmetic — free.
- **Gateway rule:** conversation embedding uses the **same local door** as document embedding (Door A
  in-process, or Door B gateway-local) — no external egress, no key, no new provider. The R4 cost cap
  stays honest (local Postgres reads + local encode = zero third-party spend).
- **Auto-write-then-correct preserved:** the **distilled** tier remains the auto-write-then-correct
  surface (unchanged). The **raw** conversation index is a **derived, recomputable index column**
  (like document embeddings) — not authored content, so it needs **no** correction/supersede governance
  of its own; it inherits the transcript's append-only, never-deleted lifecycle. The lawyer corrects the
  *distilled* tier (which wins on current truth); the raw index is just a search aid over what was said.

### 5f. Reuse vs net-new (explicit)

| Component | Status |
|---|---|
| Hybrid retriever (pgvector + FTS + fusion + overshoot) | **Reuse** `api/app/knowledge/retrieval.py` (ADR 0008) |
| Local embedder + embed worker + dimension/ALTER | **Reuse** the document plan's local-embedding slice (prior Slice C, ADR-F049) |
| Character-precise chunker | **Reuse** `chunker.py` |
| Distillation (wiki + fact ledger + corrections + roster) | **Reuse** as-is (the distilled tier; ADR-F042/F043/F044/F048) |
| Within-chat window + running summary | **Reuse** deepagents native compaction |
| Legacy `messages.content_tsv` + `GET /chats/search` | **Do not reuse for the agent** (owner-scoped, FTS-only, wrong substrate) — keep for the legacy human UI only |
| `source_type` discriminator + `agent_run_id` on the chunk store | **Net-new** (small migration) |
| Conversation→chunk→embed path (fires on run completion) | **Net-new** (sibling of the doc embed trigger) |
| `search_matter_conversations` agent tool (matter- or thread-scoped) | **Net-new** (sibling of `search_documents`) |
| Recency-weighting term in fusion | **Net-new** (a few lines) |

---

## 6. Upstream awareness (LegalQuants/lq-ai, ADR-F001 FROZEN — awareness only)

**Method:** the `upstream` remote is configured and reachable; I fetched `upstream/main` (`4de10ec`,
"docs: session handoff 2026-06-26 — Phase 2 underway, WS-G validity layer") and diffed against our
baseline `f91149a` — **76 commits**. This is a **code-grounded** awareness review, **not** a merge
proposal. **Governance: nothing below is recommended for sync; any sync requires the maintainer's
explicit per-case approval (ADR-F001).**

### 6a. What upstream added since v0.4.0 (the relevant slices)

The post-baseline surge is one milestone: **legal-research (CourtListener) + MCP + a governed chat
tool-loop**, plus a multi-turn fix. New migrations **0048-0057**; new ADRs **0014/0015**.

| Upstream item (SHA / PR) | What it is | Relevance to us | Did it solve (differently) something we're about to build? |
|---|---|---|---|
| **#151 `4ff41221` — "Replay prior chat turns to the model (multi-turn memory)"** | **Window-replay** of prior turns on the **legacy chat path**: `_load_history_messages` + `_select_history_within_budget` (most-recent-first, trimmed to a token budget **and** a message-count cap; both knobs in `config.py`, default-on; `0` reverts to single-turn). No embedding, no summary — pure recent-window. | **Directly relevant to our open *legacy-path* single-turn blocker** (§2c) — and to need 3b's "window" leg conceptually. | **Partly, and only for the legacy path.** It is the *window* strategy for *legacy chat* — the substrate we are migrating away from. Our **agent path** already does multi-turn via the checkpointer (better than replay). It does **nothing** for cross-thread or semantic conversation retrieval (need 3a). |
| **#181 `36223de7` — tool-governance substrate** (`tool_call_log`, `governed_tool_invocation`, `retrieve_caselaw`/`call_mcp_tool`); **#187 `97ccbc08` — governed chat tool-loop** (tools passthrough + Anthropic `tool_use`, migration 0054); **#189 `47d9bed0` — in-chat confirmation gate** | Upstream bolts a **tool-calling loop onto the legacy chat path** with a persist-and-resume human confirmation gate, and forwards `tools` through the gateway's Anthropic adapter. | Relevant as **awareness of how upstream closed CLAUDE.md blocker #2** (gateway Anthropic adapter was text-only). We solved tool-calling **differently and more deeply** via the deepagents pivot (model-driven loop, `guarded_tool_call`). | **No overlap with conversation retrieval.** It's a different answer to a blocker we already passed; it does not index or search conversations. |
| **#159-#161, #191/#192 `c7e9318e`/`dac1f3fc`/`13a5f9ed`/`658fdbce` — CourtListener research subsystem + case-law-research skill + external-source citation provenance** (migrations 0049 `research_metadata`, 0057 `message_caselaw_citations`) | An **external legal-research** capability (case-law retrieval) with provenance/citation rows for externally-retrieved sources. | Tangentially relevant: it's **retrieval**, but of **external case law**, not of the matter's own documents/conversations. Their "retrieval provenance" idea (record where a retrieved snippet came from) echoes our citation/provenance posture. | **No.** It's a different corpus (public case law) and a different need; it does not touch conversation-as-memory or our local hybrid plan. |
| **#158 `49326faa` — gateway tool-provider egress boundary** (ADRs 0014/0015); **#220 `e9c399d0` — generic-MCP retrieval-provenance**; **#207/#211 sticky-skills** | MCP client brokered through the gateway as the egress boundary; generic provenance for MCP-retrieved content; an opt-in sticky-skills toggle. | **Awareness for our deferred MCP milestone** (MEMORY: MCP is its own approval-gated milestone — sanction upstream's gateway-brokered MCP client, ADRs 0014/0015). The egress-boundary discipline matches ours (ADR-F010). | **No** — unrelated to conversation retrieval. Logged here only because it's the sanctioned reference for the *future* MCP slice (per-case approval still required). |

### 6b. What upstream did NOT do (the load-bearing negatives, verified)

- **No conversation embeddings / vector-over-chat.** `messages` upstream has **no embedding column**;
  the only message index is the **same `content_tsv` FTS we already have** (migration 0016, pre-baseline
  — it's ours too). Verified: no vector/dense path over chat anywhere upstream.
- **No cross-thread / matter-scoped conversation retrieval.** Their multi-turn is **within one chat**
  (window replay); there is **no** "search past conversations in a matter." Need 3a is **unsolved
  upstream**.
- **No deepagents / langgraph 1.x pivot.** Upstream is still `langgraph>=0.2.76,<0.3` (legacy
  executors). Our agent path — the substrate this whole doc builds on — **does not exist upstream**; their
  conversation work is all on the legacy chat path we are leaving behind.
- **No local-embedding cost play.** Upstream's embeddings remain the cloud path; they did not add the
  local in-process embedder the scale doc recommends.

### 6c. Awareness verdict

On **this doc's core need — conversations as a retrievable corpus, matter-scoped, semantic — upstream
solved nothing we are about to build.** The one genuinely adjacent item is **#151 multi-turn window
replay**, and it targets the **legacy chat path** (which our agent path already surpasses via the
checkpointer). The MCP/research items are awareness for a **separate, already-approval-gated** milestone.
**No sync is recommended.** The single *candidate* for a per-case request is in §8 (Q7): *if* the
maintainer wants the legacy chat path made multi-turn in the interim (before it's fully retired),
#151's `_load_history_messages` window-replay is the small, self-contained reference — but it is
**awareness only** until the maintainer approves per-case, and the strategic answer is to retire the
legacy path, not patch it.

---

## 7. Revised decomposition — folding conversation retrieval into the prior plan

The prior docs' slice plan (Slice A wire hybrid → B coverage signal → **C local embeddings [ADR-F049]**
→ D rerank → E enrichment → F typed documents MAP) is the spine. Conversation retrieval slots in as
**siblings that reuse C's embedder and A's retriever**. **Next fork ADR number is F049**; next migration
is **0078** (per the scale doc). Separated into cheap-wins, scale-foundation, later.

### Cheap wins (no new dependency; ship early)

- **Slice A (carried forward, unchanged) — wire the matter document tools to the EXISTING hybrid
  retriever.** Point `_search` (`api/app/agents/tools.py`) at a matter-scoped `hybrid_search`; degrades
  to FTS until vectors exist. Pure upside. *(Prerequisite framing for the conversation tool, which
  mirrors it.)*

- **Slice G (net-new, cheap) — `search_matter_conversations` over INDEXED conversation, FTS-first.**
  Add the agent tool (sibling of `search_documents`), matter-scoped (`AgentThread.project_id`), with a
  `thread_id` filter option for within-chat recall (need 3b). **First cut indexes conversation as
  FTS-only** (a `content_tsv` over run prompt + final answer — mirrors `document_chunks` / the legacy
  `messages.content_tsv`), so it ships **before** the embedding work and **degrades exactly like the
  document wiring** (FTS now, dense when Slice C lands). **Net-new:** the `source_type` discriminator +
  `agent_run_id` on the chunk store (small migration, can ride 0078) + the conversation→chunk path
  firing on run completion + the tool. **Needs the ADR-F049 conversation decision** (raw-transcript
  retrieval as a matter-scoped, never-authoritative source; the raw-vs-distilled split §4). *This is the
  highest-leverage cheap win for need 3a.*

### Scale-foundation (the cost play — shared with documents)

- **Slice C (carried forward, EXTENDED) — LOCAL embedding source + column dimension [ADR-F049, mig
  0078].** Implement local embeddings (Door A in-process FastEmbed/ONNX, or Door B gateway-local Ollama
  stub), repoint the `embedding` alias, ALTER the chunk `vector` column to the local dim (768 rec.).
  **Extension for conversations:** the same backfill embeds `source_type='conversation'` chunks — **one
  local model, one dimension, one worker path** covers documents *and* conversations. **No extra ADR**
  for the conversation embeddings — Slice C's ADR-F049 already sanctions local compute as a non-egress
  inference locus; conversations are just another source feeding it.

- **Slice H (net-new, depends on C+G) — conversation dense retrieval + recency weighting.** Once
  conversation chunks have vectors, make `search_matter_conversations` **hybrid** (it was FTS-only in G)
  and add the **recency-weighting** term to the fusion (`β` blend; documents get β=0) (§5d). Turns the
  lexical-recall gap (the same one the scale doc proved for documents) into semantic recall for
  conversation, with staleness handled by recency + the bi-temporal ledger. **ADR addendum** (recency
  weighting + conversation-as-hybrid-source) folded into F049.

### Later (only if measured)

- **Slice D (carried forward) — local cross-encoder rerank** over the fused set — reranks
  document **and** conversation candidates uniformly. After C/G/H, once precision (not recall) is the
  residual.

- **Slice I (net-new, optional) — distilled per-thread summaries as L1 router signal + within-chat
  retrieval.** A small local summary per thread ("what this thread was about") improves L1 routing
  across many threads, and within-chat retrieval (need 3b) is enabled by G's `thread_id` filter — but
  **only build the within-chat leg if deepagents compaction proves insufficient** on long sessions
  (don't pre-empt deepagents' native window+summary). Reuses Slice E's local enrichment pass.

- **Slice F (carried forward) — typed documents MAP (`fact_type="document"`)** + the L1 matter index
  that routes across sources (§5b). Synergistic with G/H (its descriptions become router signal).

**Triggers/thresholds.** Ship **A + G(FTS)** now (pure upside, no dep). Land **C** (local embeddings)
when any matter hits the scale where FTS recall bites (the 1000-doc scenario is past it; a multi-thread
deal hits the conversation recall gap sooner because turns paraphrase heavily). **H** rides C. **D/I**
gate on *measured* precision/long-session complaints. **Dependency order:** A → G(FTS) → **C
[ADR-F049]** → H → D; F/I parallel; within-chat retrieval (3b) only on measured need.

**What's net-new vs reused (summary).** Net-new = the `source_type`/`agent_run_id` chunk-store delta,
the conversation→chunk→embed trigger, the `search_matter_conversations` tool, recency weighting, and
(optional) per-thread summaries + within-chat retrieval. **Everything else is reused** — the retriever,
the local embedder/worker, the chunker, the distillation tiers, deepagents compaction. The marginal
build for "conversations as a first-class source" is **small** precisely because the document plan
already builds the hard parts.

---

## 8. Open questions for the maintainer

1. **Raw-transcript search now, or rely on distilled memory for the near term?** §4 recommends keeping
   **both** (distill for the hot path, retrieve raw on demand — the verified MemGPT pattern) and shipping
   the cheap FTS-first `search_matter_conversations` (Slice G) early. The alternative is to lean on the
   distilled wiki/ledger alone for now and defer raw retrieval. **Do you want raw conversation search as
   a near-term slice, or is the distilled tier sufficient until a real recall failure is observed?**

2. **Per-matter conversation store — reuse `document_chunks` (source-typed) or a dedicated
   `conversation_chunks` table?** §5a (i) vs (ii). Reusing `document_chunks` with a `source_type` +
   `agent_run_id` is the **smallest delta and one retriever**; a dedicated table is **cleaner
   separation** at the cost of a `UNION` in the retriever. Recommendation: **reuse with a discriminator**
   (relax the citation-offset invariant for conversation rows). **Which do you prefer?**

3. **Recency weighting — accept the `β` recency-blend for conversation candidates (documents β=0)?**
   §5d. It's a few lines and it's the main guard against surfacing a *superseded* decision. **OK to add a
   conservative recency decay to conversation retrieval, and what default β feels right (start ~0.2)?**

4. **Within-chat (need 3b): lean on deepagents compaction, or build within-thread retrieval?** §5c —
   web consensus is window+summary+retrieval, and deepagents **already** gives window+summary.
   Recommendation: **rely on compaction first; add within-thread retrieval (G with a `thread_id` filter)
   only if long-session recall failures appear.** **Accept "measure before building the within-chat
   retrieval leg," or fund it up front?**

5. **What to index from the agent path — run prompt + final answer only, or also `AgentRunStep`
   summaries?** §5a recommends **prompt + final answer** (verbatim, meaningful) and treating step
   summaries (digests, noisier) as optional/later. **Index just the turns, or also the tool-step
   summaries?**

6. **Local-embedding door for conversations — same as documents (Door A in-process / Door B
   gateway-local)?** Conversations should use **whatever Slice C picks** (one model, one path). This is
   really the document doc's Q1 — flagged here only to confirm conversations don't change the answer.
   **Confirm conversations ride the document embedder's door, no separate decision?**

7. **Upstream per-case sync — patch the legacy chat path's single-turn blocker with #151's window
   replay, or retire the legacy path?** §6c. The legacy chat path is **still single-turn**
   (`chats.py:1370`); upstream #151 is a small, self-contained window-replay fix. **Strategically** the
   answer is to retire the legacy path in favour of the agent path (already multi-turn) — but **if** you
   want the legacy path usable in the interim, #151 is the awareness reference. **Per ADR-F001 this needs
   your explicit per-case approval before any code is taken — do you want a per-case sync request raised,
   or do we let the legacy path stay single-turn until retirement?** (Nothing has been taken; this is the
   only item in the whole review that is even a *candidate* for sync.)

8. **Read cap / injection budget when conversation is a source.** Retrieved conversation turns compete
   for the same context budget as documents and the injected distilled tier. **Should retrieved
   conversation be on-demand-only (recommended — never injected by default, §4d), or do you want a small
   "recent conversation" block injected at run start the way the wiki is?** (Recommendation: on-demand
   only, to keep the hot path the small distilled tier and avoid re-surfacing stale turns.)

---

### Honest limits of this dossier

- **Two substrates, and the matter agent is on the newer one.** The *queryable* conversation FTS that
  ships today (`messages.content_tsv` / `GET /chats/search`) is on the **legacy** chat path; the
  **agent** path where matters run has **no** conversation search at all. The "we already have
  conversation search" claim is true only for the legacy path and is owner-scoped — easy to overstate, so
  it's separated carefully in §2.
- **The checkpointer is opaque on purpose.** The full verbatim agent conversation lives in
  library-owned tables we don't schema-control (`checkpointer.py:1-25`). The recommendation indexes a
  *projection* (run prompt + final answer from `agent_runs`, which we **do** own), not the checkpointer
  internals — reading another thread's checkpoint to search it is neither supported nor advisable.
- **No measured conversation-recall need on our own data.** The need is reasoned from the substrate's
  shape (no search over agent conversation) + the verified web consensus (summary-only is lossy), not
  from incident data or a labelled conversation-retrieval eval. Slice G/H should ship with a small recall
  spot-check (a handful of "what did we discuss" questions with known-relevant threads), mirroring the
  scale doc's recommended recall eval for documents.
- **Recency weighting is a heuristic.** The `β` recency blend (§5d) is a defensible guard against stale
  turns, not a tuned constant — calibrate it (and the bi-temporal-ledger interaction) against real
  matters; treat the ~0.2 default as a starting point.
- **Upstream awareness is a point-in-time diff** (`upstream/main` `4de10ec`, 76 commits since
  `f91149a`, fetched 2026-06-27). Upstream keeps moving; the negatives (no conversation embeddings, no
  deepagents pivot) are verified as of this SHA. Per ADR-F001 this is awareness only — re-diff before any
  future per-case sync conversation.
