# F047 — In-app Word editor via self-hosted Collabora Online over WOPI

- Status: proposed
- Date: 2026-06-25
- Deciders: maintainer (Arturs), agent
- Slice: libreoffice-editor Slice 1 (first of 6; the WOPI host + UI land in Slices 2–5)

## Context

The commercial agent's primary work product is a redlined `.docx` with native tracked changes
+ comments (C4/C8/C9, ADR-F031/F041/F045). Today the lawyer can only **download** it (C7a,
ADR-F046). The maintainer wants an **embedded editor**: agent redlines → the lawyer
views/edits/comments/exports the document **inside the tool** → hands it back so the agent
**resumes reading their markup** and continues negotiating. The agent already reads tracked
changes + comments (C5a/C5b: `extract_counterparty_position` / `respond_to_counterparty`), so
**no new agent capability is needed** — the editor is the missing UI.

Hard constraints (from CLAUDE.md + the maintainer): "only LibreOffice is acceptable", **local /
self-hosted, no SaaS**; the UI must match our Vercel design system (ADR-F013); strict
copyleft/licence posture (PyMuPDF's AGPL is the single grandfathered copyleft dep — no new
copyleft surprises); cross-user access → 404 not 403; provider keys live only in the gateway and
**every** LLM call routes through it (ADR-F010); retrieved/edited documents are untrusted input.

This decision is backed by a full research pass (`docs/fork/research/libreoffice-editor.md` — 9
research agents + 4 adversarial verifiers) and a throwaway **Spike 0** that returned **GO**
(`docs/fork/evidence/libreoffice-spike0/`): on the real engine (Collabora Office 26.04.1.4),
author `w:author` byte-strings survive a save verbatim (so the agent's `is_ours` discriminator
holds), the "remove personal info on save" strip is OFF by default, comments + multi-author
changes survive, there is **zero `<w:ins><w:del>` nesting even on the multi-pass case** (the
failure that sank the maintainer's earlier VibeLegalStudio project — our gate-against-clean-text
+ word-diff avoids it), and Adeu re-reads Collabora-serialised OOXML cleanly.

## Considered options

1. **Collabora Online / CODE, self-hosted, integrated over WOPI, reskinned via our Svelte chrome.**
   Collabora Online *is* LibreOffice running headless on LibreOfficeKit — it satisfies
   "only LibreOffice, local, no SaaS" and ships, already built, the per-document sandboxed engine,
   the tile protocol, the JS canvas client, and — decisively for a redline tool — the
   **tracked-changes + comment UI** that round-trips Word markup through the same LibreOffice core
   Adeu targets. Source is **MPL-2.0** (core dual MPL-2.0 / LGPLv3+), no AGPL.
2. **LibreOffice-WASM (ZetaOffice), fully client-side.** Best *potential* reskin, but the
   track-change round-trip is **unverified** in WASM, it ships a ~250 MB–1 GB MPL+LGPL payload to
   the browser (turning our clean server-side boundary into client distribution), and it mandates
   invasive COOP/COEP isolation of the web app.
3. **Custom build directly on LibreOfficeKit (LOK).** Total UI control, but reinvents Collabora
   (the WSD/ForKit/Kit/tile-cache/JS-client/comment-UI) as net-new C++ for **identical** licensing
   and strictly more cost, risk, and security-ownership.

## Decision outcome

**Chosen: option 1 — Collabora Online over WOPI, `api` as the WOPI host, reskinned via our Svelte
chrome.** This ADR governs the architecture; Slice 1 lands only the engine + its isolation +
licence record (the WOPI host, save-back, cockpit editor/reskin, and hand-back/resume are
Slices 2–5).

