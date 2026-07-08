# B-2a live verification — org-skill harness end to end

2026-07-08, dev stack, REBUILT api/arq-worker/ingest-worker (migration 0091 applied on boot —
`Running upgrade 0090 -> 0091, org_skill_versions` in the api log). Lead-authored API probe
(never committed); throwaway admin `b2a-probe-admin@example.com` minted for the run and swept
afterwards; every probe artifact (user skill, versions, Library adoption, area, binding, matter)
created and removed in the same session.

## Result: PASS — the milestone's live proof

Author → propose → approve → adopt → bind → run, as one uninterrupted API sequence:

| Step | Result |
|---|---|
| POST /user-skills (author a personal skill) | 201 |
| POST /user-skills/{id}/propose | 201 — state `proposed`, content hash recorded |
| POST /admin/org-skills/{id}/approve | 200 — state `approved` (self-approval, audited) |
| POST /admin/library {kind: skill} (adopt) | 204 |
| POST /practice-areas + bind the org slug | 201 / 204 — bind accepts the approved org slug |
| POST /projects (matter in the area) | 201 |
| POST /agents/runs → real Deep Agent run | 202 → **completed** (4 steps, 22,329 tokens, ~8 s) |

The agent listed its skills, read the org skill through the read-only skill backend, and quoted
back — verbatim in the settled transcript:

> Provenance: org-authored by b2a-probe-admin@example.com, approved by
> b2a-probe-admin@example.com on 2026-07-08 — your company's own material, not LQ-shipped.

followed by the snapshot body's marker instruction. That is the ADR-F067 D3.5 banner rendered at
serve time from the immutable snapshot — the model saw the org provenance at the point of use.

Also proven live in the same session (probe iterations): **revoke** (200, version leaves the
adoptable set), the **unconfigured-area guard** (matter creation 400s until the area has
`profile_md`), and the full teardown path (unbind/delete area/remove adoption/revoke/delete
skill).

## Notes

- Two early probe iterations failed on PROBE assertions, not product behavior: the bind endpoint
  returns 204 (probe expected 201), and a matter cannot file under an area without `profile_md`
  (the F1-S3 inert-area guard — the probe's area was initially bare).
- Deterministic gate (same head): full containerized api suite from a `git archive` tree —
  **3516 passed / 1 failed / 42 skipped**, the single failure being the `test_openapi` path-count
  pin (176 → 182 for the six new routes); after the pin update the four touched modules re-ran
  **74 passed / 1 skipped**. Effective: **3517 passed / 42 skipped / 0 real failures**.
- Probe sweep: `org_skill_versions` probe rows and the throwaway admin removed by SQL after the
  evidence capture (immutable versions have no delete endpoint by design); audit rows remain with
  a NULL user per the FK's SET NULL — the audit trail is append-only.
