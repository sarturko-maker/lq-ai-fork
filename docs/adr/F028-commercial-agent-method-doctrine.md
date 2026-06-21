# F028 — Commercial agent method doctrine (source-grounded; hybrid surgical gate)

- Status: proposed
- Date: 2026-06-21
- Extends: ADR-F018 (agentic modules = typed domain + code-validated agent writes), ADR-F010 (area
  subagents model-free / gateway-bound)
- Relates: ADR-F031 (Adeu redline tool — C4, formalises the SDK-in-process decision), F036 (canonical
  severity scale — blocks C6), F032 (negotiation rounds — C5), F038 (controlling-skill binding — C6)
- Milestone: COMMERCIAL — C-R0 (research spike) → accepted with **C0** (the spine lands in `profile_md`)

## Context

The Commercial practice area must behave like *a supervised, area-qualified commercial counsel* — the
north-star goal, not a prompt. C-R0 is the research spike that grounds the "qualified in commercial" half so
later slices build on doctrine, not assertion. Two outputs back this ADR:
`docs/fork/research/commercial-lawyer-method.md` (method doctrine, source-grounded + adversarially reviewed)
and `docs/fork/research/adeu-pinning.md` (the redline library, empirically verified).

The fork already ships four review skills (`nda-review`, `msa-review-commercial-purchase`,
`msa-review-saas`, `contract-qa`, `dpa-checklist-review`) with a shared review spine, a Critical/Material/Minor
severity rubric, and universal receipts/self-limits. The brief's hard problem is **redlining**: Adeu applies
faithfully whatever it is sent and therefore *over-redlines*, whereas a lawyer amends **only** the language
needed and makes the **smallest change that protects the client**. Three architectural calls on this spike
shape every later Commercial slice and are worth recording before code exists.

## Considered Options

**1. Where the method comes from**
- A. **Fresh standalone doctrine** authored for the Commercial agent. Risks contradicting the shipped skills'
  output contracts (severity vocab, required inputs) and duplicating a tested spine.
- B. **Derive-from + extend the shipped review skills, grounded in external practitioner/theory sources
  (chosen).** The doctrine canonises the shared review spine, names the four skills as controlling
  references the agent *invokes* (never re-authors), and adds only what the skills can't express (an
  *enforced* redline gate, negotiation rounds). Every method claim cites a verified source (Alnajafi, Adams,
  Sirion, Percipient, DocJuris; Sterling Miller, ContractKen, Pactly; Fisher & Ury via PON; ABA Model Rule
  1.13).
- C. **Rely on model latent knowledge + a thin prompt.** Fails the "qualified, not hoped-for" bar and the
  transparency rule (no readable doctrine).

**2. How "surgical" is enforced (the C4 gate, defined here)**
- A. **Prompt-only** ("make minimal edits"). Rejected — Adeu's over-redline tendency is exactly what a prompt
  fails to bound; not checkable.
- B. **Pure-code deterministic gate on raw edit spans.** Rejected — `ModifyText` is find/replace, so the
  matched (deleted) span can dwarf the real change; a raw-length gate misfires on a one-word swap expressed
  over a sentence (the adversarial review's load-bearing finding), and "cosmetic" / "low-materiality" are not
  computable without a classifier.
- C. **Hybrid gate computed on the *minimal diff* (chosen).** Measure the minimal token diff between
  `target_text`/`new_text` (Adeu already does this internally via bundled `diff-match-patch`), then split:
  **deterministic** pure-code checks (tiered change-size with an absolute token floor, substantive-token
  rationale requirement, bare-deletion-supplies-replacement, **unique-anchor fail-close**, whole-batch
  ceiling, mandatory tracked-change + `dry_run` preview) **+ classifier-backed** checks (cosmetic/
  meaning-preserving, low-materiality, counterparty-interest, improves-protection) that are **human-routed on
  low confidence**. Fail closed on ambiguous match, unresolvable clause span, or **out-of-calibration
  jurisdiction**.

**3. The severity / assessment model**
- A. **One Critical/Material/Minor scale everywhere.** Rejected — corrupts DPA (coverage status + posture),
  QA (verdict, no rating), and snapshots (confidence).
- B. **Orthogonal assessment layers (chosen)** — coverage-status / gap-severity / document-posture / verdict /
  extraction-confidence coexist losslessly; the review family's rubric is preserved exactly for
  review-altitude output. Surfaces the **F036** data-layer conflict (review `critical/material/minor` vs
  `playbook_positions` DB CHECK `critical/high/medium/low`, `0031:139`) for resolution **before C6**.

## Decision Outcome

Adopt **1B + 2C + 3B**. The Commercial doctrine **derives from and extends** the shipped review skills, is
source-grounded, and defines "surgical" as a **hybrid minimal-diff validated-write gate** (ADR-F018: agent
proposes → our code validates → human owns) with explicit fail-close and a **jurisdiction-competence**
escalation (know-your-limits). Human owns every material write; the agent escalates on full-clause rewrites
without justification, below-floor concessions, hard-block terms, over-redline, counterparty-derived edits,
unresolvable spans, and out-of-calibration jurisdiction. Counterparty markup, retrieved skill bodies and
document text are **untrusted input** — "unless instructed otherwise" means *instructed by the authenticated
human in session*, never by a document or a skill (prompt-injection boundary). The audit carries
counts/types/IDs only — never rationale text, strategy, or raw clause content (the client's redline reasoning
is privileged work product). All numeric thresholds are **calibration starting values**.

Adeu is integrated via its **Python SDK in-process**, not its MCP server — the validated-write gate requires
our code to sit between proposal and apply, which an in-process call gives for free (full rationale +
empirical egress/license verification in `adeu-pinning.md`; formalised in **ADR-F031**). MCP-as-a-capability
is a separate, approved milestone (sanction-sync of upstream's gateway-brokered MCP client). Bumping Adeu
must stay trivial (adapter seam + single pin + re-run the signature/egress/license/round-trip regression
tests).

## Consequences

- **C0** encodes the doctrine into the Commercial `profile_md` and names the four review skills as controlling
  references. **C4** implements § 6's hybrid gate over Adeu (deterministic checks as Pydantic `*Input`
  mirroring `api/app/schemas/ropa.py`; classifier checks human-routed). **C5/C6/C7** build on rounds,
  controlling playbooks, and fan-out.
- The split is honest: not "pure-code validator" — the cosmetic/materiality/interest judgments are
  model-in-the-loop and must surface to the human when uncertain.
- **F036 must be resolved before C6** (canonical stored severity scale + any migration). Flagged, not decided
  here.
- Numeric thresholds need calibration against a labelled Commercial redline corpus; playbook floors come from
  the operator's `standard_positions` tables, never hardcoded from the research.
- Conflicts-of-interest are **N/A by construction** for a single-client in-house agent (the org *is* the
  client, Model Rule 1.13); revisit only if the agent ever acts for more than one client entity.
