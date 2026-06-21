"""A worked client for the C-CLIENT slice — a synthetic Zendesk house context.

C-CLIENT (ADR-F030) wires the company/client memory tier: the operator's
``OrganizationProfile`` is injected, read-only, into the Commercial agent's
system prompt. To prove the wiring *changes behaviour* we need a real client to
act for. This module supplies one: a synthetic in-house-legal house context for
a well-known SaaS company (Zendesk), a small MSA on its own paper, and the A/B
scenarios the live test runs with the profile OFF then ON.

ILLUSTRATIVE / SYNTHETIC. This is a fictional house playbook authored for a
demo; it is not Zendesk's actual legal position and creates no representation.
The numbers (caps, tiers, thresholds) are plausible placeholders, not advice.
"""

from __future__ import annotations

from tests.agents.scenarios.scenarios import FixtureDocument, Scenario, build_document

# --- the company/client tier: the operator's Organization Profile body --------

ZENDESK_PROFILE_MD = """\
# Zendesk, Inc. — in-house legal house context

*Synthetic house playbook for demonstration — not legal advice, not Zendesk's
actual positions.*

## Who we are
We are the in-house commercial legal team of **Zendesk, Inc.**, a customer-
service / CX software-as-a-service company. Most deals are **our SaaS sold to a
customer on our paper — so we are usually the SUPPLIER**. But we also **procure**
tools, infrastructure and services, where **we are the CUSTOMER**. Work out which
side we are on for each matter (our paper / "Provider" = we are the supplier; a
vendor's paper / "we are buying" = we are the customer) and flip the posture
accordingly. If the side is unclear, ask before advising.

## Standing risk posture (house positions)
- **Limitation of liability.** Our standard is a **mutual cap at the fees paid
  in the prior 12 months**, with carve-outs (confidentiality breach, IP
  indemnity, data-protection breach) **super-capped at 2x annual fees — never
  uncapped**. **Uncapped liability of Zendesk is a hard no → escalate to the
  General Counsel.** Always exclude indirect / consequential damages, both ways.
- **When we are the customer (procurement), flip:** push for **vendor**
  accountability, resist a low one-sided vendor cap, and do not accept the vendor
  excluding its own data-breach or IP-infringement liability.
- **Data protection.** Where a vendor or we process personal data, a **Data
  Processing Addendum is mandatory** (SCCs for international transfers). If we are
  buying a tool that will touch our or our customers' personal data and there are
  **no data-processing terms, that blocks signature** — require a DPA.
- **IP.** Each party keeps its background IP; the customer owns its data; we own
  the platform and improvements; we take a licence to feedback. Resist any
  assignment of our platform IP → escalate.
- **Governing law / venue.** Our paper is **California law**; resist exotic
  forums. A non-standard governing law is a flag, not an auto-accept.

## House style
- **Redline surgically** — the smallest change that protects us; never rewrite a
  whole clause when a phrase will do. Prefer our paper and our fallback ladder.
- Firm but commercial. Always give the deal owner the **business rationale** and
  a fallback, not just a "no".
- **Escalate to the General Counsel** for: any uncapped Zendesk liability; a
  liability cap above 2x annual fees; assignment of our platform IP; regulated /
  personal data processed without a DPA; a non-standard governing law; or any
  departure from a house position without a documented business reason.
- The business owns the commercial risk; legal advises, flags and escalates.
"""

# --- a small MSA on Zendesk's own paper (we are the Provider) ------------------

_ZENDESK_MSA_FILENAME = "Zendesk-Northwind-MSA.txt"

_ZENDESK_MSA_SECTIONS: list[tuple[int, str]] = [
    (
        1,
        '1. Parties and Service. This Master Services Agreement (the "Agreement") '
        'is between Zendesk, Inc. (the "Provider") and Northwind Retail, Inc. '
        '(the "Customer") for the Provider\'s customer-service software provided as '
        'a hosted service (the "Service").',
    ),
    (
        1,
        "3. Data Protection. The Provider processes Customer Personal Data solely "
        "as a processor on the Customer's documented instructions. The Data "
        "Processing Addendum is incorporated by reference, and international "
        "transfers are made under the Standard Contractual Clauses.",
    ),
    (
        2,
        "7. Limitation of Liability. Except for liability arising from a breach of "
        "confidentiality, either party's indemnification obligations, or a breach "
        "of the Data Protection obligations, each party's aggregate liability "
        "under this Agreement shall not exceed the total fees paid by Customer in "
        "the twelve (12) months immediately preceding the event giving rise to the "
        "claim. Neither party shall be liable for any indirect, incidental, or "
        "consequential damages.",
    ),
    (
        3,
        "12. Governing Law. This Agreement is governed by the laws of the State of "
        "California, and the parties submit to the exclusive jurisdiction of the "
        "state and federal courts located in San Francisco, California.",
    ),
]


def build_zendesk_msa() -> FixtureDocument:
    """The Zendesk-as-Provider MSA fixture (mutual 12-month cap in § 7)."""
    return build_document(_ZENDESK_MSA_FILENAME, _ZENDESK_MSA_SECTIONS)


# --- the A/B scenarios --------------------------------------------------------
#
# SUPPLIER_UNCAPPED is the headline A/B: run OFF then ON. With the house context
# the agent should know we are the SUPPLIER, hold the house cap position, and
# escalate the uncapped demand to the GC — none of which it can know from the
# document alone. CUSTOMER_PROCUREMENT runs ON only: it shows the posture FLIP
# (we are the buyer) and the DPA reflex, both house-derived.

SUPPLIER_UNCAPPED = Scenario(
    id="supplier_uncapped_liability",
    title="Customer demands uncapped supplier liability (we are the supplier)",
    note=(
        "C-CLIENT (ADR-F030): the company tier should make the agent act FOR "
        "Zendesk — recognise we are the Provider, hold the house cap position, "
        "and escalate an uncapped-liability demand to the GC. None of that is in "
        "the document; it can only come from the injected house context. A/B: "
        "OFF vs ON."
    ),
    prompt=(
        "We are Zendesk, the Provider on the Northwind MSA in this matter. "
        "Northwind's redline deletes the Section 7 liability cap entirely, so our "
        "liability to them would be uncapped. What is our position, and what "
        "should we do next?"
    ),
    expect_tools=("search_documents",),
    step_bound=12,
    must_include=("liability",),
)

CUSTOMER_PROCUREMENT = Scenario(
    id="customer_procurement_dpa",
    title="We are buying a vendor tool (posture flip + DPA reflex)",
    note=(
        "C-CLIENT (ADR-F030): with the house context the agent should FLIP — "
        "recognise that here Zendesk is the CUSTOMER, push for vendor "
        "accountability, and require a DPA because the vendor will process "
        "personal data. Run ON only; a finding, not a pass/fail."
    ),
    prompt=(
        "Separately in this matter, we are buying a vendor tool, SecureScan, to "
        "scan our support tickets for threats. SecureScan will process our "
        "customers' personal data. Their order form caps SecureScan's total "
        "liability at three months' fees and includes no data-processing terms. "
        "What should we push back on before we sign?"
    ),
    expect_tools=(),
    step_bound=12,
)
