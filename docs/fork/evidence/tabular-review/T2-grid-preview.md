# F2 Tabular T2 — in-chat grid preview + Expand (ADR-F055)

The cockpit now surfaces a finalized grid as a **durable preview card** in the
conversation, with an **Expand** button that opens the full, reused `TabularGrid`
in an in-conversation overlay. T1 was headless (the grid persisted and rendered
only at `/tabular/[id]`); T2 makes it visible in chat.

## Design (refines the T2/ADR-F055 wording)

The SSE replay path (`api/app/api/agent_runs.py:_stream_run_events`) re-emits only
settled `data-step` rows — custom `data-*` frames (`data-plan`, `data-deal-change`)
are **live-only** and never survive a reload. A grid is a durable artifact, so its
preview must re-derive on reload. Therefore T2 anchors the card on the **settled
`finalize_tabular_review` step** already in the run timeline (its tool-call input is
a short `{"grid_id": "<uuid>"}` digest, well under the ~2000-char summary cap), and
fetches the body from the existing owner-scoped `GET /tabular/executions/{id}`. This
makes T2 **frontend-only** — no `stream.py` change, no new wire frame — and the card
renders identically live and on reload (ADR-F004). The maintainer signed this off
(2026-07-01): *preview source = "Derive from settled step"; Expand = "Inline overlay
in chat"*.

## Browser render — `T2-cypress/` (deterministic, no LLM)

`web/cypress/e2e/f2-tabular-t2-grid-preview.cy.ts` drives the REAL component code
path in the REAL browser: the thread detail is intercepted to return a COMPLETED
run whose steps include a `finalize_tabular_review` tool call, and
`GET /tabular/executions/{id}` is intercepted with a completed agentic grid (the
three NDAs of the T1 live evidence — distinct Term / Governing-law per doc). The
spec asserts the card derives + renders and then expands, and captures four shots:

- `f2-tabular-t2-preview-card.png` — the card: **GRID · 3 documents · 2 columns ·
  Ready**, column pills (`Term`, `Governing law`), and the compact mini-table,
  rendered after the answer.
- `f2-tabular-t2-preview-light.png` / `-dark.png` — the card in conversation context
  (light + dark).
- `f2-tabular-t2-expanded.png` — **Expand** → the full reused `TabularGrid` in an
  in-conversation overlay: Document / Term / Governing law headers, all three NDA
  rows with correct values + `high` confidence chips, sticky columns, close button.

Run:

```
cd web && DISPLAY=:0 npx cypress run --browser electron \
  --spec 'cypress/e2e/f2-tabular-t2-grid-preview.cy.ts' \
  --env LQAI_ADMIN_PASSWORD=...
```

Result: **1 passing**, 4 screenshots. (The same render fires live on DeepSeek —
the T1 live run already produced exactly this grid; see `T1-live-grid.md`.)

## Known cosmetic (deferred to T6)

At rest, the cockpit composer ("Continue the conversation") floats over the bottom
of the conversation, so a *tall* trailing artifact — the grid card — has its
mini-table partly behind the composer until the user scrolls up (the card header,
status, and pills stay clear; Expand is unaffected). This is a pre-existing layout
trait of any tall trailing content, not introduced by T2; the T6 stage-takeover
("panels slide back, grid takes the stage") reworks this region and is the right
place to address it.