Slice 1 specifics:
- A new **`collabora` compose service** (Collabora Online / CODE), pinned **by digest** to the
  Spike-0-validated build, with **no host port** — reachable only over the private
  `lq-ai_default` network by `web` (the same-origin proxy) and able to reach `api` (the WOPI host,
  Slice 2). Sandbox uses `cap_add: [MKNOD]` only (no `privileged`/`SYS_ADMIN`). The WOPI host
  allow-list (`aliasgroup1`) is fixed to the `api` origin. **No gateway reachability** — the editor
  data plane never calls an LLM, so the ADR-F010 egress invariant is untouched.
- **Same-origin** hosting: the `web` nginx proxies `/collabora/` to the service (WebSocket-upgrade),
  **stripping the prefix** so coolwsd routes at its own root — the editor is served from our own
  origin, simplifying CSP and avoiding cross-origin/COOP-COEP. (Empirically, coolwsd **400s on a
  prefixed path** and `--o:net.proxy_prefix` does not change that, so the prefix is stripped at
  nginx; making coolwsd EMIT `/collabora/`-prefixed asset URLs for the iframe is a **Slice-4** task —
  proxy-prefix done right, a `<base>` tag, or a dedicated origin. The admin console is additionally
  hard-404'd at the proxy as defence-in-depth.) A **minimal framing CSP** (`frame-src 'self';
  frame-ancestors 'self'`) is added (CSP is greenfield here); a full `script-src`/`style-src` CSP
  is future hardening.
- **Build posture: the prebuilt `collabora/code` image is used for the dev stack and all
  integration slices.** Research settled the licence question: the cap is gone in current CODE,
  "not for production" is a support/warranty framing (not a licence prohibition), internal
  self-hosted non-redistributed use is defensible, and we hide Collabora chrome via our own UI +
  CSS (officially permitted for self-hosted installs). The clean unbranded / supported
  **production** posture — **self-build from MPL-2.0 source OR a Collabora subscription** — is a
  **deferred decision**, triggered at real productionisation (recorded in `docs/fork/MILESTONES.md`).
  Engine behaviour is identical between prebuilt and self-built, so deferring it blocks nothing.

## Consequences

- **(+)** A production-grade engine with real tracked-changes/comment fidelity; the agent resumes
  through the existing C5a path with **zero new agent code**; copyleft is **weak/file-level MPL-2.0
  (+ LGPLv3+/BSD/OFL/MPL-1.1), server-side, in a separate unmodified container — no AGPL, no
  network copyleft** — strictly **lighter than the accepted PyMuPDF AGPL** (NOTICES.md).
- **(+)** Strong isolation by construction: no host port, MKNOD-only, WOPI allow-list = `api`,
  admin console unreachable, untrusted documents confined to the sandboxed container.
- **(−)** A new SBOM / CVE-patch surface (pin by digest; re-pin + re-run the Spike-0 fidelity
  corpus on every bump). The **clean unbranded/supported production posture is deferred** (build or
  subscribe) — it must be decided before any real deployment, not before internal use.
- **(−)** Residual in-canvas chrome (context menus, dialogs, a thin toolbar strip) is
  LibreOffice-rendered and can be covered/themed but not deleted — accepted as the cost of a real
  engine (Slice 4 reskin).
- **(deferred)** The WOPI host endpoints + file-scoped token + cross-user-404 (Slice 2), save-back
  as a new user-authored `File` version (Slice 3), the cockpit editor panel + reskin/postMessage
  (Slice 4), and hand-back → agent resume (Slice 5) get their own slices; any architectural calls
  there extend or supersede this ADR.
- This ADR takes the next free fork number after **F046**; the WASM and custom-LOK paths are
  recorded as rejected so a future reader does not re-litigate them.

## Addendum — Slice 2: the WOPI host (2026-06-25)

Slice 2 implemented the WOPI **read** half (`api/app/api/wopi.py`): `CheckFileInfo`, `GetFile`, and
the **Lock family** (LOCK / GET_LOCK / REFRESH_LOCK / UNLOCK / UNLOCK_AND_RELOCK). These calls
materialise this ADR's "WOPI host endpoints + file-scoped token + cross-user-404" deferral. The
architectural calls made within that envelope (recorded here rather than minting a new ADR — F047
governs the editor):

- **Read-only viewer this slice.** `CheckFileInfo` advertises `UserCanWrite=false` / `ReadOnly=true`
  and omits `SupportsUpdate`, so the lawyer SEES the agent's redline with **no save path** — no
  data-loss window. Slice 3 flips to editable and adds `PutFile` atomically. (Milestone sequence:
  WOPI read → save-back.)
- **File-scoped editor token = a stateless signed JWT** (`create_wopi_token`, `typ="wopi"`), HS256
  on the existing `jwt_secret`, claims `sub`/`fid`/`name`/`exp`. No server-side session table.
  Three-layer authz: mint is gated by `ActiveUser` + `_load_visible_file` (cross-user → 404); the
  `fid` claim must equal the URL `{file_id}` (no cross-file replay); every WOPI handler re-runs
  `_load_visible_file(db, fid, claims.user_id)`. Token failure → **401**; file not visible → **404**.
  The router is mounted WITHOUT the user-bearer gate (same posture as `word_addin.public_router`).
- **Locks = a small `editor_locks` table** (migration `0074`, PK `file_id`, FK→files `CASCADE`,
  30-min TTL; expired ⇒ treated as unlocked). The WOPI lock state machine is a **pure function**
  (`app/schemas/wopi.decide_lock`) the handler wires DB I/O around — fully unit-tested incl. the
  409 + `X-WOPI-Lock`-echo / empty-string-when-unlocked semantics. `SupportsExtendedLockLength=true`
  → lock ids up to 1024 chars (`Text`). Implemented this slice (HANDOFF-recorded Slice-2 scope,
  de-risks Slice 3); a read-only session won't drive them live, so they're proven by unit tests + a
  curl smoke replicating Collabora's exact lock sequence.
- **`Version`/`X-WOPI-ItemVersion` = `File.hash_sha256`** (content-addressed); `OwnerId`/`UserId` =
  `uuid.hex` (WOPI requires **alphanumeric** — the hyphenated form is invalid).
- **No model calls; the host never reaches the gateway** (ADR-F010 trivially intact). Proof-key
  (`X-WOPI-Proof`) validation stays **deferred** — the threat model is the file-scoped short-TTL
  token + the private compose network + the `aliasgroup1` allow-list. New settings:
  `collabora_wopi_host` (WOPISrc base = `http://api:8000`), `wopi_token_ttl_seconds`,
  `collabora_post_message_origin`. No `docker-compose.yml`/nginx change (WOPI is server-to-server
  on the compose network).

## Addendum — Slice 3: PutFile save-back (2026-06-25)

Slice 3 made the session **editable** and added WOPI `PutFile`
(`POST /wopi/files/{id}/contents`, `X-WOPI-Override: PUT`) so the lawyer's edits in Collabora save
back. `CheckFileInfo` now advertises `UserCanWrite=true` / `SupportsUpdate=true` / `ReadOnly=false`
(`PutRelativeFile`/`RenameFile` stay disabled via `UserCanNotWriteRelative`). The architectural call
the kickoff flagged — **the version model** — was decided by the maintainer:

- **Version model = snapshot-then-mutate** (chosen over mutate-in-place-no-history and the rejected
  new-row-only, which would leave the editor's `WOPISrc` serving stale bytes on reload). WOPI requires
  the **row id** in the `WOPISrc` URL to keep serving the latest bytes; the **storage key** is
  internal, so we keep the ADR-0005 `key == row id` convention for *both* rows. On the **first** human
  save of an agent redline (`created_by_run_id` set), the agent's current bytes are **copied to a new
  immutable `File` row** (key `str(snapshot_id)`, provenance `created_by_run_id` carried over, name
  `… (agent draft).docx` → visible in the C7a Documents tab) **before** the live object is overwritten;
  the live row keeps its id, is mutated in place (new `hash`/`size`/`updated_at`), and flips to
  `created_by_run_id = NULL` (human-authored). Later saves just mutate in place (no per-autosave
  snapshot). A no-op autosave (identical hash) writes nothing and does not flip provenance. **Why:**
  the editor stays coherent across reloads AND the agent's work product is preserved as a recoverable
  prior version — the data-loss risk a plain mutate-in-place carries for legal work.
- **Data-safety ordering = two durable steps** (refined in adversarial review). Storage and DB are not
  one transaction, so the save-back is two commits so that a partial failure + the client's PutFile
  retry can neither re-snapshot the edited bytes nor lose the edit: **(1)** on the first human save,
  copy the agent's current bytes to the snapshot key (copy-first), then **commit the snapshot row +
  the provenance flip (`created_by_run_id → NULL`) BEFORE any overwrite**; **(2)** overwrite the live
  object, then commit the new `hash`/`size`/`updated_at`. Because the provenance flip is durable before
  the overwrite, a retry after a step-2 failure sees `created_by_run_id=NULL` and skips the snapshot
  entirely (it never copies the already-overwritten edited bytes under the agent's provenance — the bug
  a single-transaction ordering would have had). The overwrite precedes its own commit, so the edit is
  durable in storage before it is recorded; a step-2 commit failure self-heals on the idempotent retry.
  If step-1's commit fails the snapshot copy is a row-less orphan and is best-effort deleted (the live
  object is untouched).
- **GetFile streams chunked** (no pinned `Content-Length`). The row's `size_bytes` and the stored bytes
  are separate sources; during the brief self-healing window after a step-2 commit failure they can
  disagree, so pinning Content-Length to the row would emit a malformed response. Letting the ASGI
  layer use chunked transfer-encoding keeps the declared length equal to the bytes actually streamed
  (Collabora handles chunked GetFile). The same DB-vs-storage window theoretically affects the C7a
  `GET /files/{id}/content` download; that is a manual, rare path and is left as-is (a fix there would
  drop the download size header) — deferred, on record.
- **`files.updated_at`** (migration `0075`, nullable, additive) is the in-place save's last-modified
  stamp. PutFile is the only path that mutates bytes in place (every other path creates a new row), so
  `LastModifiedTime = updated_at or created_at` is now honest, and the **`X-COOL-WOPI-Timestamp`
  save-race backstop** (→ `409 {"COOLStatusCode": 1010}` when the stored file changed since the editor
  loaded it) is meaningful. PutFile's JSON response carries the new `LastModifiedTime` (the documented
  Collabora quirk).
