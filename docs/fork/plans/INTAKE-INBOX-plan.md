# INTAKE — agent-monitored legal-intake inbox (email front door → candidate matters → HITL)

Status: ACCEPTED 2026-08-16 — maintainer phone review resolved all 6 decisions (see
§ Maintainer decisions; rulings 1 and 5 reshaped the design in place). No start blocker:
INTAKE-0/1 need nothing external; the AgentMail key + dedicated inbox address are needed
from INTAKE-2 (the only slice that touches AgentMail). Task #536.
Research pack (read on demand): `docs/fork/plans/research/INTAKE-{agent-inbox-langgraph,agentmail,substrate-map,taxonomy-policy,inbox-ui-alternatives}.md` (5 Sonnet research reports, 2026-08-16 — the last one is the round-2 alternatives/de-investment/production-practice survey grounding Ruling 2).

## What we're building (one paragraph)

A practice-area Deep Agent ambiently monitors the company's legal-intake mailbox. **Every
inbound email thread is one deep-agent run** — separate inference, separate context — on the
bound area agent, which reads the thread and its ingested attachments and concludes one of
three ways: *dealt with* (nothing needed — filed with a note), *paused for the lawyer*
(drafted advice / redline / reply, waiting for approve / edit / reject / respond in an
inbox-style HITL surface in the cockpit), or *kept as a candidate matter* (a real project
carrying the thread's documents and the agent's work). Nothing ever leaves the system without
a human approval. Test rig: AgentMail. Production email (M365/Gmail) swaps in behind the same
bridge seam later.

## Ruling 1 — who monitors: the bound area agent, one run per thread (MAINTAINER-RULED 2026-08-16)

The inbox is bound by the admin to ONE practice-area agent (v1: Commercial). There is no
neutral "intake monitor" agent — a neutral agent would have no Practice Playbook, no skills,
no tools, and would have to hand off to the area agent anyway.

**No deterministic pre-classifier.** The originally-drafted two-stage design (cheap
schema-constrained triage call → policy-gated agent run) was REJECTED by the maintainer:
legal inboxes are messy places; a deterministic classifier plus a fixed category policy is
structured intake by the back door — and if you have structured intake you don't need an
agent. Ruled design:

- **Every inbound email thread = one deep-agent run** (separate inference, separate context
  call) on the bound area agent, composed normally (Practice Playbook, skills, tools, HITL
  policy, tier floor), with the thread envelope + ingested attachments in front of it.
- The run ends in exactly one of three outcomes, recorded STRUCTURALLY (a
  `record_intake_outcome` tool call with a closed outcome field — never free prose):
  **(a) dealt with** — nothing needed (spam, FYI, pure notification): the agent files the
  thread with a short note; nothing external happens; the eagerly-created project is
  auto-dismissed so no clutter survives. **(b) paused for HITL** — the agent prepared
  something (reply draft, advice, redline) and the run settles `awaiting_input` for the owner
  to approve / edit / reject / respond. **(c) candidate matter** — substantive work: the
  project stays as a candidate matter carrying documents, memory and the agent's work product
  (in practice (c) also lands in (b) the moment anything would leave the system).
- Plumbing note: the project row is still created eagerly at ingest (runs and files are
  project-scoped — that's substrate, not policy); the agent's OUTCOME decides whether it
  survives as a candidate or is dismissed on the spot.
- **Cost control moves from "don't run the agent" to "run it briefly":** intake runs get a
  lean budget profile + low step cap; a spam conclusion is one short turn. The maintainer
  explicitly accepts per-thread inference cost in exchange for judgment.
- Follow-up emails on a known thread continue the SAME agent thread (conversation memory
  carries); each new inbound message triggers a new run on it.

Cross-area mail: doctrine (not config) says out-of-area threads end as (b) with a proposed
handoff note — routing stays human. A second area later = another `intake_mailboxes` row. A
shared multi-area front-door inbox with an automatic router stays out of scope (backlog;
would supersede this section of ADR-F086 if ever built).

## Ruling 2 — Agent Inbox: adopt the concept and the decision vocabulary, not the app

(Refined 2026-08-16 by round-2 research: `research/INTAKE-inbox-ui-alternatives.md` —
alternatives survey + production-practice survey + de-investment evidence timeline.)

**Build the inbox surface natively in the Svelte cockpit on the F071 plumbing**, widened with
the two decision types we haven't enabled yet (`edit`, `respond` — middleware-native, we
currently compile only `approve`/`reject`). No LangGraph Server, no API shim, no React app.
Grounds:

