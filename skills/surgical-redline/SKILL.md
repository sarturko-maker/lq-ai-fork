---
name: surgical-redline
description: Use when redlining the other side's contract draft with tracked changes (the apply_redline / preview_redline tools) — for any clause you amend. Teaches the craft of surgical, structure-preserving edits — decompose a clause into several NARROW edits (swap a party, narrow a trigger, insert a carve-out) instead of striking the whole clause and retyping it, keep recognisable boilerplate bare, balance a one-sided clause by weaving protection in, and preview the rendered tracked changes before you apply.
lq_ai:
  title: Surgical Redline Craft
  version: 1.0.0
  author: LegalQuants
  tags: [commercial, redline, tracked-changes, contracts, drafting]
  jurisdiction: US-default
  trigger_examples:
    - "redline this MSA to protect us"
    - "turn this vendor-favoured agreement into our position with tracked changes"
    - "mark up the indemnity and liability clauses"
    - "redline clause 8 so the indemnity is mutual"
  inputs:
    required:
      - name: document
        type: document
        description: The matter .docx to redline (the counterparty's draft). The tools read it from the matter; you quote the exact existing text as each edit's anchor.
    optional:
      - name: positions
        type: text
        description: The house positions / playbook tier to apply (preferred / fallback / walk-away). If absent, apply the standing in-house posture and flag anything at or below a walk-away floor for the supervising lawyer.
---

# Surgical redline craft — change the few words that need changing

You are marking up the **other side's** draft with native tracked changes, via `apply_redline` (and
`preview_redline` to check your work first). A redline is read by a human who accepts or rejects each
change in Word. **Good craft is what makes that review fast and your position obvious.** This skill is
*how* to edit; the matter doctrine is *what* to protect.

## The one rule everything follows from

**One discrete change = one narrow edit.** Never strike a whole clause (or sentence) and retype it to
change part of it. Find the few words that carry the change and edit only those; leave the surrounding
language **bare** (unchanged), so the tracked-change view shows a small, legible edit — not a wall of red.

Striking and retyping near-identical language is the mark of a poor redliner: the big red block reads as
aggressive even when the change is tiny, and it buries *what actually changed* under text that did not.

This applies to **any** one-sided clause in **any** commercial agreement — MSA, SaaS, software licence,
DPA, NDA — not only the examples below. Keep these recognisable phrases **bare** and edit *around* them:

- the indemnity verb phrase — "shall indemnify, defend and hold harmless …";
- the liability-cap stem — "… shall not exceed the total fees paid by the [party] in the …": change only
  the period/number and **append** the carve-out proviso; **never** strike the whole cap sentence to add
  carve-outs;
- the skeleton of any clause you are only narrowing, qualifying, or making reciprocal — change the operative
  words, leave the frame.

A long continuous `[-…-]` block spanning a whole sentence is the tell that you rewrote wholesale — split it.

## Decompose a clause into several narrow edits

A one-sided clause is usually fixed by **several** small edits, each its own entry in the batch — a party
swap here, a narrowed trigger there, an inserted carve-out at the end. That is surgical; a single
clause-sized replacement is not.

### Worked example — mutualising a one-sided indemnity (§8)

> **Original:** *The Customer shall indemnify, defend and hold harmless the Vendor and its affiliates
> against any and all claims, losses, damages, liabilities and expenses arising from or in connection
> with the Customer's use of the Services or the Customer Data.*

**✗ Rip-and-replace (do NOT do this)** — one edit that strikes the whole clause and retypes it:

```
target_text: "The Customer shall indemnify, defend and hold harmless the Vendor and its affiliates
              against any and all claims, losses, damages, liabilities and expenses arising from or in
              connection with the Customer's use of the Services or the Customer Data."
new_text:     "The Vendor shall indemnify, defend and hold harmless the Customer ... [whole clause
              retyped] ..."
```

Even where the net change is small, this renders as one large struck-and-retyped block. The boilerplate
("shall indemnify, defend and hold harmless", "any and all claims, losses, damages") is destroyed and
recreated for no reason.

**✓ Surgical (do this)** — several narrow edits; the verb phrase and structure stay **bare**:

1. Mutualise the indemnifying party — swap one defined term ("shall indemnify, defend and hold harmless"
   stays bare):
   ```
   target_text: "The Customer shall"
   new_text:    "Each party shall"
   ```