- **Untrusted upload surface.** The PutFile body is browser-supplied bytes → a size cap
  (`lq_ai_max_upload_size_mb`, streamed → 413), the existing `guard_ooxml` (zip-bomb / XXE → 400), and
  a `ooxml_subtype == "docx"` check (reject a renamed `.xlsx`/`.pptx` → 400) gate every save. Lock
  enforcement reuses a pure `decide_putfile_lock` (held-lock mismatch → 409 + `X-WOPI-Lock` echo;
  unlocked or matching → proceed). Counts-only audit `editor.file_saved`. No model calls; no migration
  beyond `0075`; no new dependency (`copy_object` added to `app/storage.py`). Re-ingestion of edited
  content (RAG re-index) and a view/edit session toggle are out of scope (backlog); the agent-resume
  loop reads the `.docx` bytes directly (Adeu), so it is unaffected.

## Addendum — Slice 4: cockpit editor panel + asset-URL fix (2026-06-25)

Slice 4 is the browser half: the lawyer opens an agent-redlined `.docx` **in the cockpit** and the
Collabora editor renders + saves through the Slice-2/3 WOPI host. Two decisions resolved here.

- **Asset-URL fix = host Collabora at its NATIVE ROOT paths, NOT a sub-path** (the Slice-1 open
  question). `cool.html` references every asset by an **absolute root path** (`href="/browser/<hash>/
  bundle.css"`, …) and the editing websocket connects to `/cool/<wopisrc>/ws`; `data-service-root=""`
  confirms root hosting is coolwsd's intended mode. So Slice-1's `/collabora/` sub-path (which stripped
  the prefix) could never serve the iframe, and `net.proxy_prefix` does not fix it (coolwsd 400s on a
  prefixed path). The web nginx now reverse-proxies `/browser/`, `/cool/` (websocket-upgrade), and
  `/hosting/` straight through to `collabora:9980` with **no prefix strip**; the admin deny
  (`/cool/adminws`, `/cool/getMetrics`, `/browser/<hash>/admin` → 404) stays a regex location, which
  nginx evaluates *before* the plain-prefix proxy locations, so it still wins. `/browser/` and `/cool/`
  do not collide with the SvelteKit SPA (which lives under `/lq-ai`, `/_app`, `/api`).
