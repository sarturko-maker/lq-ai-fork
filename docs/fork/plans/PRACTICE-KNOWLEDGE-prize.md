# The prize — Practice Knowledge: cross-matter learning behind a safety harness

**Status: SKETCH (design only — not built).** Registers the target so the N-ladder builds toward it.
Decision space: [ADR-F050](../../adr/F050-practice-knowledge-shared-learning.md) (proposed). Sits on the
F2 memory arc ([RETRIEVAL-MEMORY-eval-first.md](RETRIEVAL-MEMORY-eval-first.md)); sequenced **after** the
N-ladder (N1 → N2 → N3). Built **eval-first** (Track-A) and **research-led** — multiple slices, each with
the deeper security review (ADR-F005).

## What it is (plain language)

**Practice Knowledge** — the firm's approved, anonymised house know-how that builds up across many
matters and is shared across the whole practice group (e.g. *"in SaaS MSAs we push for a mutual liability
cap and resist unlimited indemnities"*, *"we escalate rather than concede perpetuity"*). It is the
highest-value memory tier and the one the whole F2 memory arc is ultimately for.

Contrast (see CLAUDE.md § Memory tiers for the full set + one-line descriptions):
- **Matter File** = facts about *one* deal (this matter). Dies with the deal. Stays SQL, human-owned.
- **Practice Knowledge** = patterns/preferences that span *many* deals. Outlives any matter. Shared.

## How deepagents "learns" — and why we can't use it as-is

deepagents' loop is **read → notice → write → reload**: at run start it pastes a memory file into the
briefing plus a standing instruction *"save new knowledge with `edit_file`"*; during the run the agent
writes durable notes; next run reloads them. Store-backed, that persists across conversations and matters.

We keep the **shape** (notes in the Store, reloaded into the briefing) but replace the **autopilot**,
because a *shared* tier whose blast radius is every colleague's every matter needs a **two-direction
gate**:

- **Anti-leakage / confidentiality (the bigger one).** A "learning" must never carry matter/client
  secrets onto the shared shelf — that is a confidentiality / conflicts / Chinese-wall / privilege
  breach. (True even within one lawyer's own book: Client X's secrets must not reach Client Y's matter;
  team-sharing only widens the radius.)
- **Anti-poisoning.** A wrong or prompt-injected "learning" must never become trusted house guidance.

CLAUDE.md already makes the shared tiers (House Brief, Practice Playbook) read-only to agents for exactly
this reason; Practice Knowledge must earn agent-proposed learning without re-opening that boundary.

## The harness (the centrepiece)

```
agent drafts a CANDIDATE   (never writes the shared shelf directly)
      ↓
DE-IDENTIFY / GENERALISE   (strip parties, figures, dates, client specifics)
      ↓
GUARD                      (reject anything still matter-specific / confidential)
      ↓
HUMAN CURATOR APPROVAL     (a senior / knowledge lead — NOT the contributing lawyer)
      ↓
PROMOTE → shared Store tier (tagged with PROVENANCE; REVOCABLE)
```

The shared shelf is **curated, not crowdsourced**: proposals flow up from everyone; only an approver
promotes. Reads inject it like the other read-only tiers (data-only fence).

### The three maintainer questions, answered by the harness
- **Only generalised learnings reach the shelf** → de-identify + guard + human approval (enforced, not
  trusted).
- **User preferences kept separate from shared learnings** → **Lawyer Preferences** is a *different,
  per-user* shelf, never promoted; personal style never becomes house knowledge.
- **5 good / 5 bad lawyers** → promotion needs an approver (not the contributor) + provenance; nothing is
  house knowledge until approved, so bad/non-approved learnings structurally can't leak in.

## Likely slice breakdown (indicative — re-plan at the milestone)

1. **Lawyer Preferences read-back** — light up the existing per-user shelf (the small, low-blast-radius
   end of the learning loop): the agent reads back its own private notes about how the lawyer works.
   (This is *not* N1 — it belongs here.)
2. **Candidate capture + staging** — the agent proposes a learning into a staging area (never the shared
   shelf); provenance recorded; nothing injected yet.
3. **De-identify + guard** — the generalisation pass (gateway-routed, ADR-F010) + the confidentiality
   guard; eval the leak rate hard.
4. **Curator review surface** — a cockpit approve/edit/reject/revoke panel (cousin of the pinned-
   corrections panel); approval writes the shared Store tier.
5. **Inject + measure** — read Practice Knowledge into the briefing (read-only fence); Track-A measures
   that it helps and never leaks/poisons.

(Conflict/staleness handling reuses the bi-temporal idea from the fact ledger, ADR-F042/F043.)

## Research questions (this is why it's research-led)
- De-identification that is *safe enough* for legal confidentiality — what technique, what residual-risk
  bar, how measured? (A single-client "pattern" can still be identifying.)
- Prompt-injection-resistant candidate capture (untrusted document text must never become a learning).
- The curator workflow + trust/provenance model (weighting, corroboration, revocation propagation).
- The eval: how to *prove* a learning improves outcomes AND prove non-leakage / non-poisoning.

## Non-goals
- Not built until ADR-F050 is accepted and the milestone is planned.
- No autonomous agent write to any shared tier, ever.
- No convergence of the Matter File onto the Store (separate ADR'd slice).