2. Mutualise the protected party — swap one defined term; the rest of the phrase stays bare:
   ```
   target_text: "hold harmless the Vendor and its affiliates"
   new_text:    "hold harmless the other party and its affiliates"
   ```
3. Narrow the trigger so we don't indemnify the vendor's own wrongdoing, and add the reciprocal
   third-party-IP cover — **fold the addition into the boundary** (replace the closing punctuation; never
   append after an unchanged anchor):
   ```
   target_text: "arising from or in connection with the Customer's use of the Services or the Customer Data."
   new_text:    "to the extent arising from a party's breach of this Agreement, and each party shall
                 indemnify the other against any claim that its materials infringe a third party's
                 intellectual property rights."
   ```

Now the review shows three legible moves, and "shall indemnify, defend and hold harmless" is never touched.

### Worked example — capping liability (§9): a swap + an appended carve-out

> **Original:** *…shall not exceed the total fees paid by the Customer in the one (1) month preceding the
> claim.*

Two narrow edits, not a clause rewrite:

1. The period: `target_text: "one (1) month"` → `new_text: "twelve (12) months"`. "shall not exceed the
   total fees paid by the Customer in the … preceding the claim" stays bare.
2. The carve-out, **inserted** after the sentence: `target_text: "preceding the claim."` →
   `new_text: "preceding the claim; provided that this limitation shall not apply to liability for breach
   of confidentiality, infringement of the Customer's intellectual property, or the Vendor's gross
   negligence or wilful misconduct."`

## Inserting language (the common surgical move)

Balancing a clause is nearly always *adding* — a carve-out, a super-cap, a "deem-direct" requalification, a
reciprocal obligation — not replacing (matter doctrine: carve high-risk heads of loss out of the cap rather
than just raising the number; deem a key loss direct; make a one-way obligation reciprocal).

To add without rewriting, **fold the addition into the boundary**: end `target_text` at the clause's
punctuation and have `new_text` replace that punctuation and continue.

```
target_text: "preceding the claim."
new_text:    "preceding the claim, save that liability for breach of confidentiality, data protection or
              IP infringement shall be unlimited."
```

The unchanged head ("preceding the claim") stays bare; only the punctuation and the addition are tracked.
**Do not** append after an unchanged anchor — repeating the anchor verbatim and tacking text on the end is
a zero-width insertion the editor cannot place, and it will be rejected.

## Anchors must be exact and unique

`target_text` must be the **exact** existing text and appear **once** in the document (the tool rejects a
zero- or multiple-match anchor — quote a longer span to disambiguate). Keep each anchor as short as the
change needs; a long anchor risks sweeping unchanged words into the edit.

## Always preview before you apply

1. Read the document and decide your edits.
2. Call **`preview_redline`** with the full batch. It returns the rendered tracked-changes view
   (`[-struck-][+inserted+]`) and any gate feedback — **nothing is saved**.
3. Read the preview as the supervising lawyer will. For each clause you touched, check:
   - **Does any clause show a long continuous `[-…-]` block (more than a few words)?** That means you
     rewrote it wholesale — the cap, indemnity and warranty clauses are where this happens most. Split it.
   - is recognisable boilerplate (verb phrases, defined terms, structure) still **bare**?
   - does accepting every change yield the balanced clause you intend?
4. Revise every edit that reads as rip-and-replace into narrower edits (e.g. for the cap: one edit on the
   period, one appended carve-out proviso — not a struck-and-retyped sentence). Preview again if you
   changed much. Then call **`apply_redline`** **once** with the whole batch. (Each call redlines the
   original afresh — batch everything; don't apply in pieces.)

## Rationale, scope, and when to stop

- Every substantive edit carries a short `rationale` (it becomes a Word comment) — the "why", tied to
  protecting the client.
- Mark up only what matters — price, liability, indemnity, IP, term, data; let boilerplate go.
- `rewrite_justified` is a genuine last resort: only when a clause is so incoherent or one-sided that no
  decomposition works, and then say why in the rationale. If a full-clause rewrite has no defensible
  justification, or the markup is ballooning across the document, **escalate** rather than push it through.
- You propose; the supervising lawyer owns the accept. Keep redline strategy and rationale within the
  matter — it is privileged work product.
