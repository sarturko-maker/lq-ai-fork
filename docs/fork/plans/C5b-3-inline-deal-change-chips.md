# Plan — COMM **C5b-3**: inline `data-deal-change` live verdict chips

## Context

C5a/C5b-1/C5b-2 shipped the **provable round-2 negotiation loop**: the Commercial agent reads the
counterparty's marked-up `.docx` (`extract_counterparty_position`) and responds to **every**
change/comment (`respond_to_counterparty`) under a code-enforced no-silent-action gate, with a curated
`negotiation-review` craft skill. The work product (the response `.docx` + per-item verdicts) is
persisted, audited, and downloadable (C7a) — but the verdicts are only visible **after the fact**, by
opening the saved document. C5b-3 adds the **live signal**: as the agent responds, the cockpit flashes a
transient **verdict chip per item** inline in the conversation ("C1 · accepted", "C3 · countered",
"Com:1 · escalated"), so the lawyer *watches the negotiation round happen* (the C5 "watch it happen"
analogue of PRIV-9b's changed-row highlight).

This **clones the `data-ropa-change` seam** (PRIV-9b, ADR-F024) — the run-scoped ledger → runner drain at
`tool_result` → transient `data-*` SSE frame → web parse → render. The one structural divergence: ropa
renders as a **register-row wash** in a co-visible panel (reached by hoisting ids to `ConversationHost`);
Commercial has **no deal-terms panel**, so the deal-change clone renders a **transient chip inline in the
conversation**, inside `ConversationPanel` itself (no host dispatch, no panel).

**Seam generalization (the one architectural call).** This is the *second* consumer of the identical
ledger→drain→frame seam, and `composition.py:399-402` already anticipates a *third* (the assessment
register). Rather than thread a parallel second ledger param through `_drive_agent` / `execute_agent_run`
/ composition (duplication), generalize the seam: a tiny `LiveChange` / `ChangeLedger` **Protocol** where
each change knows how to publish itself. The runner drain becomes area-agnostic
(`for change in change_ledger.drain(): change.publish(publisher)`); `RopaChange` gains a 2-line `publish`;
`DealChange` is the second implementer. Privacy blast radius is minimal and fully covered by existing ropa
tests. Documented as an addendum to ADR-F024 (the ledger-seam ADR) + a C5b-3 note on ADR-F032.

**No new dependency, no new HTTP endpoint, no migration, no runtime-gate change** (the C5a/C5b-1 gates are
untouched — the chip is pure animation; the saved `.docx` + run timeline remain the truth, ADR-F004).
The frame carries only `{ref, verdict}` — audit-safe (refs/types, never raw clause text).

## Deliverables

### Backend (`api/`)

1. **`app/agents/live_changes.py` (NEW, tiny)** — the shared seam contract:
   - `LiveChange` Protocol: `publish(self, publisher: RunStreamPublisher) -> None` (TYPE_CHECKING import,
     no runtime cycle).
   - `ChangeLedger` Protocol: `drain(self) -> Sequence[LiveChange]`.
2. **`app/agents/ropa_changes.py`** — add a 2-line `RopaChange.publish(publisher)` →
   `publisher.ropa_changed(kind=…, entity_id=…, verb=…)`. Fields + `RopaChangeLedger.record/drain` API
   **unchanged** (byte-identical for Privacy; existing ropa tests must stay green).
3. **`app/agents/deal_changes.py` (NEW, mirrors ropa_changes.py)** — `DealChange(ref, verdict)` frozen
   dataclass with `publish(publisher)` → `publisher.deal_changed(ref=…, verdict=…)`; `DealChangeLedger`
   with `record(ref, verdict)` + cursor `drain()`. Docstring states render-determinism + audit-safety.
4. **`app/agents/stream.py`** — `RunStreamPublisher.deal_changed(*, ref, verdict)` publishes the transient
   frame `{"type": "data-deal-change", "transient": True, "data": {"ref", "verdict"}}` (sibling to
   `ropa_changed`; `transient` ⇒ not seeded to late subscribers).
5. **`app/agents/runner.py`** — drain seam becomes area-agnostic: `change.publish(publisher)` (one line);
   type hints `change_ledger: ChangeLedger | None` in `_drive_agent` + `execute_agent_run` (drop the now
   wrong `RopaChangeLedger` import, import `ChangeLedger`).
6. **`app/agents/composition.py`** — `change_ledger: ChangeLedger | None = None`; in the
   `COMMERCIAL_AREA_KEY` branch create `DealChangeLedger()` and pass to `build_commercial_tools(...,
   change_ledger=...)`. It flows to the already-present `execute_agent_run(..., change_ledger=change_ledger)`.
7. **`app/agents/commercial_tools.py`** — `build_commercial_tools(..., change_ledger: DealChangeLedger |
   None = None)`; thread into `_respond_to_counterparty(..., change_ledger=…)`; **after `recon.ok` and the
   response is persisted + audited** (best-effort, end of the body, before the return), record each
   validated decision: `for d in proposal.decisions: change_ledger.record(ref=d.ref, verdict=d.verdict)`.
   Records **only on success** (a coverage/anchoring/recon rejection returns early → nothing recorded),
   mirroring ropa's "record only on a REAL change".

### Web (`web/src/lib/lq-ai/`)

8. **`agents/run-stream.ts`** — `DEAL_VERDICTS` (the closed taxonomy, mirrors
   `commercial_tools._RESPOND_VERDICTS`), `DealVerdict` type, `DealChangePayload {ref, verdict}`,
   `parseDealChangePayload(data)` (**both** `ref` and `verdict` load-bearing; reject if `verdict` ∉
   taxonomy → null → no chip), and pure presenters `dealVerdictLabel(verdict)` ("accepted"/"countered"/…)
   + `dealVerdictTone(verdict)` (`positive|negative|info|warning|neutral`). All pure → unit-tested.
9. **`components/agents/ConversationPanel.svelte`** — `case 'data-deal-change':` parses → `pushDealChip`
   into a local `recentDealChanges` list (dedupe by `ref`, last verdict wins; reassign for reactivity);
   a single decay timer (`DEAL_CHIP_DECAY_MS ≈ 6000`) clears all (mirrors `ConversationHost`'s
   reset-on-each-change decay). Cleared in `clearStreamState()` + `onDestroy`. Render a transient chip row
   inline in the last running turn (beside the thinking ribbon), one pill per chip
   (`{ref} · {dealVerdictLabel}`), colored by `dealVerdictTone` via existing intent tokens. `data-testid`
   on the row + each chip. No host dispatch, no `ConversationHost` change.

### Tests

10. **`api/tests/agents/test_deal_changes.py` (NEW)** — ledger record/drain once-each + cursor advance
    (mirror `test_ropa_changes.py`).
11. **`api/tests/agents/test_agent_stream.py`** — `test_publisher_deal_changed_emits_transient_data_frame`
    + `_is_not_seeded_to_late_subscribers` (mirror the ropa pair).
12. **`api/tests/agents/test_agent_stream_redis.py`** — `test_deal_change_frame_survives_the_round_trip`.
13. **`api/tests/agents/test_agent_runner.py`** — a deal-change drain test: a `DealChangeLedger` recorded
    in a tool body → runner emits `data-deal-change` parts (mirror the ropa drain test; also proves the
    polymorphic `change.publish` dispatch).
14. **Commercial tool test** (existing negotiation tool test file) — `_respond_to_counterparty` records
    one ledger entry per decision on success, and records **nothing** on a coverage/anchoring/recon
    rejection.
15. **`web/.../agents/__tests__/run-stream.test.ts`** — `describe('parseDealChangePayload')` (valid;
    reject missing `ref`; reject missing/unknown `verdict`) + `dealVerdictLabel`/`dealVerdictTone` maps.
16. **`web/cypress/e2e/c5b3-deal-change.cy.ts` (NEW)** — intercept the run stream with a real
    `data-deal-change` SSE body, assert the inline chips appear (per ref + tone), light+dark screenshots
    (mirror `priv-9b-highlight.cy.ts`; rebuild the prebuilt `web` container first).

## Non-goals

- No deal-terms register/panel (the chip is the whole surface; transient, animation-only).
- No new gate / no change to the no-silent-action guarantee (C5a/C5b-1) — the ledger records only what
  already passed reconciliation.
- No new ADR — applies ADR-F032 (loop), ADR-F024 (ledger seam) + addendum (seam now area-agnostic),
  ADR-F004 (render-determinism). Cite in commit + the new modules.
- No raw clause text on the wire — only `ref` + `verdict` (audit contract).

## Verification (DoD)

1. Containerized api suite (dev-image, repo-root mounted) green, counts quoted; `ruff check`/`format`
   (CI-exact) + mypy clean. **All existing ropa tests stay green** (the seam generalization is
   behavior-preserving for Privacy).
2. Web: `npm run check` 0 errors; vitest (new parser/presenter tests) green; eslint + prettier clean on
   touched files.
3. **Live (DeepSeek, dev stack):** rebuild `api` + `arq-worker` + `ingest-worker` (agent runs in the
   worker) + `web`; drive the round-2 negotiation on a counterparty markup; **screenshot the live verdict
   chips** flashing inline. Evidence → `docs/fork/evidence/c5b3/`.
4. Headed Cypress 2/2 (light+dark) with the screenshot matrix.
5. Fresh-context adversarial + **security + simplification** pass on the diff. Update `docs/fork/HANDOFF.md`
   + a memory note. ADR-F024/F032 addendum. Squash-merge under the ADR-F005 gate.

## Recommended order

live_changes protocol + ropa.publish → deal_changes ledger → stream.deal_changed → runner drain +
composition wiring → commercial_tools record → backend tests → web parse/presenters + chip render → web
tests → live run + evidence → review/merge.
