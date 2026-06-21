# C-CLIENT live verification — injected client/house context (DeepSeek)

Slice **C-CLIENT** (ADR-F030): the operator's Organization Profile (the company/
client memory tier) is injected read-only at the composition seam. Proof is an A/B —
the same Commercial matter and prompt, profile **OFF then ON** — using a synthetic
Zendesk house context (`zendesk-org-profile.md`). Per ADR-F015 the house-context
signals are findings, not a pass/fail gate.

## supplier · profile OFF — `supplier_uncapped_liability` · completed · 12 steps

**Prompt:** We are Zendesk, the Provider on the Northwind MSA in this matter. Northwind's redline deletes the Section 7 liability cap entirely, so our liability to them would be uncapped. What is our position, and what should we do next?

**Tools:** ['search_documents', 'read_document', 'search_documents', 'search_documents']  ·  **House signals:** ['escalat', 'hard no']

**Answer:**

> The matter only contains the base MSA text — there's no redline document on file. But working from what you've described, here is the position.
> 
> ---
> 
> ## Assessment
> 
> **Section 7 — Limitation of Liability** (as agreed in the base draft):
> 
> > Except for liability arising from a breach of confidentiality, either party's indemnification obligations, or a breach of the Data Protection obligations, each party's aggregate liability under this Agreement shall not exceed the total fees paid by Customer in the twelve (12) months immediately preceding the event giving rise to the claim. Neither party shall be liable for any indirect, incidental, or consequential damages.
> 
> This is a standard, mutual, pro-Provider cap — a 12-month **fee-based cap** (not a fixed dollar amount) with mutual carve-outs for t…

## supplier · profile ON — `supplier_uncapped_liability` · completed · 7 steps

**Prompt:** We are Zendesk, the Provider on the Northwind MSA in this matter. Northwind's redline deletes the Section 7 liability cap entirely, so our liability to them would be uncapped. What is our position, and what should we do next?

**Tools:** ['search_documents', 'read_document']  ·  **House signals:** ['escalat', 'general counsel', 'hard no', '2x annual']

**Answer:**

> ## Position
> 
> Northwind's redline deletes **Section 7** of the MSA in its entirety. That section is our standard liability cap (mutual, capped at fees paid in the prior 12 months, with carve-outs and an exclusion of indirect damages). Its deletion means **our liability to Northwind would be uncapped** — no ceiling, no exclusion of consequential damages.
> 
> Per our house posture, **uncapped liability of Zendesk is a hard no** — this is a line we do not cross and it **requires escalation to the General Counsel**.
> 
> ---
> 
> ## What we should do next
> 
> ### 1. Prepare the counter-proposal before escalating
> 
> We don't escalate an open question — we escalate with a clear recommendation and fallback. The next step is to counter Northwind's deletion by:
> 
> **Counter-proposal (restore Section 7 with the liabil…

## procurement · profile ON — `customer_procurement_dpa` · completed · 7 steps

**Prompt:** Separately in this matter, we are buying a vendor tool, SecureScan, to scan our support tickets for threats. SecureScan will process our customers' personal data. Their order form caps SecureScan's total liability at three months' fees and includes no data-processing terms. What should we push back on before we sign?

**Tools:** ['search_documents', 'read_document']  ·  **House signals:** ['dpa', 'data processing addendum', 'vendor']

**Answer:**

> This is a **procurement** where Zendesk is the customer buying a tool that will process our customers' personal data. Two issues block signature.
> 
> ---
> 
> ## 1. Missing Data Processing Addendum — **Blocker (must-have)**
> 
> The order form includes **no data-processing terms**. SecureScan will process our customers' personal data (scanning the content of support tickets). Per our house position:
> 
> > *"If we are buying a tool that will touch our or our customers' personal data and there are no data-processing terms, that blocks signature — require a DPA."*
> 
> **Action:** Require SecureScan to enter into a Data Processing Addendum incorporating Standard Contractual Clauses (SCCs) for any international transfers, before signing. This is non-negotiable.
> 
> ---
> 
> ## 2. Liability cap at three months' fees — …