- **The OSS `agent-inbox` app is de-invested and can't round-trip our schema.** Last real
  feature work Jan 2026; auth question for production use unanswered 10+ months; its one
  merged bridge to the current middleware schema (PR #91) is inbound-only AND partial (reads
  `action_requests[0]` only; the resume path still posts the legacy `HumanResponse[]`
  vocabulary — accept≠approve, no `respond`). The reason it stalled: **LangChain moved the
  inbox concept into paid LangSmith Fleet** (2026-03-19 launch ships a commercial feature
  literally named "Agent Inbox" — review/approve/reject centrally — with no reference to the
  OSS repo), while HITL investment moved into `langchain` core middleware. Closed-source SaaS
  in the approval path is a non-starter for a self-host-first legal product.
- **Every credible alternative was surveyed and none beats native.** agent-chat-ui is the
  only project speaking our exact schema, but is React-only, app-not-library, requires the
  LangGraph Platform API we deliberately don't run, lacks `respond`, and has open bugs on
  deepagents interrupts — useful strictly as a logic reference. AG-UI is a real
  framework-agnostic protocol but buys cross-framework interop we don't need at the cost of
  a schema-translation layer. HumanLayer's approvals SDK is dead (pivoted to CodeLayer);
  Portia is defunct; gotoHuman/Permit.io put a third-party cloud in the approval path
  (data-residency fail); Inngest has no UI and duplicates our checkpointer. Nothing
  Svelte-native exists. Full survey + shortlist in the research file.
- **Production practice says approval surfaces are built, not bought.** No observability
  product (LangSmith, Langfuse, …) ships a pre-execution approval inbox — annotation queues
  are post-hoc labeling; surveys (LangChain n=1,340; Zapier n=500+) put approval-gated
  write/delete actions at ~38–50%, overwhelmingly implemented as custom code in the product's
  own UI or Slack buttons.
