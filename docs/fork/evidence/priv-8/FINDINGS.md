# PRIV-8b — live ROPA *maintenance*: "we moved off Mixpanel, we use Hotjar now"

**Date:** 2026-06-19 · **Milestone:** PRIV-8b · **ADR:** F023 (change verbs / soft-retire) · F015 (report,
not gate) · **Model:** DeepSeek V4 via the gateway (`deepseek` → deepseek-v4-flash, `deepseek-pro` →
deepseek-v4-pro). DeepSeek is **not** scenario-qualified — this is qualification data, kept verbatim, **not
tuned green**.

## Headline

**The product thesis works.** Hand the Privacy Deep Agent a plain-language ask — *"We've moved off Mixpanel
— we use Hotjar now for our product analytics. Please update our Record of Processing Activities"* — and,
**with the `ropa-maintenance` skill**, it composes the PRIV-8a change verbs into a **coherent, complete,
audited swap**: Hotjar added + linked, Mixpanel unlinked **and soft-retired** (kept on record), and a clear
receipt of exactly what changed. Both skilled arms (flash and pro) did this, completed inside budget, and
reported back.

**The skill is load-bearing.** The no-skill baseline — given *more* budget — wandered and left the register
listing **both** Mixpanel and Hotjar as recipients of the activity (the exact ADR-F023 failure mode the skill
exists to prevent). Capability + method, not capability alone.

## The run

Synthetic register (no third-party material): `seed_ropa_register` plants a *Product analytics* activity with
a **Mixpanel** vendor (US processor, DPA in place) and a **Mixpanel** analytics system, both linked. One
plain-language prompt, held constant across arms; the only variables are the skill and the model. Coherence
is scored from the live register by `evaluate_swap` (a row is "live-visible" on the activity iff it is linked
AND not retired — mirroring what the API serves). Per ADR-F015 the test asserts only that each run is honest
(terminal + a model turn); the swap's coherence is this recorded finding, not a pass/fail gate.

`max_steps=80`. (A first pass at 40 hit `cap_exceeded` on every arm with an **empty final answer** — the model
spent early steps reading the matter note, then ran out before retiring + reporting. 80 gives a single-pass
swap clear headroom; see *Budget* below.)

## Controlled comparison (canonical run, max_steps=80)

| Arm | Model | Skill | Status | Steps / turns | Verdict | Live register (activity) | Mixpanel kept on record |
|---|---|---|---|---|---|---|---|
| `swap-deepseek-noskill` | flash | off | `completed` | 72 / 16 | ⚠️ **lists BOTH** | recipients `[Hotjar, Mixpanel]`, systems `[Hotjar]` | system retired; **vendor left live + linked** |
| `swap-deepseek-skill` | flash | **ropa-maintenance** | `completed` | 53 / 9 | ✅ **coherent** | recipients `[Hotjar]`, systems `[Hotjar]` | vendor + system **soft-retired** (with reason) |
| `swap-deepseek-pro-skill` | pro | **ropa-maintenance** | `completed` | 47 / 9 | ✅ **coherent** | recipients `[Hotjar]`, systems `[Hotjar]` | vendor + system **soft-retired** (with reason) |

Both before-states: recipients `[Mixpanel]`, systems `[Mixpanel]`. Nothing was ever destroyed — the retired
Mixpanel rows remain in the register under `include_retired` (auditable), exactly as the maintainer required.

## What the skill does (the lever)

Both skilled arms executed the full textbook sequence in one pass and stopped:

`list_* (orient) → propose_vendor + propose_system (Hotjar) → link ×2 → unlink_vendor/system_from_activity
(Mixpanel) → retire_vendor + retire_system (Mixpanel, with a reason) → list_* (confirm) → report`.

The flash+skill arm's own receipt: *"Added Hotjar (processor, Malta) — DPA status pending (I don't have the
actual status… see flag below); … Unlinked Mixpanel … Retired Mixpanel vendor — company-wide removal, kept on
record for audit with reason 'Replaced by Hotjar for product analytics'."* That is the honest-receipt UX the
group chat asked for — including **flagging the unknown DPA status as an assumption** rather than inventing it.

## The baseline failure (honest)

`deepseek-noskill` used the most budget (72 steps, 16 turns) yet produced the **incoherent** result. It
unlinked + retired the Mixpanel *system* correctly, but for the *vendor* it (by its own final answer)
*"attempted unlink and retire (a record issue prevented the retire)"* and left it **live and linked** — so the
activity ends up listing both Mixpanel and Hotjar as recipients. It also wandered into unprompted work
(`add_data_subject_categories` / `add_data_categories`) and re-tried `retire_vendor`. This is precisely the
"register lists both" mistake ADR-F023 names and the skill's *"never leave both"* rule prevents.

## Budget (the second lever — confirms the PRIV-7 finding)

| max_steps | Skilled arms | Baseline |
|---|---|---|
| 40 (first pass) | unlinked, **but** `cap_exceeded` before `retire` + report (empty final answer) | `cap_exceeded`, incomplete, oddly-named system |
| 80 (canonical) | `completed`: full add→link→unlink→**retire**→confirm→**report** | `completed` but **lists both** |

A swap is small (~15–20 tool calls), but the agent spends real steps orienting (reading the matter note,
listing the register) before it writes. 40 was too tight for swap **and** report; 80 is comfortable. (The
PRIV-7 `recursion_limit = max(50, max_steps*4)` fix lets the budget actually be spent.)

## Honest caveats (ADR-F015)

- **One observation per arm.** Provider runs are non-deterministic; these are single data points, kept
  verbatim, not retried-until-green. Re-runs may differ — particularly the baseline.
- **DeepSeek is not scenario-qualified.** This is its first maintenance-swap data point, not a qualification
  decision.
- **The synthetic register is deliberately minimal** (one activity, one vendor + system). A real swap may
  touch several activities and transfers; the skill teaches "link the replacement to *each* affected activity"
  but that breadth is untested here (follow-up: a multi-activity swap fixture).
- **Hotjar `dpa_status=pending`, `country=Malta`** are the model's defensible assumptions (flagged in its
  receipt), not ground truth — the seed gives no Hotjar facts. Correct behaviour, but a reader must treat them
  as drafts.
- **The baseline's "record issue"** that blocked the vendor retire was self-reported, not reproduced/diagnosed
  here. It did not corrupt anything (the run completed; nothing was destroyed); it is noted, not fixed.

## Recommendations / follow-ups

- **Ship `ropa-maintenance` via a binding migration** (the 0056 pattern), alongside `ropa-population` —
  both are now proven; bound test-only today. (Backlog item already exists for ropa-population.)
- **Multi-activity swap fixture** — extend `seed_ropa_register` to link the old tool to ≥2 activities and
  assert the skilled agent unlinks/relinks *each*.
- **Parallel-tool-call deadlock (PRIV-7 HIGH, still open)** touches the same guarded path; the swap runs are
  serial here, but a real concurrent run could hit it.
- **PRIV-9 (cockpit UX)** is the natural next slice: make the chat + register co-visible and poll-while-running
  so a user *watches* this swap happen — the side-panel idea behind the original request.

## Evidence files

`swap-deepseek-noskill/`, `swap-deepseek-skill/`, `swap-deepseek-pro-skill/` — each `behavior-report.json`
(machine) + `behavior-report.md` (human): the verdict, the per-axis table, the run receipt, and the register
before→after. Observations + the agent's own output only — no provider key/URL; the prompt + matter note are
synthetic (committable).
