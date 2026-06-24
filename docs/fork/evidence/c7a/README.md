# C7a — redline-download surface evidence (ADR-F046)

## Cockpit Documents tab (headed Cypress, `c7a-documents.cy.ts`, 2/2)

`c7a-documents-{wide,narrow}-{light,dark}.png` — the Documents tab on a real (Privacy) matter,
proving the **all-areas placement** (Documents sits beside Conversation/Memory). Each file row
shows name, size, time, and a Download button; the agent's `(redlined).docx` carries a **Redline**
badge. The download round-trip is asserted in the spec (button → `GET /files/{id}/content`).

## Live end-to-end (real DeepSeek redline on the Atlas matter, 2026-06-24)

A real agent redline run on the seeded Atlas Commercial matter
(`905720d1-5d17-43cd-a8f0-3a76d095de34`), run `b588d8f8-4693-4664-b256-82b2c6694d22`:

- run `status=completed`; final answer: "saved as **02_Cirrus-Analytics-MSA-Draft (redlined).docx**".
- `GET /api/v1/matters/{atlas}/files` then returned the new output with
  **`created_by_run_id = b588d8f8-…`** (the run id) — every uploaded file has `created_by_run_id = null`.

This proves the full chain through the **rebuilt arq-worker**: agent redline → persisted as a
matter `File` with run provenance → surfaced by the new listing endpoint, which feeds both the
Documents tab and the inline run-timeline download (filtered to `created_by_run_id === run.id`). A
nonexistent/cross-user matter returns **404** (owner-scoped, no existence leak).