- **Dev scheme = `ssl.termination=false`.** coolwsd builds asset/websocket URLs for the public scheme:
  `true` → `https`/`wss`, `false` → `http`/`ws`. The dev origin is plain HTTP, so the compose default
  is now `COLLABORA_SSL_TERMINATION=false` (→ `data-host="ws://…"`); **production, terminating TLS at
  the operator proxy, MUST set it `true`.** The frontend belt-and-braces this: it takes the discovery
  `urlsrc` **pathname only** and re-homes it on `window.location.origin`, so coolwsd's advertised
  `server_name`/scheme never has to match how the page is actually served.
- **Launch = standard WOPI form-POST.** `POST /files/{id}/editor-session` mints the file-scoped token;
  `GET /hosting/discovery` yields the loader `urlsrc`; the iframe `src` carries only `WOPISrc` (the host
  callback), and a hidden `<form method=POST target=iframe>` POSTs the `access_token` — so the token
  never lands in a URL/history, and Collabora never sees the user's session JWT. No backend change
  (`PostMessageOrigin` was already wired in CheckFileInfo); no migration; no new dependency.
- **UX (maintainer-specified) = slide-in beside the conversation, not an overlay/tab.** When the agent
  produces a redline (or the lawyer clicks *Edit* on a `.docx` in the Documents tab), the editor slides
  in from the **right** while the conversation stays on the **left** — so the lawyer edits the document
  and keeps talking to the agent side by side (the round-2 hand-back loop). The shell **gracefully
  collapses the practice-area rail** (a shared `cockpit.editorOpen` signal → `railPane.collapse()`,
  restored only if we collapsed it) and the in-card thread list yields, giving the conversation +
  editor the full width (on a narrow/stacked host the conversation card is hidden — kept mounted — so the
  editor takes the whole pane). The conversation **never remounts** when the editor opens/closes (the
  live-SSE invariant): it is always the first flex child; the editor is a sibling that flies in. Auto-open
  fires only for a **freshly** produced redline: the panel snapshots the redline ids that exist when the
  thread is first opened (a memoized baseline captured eagerly when the matter is known — *not* on the first
  completed-run-driven file refresh, which in the headline "fresh conversation, first ask is a redline" flow
  would otherwise mark the new redline as already-seen and never open it) and announces only ids that appear
  later; it also yields to a document the lawyer is already editing rather than swapping it out.