- What we DO take from the ecosystem: the middleware's decision vocabulary we already run;
  a component taxonomy as design reference (assistant-ui's Approval Card / Permission Grant /
  Reviewable Diff; agent-chat-ui's decision-type-driven rendering — patterns, not code); and
  agent-chat-ui's `use-interrupted-actions.tsx` as a porting reference for decision-building
  logic in INTAKE-4/5.
- This is also the vendor's own free-tier recommendation: LangChain's current frontend HITL
  docs teach building your own approval card (with **Svelte** among the worked examples,
  covering all four decisions incl. `respond`) and name no inbox app.

## Architecture

```
AgentMail cloud                      dev: outbound websocket (no tunnel needed)
   │  message.received(+.spam/.blocked/.unauthenticated)   prod: Svix-signed webhook
   ▼
mail-bridge (NEW microservice — the ONLY holder of mailbox credentials, ADR-F086)
   │  normalizes → InboundEmail envelope {mailbox, thread, message, headers, auth_results,
   │  attachments[b64]}; also exposes POST /send for approved outbound replies
   ▼  bearer LQ_AI_BRIDGE_TOKEN (require_bridge_auth — slack/teams-bridge precedent)
api  POST /internal/intake/emails  → idempotency check → intake_threads upsert
   │                                → candidate project (projects.intake_state='candidate')
   │                                → ingest_bytes() per attachment → arq intake_email_job
   ▼
ONE deep-agent run PER EMAIL THREAD — the bound area agent (normal agent_run via
   │   enqueue_agent_run_job; prompt = intake doctrine + fenced envelope; attachments
   │   already ingested; draft_email_reply + every outbound tool ALWAYS interrupt-gated)
   │   run concludes with a structural outcome (record_intake_outcome tool):
   │     (a) dealt with     → thread filed with a note; candidate project auto-dismissed
   │     (b) awaiting human → run settles awaiting_input → Intake view
   │     (c) candidate matter → project + work product stay (usually also lands in (b))
   ▼
HITL     run settles awaiting_input → Intake view in cockpit → approve/edit/reject/respond
   │        (POST /agents/runs/{id}/resume, widened decisions — ADR-F087)
   ▼
approve on draft_email_reply → api → mail-bridge /send → AgentMail reply lands in thread
```

Unchanged and load-bearing: gateway as sole LLM egress; `guarded_tool_call` + R4/R5/R6 brakes
on every agent action; audit counts/types/IDs only (no email bodies in audit rows); citation
engine; ADR-F042 matter-memory semantics on the candidate matter.

## Data model (one migration, INTAKE-1)

- `projects.intake_state` — nullable enum `candidate | promoted | dismissed`; NULL = normal
  matter. Candidate matters are REAL projects (ingest, memory tiers, HITL, cockpit panels all
  reuse); the default matter list filters `intake_state='candidate'` out until promoted.
  Dismiss = `intake_state='dismissed'` + existing soft archive. NOT sandboxes (sandboxes are
  CHECK-forbidden a practice_area_id; candidates need one).
- `intake_mailboxes` — the binding, admin-owned: `id, provider('agentmail'), inbox_id,
  address, practice_area_id FK, owner_user_id FK` (the **queue owner** — owns every candidate
  matter and run, approves in v1), `default_budget_profile, max_steps, active, created_at,
  updated_at, deleted_at`. No policy JSONB, no triage model — doctrine lives in the intake
  skill (Ruling 1/5).
- `intake_threads` — the inbox backbone: `id, mailbox_id FK, provider_thread_id (UNIQUE with
  mailbox), project_id FK nullable, agent_thread_id FK nullable, subject, label` (free-text
  agent-chosen tag — display/grouping only, nothing branches on it), `outcome_note,
  status(received|processing|awaiting_human|replied|handled|error), last_message_id,
  last_inbound_at, auth_state(pass|fail|unknown), message_count, created_at, updated_at`.
- `intake_messages` — idempotency + provenance: `id, thread_id FK, provider_message_id
  (UNIQUE with mailbox), direction(in|out), run_id FK nullable, created_at`. Duplicate webhook
  delivery / websocket replay = no-op on the unique key.

## Doctrine, not policy config (MAINTAINER-RULED 2026-08-16)

The originally-drafted fixed 12-category taxonomy + per-category action-ladder config was
REJECTED as the driver — maintainer estimate: a fixed list fits maybe 30% of one org, and
orgs differ. Ruled replacement:

- **An intake SKILL (doctrine)** bound to the area — transparent and admin-editable like
  every skill — tells the agent how to read an intake thread, the three outcomes, what must
  always stop for HITL (anything outbound; any legal judgment reaching a requester),
  sender-authenticity caution (auth_state), and the misdirected/privileged-mail rule
  (classify only; never summarize into memory). The research taxonomy
  (`research/INTAKE-taxonomy-policy.md`) survives as ILLUSTRATIVE EXAMPLES inside the
  doctrine — never as enforced config.
- **Free-form labels, not an enum**: the agent tags each thread with a short label of its own
  choosing ("NDA review", "renewal notice"…) → `intake_threads.label`. Labels are for display
  and grouping; no code branches on them.
- **Categories EMERGE from use** (post-v1 slice): after a period of operation, a
  consolidation pass reads the accumulated labels + outcomes and PROPOSES an org-specific
  taxonomy and doctrine amendments to the admin; approve → it becomes part of the intake
  doctrine. "System proposes, user owns" — same shape as the Practice Knowledge prize (F050).
- **The safety line is structural, not policy**: `draft_email_reply` (the ONE new tool:
  to/subject/body/attachment refs; approval triggers the bridge send) and every other
  outbound tool is interrupt-gated in `hitl_policy` unconditionally. No category mechanism
  exists, so nothing can unlock auto-send. Everything else maps onto EXISTING substrate:
  document summaries (F082), Matter Facts, the agent's normal skills + redline tools (already
  HITL-gated).
- v1 acknowledgements: **approval-required only** — NO auto-send path anywhere in v1 (kills
  the mail-loop class outright; auto-ack with loop guards is backlog).

## Security posture (folded into every slice's review)

1. **Email is untrusted model input.** Envelope content is fenced as data in prompts; the
   run's conclusion is a schema-constrained tool call (`record_intake_outcome`), never free
   prose; the injection BACKSTOP is structural — every outbound/state-changing tool is
   interrupt-gated no matter what the email says (per F071 mechanics, not prompt language).
2. **Sender authenticity**: subscribe to `message.received.unauthenticated/.spam/.blocked`
   too; `auth_state` lands on the thread and caps the ladder at summarize + banners the UI.
3. **Loops**: bridge drops `message.sent` events; inbound `Auto-Submitted`/`Precedence: bulk`
   headers force `spam_marketing`; v1 sends nothing without a human.
4. **Credentials**: AgentMail key + webhook secret live ONLY in mail-bridge env (gateway-
   pattern); api holds only `LQ_AI_BRIDGE_TOKEN`-class shared secrets.
