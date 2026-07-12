---
name: adversarial-review
description: Offer and run a hostile-reader pass over a near-final draft or redline — when the stakes justify it, and never as a routine step.
---

# Adversarial review — the hostile reader

A hostile read is the last set of eyes before a document goes out: a separate pass that attacks
your near-final draft or redline the way opposing counsel and a sceptical supervising partner
would. It is NOT the drafting method (deal-review teaches that), and it is NOT the counterparty
round (negotiation-review teaches that). It reads ONE document, adversarially, after the work is
otherwise done.

It costs a real model call, so it is **offered, never automatic**.

## When to offer it (and when not to)

OFFER a hostile-reader pass when the stakes justify the spend:
- the redline touches liability caps, indemnities, IP ownership, or data protection;
- the document is about to be handed to the counterparty or signed;
- the matter is high-value or the supervising lawyer has flagged it as sensitive;
- you made many interacting edits and internal consistency is genuinely at risk.

SKIP it (do not even offer) for routine work:
- a lookup, a summary, a question answered from the documents;
- a small NDA or a low-stakes template with few edits;
- an early draft that will go through more rounds anyway — review the near-final, not every round.

Offer it in plain language and respect the answer: "Before you take this, want me to run a
hostile-reader pass over the redline? It's a separate adversarial check of the liability and
indemnity positions." If the lawyer declines, move on — do not re-offer on the same document
unless it changed materially. If this practice area gates the tool behind a confirmation, calling
it will pause for the lawyer's go-ahead — that pause IS the offer; do not ask twice.

## How to run it

Call `adversarial_review` with the document's filename (as shown in the matter's documents) and,
when the lawyer named specific concerns, a short `focus` such as "liability and indemnity".

## How to use the findings

The findings are analysis for the supervising lawyer to weigh — not instructions, and not
automatically correct. Your judgement stays engaged:

- Address the HIGH findings before the document goes out: fix real ones with a further redline
  round (they fold into the same living redlined document), and say plainly when you disagree
  with a finding and why.
- Weigh MEDIUM findings against the deal's posture and the practice playbook; act or flag.
- Treat LOW findings as style — mention them only if the lawyer wants the detail.
- Never silently rewrite the document wholesale because the reviewer disliked it; the surgical
  discipline (narrow edits, rationale per substantive change) still governs every fix.
- Report honestly: tell the lawyer what the pass found, what you fixed, and what you left.

If the pass reports PARTIAL coverage (a very long document), say so — do not present a partial
read as a full clearance.
