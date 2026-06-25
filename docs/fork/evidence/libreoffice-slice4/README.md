# Evidence — in-app Word editor, Slice 4 (ADR-F047)

The cockpit Editor panel: the lawyer opens an agent-redlined `.docx` **in the cockpit**, it renders in a
reskinned Collabora iframe, and edits save back through the Slice-3 WOPI PutFile. Captured live (headed
Cypress, real stack + the `collabora` container) against the admin-owned **Atlas** matter's real agent
redline (`02_Cirrus-Analytics-MSA-Draft (redlined).docx`).

## The asset-URL blocker — solved (the Slice-1 open question)
Probed live: `cool.html` references every asset by an **absolute root path** (`/browser/<hash>/bundle.css`,
…) and the editing websocket connects to `/cool/<wopisrc>/ws` (`data-service-root=""`). So Slice-1's
`/collabora/` sub-path could never serve the iframe. Fix = host Collabora at its **native root paths** in
nginx (`/browser/`, `/cool/`, `/hosting/`, no strip; admin-404 regex still wins) + `ssl.termination=false`
for HTTP dev (→ `data-host="ws://…"`) + the frontend re-homes the discovery `urlsrc` pathname onto
`window.location.origin`. Verified through the proxy: discovery `urlsrc` is `http://…/browser/<hash>/cool.html`,
`bundle.js`/`bundle.css` 200, `cool.html` 200, admin paths (`/cool/adminws`, `/cool/getMetrics`,
`/browser/<hash>/admin`) all 404, SPA `/` + `/lq-ai/login` 200.

## Screenshots
- `slice4-editor-wide-light.png` / `slice4-editor-wide-dark.png` — the conversation-left / editor-right
  layout, the practice-area rail **collapsed**, the agent redline rendered with tracked changes + the
  agent's margin comments ("Make indemnity mutual…", "Extend cap from 1 month to 12 months…"). The editor
  is reskinned to a clean **classic** toolbar with **no properties sidebar / no ruler** (via WOPI
  `ui_defaults`) — not Collabora's default notebookbar ribbon.
- `slice4-editor-narrow-light.png` / `slice4-editor-narrow-dark.png` — usable at 1024px (the heavy ribbon +
  sidebar would have crushed this; the slim toolbar fits).
- `slice4-roundtrip-saved.png` — after an in-editor edit + save: the marker text is in the document, and
  the menubar is **hidden** (the best-effort `Hide_Menubar` postMessage engaged on this cold load).
- `slice4-editor-closed.png` — Close slides the editor away, **restores** the rail, and brings back the
  thread list + single-pane conversation.
- `slice4-auto-open.png` — the **auto-open** regression (deterministic, intercepted): a redline appearing
  after the conversation is open slides the editor in **with no Edit click** (chrome shows the redline
  filename beside the live conversation). The iframe shows a 404 here because this test stubs discovery at a
  non-existent doc — the point is the panel auto-opening; real rendering is the screenshots above.

## Round-trip — proven at the DB (edit → save → snapshot-then-mutate)
Drove a real edit (Collabora `Action_Paste`) + save (`Action_Save`) through the loaded editor, then read the DB:

| | before | after |
|---|---|---|
| live redline hash | `b1fe5b36…` | `7b0366d8…` (edit persisted) |
| live `created_by_run_id` | agent (set) | NULL (now human-authored) |
| live `updated_at` | null | set |
| `(agent draft)` snapshot | 0 | 1 — `…(redlined) (agent draft).docx`, hash `b1fe5b36…` (original agent bytes preserved, provenance kept → C7a Documents) |
| `editor.file_saved` audits | 6 | 7 |

Exactly the ADR-F047 Slice-3 snapshot-then-mutate, driven from the cockpit editor UI.

## UX judgement (maintainer mandate)
**Layout — ships the maintainer's spec exactly.** When the agent redlines (or the lawyer clicks *Edit* on a
`.docx` in Documents), the editor slides in from the right, the conversation stays on the left, and the
practice-area rail gracefully collapses — so the lawyer edits the document while still talking to the agent
(the round-2 hand-back loop). Close reverses it. The conversation never remounts (live SSE preserved). This
feels right: document-focused without losing the agent.

**Reskin — clean, with an honest residual.** The two heaviest, most-branded Collabora elements (the
notebookbar ribbon and the properties sidebar) are gone reliably via `ui_defaults`, leaving a slim classic
toolbar under our own charcoal chrome (filename · save-state · Close). Two residuals, both documented as the
**incremental** de-branding follow-up (ADR-F047): (1) Collabora's thin menubar + the save-state pill are
hidden/driven by postMessage, whose one-shot `App_LoadingStatus` races the host handshake — reliable on a
real cold open, ~50/50 under rapid automation (degrades gracefully: menubar shows, chrome stays clean); (2)
the toolbar keeps Collabora's blue accent — charcoal theming via `css_variables` is deferred. Neither blocks
the core: a lawyer can open, read the redline + comments, edit, and save.

## Reproduce
```
cd web && DISPLAY=:0 npx cypress run --headed --browser electron \
  --spec 'cypress/e2e/libreoffice-editor.cy.ts' --env LQAI_ADMIN_PASSWORD=LQ-AI-local-Pw1!
```
(Needs the stack + the `collabora` container + a redline `.docx` in the Atlas matter. Not a CI gate — CI runs
svelte-check + Vitest only.)