5. **Misdirected/privileged mail**: doctrine caps this class of mail at classify-only; no
   memory writes, no summaries.
6. **Authz**: internal intake router mounted without the user gate but behind
   `require_bridge_auth`; everything user-facing owner-scoped, cross-user 404.
7. **Budget**: every intake run gets the binding's lean budget profile (default: cheapest
   existing profile) + a low `max_steps` cap — cost control is "run briefly", not "don't
   run" (Ruling 1).

## Slices (one PR each, full ADR-F005 gate each)

- **INTAKE-0 — ADR + re-sequence (≤half day, NO external dependency).** Draft ADR-F086
  (email intake architecture: the two rulings above, bridge-held credentials,
  candidate-matters-as-projects, one-run-per-thread with structural outcome; verify
  F086/F087 numbering free) + MILESTONES.md re-sequence (INTAKE next, CUSTODIAN behind).
  AgentMail deliberately NOT involved — only the bridge (INTAKE-2) ever touches it;
  everything else runs on our provider-agnostic envelope.
- **INTAKE-1 — substrate (2–3 days).** Migration (4 schema items above). Extract
  `ingest_bytes()` service from `upload_file` (refactor + tests; HTTP route now calls it).
  `POST /internal/intake/emails` (bridge-auth): idempotent envelope landing → thread upsert →
  project (eager, per Ruling 1) → attachment ingest → enqueue `intake_email_job` (arq,
  `arq:m3a6`). Admin CRUD for `intake_mailboxes` (UI later). Verifiable with curl — no LLM,
  no bridge yet.
- **INTAKE-2 — AgentMail probe + mail-bridge (2 days; NEEDS the API key + inbox address).**
  First: scripted probe against the dedicated inbox — websocket subscribe, webhook payload
  capture, attachment download semantics (bytes vs signed URL — docs disagree),
  reply-with-docx round-trip; evidence → `docs/fork/evidence/intake-probe/`. Then the
  bridge: new microservice (mirrors slack-bridge): websocket subscriber loop (dev) +
  Svix-verified webhook route (prod-ready), envelope normalization + attachment fetch, POST
  to api; `POST /send` for outbound (contract landed now, used in INTAKE-4); compose service
  + env + healthcheck. Live smoke: email a real attachment to the test inbox → thread +
  project with ingested file appear. **The ONLY AgentMail-touching slice.**
- **INTAKE-3 — the intake run (2–3 days).** The heart of Ruling 1: intake doctrine skill
  (transparent, admin-editable; research taxonomy folded in as examples);
  `record_intake_outcome` tool (closed outcome enum + free-text label + note); worker
  launches ONE bound-area-agent run per inbound thread (`enqueue_agent_run_job`;
  `intake_threads.agent_thread_id` reused so follow-ups continue the SAME agent
  thread/conversation memory); outcome wiring (dealt-with → thread `handled` + project
  dismissed; paused → `awaiting_human`; candidate → project stays). New `draft_email_reply`
  tool registered in the commercial tool group, hitl_policy-gated unconditionally. NO gateway
  change (runs are normal `agent_loop` purpose). **Eval gate**: committed fixture pack of
  ~20 emails (extend `sample-documents/`), Claude-judged on OUTCOME correctness + label
  sanity; "paused for human when unsure" counts as a safe-fail. Live scenario test: NDA
  email → agent reads playbook → proposes redline + reply → run settles `awaiting_input`;
  spam email → `handled`, project dismissed.
- **INTAKE-4 — HITL widening + send (2–3 days).** ADR-F087 (amends F071): `edit` + `respond`
  decisions end-to-end — policy compile, `ResumeDecision`, `_build_resume_command`,
  `HitlConfirmCard` (args editor for `draft_email_reply` only). Approve → api → bridge
  `/send` → outbound recorded in `intake_messages`. Live verify: approved reply actually
  delivered to the counterparty address; edited reply sends the edited text.
- **INTAKE-5 — Intake UI (2–3 days).** Cockpit-level Intake view (Grids list+detail
  precedent): thread list with status/label/auth chips, awaiting-human first; detail =
  email thread + pending proposal card + candidate-matter link; promote / dismiss actions
  (`intake_state` transitions); default matter list filters candidates.
- **INTAKE-6 — milestone acceptance (1 day).** E2E live rehearsal on the dev stack: 5-email
  mixed pack (NDA w/ docx, MSA, bare question, spam, misdirected-HR) through the whole loop,
  evidence + screenshots in the PR; HANDOFF.md; backlog notes below.

