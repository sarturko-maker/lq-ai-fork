# Scenario B — Project Meridian (inbound redlines, multi-attachment, round-2)

**Status:** design, held **for later** (needs C2 + C4 + C5; layers on top of Scenario A). Synthetic/illustrative
— NOT real positions. The heavier, multi-turn counterpart to Scenario A.

## One-liner

A regulated enterprise customer has **already redlined** Zendesk's paper and sent it back as an email chain with
a pile of attachments. The agent ingests the chain + attachments (**C1/C2**), triages signal from noise, fans
out subagents to **extract the counterparty's revealed positions** (**C5**), reconciles them against the house
playbook, **checks in** with the human on the business-vs-legal split, and produces **surgical tracked-changes
redlines via Adeu** (**C4**) — round-2 of a live negotiation. Adeu can handle it, but with heavy work, which is
why this is Scenario B, not the first thing to run.

## Deal setup

**Customer:** "Meridian Bank" — regulated, high compliance bar, board-visible. **Deal:** Zendesk Suite
Enterprise + Advanced AI for ~5,000 agents, 3-year term + implementation services. **Zendesk = supplier on its
own paper**, but Meridian's outside counsel returned heavy redlines. (Hits the C-CLIENT **supplier-side** house
posture: uncapped = hard no → GC; DPA mandatory.)

## Inbound email

Deal-desk AE → Legal: "Strategic logo, board-visible, sign by quarter-end; their counsel is aggressive on
liability and data residency — can you turn the redlines today?" — **plus a forwarded chain** showing the prior
commercial back-and-forth.

## Attachments (signal vs noise, round-2)

| Bucket | File | Format |
|---|---|---|
| **Directly relevant** | Meridian's **redlined MSA** (tracked changes) | `.docx` |
| **Directly relevant** | Redlined **DPA + SCCs** | `.docx` |
| **Directly relevant** | **Order Form** | `.pdf` |
| **Directly relevant** | **SLA exhibit** (99.99% uptime + uncapped service-credit demand) | `.xlsx` |
| **Context** | Requirements **deck** | `.pptx` |
| **Context** | **Security questionnaire** | `.xlsx` |
| **Context** | Prior **email chain** | `.eml` / `.msg` |
| **Noise** | Signed **NDA** from 8 months ago | `.pdf` |
| **Noise** | Product **one-pager** / unrelated **invoice** | `.pdf` |

## What it forces the agent to do → slice coverage

1. **Ingest** every format incl. the **email chain + attachments** → C1 + **C2** (threading, `.msg`, one-level
   attachment recursion).
2. **Triage** 9 attachments; fan out a subagent **per directly-relevant doc** → **C7** (deepagents `task`
   fan-out) + post-fan-out reconciliation.
3. **Build deal context** (supplier side, regulated counterparty) → **C3**.
4. **Extract + classify the counterparty's redlines** accept/reject/counter against the playbook tier; their
   tracked-changes `.docx` = their revealed position → **C5** (the core thing A does NOT do).
5. **Check in — two distinct types:**
   - **Legal hard-stop → GC:** deleted mutual liability cap (uncapped) + unlimited data-breach liability →
     house = hard no, escalate (the `escalation-required` gate).
   - **Business decision → deal owner:** 99.99% SLA with uncapped service credits; 3-year price lock — not a
     legal call; surface, don't decide.
6. **Redline surgically** — counter the cap deletion (restore the clause + 2× super-cap), require/repair the
   DPA, narrow the on-site audit to a SOC 2 report — via **Adeu** tracked changes (**C4**), downloadable
   `.docx` (**C7**).

## Why later (vs Scenario A)

B depends on the inbound-redline machinery that doesn't exist yet: the `.eml`/`.msg` email-chain reader (C2),
counterparty-position extraction (C5), the Adeu tracked-changes tool (C4), fan-out + download surface (C7), and
deal-context accumulation (C3). Scenario A proves the buy-side posture + multi-format ingest **now**; B is the
round-2, multi-turn proof once those land. The full multi-turn redlining system is the maintainer's separate
held follow-on (COMM plan, decision H) — B is its first end-to-end scenario, not the whole system.
