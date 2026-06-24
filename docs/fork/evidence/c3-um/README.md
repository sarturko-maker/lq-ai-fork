# C3-UM — human "update memory" UX evidence

The three human gestures layered on the C3c-2 read-only Memory panel (ADR-F042 / F044 §4B),
captured headed (electron) on the live dev stack via `cypress/e2e/c3-update-memory.cy.ts`.

- **`c3-um-affordances-{light,dark}.png`** — the panel with the new affordances: a
  `+ Pin a correction` button in the Corrections header, quiet `Correct` + `Retire` actions
  on each Fact row, and a `Retire` action on the pinned correction (beside its brand rail).
- **`c3-um-composer-{light,dark}.png`** — the inline pin composer open (textarea + a
  `N/4,000` char counter + Cancel / Pin correction).

The Cypress run also exercises the full functional flow (not screenshotted): pin a correction
→ correct-a-fact pre-fills the composer with a `Re: "…" →` stub → retire a correction (confirm
dialog) → retire a fact (confirm dialog). Writes are intercepted so the panel is deterministic;
the disabled-while-a-run-is-active gate is host-driven and is covered by the `canWrite` unit test.

## Live real-stack smoke (api on :8000, Atlas matter `905720d1-…`)

Proven end-to-end against the live API (not the test DB), 2026-06-23:

| step | result |
|---|---|
| `POST .../memory/corrections` (pin) | **201** |
| `POST .../memory/corrections/{id}/retire` | **200**, dropped from live corrections |
| `POST .../memory/facts/{id}/retire` (throwaway past-dated fact) | **200**, dropped from live facts |
| retire again (idempotent) | **200**, same `retired_at` |
| fact id via the corrections route (cross-kind guard) | **404** |
| final Atlas state | 5 live facts + 1 live correction (intact); append-only log preserved (log_total 9→11) |

The 409 future-dated-fact reject (closing a window before it opens would violate the
`invalid_at > valid_at` CHECK) is covered deterministically by `test_retire_fact_future_dated_is_409`.