Rough total: ~2 weeks of slices. INTAKE-1..3 are independent of the UI and individually
demonstrable; nothing user-visible changes until INTAKE-5 except the admin binding page.

## Maintainer decisions (updated 2026-08-16 after phone review)

1. **RESOLVED — redesigned per maintainer.** No deterministic classifier, no fixed policy:
   "classification cannot be deterministic; legal inboxes are messy places; if you have
   structured intake you don't need this." Every email thread = one deep-agent run on the
   bound Commercial agent; the run itself concludes dealt-with / paused-for-HITL / candidate
   matter (Ruling 1 as rewritten).
2. **RESOLVED — one owner.** "There is no Team who can own intake with agents" — one
   designated user owns and approves everything; team visibility not planned.
3. **RESOLVED — sending only after HITL.** Confirmed.
4. **RESOLVED — AgentMail.** Account exists (used on other projects); a dedicated inbox will
   be created. Key + inbox address needed only from INTAKE-2 on (the sole AgentMail-touching
   slice) — INTAKE-0/1 start without them.
5. **RESOLVED — no fixed taxonomy.** "A fixed list fits maybe 30% of my org, and orgs
   differ." Free-form agent labels now; categories EMERGE from use via a propose→approve
   consolidation slice after v1 (Doctrine section). Research taxonomy = doctrine examples
   only.
6. **RESOLVED — inbox first.** Maintainer 2026-08-16: "yes, inbox first." INTAKE is the next
   milestone; CUSTODIAN queues behind it (MILESTONES.md re-sequencing rides the INTAKE-0 PR).

## Risks

- **Wrong outcome** (the agent files something substantive as dealt-with). Mitigation:
  doctrine biases hard toward "pause for the human when unsure"; EVERY thread — including
  dealt-with ones — stays visible in the Intake list with its label + note, so nothing
  disappears silently; the owner can reopen and re-run; the INTAKE-3 eval gates outcome
  correctness before ship.
- **AgentMail unknowns** (attachment semantics, retry schedule, send idempotency) — INTAKE-0
  probe resolves before anything depends on them; our `intake_messages` unique keys make
  duplicate delivery a no-op regardless.
- **HITL widening touches every existing approval surface** (redline confirm etc.) — F087
  keeps `approve/reject` the default compile; `edit/respond` only where policy opts in;
  regression tests on the existing confirm path.
- **Candidate-matter clutter** — dealt-with outcomes auto-dismiss their eagerly-created
  project on the spot; only paused/candidate threads leave a visible matter, and the owner
  can dismiss those too.
- **Per-thread inference cost** (every email, even spam, spins the agent). Accepted by the
  maintainer in exchange for judgment; contained by lean budget profile + low step cap;
  tracked via existing token persistence. If real volumes ever hurt, a cheap spam pre-filter
  can return as a pure cost valve — maintainer's call, backlog only.
- **langgraph #6626** (parallel-interrupt ID collision) does not bite: deepagents batches all
  gated calls into ONE interrupt per turn (research report 1 §3/§5).
- **North-star check**: bridge is a per-customer container with a swappable provider (M365
  Graph bridge later, api unchanged); no always-on model loop (event-driven); AKS-compatible.

## Non-goals / backlog

- **Approve from Teams/Slack via the existing bridges** — the dominant production approval
  pattern (round-2 research §3); we already run both bridges, so a "pending approval →
  Teams/Slack card → decision posts back to /resume" surface is a natural post-v1 slice.
- Auto-ack fixed-template send (with Auto-Submitted loop guards) — first candidate after v1.
- Multi-area shared inbox + neutral router agent — only if a real customer inbox demands it.
- **Emergent taxonomy consolidation** (Ruling 5): propose org-specific categories + doctrine
  amendments from accumulated labels/outcomes; admin approves ("system proposes, user
  owns"). First candidate once v1 has real traffic.
- M365/Gmail production bridge (enterprise phase; same envelope contract).
- Intake doctrine editing UI (it's a skill — existing skill surfaces may already cover it).
- SLA nudges + intake analytics.
- Human-feedback → Lawyer Preferences / Practice Knowledge memory writes from edit/respond
  decisions (the agents-from-scratch memory-update pattern) — powerful, but its own ADR'd
  slice on top of the F050 prize work.
- OSS Agent Inbox compatibility shim (five LangGraph-Platform endpoints) — only if we ever
  want their hosted UI as a second surface.
