---
name: surgical-redline
description: Use when redlining the other side's contract draft with tracked changes (the apply_redline / preview_redline tools) — for any clause you amend. Teaches how to return each amendment so the tool renders surgical, structure-preserving tracked changes — quote the existing clause and return it with only the necessary words changed (the tool computes the word-level diff and keeps the rest bare), balance one-sided clauses through the right legal mechanism, and preview before you apply.
lq_ai:
  title: Surgical Redline Craft
  version: 2.0.0
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
*how* to return an amendment so it renders surgically; the matter doctrine is *what* to protect.

## The one rule everything follows from

**Return the clause with only the necessary words changed, and keep every other word identical.**

For each amendment you set `target_text` to the existing clause (or the unique sentence you are
amending) and `new_text` to that **same text** with only the words that must change altered. The tool
computes the **word-level diff** between the two, so it strikes and inserts only the words that actually
differ and leaves the unchanged wording **bare**. You do **not** hand-craft narrow anchors, decompose a
clause into several tiny edits, or "split" a block — the tool does the surgery; your job is to preserve
the wording you are not changing.

The failure to avoid is **re-wording**: paraphrasing a clause you are only narrowing or mutualising.
If you re-type the clause in fresh words, the diff is legitimately large and the tracked change reads as
a wall of red — even when the legal change is tiny. So when you only mean to swap a party or narrow a
trigger, copy the original wording across into `new_text` verbatim and touch only those words.

Keep these recognisable phrases **identical** between `target_text` and `new_text` so they stay bare:

- the indemnity verb phrase — "shall indemnify, defend and hold harmless …";
- the liability-cap stem — "… shall not exceed the total fees paid by the [party] in the …": change only
  the period/number and **append** the carve-out proviso; never re-type the whole cap sentence;
- the skeleton of any clause you are only narrowing, qualifying, or making reciprocal — change the
  operative words, leave the frame word-for-word.

## How to quote the clause

- `target_text` must be the **exact** existing text and appear **once** in the document. Quoting the
  whole clause (or its full sentence) is the easy way to be unique and to capture every change you want
  to make there — the tool will still only mark the words that change.
- `new_text` is that same text edited in place. Where you are adding language (a carve-out, a reciprocal
  obligation), just write it into `new_text` at the right point — the tool renders the addition as a
  clean insertion; you do not need to manipulate punctuation or anchors to "place" it.
- If a clause spans two sentences and you are changing words in both, you may quote each sentence as its
  own edit — but you never need to go finer than that.

### Worked example — mutualising a one-sided indemnity (§8)

> **Original:** *The Customer shall indemnify, defend and hold harmless the Vendor and its affiliates
> against any and all claims, losses, damages, liabilities and expenses arising from or in connection
> with the Customer's use of the Services or the Customer Data.*

One edit. `target_text` is the clause above; `new_text` is the **same clause** with three changes woven
in — the indemnifying party, the protected party, and the trigger — and **everything else copied across
verbatim**:

```
target_text: "The Customer shall indemnify, defend and hold harmless the Vendor and its affiliates
              against any and all claims, losses, damages, liabilities and expenses arising from or in
              connection with the Customer's use of the Services or the Customer Data."
new_text:     "Each party shall indemnify, defend and hold harmless the other party and its affiliates
              against any and all claims, losses, damages, liabilities and expenses arising from or in
              connection with a party's breach of this Agreement, and each party shall indemnify the
              other against any claim that its materials infringe a third party's intellectual property
              rights."
```

Because the verb phrase, the "any and all claims, losses, damages…" list and the "and its affiliates"
frame are **identical** in both, the tool leaves them bare and the review shows only:
`[-The Customer-][+Each party+] … hold harmless the [-Vendor-][+other party+] … [-the Customer's use of
the Services or the Customer Data-][+a party's breach of this Agreement, and each party shall indemnify
…+]`. Three legible moves; "shall indemnify, defend and hold harmless" is never touched.

The mistake would be to write `new_text` as a freshly-phrased mutual indemnity — even with the same
meaning, every word would differ and the whole clause would strike-and-retype.

### Worked example — capping liability (§9): a number swap + an appended carve-out

> **Original:** *…shall not exceed the total fees paid by the Customer in the one (1) month preceding the
> claim.*

`target_text` is the sentence; `new_text` is the same sentence with the period changed and the carve-out
added — the cap stem copied across word-for-word:

```
target_text: "shall not exceed the total fees paid by the Customer in the one (1) month preceding the
              claim."
new_text:     "shall not exceed the total fees paid by the Customer in the twelve (12) months preceding
              the claim; provided that this limitation shall not apply to liability for breach of
              confidentiality, infringement of the Customer's intellectual property, or the Vendor's
              gross negligence or wilful misconduct."
```

The tool marks `[-one (1) month-][+twelve (12) months+]` and inserts the proviso; the cap stem stays
bare.

## What to change (matter doctrine)

Balancing a one-sided clause is nearly always *adding* protection through the right mechanism — not just
flipping a number:

- carve high-risk heads of loss (confidentiality, data protection, IP infringement, indemnified claims)
  **out** of the liability cap, or put them under a higher super-cap, rather than only raising the number;
- **deem** a key loss (e.g. data-breach response costs) a direct loss so an exclusion of indirect/
  consequential loss cannot reach it;
- make a one-way obligation **reciprocal** (mutualise indemnities, audit rights, termination rights);
- narrow an over-broad trigger to *that party's* breach/negligence; read the whole agreement for the
  defined terms and cross-references your change depends on.

Mark up only what matters — price, liability, indemnity, IP, term, data; let pure boilerplate go.

## Always preview before you apply

1. Read the document and decide your edits.
2. Call **`preview_redline`** with the full batch. It returns the rendered tracked-changes view
   (`[-struck-][+inserted+]`) and any gate feedback — **nothing is saved**.
3. Read the preview as the supervising lawyer will. For each clause you touched, check:
   - **Are only the words that needed changing struck, with the rest bare?** A large continuous
     `[-…-]` block means you re-worded more than necessary — go back to `new_text` and copy the
     unchanged wording across verbatim so only the operative words differ.
   - is recognisable boilerplate (verb phrases, defined terms, structure) still **bare**?
   - does accepting every change yield the balanced clause you intend?
4. Revise any edit that reads as rip-and-replace, then preview again if you changed much. When the
   redline reads surgically, call **`apply_redline`** **once** with the whole batch. (Each call redlines
   the original afresh — batch everything; don't apply in pieces.)

## Rationale, scope, and when to stop

- Every substantive edit carries a short `rationale` (it becomes a Word comment) — the "why", tied to
  protecting the client.
- `rewrite_justified` is a genuine last resort: only when a clause is so incoherent or one-sided that no
  in-place edit works, and then say why in the rationale. If a full-clause rewrite has no defensible
  justification, or the markup is ballooning across the document, **escalate** rather than push it through.
- You propose; the supervising lawyer owns the accept. Keep redline strategy and rationale within the
  matter — it is privileged work product.
