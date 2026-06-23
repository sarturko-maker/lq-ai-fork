# C3c-2 evidence — cockpit matter-memory panel

Live verification for COMM C3c-2 (the frontend over the C3c-1 read/revert backend, ADR-F042/F044).

## Real-stack smoke (rebuilt dev `api`)

After rebuilding `api` + `arq-worker` + `ingest-worker` (no migration — head stays `0070`), the C3c-1
endpoint is live and returns the exact composite the frontend types expect:

```
POST /api/v1/auth/login (admin@lq.ai)                          → 200, access_token
GET  /api/v1/matters/47519e68-…-2d703c16229c/memory            → HTTP 200
     keys: corrections, facts, log, log_total, project_id, wiki
     wiki keys: char_count, content_md, version_count
     (seeded Privacy matter has empty memory: facts/corrections/log = 0, version_count = 0)
```

## Headed Cypress (live web at :3000, rebuilt bundle)

`web/cypress/e2e/c3c2-matter-memory.cy.ts` — **2 passing / 0 failing** (Electron, headed):

1. **render + revert** — drives the seeded Privacy matter (proves the "all matters, any area" decision:
   a Privacy matter gets a Memory tab *alongside* its ROPA register), with the composite GET + revert POST
   intercepted for deterministic content. Asserts the four sections render (Working summary / Facts (2) /
   Pinned corrections (1) / Activity (7) + the "most recent of 7" tail note), then clicks "Restore this
   version" → confirm Dialog → confirm → asserts the revert POST body `{snapshot_id}`, the dialog dismisses,
   and the panel refetches the composite.
2. **capture** — the screenshot matrix below.

## Screenshots (light/dark × wide/narrow)

- `c3c2-memory-wide-light.png` / `c3c2-memory-wide-dark.png` — at wide width a Privacy matter shows the
  **Conversation | Memory** strip (the ROPA register is co-visible in the conversation view); the Memory
  panel renders the markdown wiki (bold/italic/list), typed facts with `fact_type` badges + provenance, and
  the pinned correction.
- `c3c2-memory-narrow-light.png` / `c3c2-memory-narrow-dark.png` — stacked/narrow shows the full
  **Conversation | ROPA register | Memory** strip; the panel renders full-width-stacked. Dark mode uses the
  `dark:prose-invert` parity on the charcoal canvas.

All model-authored bodies render through `renderModelMarkdown` (DOMPurify, media-forbid) — never raw `{@html}`.
