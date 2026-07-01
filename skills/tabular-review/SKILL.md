---
name: tabular-review
description: Use when this matter holds SEVERAL documents and the lawyer wants the same fields compared, extracted, or summarised across them — a due-diligence sweep, a key-terms table, "what is the X in each of these", "compare these contracts". Teaches when to PROACTIVELY offer a grid (so the lawyer discovers the capability), how to map natural language onto start_tabular_review with well-chosen columns, ready-made column templates for common reviews, and — just as important — when NOT to build a grid.
lq_ai:
  title: Tabular Review Craft
  version: 1.0.0
  author: LegalQuants
  tags: [commercial, tabular, grid, due-diligence, comparison, extraction]
  jurisdiction: general
  trigger_examples:
    - "compare the term and governing law across these three NDAs"
    - "I've dropped 12 contracts in — help me get on top of them"
    - "make me a table of the key terms in each of these agreements"
    - "what's the liability cap in each vendor MSA?"
    - "due diligence grid for the data room documents"
    - "summarise the payment terms across all the SOWs"
  inputs:
    required:
      - name: documents
        type: document
        description: Two or more of this matter's ingested documents. The grid has one row per document; you pass filenames to the tabular tools, which resolve them within the matter.
    optional:
      - name: columns
        type: text
        description: The fields to extract (each becomes a column — a name plus the question asked of every document). If the lawyer does not spell them out, infer them from the ask and the document type, propose them briefly, and proceed.
---

# Tabular review — offer a grid, map the ask to columns, know when not to

This matter has a **grid** capability: a columns-as-questions × documents-as-rows table the agent builds
by reading each document and recording its answers, with a verbatim source quote and a confidence per
cell. It is the right tool whenever the real question is *"the same thing, across many documents."* The
`start_tabular_review` → (fan out) `record_tabular_row` → `finalize_tabular_review` mechanics are covered by
the matter's standing method; **this skill is about judgement**: when to reach for a grid (and say so),
how to turn a loose request into good columns, and when a grid is the wrong answer.

## Reach for a grid — the lawyer may not know grids exist

When this matter holds **several documents** and the ask is even loosely comparative or extract-across —
"compare these", "the X in each", "get on top of these", "what's the best way to see this across them",
"key terms of these contracts" — the grid is the answer. **Build it**; do not answer that same
across-many-documents question in prose. Reading each document and typing the fields into the reply is the
*wrong* move here: it buries the comparison, carries no per-cell source quote or confidence, and leaves the
lawyer nothing to iterate on. A grid does all three and the lawyer can adjust it conversationally.

So on a clear multi-document compare/extract/get-on-top intent, **just build the grid** with sensible
columns inferred from the ask and the document type, then present it — that IS the answer, and it is the
strongest way to show the lawyer the capability exists. You do not need permission first; the grid is
cheap, auditable, and fully adjustable ("add a column", "re-pull that cell", "combine these two").

Only **offer-and-ask-first** when it is genuinely unclear whether a grid fits (an ambiguous ask, or an
unusually large/expensive run) — and then make the offer concrete by naming the columns, so the capability
is still discoverable:

> "There are 6 NDAs here — I can build a grid comparing them (**Term**, **Governing law**, **Assignment**,
> **Carve-outs**) with the exact wording pulled for each. Want that, or a narrower cut?"

If the lawyer named only one field ("the term in each?"), still build the grid with that one column — a
one-column grid over many documents beats a prose list, and they can add columns from there.

## Map natural language onto columns

The lawyer will rarely hand you a column list. Translate:

- **"compare / table of / grid of / line these up"** → a grid; the fields named become columns.
- **"the X across / in each / for all"** → one column `X` (add obvious siblings if they clearly help).
- **"key terms" / "the important bits"** → a template below, trimmed to the document type.
- **"due diligence on the data room"** → the M&A DD template, scoped to the document class present.

Each column is a **name** (the header the lawyer reads) plus a **question** asked of every document (what
the reader extracts). Prefer a handful of sharp, answerable columns over a sprawling set — you can always
add a column later on request. A column whose answer is a long clause is fine; the cell keeps a short
verbatim `source_quote` and the full text stays one click away.

## Column templates (starting points, not straitjackets)

Trim and adapt to the actual documents and the lawyer's ask.

- **Key commercial terms (any agreement):** Parties · Term & renewal · Termination rights · Payment /
  fees · Liability cap · Indemnities · Governing law · Assignment / change of control.
- **NDA sweep:** Mutual or one-way · Term · Definition of Confidential Information · Permitted use ·
  Carve-outs · Return/destruction · Governing law.
- **M&A due-diligence (contracts):** Counterparty · Value / fees · Term & expiry · Change-of-control /
  assignment on a sale · Termination for convenience · Exclusivity / non-compete · Liability cap ·
  Governing law · Red flags.
- **SaaS / MSA:** Service & SLA · Fees & uplift · Data protection / sub-processors · Security commitments
  · Liability cap & exclusions · IP ownership · Term & termination · Governing law.
- **Data protection (DPA / processing):** Role (controller/processor) · Purpose · Categories of data ·
  Sub-processors · International transfers · Security measures · Breach notification · Audit rights.

## When NOT to build a grid — restraint is part of the craft

A grid is for *many documents, same fields*. Do not reach for it when:

- **One document.** A single contract is a read-and-answer or a redline job, not a grid — answer directly
  (or use the matter's review/redline method). "What's the cap in this MSA?" over one file is a lookup.
- **A single cross-cutting question that needs one mind.** Tracing one defined term through a deal, or
  "does this set hang together / conflict?", is a reasoning task, not a per-document extraction — answer in
  prose; don't fragment it into cells.
- **Drafting, negotiating, or advising.** Writing a clause, responding to a counterparty's markup, or
  giving a recommendation are not extraction — use the right method for those.
- **The ask is genuinely open.** If it is unclear what to compare, ask one sharp clarifying question rather
  than guessing a grid into existence.

Offer a grid when it *fits*; stay quiet when it doesn't. An over-eager grid on a one-document lookup is as
much a miss as failing to offer one across a data room.

## After the grid exists

The grid is the work product and the matter keeps it. The lawyer can iterate conversationally — "add a
governing-law column", "re-pull the cap for rows 3 and 7", "combine the two Acme agreements" — and you
update the same grid in place. Keep it current; the lawyer owns it and can correct or undo any change.
