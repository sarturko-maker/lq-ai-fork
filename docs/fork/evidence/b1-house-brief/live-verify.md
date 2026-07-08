# B-1 live verification — House Brief page + degraded-binding chip

2026-07-08, dev stack, against the REBUILT web container (prebuilt-bundle rule). Lead-authored
Cypress probe (never committed); all probe state (throwaway `b1-cy-admin` user, probe practice
area, probe Library adoption, House Brief content) created and removed inside the same run —
net-zero verified in SQL afterwards (no probe area row, no probe library row, brief back to
baseline).

## Result: 3/3 passing

| Check | Result |
|---|---|
| House Brief page: type a marker draft → live preview renders it → Save → **intercepted `PUT /organization-profile` returns 200 with the typed draft as `content_md`** → "Last updated … by …" renders → reload → textarea shows the persisted marker → original restored | PASS (`b1-house-brief-saved.png`) |
| Teaching empty state renders on an empty brief (explains the House Brief tier, ADR-F049, in-house vocabulary) | PASS (`b1-house-brief-empty-state.png`) |
| Degraded chip: adopt an unadopted skill → create probe area → bind it → **remove it from the Library** → area page shows the amber chip "Not in your Library — the agent will not receive this. Adopt in Store." → **re-adopt** → chip clears | PASS (`b1-degraded-chip.png`, `b1-chip-cleared.png`) |

## Notes

- An earlier probe iteration failed on the save test because `cy.reload()` raced the in-flight
  PUT (no explicit wait) — a probe artifact, not a product bug; the page shows saving/saved
  states to a human. The final probe asserts the PUT round-trip explicitly via `cy.intercept`.
- The raw `GET /admin/capabilities` entries carry `capability_key` (the web client projects it
  to `key`); the probe's Library calls use the raw field.
- `updated_by` renders the raw user id (endpoint has no user-name join) — known minor, deferred
  on the PR.