- **Save-state chrome** maps Collabora's same-origin postMessage events (`App_LoadingStatus`,
  `Doc_ModifiedStatus`, `Action_Save_Resp`) to a Saved / Unsaved indicator; the listener rejects any
  message whose `event.origin` is not our own. Deeper de-branding of Collabora's in-canvas toolbar
  (Hide_Command / UI customisation, issue #13224) is incremental and deferred — Slice 4 delivers a
  clean framed editor under our charcoal chrome. Hand-back → agent resume is Slice 5.

## Addendum — Slice 4b: editor-panel polish (width, popups, fit-to-width) (2026-06-26)

Maintainer review of the live Slice-4 editor surfaced four UX defects; this slice fixes them
(frontend + compose only — no backend, migration, or new dependency).

- **Editor pane is 2/3 of the workspace, not 1/2.** The `ConversationHost` editor card is
  `flex-[2_1_0%]` against the conversation card's `flex-1` (2:1). Load-bearing companion fix: the
  `DocumentEditorPanel` root `<section>` carries `w-full` — without it the section is a flex child that
  shrinks to its content (~the iframe's intrinsic width) and leaves a wide blank gap to the right of
  the document inside the 2/3 slot (the maintainer's "white space as if reserved for a panel").
- **Collabora's "What's New" / feedback / update popups are suppressed.** The only lever that sticks on
  the prebuilt `collabora/code` image is `--o:home_mode.enable=true` (it is built
  `ENABLE_WELCOME_MESSAGE=1` and force-re-enables `welcome.enable` at boot otherwise), plus
  `--o:allow_update_popup=false`. **Trade-off:** `home_mode` also caps coolwsd to **20 concurrent
  connections / 10 open documents** — fine for an in-house embedded editor, env-overridable
  (`COLLABORA_HOME_MODE=false`), and the cap-free unbranded posture remains the deferred self-build
  productionisation decision (below).
- **Fit-to-width is computed in the client, by iteration, off the same-origin map.** Collabora opens a
  Writer doc at a stuck low zoom (~30%) and exposes **no zoom postMessage**, so we drive its internal
  client map (`iframe.contentWindow.app.map.setZoom`) directly — the editor is same-origin (the nginx
  proxy), which is what makes this reach legal; it is fully `try/catch`-guarded so a Collabora rename
  degrades to "keep Collabora's zoom", never a crash. Three findings shaped the algorithm, each found
  empirically (probe specs, since discarded):
  - The lifecycle is **driven by a poll**, not the one-shot `Document_Loaded` postMessage (that event
    is ~50/50 under load and the doc-pixel size lags it). The poll also installs a `ResizeObserver` so
    the page **re-fits on any later width change** (slide-in, the rail collapsing, a window resize).
  - The fit **iterates one zoom level at a time off the measured doc width**. Collabora's `getScaleZoom`
    reports a base-2 zoom delta, but its real pixel scaling is **~1.2×/level**, so a single computed
    jump lands far short (observed ~0.68 of the pane). The pure, unit-tested `nextFitAction` grows
    toward a 92–99% band and backs off one level on overflow (no horizontal scroll); discrete 1.2×
    steps mean the achieved fill is ~0.83–0.99 (≈0.98 at a 1920 pane).
  - Convergence is **gated on the measured pane width being stable across ticks** — Collabora's
    `getSize()` lags the iframe resize, so a shrink computed against a stale (large) width would look
    fitted and leave the doc overflowing the new, smaller pane. The poll also separates a long
    "waiting for the doc to boot" ceiling from the short post-ready iteration budget, so a ~15–20s cold
    boot never consumes the fit budget. A spinner overlay masks the cold-zoom→fit jump until converged.
- **Verification.** svelte-check 0 errors; Vitest **969** (6 new `nextFitAction` cases incl. a
  convergence/no-oscillation simulation); a live headed-Cypress check asserts the doc fills the pane
  (ratio ∈ [0.8, 1.0], no overflow) at **1920 / 1440 / 1024** (light + dark) — evidence in
  `docs/fork/evidence/libreoffice-slice4b/`.

The **internal-map reach is version-fragile by nature** (it uses `app.map` / `_docLayer._docPixelSize`
/ `getSize` / `setZoom`); it is isolated behind `getCoolMap()` + `nextFitAction`, fully guarded, and a
no-op degrades to Collabora's own (worse) default zoom rather than breaking the editor. If a future
Collabora ships a real fit-to-width host command, prefer it over this reach.
