# F050 — Practice Knowledge: shared cross-matter learning behind a safety harness

- Status: **proposed** (sketch — registers the decision space + the load-bearing invariants for a future
  milestone; NOT accepted. No code lands on this ADR until it is accepted and sliced.)
- Date: 2026-06-28
- Relates to: ADR-F049 (native memory substrate + eval-gated retrieval), ADR-F042 (unit-of-work
  auto-write-then-correct), ADR-0013 D4 ("system proposes, user owns"), ADR-F010 (gateway egress),
  ADR-F015 (eval metrics are findings). Full design: `docs/fork/plans/PRACTICE-KNOWLEDGE-prize.md`.

## Context

The fork's memory model has four levels (CLAUDE.md § Memory model). One — **Practice Knowledge** (the
firm's approved, anonymised house know-how that compounds across matters and is **shared across the whole
practice group**) — is the highest-value memory tier and does **not exist yet**. It is the "prize" the
F2 memory arc is ultimately building toward.

deepagents ships a generic "learn and save new knowledge yourself" loop (its `MemoryMiddleware`): the
agent decides what is worth keeping and writes it via `edit_file`; the note is reloaded into the system
prompt on the next run. That loop is the right *shape* (notes written to the Store, reloaded into the
briefing) but the *autopilot* is unsafe for a legal product, and uniquely so for a **shared** tier whose
blast radius is every colleague's every matter:

- **Anti-leakage / confidentiality (the larger risk).** A "learning" that carries matter- or
  client-confidential detail onto the shared shelf is a confidentiality breach and a conflicts /
  Chinese-wall / privilege failure — colleagues (possibly acting *against* that client elsewhere) would
  see it. This risk exists even for one lawyer's own book (Client X's secrets must not reach Client Y's
  matter); sharing across the team only widens the radius.
- **Anti-poisoning.** A wrong or prompt-injected "learning" (e.g. hidden text in a counterparty document)
  must never become trusted house guidance for the whole group.

CLAUDE.md already makes the two *shared* tiers (House Brief, Practice Playbook) **read-only to agents**
for exactly this reason. Practice Knowledge needs the value of agent-proposed learning *without*
re-opening that boundary.

## Considered options

1. **Adopt deepagents' stock auto-save loop to a shared Store namespace.** Lowest effort. **Rejected** —
   no de-identification, no human approval, no provenance; the agent's `edit_file` would write a shared,
   prompt-injected, confidential-leaking tier. Directly violates the read-only-shared-tier boundary.
2. **Per-user learning only (Lawyer Preferences), no shared tier.** Safe and small — a private per-lawyer
   shelf the agent proposes and the lawyer owns. **Partial** — captures personal style but misses the
   cross-matter, cross-lawyer firm know-how that is the actual prize (and still needs a confidentiality
   gate within one lawyer's book).
3. **Harnessed propose → de-identify → guard → human-curator approval → provenance → revoke pipeline,
   writing to a curated shared Store tier.** Keeps the value, closes both gates; the Store is storage but
   the learn loop is fork-owned (not stock). Highest effort; security-sensitive; multi-slice + research.
4. **No learning at all (status quo).** Zero risk, zero prize.

## Decision outcome (proposed)

**Direction = Option 3**, built as its **own multi-slice, research-led milestone sequenced AFTER the
N-ladder** (N1 → N2 → N3) and **eval-gated** (Track-A must show learnings help and never leak/poison,
ADR-F015). This ADR is **proposed only**: it registers the direction and the non-negotiable invariants so
no piece of it is built ad hoc before the milestone is planned and this ADR is accepted.

Load-bearing invariants (any implementation must honour all):
- **Curated, not crowdsourced** — the agent only *proposes* a candidate into a staging area; nothing
  reaches the shared shelf without a designated human curator's approval (never the contributing lawyer).
- **De-identify before promote** — strip parties, figures, dates, client specifics; a guard rejects
  anything still matter-specific. "Generalised" is enforced, not trusted.
- **Provenance + revocation** — every candidate tagged with origin matter/lawyer; every promoted item
  revocable.
- **Untrusted input boundary** — document text can never become a learning directly (prompt-injection).
- **Lawyer Preferences ≠ Practice Knowledge** — the private per-user shelf is never auto-promoted to the
  shared tier.
- **Gateway + brakes + audit** — any model-assisted de-id/generalisation routes through the gateway
  (ADR-F010); writes/promotions pass the guard chokepoint and audit counts/IDs only.

## Consequences

- Confidentiality/conflicts become a first-class, code-enforced concern of the memory layer, not a
  prompt-time hope.
- A new human role (knowledge curator) and a cockpit review/approve/revoke surface are required.
- Staleness/conflict handling reuses the bi-temporal idea from the fact ledger (ADR-F042/F043).
- The milestone is security-sensitive → each slice gets the deeper security-focused review (ADR-F005).
- Until accepted + built, Practice Knowledge stays absent; the agent's cross-matter improvement is
  deferred (the N-ladder ships the substrate + recall first).
